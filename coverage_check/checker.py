"""One question through the chat's own path up to retrieval, then batch judging.

Normalization, intent and the retrieval query are computed exactly as
``AnsweringService._answer`` does for a single question with no history.
Only the retrieval depth and the rerank ``top_k`` differ.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from coverage_check import prompts
from pipeline_observer import bind_pipeline_observer
from utils.concurrency import run_with_limit
from utils.faq_content import parse_faq_content
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.persian_normalization import normalize_persian_text
from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query

RESULTS = ("answered", "answered_combined", "partial", "not_answered", "chitchat", "error")


class CheckError(Exception):
    """A row error with a fixed code; never carries exception text."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class _Chunk:
    chunk_id: str
    content: str
    rank: int
    title: str | None


@dataclass
class _Row:
    result: str | None = None
    intent: str | None = None
    answer_batch: int | None = None
    answer_phase: str | None = None
    answer_chunk_ids: list[str] = field(default_factory=list)
    batches: list[dict] = field(default_factory=list)
    combines: list[dict] = field(default_factory=list)
    titles: dict[str, str | None] = field(default_factory=dict)
    broader_used: bool = False
    retrievals: int = 0
    model_calls: int = 0
    error_code: str | None = None
    note: str | None = None


def faq_title(content: str) -> str | None:
    try:
        parts = parse_faq_content(str(content))
    except ValueError:
        return None
    return parts.question if parts.is_qa else None


