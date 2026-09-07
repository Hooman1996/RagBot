"""Shared application-level answering semantics for web, mobile, and batch."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from utils.request_instrumentation import trace_span
from utils.service_errors import InvalidRequestError
from utils.persian_normalization import normalize_persian_text, query_fingerprint
from utils.request_instrumentation import current_trace
from utils.performance_config import (
    PIPELINE_DEBUG_SETTINGS,
    PipelineDebugSettings,
)
from conversation_history import (
    NO_CONVERSATION_HISTORY,
    PRODUCTION_EXECUTION_POLICY,
    ConversationHistoryProvider,
    TurnExecutionPolicy,
    canonical_history_messages,
    enforce_history_policy,
    format_rewrite_history,
)
from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query
from pipeline_observer import (
    PipelineObserver,
    PipelineStage,
    PipelineStageResult,
    TerminalPipelineObserver,
    bind_pipeline_observer,
    combine_pipeline_observers,
    emit_pipeline_stage_lazy,
    stable_hash,
)


@dataclass(frozen=True)
class AnswerRequestContext:
    original_query: str
    selected_documents: tuple[str, ...] = ()
    session_id: str | None = None
    channel: str = "web"
    use_history: bool = True
    persist_agent_state: bool = True
    include_related_questions: bool = True
    timeout_seconds: float | None = None
    conversation_key: object | None = None
    apply_mobile_empty_answer_fallback: bool = False


@dataclass
class AnswerResult:
    original_query: str
    normalized_query: str
    canonical_retrieval_query: str
    final_retrieval_query: str
    rewritten_query: str
    intent: str
    answer: str
    related_questions: list[dict[str, str]] = field(default_factory=list)
    feedback_needed: bool = False
    timings_ms: dict[str, float] = field(default_factory=dict)
    fallback_reason: str | None = None
    intent_details: dict[str, Any] = field(default_factory=dict)
    history_before: list[dict[str, str]] = field(default_factory=list)
    history_after: list[dict[str, str]] = field(default_factory=list)
    history_before_hash: str | None = None
    history_after_hash: str | None = None


class AnsweringService:
    """Own the semantic answer path without importing FastAPI request objects."""

    def __init__(
        self,
        *,
        agent_service,
        intent_classifier,
        history_rewriting_service,
        text_processor,
        blocking_runner,
        category_resolver: Callable[[str], str],
        selection_validator: Callable[[list[str]], list[str]] | None = None,
        history_provider: ConversationHistoryProvider | None = None,
        pipeline_debug_settings: PipelineDebugSettings | None = None,
    ):
        self.agent_service = agent_service
        self.intent_classifier = intent_classifier
        self.history_rewriting_service = history_rewriting_service
        self.text_processor = text_processor
        self.blocking_runner = blocking_runner
        self.category_resolver = category_resolver
        self.selection_validator = selection_validator
        self.history_provider = history_provider
        self.pipeline_debug_settings = (
            pipeline_debug_settings
            if pipeline_debug_settings is not None
            else PIPELINE_DEBUG_SETTINGS
        )

    async def answer(
        self,
        request: AnswerRequestContext,
        *,
        history_provider: ConversationHistoryProvider | None = None,
        observer: PipelineObserver | None = None,
        execution_policy: TurnExecutionPolicy = PRODUCTION_EXECUTION_POLICY,
    ) -> AnswerResult:
        terminal_observer = self._terminal_observer(request)
        active_observer = combine_pipeline_observers(observer, terminal_observer)
        try:
            with bind_pipeline_observer(active_observer):
                operation = self._answer(
                    request,
                    history_provider=history_provider,
                    execution_policy=execution_policy,
                )
                if request.timeout_seconds is None:
                    result = await operation
                else:
                    result = await asyncio.wait_for(
                        operation, timeout=request.timeout_seconds
                    )
        except BaseException as exc:
            if terminal_observer is not None:
                terminal_observer.finish(error=exc)
            raise
        if terminal_observer is not None:
            terminal_observer.finish(result=result)
        return result

    def _terminal_observer(
        self, request: AnswerRequestContext
    ) -> TerminalPipelineObserver | None:
        if not self.pipeline_debug_settings.enabled:
            return None
        try:
            trace = current_trace()
            conversation_key = (
                request.conversation_key
                if request.conversation_key is not None
                else request.session_id
            )
            return TerminalPipelineObserver(
                self.pipeline_debug_settings,
                raw_query=str(request.original_query),
                session_id=conversation_key,
                channel=request.channel,
                use_history=request.use_history,
                request_id=trace.request_id if trace is not None else None,
            )
        except BaseException:
            return None

    async def _answer(
        self,
        request: AnswerRequestContext,
        *,
        history_provider: ConversationHistoryProvider | None,
        execution_policy: TurnExecutionPolicy,
    ) -> AnswerResult:
        timings: dict[str, float] = {}
        total_started = time.perf_counter()
        original_query = str(request.original_query).strip()
        if not original_query:
            raise ValueError("query is empty")

        normalization_started = time.perf_counter()
        normalized_query = await self._timed(
            timings,
            "normalization",
            self.blocking_runner.run(self.text_processor.normalize, original_query),
        )
        normalized_query = normalize_persian_text(str(normalized_query).strip())
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.NORMALIZATION,
            input_data={"raw_query": original_query},
            output_data={"normalized_query": normalized_query},
            duration_ms=(time.perf_counter() - normalization_started) * 1000,
        ))
        if not normalized_query:
            raise ValueError("query is empty after normalization")

        trace = current_trace()
        if trace is not None:
            trace.set_diagnostic(
                "raw_query_fingerprint", query_fingerprint(original_query)
            )
            trace.set_diagnostic(
                "normalized_query_fingerprint",
                query_fingerprint(normalized_query),
            )

        provider = history_provider or self.history_provider
        conversation_key = (
            request.conversation_key
            if request.conversation_key is not None
            else request.session_id
        )
        enforce_history_policy(provider, execution_policy)

        history_messages: list[dict[str, str]] = []
        history = NO_CONVERSATION_HISTORY
        rewritten_query = normalized_query
        rewrite_used = False
        if request.use_history:
            if conversation_key is None:
                raise ValueError("session_id is required when history is enabled")
            if provider is None:
                history = await self._timed(
                    timings,
                    "history",
                    self.blocking_runner.run(
                        self.history_rewriting_service.get_formatted_history_string,
                        current_chat_id=request.session_id,
                        max_turns=3,
                    ),
                )
            else:
                history_messages = canonical_history_messages(
                    await self._timed(
                        timings,
                        "history",
                        provider.load_rewrite_messages(conversation_key),
                    )
                )
                history = format_rewrite_history(history_messages, max_turns=3)

            history_text = str(history or "").strip()
            real_history_exists = bool(
                history_text and history_text != NO_CONVERSATION_HISTORY
            )
            history_messages_used = (
                history_messages[-6:] if history_messages else []
            )
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.HISTORY,
                output_data={
                    "real_history_exists": real_history_exists,
                    "messages_used": history_messages_used,
                    "formatted_history": history_text,
                },
                metrics={
                    "history_message_count": len(history_messages),
                    "source": "provider" if provider is not None else "fallback",
                },
                duration_ms=timings.get("history"),
            ))
            if real_history_exists:
                rewrite_result = await self._timed(
                    timings,
                    "rewrite",
                    self.history_rewriting_service.rewrite_query(
                        current_query=normalized_query,
                        current_summary=history,
                    ),
                )
                rewrite_used = True
                normalized_rewrite = normalize_persian_text(
                    str(rewrite_result or "").strip()
                )
                rewritten_query = normalized_rewrite or normalized_query
            else:
                emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                    stage=PipelineStage.REWRITE,
                    status="SKIPPED",
                    input_data={"normalized_query": normalized_query},
                    output_data={
                        "rewritten_query": normalized_query,
                        "classification_query": normalized_query,
                    },
                    metrics={
                        "rewrite_used": False,
                        "reason": "NO_PRIOR_CONVERSATION",
                    },
                    duration_ms=0.0,
                ))
        else:
            real_history_exists = False
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.HISTORY,
                status="SKIPPED",
                output_data={
                    "real_history_exists": False,
                    "messages_used": [],
                    "formatted_history": "",
                },
                metrics={"reason": "HISTORY_DISABLED"},
                duration_ms=0.0,
            ))
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.REWRITE,
                status="SKIPPED",
                input_data={"normalized_query": normalized_query},
                output_data={
                    "rewritten_query": normalized_query,
                    "classification_query": normalized_query,
                },
                metrics={
                    "rewrite_used": False,
                    "reason": "HISTORY_DISABLED",
                },
                duration_ms=0.0,
            ))

        classification_query = (
            rewritten_query if rewrite_used else normalized_query
        )
        classify_detailed = getattr(
            self.intent_classifier, "classify_detailed", None
        ) or self.intent_classifier.classify
        classified = await self._timed(
            timings,
            "intent_classification",
            classify_detailed(classification_query),
        )
        intent_details = dict(classified)
        intent_data = {
            "type": classified.get("type") or "general",
            "scenario_id": classified.get("scenario_id"),
        }
        intent = str(intent_data.get("type") or "general")
        canonical_retrieval_query = classification_query
        if intent == "general":
            canonical_retrieval_query = canonicalize_retrieval_query(
                classification_query
            )
        final_retrieval_query = canonical_retrieval_query
        emit_pipeline_stage_lazy(lambda: PipelineStageResult(
            stage=PipelineStage.INTENT,
            input_data={"classifier_input": classification_query},
            output_data={
                **intent_details,
                "canonical_retrieval_query": canonical_retrieval_query,
                "final_retrieval_query": final_retrieval_query,
            },
            metrics={
                "effective_threshold": getattr(
                    self.intent_classifier, "threshold", None
                )
            },
            duration_ms=timings.get("intent_classification"),
        ))

        if intent == "chitchat":
            for skipped_stage in (
                PipelineStage.RETRIEVAL,
                PipelineStage.RERANK,
                PipelineStage.CONTEXT_SELECTION,
            ):
                emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                    stage=skipped_stage,
                    status="SKIPPED",
                    input_data={"query": final_retrieval_query},
                    output_data={"candidates": []},
                    metrics={"reason": "CHITCHAT"},
                    duration_ms=0.0,
                ))

        if trace is not None:
            trace.set_diagnostic(
                "rewrite_used", rewrite_used
            )
            trace.set_diagnostic(
                "canonical_query_fingerprint",
                query_fingerprint(canonical_retrieval_query),
            )
            trace.set_diagnostic(
                "rewritten_query_fingerprint",
                query_fingerprint(rewritten_query),
            )
            trace.set_diagnostic(
                "final_retrieval_query_fingerprint",
                query_fingerprint(final_retrieval_query),
            )

        requested_documents = list(request.selected_documents)
        if self.selection_validator is not None:
            documents = await self._timed(
                timings,
                "document_validation",
                self.blocking_runner.run(
                    self.selection_validator,
                    requested_documents,
                ),
            )
        else:
            documents = list(dict.fromkeys(
                str(document).strip()
                for document in requested_documents
                if str(document).strip()
            ))
        if intent == "general" and not documents:
            raise InvalidRequestError(
                "Select at least one current datasource before asking a knowledge question"
            )
        category = (
            self.category_resolver(documents[0]) if documents else None
        )
        graph_started = time.perf_counter()
        if request.persist_agent_state:
            if conversation_key is None:
                raise ValueError(
                    "session_id is required when agent state persistence is enabled"
                )
            turn = await self.agent_service.process_message_detailed(
                session_id=conversation_key,
                user_message=original_query,
                selected_docs=documents,
                retrieval_query=final_retrieval_query,
                preclassified_intent=intent_data,
                doc_category=category,
                history_provider=provider,
                execution_policy=execution_policy,
            )
        else:
            turn = await self.agent_service.process_stateless_message(
                user_message=original_query,
                selected_docs=documents,
                retrieval_query=final_retrieval_query,
                preclassified_intent=intent_data,
                doc_category=category,
            )
        timings["graph"] = (time.perf_counter() - graph_started) * 1000
        timings["total"] = (time.perf_counter() - total_started) * 1000

        state = turn.state
        actual_history_before = canonical_history_messages(
            list(getattr(turn, "history_before", None) or history_messages)
        )
        history_after = canonical_history_messages(
            list(state.get("messages") or [])
        )
        related = (
            list(state.get("related_questions", []))
            if request.include_related_questions
            else []
        )
        answer = turn.answer or ""
        fallback_reason = state.get("fallback_reason")
        if request.apply_mobile_empty_answer_fallback and not answer:
            answer = mobile_empty_answer_fallback(answer)
            fallback_reason = fallback_reason or "NO_ANSWER"
        return AnswerResult(
            original_query=original_query,
            normalized_query=normalized_query,
            canonical_retrieval_query=canonical_retrieval_query,
            final_retrieval_query=final_retrieval_query,
            rewritten_query=rewritten_query,
            intent=intent,
            answer=answer,
            related_questions=related,
            feedback_needed=bool(state.get("feedback_needed", False)),
            timings_ms=timings,
            fallback_reason=fallback_reason,
            intent_details=intent_details,
            history_before=actual_history_before,
            history_after=history_after,
            history_before_hash=stable_hash(actual_history_before),
            history_after_hash=stable_hash(history_after),
        )

    @staticmethod
    async def _timed(
        timings: dict[str, float], name: str, awaitable: Any
    ) -> Any:
        started = time.perf_counter()
        trace_name = {
            "intent_classification": "intent",
            "history": "history",
            "rewrite": "rewrite",
        }.get(name, name)
        try:
            async with trace_span(trace_name):
                return await awaitable
        finally:
            timings[name] = (time.perf_counter() - started) * 1000


def mobile_empty_answer_fallback(answer: str | None) -> str:
    """The exact mobile fallback, shared by production and evaluation."""

    return answer or "متاسفانه پاسخی دریافت نشد."
