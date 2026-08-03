"""Tracked in-process execution for PostgreSQL-backed mass-answer jobs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


class MassAnswerJobManager:
    def __init__(self):
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._progress: dict[str, object] = {}
        self._closed = False

    @property
    def active_job_ids(self) -> set[str]:
        return set(self._tasks)

    def set_progress(self, job_id: str, progress: object) -> None:
        if job_id in self._tasks:
            self._progress[job_id] = progress

    def get_progress(self, job_id: str):
        return self._progress.get(job_id)

    def start(self, job_id: str, operation: Callable[[], Awaitable[None]]) -> None:
        if self._closed:
            raise RuntimeError("mass-answer job manager is closed")
        if job_id in self._tasks:
            raise ValueError("job is already active")
        task = asyncio.create_task(operation(), name=f"mass-answer:{job_id}")
        self._tasks[job_id] = task

        def finished(done: asyncio.Task[None]) -> None:
            self._tasks.pop(job_id, None)
            self._progress.pop(job_id, None)
            if done.cancelled():
                return
            try:
                done.exception()
            except (asyncio.CancelledError, Exception):
                pass

        task.add_done_callback(finished)

    async def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task is None:
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def aclose(self) -> None:
        self._closed = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._progress.clear()
