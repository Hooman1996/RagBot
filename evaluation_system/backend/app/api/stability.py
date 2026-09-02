from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..schemas.api import IdResponse, ManualStabilityRequest
from ..services.config_snapshot import build_config_snapshot
from ..services.importer import parse_manual_dataset
from ..services.repository import create_run, persist_parsed_dataset
from ..services.run_planning import RunPlanError
from ..db.models import Run
from ..worker.celery_app import celery_app
from ..config import get_settings
from .dependencies import AuthenticatedUserDep, DatabaseDep


router = APIRouter(prefix="/stability", tags=["evaluation-stability"])


@router.post("/manual", response_model=IdResponse)
async def manual_stability(body: ManualStabilityRequest, _user: AuthenticatedUserDep, db: DatabaseDep) -> IdResponse:
    settings = get_settings()
    if not settings.use_celery:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "EVALUATION_BACKGROUND_EXECUTION_UNAVAILABLE"},
        )
    parsed = parse_manual_dataset(body.queries)
    dataset = await persist_parsed_dataset(db, parsed)
    snapshot = build_config_snapshot(selected_documents=body.documents)
    run_type = "STABILITY_QUERY" if parsed.valid_row_count == 1 else "STABILITY_SESSION"
    try:
        run = await create_run(
            db, dataset=dataset, run_type=run_type, repeat_count=body.repeat_count,
            config_snapshot=snapshot, git_commit_sha=snapshot.get("git_commit_sha"),
        )
    except RunPlanError as exc:
        raise HTTPException(status_code=422, detail={"error_code": exc.code}) from exc
    await db.commit()
    try:
        task = celery_app.send_task(
            "evaluation.execute_run", args=[str(run.id)],
            queue=settings.celery_queue,
        )
    except Exception as exc:
        durable_run = await db.get(Run, run.id, with_for_update=True)
        if durable_run is not None and durable_run.status == "PENDING":
            durable_run.status = "FAILED"
            durable_run.failure_code = "EVALUATION_QUEUE_UNAVAILABLE"
            durable_run.finished_at = datetime.now(timezone.utc)
            await db.commit()
        raise HTTPException(status_code=503, detail={"error_code": "EVALUATION_QUEUE_UNAVAILABLE", "run_id": str(run.id)}) from exc
    run.worker_task_id = str(task.id)
    await db.commit()
    return IdResponse(id=run.id, status=run.status)
