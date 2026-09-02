"""Separately startable Celery application."""

from celery import Celery

from ..config import get_settings


settings = get_settings()
celery_app = Celery(
    "ragbot_evaluation",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["evaluation_system.backend.app.worker.tasks"],
)
celery_app.conf.update(
    task_default_queue=settings.celery_queue,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_pool=settings.celery_pool,
    worker_concurrency=settings.celery_concurrency,
)
