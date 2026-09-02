"""Celery task entrypoint for durable evaluation runs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from celery.signals import worker_shutdown
from redis.asyncio import Redis

from ..config import get_settings
from ..services.events import safe_error_code
from .celery_app import celery_app
from .process_runtime import (
    WorkerRuntimeInitializationError,
    close_worker_runtime,
    get_worker_runtime,
)


class EvaluationWorkerTaskFailed(RuntimeError):
    """Content-free task boundary failure safe for worker logs."""

    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(f"evaluation worker task failed: {error_code}")


def _task_failure_code(exc: Exception) -> str:
    if isinstance(exc, WorkerRuntimeInitializationError):
        return exc.error_code
    return safe_error_code(
        getattr(exc, "error_code", None),
        fallback="EVALUATION_WORKER_TASK_FAILED",
    )


def _mark_run_failed(run, error_code: str, *, finished_at) -> str:
    """Apply the durable terminal state without exposing exception content."""

    if run.status in {"COMPLETED", "CANCELLED"}:
        return run.failure_code or error_code
    durable_code = run.failure_code or error_code
    run.status = "FAILED"
    run.finished_at = finished_at
    run.failure_code = durable_code
    metadata = dict(run.metadata_json or {})
    metadata["failure_code"] = durable_code
    run.metadata_json = metadata
    return durable_code


@celery_app.task(name="evaluation.execute_run", bind=True)
def execute_run_task(self, run_id: str) -> None:
    durable_run_id = uuid.UUID(run_id)
    runtime = get_worker_runtime()
    try:
        runtime.run_with_service(
            lambda answering_service: _execute(
                durable_run_id,
                worker_task_id=str(self.request.id),
                answering_service=answering_service,
            )
        )
    except Exception as exc:
        error_code = _task_failure_code(exc)
        try:
            runtime.run_maintenance(
                _persist_task_failure(durable_run_id, error_code)
            )
        except Exception:
            pass
        raise EvaluationWorkerTaskFailed(error_code) from None


async def _execute(
    run_id: uuid.UUID,
    *,
    worker_task_id: str,
    answering_service,
) -> None:
    from ..db.session import AsyncSessionFactory, engine
    from ..services.events import EvaluationEventBus
    from .runner import EvaluationRunExecutor

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        runner = EvaluationRunExecutor(
            session_factory=AsyncSessionFactory,
            answering_service=answering_service,
            session_concurrency=settings.session_concurrency,
            event_bus=EvaluationEventBus(redis),
        )
        await runner.execute(run_id, worker_task_id=worker_task_id)
    finally:
        try:
            await redis.aclose()
        finally:
            # The canonical runtime remains alive, but evaluation SQLAlchemy
            # connections are released between durable runs.
            await engine.dispose()


async def _persist_task_failure(run_id: uuid.UUID, error_code: str) -> None:
    """Persist terminal truth even when failure precedes runtime construction."""

    from ..db.models import Run
    from ..db.session import AsyncSessionFactory, engine
    from ..services.events import EvaluationEventBus

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    durable_code = error_code
    try:
        async with AsyncSessionFactory() as session:
            run = await session.get(Run, run_id, with_for_update=True)
            if run is None:
                return
            if run.status in {"COMPLETED", "CANCELLED"}:
                return
            durable_code = _mark_run_failed(
                run,
                error_code,
                finished_at=datetime.now(timezone.utc),
            )
            await session.commit()
        await EvaluationEventBus(redis).publish(
            run_id,
            "run_failed",
            {
                "run_id": str(run_id),
                "status": "FAILED",
                "error_code": durable_code,
            },
        )
    finally:
        try:
            await redis.aclose()
        finally:
            await engine.dispose()


@worker_shutdown.connect
def _close_process_runtime(**_kwargs) -> None:
    close_worker_runtime()
