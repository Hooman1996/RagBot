from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..config import get_settings
from ..schemas.api import DeleteResponse
from ..services.importer import DatasetImportError, parse_dataset_file
from ..services.repository import delete_dataset, get_dataset, list_datasets, persist_parsed_dataset
from ..db.models import DatasetSession, DatasetTurn, Run
from sqlalchemy import select
from .dependencies import AuthenticatedUserDep, DatabaseDep


router = APIRouter(prefix="/datasets", tags=["evaluation-datasets"])


async def _read_limited(upload: UploadFile, maximum: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > maximum:
            raise HTTPException(status_code=413, detail={"error_code": "UPLOAD_TOO_LARGE"})
        chunks.append(chunk)
    return b"".join(chunks)


def _dataset_dict(row) -> dict:
    return {
        "id": row.id, "filename": row.filename, "source_type": row.source_type,
        "file_sha256": row.file_sha256, "dataset_type": row.dataset_type,
        "row_count": row.row_count, "session_count": row.session_count,
        "valid_row_count": row.valid_row_count, "invalid_row_count": row.invalid_row_count,
        "created_at": row.created_at, "metadata": row.metadata_json,
    }


@router.post("/import")
async def import_dataset(
    _user: AuthenticatedUserDep,
    db: DatabaseDep,
    file: Annotated[UploadFile, File()],
    dataset_type: Annotated[Literal["PIPELINE_INSPECTION", "STABILITY"], Form()] = "PIPELINE_INSPECTION",
) -> dict:
    settings = get_settings()
    content = await _read_limited(file, settings.max_upload_bytes)
    filename = file.filename or "dataset"
    try:
        parsed = await asyncio.to_thread(
            parse_dataset_file, filename=filename, content=content,
            dataset_type=dataset_type, max_rows=settings.max_dataset_rows,
        )
    except DatasetImportError as exc:
        raise HTTPException(status_code=422, detail={"error_code": exc.code, "message": exc.public_message}) from exc
    finally:
        content = b""
        await file.close()
    row = await persist_parsed_dataset(db, parsed)
    await db.commit()
    return {"dataset": _dataset_dict(row), "summary": parsed.summary()}


@router.get("")
async def get_datasets(_user: AuthenticatedUserDep, db: DatabaseDep) -> list[dict]:
    return [_dataset_dict(row) for row in await list_datasets(db)]


@router.get("/{dataset_id}")
async def get_dataset_by_id(dataset_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> dict:
    row = await get_dataset(db, dataset_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"error_code": "DATASET_NOT_FOUND"})
    return _dataset_dict(row)


@router.get("/{dataset_id}/sessions")
async def get_dataset_sessions(dataset_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> list[dict]:
    rows = list(await db.scalars(
        select(DatasetSession).where(DatasetSession.dataset_id == dataset_id).order_by(DatasetSession.first_source_row)
    ))
    return [{
        "id": row.id, "source_session_id": row.source_session_id,
        "synthetic_session": row.synthetic_session,
        "first_source_row": row.first_source_row,
        "first_source_timestamp": row.first_source_timestamp,
        "last_source_timestamp": row.last_source_timestamp,
        "turn_count": row.turn_count, "metadata": row.metadata_json,
    } for row in rows]


@router.get("/sessions/{dataset_session_id}/turns")
async def get_dataset_session_turns(dataset_session_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> list[dict]:
    rows = list(await db.scalars(
        select(DatasetTurn).where(DatasetTurn.dataset_session_id == dataset_session_id).order_by(DatasetTurn.turn_index)
    ))
    return [{
        "id": row.id, "turn_index": row.turn_index,
        "source_row_number": row.source_row_number,
        "source_time_raw": row.source_time_raw,
        "source_timestamp": row.source_timestamp,
        "query": row.query, "metadata": row.metadata_json,
    } for row in rows]


@router.delete("/{dataset_id}", response_model=DeleteResponse)
async def remove_dataset(dataset_id: uuid.UUID, _user: AuthenticatedUserDep, db: DatabaseDep) -> DeleteResponse:
    active_run = await db.scalar(
        select(Run.id).where(
            Run.dataset_id == dataset_id,
            Run.status.in_(["PENDING", "RUNNING"]),
        ).limit(1)
    )
    if active_run is not None:
        raise HTTPException(
            status_code=409,
            detail={"error_code": "DATASET_HAS_ACTIVE_RUN"},
        )
    deleted = await delete_dataset(db, dataset_id)
    await db.commit()
    return DeleteResponse(deleted=deleted)
