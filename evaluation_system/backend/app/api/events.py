from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..db.models import Run
from ..db.session import AsyncSessionFactory
from ..services.events import EvaluationEventBus
from ..config import get_settings
from .dependencies import AuthenticatedUserDep


router = APIRouter(tags=["evaluation-events"])


def _event(*, event: str, data: dict, event_id: str | None = None) -> bytes:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append("data: " + json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str))
    return ("\n".join(lines) + "\n\n").encode("utf-8")


@router.get("/runs/{run_id}/events", response_class=StreamingResponse)
async def run_events(
    run_id: uuid.UUID,
    request: Request,
    _user: AuthenticatedUserDep,
):
    if not get_settings().use_celery:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "EVALUATION_BACKGROUND_EXECUTION_UNAVAILABLE"
            },
        )
    async with AsyncSessionFactory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})
        snapshot = {
            "run_id": str(run.id), "status": run.status,
            "completed_sessions": run.completed_sessions, "total_sessions": run.total_sessions,
            "completed_turns": run.completed_turns, "total_turns": run.total_turns,
        }
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "EVALUATION_BACKGROUND_EXECUTION_UNAVAILABLE"
            },
        )
    stream_key = EvaluationEventBus.stream_key(run_id)
    last_id = request.headers.get("last-event-id", "0-0")

    async def stream() -> AsyncIterator[bytes]:
        nonlocal last_id
        yield _event(event="snapshot", data=snapshot)
        if snapshot["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return
        while not await request.is_disconnected():
            try:
                entries = await redis.xread({stream_key: last_id}, count=100, block=15_000)
            except asyncio.CancelledError:
                raise
            except Exception:
                yield b": redis unavailable; durable state remains in PostgreSQL\n\n"
                await asyncio.sleep(2)
                continue
            if not entries:
                yield b": heartbeat\n\n"
                continue
            for _key, messages in entries:
                for event_id, fields in messages:
                    last_id = event_id.decode() if isinstance(event_id, bytes) else str(event_id)
                    raw_event = fields.get(b"event", fields.get("event", b"progress"))
                    raw_data = fields.get(b"data", fields.get("data", b"{}"))
                    name = raw_event.decode() if isinstance(raw_event, bytes) else str(raw_event)
                    data_text = raw_data.decode() if isinstance(raw_data, bytes) else str(raw_data)
                    try:
                        data = json.loads(data_text)
                    except json.JSONDecodeError:
                        data = {"status": "EVENT_DECODE_ERROR"}
                    yield _event(event=name, data=data, event_id=last_id)
                    if name in {"run_completed", "run_failed", "run_cancelled"}:
                        return

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
