"""Bounded ASGI observation of HTTP transactions without consuming streams."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .log_sanitizer import sanitize_body, scrub_text
from .request_instrumentation import (
    RequestTrace,
    new_request_id,
    reset_current_trace,
    safe_upstream_request_id,
    set_current_trace,
)
from .structured_logging import LoggingSettings, load_logging_settings, log_event

HTTP_LOGGER = logging.getLogger("http_transaction")
_MEDIA_PATTERN = re.compile(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+")
_SAFE_TEXT_TYPES = frozenset({"text/plain", "text/xml", "application/xml"})
_BINARY_TYPES = frozenset({
    "application/octet-stream", "application/pdf", "application/zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel", "text/csv", "multipart/form-data",
})


@dataclass(frozen=True)
class RouteLogPolicy:
    emit_events: bool = True
    request_body: bool = True
    response_body: bool = True


def route_log_policy(path: str) -> RouteLogPolicy:
    """Central policy; it has no effect on routing or authentication."""
    if path == "/static" or path.startswith("/static/"):
        return RouteLogPolicy(False, False, False)
    if path in {"/", "/app", "/analytics", "/api/health", "/docs",
                "/redoc", "/openapi.json", "/favicon.ico", "/knowledge-base/"}:
        return RouteLogPolicy(True, False, False)
    if path.startswith("/api/sessions/") and path.endswith("/download"):
        return RouteLogPolicy(True, False, False)
    if path in {"/api/ocr/extract", "/api/mass-answer"}:
        return RouteLogPolicy(True, False, False)
    return RouteLogPolicy()


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _media_type(value: str | None) -> str | None:
    if not value:
        return None
    media = value.split(";", 1)[0].strip().lower()
    return media if len(media) <= 128 and _MEDIA_PATTERN.fullmatch(media) else None


def _content_length(value: str | None) -> int | None:
    if value is None or len(value) > 20 or not value.isascii() or not value.isdigit():
        return None
    return int(value)


def _body_kind(media: str | None) -> str | None:
    if media is None or media in _BINARY_TYPES or media.startswith(("image/", "audio/", "video/")):
        return None
    if media == "application/json" or media.endswith("+json"):
        return "json"
    if media in _SAFE_TEXT_TYPES:
        return "text"
    return None


class _BodyObservation:
    """Copies no more than the configured limit, and only for allowed media."""

    def __init__(self, *, media: str | None, content_length: int | None,
                 enabled: bool, max_bytes: int):
        self.media = media
        self.content_length = content_length
        self.kind = _body_kind(media) if enabled else None
        self.max_bytes = max_bytes
        self.total_bytes = 0
        self.complete = False
        self._buffer = bytearray() if self.kind and (content_length is None or content_length <= max_bytes) else None

    @property
    def truncated(self) -> bool:
        return self.total_bytes > self.max_bytes or (
            self.content_length is not None and self.content_length > self.max_bytes
        )

    def observe(self, chunk: bytes, *, complete: bool) -> None:
        self.total_bytes += len(chunk)
        self.complete = complete
        if self._buffer is None:
            return
        remaining = self.max_bytes - len(self._buffer)
        if len(chunk) > remaining:
            self._buffer.clear()
            self._buffer = None
            return
        self._buffer.extend(chunk)

    def safe_metadata(self, *, hmac_secret: str | None) -> dict[str, Any]:
        original_size = self.total_bytes if self.complete else self.content_length
        result: dict[str, Any] = {
            "content_type": self.media,
            "content_length": self.content_length,
            "observed_size_bytes": self.total_bytes,
            "original_size_bytes": original_size,
            "body_truncated": self.truncated,
        }
        if self.truncated:
            result["body"] = "[TRUNCATED]"
            result["body_omitted"] = True
            self.clear()
            return result
        if self._buffer is None or not self.complete:
            result["body_omitted"] = True
            self.clear()
            return result
        if not self._buffer:
            result["body"] = None
            result["body_omitted"] = False
            self.clear()
            return result
        try:
            text = self._buffer.decode("utf-8")
            body = json.loads(text) if self.kind == "json" else text
            safe = sanitize_body(
                body, max_bytes=self.max_bytes, hmac_secret=hmac_secret,
                original_size_bytes=original_size,
            )
            result.update(safe)
            result["body_omitted"] = safe.get("body_truncated", False)
        except (UnicodeError, ValueError, TypeError, OverflowError):
            result["body_omitted"] = True
            result["body_parse_error"] = True
        finally:
            self.clear()
        return result

    def clear(self) -> None:
        if self._buffer is not None:
            self._buffer.clear()
            self._buffer = None


class HttpLoggingMiddleware:
    def __init__(self, app: Callable, settings: LoggingSettings | None = None,
                 logger: logging.Logger | None = None):
        self.app = app
        self.settings = settings or load_logging_settings()
        self.logger = logger or HTTP_LOGGER

    async def __call__(self, scope: dict, receive: Callable[[], Awaitable[dict]],
                       send: Callable[[dict], Awaitable[None]]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = scope.get("headers", [])
        trace = RequestTrace(
            request_id=new_request_id(),
            process_id=os.getpid(),
            upstream_request_id=safe_upstream_request_id(
                _header(request_headers, b"x-request-id")
            ),
        )
        trace.mark("request_received")
        token = set_current_trace(trace)
        path = scope.get("path", "")
        method = scope.get("method", "")
        policy = route_log_policy(path)
        safe_path = scrub_text(path, hmac_secret=self.settings.pii_hmac_secret,
                               max_chars=2048)
        safe_method = scrub_text(method, hmac_secret=self.settings.pii_hmac_secret,
                                 max_chars=32)
        request_media = _media_type(_header(request_headers, b"content-type"))
        request_body = _BodyObservation(
            media=request_media,
            content_length=_content_length(_header(request_headers, b"content-length")),
            enabled=policy.emit_events and policy.request_body and self.settings.request_body,
            max_bytes=self.settings.body_max_bytes,
        )
        response_body: _BodyObservation | None = None
        request_logged = False
        response_started = False
        response_complete = False
        status_code = 500
        error_type: str | None = None

        def safe_log(event: str, data: dict[str, Any]) -> None:
            if not policy.emit_events:
                return
            try:
                log_event(self.logger, event, data)
            except Exception:
                # Logging must not alter the application's HTTP behavior.
                pass

        def emit_request() -> None:
            nonlocal request_logged
            if request_logged:
                return
            request_logged = True
            try:
                details = request_body.safe_metadata(hmac_secret=self.settings.pii_hmac_secret)
            except Exception:
                request_body.clear()
                details = {"content_type": request_media, "body_omitted": True,
                           "logging_error": True}
            details["received_at"] = trace.received_timestamp
            safe_log("request_received", {
                "http": {"method": safe_method, "path": safe_path},
                "request": details,
            })

        async def observing_receive() -> dict:
            message = await receive()
            if message["type"] == "http.request":
                try:
                    request_body.observe(
                        message.get("body", b""),
                        complete=not message.get("more_body", False),
                    )
                    if request_body.complete:
                        emit_request()
                except Exception:
                    request_body.clear()
            return message

        async def observing_send(message: dict) -> None:
            nonlocal response_body, response_started, response_complete, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                raw_headers = list(message.get("headers", []))
                media = _media_type(_header(raw_headers, b"content-type"))
                response_body = _BodyObservation(
                    media=media,
                    content_length=_content_length(_header(raw_headers, b"content-length")),
                    enabled=(policy.emit_events and policy.response_body and self.settings.response_body
                             and not (request_media is not None and _body_kind(request_media) is None
                                      and method in {"POST", "PUT", "PATCH"})),
                    max_bytes=self.settings.body_max_bytes,
                )
                trace.mark("response_returned")
                additions = [(name.lower().encode("ascii"), value.encode("ascii"))
                             for name, value in trace.response_headers().items()]
                owned = {name for name, _ in additions}
                # Replace only instrumentation headers. Preserve every other
                # application header and do not mutate the original message.
                updated = dict(message)
                updated["headers"] = [(key, value) for key, value in raw_headers
                                      if key.lower() not in owned] + additions
                await send(updated)
                return
            if message["type"] == "http.response.body":
                if response_body is not None:
                    try:
                        response_body.observe(
                            message.get("body", b""),
                            complete=not message.get("more_body", False),
                        )
                    except Exception:
                        response_body.clear()
                await send(message)
                if response_body is not None and response_body.complete:
                    response_complete = True
                return
            await send(message)

        try:
            await self.app(scope, observing_receive, observing_send)
        except BaseException as exc:
            error_type = type(exc).__name__
            raise
        finally:
            try:
                try:
                    emit_request()
                    if policy.emit_events:
                        try:
                            response_details = (response_body.safe_metadata(
                                hmac_secret=self.settings.pii_hmac_secret
                            ) if response_body is not None else {
                                "body_omitted": True, "original_size_bytes": None,
                            })
                        except Exception:
                            if response_body is not None:
                                response_body.clear()
                            response_details = {"body_omitted": True, "logging_error": True}
                        response_details["complete"] = response_complete
                        data: dict[str, Any] = {
                            "http": {"method": safe_method, "path": safe_path,
                                     "status_code": status_code if response_started else 500},
                            "response": response_details,
                            "timing": {
                                "started_at": trace.received_timestamp,
                                "completed_at": datetime.now(timezone.utc).isoformat(),
                                "total_ms": trace.elapsed_ms(),
                                "durations_ms": dict(trace.durations_ms),
                                "admission_acquired": trace.admission_acquired,
                                "admission_outcome": trace.admission_outcome,
                                "admission_wait_ms": trace.admission_wait_ms,
                                "permit_hold_ms": trace.permit_hold_ms,
                            },
                        }
                        if error_type is not None:
                            data["error"] = {"type": error_type}
                        safe_log("response_completed", data)
                except Exception:
                    # Even unexpected preparation failures must not mask an
                    # endpoint response or replace its original exception.
                    pass
            finally:
                reset_current_trace(token)
