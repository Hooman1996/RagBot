"""Mount the evaluation control plane and built UI into an existing app."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .config import EvaluationSettings


def install_evaluation_routes(
    app: FastAPI,
    settings: EvaluationSettings,
    *,
    frontend_dist: Path,
    control_plane_router=None,
) -> bool:
    if not settings.enabled:
        return False

    if control_plane_router is None:
        from .control_plane import router as configured_control_plane_router

        control_plane_router = configured_control_plane_router
    app.include_router(control_plane_router)
    index_file = frontend_dist / "index.html"
    if index_file.is_file():
        app.mount(
            "/evaluation",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="evaluation-frontend",
        )
    else:
        @app.get("/evaluation", include_in_schema=False)
        @app.get("/evaluation/", include_in_schema=False)
        async def evaluation_frontend_not_built():
            raise HTTPException(
                status_code=503,
                detail={"error_code": "EVALUATION_FRONTEND_NOT_BUILT"},
            )
    return True
