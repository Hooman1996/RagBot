"""Content-free request timing and correlation for the answering path."""

from __future__ import annotations

import contextvars
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from datetime import datetime, timezone


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_current_trace: contextvars.ContextVar[RequestTrace | None] = contextvars.ContextVar(
    "request_trace", default=None
)


def safe_request_id(candidate: str | None) -> str:
    """Accept a bounded opaque ID or generate one; never derive it from content."""

    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


@dataclass
class RequestTrace:
    request_id: str
    process_id: int
    received_ns: int = field(default_factory=time.perf_counter_ns)
    received_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    events_ns: dict[str, int] = field(default_factory=dict)
    durations_ms: dict[str, float] = field(default_factory=dict)
    admission_acquired: bool = False
    admission_outcome: str = "not_attempted"
    admission_wait_ms: float | None = None
    permit_hold_ms: float | None = None
    limiter_id: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def mark(self, event: str) -> int:
        now = time.perf_counter_ns()
        self.events_ns[event] = now
        return now

    def add_duration(self, name: str, elapsed_ms: float) -> None:
        self.durations_ms[name] = self.durations_ms.get(name, 0.0) + elapsed_ms

    def elapsed_ms(self) -> float:
        return (time.perf_counter_ns() - self.received_ns) / 1_000_000

    def set_diagnostic(self, name: str, value: Any) -> None:
        """Attach bounded, content-free request diagnostics."""

        self.diagnostics[name] = value

    def response_headers(self) -> dict[str, str]:
        headers = {
            "X-Request-Id": self.request_id,
            "X-Server-Receive-Time": self.received_timestamp,
            "X-Admission-Acquired": str(self.admission_acquired).lower(),
            "X-Admission-Outcome": self.admission_outcome,
            "X-Endpoint-Processing-Ms": f"{self.elapsed_ms():.3f}",
        }
        if self.admission_wait_ms is not None:
            headers["X-Admission-Wait-Ms"] = f"{self.admission_wait_ms:.3f}"
        if self.permit_hold_ms is not None:
            headers["X-Permit-Hold-Ms"] = f"{self.permit_hold_ms:.3f}"
        for stage, value in self.durations_ms.items():
            header = _STAGE_HEADERS.get(stage)
            if header:
                headers[header] = f"{value:.3f}"
        return headers


_STAGE_HEADERS = {
    "pre_admission": "X-Pre-Admission-Ms",
    "pipeline": "X-Pipeline-Ms",
    "authentication": "X-Authentication-Duration-Ms",
    "history": "X-History-Duration-Ms",
    "intent": "X-Intent-Duration-Ms",
    "rewrite": "X-Rewrite-Duration-Ms",
    "embedding": "X-Embedding-Duration-Ms",
    "qdrant_wait": "X-Qdrant-Wait-Ms",
    "qdrant": "X-Qdrant-Duration-Ms",
    "reranker": "X-Reranker-Duration-Ms",
    "vllm": "X-Vllm-Duration-Ms",
    "persistence": "X-Persistence-Duration-Ms",
    "response_build": "X-Response-Build-Ms",
    "blocking_wait": "X-Blocking-Wait-Ms",
    "post_generation": "X-Post-Generation-Ms",
}


def current_trace() -> RequestTrace | None:
    return _current_trace.get()


def set_current_trace(trace: RequestTrace) -> contextvars.Token[RequestTrace | None]:
    return _current_trace.set(trace)


def reset_current_trace(token: contextvars.Token[RequestTrace | None]) -> None:
    _current_trace.reset(token)


def mark_event(name: str) -> None:
    trace = current_trace()
    if trace is not None:
        trace.mark(name)


@asynccontextmanager
async def trace_span(name: str) -> AsyncIterator[None]:
    trace = current_trace()
    if trace is None:
        yield
        return
    trace.mark(f"{name}_start")
    started = time.perf_counter_ns()
    try:
        yield
    finally:
        ended = trace.mark(f"{name}_end")
        trace.add_duration(name, (ended - started) / 1_000_000)


def trace_summary(trace: RequestTrace) -> dict[str, Any]:
    """Return sanitized, content-free data suitable for structured logs/tests."""

    return {
        "request_id": trace.request_id,
        "process_id": trace.process_id,
        "limiter_id": trace.limiter_id,
        "admission_acquired": trace.admission_acquired,
        "admission_outcome": trace.admission_outcome,
        "admission_wait_ms": trace.admission_wait_ms,
        "permit_hold_ms": trace.permit_hold_ms,
        "total_ms": trace.elapsed_ms(),
        "durations_ms": dict(trace.durations_ms),
        "diagnostics": dict(trace.diagnostics),
    }
