"""Create the isolated RagBot evaluation V1 schema.

Revision ID: 20260831_0001
Revises: None
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_0001"
down_revision = None
branch_labels = None
depends_on = None
SCHEMA = "evaluation"
JSON_DEFAULT = sa.text("'{}'::jsonb")


def uuid_column(name="id", *, nullable=False):
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade():
    op.execute("create schema if not exists evaluation")
    op.create_table(
        "datasets",
        uuid_column(), sa.Column("filename", sa.Text()),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.Text()),
        sa.Column("dataset_type", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False),
        sa.Column("valid_row_count", sa.Integer(), nullable=False),
        sa.Column("invalid_row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=JSON_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_datasets"),
        sa.CheckConstraint("source_type in ('FILE','MANUAL')", name="ck_datasets_source_type"),
        sa.CheckConstraint("dataset_type in ('PIPELINE_INSPECTION','STABILITY')", name="ck_datasets_dataset_type"),
        sa.CheckConstraint("row_count >= 0", name="ck_datasets_row_count"),
        sa.CheckConstraint("session_count >= 0", name="ck_datasets_session_count"),
        sa.CheckConstraint("valid_row_count >= 0", name="ck_datasets_valid_count"),
        sa.CheckConstraint("invalid_row_count >= 0", name="ck_datasets_invalid_count"),
        sa.CheckConstraint("file_sha256 is null or length(file_sha256) = 64", name="ck_datasets_file_sha256"),
        sa.CheckConstraint("row_count = valid_row_count + invalid_row_count", name="ck_datasets_row_accounting"),
        schema=SCHEMA,
    )
    op.create_index("ix_datasets_created_at", "datasets", ["created_at", "id"], schema=SCHEMA)
    op.create_index("ix_datasets_type_created_at", "datasets", ["dataset_type", "created_at"], schema=SCHEMA)

    op.create_table(
        "dataset_sessions",
        uuid_column(), uuid_column("dataset_id"),
        sa.Column("source_session_id", sa.Text()),
        sa.Column("synthetic_session", sa.Boolean(), nullable=False),
        sa.Column("first_source_row", sa.Integer(), nullable=False),
        sa.Column("first_source_timestamp", sa.DateTime(timezone=True)),
        sa.Column("last_source_timestamp", sa.DateTime(timezone=True)),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=JSON_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_sessions"),
        sa.ForeignKeyConstraint(["dataset_id"], ["evaluation.datasets.id"], ondelete="CASCADE", name="fk_dataset_sessions_dataset"),
        sa.UniqueConstraint("dataset_id", "first_source_row", name="uq_dataset_sessions_first_row"),
        sa.UniqueConstraint("dataset_id", "source_session_id", name="uq_dataset_sessions_source_id"),
        sa.CheckConstraint("first_source_row >= 1", name="ck_dataset_sessions_first_row"),
        sa.CheckConstraint("turn_count >= 0", name="ck_dataset_sessions_turn_count"),
        schema=SCHEMA,
    )
    for name, columns in (
        ("ix_dataset_sessions_dataset_id", ["dataset_id"]),
        ("ix_dataset_sessions_source_id", ["source_session_id"]),
        ("ix_dataset_sessions_dataset_source", ["dataset_id", "source_session_id"]),
    ):
        op.create_index(name, "dataset_sessions", columns, schema=SCHEMA)

    op.create_table(
        "dataset_turns",
        uuid_column(), uuid_column("dataset_session_id"),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("source_row_number", sa.Integer()),
        sa.Column("source_time_raw", sa.Text()),
        sa.Column("source_timestamp", sa.DateTime(timezone=True)),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=JSON_DEFAULT, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_turns"),
        sa.ForeignKeyConstraint(["dataset_session_id"], ["evaluation.dataset_sessions.id"], ondelete="CASCADE", name="fk_dataset_turns_session"),
        sa.UniqueConstraint("dataset_session_id", "turn_index", name="uq_dataset_turns_index"),
        sa.CheckConstraint("turn_index >= 1", name="ck_dataset_turns_index"),
        sa.CheckConstraint("btrim(query) <> ''", name="ck_dataset_turns_query"),
        sa.CheckConstraint("source_row_number is null or source_row_number >= 1", name="ck_dataset_turns_source_row"),
        schema=SCHEMA,
    )
    op.create_index("ix_dataset_turns_session_id", "dataset_turns", ["dataset_session_id"], schema=SCHEMA)
    op.create_index("ix_dataset_turns_session_turn", "dataset_turns", ["dataset_session_id", "turn_index"], schema=SCHEMA)
    op.create_index("ix_dataset_turns_time_order", "dataset_turns", ["dataset_session_id", "source_timestamp", "source_row_number"], schema=SCHEMA)

    op.create_table(
        "runs",
        uuid_column(), uuid_column("dataset_id", nullable=True),
        sa.Column("run_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), server_default=JSON_DEFAULT, nullable=False),
        sa.Column("total_sessions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_sessions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_turns", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_turns", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fallback_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("infrastructure_error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("git_commit_sha", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("worker_task_id", sa.Text()),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.Text()),
        sa.Column("failure_data", postgresql.JSONB()),
        sa.Column("metadata", postgresql.JSONB(), server_default=JSON_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
        sa.ForeignKeyConstraint(["dataset_id"], ["evaluation.datasets.id"], ondelete="CASCADE", name="fk_runs_dataset"),
        sa.CheckConstraint("run_type in ('DATASET_INSPECTION','STABILITY_QUERY','STABILITY_SESSION','STABILITY_DATASET')", name="ck_runs_type"),
        sa.CheckConstraint("status in ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="ck_runs_status"),
        sa.CheckConstraint("total_sessions >= 0", name="ck_runs_total_sessions"),
        sa.CheckConstraint("completed_sessions >= 0", name="ck_runs_completed_sessions"),
        sa.CheckConstraint("completed_sessions <= total_sessions", name="ck_runs_session_progress"),
        sa.CheckConstraint("total_turns >= 0", name="ck_runs_total_turns"),
        sa.CheckConstraint("completed_turns >= 0", name="ck_runs_completed_turns"),
        sa.CheckConstraint("completed_turns <= total_turns", name="ck_runs_turn_progress"),
        sa.CheckConstraint("fallback_count >= 0", name="ck_runs_fallback_count"),
        sa.CheckConstraint("error_count >= 0", name="ck_runs_error_count"),
        sa.CheckConstraint("infrastructure_error_count >= 0", name="ck_runs_infrastructure_error_count"),
        sa.CheckConstraint("finished_at is null or started_at is null or finished_at >= started_at", name="ck_runs_finished_after_started"),
        schema=SCHEMA,
    )
    op.create_index("ix_runs_dataset_id", "runs", ["dataset_id"], schema=SCHEMA)
    op.create_index("ix_runs_dataset_created", "runs", ["dataset_id", "created_at"], schema=SCHEMA)
    op.create_index("ix_runs_status_created_at", "runs", ["status", "created_at"], schema=SCHEMA)
    op.create_index("ix_runs_created_at", "runs", ["created_at", "id"], schema=SCHEMA)
    op.create_index("ix_runs_heartbeat_running", "runs", ["heartbeat_at"], schema=SCHEMA, postgresql_where=sa.text("status = 'RUNNING'"))

    op.create_table(
        "run_sessions",
        uuid_column(), uuid_column("run_id"), uuid_column("dataset_session_id", nullable=True),
        sa.Column("source_session_id", sa.Text()),
        sa.Column("repeat_index", sa.Integer(), server_default="1", nullable=False),
        uuid_column("evaluation_session_key"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("turn_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fallback_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("infrastructure_error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_latency_ms", sa.Float()),
        sa.Column("first_divergent_turn", sa.Integer()),
        sa.Column("first_divergent_stage", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default=JSON_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_run_sessions"),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation.runs.id"], ondelete="CASCADE", name="fk_run_sessions_run"),
        sa.ForeignKeyConstraint(["dataset_session_id"], ["evaluation.dataset_sessions.id"], ondelete="SET NULL", name="fk_run_sessions_dataset_session"),
        sa.UniqueConstraint("evaluation_session_key", name="uq_run_sessions_eval_key"),
        sa.UniqueConstraint("run_id", "dataset_session_id", "repeat_index", name="uq_run_sessions_repeat"),
        sa.CheckConstraint("repeat_index >= 1", name="ck_run_sessions_repeat"),
        sa.CheckConstraint("turn_count >= 0", name="ck_run_sessions_turn_count"),
        sa.CheckConstraint("fallback_count >= 0", name="ck_run_sessions_fallback_count"),
        sa.CheckConstraint("error_count >= 0", name="ck_run_sessions_error_count"),
        sa.CheckConstraint("infrastructure_error_count >= 0", name="ck_run_sessions_infrastructure_error_count"),
        sa.CheckConstraint("total_latency_ms is null or total_latency_ms >= 0", name="ck_run_sessions_latency"),
        sa.CheckConstraint("first_divergent_turn is null or first_divergent_turn >= 1", name="ck_run_sessions_divergent_turn"),
        sa.CheckConstraint("finished_at is null or started_at is null or finished_at >= started_at", name="ck_run_sessions_finished_after_started"),
        sa.CheckConstraint("status in ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="ck_run_sessions_status"),
        schema=SCHEMA,
    )
    for name, columns in (
        ("ix_run_sessions_run_id", ["run_id"]),
        ("ix_run_sessions_dataset_session_id", ["dataset_session_id"]),
        ("ix_run_sessions_source_id", ["source_session_id"]),
        ("ix_run_sessions_status", ["status"]),
        ("ix_run_sessions_run_repeat", ["run_id", "repeat_index"]),
        ("ix_run_sessions_run_status_repeat", ["run_id", "status", "repeat_index"]),
    ):
        op.create_index(name, "run_sessions", columns, schema=SCHEMA)

    op.create_table(
        "run_turns",
        uuid_column(), uuid_column("run_session_id"), uuid_column("dataset_turn_id", nullable=True),
        sa.Column("turn_index", sa.Integer(), nullable=False), uuid_column("request_id"),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("normalized_query", sa.Text()),
        sa.Column("history_before_hash", sa.Text()), sa.Column("history_after_hash", sa.Text()),
        sa.Column("actual_intent", sa.Text()), sa.Column("intent_score", sa.Float()),
        sa.Column("rewritten_query", sa.Text()), sa.Column("selected_context_hash", sa.Text()),
        sa.Column("actual_answer", sa.Text()),
        sa.Column("fallback_used", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fallback_reason", sa.Text()), sa.Column("status", sa.Text(), nullable=False),
        sa.Column("infrastructure_error", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("error_code", sa.Text()), sa.Column("error_data", postgresql.JSONB()),
        sa.Column("attempt_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("total_latency_ms", sa.Float()),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default=JSON_DEFAULT, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_run_turns"),
        sa.ForeignKeyConstraint(["run_session_id"], ["evaluation.run_sessions.id"], ondelete="CASCADE", name="fk_run_turns_run_session"),
        sa.ForeignKeyConstraint(["dataset_turn_id"], ["evaluation.dataset_turns.id"], ondelete="SET NULL", name="fk_run_turns_dataset_turn"),
        sa.UniqueConstraint("run_session_id", "turn_index", name="uq_run_turns_index"),
        sa.UniqueConstraint("request_id", name="uq_run_turns_request_id"),
        sa.CheckConstraint("turn_index >= 1", name="ck_run_turns_index"),
        sa.CheckConstraint("status in ('PENDING','RUNNING','COMPLETED','ERROR','CANCELLED')", name="ck_run_turns_status"),
        sa.CheckConstraint("attempt_count >= 1", name="ck_run_turns_attempt_count"),
        sa.CheckConstraint("total_latency_ms is null or total_latency_ms >= 0", name="ck_run_turns_latency"),
        sa.CheckConstraint("history_before_hash is null or length(history_before_hash) = 64", name="ck_run_turns_history_before_hash"),
        sa.CheckConstraint("history_after_hash is null or length(history_after_hash) = 64", name="ck_run_turns_history_after_hash"),
        sa.CheckConstraint("selected_context_hash is null or length(selected_context_hash) = 64", name="ck_run_turns_context_hash"),
        sa.CheckConstraint("finished_at is null or started_at is null or finished_at >= started_at", name="ck_run_turns_finished_after_started"),
        schema=SCHEMA,
    )
    for name, columns in (
        ("ix_run_turns_run_session_id", ["run_session_id"]),
        ("ix_run_turns_dataset_turn_id", ["dataset_turn_id"]),
        ("ix_run_turns_status", ["status"]),
        ("ix_run_turns_session_turn", ["run_session_id", "turn_index"]),
        ("ix_run_turns_status_started", ["status", "started_at"]),
    ):
        op.create_index(name, "run_turns", columns, schema=SCHEMA)

    op.create_table(
        "stage_results",
        uuid_column(), uuid_column("run_turn_id"),
        sa.Column("stage_name", sa.Text(), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text()), sa.Column("output_hash", sa.Text()),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("input_data", postgresql.JSONB()), sa.Column("output_data", postgresql.JSONB()),
        sa.Column("metrics", postgresql.JSONB()), sa.Column("error_code", sa.Text()),
        sa.Column("error_data", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_stage_results"),
        sa.ForeignKeyConstraint(["run_turn_id"], ["evaluation.run_turns.id"], ondelete="CASCADE", name="fk_stage_results_run_turn"),
        sa.UniqueConstraint("run_turn_id", "stage_name", name="uq_stage_results_stage"),
        sa.UniqueConstraint("run_turn_id", "stage_order", name="uq_stage_results_order"),
        sa.CheckConstraint("stage_name in ('NORMALIZATION','INTENT','REWRITE','RETRIEVAL','RERANK','CONTEXT_SELECTION','PROMPT_BUILD','GENERATION')", name="ck_stage_results_name"),
        sa.CheckConstraint("stage_order >= 0", name="ck_stage_results_order"),
        sa.CheckConstraint("duration_ms is null or duration_ms >= 0", name="ck_stage_results_duration"),
        sa.CheckConstraint("input_hash is null or length(input_hash) = 64", name="ck_stage_results_input_hash"),
        sa.CheckConstraint("output_hash is null or length(output_hash) = 64", name="ck_stage_results_output_hash"),
        sa.CheckConstraint("status in ('PENDING','RUNNING','COMPLETED','SKIPPED','ERROR')", name="ck_stage_results_status"),
        schema=SCHEMA,
    )
    op.create_index("ix_stage_results_run_turn_id", "stage_results", ["run_turn_id"], schema=SCHEMA)
    op.create_index("ix_stage_results_turn_order", "stage_results", ["run_turn_id", "stage_order"], schema=SCHEMA)
    op.create_index("ix_stage_results_status", "stage_results", ["status"], schema=SCHEMA)


def downgrade():
    for table in ("stage_results", "run_turns", "run_sessions", "runs", "dataset_turns", "dataset_sessions", "datasets"):
        op.drop_table(table, schema=SCHEMA)
