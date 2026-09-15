from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..clients.ragbot import RagBotClientError, RagBotEvaluationClient
from ..config import get_settings
from .dependencies import AuthenticatedUserDep


router = APIRouter(tags=["evaluation-datasources"])


@router.get("/datasources")
async def list_datasources(_user: AuthenticatedUserDep) -> list[dict]:
    settings = get_settings()
    try:
        async with RagBotEvaluationClient(
            base_url=settings.ragbot_base_url,
            timeout_seconds=settings.ragbot_http_timeout_seconds,
        ) as client:
            response = await client.list_datasources()
    except RagBotClientError as exc:
        raise HTTPException(status_code=503, detail={"error_code": "DATASOURCE_LOOKUP_UNAVAILABLE"}) from exc
    return [{"title": item.name} for item in response.documents if item.name]
