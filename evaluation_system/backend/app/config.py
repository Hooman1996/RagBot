"""Environment-backed evaluation settings without secret rendering."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


# Match the existing RagBot configuration behavior without changing the file.
load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


@dataclass(frozen=True)
class EvaluationSettings:
    enabled: bool
    api_host: str
    api_port: int
    postgres_host: str | None
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    allow_db_init: bool
    cors_origins: tuple[str, ...]
    redis_url: str
    use_celery: bool
    celery_queue: str
    celery_pool: str
    celery_concurrency: int
    session_concurrency: int
    repeat_max: int
    max_upload_bytes: int
    max_dataset_rows: int
    qdrant_collection: str

    @classmethod
    def from_environment(cls) -> "EvaluationSettings":
        origins = tuple(
            item.strip()
            for item in os.getenv("EVAL_CORS_ORIGINS", "").split(",")
            if item.strip()
        )
        return cls(
            enabled=_bool("EVAL_ENABLED", False),
            api_host=os.getenv("EVAL_API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("EVAL_API_PORT", "8090")),
            postgres_host=os.getenv("POSTGRES_HOST"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("POSTGRES_DB", "hihelp_db"),
            postgres_user=os.getenv("POSTGRES_USER", "postgres"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "postgres"),
            allow_db_init=_bool("EVAL_ALLOW_DB_INIT", False),
            cors_origins=origins,
            redis_url=os.getenv("EVAL_REDIS_URL", "redis://127.0.0.1:6379/1"),
            use_celery=_bool("EVAL_USE_CELERY", True),
            celery_queue=os.getenv("EVAL_CELERY_QUEUE", "ragbot-evaluation"),
            celery_pool=os.getenv("EVAL_CELERY_POOL", "solo"),
            celery_concurrency=_positive_int("EVAL_CELERY_CONCURRENCY", 1),
            session_concurrency=_positive_int("EVAL_SESSION_CONCURRENCY", 1),
            repeat_max=_positive_int("EVAL_REPEAT_MAX", 100),
            max_upload_bytes=_positive_int(
                "EVAL_MAX_UPLOAD_BYTES", 20 * 1024 * 1024
            ),
            max_dataset_rows=_positive_int("EVAL_MAX_DATASET_ROWS", 50_000),
            qdrant_collection=os.getenv(
                "QDRANT_COLLECTION", "hihelp_embeddings"
            ),
        )

    def sqlalchemy_url(self, *, async_driver: bool) -> object:
        from sqlalchemy import URL

        return URL.create(
            "postgresql+asyncpg" if async_driver else "postgresql+psycopg2",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache(maxsize=1)
def get_settings() -> EvaluationSettings:
    return EvaluationSettings.from_environment()
