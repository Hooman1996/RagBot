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


def _positive_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _ragbot_base_url() -> str:
    value = os.getenv("EVAL_RAGBOT_BASE_URL", "http://127.0.0.1:8080").strip()
    if not value:
        raise ValueError("EVAL_RAGBOT_BASE_URL must not be empty")
    return value.rstrip("/")


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
    sse_poll_interval_seconds: float
    worker_poll_interval_seconds: float
    worker_stale_after_seconds: int
    session_concurrency: int
    repeat_max: int
    max_upload_bytes: int
    max_dataset_rows: int
    ragbot_base_url: str
    ragbot_http_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "EvaluationSettings":
        origins = tuple(
            item.strip()
            for item in os.getenv("EVAL_CORS_ORIGINS", "").split(",")
            if item.strip()
        )
        ragbot_http_timeout_seconds = _positive_float(
            "EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS", 70.0
        )
        worker_stale_after_seconds = _positive_int(
            "EVAL_WORKER_STALE_AFTER_SECONDS", 300
        )
        if worker_stale_after_seconds <= ragbot_http_timeout_seconds:
            raise ValueError(
                "EVAL_WORKER_STALE_AFTER_SECONDS must be greater than "
                "EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS"
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
            sse_poll_interval_seconds=_positive_float(
                "EVAL_SSE_POLL_INTERVAL_SECONDS", 1.0
            ),
            worker_poll_interval_seconds=_positive_float(
                "EVAL_WORKER_POLL_INTERVAL_SECONDS", 1.0
            ),
            worker_stale_after_seconds=worker_stale_after_seconds,
            session_concurrency=_positive_int("EVAL_SESSION_CONCURRENCY", 1),
            repeat_max=_positive_int("EVAL_REPEAT_MAX", 100),
            max_upload_bytes=_positive_int(
                "EVAL_MAX_UPLOAD_BYTES", 20 * 1024 * 1024
            ),
            max_dataset_rows=_positive_int("EVAL_MAX_DATASET_ROWS", 50_000),
            ragbot_base_url=_ragbot_base_url(),
            ragbot_http_timeout_seconds=ragbot_http_timeout_seconds,
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
