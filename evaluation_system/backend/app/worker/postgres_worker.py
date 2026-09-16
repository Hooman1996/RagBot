"""Standalone asyncio worker for PostgreSQL-backed evaluation runs."""

from __future__ import annotations

import asyncio
import os
import signal
import socket
import uuid
from collections.abc import Awaitable, Callable

from ..clients.ragbot import RagBotEvaluationClient
from ..config import EvaluationSettings, get_settings
from ..db.session import AsyncSessionFactory, engine
from .postgres_queue import PostgresRunQueue
from .runner import EvaluationRunExecutor, EvaluationRunFailed


def create_worker_id() -> str:
    """Return a content-free identity stable for this process lifetime."""

    return f"eval-worker:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"


async def _wait_for_stop(stop_event: asyncio.Event, delay: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=delay)
    except TimeoutError:
        pass


class PostgresEvaluationWorker:
    def __init__(
        self,
        *,
        queue: PostgresRunQueue,
        executor: EvaluationRunExecutor,
        worker_id: str,
        poll_interval_seconds: float,
        wait_for_stop: Callable[[asyncio.Event, float], Awaitable[None]] = _wait_for_stop,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.queue = queue
        self.executor = executor
        self.worker_id = worker_id
        self.poll_interval_seconds = poll_interval_seconds
        self.wait_for_stop = wait_for_stop

    async def run(self, stop_event: asyncio.Event) -> None:
        """Poll until stopped, letting an already claimed run finish normally."""

        while not stop_event.is_set():
            try:
                run_id = await self.queue.claim_next(self.worker_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                await self.wait_for_stop(stop_event, self.poll_interval_seconds)
                continue
            if run_id is None:
                await self.wait_for_stop(stop_event, self.poll_interval_seconds)
                continue
            try:
                await self.executor.execute(
                    run_id, worker_task_id=self.worker_id
                )
            except asyncio.CancelledError:
                raise
            except EvaluationRunFailed:
                continue


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass


async def run_worker(
    *,
    settings: EvaluationSettings | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    settings = settings or get_settings()
    if not settings.enabled:
        raise RuntimeError("EVALUATION_WORKER_DISABLED")
    stop_event = stop_event or asyncio.Event()
    _install_signal_handlers(stop_event)
    ragbot_client = None
    try:
        ragbot_client = RagBotEvaluationClient(
            base_url=settings.ragbot_base_url,
            timeout_seconds=settings.ragbot_http_timeout_seconds,
        )
        queue = PostgresRunQueue(
            session_factory=AsyncSessionFactory,
            stale_after_seconds=settings.worker_stale_after_seconds,
        )
        executor = EvaluationRunExecutor(
            session_factory=AsyncSessionFactory,
            ragbot_client=ragbot_client,
            session_concurrency=settings.session_concurrency,
        )
        worker = PostgresEvaluationWorker(
            queue=queue,
            executor=executor,
            worker_id=create_worker_id(),
            poll_interval_seconds=settings.worker_poll_interval_seconds,
        )
        await worker.run(stop_event)
    finally:
        try:
            if ragbot_client is not None:
                await ragbot_client.aclose()
        finally:
            await engine.dispose()


def main() -> int:
    try:
        asyncio.run(run_worker())
    except RuntimeError as exc:
        if str(exc) == "EVALUATION_WORKER_DISABLED":
            raise SystemExit(
                "Evaluation is disabled: set EVAL_ENABLED=true in .env"
            ) from None
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
