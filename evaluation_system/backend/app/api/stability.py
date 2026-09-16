from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.api import IdResponse, ManualStabilityRequest
from ..services.provisional_snapshot import build_provisional_snapshot
from ..services.importer import parse_manual_dataset
from ..services.repository import create_run, persist_parsed_dataset
from ..services.run_planning import RunPlanError
from .dependencies import DatabaseDep


router = APIRouter(prefix="/stability", tags=["evaluation-stability"])


@router.post("/manual", response_model=IdResponse)
async def manual_stability(body: ManualStabilityRequest, db: DatabaseDep) -> IdResponse:
    parsed = parse_manual_dataset(body.queries)
    dataset = await persist_parsed_dataset(db, parsed)
    snapshot = build_provisional_snapshot(body.documents)
    run_type = "STABILITY_QUERY" if parsed.valid_row_count == 1 else "STABILITY_SESSION"
    try:
        run = await create_run(
            db, dataset=dataset, run_type=run_type, repeat_count=body.repeat_count,
            config_snapshot=snapshot, git_commit_sha=None,
        )
    except RunPlanError as exc:
        raise HTTPException(status_code=422, detail={"error_code": exc.code}) from exc
    await db.commit()
    return IdResponse(id=run.id, status=run.status)
