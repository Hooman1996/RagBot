"""Evaluation-owned PostgreSQL model set.

There are intentionally no relationships or foreign keys to application tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import EVALUATION_SCHEMA, EvaluationBase


UUID_PK = UUID(as_uuid=True)


class Dataset(EvaluationBase):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint("source_type in ('FILE','MANUAL')", name="ck_datasets_source_type"),
        CheckConstraint(
            "dataset_type in ('PIPELINE_INSPECTION','STABILITY')",
            name="ck_datasets_dataset_type",
        ),
        CheckConstraint("row_count >= 0", name="ck_datasets_row_count"),
        CheckConstraint("session_count >= 0", name="ck_datasets_session_count"),
        CheckConstraint("valid_row_count >= 0", name="ck_datasets_valid_count"),
        CheckConstraint("invalid_row_count >= 0", name="ck_datasets_invalid_count"),
        CheckConstraint(
            "file_sha256 is null or length(file_sha256) = 64",
            name="ck_datasets_file_sha256",
        ),
        CheckConstraint(
            "row_count = valid_row_count + invalid_row_count",
            name="ck_datasets_row_accounting",
        ),
        Index("ix_datasets_created_at", "created_at", "id"),
        Index("ix_datasets_type_created_at", "dataset_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str | None] = mapped_column(Text)
    dataset_type: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    sessions: Mapped[list["DatasetSession"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )


class DatasetSession(EvaluationBase):
    __tablename__ = "dataset_sessions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "first_source_row", name="uq_dataset_sessions_first_row"),
        UniqueConstraint("dataset_id", "source_session_id", name="uq_dataset_sessions_source_id"),
        CheckConstraint("first_source_row >= 1", name="ck_dataset_sessions_first_row"),
        CheckConstraint("turn_count >= 0", name="ck_dataset_sessions_turn_count"),
        Index("ix_dataset_sessions_dataset_id", "dataset_id"),
        Index("ix_dataset_sessions_source_id", "source_session_id"),
        Index("ix_dataset_sessions_dataset_source", "dataset_id", "source_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID_PK,
        ForeignKey(f"{EVALUATION_SCHEMA}.datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_session_id: Mapped[str | None] = mapped_column(Text)
    synthetic_session: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    first_source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    dataset: Mapped[Dataset] = relationship(back_populates="sessions")
    turns: Mapped[list["DatasetTurn"]] = relationship(
        back_populates="dataset_session", cascade="all, delete-orphan", passive_deletes=True
    )


class DatasetTurn(EvaluationBase):
    __tablename__ = "dataset_turns"
    __table_args__ = (
        UniqueConstraint("dataset_session_id", "turn_index", name="uq_dataset_turns_index"),
        CheckConstraint("turn_index >= 1", name="ck_dataset_turns_index"),
        CheckConstraint("btrim(query) <> ''", name="ck_dataset_turns_query"),
        CheckConstraint(
            "source_row_number is null or source_row_number >= 1",
            name="ck_dataset_turns_source_row",
        ),
        Index("ix_dataset_turns_session_id", "dataset_session_id"),
        Index("ix_dataset_turns_session_turn", "dataset_session_id", "turn_index"),
        Index(
            "ix_dataset_turns_time_order",
            "dataset_session_id",
            "source_timestamp",
            "source_row_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    dataset_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID_PK,
        ForeignKey(f"{EVALUATION_SCHEMA}.dataset_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_number: Mapped[int | None] = mapped_column(Integer)
    source_time_raw: Mapped[str | None] = mapped_column(Text)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    query: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    dataset_session: Mapped[DatasetSession] = relationship(back_populates="turns")


class Run(EvaluationBase):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "run_type in ('DATASET_INSPECTION','STABILITY_QUERY','STABILITY_SESSION','STABILITY_DATASET')",
            name="ck_runs_type",
        ),
        CheckConstraint(
            "status in ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')",
            name="ck_runs_status",
        ),
        CheckConstraint("total_sessions >= 0", name="ck_runs_total_sessions"),
        CheckConstraint("completed_sessions >= 0", name="ck_runs_completed_sessions"),
        CheckConstraint("completed_sessions <= total_sessions", name="ck_runs_session_progress"),
        CheckConstraint("total_turns >= 0", name="ck_runs_total_turns"),
        CheckConstraint("completed_turns >= 0", name="ck_runs_completed_turns"),
        CheckConstraint("completed_turns <= total_turns", name="ck_runs_turn_progress"),
        CheckConstraint("fallback_count >= 0", name="ck_runs_fallback_count"),
        CheckConstraint("error_count >= 0", name="ck_runs_error_count"),
        CheckConstraint(
            "infrastructure_error_count >= 0",
            name="ck_runs_infrastructure_error_count",
        ),
        CheckConstraint(
            "finished_at is null or started_at is null or finished_at >= started_at",
            name="ck_runs_finished_after_started",
        ),
        Index("ix_runs_dataset_id", "dataset_id"),
        Index("ix_runs_dataset_created", "dataset_id", "created_at"),
        Index("ix_runs_status_created_at", "status", "created_at"),
        Index("ix_runs_created_at", "created_at", "id"),
        Index("ix_runs_heartbeat_running", "heartbeat_at", postgresql_where=text("status = 'RUNNING'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID_PK, ForeignKey(f"{EVALUATION_SCHEMA}.datasets.id", ondelete="CASCADE")
    )
    run_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    infrastructure_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    git_commit_sha: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_task_id: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(Text)
    failure_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class RunSession(EvaluationBase):
    __tablename__ = "run_sessions"
    __table_args__ = (
        UniqueConstraint("evaluation_session_key", name="uq_run_sessions_eval_key"),
        UniqueConstraint("run_id", "dataset_session_id", "repeat_index", name="uq_run_sessions_repeat"),
        CheckConstraint("repeat_index >= 1", name="ck_run_sessions_repeat"),
        CheckConstraint("turn_count >= 0", name="ck_run_sessions_turn_count"),
        CheckConstraint("fallback_count >= 0", name="ck_run_sessions_fallback_count"),
        CheckConstraint("error_count >= 0", name="ck_run_sessions_error_count"),
        CheckConstraint(
            "infrastructure_error_count >= 0",
            name="ck_run_sessions_infrastructure_error_count",
        ),
        CheckConstraint(
            "total_latency_ms is null or total_latency_ms >= 0",
            name="ck_run_sessions_latency",
        ),
        CheckConstraint(
            "first_divergent_turn is null or first_divergent_turn >= 1",
            name="ck_run_sessions_divergent_turn",
        ),
        CheckConstraint(
            "finished_at is null or started_at is null or finished_at >= started_at",
            name="ck_run_sessions_finished_after_started",
        ),
        CheckConstraint(
            "status in ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')",
            name="ck_run_sessions_status",
        ),
        Index("ix_run_sessions_run_id", "run_id"),
        Index("ix_run_sessions_dataset_session_id", "dataset_session_id"),
        Index("ix_run_sessions_source_id", "source_session_id"),
        Index("ix_run_sessions_status", "status"),
        Index("ix_run_sessions_run_repeat", "run_id", "repeat_index"),
        Index(
            "ix_run_sessions_run_status_repeat",
            "run_id",
            "status",
            "repeat_index",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID_PK, ForeignKey(f"{EVALUATION_SCHEMA}.runs.id", ondelete="CASCADE"), nullable=False)
    dataset_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID_PK, ForeignKey(f"{EVALUATION_SCHEMA}.dataset_sessions.id", ondelete="SET NULL"))
    source_session_id: Mapped[str | None] = mapped_column(Text)
    repeat_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evaluation_session_key: Mapped[uuid.UUID] = mapped_column(UUID_PK, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    infrastructure_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_latency_ms: Mapped[float | None] = mapped_column(Float)
    first_divergent_turn: Mapped[int | None] = mapped_column(Integer)
    first_divergent_stage: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class RunTurn(EvaluationBase):
    __tablename__ = "run_turns"
    __table_args__ = (
        UniqueConstraint("run_session_id", "turn_index", name="uq_run_turns_index"),
        UniqueConstraint("request_id", name="uq_run_turns_request_id"),
        CheckConstraint("turn_index >= 1", name="ck_run_turns_index"),
        CheckConstraint(
            "status in ('PENDING','RUNNING','COMPLETED','ERROR','CANCELLED')",
            name="ck_run_turns_status",
        ),
        CheckConstraint("attempt_count >= 1", name="ck_run_turns_attempt_count"),
        CheckConstraint(
            "total_latency_ms is null or total_latency_ms >= 0",
            name="ck_run_turns_latency",
        ),
        CheckConstraint(
            "history_before_hash is null or length(history_before_hash) = 64",
            name="ck_run_turns_history_before_hash",
        ),
        CheckConstraint(
            "history_after_hash is null or length(history_after_hash) = 64",
            name="ck_run_turns_history_after_hash",
        ),
        CheckConstraint(
            "selected_context_hash is null or length(selected_context_hash) = 64",
            name="ck_run_turns_context_hash",
        ),
        CheckConstraint(
            "finished_at is null or started_at is null or finished_at >= started_at",
            name="ck_run_turns_finished_after_started",
        ),
        Index("ix_run_turns_run_session_id", "run_session_id"),
        Index("ix_run_turns_dataset_turn_id", "dataset_turn_id"),
        Index("ix_run_turns_status", "status"),
        Index("ix_run_turns_session_turn", "run_session_id", "turn_index"),
        Index("ix_run_turns_status_started", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    run_session_id: Mapped[uuid.UUID] = mapped_column(UUID_PK, ForeignKey(f"{EVALUATION_SCHEMA}.run_sessions.id", ondelete="CASCADE"), nullable=False)
    dataset_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID_PK, ForeignKey(f"{EVALUATION_SCHEMA}.dataset_turns.id", ondelete="SET NULL"))
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID_PK, nullable=False, default=uuid.uuid4)
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str | None] = mapped_column(Text)
    history_before_hash: Mapped[str | None] = mapped_column(Text)
    history_after_hash: Mapped[str | None] = mapped_column(Text)
    actual_intent: Mapped[str | None] = mapped_column(Text)
    intent_score: Mapped[float | None] = mapped_column(Float)
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    selected_context_hash: Mapped[str | None] = mapped_column(Text)
    actual_answer: Mapped[str | None] = mapped_column(Text)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    infrastructure_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_latency_ms: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class StageResult(EvaluationBase):
    __tablename__ = "stage_results"
    __table_args__ = (
        UniqueConstraint("run_turn_id", "stage_name", name="uq_stage_results_stage"),
        UniqueConstraint("run_turn_id", "stage_order", name="uq_stage_results_order"),
        CheckConstraint(
            "stage_name in ('NORMALIZATION','INTENT','REWRITE','RETRIEVAL','RERANK','CONTEXT_SELECTION','PROMPT_BUILD','GENERATION')",
            name="ck_stage_results_name",
        ),
        CheckConstraint("stage_order >= 0", name="ck_stage_results_order"),
        CheckConstraint(
            "duration_ms is null or duration_ms >= 0",
            name="ck_stage_results_duration",
        ),
        CheckConstraint(
            "input_hash is null or length(input_hash) = 64",
            name="ck_stage_results_input_hash",
        ),
        CheckConstraint(
            "output_hash is null or length(output_hash) = 64",
            name="ck_stage_results_output_hash",
        ),
        CheckConstraint(
            "status in ('PENDING','RUNNING','COMPLETED','SKIPPED','ERROR')",
            name="ck_stage_results_status",
        ),
        Index("ix_stage_results_run_turn_id", "run_turn_id"),
        Index("ix_stage_results_turn_order", "run_turn_id", "stage_order"),
        Index("ix_stage_results_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID_PK, primary_key=True, default=uuid.uuid4)
    run_turn_id: Mapped[uuid.UUID] = mapped_column(UUID_PK, ForeignKey(f"{EVALUATION_SCHEMA}.run_turns.id", ondelete="CASCADE"), nullable=False)
    stage_name: Mapped[str] = mapped_column(Text, nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str | None] = mapped_column(Text)
    output_hash: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    input_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
