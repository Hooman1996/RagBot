"""Optional content-bearing observation for evaluation and terminal debugging.

The production default is a no-op. This module never writes artifacts and is
deliberately separate from ``utils.request_instrumentation``.
"""

from __future__ import annotations

import contextvars
import dataclasses
import hashlib
import json
import math
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterator, Protocol, runtime_checkable

from utils.performance_config import PipelineDebugSettings


class PipelineStage(StrEnum):
    NORMALIZATION = "NORMALIZATION"
    HISTORY = "HISTORY"
    REWRITE = "REWRITE"
    INTENT = "INTENT"
    RETRIEVAL = "RETRIEVAL"
    RERANK = "RERANK"
    CONTEXT_SELECTION = "CONTEXT_SELECTION"
    PROMPT_BUILD = "PROMPT_BUILD"
    GENERATION = "GENERATION"


STAGE_ORDER: dict[PipelineStage, int] = {
    PipelineStage.NORMALIZATION: 10,
    PipelineStage.HISTORY: 20,
    PipelineStage.REWRITE: 30,
    PipelineStage.INTENT: 40,
    PipelineStage.RETRIEVAL: 50,
    PipelineStage.RERANK: 60,
    PipelineStage.CONTEXT_SELECTION: 70,
    PipelineStage.PROMPT_BUILD: 80,
    PipelineStage.GENERATION: 90,
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
    pipeline_hashes_enabled = False

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


class CompositePipelineObserver:
    """Fan out one real pipeline event to independent in-memory observers."""

    def __init__(self, *observers: PipelineObserver):
        self.observers = tuple(observers)
        self.pipeline_hashes_enabled = any(
            getattr(observer, "pipeline_hashes_enabled", True)
            for observer in self.observers
        )

    def record(self, result: PipelineStageResult) -> None:
        for observer in self.observers:
            try:
                observer.record(result)
            except Exception:
                continue


def combine_pipeline_observers(
    *observers: PipelineObserver | None,
) -> PipelineObserver:
    active = tuple(observer for observer in observers if observer is not None)
    if not active:
        return NOOP_PIPELINE_OBSERVER
    if len(active) == 1:
        return active[0]
    return CompositePipelineObserver(*active)


def pipeline_hashes_enabled() -> bool:
    """Keep evaluation hashes while avoiding hash work for terminal debugging."""

    observer = current_pipeline_observer()
    return bool(getattr(observer, "pipeline_hashes_enabled", True))


_STDOUT_PRINT_LOCK = threading.Lock()
_RULE = "=" * 70
_SUBRULE = "-" * 70


def _print_pipeline_report(report: str) -> None:
    """Emit one cohesive request block while holding only the stdout lock."""

    with _STDOUT_PRINT_LOCK:
        print(report, flush=True)


class TerminalPipelineObserver:
    """Collect one request in memory and render it once to stdout."""

    pipeline_hashes_enabled = False

    def __init__(
        self,
        settings: PipelineDebugSettings,
        *,
        raw_query: str,
        session_id: object | None,
        channel: str,
        use_history: bool,
        request_id: str | None = None,
    ) -> None:
        self.settings = settings
        self.raw_query = raw_query
        self.session_id = session_id
        self.channel = channel
        self.use_history = use_history
        self.request_id = request_id or uuid.uuid4().hex
        self._started = time.perf_counter()
        self._records: list[PipelineStageResult] = []
        self._finished = False

    def record(self, result: PipelineStageResult) -> None:
        self._records.append(result)

    @property
    def records(self) -> tuple[PipelineStageResult, ...]:
        return tuple(self._records)

    def finish(self, *, result: Any = None, error: BaseException | None = None) -> None:
        """Best-effort formatting and output; debugging can never fail a request."""

        if self._finished:
            return
        self._finished = True
        try:
            report = self.build_report(result=result, error=error)
            _print_pipeline_report(report)
        except BaseException:
            return

    def build_report(
        self, *, result: Any = None, error: BaseException | None = None
    ) -> str:
        lines = [
            _RULE,
            "                        RAGBOT PIPELINE",
            _RULE,
            f"Request      : {self.request_id}",
            f"Session      : {self.session_id if self.session_id is not None else '[none]'}",
            f"Channel      : {self.channel}",
            f"History mode : {'ENABLED' if self.use_history else 'DISABLED'}",
            _SUBRULE,
        ]

        normalization = self._record(PipelineStage.NORMALIZATION)
        history = self._record(PipelineStage.HISTORY)
        rewrite = self._record(PipelineStage.REWRITE)
        intent = self._record(PipelineStage.INTENT)
        retrieval = self._record(PipelineStage.RETRIEVAL)
        rerank = self._record(
            PipelineStage.RERANK,
            lambda item: item.metrics.get("purpose") == "answer_context",
        ) or self._record(PipelineStage.RERANK)
        context = self._record(PipelineStage.CONTEXT_SELECTION)
        prompt = self._record(PipelineStage.PROMPT_BUILD)
        generation = self._record(
            PipelineStage.GENERATION,
            lambda item: "model" in item.metrics,
        ) or self._record(PipelineStage.GENERATION)

        if self.settings.displays("query"):
            self._section(lines, "[1] USER QUERY")
            lines.append(self.raw_query)

        if self.settings.displays("normalization"):
            self._section(lines, "[2] NORMALIZATION", self._duration(normalization))
            normalized = self._output(normalization, "normalized_query")
            raw_input = self._input(normalization, "raw_query", self.raw_query)
            self._label_value(lines, "INPUT", raw_input)
            self._label_value(lines, "OUTPUT", normalized)
            self._label_value(lines, "CHANGED", self._yes_no(raw_input != normalized))

        if self.settings.displays("history"):
            self._section(lines, "[3] HISTORY", self._duration(history))
            real_history = bool(self._output(history, "real_history_exists", False))
            lines.append(f"Enabled       : {self._yes_no(self.use_history)}")
            lines.append(f"Prior history : {self._yes_no(real_history)}")
            messages = self._output(history, "messages_used", []) or []
            if messages:
                lines.append(f"Messages used : {len(messages)}")
                lines.append("")
                for message in messages:
                    role = str(message.get("role", "")).lower()
                    speaker = "Assistant" if role in {"assistant", "ai", "model"} else "User"
                    self._label_value(lines, speaker, message.get("content", ""))
            elif real_history:
                formatted = self._output(history, "formatted_history", "")
                if formatted:
                    self._label_value(lines, "History used", formatted)

        if self.settings.displays("rewrite"):
            self._section(lines, "[4] QUERY REWRITE", self._duration(rewrite))
            status = rewrite.status if rewrite is not None else "UNKNOWN"
            rewrite_used = bool(
                self._metric(rewrite, "rewrite_used", status != "SKIPPED")
            )
            lines.append(f"Used   : {self._yes_no(rewrite_used)}")
            if status == "SKIPPED":
                lines.append("Status : SKIPPED")
                reason = self._metric(rewrite, "reason")
                if reason is not None:
                    lines.append(f"Reason : {reason}")
            else:
                rewrite_input = self._input(
                    rewrite,
                    "original_query",
                    self._result_value(result, "normalized_query", ""),
                )
                rewrite_output = self._output(
                    rewrite,
                    "rewritten_query",
                    self._result_value(result, "rewritten_query", ""),
                )
                self._label_value(lines, "INPUT", rewrite_input)
                self._label_value(lines, "OUTPUT", rewrite_output)
                self._label_value(
                    lines, "CHANGED", self._yes_no(rewrite_input != rewrite_output)
                )

        if self.settings.displays("intent"):
            self._section(lines, "[5] INTENT CLASSIFICATION", self._duration(intent))
            classifier_input = self._input(intent, "classifier_input", "")
            self._label_value(lines, "INPUT", classifier_input)
            intent_output = intent.output_data if intent and intent.output_data else {}
            for label, key in (
                ("TYPE", "type"),
                ("SELECTED CLASS", "selected_class"),
                ("class_id", "class_id"),
                ("p_actionable", "p_actionable"),
                ("p_chitchat", "p_chitchat"),
            ):
                if key in intent_output:
                    self._label_value(lines, label, intent_output[key])
            threshold = intent_output.get("effective_threshold")
            if threshold is None:
                threshold = self._metric(intent, "effective_threshold")
            if threshold is not None:
                self._label_value(lines, "threshold", threshold)

        self._section(lines, "[6] EFFECTIVE QUERY")
        normalized_query = self._result_value(
            result, "normalized_query", self._output(normalization, "normalized_query", "")
        )
        rewritten_query = self._result_value(
            result, "rewritten_query", self._output(rewrite, "rewritten_query", normalized_query)
        )
        canonical_query = self._result_value(
            result,
            "canonical_retrieval_query",
            self._output(intent, "canonical_retrieval_query", "[not available]"),
        )
        final_query = self._result_value(
            result,
            "final_retrieval_query",
            self._output(intent, "final_retrieval_query", "[not available]"),
        )
        result_intent = self._result_value(result, "intent", self._output(intent, "type", ""))
        self._label_value(lines, "Normalized", normalized_query)
        self._label_value(lines, "Rewritten", rewritten_query)
        self._label_value(lines, "Canonical", canonical_query)
        self._label_value(
            lines,
            "FINAL RETRIEVAL QUERY",
            "[not used - chitchat]" if result_intent == "chitchat" else final_query,
        )

        if self.settings.displays("retrieval"):
            self._render_retrieval(lines, retrieval)
        if self.settings.displays("rerank"):
            self._render_rerank(lines, rerank)
        if self.settings.displays("context"):
            self._render_context(lines, context)

        self._render_prompt(lines, prompt, generation)

        if self.settings.displays("answer"):
            self._section(lines, "[11] FINAL ANSWER", self._duration(generation))
            metrics = generation.metrics if generation else {}
            for label, keys in (
                ("Model", ("model",)),
                ("temperature", ("temperature", "generation_temperature")),
                ("top_p", ("top_p", "generation_top_p")),
                ("seed", ("seed", "generation_seed")),
                ("max_tokens", ("max_tokens",)),
            ):
                value = self._first(metrics, *keys)
                if value is not None:
                    lines.append(f"{label:<12}: {value}")
            lines.append("")
            lines.append(str(self._result_value(
                result, "answer", self._output(generation, "answer", "")
            )))

        if self.settings.displays("timings"):
            self._render_timings(lines, result)

        if error is not None:
            lines.extend([
                _RULE,
                "ERROR",
                _RULE,
                f"Type    : {type(error).__name__}",
                f"Message : {error}",
            ])
        if not lines or lines[-1] != _RULE:
            lines.append(_RULE)
        return "\n".join(lines)

    def _render_retrieval(
        self, lines: list[str], record: PipelineStageResult | None
    ) -> None:
        self._section(lines, "[7] HYBRID RETRIEVAL", self._duration(record))
        if record is not None and record.status == "SKIPPED":
            lines.append(f"SKIPPED - {self._metric(record, 'reason', 'UNKNOWN')}")
            return
        candidates = self._output(record, "candidates", []) or []
        lines.append("Rank | Chunk ID        | Score         | Source")
        lines.append("-----+-----------------+---------------+-------------------------")
        for position, candidate in enumerate(candidates, start=1):
            metadata = candidate.get("metadata") or {}
            rank = candidate.get("rank", position)
            chunk_id = candidate.get("chunk_id", "")
            score = self._first(candidate, "retrieval_score", "hybrid_score", "score")
            source = self._metadata(metadata, "source", "document_name", "file", "filename")
            lines.append(
                f"{str(rank):<4} | {str(chunk_id)[:15]:<15} | "
                f"{self._format_score(score):<13} | {source or ''}"
            )
            extras = []
            for label, key in (("page", "page"), ("category", "category")):
                value = self._metadata(metadata, key)
                if value is not None:
                    extras.append(f"{label}={value}")
            preview = str(candidate.get("content") or "").replace("\n", " ")[:150]
            if extras or preview:
                suffix = f" | {'; '.join(extras)}" if extras else ""
                lines.append(f"     preview: {preview}{suffix}")

    def _render_rerank(
        self, lines: list[str], record: PipelineStageResult | None
    ) -> None:
        rankings = self._output(record, "rankings", []) or []
        selected = [item for item in rankings if item.get("selected", True)]
        title = f"[8] BGE RERANK - FINAL TOP {len(selected)}"
        self._section(lines, title, self._duration(record))
        if record is not None and record.status == "SKIPPED":
            lines.append(f"SKIPPED - {self._metric(record, 'reason', 'UNKNOWN')}")
            return
        for position, candidate in enumerate(selected, start=1):
            metadata = candidate.get("metadata") or {}
            lines.append(f"#{position}")
            for label, keys in (
                ("chunk_id", ("chunk_id",)),
                ("retrieval_rank", ("original_rrf_rank", "retrieval_rank")),
                ("retrieval_score", ("hybrid_score", "retrieval_score")),
                ("rerank_score", ("reranker_score", "rerank_score")),
            ):
                value = self._first(candidate, *keys)
                if value is not None:
                    lines.append(f"{label:<16}: {value}")
            for label, keys in (
                ("source", ("source", "document_name", "file", "filename")),
                ("page", ("page",)),
                ("category", ("category",)),
            ):
                value = self._metadata(metadata, *keys)
                if value is not None:
                    lines.append(f"{label:<16}: {value}")
            lines.append("")
            lines.append("BGE INPUT:")
            lines.append(f"   {str(candidate.get('rerank_text') or '')}")
            lines.append("")
            lines.append("ORIGINAL CONTENT:")
            lines.append(f"   {self._chunk_preview(str(candidate.get('content') or ''))}")
            lines.append(_SUBRULE)

    def _render_context(
        self, lines: list[str], record: PipelineStageResult | None
    ) -> None:
        self._section(lines, "[9] CONTEXT SELECTION", self._duration(record))
        if record is not None and record.status == "SKIPPED":
            lines.append(f"SKIPPED - {self._metric(record, 'reason', 'UNKNOWN')}")
            return
        category = self._input(record, "category")
        selected_ids = self._output(record, "selected_chunk_ids", []) or []
        if category is not None:
            self._label_value(lines, "Category", category)
        lines.append("Selected chunks:")
        for position, chunk_id in enumerate(selected_ids, start=1):
            lines.append(f"   {position}. {chunk_id}")
        lines.append("")
        lines.append(f"Selected count: {len(selected_ids)}")

    def _render_prompt(
        self,
        lines: list[str],
        prompt: PipelineStageResult | None,
        generation: PipelineStageResult | None,
    ) -> None:
        self._section(lines, "[10] GENERATION PROMPT", self._duration(prompt))
        system_message = str(self._output(prompt, "system_message", ""))
        user_prompt = str(self._output(prompt, "user_prompt", ""))
        model = self._metric(generation, "model")
        lines.append(f"System prompt chars : {len(system_message)}")
        lines.append(f"User prompt chars   : {len(user_prompt)}")
        if model is not None:
            lines.append(f"Model               : {model}")
        if not self.settings.displays("prompt"):
            return
        lines.extend([
            "",
            "----- BEGIN SYSTEM PROMPT -----",
            system_message,
            "----- END SYSTEM PROMPT -------",
            "",
            "----- BEGIN USER PROMPT -------",
            user_prompt,
            "----- END USER PROMPT ---------",
        ])

    def _render_timings(self, lines: list[str], result: Any) -> None:
        lines.extend([_RULE, "TIMINGS", _RULE])
        result_timings = dict(getattr(result, "timings_ms", {}) or {})
        stage_names = (
            ("normalization", PipelineStage.NORMALIZATION),
            ("history", PipelineStage.HISTORY),
            ("rewrite", PipelineStage.REWRITE),
            ("intent", PipelineStage.INTENT),
            ("retrieval", PipelineStage.RETRIEVAL),
            ("rerank", PipelineStage.RERANK),
            ("context_selection", PipelineStage.CONTEXT_SELECTION),
            ("generation", PipelineStage.GENERATION),
        )
        for label, stage in stage_names:
            key = "intent_classification" if label == "intent" else label
            selected = self._record(
                stage,
                (lambda item: item.metrics.get("purpose") == "answer_context")
                if stage == PipelineStage.RERANK
                else None,
            )
            value = self._duration(selected)
            if value is None:
                value = result_timings.get(key)
            if value is not None:
                lines.append(f"{label:<20} : {value:9.2f} ms")
        graph = result_timings.get("graph")
        if graph is not None:
            lines.append(f"{'graph':<20} : {graph:9.2f} ms")
        total = result_timings.get("total")
        if total is None:
            total = (time.perf_counter() - self._started) * 1000
        lines.extend([_SUBRULE, f"{'TOTAL':<20} : {total:9.2f} ms"])

    def _record(self, stage: PipelineStage, predicate=None) -> PipelineStageResult | None:
        for record in reversed(self._records):
            if record.stage == stage and (predicate is None or predicate(record)):
                return record
        return None

    @staticmethod
    def _duration(record: PipelineStageResult | None) -> float | None:
        return record.duration_ms if record is not None else None

    @staticmethod
    def _input(record: PipelineStageResult | None, key: str, default=None):
        return (record.input_data or {}).get(key, default) if record else default

    @staticmethod
    def _output(record: PipelineStageResult | None, key: str, default=None):
        return (record.output_data or {}).get(key, default) if record else default

    @staticmethod
    def _metric(record: PipelineStageResult | None, key: str, default=None):
        return record.metrics.get(key, default) if record else default

    @staticmethod
    def _result_value(result: Any, key: str, default=None):
        return getattr(result, key, default) if result is not None else default

    @staticmethod
    def _first(mapping: dict[str, Any], *keys: str):
        for key in keys:
            if key in mapping and mapping[key] is not None:
                return mapping[key]
        return None

    @classmethod
    def _metadata(cls, metadata: dict[str, Any], *keys: str):
        return cls._first(metadata, *keys)

    @staticmethod
    def _yes_no(value: bool) -> str:
        return "YES" if value else "NO"

    @staticmethod
    def _format_score(value: Any) -> str:
        return "" if value is None else str(value)

    def _chunk_preview(self, content: str) -> str:
        if self.settings.full_chunks or len(content) <= self.settings.chunk_max_chars:
            return content
        return (
            content[: self.settings.chunk_max_chars]
            + "... [terminal preview truncated]"
        )

    @staticmethod
    def _section(lines: list[str], title: str, duration_ms: float | None = None) -> None:
        lines.append("")
        suffix = f"{duration_ms:.2f} ms" if duration_ms is not None else ""
        lines.append(f"{title:<54}{suffix:>16}")
        lines.append(_SUBRULE)

    @staticmethod
    def _label_value(lines: list[str], label: str, value: Any) -> None:
        lines.extend([f"{label}:", f"   {value}", ""])


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
