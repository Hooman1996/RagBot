"""Versioned, safe JSON events written to stdout by one worker thread."""

from __future__ import annotations

import copy
import json
import logging
import os
import queue
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener
from typing import Any, TextIO

from .log_sanitizer import REDACTED, sanitize
from .request_instrumentation import current_trace

SCHEMA_VERSION = "1.0"
DEFAULT_QUEUE_SIZE = 4096


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class LoggingSettings:
    level: int = logging.INFO
    service: str = "ragbot"
    environment: str = "unknown"
    body_max_bytes: int = 32768
    request_body: bool = True
    response_body: bool = True
    pii_hmac_secret: str | None = None
    queue_size: int = DEFAULT_QUEUE_SIZE


def load_logging_settings() -> LoggingSettings:
    """Load safe settings; missing HMAC key means redaction, never raw PII."""
    name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = logging.getLevelName(name)
    if not isinstance(level, int) or name not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be a standard logging level")
    if os.getenv("LOG_FORMAT", "json").lower() != "json":
        raise ValueError("LOG_FORMAT must be json")
    if not _boolean("LOG_PII_REDACTION", True):
        raise ValueError("LOG_PII_REDACTION cannot be disabled")
    body_max_bytes = int(os.getenv("LOG_BODY_MAX_BYTES", "32768"))
    if not 1 <= body_max_bytes <= 262144:
        raise ValueError("LOG_BODY_MAX_BYTES must be between 1 and 262144")
    service = os.getenv("LOG_SERVICE_NAME", "ragbot")
    environment = os.getenv("LOG_ENVIRONMENT")
    if environment is None:
        environment = os.getenv("WEB_ENVIRONMENT")
    if environment is None:
        environment = os.getenv("ENVIRONMENT")
    if environment is None:
        environment = "unknown"
    if not service.isascii() or not service.replace("-", "").replace("_", "").isalnum() or len(service) > 64:
        raise ValueError("LOG_SERVICE_NAME must be a short ASCII identifier")
    if not environment.isascii() or not environment.replace("-", "").replace("_", "").isalnum() or len(environment) > 64:
        raise ValueError("ENVIRONMENT must be a short ASCII identifier")
    return LoggingSettings(
        level=level,
        service=service,
        environment=environment,
        body_max_bytes=body_max_bytes,
        request_body=_boolean("LOG_REQUEST_BODY", True),
        response_body=_boolean("LOG_RESPONSE_BODY", True),
        pii_hmac_secret=os.getenv("LOG_PII_HMAC_SECRET") or None,
    )


class RequestContextFilter(logging.Filter):
    """Capture ContextVar values before records cross the queue boundary."""

    def filter(self, record: logging.LogRecord) -> bool:
        trace = current_trace()
        record.ragbot_request_id = trace.request_id if trace else None
        record.ragbot_upstream_request_id = trace.upstream_request_id if trace else None
        return True


