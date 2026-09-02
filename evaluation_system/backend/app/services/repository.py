"""Evaluation-only persistence operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Dataset, DatasetSession, DatasetTurn, Run, RunSession, RunTurn, StageResult
from .importer import ParsedDataset
from .run_planning import build_run_session_specs, validate_run_shape


async def persist_parsed_dataset(session: AsyncSession, parsed: ParsedDataset) -> Dataset:
    dataset = Dataset(
        filename=parsed.filename,
        source_type=parsed.source_type,
        file_sha256=parsed.file_sha256,
        dataset_type=parsed.dataset_type,
        row_count=parsed.row_count,
        session_count=parsed.session_count,
        valid_row_count=parsed.valid_row_count,
        invalid_row_count=parsed.invalid_row_count,
        metadata_json={
            **parsed.metadata,
            "issues": [issue.as_dict() for issue in parsed.issues],
        },
    )
    session.add(dataset)
    await session.flush()
    for parsed_session in parsed.sessions:
        timestamps = [turn.source_timestamp for turn in parsed_session.turns if turn.source_timestamp]
        row = DatasetSession(
            dataset_id=dataset.id,
            source_session_id=parsed_session.source_session_id,
            synthetic_session=parsed_session.synthetic_session,
            first_source_row=min(turn.source_row_number for turn in parsed_session.turns),
            first_source_timestamp=min(timestamps) if timestamps else None,
            last_source_timestamp=max(timestamps) if timestamps else None,
            turn_count=len(parsed_session.turns),
            metadata_json={
                **parsed_session.metadata,
                "synthetic_label": parsed_session.synthetic_label,
            },
        )
        session.add(row)
        await session.flush()
        session.add_all([
            DatasetTurn(
                dataset_session_id=row.id,
                turn_index=turn.turn_index,
                source_row_number=turn.source_row_number,
                source_time_raw=turn.source_time_raw,
                source_timestamp=turn.source_timestamp,
                query=turn.query,
                metadata_json=turn.metadata,
            )
            for turn in parsed_session.turns
        ])
    await session.flush()
    return dataset


async def get_dataset(session: AsyncSession, dataset_id: uuid.UUID) -> Dataset | None:
    return await session.get(Dataset, dataset_id)


async def delete_dataset(session: AsyncSession, dataset_id: uuid.UUID) -> bool:
    result = await session.execute(delete(Dataset).where(Dataset.id == dataset_id))
    return bool(result.rowcount)


async def delete_run(session: AsyncSession, run_id: uuid.UUID) -> bool:
    result = await session.execute(delete(Run).where(Run.id == run_id))
    return bool(result.rowcount)


async def list_datasets(session: AsyncSession, limit: int = 100) -> list[Dataset]:
    rows = await session.scalars(select(Dataset).order_by(Dataset.created_at.desc(), Dataset.id).limit(limit))
    return list(rows)


async def list_runs(session: AsyncSession, limit: int = 100) -> list[Run]:
    rows = await session.scalars(select(Run).order_by(Run.created_at.desc(), Run.id).limit(limit))
    return list(rows)


async def create_run(
    session: AsyncSession,
    *,
    dataset: Dataset,
    run_type: str,
    repeat_count: int,
    config_snapshot: dict[str, Any],
    git_commit_sha: str | None,
) -> Run:
    dataset_sessions = list(await session.scalars(
        select(DatasetSession).where(DatasetSession.dataset_id == dataset.id).order_by(DatasetSession.first_source_row)
    ))
    validate_run_shape(
        run_type,
        repeat_count,
        [item.turn_count for item in dataset_sessions],
    )
    total_turns_per_repeat = sum(item.turn_count for item in dataset_sessions)
    run = Run(
        dataset_id=dataset.id,
        run_type=run_type,
        status="PENDING",
        config_snapshot=config_snapshot,
        total_sessions=len(dataset_sessions) * repeat_count,
        total_turns=total_turns_per_repeat * repeat_count,
        git_commit_sha=git_commit_sha,
        metadata_json={"repeat_count": repeat_count},
    )
    session.add(run)
    await session.flush()
    sources_by_id = {source.id: source for source in dataset_sessions}
    for spec in build_run_session_specs(list(sources_by_id), repeat_count):
        source = sources_by_id[spec.dataset_session_id]
        session.add(RunSession(
            run_id=run.id,
            dataset_session_id=source.id,
            source_session_id=source.source_session_id,
            repeat_index=spec.repeat_index,
            evaluation_session_key=spec.evaluation_session_key,
            status="PENDING",
            turn_count=source.turn_count,
            metadata_json={
                "synthetic_session": source.synthetic_session,
                "synthetic_label": (source.metadata_json or {}).get(
                    "synthetic_label"
                ),
            },
        ))
    await session.flush()
    return run


async def utcnow() -> datetime:
    return datetime.now(timezone.utc)
