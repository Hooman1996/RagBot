"""One background task at a time; later runs wait in a FIFO queue."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from starlette.concurrency import run_in_threadpool

from coverage_check.store import CheckStore
from utils.request_instrumentation import background_operation_context
from utils.structured_logging import log_event

logger = logging.getLogger("coverage_check")


class CheckJobs:
    """``checker_factory(meta)`` builds the checker for one run's stored settings."""

    def __init__(self, store: CheckStore, checker_factory):
        self.store = store
        self.checker_factory = checker_factory
        self._queue: deque[str] = deque()
        self._wakeup = asyncio.Event()
        self._cancel: set[str] = set()
        self._task: asyncio.Task | None = None
        self._closed = False
        self.current: str | None = None

    async def recover(self) -> int:
        """Runs left running or queued by a previous process become interrupted."""
        count = 0
        for meta in await run_in_threadpool(self.store.list):
            if meta["state"] in {"running", "queued"}:
                await run_in_threadpool(self.store.set_state, meta["run_id"], "interrupted")
                count += 1
        if count:
            log_event(logger, "coverage_check_recovered", {"interrupted_runs": count})
        return count

    def _ensure_worker(self) -> None:
        if self._closed:
            raise RuntimeError("coverage check jobs are closed")
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._worker(), name="coverage-check")

    def enqueue(self, run_id: str) -> None:
        self._cancel.discard(run_id)
        self._queue.append(run_id)
        self._wakeup.set()
        self._ensure_worker()

    async def cancel(self, run_id: str) -> None:
        if run_id in self._queue:
            self._queue.remove(run_id)
            await run_in_threadpool(self.store.set_state, run_id, "cancelled")
            log_event(logger, "coverage_check_cancelled", {"run_id": run_id, "while": "queued"})
        elif run_id == self.current:
            self._cancel.add(run_id)
        else:
            # Queued in storage but not in this process's queue; nothing is running it.
            await run_in_threadpool(self.store.set_state, run_id, "cancelled")

    async def _worker(self) -> None:
        while not self._closed:
            if not self._queue:
                self._wakeup.clear()
                await self._wakeup.wait()
                continue
            run_id = self._queue.popleft()
            self.current = run_id
            try:
                await self._run(run_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event(logger, "coverage_check_failed",
                          {"run_id": run_id, "error_type": type(exc).__name__}, level=logging.ERROR)
                try:
                    await run_in_threadpool(self.store.set_state, run_id, "interrupted")
                except Exception:
                    pass
            finally:
                self.current = None
                self._cancel.discard(run_id)

    async def _run(self, run_id: str) -> None:
        meta = await run_in_threadpool(self.store.meta, run_id)
        if meta["state"] != "queued":
            return
        meta = await run_in_threadpool(self.store.set_state, run_id, "running")
        rows = await run_in_threadpool(self.store.inputs, run_id)
        done = await run_in_threadpool(self.store.result_codes, run_id)
        started = time.perf_counter()
        log_event(logger, "coverage_check_started",
                  {"run_id": run_id, "rows": len(rows), "finished_rows": len(done)})
        with background_operation_context(operation_id=run_id, parent_request_id=None,
                                          operation_type="knowledge_coverage_check"):
            checker = self.checker_factory(meta)
            checked = 0
            for item in rows:
                if run_id in self._cancel:
                    break
                if item["row"] in done:
                    continue
                result = await checker.check(item["question"])
                await run_in_threadpool(self.store.write_result, run_id, item["row"], result)
                checked += 1
                log_event(logger, "coverage_check_row", {
                    "run_id": run_id, "row": item["row"], "result": result["result"],
                    "error_code": result["error_code"], "model_calls": result["model_calls"],
                    "duration_ms": result["duration_ms"]})
        state = "cancelled" if run_id in self._cancel else "completed"
        await run_in_threadpool(self.store.set_state, run_id, state)
        log_event(logger, "coverage_check_finished", {
            "run_id": run_id, "state": state, "checked_rows": checked,
            "duration_ms": round((time.perf_counter() - started) * 1000)})

    async def aclose(self) -> None:
        self._closed = True
        self._queue.clear()
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
