"""Dependency-free bounded session execution primitives."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar


T = TypeVar("T")


def effective_session_concurrency(run_type: str, configured: int) -> int:
    if configured < 1:
        raise ValueError("configured concurrency must be positive")
    return 1 if run_type.startswith("STABILITY") else configured


async def bounded_for_each(
    items: Iterable[T], concurrency: int, handler: Callable[[T], Awaitable[None]]
) -> None:
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    iterator = iter(items)
    iterator_lock = asyncio.Lock()

    async def worker() -> None:
        while True:
            async with iterator_lock:
                try:
                    item = next(iterator)
                except StopIteration:
                    return
            await handler(item)

    # The task count is fixed by the configured concurrency, never by dataset
    # size. TaskGroup cancels peers if one worker has a fatal orchestration
    # failure, so a failed worker cannot leave a queue join hanging.
    async with asyncio.TaskGroup() as group:
        for _ in range(concurrency):
            group.create_task(worker())
