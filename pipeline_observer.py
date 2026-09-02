"""Optional content-bearing pipeline observation for evaluation executions only.

The production default is a no-op.  This module never logs artifacts and is
deliberately separate from ``utils.request_instrumentation``.
"""

from __future__ import annotations

import contextvars
import dataclasses
import hashlib
import json
import math
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterator, Protocol, runtime_checkable


class PipelineStage(StrEnum):
    NORMALIZATION = "NORMALIZATION"
    INTENT = "INTENT"
    REWRITE = "REWRITE"
    RETRIEVAL = "RETRIEVAL"
    RERANK = "RERANK"
    CONTEXT_SELECTION = "CONTEXT_SELECTION"
    PROMPT_BUILD = "PROMPT_BUILD"
    GENERATION = "GENERATION"


STAGE_ORDER: dict[PipelineStage, int] = {
    PipelineStage.NORMALIZATION: 10,
    PipelineStage.INTENT: 20,
    PipelineStage.REWRITE: 30,
    PipelineStage.RETRIEVAL: 40,
    PipelineStage.RERANK: 50,
    PipelineStage.CONTEXT_SELECTION: 60,
    PipelineStage.PROMPT_BUILD: 70,
    PipelineStage.GENERATION: 80,
}


@dataclass(frozen=True)
class PipelineStageResult:
    stage: PipelineStage
    status: str = "COMPLETED"
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None
    error_code: str | None = None
    error_data: dict[str, Any] | None = None

    @property
    def stage_order(self) -> int:
        return STAGE_ORDER[self.stage]

    @property
    def input_hash(self) -> str | None:
        return stable_hash(self.input_data) if self.input_data is not None else None

    @property
    def output_hash(self) -> str | None:
        return stable_hash(self.output_data) if self.output_data is not None else None


@runtime_checkable
class PipelineObserver(Protocol):
    def record(self, result: PipelineStageResult) -> None: ...


class NoOpPipelineObserver:
    def record(self, result: PipelineStageResult) -> None:
        del result


NOOP_PIPELINE_OBSERVER = NoOpPipelineObserver()
_current_observer: contextvars.ContextVar[PipelineObserver] = contextvars.ContextVar(
    "pipeline_observer", default=NOOP_PIPELINE_OBSERVER
)


def current_pipeline_observer() -> PipelineObserver:
    return _current_observer.get()


@contextmanager
def bind_pipeline_observer(
    observer: PipelineObserver | None,
) -> Iterator[PipelineObserver]:
    active = observer or NOOP_PIPELINE_OBSERVER
    token = _current_observer.set(active)
    try:
        yield active
    finally:
        _current_observer.reset(token)


def emit_pipeline_stage(result: PipelineStageResult) -> None:
    """Best-effort observation: collector failures never affect decisions."""

    try:
        current_pipeline_observer().record(result)
    except Exception:
        # Intentionally do not log content or propagate observer failures.
        return


def emit_pipeline_stage_lazy(factory) -> None:
    """Construct content-bearing artifacts only when an observer is active."""

    if current_pipeline_observer() is NOOP_PIPELINE_OBSERVER:
        return
    try:
        current_pipeline_observer().record(factory())
    except Exception:
        return


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted((_jsonable(item) for item in value), key=repr)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def json_safe(value: Any) -> Any:
    """Return a detached JSON-compatible artifact for evaluation persistence."""

    return _jsonable(value)


def stable_hash(value: Any) -> str:
    if isinstance(value, str):
        payload = value
    else:
        payload = canonical_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
