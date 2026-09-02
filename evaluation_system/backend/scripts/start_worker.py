"""Start the evaluation worker using root-.env-backed settings."""

from evaluation_system.backend.app.config import get_settings
from evaluation_system.backend.app.worker.celery_app import celery_app


def build_worker_argv(settings) -> list[str]:
    """Return the fully explicit, root-.env-backed Celery worker arguments."""

    return [
        "worker",
        "--loglevel=INFO",
        f"--queues={settings.celery_queue}",
        f"--pool={settings.celery_pool}",
        f"--concurrency={settings.celery_concurrency}",
    ]


def main() -> int:
    settings = get_settings()
    if not settings.enabled:
        raise SystemExit("Evaluation is disabled: set EVAL_ENABLED=true in root .env")
    if not settings.use_celery:
        raise SystemExit("Celery is disabled: set EVAL_USE_CELERY=true in root .env")
    celery_app.worker_main(build_worker_argv(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
