"""Bounded, order-preserving row execution for mass answering."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from answering_service import AnswerRequestContext
from utils.service_errors import (
    ServiceError,
    ServiceOverloadedError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)


@dataclass
class MassAnswerRowResult:
    index: int
    answer: str = ""
    status: str = "success"
    error_code: str = ""
    error_message: str = ""
    processing_time_ms: float = 0.0
    intent: str = ""
    rewritten_query: str = ""
    related_questions: str = "[]"


@dataclass(frozen=True)
class MassAnswerProgress:
    total_rows: int
    completed_rows: int
    successful_rows: int
    failed_rows: int
    timed_out_rows: int
    queued_rows: int
    active_rows: int


logger = logging.getLogger(__name__)


class MassAnswerProcessor:
    def __init__(
        self,
        *,
        answering_service,
        row_concurrency: int,
        row_timeout_seconds: float,
        queue_multiplier: int = 2,
    ):
        if row_concurrency < 1:
            raise ValueError("row_concurrency must be at least 1")
        if row_timeout_seconds <= 0:
            raise ValueError("row_timeout_seconds must be greater than 0")
        self.answering_service = answering_service
        self.row_concurrency = row_concurrency
        self.row_timeout_seconds = row_timeout_seconds
        self.queue_size = max(row_concurrency, row_concurrency * queue_multiplier)

    async def process(
        self,
        queries: Sequence[str | None],
        *,
        selected_documents: Sequence[str],
        batch_id: str = "direct",
        progress_callback: Callable[[MassAnswerProgress], None] | None = None,
    ) -> list[MassAnswerRowResult]:
        """Process with a fixed task count and preserve positional ordering."""
        if not queries:
            return []
        queue: asyncio.Queue[tuple[int, str | None] | None] = asyncio.Queue(
            maxsize=self.queue_size
        )
        results: list[MassAnswerRowResult | None] = [None] * len(queries)
        progress_lock = asyncio.Lock()
        counters = {
            "completed": 0,
            "successful": 0,
            "failed": 0,
            "timed_out": 0,
            "active": 0,
        }

        def report_progress() -> None:
            if progress_callback is None:
                return
            progress_callback(MassAnswerProgress(
                total_rows=len(queries),
                completed_rows=counters["completed"],
                successful_rows=counters["successful"],
                failed_rows=counters["failed"],
                timed_out_rows=counters["timed_out"],
                queued_rows=max(
                    0,
                    len(queries) - counters["completed"] - counters["active"],
                ),
                active_rows=counters["active"],
            ))

        async def producer() -> None:
            for index, query in enumerate(queries):
                await queue.put((index, query))
            for _ in range(self.row_concurrency):
                await queue.put(None)

        async def worker() -> None:
            while True:
                item = await queue.get()
                try:
                    if item is None:
                        return
                    index, query = item
                    async with progress_lock:
                        counters["active"] += 1
                        report_progress()
                    results[index] = await self._process_row(
                        index,
                        query,
                        selected_documents=selected_documents,
                        batch_id=batch_id,
                    )
                    async with progress_lock:
                        row = results[index]
                        counters["active"] -= 1
                        counters["completed"] += 1
                        if row.status == "success":
                            counters["successful"] += 1
                        else:
                            counters["failed"] += 1
                        if row.status == "timeout":
                            counters["timed_out"] += 1
                        report_progress()
                finally:
                    queue.task_done()

        producer_task = asyncio.create_task(producer())
        workers = [
            asyncio.create_task(worker()) for _ in range(self.row_concurrency)
        ]
        tasks = [producer_task, *workers]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        except Exception:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        return [
            result
            if result is not None
            else MassAnswerRowResult(
                index=index,
                status="internal_error",
                error_code="internal_error",
                error_message="Row result was not produced",
            )
            for index, result in enumerate(results)
        ]

    async def _process_row(
        self,
        index: int,
        query: str | None,
        *,
        selected_documents: Sequence[str],
        batch_id: str,
    ) -> MassAnswerRowResult:
        started = time.perf_counter()
        query_text = "" if query is None else str(query).strip()
        if not query_text:
            return MassAnswerRowResult(
                index=index,
                status="invalid_input",
                error_code="empty_query",
                error_message="Query cell is empty",
                processing_time_ms=(time.perf_counter() - started) * 1000,
            )
        try:
            answer = await asyncio.wait_for(
                self.answering_service.answer(AnswerRequestContext(
                    original_query=query_text,
                    selected_documents=tuple(selected_documents),
                    channel="mass_answer",
                    use_history=False,
                    persist_agent_state=False,
                    include_related_questions=True,
                    timeout_seconds=self.row_timeout_seconds,
                )),
                timeout=self.row_timeout_seconds,
            )
            return MassAnswerRowResult(
                index=index,
                answer=answer.answer or "پاسخی یافت نشد.",
                intent=answer.intent,
                rewritten_query=answer.rewritten_query,
                related_questions=json.dumps(
                    answer.related_questions, ensure_ascii=False
                ),
                processing_time_ms=(time.perf_counter() - started) * 1000,
            )
        except asyncio.CancelledError:
            raise
        except (TimeoutError, ServiceTimeoutError):
            return self._failure(index, started, "timeout", "Row timed out")
        except ServiceOverloadedError:
            return self._failure(index, started, "busy", "Service is busy")
        except ServiceUnavailableError:
            return self._failure(
                index, started, "retrieval_error", "Answer dependency unavailable"
            )
        except ServiceError:
            return self._failure(
                index, started, "retrieval_error", "Answer dependency failed"
            )
        except ValueError as exc:
            return self._failure(index, started, "invalid_input", str(exc))
        except Exception:
            logger.exception(
                "mass-answer row failed",
                extra={"batch_id": batch_id, "row_index": index},
            )
            return self._failure(
                index, started, "internal_error", "Row processing failed"
            )

    @staticmethod
    def _failure(
        index: int, started: float, code: str, message: str
    ) -> MassAnswerRowResult:
        return MassAnswerRowResult(
            index=index,
            status=code,
            error_code=code,
            error_message=message,
            processing_time_ms=(time.perf_counter() - started) * 1000,
        )
