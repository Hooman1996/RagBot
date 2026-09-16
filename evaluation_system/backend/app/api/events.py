"""PostgreSQL-backed live projection for evaluation run SSE clients."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..config import get_settings
from ..db.models import Run, RunSession, RunTurn, StageResult
from ..db.session import AsyncSessionFactory
from ..services.error_codes import safe_error_code
from .dependencies import AuthenticatedUserDep


router = APIRouter(tags=["evaluation-events"])
TERMINAL_RUN_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
TERMINAL_SESSION_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
TERMINAL_TURN_STATUSES = frozenset({"COMPLETED", "ERROR", "CANCELLED"})
PROGRESS_FIELDS = (
    "status",
    "completed_sessions",
    "total_sessions",
    "completed_turns",
    "total_turns",
    "fallback_count",
    "error_count",
    "infrastructure_error_count",
)
HEARTBEAT_INTERVAL_SECONDS = 15.0


@dataclass(frozen=True)
class SessionProjection:
    id: str
    status: str
    repeat_index: int
    total_latency_ms: float | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class TurnProjection:
    id: str
    run_session_id: str
    status: str
    turn_index: int
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class StageProjection:
    id: str
    run_turn_id: str
    stage_name: str
    stage_order: int
    status: str
    duration_ms: float | None
    error_code: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class DurableProjection:
    run: dict[str, Any]
    sessions: tuple[SessionProjection, ...]
    turns: tuple[TurnProjection, ...]
    stages: tuple[StageProjection, ...]


class ProjectionNotFound(LookupError):
    pass


def _event(*, event: str, data: dict[str, Any]) -> bytes:
    lines = [
        f"event: {event}",
        "data: "
        + json.dumps(
            data, ensure_ascii=False, separators=(",", ":"), default=str
        ),
    ]
    return ("\n".join(lines) + "\n\n").encode("utf-8")


def snapshot_payload(projection: DurableProjection) -> dict[str, Any]:
    return dict(projection.run)


async def read_projection(
    run_id: uuid.UUID,
    *,
    session_factory=AsyncSessionFactory,
) -> DurableProjection:
    """Read one projection in a short, read-only database session."""

    async with session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise ProjectionNotFound(str(run_id))
        session_rows = list(
            await session.scalars(
                select(RunSession)
                .where(RunSession.run_id == run_id)
                .order_by(
                    RunSession.repeat_index,
                    RunSession.dataset_session_id,
                    RunSession.id,
                )
            )
        )
        turn_rows = list(
            await session.scalars(
                select(RunTurn)
                .join(RunSession, RunTurn.run_session_id == RunSession.id)
                .where(RunSession.run_id == run_id)
                .order_by(
                    RunSession.repeat_index,
                    RunSession.id,
                    RunTurn.turn_index,
                    RunTurn.id,
                )
            )
        )
        stage_rows = list(
            await session.scalars(
                select(StageResult)
                .join(RunTurn, StageResult.run_turn_id == RunTurn.id)
                .join(RunSession, RunTurn.run_session_id == RunSession.id)
                .where(RunSession.run_id == run_id)
                .order_by(
                    StageResult.stage_order,
                    StageResult.created_at,
                    StageResult.id,
                )
            )
        )
        run_projection = {
            "run_id": str(run.id),
            "status": run.status,
            "completed_sessions": run.completed_sessions,
            "total_sessions": run.total_sessions,
            "completed_turns": run.completed_turns,
            "total_turns": run.total_turns,
            "fallback_count": run.fallback_count,
            "error_count": run.error_count,
            "infrastructure_error_count": run.infrastructure_error_count,
            "heartbeat_at": run.heartbeat_at,
        }
        sessions = tuple(
            SessionProjection(
                id=str(row.id),
                status=row.status,
                repeat_index=row.repeat_index,
                total_latency_ms=row.total_latency_ms,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
            for row in session_rows
        )
        turns = tuple(
            TurnProjection(
                id=str(row.id),
                run_session_id=str(row.run_session_id),
                status=row.status,
                turn_index=row.turn_index,
                started_at=row.started_at,
                finished_at=row.finished_at,
            )
            for row in turn_rows
        )
        stages = tuple(
            StageProjection(
                id=str(row.id),
                run_turn_id=str(row.run_turn_id),
                stage_name=row.stage_name,
                stage_order=row.stage_order,
                status=row.status,
                duration_ms=row.duration_ms,
                error_code=(
                    safe_error_code(row.error_code) if row.error_code else None
                ),
                created_at=row.created_at,
            )
            for row in stage_rows
        )
    return DurableProjection(run_projection, sessions, turns, stages)


def project_changes(
    previous: DurableProjection,
    current: DurableProjection,
) -> list[tuple[str, dict[str, Any]]]:
    """Derive frontend-compatible events in a stable logical order."""

    run_id = current.run["run_id"]
    previous_sessions = {row.id: row for row in previous.sessions}
    previous_turns = {row.id: row for row in previous.turns}
    previous_stage_ids = {row.id for row in previous.stages}
    current_turns = {row.id: row for row in current.turns}
    events: list[tuple[str, dict[str, Any]]] = []

    for row in current.sessions:
        old = previous_sessions.get(row.id)
        if row.status == "RUNNING" and (old is None or old.status != "RUNNING"):
            events.append(("session_started", {
                "run_id": run_id,
                "run_session_id": row.id,
                "status": row.status,
            }))

    for row in current.turns:
        old = previous_turns.get(row.id)
        if row.status == "RUNNING" and (old is None or old.status != "RUNNING"):
            events.append(("turn_started", {
                "run_id": run_id,
                "run_session_id": row.run_session_id,
                "run_turn_id": row.id,
                "status": row.status,
            }))

    new_stages = sorted(
        (row for row in current.stages if row.id not in previous_stage_ids),
        key=lambda row: (row.stage_order, str(row.created_at or ""), row.id),
    )
    for row in new_stages:
        turn = current_turns.get(row.run_turn_id)
        if turn is None:
            continue
        events.append(("stage_completed", {
            "run_id": run_id,
            "run_session_id": turn.run_session_id,
            "run_turn_id": row.run_turn_id,
            "stage_name": row.stage_name,
            "status": row.status,
            "duration_ms": row.duration_ms,
            "error_code": row.error_code,
        }))

    for row in current.turns:
        old = previous_turns.get(row.id)
        if row.status in TERMINAL_TURN_STATUSES and (
            old is None or old.status not in TERMINAL_TURN_STATUSES
        ):
            events.append(("turn_completed", {
                "run_id": run_id,
                "run_session_id": row.run_session_id,
                "run_turn_id": row.id,
                "status": row.status,
            }))

    for row in current.sessions:
        old = previous_sessions.get(row.id)
        if row.status in TERMINAL_SESSION_STATUSES and (
            old is None or old.status not in TERMINAL_SESSION_STATUSES
        ):
            events.append(("session_completed", {
                "run_id": run_id,
                "run_session_id": row.id,
                "status": row.status,
                "duration_ms": row.total_latency_ms,
            }))

    if any(previous.run.get(name) != current.run.get(name) for name in PROGRESS_FIELDS):
        events.append(("progress", {
            name: current.run[name]
            for name in ("run_id", *PROGRESS_FIELDS)
        }))

    old_status = previous.run["status"]
    new_status = current.run["status"]
    if new_status in TERMINAL_RUN_STATUSES and old_status not in TERMINAL_RUN_STATUSES:
        terminal_name = {
            "COMPLETED": "run_completed",
            "FAILED": "run_failed",
            "CANCELLED": "run_cancelled",
        }[new_status]
        events.append((terminal_name, {"run_id": run_id, "status": new_status}))
    return events


@router.get("/runs/{run_id}/events", response_class=StreamingResponse)
async def run_events(
    run_id: uuid.UUID,
    request: Request,
    _user: AuthenticatedUserDep,
):
    # Deliberately tolerated: reconnect recovery uses a fresh snapshot, not replay.
    request.headers.get("last-event-id")
    try:
        initial = await read_projection(run_id)
    except ProjectionNotFound:
        raise HTTPException(
            status_code=404, detail={"error_code": "RUN_NOT_FOUND"}
        ) from None

    poll_interval = get_settings().sse_poll_interval_seconds

    async def stream() -> AsyncIterator[bytes]:
        previous = initial
        yield _event(event="snapshot", data=snapshot_payload(previous))
        if previous.run["status"] in TERMINAL_RUN_STATUSES:
            return
        loop = asyncio.get_running_loop()
        last_output_at = loop.time()
        try:
            while not await request.is_disconnected():
                await asyncio.sleep(poll_interval)
                if await request.is_disconnected():
                    return
                try:
                    current = await read_projection(run_id)
                except ProjectionNotFound:
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    yield b": evaluation state temporarily unavailable\n\n"
                    last_output_at = loop.time()
                    continue

                changes = project_changes(previous, current)
                previous = current
                for name, payload in changes:
                    yield _event(event=name, data=payload)
                    last_output_at = loop.time()
                if current.run["status"] in TERMINAL_RUN_STATUSES:
                    return
                if not changes and loop.time() - last_output_at >= HEARTBEAT_INTERVAL_SECONDS:
                    yield b": heartbeat\n\n"
                    last_output_at = loop.time()
        except asyncio.CancelledError:
            raise

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
