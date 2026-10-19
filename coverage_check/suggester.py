"""One draft FAQ entry for a not-answered or partly answered row, from the chunks its check saved.

There is no new retrieval: the model sees the chunk text stored with the row's result.
"""
from __future__ import annotations

import asyncio
import time

from starlette.concurrency import run_in_threadpool

from coverage_check import suggest_prompts
from coverage_check.store import CheckStore, now
from pipeline_observer import bind_pipeline_observer
from utils.concurrency import run_with_limit
from utils.performance_config import PERFORMANCE_SETTINGS

ELIGIBLE = ("not_answered", "partial")


def eligible(result: dict | None) -> bool:
    return bool(result) and result.get("result") in ELIGIBLE


def context_chunk_ids(result: dict) -> list[str]:
    """Relied chunks of partial batches and combine calls in rank order, then the rest in batch order."""
    ranked = list(dict.fromkeys(cid for b in result.get("batches") or [] for cid in b.get("chunk_ids") or []))
    relied = set()
    for batch in result.get("batches") or []:
        if batch.get("verdict") == "partial":
            relied.update(batch.get("relied_chunk_ids") or [])
    for combine in result.get("combines") or []:
        relied.update(combine.get("relied_chunk_ids") or [])
    first = [cid for cid in ranked if cid in relied]
    return first + [cid for cid in ranked if cid not in relied]


def context_chunks(store: CheckStore, run_id: str, result: dict, limit: int) -> list[tuple[str, str]]:
    """Up to ``limit`` (chunk_id, text) pairs; a chunk with no saved text is skipped."""
    keys = result.get("text_keys") or {}
    picked = []
    for chunk_id in context_chunk_ids(result):
        if len(picked) >= limit:
            break
        text = store.chunk_text(run_id, keys.get(chunk_id))
        if text is not None:
            picked.append((chunk_id, text))
    return picked


class _Failed(Exception):
    def __init__(self, code: str, model_calls: int):
        super().__init__(code)
        self.code = code
        self.model_calls = model_calls


class Suggester:
    def __init__(self, rag, limiter, store: CheckStore, settings):
        self.rag = rag
        self.limiter = limiter
        self.store = store
        self.settings = settings

    async def _limited(self, operation):
        """One admission slot per call, as the checker does, so chat keeps its admission limit."""
        async def guarded():
            with bind_pipeline_observer(None):
                return await operation()
        return await asyncio.wait_for(
            run_with_limit(self.limiter, guarded,
                           acquire_timeout=PERFORMANCE_SETTINGS.request_admission_timeout_seconds),
            PERFORMANCE_SETTINGS.application_request_timeout_seconds)

    async def suggest(self, run_id: str, row: int, question: str, result: dict | None) -> dict:
        started = time.perf_counter()
        data = {"status": "error", "error_code": None, "faq_question": None, "faq_answer": None, "missing": [],
                "chunks": [], "used_chunk_ids": [], "unverified_numbers": [],
                "suggest_prompt_version": suggest_prompts.SUGGEST_PROMPT_VERSION, "model_calls": 0}
        try:
            if not eligible(result):
                raise _Failed("not_eligible", 0)
            picked = await run_in_threadpool(context_chunks, self.store, run_id, result,
                                             self.settings.suggest_context)
            if not picked:
                raise _Failed("no_saved_chunks", 0)
            titles = result.get("titles") or {}
            data["chunks"] = [{"number": n, "chunk_id": cid, "title": titles.get(cid)}
                              for n, (cid, _) in enumerate(picked, 1)]
            texts = [text for _, text in picked]
            suggestion, calls = await self._call(str(question).strip(), texts)
            data["model_calls"] = calls
            data.update(status="done", faq_question=suggestion.faq_question, faq_answer=suggestion.faq_answer,
                        missing=suggestion.missing,
                        used_chunk_ids=[picked[n - 1][0] for n in suggestion.chunk_numbers],
                        unverified_numbers=suggest_prompts.unverified_numbers(suggestion.faq_answer, texts))
        except _Failed as exc:
            data["error_code"], data["model_calls"] = exc.code, exc.model_calls
        data["duration_ms"] = round((time.perf_counter() - started) * 1000)
        data["created_at"] = now()
        return data

    async def _call(self, question: str, texts: list[str]):
        """One model call, retried once on failure, a cut-off reply or an invalid reply."""
        msgs = suggest_prompts.messages(question, texts, self.settings.chunk_max_chars)

        async def operation():
            return await self.rag._completion(
                model=self.rag.model_id, messages=msgs, max_tokens=self.settings.suggest_max_tokens,
                temperature=0, top_p=1, seed=42, response_format=suggest_prompts.response_format())
        code, calls = "model_failed", 0
        for _ in range(2):
            calls += 1
            try:
                response = await self._limited(operation)
                choice = response.choices[0]
                finish_reason, content = choice.finish_reason, choice.message.content
            except Exception:
                code = "model_failed"
                continue
            if finish_reason == "length":
                # Hit KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS; a cut reply is not parsed.
                code = "model_output_cut"
                continue
            suggestion, code = suggest_prompts.parse_suggestion(content, len(texts))
            if suggestion is not None:
                return suggestion, calls
        raise _Failed(code, calls)