class CoverageChecker:
    """Checks one question at a time with a run's stored settings."""

    def __init__(self, answering_service, limiter, documents: list[str], settings: dict):
        self.answering = answering_service
        self.rag = answering_service.agent_service.rag_system
        self.limiter = limiter
        self.documents = list(documents)
        self.settings = settings

    async def _limited(self, operation):
        """One admission slot per call, so chat keeps its admission limit."""
        async def guarded():
            with bind_pipeline_observer(None):
                return await operation()
        return await asyncio.wait_for(
            run_with_limit(self.limiter, guarded,
                           acquire_timeout=PERFORMANCE_SETTINGS.request_admission_timeout_seconds),
            PERFORMANCE_SETTINGS.application_request_timeout_seconds)

    async def check(self, question: str) -> dict:
        started = time.perf_counter()
        row = _Row()
        try:
            await self._check(str(question), row)
        except CheckError as exc:
            row.result, row.error_code = "error", exc.code
        result = {
            "result": row.result, "intent": row.intent,
            "answer_batch": row.answer_batch, "answer_phase": row.answer_phase,
            "answer_chunk_ids": row.answer_chunk_ids, "batches": row.batches,
            "combines": row.combines, "titles": row.titles, "broader_used": row.broader_used,
            "retrievals": row.retrievals, "model_calls": row.model_calls,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "error_code": row.error_code, "note": row.note,
        }
        return result

    async def _check(self, question: str, row: _Row) -> None:
        original = question.strip()
        if not original:
            raise CheckError("empty_query")
        # 1. Normalize, as the chat does.
        try:
            normalized = await self.answering.blocking_runner.run(
                self.answering.text_processor.normalize, original)
        except Exception:
            raise CheckError("normalization_failed") from None
        normalized = normalize_persian_text(str(normalized).strip())
        if not normalized:
            raise CheckError("empty_query")
        # 2. Intent, as the chat does.
        classifier = self.answering.intent_classifier
        classify = getattr(classifier, "classify_detailed", None) or classifier.classify
        try:
            classified = await self._limited(lambda: classify(normalized))
            intent = str(dict(classified).get("type") or "general")
        except Exception:
            raise CheckError("intent_failed") from None
        row.intent = intent
        if intent == "chitchat":
            row.result = "chitchat"
            return
        # 3. Retrieval query, as the chat does.
        query = canonicalize_retrieval_query(normalized) if intent == "general" else normalized

        settings = self.settings
        judged: list[_Chunk] = []
        partial_chunks: list[_Chunk] = []
        combined_ids: list[str] | None = None
        any_partial = False

        phases = [("initial", settings["depth"], settings["keep"])]
        if settings["broader_enabled"]:
            phases.append(("broader", settings["broader_depth"], settings["broader_keep"]))
        for phase, depth, keep in phases:
            if phase == "broader":
                row.broader_used = True
                seen = {chunk.chunk_id for chunk in judged}
                ranked = await self._retrieve(query, depth, None, row)
                candidates = [c for c in ranked if str(c.doc_id) not in seen][:keep]
            else:
                candidates = await self._retrieve(query, depth, keep, row)
            chunks = []
            for candidate in candidates:
                chunk = _Chunk(str(candidate.doc_id), str(candidate.content), len(judged) + len(chunks),
                               faq_title(candidate.content))
                chunks.append(chunk)
                row.titles[chunk.chunk_id] = chunk.title
            judged.extend(chunks)
            # 6-7. Judge consecutive batches in rank order; stop at the first complete.
            size = settings["batch_size"]
            for start in range(0, len(chunks), size):
                batch = chunks[start:start + size]
                number = len(row.batches) + 1
                verdict = await self._judge("batch", query, batch, row)
                relied = [batch[n - 1] for n in verdict.chunk_numbers]
                row.batches.append({
                    "number": number, "phase": phase, "verdict": verdict.verdict,
                    "chunk_ids": [c.chunk_id for c in batch],
                    "relied_chunk_ids": [c.chunk_id for c in relied], "note": verdict.note})
                row.note = verdict.note
                if verdict.verdict == "complete":
                    row.result, row.answer_batch, row.answer_phase = "answered", number, phase
                    row.answer_chunk_ids = [c.chunk_id for c in relied] or [c.chunk_id for c in batch]
                    return
                if verdict.verdict == "partial":
                    any_partial = True
                    partial_chunks.extend(relied)
            # 8. Combine the partial chunks of every phase so far, in rank order.
            if any_partial:
                ordered = sorted({c.chunk_id: c for c in partial_chunks}.values(), key=lambda c: c.rank)
                ordered = ordered[:settings["combine_max"]]
                ids = [c.chunk_id for c in ordered]
                if ordered and ids != combined_ids:
                    combined_ids = ids
                    verdict = await self._judge("combine", query, ordered, row)
                    relied = [ordered[n - 1] for n in verdict.chunk_numbers]
                    row.combines.append({
                        "phase": phase, "verdict": verdict.verdict, "chunk_ids": ids,
                        "relied_chunk_ids": [c.chunk_id for c in relied], "note": verdict.note})
                    row.note = verdict.note
                    if verdict.verdict == "complete":
                        row.result, row.answer_phase = "answered_combined", phase
                        row.answer_chunk_ids = [c.chunk_id for c in relied] or ids
                        return
        row.result = "partial" if any_partial else "not_answered"

    async def _retrieve(self, query: str, depth: int, keep: int | None, row: _Row):
        """Retrieve at ``depth`` and rerank to ``keep`` (all candidates when None)."""
        async def operation():
            results = await self.rag.retrieve(
                query, top_k=depth, allowed_docs=self.documents,
                bm25_candidate_limit=depth, semantic_candidate_limit=depth)
            if not results:
                return []
            return await self.rag.search_engine.rerank_search_results(
                query, results, top_k=len(results) if keep is None else keep)
        for attempt in range(2):
            row.retrievals += 1
            try:
                return list(await self._limited(operation))
            except Exception:
                if attempt:
                    raise CheckError("retrieval_failed") from None

    async def _judge(self, kind: str, query: str, chunks: list[_Chunk], row: _Row) -> prompts.Verdict:
        """One model call, retried once on failure or an invalid reply."""
        settings = self.settings
        msgs = prompts.messages(kind, query, [c.content for c in chunks], settings["chunk_max_chars"])

        async def operation():
            return await self.rag._completion(
                model=self.rag.model_id, messages=msgs, max_tokens=settings["model_max_tokens"],
                temperature=0, top_p=1, seed=42, response_format=prompts.response_format())
        code = "model_failed"
        for _ in range(2):
            row.model_calls += 1
            try:
                response = await self._limited(operation)
                content = response.choices[0].message.content
            except Exception:
                code = "model_failed"
                continue
            verdict = prompts.parse_verdict(content, len(chunks))
            if verdict is not None:
                return verdict
            code = "invalid_model_output"
        raise CheckError(code)
