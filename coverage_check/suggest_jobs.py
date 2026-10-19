"""One suggestion at a time from a FIFO queue of (run_id, row), separate from the check queue.

The queue lives in memory only: after a restart queued rows are gone and the owner clicks again.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque

from starlette.concurrency import run_in_threadpool

from coverage_check.store import CheckStore
from utils.request_instrumentation import background_operation_context
from utils.structured_logging import log_event

logger = logging.getLogger("coverage_check")


class SuggestJobs:
    """``suggester_factory()`` builds the suggester; ``suggest(run_id, row, question, result)`` returns the
    suggestion to store."""

    def __init__(self, store: CheckStore, suggester_factory):
        self.store = store
        self.suggester_factory = suggester_factory
        self._queue: deque[tuple[str, int]] = deque()
        self._queued: set[tuple[str, int]] = set()
        self._wakeup = asyncio.Event()
        self._stopping: set[str] = set()
        self._task: asyncio.Task | None = None
        self._row_task: asyncio.Task | None = None
        self._closed = False
        # The row being suggested; memory only.
        self.active: dict | None = None

    def _ensure_worker(self) -> None:
        if self._closed:
            raise RuntimeError("coverage suggestion jobs are closed")
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._worker(), name="coverage-suggest")

    def active_row(self, run_id: str) -> int | None:
        active = self.active
        return active["row"] if active is not None and active["run_id"] == run_id else None

    def queued_rows(self, run_id: str) -> set[int]:
        return {row for queued_run, row in self._queued if queued_run == run_id}

    def status(self, run_id: str, row: int) -> str | None:
        """``active`` or ``queued`` while this process is working on the row, else None."""
        if self.active_row(run_id) == row:
            return "active"
        return "queued" if (run_id, row) in self._queued else None

    def enqueue(self, run_id: str, rows) -> int:
        """Rows already queued or active are skipped; returns how many were added."""
        added = 0
        for row in rows:
            key = (run_id, int(row))
            if key in self._queued or self.active_row(run_id) == key[1]:
                continue
            self._queue.append(key)
            self._queued.add(key)
            added += 1
        if added:
            self._wakeup.set()
            self._ensure_worker()
        return added

    async def cancel(self, run_id: str) -> int:
        """Drops the run's queued rows and stops its active row at once; a stopped row writes nothing."""
        dropped = [key for key in self._queue if key[0] == run_id]
        if dropped:
            self._queue = deque(key for key in self._queue if key[0] != run_id)
            self._queued.difference_update(dropped)
        stopped = self.active_row(run_id) is not None
        if stopped:
            self._stopping.add(run_id)
            if self._row_task is not None:
                self._row_task.cancel()
        count = len(dropped) + int(stopped)
        if count:
            log_event(logger, "coverage_suggest_cancelled",
                      {"run_id": run_id, "queued_rows": len(dropped), "active_stopped": stopped})
        return count

    async def _worker(self) -> None:
        while not self._closed:
            if not self._queue:
                self._wakeup.clear()
                await self._wakeup.wait()
                continue
            run_id, row = self._queue.popleft()
            self._queued.discard((run_id, row))
            self.active = {"run_id": run_id, "row": row}
            try:
                await self._run(run_id, row)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event(logger, "coverage_suggest_failed",
                          {"run_id": run_id, "row": row, "error_type": type(exc).__name__}, level=logging.ERROR)
            finally:
                self.active = None
                self._stopping.discard(run_id)

    async def _run(self, run_id: str, row: int) -> None:
        items = await run_in_threadpool(self.store.inputs, run_id)
        item = next((item for item in items if item["row"] == row), None)
        if item is None:
            return
        result = await run_in_threadpool(self.store.result, run_id, row)
        with background_operation_context(operation_id=run_id, parent_request_id=None,
                                          operation_type="knowledge_coverage_suggest"):
            suggester = self.suggester_factory()
            self._row_task = asyncio.create_task(suggester.suggest(run_id, row, item["question"], result),
                                                 name="coverage-suggest-row")
            try:
                data = await self._row_task
            except asyncio.CancelledError:
                # Only a Stop for this run; app shutdown cancels this task and is re-raised.
                if run_id not in self._stopping or asyncio.current_task().cancelling():
                    raise
                return
            finally:
                self._row_task = None
        if run_id in self._stopping:
            return
        await run_in_threadpool(self.store.write_suggestion, run_id, row, data)
        log_event(logger, "coverage_suggest_row", {
            "run_id": run_id, "row": row, "status": data["status"], "error_code": data["error_code"],
            "model_calls": data["model_calls"], "duration_ms": data["duration_ms"]})

    async def aclose(self) -> None:
        self._closed = True
        self._queue.clear()
        self._queued.clear()
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
