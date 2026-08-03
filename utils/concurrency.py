"""Bounded adapters for synchronous work called from asyncio request paths."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

from .service_errors import ServiceOverloadedError

T = TypeVar("T")


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
        self._closed = False
        self._active_workers: set[asyncio.Task[Any]] = set()

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def active_count(self) -> int:
        return len(self._active_workers)

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

        await self._semaphore.acquire()
        if self._closed:
            self._semaphore.release()
            raise RuntimeError("blocking runner is closed")
        call = functools.partial(func, *args, **kwargs)
        worker = asyncio.create_task(asyncio.to_thread(call))
        self._active_workers.add(worker)
        release_in_callback = False

        def release(_task: asyncio.Task[Any]) -> None:
            self._active_workers.discard(_task)
            self._semaphore.release()
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

    async def aclose(self) -> None:
        self._closed = True
        if self._active_workers:
            await asyncio.gather(
                *(asyncio.shield(task) for task in tuple(self._active_workers)),
                return_exceptions=True,
            )


async def run_with_limit(
    semaphore: asyncio.Semaphore,
    operation: Callable[[], Any],
    *,
    acquire_timeout: float,
) -> Any:
    """Run one async operation after bounded, cancellation-safe admission."""

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
