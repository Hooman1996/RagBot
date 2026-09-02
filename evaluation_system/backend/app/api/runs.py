from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from ..db.models import DatasetTurn, Run, RunSession, RunTurn, StageResult
from ..schemas.api import DeleteResponse, IdResponse, RunCreateRequest
from ..services.config_snapshot import build_config_snapshot, git_commit_sha
from ..services.repository import create_run, delete_run, get_dataset, list_runs
from ..services.run_planning import RunPlanError
from ..services.events import EvaluationEventBus
from ..worker.celery_app import celery_app
from ..config import get_settings
from .dependencies import AuthenticatedUserDep, DatabaseDep


router = APIRouter(tags=["evaluation-runs"])


def _run_dict(row: Run) -> dict[str, Any]:
    return {
        "id": row.id, "dataset_id": row.dataset_id, "run_type": row.run_type,
        "status": row.status, "config_snapshot": row.config_snapshot,
        "total_sessions": row.total_sessions, "completed_sessions": row.completed_sessions,
        "total_turns": row.total_turns, "completed_turns": row.completed_turns,
        "fallback_count": row.fallback_count, "error_count": row.error_count,
        "infrastructure_error_count": row.infrastructure_error_count,
        "git_commit_sha": row.git_commit_sha, "created_at": row.created_at,
        "started_at": row.started_at, "finished_at": row.finished_at,
        "cancel_requested_at": row.cancel_requested_at,
        "heartbeat_at": row.heartbeat_at,
        "failure_code": row.failure_code,
        "metadata": row.metadata_json,
    }


