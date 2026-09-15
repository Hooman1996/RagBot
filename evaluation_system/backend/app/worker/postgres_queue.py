"""Atomic PostgreSQL claiming for durable evaluation runs."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select

from ..db.models import Run


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def build_claim_statement(stale_cutoff: datetime):
    """Build the PostgreSQL locking query used by every worker instance."""

    effective_activity = func.coalesce(
        Run.heartbeat_at, Run.started_at, Run.created_at
    )
    return (
        select(Run)
        .where(
            or_(
                Run.status == "PENDING",
                and_(
                    Run.status == "RUNNING",
                    effective_activity < stale_cutoff,
                ),
            )
        )
        .order_by(Run.created_at.asc(), Run.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )


class PostgresRunQueue:
    """Claim at most one run, committing ownership before execution begins."""

    def __init__(self, *, session_factory, stale_after_seconds: int) -> None:
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")
        self.session_factory = session_factory
        self.stale_after_seconds = stale_after_seconds

    async def claim_next(self, worker_id: str) -> uuid.UUID | None:
        claimed_at = now_utc()
        stale_cutoff = claimed_at - timedelta(seconds=self.stale_after_seconds)
        async with self.session_factory() as session:
            run = await session.scalar(build_claim_statement(stale_cutoff))
            if run is None:
                return None
            was_pending = run.status == "PENDING"
            run.status = "RUNNING"
            run.worker_task_id = worker_id
            run.heartbeat_at = claimed_at
            if was_pending:
                run.started_at = run.started_at or claimed_at
            await session.commit()
            return run.id
