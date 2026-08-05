"""Bounded adapters for synchronous work called from asyncio request paths."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from .request_instrumentation import current_trace, trace_span
from .service_errors import ServiceOverloadedError

T = TypeVar("T")
admission_logger = logging.getLogger("request_admission")


@dataclass(frozen=True)
class LimiterSnapshot:
    limiter_id: str
    capacity: int
    active: int
    waiting: int
    acquired_total: int
    timeout_total: int
    cancelled_total: int
    released_total: int


class AdmissionLimiter:
    """Worker-local admission with explicit ownership, timing, and counters."""

    def __init__(self, capacity: int, *, name: str = "request"):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self.limiter_id = f"{name}:{os.getpid()}:{id(self):x}"
        self._semaphore = asyncio.Semaphore(capacity)
        self._active = 0
        self._waiting = 0
        self._acquired_total = 0
        self._timeout_total = 0
        self._cancelled_total = 0
        self._released_total = 0

    def snapshot(self) -> LimiterSnapshot:
        return LimiterSnapshot(
            limiter_id=self.limiter_id,
            capacity=self.capacity,
            active=self._active,
            waiting=self._waiting,
            acquired_total=self._acquired_total,
            timeout_total=self._timeout_total,
            cancelled_total=self._cancelled_total,
            released_total=self._released_total,
        )

    def _emit(
        self,
        event: str,
        *,
        request_id: str,
        outcome: str,
        wait_ms: float | None = None,
        hold_ms: float | None = None,
        release_reason: str | None = None,
    ) -> None:
        snapshot = self.snapshot()
        admission_logger.info(
            json.dumps(
                {
                    "event": event,
                    "request_id": request_id,
                    "process_id": os.getpid(),
                    "limiter_id": self.limiter_id,
                    "capacity": self.capacity,
                    "active": snapshot.active,
                    "waiting": snapshot.waiting,
                    "outcome": outcome,
                    "wait_ms": wait_ms,
                    "hold_ms": hold_ms,
                    "release_reason": release_reason,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )

    @asynccontextmanager
    async def slot(
        self,
        *,
        acquire_timeout: float,
        request_id: str | None = None,
    ):
        if acquire_timeout <= 0:
            raise ValueError("acquire_timeout must be greater than 0")
        trace = current_trace()
        correlation_id = request_id or (trace.request_id if trace else "untracked")
        wait_started = time.perf_counter_ns()
        acquired = False
        waiting = True
        hold_started = 0
        release_reason = "success"
        self._waiting += 1
        if trace:
            trace.limiter_id = self.limiter_id
            trace.admission_outcome = "waiting"
            trace.add_duration(
                "pre_admission",
                (wait_started - trace.received_ns) / 1_000_000,
            )
            trace.mark("admission_wait_start")
        self._emit("admission_wait_start", request_id=correlation_id, outcome="waiting")
        try:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(), timeout=acquire_timeout
                )
            except TimeoutError as exc:
                wait_ms = (time.perf_counter_ns() - wait_started) / 1_000_000
                self._timeout_total += 1
                if trace:
                    trace.admission_outcome = "timeout"
                    trace.admission_wait_ms = wait_ms
                self._emit(
                    "admission_timeout",
                    request_id=correlation_id,
                    outcome="timeout",
                    wait_ms=wait_ms,
                )
                raise ServiceOverloadedError(
                    "Request concurrency limit reached"
                ) from exc
            finally:
                if waiting:
                    self._waiting -= 1
                    waiting = False

            acquired = True
            hold_started = time.perf_counter_ns()
            wait_ms = (hold_started - wait_started) / 1_000_000
            self._active += 1
            self._acquired_total += 1
            if trace:
                trace.admission_acquired = True
                trace.admission_outcome = "acquired"
                trace.admission_wait_ms = wait_ms
                trace.mark("admission_acquired")
            self._emit(
                "admission_acquired",
                request_id=correlation_id,
                outcome="acquired",
                wait_ms=wait_ms,
            )
            try:
                yield
            except asyncio.CancelledError:
                release_reason = "cancelled"
                self._cancelled_total += 1
                if trace:
                    trace.admission_outcome = "cancelled_after_acquire"
                raise
            except Exception:
                release_reason = "exception"
                raise
        except asyncio.CancelledError:
            if not acquired:
                self._cancelled_total += 1
                if trace:
                    trace.admission_outcome = "cancelled_while_waiting"
                self._emit(
                    "admission_cancelled",
                    request_id=correlation_id,
                    outcome="cancelled_while_waiting",
                    wait_ms=(time.perf_counter_ns() - wait_started) / 1_000_000,
                )
            raise
        finally:
            if waiting:
                self._waiting -= 1
            if acquired:
                released_ns = time.perf_counter_ns()
                hold_ms = (released_ns - hold_started) / 1_000_000
                self._active -= 1
                self._released_total += 1
                self._semaphore.release()
                if trace:
                    trace.permit_hold_ms = hold_ms
                    trace.mark("admission_release")
                self._emit(
                    "admission_release",
                    request_id=correlation_id,
                    outcome="released",
                    wait_ms=(hold_started - wait_started) / 1_000_000,
                    hold_ms=hold_ms,
                    release_reason=release_reason,
                )

    async def run(
        self,
        operation: Callable[[], Any],
        *,
        acquire_timeout: float,
        request_id: str | None = None,
    ) -> Any:
        async with self.slot(
            acquire_timeout=acquire_timeout, request_id=request_id
        ):
            return await operation()


class BoundedBlockingRunner:
    """Run blocking callables in worker threads with bounded admission.

    A cancelled asyncio waiter cannot stop Python code that is already running in
    a thread.  Read-only work is allowed to finish in the background while its
    slot remains reserved.  Transactional writes may opt into waiting for the
    worker to finish before cancellation is re-raised, ensuring that connection
    cleanup and commit/rollback complete deterministically.
    """

    def __init__(self, max_concurrency: int = 16):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.capacity = max_concurrency
        self.limiter_id = f"blocking:{os.getpid()}:{id(self):x}"
        self._closed = False
        self._active_workers: set[asyncio.Task[Any]] = set()
        self._waiting = 0
        self._acquired_total = 0
        self._cancelled_total = 0
        self._released_total = 0

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def active_count(self) -> int:
        return len(self._active_workers)

    def snapshot(self) -> dict[str, int | str]:
        return {
            "limiter_id": self.limiter_id,
            "capacity": self.capacity,
            "active": self.active_count,
            "waiting": self._waiting,
            "acquired_total": self._acquired_total,
            "cancelled_total": self._cancelled_total,
            "released_total": self._released_total,
        }

    async def run(
        self,
        func: Callable[..., T],
        /,
        *args: Any,
        wait_for_completion_on_cancel: bool = False,
        **kwargs: Any,
    ) -> T:
        if self._closed:
            raise RuntimeError("blocking runner is closed")

        self._waiting += 1
        try:
            async with trace_span("blocking_wait"):
                await self._semaphore.acquire()
        except asyncio.CancelledError:
            self._cancelled_total += 1
            raise
        finally:
            self._waiting -= 1
        self._acquired_total += 1
        if self._closed:
            self._semaphore.release()
            self._released_total += 1
            raise RuntimeError("blocking runner is closed")
        call = functools.partial(func, *args, **kwargs)
        worker = asyncio.create_task(asyncio.to_thread(call))
        self._active_workers.add(worker)
        release_in_callback = False

        def release(_task: asyncio.Task[Any]) -> None:
            self._active_workers.discard(_task)
            self._semaphore.release()
            self._released_total += 1
            # Retrieve failures from work whose waiter was cancelled.
            if _task.cancelled():
                return
            try:
                _task.exception()
            except (asyncio.CancelledError, Exception):
                pass

        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            if wait_for_completion_on_cancel:
                try:
                    await asyncio.shield(worker)
                except Exception:
                    # Cancellation remains the boundary result. The blocking
                    # callable owns rollback/cleanup for its local resource.
                    pass
            else:
                worker.add_done_callback(release)
                release_in_callback = True
            raise
        finally:
            if not release_in_callback:
                self._active_workers.discard(worker)
                self._semaphore.release()
                self._released_total += 1

    async def aclose(self) -> None:
        self._closed = True
        if self._active_workers:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tuple(self._active_workers)),
                return_exceptions=True,
            )


async def run_with_limit(
    semaphore: asyncio.Semaphore | AdmissionLimiter,
    operation: Callable[[], Any],
    *,
    acquire_timeout: float,
) -> Any:
    """Run one async operation after bounded, cancellation-safe admission."""

    if isinstance(semaphore, AdmissionLimiter):
        return await semaphore.run(
            operation, acquire_timeout=acquire_timeout
        )

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=acquire_timeout)
    except TimeoutError as exc:
        raise ServiceOverloadedError(
            "Request concurrency limit reached"
        ) from exc

    try:
        return await operation()
    finally:
        semaphore.release()