@router.post("/runs", response_model=IdResponse)
async def start_run(body: RunCreateRequest, _user: AuthenticatedUserDep, db: DatabaseDep) -> IdResponse:
    settings = get_settings()
    if not settings.use_celery:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "EVALUATION_BACKGROUND_EXECUTION_UNAVAILABLE"},
        )
    dataset = await get_dataset(db, body.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail={"error_code": "DATASET_NOT_FOUND"})
    snapshot = build_config_snapshot(selected_documents=body.documents)
    try:
        run = await create_run(
            db, dataset=dataset, run_type=body.run_type,
            repeat_count=body.repeat_count, config_snapshot=snapshot,
            git_commit_sha=snapshot.get("git_commit_sha"),
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


@router.get("/runs")
async def get_runs(_user: AuthenticatedUserDep, db: DatabaseDep) -> list[dict]:
    return [_run_dict(row) for row in await list_runs(db)]


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> dict:
    row = await db.get(Run, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    return _run_dict(row)


@router.delete("/runs/{run_id}", response_model=DeleteResponse)
async def remove_run(run_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> DeleteResponse:
    row = await db.get(Run, run_id)
    if row is not None and row.status in {"PENDING", "RUNNING"}:
        raise HTTPException(status_code=409, detail={"error_code": "RUN_NOT_TERMINAL"})
    deleted = await delete_run(db, run_id)
    await db.commit()
    return DeleteResponse(deleted=deleted)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: uuid.UUID,
    request: Request,
    _user: AuthenticatedUserDep,
    db: DatabaseDep,
) -> dict:
    row = await db.get(Run, run_id, with_for_update=True)
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
    if row.status not in {"PENDING", "RUNNING"}:
        raise HTTPException(status_code=409, detail={"error_code": "RUN_NOT_CANCELLABLE"})
    row.cancel_requested_at = datetime.now(timezone.utc)
    if row.status == "PENDING":
        row.status = "CANCELLED"
        row.finished_at = row.cancel_requested_at
    await db.commit()
    await EvaluationEventBus(request.app.state.redis).publish(
        run_id,
        "run_cancelled" if row.status == "CANCELLED" else "progress",
        {"run_id": str(run_id), "status": row.status},
    )
    return {"id": row.id, "status": row.status, "cancel_requested": True}


@router.get("/runs/{run_id}/sessions")
async def get_run_sessions(run_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> list[dict]:
    rows = list(await db.scalars(select(RunSession).where(RunSession.run_id == run_id).order_by(RunSession.repeat_index, RunSession.dataset_session_id)))
    dataset_session_ids = {
        row.dataset_session_id for row in rows if row.dataset_session_id is not None
    }
    first_queries = {}
    if dataset_session_ids:
        first_turns = list(await db.scalars(
            select(DatasetTurn).where(
                DatasetTurn.dataset_session_id.in_(dataset_session_ids),
                DatasetTurn.turn_index == 1,
            )
        ))
        first_queries = {
            turn.dataset_session_id: turn.query for turn in first_turns
        }
    return [{
        "id": row.id, "run_id": row.run_id, "dataset_session_id": row.dataset_session_id,
        "source_session_id": row.source_session_id, "repeat_index": row.repeat_index,
        "evaluation_session_key": row.evaluation_session_key, "status": row.status,
        "turn_count": row.turn_count, "fallback_count": row.fallback_count,
        "error_count": row.error_count, "total_latency_ms": row.total_latency_ms,
        "infrastructure_error_count": row.infrastructure_error_count,
        "first_divergent_turn": row.first_divergent_turn,
        "first_divergent_stage": row.first_divergent_stage,
        "first_query": first_queries.get(row.dataset_session_id),
        "synthetic_session": (row.metadata_json or {}).get("synthetic_session", False),
        "synthetic_label": (row.metadata_json or {}).get("synthetic_label"),
        "started_at": row.started_at, "finished_at": row.finished_at,
        "metadata": row.metadata_json,
    } for row in rows]


@router.get("/run-sessions/{run_session_id}")
async def get_run_session(run_session_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> dict:
    row = await db.get(RunSession, run_session_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_SESSION_NOT_FOUND"})
    turns = list(await db.scalars(select(RunTurn).where(RunTurn.run_session_id == row.id).order_by(RunTurn.turn_index)))
    return {"id": row.id, "status": row.status, "repeat_index": row.repeat_index, "turns": [{
        "id": turn.id, "turn_index": turn.turn_index, "raw_query": turn.raw_query,
        "actual_answer": turn.actual_answer, "actual_intent": turn.actual_intent,
        "rewritten_query": turn.rewritten_query, "fallback_used": turn.fallback_used,
        "fallback_reason": turn.fallback_reason, "status": turn.status,
        "infrastructure_error": turn.infrastructure_error,
        "error_code": turn.error_code,
        "total_latency_ms": turn.total_latency_ms,
    } for turn in turns]}


@router.get("/run-turns/{run_turn_id}/trace")
async def get_turn_trace(run_turn_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> dict:
    turn = await db.get(RunTurn, run_turn_id)
    if turn is None:
        raise HTTPException(status_code=404, detail={"error_code": "RUN_TURN_NOT_FOUND"})
    stages = list(await db.scalars(select(StageResult).where(StageResult.run_turn_id == run_turn_id).order_by(StageResult.stage_order)))
    return {
        "turn": {
            "id": turn.id, "turn_index": turn.turn_index, "raw_query": turn.raw_query,
            "normalized_query": turn.normalized_query, "rewritten_query": turn.rewritten_query,
            "history_before_hash": turn.history_before_hash, "history_after_hash": turn.history_after_hash,
            "actual_intent": turn.actual_intent, "intent_score": turn.intent_score,
            "selected_context_hash": turn.selected_context_hash,
            "actual_answer": turn.actual_answer, "fallback_used": turn.fallback_used,
            "fallback_reason": turn.fallback_reason, "status": turn.status,
            "infrastructure_error": turn.infrastructure_error,
            "error_code": turn.error_code,
            "total_latency_ms": turn.total_latency_ms,
            "started_at": turn.started_at,
            "finished_at": turn.finished_at,
        },
        "stages": [{
            "stage_name": stage.stage_name, "stage_order": stage.stage_order,
            "status": stage.status, "input_hash": stage.input_hash,
            "output_hash": stage.output_hash, "duration_ms": stage.duration_ms,
            "input_data": stage.input_data, "output_data": stage.output_data,
            "metrics": stage.metrics, "error_code": stage.error_code,
            "error_data": stage.error_data,
        } for stage in stages],
    }
