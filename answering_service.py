"""Shared application-level answering semantics for web, mobile, and batch."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from utils.request_instrumentation import trace_span


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


@dataclass
class AnswerResult:
    original_query: str
    normalized_query: str
    rewritten_query: str
    intent: str
    answer: str
    related_questions: list[dict[str, str]] = field(default_factory=list)
    feedback_needed: bool = False
    timings_ms: dict[str, float] = field(default_factory=dict)


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
    ):
        self.agent_service = agent_service
        self.intent_classifier = intent_classifier
        self.history_rewriting_service = history_rewriting_service
        self.text_processor = text_processor
        self.blocking_runner = blocking_runner
        self.category_resolver = category_resolver

    async def answer(self, request: AnswerRequestContext) -> AnswerResult:
        if request.timeout_seconds is None:
            return await self._answer(request)
        return await asyncio.wait_for(
            self._answer(request), timeout=request.timeout_seconds
        )

    async def _answer(self, request: AnswerRequestContext) -> AnswerResult:
        timings: dict[str, float] = {}
        total_started = time.perf_counter()
        original_query = str(request.original_query).strip()
        if not original_query:
            raise ValueError("query is empty")

        normalized_query = await self._timed(
            timings,
            "normalization",
            self.blocking_runner.run(
                self.text_processor.normalize, original_query
            ),
        )
        normalized_query = str(normalized_query).strip()
        if not normalized_query:
            raise ValueError("query is empty after normalization")

        intent_data = await self._timed(
            timings,
            "intent_classification",
            self.intent_classifier.classify(normalized_query),
        )
        intent = str(intent_data.get("type") or "general")

        rewritten_query = normalized_query
        if request.use_history and intent != "chitchat":
            if not request.session_id:
                raise ValueError("session_id is required when history is enabled")
            history = await self._timed(
                timings,
                "history",
                self.blocking_runner.run(
                    self.history_rewriting_service.get_formatted_history_string,
                    current_chat_id=request.session_id,
                    max_turns=3,
                ),
            )
            rewritten_query = await self._timed(
                timings,
                "rewrite",
                self.history_rewriting_service.rewrite_query(
                    current_query=normalized_query,
                    current_summary=history,
                ),
            )

        documents = list(request.selected_documents)
        category = (
            self.category_resolver(documents[0]) if documents else None
        )
        graph_started = time.perf_counter()
        if request.persist_agent_state:
            if not request.session_id:
                raise ValueError(
                    "session_id is required when agent state persistence is enabled"
                )
            turn = await self.agent_service.process_message_detailed(
                session_id=request.session_id,
                user_message=original_query,
                selected_docs=documents,
                retrieval_query=rewritten_query,
                preclassified_intent=intent_data,
                doc_category=category,
            )
        else:
            turn = await self.agent_service.process_stateless_message(
                user_message=original_query,
                selected_docs=documents,
                retrieval_query=rewritten_query,
                preclassified_intent=intent_data,
                doc_category=category,
            )
        timings["graph"] = (time.perf_counter() - graph_started) * 1000
        timings["total"] = (time.perf_counter() - total_started) * 1000

        state = turn.state
        related = (
            list(state.get("related_questions", []))
            if request.include_related_questions
            else []
        )
        return AnswerResult(
            original_query=original_query,
            normalized_query=normalized_query,
            rewritten_query=rewritten_query,
            intent=intent,
            answer=turn.answer or "",
            related_questions=related,
            feedback_needed=bool(state.get("feedback_needed", False)),
            timings_ms=timings,
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
