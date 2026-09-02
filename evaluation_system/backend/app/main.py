"""Separately deployable RagBot Evaluation API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from .api import datasets, datasources, events, runs, stability, system
from .config import get_settings
from .db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        yield
    finally:
        try:
            await app.state.redis.aclose()
        finally:
            await engine.dispose()


app = FastAPI(
    title="RagBot Evaluation API",
    version="1.0.0",
    lifespan=lifespan,
    # FastAPI's stock Swagger page references public CDNs. Keep only the local
    # OpenAPI JSON; the separately bundled frontend must make zero public calls.
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/v1/evaluation/openapi.json",
)
settings = get_settings()


@app.middleware("http")
async def safe_evaluation_boundary(request: Request, call_next):
    """Prevent content-bearing DB parameters/exceptions from reaching logs."""

    try:
        response = await call_next(request)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"detail": {"error_code": "EVALUATION_INTERNAL_ERROR"}},
            headers={"Cache-Control": "no-store"},
        )
    response.headers["Cache-Control"] = "no-store"
    return response


if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

from .control_plane import router as control_plane_router

app.include_router(control_plane_router)
