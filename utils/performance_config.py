"""Validated application-side performance settings loaded from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be at least 0")
    return value


def _nonnegative_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not value >= 0:
        raise ValueError(f"{name} must be at least 0")
    return value


def _strict_probability(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not 0 < value <= 1:
        raise ValueError(f"{name} must be greater than 0 and at most 1")
    return value


def _probability(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def _bounded_positive_float(
    name: str, default: float, *, maximum: float
) -> float:
    value = _positive_float(name, default)
    if value > maximum:
        raise ValueError(f"{name} cannot exceed {maximum}")
    return value


@dataclass(frozen=True)
class PerformanceSettings:
    application_request_timeout_seconds: float
    request_concurrency_limit: int
    request_admission_timeout_seconds: float
    blocking_concurrency_limit: int
    tei_http_max_connections: int
    tei_http_max_keepalive_connections: int
    tei_http_keepalive_expiry_seconds: float
    tei_http_connect_timeout_seconds: float
    tei_http_read_timeout_seconds: float
    tei_http_write_timeout_seconds: float
    tei_http_pool_timeout_seconds: float
    tei_embed_insert_batch_size: int
    tei_embed_max_client_batch_size: int
    vllm_http_max_connections: int
    vllm_http_max_keepalive_connections: int
    vllm_http_keepalive_expiry_seconds: float
    vllm_http_connect_timeout_seconds: float
    vllm_http_read_timeout_seconds: float
    vllm_http_write_timeout_seconds: float
    vllm_http_pool_timeout_seconds: float
    qdrant_concurrency: int
    rag_retrieval_top_k: int
    rag_semantic_candidate_limit: int
    rag_related_questions_rerank_threshold: float
    mobile_related_questions_rerank_threshold: float
    rag_max_new_tokens: int
    rag_chitchat_max_new_tokens: int
    rag_rewrite_max_tokens: int
    rag_answer_temperature: float
    rag_answer_top_p: float
    rag_answer_seed: int
    rag_chitchat_temperature: float
    rag_chitchat_top_p: float
    rag_chitchat_seed: int
    rag_rewrite_temperature: float
    rag_rewrite_top_p: float
    rag_rewrite_seed: int
    mass_answer_row_concurrency: int
    mass_answer_row_timeout_seconds: float
    mass_answer_direct_max_rows: int
    mass_answer_job_retention_hours: int
    mass_answer_max_rows: int
    mass_answer_max_upload_mb: int


def load_performance_settings() -> PerformanceSettings:
    settings = PerformanceSettings(
        application_request_timeout_seconds=_bounded_positive_float(
            "APPLICATION_REQUEST_TIMEOUT_SECONDS", 50.0, maximum=50.0
        ),
        request_concurrency_limit=_positive_int(
            "REQUEST_CONCURRENCY_LIMIT", 32
        ),
        request_admission_timeout_seconds=_positive_float(
            "REQUEST_ADMISSION_TIMEOUT_SECONDS", 12.0
        ),
        blocking_concurrency_limit=_positive_int(
            "BLOCKING_CONCURRENCY_LIMIT", 16
        ),
        tei_http_max_connections=_positive_int(
            "TEI_HTTP_MAX_CONNECTIONS", 32
        ),
        tei_http_max_keepalive_connections=_positive_int(
            "TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS", 16
        ),
        tei_http_keepalive_expiry_seconds=_positive_float(
            "TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS", 30.0
        ),
        tei_http_connect_timeout_seconds=_positive_float(
            "TEI_HTTP_CONNECT_TIMEOUT_SECONDS", 3.0
        ),
        tei_http_read_timeout_seconds=_positive_float(
            "TEI_HTTP_READ_TIMEOUT_SECONDS", 15.0
        ),
        tei_http_write_timeout_seconds=_positive_float(
            "TEI_HTTP_WRITE_TIMEOUT_SECONDS", 5.0
        ),
        tei_http_pool_timeout_seconds=_positive_float(
            "TEI_HTTP_POOL_TIMEOUT_SECONDS", 3.0
        ),
        tei_embed_insert_batch_size=_positive_int(
            "TEI_EMBED_INSERT_BATCH_SIZE", 32
        ),
        tei_embed_max_client_batch_size=_positive_int(
            "TEI_EMBED_MAX_CLIENT_BATCH_SIZE", 50
        ),
        vllm_http_max_connections=_positive_int(
            "VLLM_HTTP_MAX_CONNECTIONS", 32
        ),
        vllm_http_max_keepalive_connections=_positive_int(
            "VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS", 16
        ),
        vllm_http_keepalive_expiry_seconds=_positive_float(
            "VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS", 30.0
        ),
        vllm_http_connect_timeout_seconds=_positive_float(
            "VLLM_HTTP_CONNECT_TIMEOUT_SECONDS", 3.0
        ),
        vllm_http_read_timeout_seconds=_positive_float(
            "VLLM_HTTP_READ_TIMEOUT_SECONDS", 45.0
        ),
        vllm_http_write_timeout_seconds=_positive_float(
            "VLLM_HTTP_WRITE_TIMEOUT_SECONDS", 5.0
        ),
        vllm_http_pool_timeout_seconds=_positive_float(
            "VLLM_HTTP_POOL_TIMEOUT_SECONDS", 3.0
        ),
        qdrant_concurrency=_positive_int("QDRANT_CONCURRENCY", 4),
        rag_retrieval_top_k=_positive_int("RAG_RETRIEVAL_TOP_K", 10),
        rag_semantic_candidate_limit=_positive_int(
            "RAG_SEMANTIC_CANDIDATE_LIMIT", 50
        ),
        rag_related_questions_rerank_threshold=_probability(
            "RAG_RELATED_QUESTIONS_RERANK_THRESHOLD", 0.1
        ),
        mobile_related_questions_rerank_threshold=_probability(
            "MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD", 0.5
        ),
        rag_max_new_tokens=_positive_int("RAG_MAX_NEW_TOKENS", 500),
        rag_chitchat_max_new_tokens=_positive_int(
            "RAG_CHITCHAT_MAX_NEW_TOKENS", 200
        ),
        rag_rewrite_max_tokens=_positive_int(
            "RAG_REWRITE_MAX_TOKENS", 1000
        ),
        rag_answer_temperature=_nonnegative_float(
            "RAG_ANSWER_TEMPERATURE", 0.0
        ),
        rag_answer_top_p=_strict_probability("RAG_ANSWER_TOP_P", 1.0),
        rag_answer_seed=_nonnegative_int("RAG_ANSWER_SEED", 42),
        rag_chitchat_temperature=_nonnegative_float(
            "RAG_CHITCHAT_TEMPERATURE", 0.0
        ),
        rag_chitchat_top_p=_strict_probability(
            "RAG_CHITCHAT_TOP_P", 1.0
        ),
        rag_chitchat_seed=_nonnegative_int("RAG_CHITCHAT_SEED", 42),
        rag_rewrite_temperature=_nonnegative_float(
            "RAG_REWRITE_TEMPERATURE", 0.0
        ),
        rag_rewrite_top_p=_strict_probability("RAG_REWRITE_TOP_P", 1.0),
        rag_rewrite_seed=_nonnegative_int("RAG_REWRITE_SEED", 42),
        mass_answer_row_concurrency=_positive_int(
            "MASS_ANSWER_ROW_CONCURRENCY", 4
        ),
        mass_answer_row_timeout_seconds=_positive_float(
            "MASS_ANSWER_ROW_TIMEOUT_SECONDS", 50.0
        ),
        mass_answer_direct_max_rows=_positive_int(
            "MASS_ANSWER_DIRECT_MAX_ROWS", 20
        ),
        mass_answer_job_retention_hours=_positive_int(
            "MASS_ANSWER_JOB_RETENTION_HOURS", 24
        ),
        mass_answer_max_rows=_positive_int("MASS_ANSWER_MAX_ROWS", 5000),
        mass_answer_max_upload_mb=_positive_int(
            "MASS_ANSWER_MAX_UPLOAD_MB", 10
        ),
    )
    if (
        settings.tei_http_max_keepalive_connections
        > settings.tei_http_max_connections
    ):
        raise ValueError(
            "TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS cannot exceed "
            "TEI_HTTP_MAX_CONNECTIONS"
        )
    if (
        settings.tei_embed_insert_batch_size
        > settings.tei_embed_max_client_batch_size
    ):
        raise ValueError(
            "TEI_EMBED_INSERT_BATCH_SIZE cannot exceed "
            "TEI_EMBED_MAX_CLIENT_BATCH_SIZE"
        )
    if (
        settings.vllm_http_max_keepalive_connections
        > settings.vllm_http_max_connections
    ):
        raise ValueError(
            "VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS cannot exceed "
            "VLLM_HTTP_MAX_CONNECTIONS"
        )
    if settings.rag_retrieval_top_k > settings.rag_semantic_candidate_limit:
        raise ValueError(
            "RAG_RETRIEVAL_TOP_K cannot exceed "
            "RAG_SEMANTIC_CANDIDATE_LIMIT"
        )
    return settings


PERFORMANCE_SETTINGS = load_performance_settings()
