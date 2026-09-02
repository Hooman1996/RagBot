from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException

from new_architecture.app.services.history.database import DatabaseManager

from .dependencies import AuthenticatedUserDep


router = APIRouter(tags=["evaluation-datasources"])


@router.get("/datasources")
async def list_datasources(_user: AuthenticatedUserDep) -> list[dict]:
    manager = DatabaseManager(
        host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"),
        dbname=os.getenv("POSTGRES_DB"), user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )
    try:
        rows = await asyncio.to_thread(manager.get_available_documents)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"error_code": "DATASOURCE_LOOKUP_UNAVAILABLE"}) from exc
    return [{"title": str(row.get("title", ""))} for row in rows if row.get("title")]