class JsonEventFormatter(logging.Formatter):
    def __init__(self, settings: LoggingSettings):
        super().__init__()
        self.settings = settings

    def format(self, record: logging.LogRecord) -> str:
        try:
            raw = getattr(record, "ragbot_event_data", None)
            event = raw.get("event") if isinstance(raw, dict) else "application_log"
            if not isinstance(event, str) or not event.isascii() or len(event) > 64:
                event = "application_log"
            data = raw.get("data", {}) if isinstance(raw, dict) else {}
            output: dict[str, Any] = {
                "@timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "schema_version": SCHEMA_VERSION,
                "service": self.settings.service,
                "environment": self.settings.environment,
                "event": event,
                "level": record.levelname,
                "request_id": getattr(record, "ragbot_request_id", None),
                "upstream_request_id": getattr(record, "ragbot_upstream_request_id", None),
                "process": {"pid": record.process},
            }
            if raw is not None:
                output["data"] = sanitize(data, hmac_secret=self.settings.pii_hmac_secret,
                                          max_chars=self.settings.body_max_bytes)
            else:
                # Legacy free-form messages and exception text may contain unknown
                # credentials. Retain safe metadata, never interpolate or emit them.
                output["logger"] = sanitize(record.name, hmac_secret=self.settings.pii_hmac_secret)
                output["message"] = REDACTED
                exception_type = getattr(record, "ragbot_exception_type", None)
                if exception_type:
                    output["exception_type"] = exception_type
            return json.dumps(output, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except Exception:
            # Do not stringify the failed object or the exception: either may
            # contain secrets. Keep this fallback valid and content-free.
            return json.dumps({
                "@timestamp": datetime.now(timezone.utc).isoformat(),
                "schema_version": SCHEMA_VERSION,
                "service": self.settings.service,
                "environment": self.settings.environment,
                "event": "logging_error",
                "level": "ERROR",
                "request_id": None,
                "upstream_request_id": None,
                "process": {"pid": os.getpid()},
            }, separators=(",", ":"))


class _SafeStdoutHandler(logging.StreamHandler):
    """Suppress stdlib diagnostic tracebacks when stdout itself fails."""

    def __init__(self, stream: TextIO):
        super().__init__(stream)
        self.write_errors = 0

    def handleError(self, record: logging.LogRecord) -> None:
        self.write_errors += 1


class _SafeQueueHandler(QueueHandler):
    """Bounded enqueue with synchronous fallback when saturated."""

    def __init__(self, log_queue: queue.Queue[logging.LogRecord], fallback: logging.Handler):
        super().__init__(log_queue)
        self.fallback = fallback
        self.overflow_count = 0
        self._lock = threading.Lock()

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        # QueueHandler.prepare would interpolate args and format traceback on
        # the request path. Keep only controlled event data and safe metadata.
        prepared = copy.copy(record)
        prepared.msg = ""
        prepared.args = None
        prepared.ragbot_exception_type = type(record.exc_info[1]).__name__ if record.exc_info else None
        prepared.exc_info = None
        prepared.exc_text = None
        prepared.stack_info = None
        return prepared

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            with self._lock:
                self.overflow_count += 1
            try:
                self.fallback.handle(record)
            except Exception:
                # Logging cannot change request behavior, even if stdout fails.
                pass

    def handleError(self, record: logging.LogRecord) -> None:
        # Avoid stdlib's traceback output, which can expose application data.
        with self._lock:
            self.overflow_count += 1


class _DrainableListener(QueueListener):
    def enqueue_sentinel(self) -> None:
        self.queue.put(self._sentinel)


class LoggingRuntime:
    def __init__(self, settings: LoggingSettings, stream: TextIO | None = None):
        self.settings = settings
        self.stream_handler = _SafeStdoutHandler(stream if stream is not None else sys.stdout)
        self.stream_handler.setFormatter(JsonEventFormatter(settings))
        self.queue: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=settings.queue_size)
        self.handler = _SafeQueueHandler(self.queue, self.stream_handler)
        self.handler.addFilter(RequestContextFilter())
        self.listener = _DrainableListener(self.queue, self.stream_handler, respect_handler_level=True)
        self.root = logging.getLogger()
        self.previous_level = self.root.level
        self.uvicorn_access = logging.getLogger("uvicorn.access")
        self.previous_access_disabled = self.uvicorn_access.disabled
        self.closed = False

    def start(self) -> "LoggingRuntime":
        self.listener.start()
        self.root.addHandler(self.handler)
        self.root.setLevel(self.settings.level)
        # Uvicorn's default access formatter writes plaintext URL/query data
        # to stdout. The structured HTTP pair replaces that access record.
        self.uvicorn_access.disabled = True
        return self

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.root.removeHandler(self.handler)
        self.root.setLevel(self.previous_level)
        self.uvicorn_access.disabled = self.previous_access_disabled
        self.listener.stop()
        self.stream_handler.close()


def start_logging(settings: LoggingSettings | None = None, stream: TextIO | None = None) -> LoggingRuntime:
    return LoggingRuntime(settings or load_logging_settings(), stream).start()


def log_event(logger: logging.Logger, event: str, data: dict[str, Any] | None = None,
              *, level: int = logging.INFO) -> None:
    """Send structured data to the configured logger without affecting callers."""
    try:
        logger.log(level, "", extra={"ragbot_event_data": {"event": event, "data": data or {}}})
    except Exception:
        pass
