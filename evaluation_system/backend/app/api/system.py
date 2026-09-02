from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ..config import EvaluationSettings, get_settings
from ..schemas.api import DatabaseInitializeRequest
from ..services.migrations import MigrationService
from .dependencies import AuthenticatedUserDep


router = APIRouter(prefix="/system", tags=["evaluation-system"])


@router.get("/database-status")
async def database_status(
    _user: AuthenticatedUserDep,
    settings: Annotated[EvaluationSettings, Depends(get_settings)],
) -> dict[str, Any]:
    return (await asyncio.to_thread(MigrationService(settings).status)).as_dict()


@router.post("/database-initialize")
async def database_initialize(
    body: DatabaseInitializeRequest,
    _user: AuthenticatedUserDep,
    settings: Annotated[EvaluationSettings, Depends(get_settings)],
) -> dict[str, Any]:
    try:
        status = await asyncio.to_thread(MigrationService(settings).initialize, body.confirmation)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"error_code": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error_code": str(exc)}) from exc
    except RuntimeError as exc:
        code = str(exc)
        raise HTTPException(status_code=409 if code == "MIGRATION_ALREADY_RUNNING" else 500, detail={"error_code": code}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error_code": "EVALUATION_MIGRATION_ERROR"}) from exc
    return status.as_dict()


@router.get("/capabilities")
async def capabilities(
    _user: AuthenticatedUserDep,
    settings: Annotated[EvaluationSettings, Depends(get_settings)],
) -> dict[str, Any]:
    return {
        "file_types": [".csv", ".xlsx"],
        "max_upload_bytes": settings.max_upload_bytes,
        "max_dataset_rows": settings.max_dataset_rows,
        "session_concurrency": settings.session_concurrency,
        "stability_default_concurrency": 1,
        "repeat_max": settings.repeat_max,
        "background_execution_available": settings.use_celery,
        "allow_database_initialize": settings.allow_db_init,
    }
