"""Evaluation routers for inclusion in the existing RagBot FastAPI app."""

from fastapi import APIRouter

from .api import datasets, datasources, events, runs, stability, system


router = APIRouter(prefix="/api/v1/evaluation")
router.include_router(system.router)
router.include_router(datasets.router)
router.include_router(datasources.router)
router.include_router(runs.router)
router.include_router(stability.router)
router.include_router(events.router)
