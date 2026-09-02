"""Read-only migration status and advisory-locked upgrade-to-head service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXPECTED_TABLES = frozenset({
    "datasets", "dataset_sessions", "dataset_turns", "runs",
    "run_sessions", "run_turns", "stage_results", "alembic_version",
})
EXPECTED_INDEXES = frozenset({
    "ix_datasets_created_at", "ix_datasets_type_created_at",
    "ix_dataset_sessions_dataset_id", "ix_dataset_sessions_source_id",
    "ix_dataset_sessions_dataset_source", "ix_dataset_turns_session_id",
    "ix_dataset_turns_session_turn", "ix_dataset_turns_time_order",
    "ix_runs_dataset_id", "ix_runs_dataset_created",
    "ix_runs_status_created_at", "ix_runs_created_at",
    "ix_runs_heartbeat_running", "ix_run_sessions_run_id",
    "ix_run_sessions_dataset_session_id", "ix_run_sessions_source_id",
    "ix_run_sessions_status", "ix_run_sessions_run_repeat",
    "ix_run_sessions_run_status_repeat",
    "ix_run_turns_run_session_id", "ix_run_turns_dataset_turn_id",
    "ix_run_turns_status", "ix_run_turns_session_turn",
    "ix_run_turns_status_started",
    "ix_stage_results_run_turn_id", "ix_stage_results_turn_order",
    "ix_stage_results_status",
})
CONFIRMATION = "CREATE_EVALUATION_TABLES"
LOCK_NAME = "ragbot:evaluation:migrations:v1"


def _sqlstate(exc: BaseException) -> str | None:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        original = getattr(current, "orig", None)
        for candidate in (current, original):
            code = getattr(candidate, "sqlstate", None) or getattr(
                candidate, "pgcode", None
            )
            if code:
                return str(code)
        current = current.__cause__ or current.__context__
    return None


@dataclass(frozen=True)
class DatabaseStatus:
    status: str
    current_revision: str | None
    required_revision: str | None
    missing_objects: tuple[str, ...]
    allow_initialize: bool
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "current_revision": self.current_revision,
            "required_revision": self.required_revision,
            "missing_objects": list(self.missing_objects),
            "allow_initialize": self.allow_initialize,
            "error_code": self.error_code,
        }


def classify_database_status(
    *,
    schema_exists: bool,
    tables: set[str],
    indexes: set[str],
    current_revision: str | None,
    required_revision: str,
    allow_initialize: bool,
) -> DatabaseStatus:
    missing = tuple(
        [f"table:{name}" for name in sorted(EXPECTED_TABLES - tables)]
        + [f"index:{name}" for name in sorted(EXPECTED_INDEXES - indexes)]
    )
    if not schema_exists or current_revision is None:
        state = "NOT_INITIALIZED"
    elif current_revision != required_revision or missing:
        state = "UPGRADE_REQUIRED"
    else:
        state = "READY"
    return DatabaseStatus(
        state,
        current_revision,
        required_revision,
        missing,
        allow_initialize,
    )


class MigrationService:
    def __init__(self, settings, *, engine_factory=None, alembic_command=None):
        self.settings = settings
        self._engine_factory = engine_factory
        self._alembic_command = alembic_command

    @property
    def ini_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "alembic.ini"

    def _engine(self):
        if self._engine_factory is not None:
            return self._engine_factory()
        from sqlalchemy import create_engine
        return create_engine(
            self.settings.sqlalchemy_url(async_driver=False),
            pool_pre_ping=True,
            hide_parameters=True,
        )

    def _alembic_config(self):
        from alembic.config import Config
        config = Config(str(self.ini_path))
        config.set_main_option("script_location", str(self.ini_path.parent / "alembic"))
        return config

    def required_revision(self) -> str:
        from alembic.script import ScriptDirectory
        return str(ScriptDirectory.from_config(self._alembic_config()).get_current_head())

    def status(self) -> DatabaseStatus:
        required = None
        try:
            from sqlalchemy import inspect, text
            required = self.required_revision()
            engine = self._engine()
            try:
                with engine.connect() as connection:
                    inspector = inspect(connection)
                    if not inspector.has_schema("evaluation"):
                        return classify_database_status(
                            schema_exists=False,
                            tables=set(),
                            indexes=set(),
                            current_revision=None,
                            required_revision=required,
                            allow_initialize=self.settings.allow_db_init,
                        )
                    tables = set(inspector.get_table_names(schema="evaluation"))
                    indexes = {
                        index["name"]
                        for table in tables & (EXPECTED_TABLES - {"alembic_version"})
                        for index in inspector.get_indexes(table, schema="evaluation")
                    }
                    current = None
                    if "alembic_version" in tables:
                        current = connection.execute(text("select version_num from evaluation.alembic_version")).scalar_one_or_none()
                    return classify_database_status(
                        schema_exists=True,
                        tables=tables,
                        indexes=indexes,
                        current_revision=current,
                        required_revision=required,
                        allow_initialize=self.settings.allow_db_init,
                    )
            finally:
                engine.dispose()
        except Exception:
            return DatabaseStatus("ERROR", None, required, (), self.settings.allow_db_init, "DATABASE_STATUS_ERROR")

    def initialize(self, confirmation: str) -> DatabaseStatus:
        if not self.settings.allow_db_init:
            raise PermissionError("EVALUATION_DB_INIT_DISABLED")
        if confirmation != CONFIRMATION:
            raise ValueError("INVALID_CONFIRMATION")
        from sqlalchemy import text
        from alembic import command

        engine = self._engine()
        try:
            with engine.connect() as connection:
                acquired = bool(connection.execute(
                    text("select pg_try_advisory_lock(hashtext(:name))"), {"name": LOCK_NAME}
                ).scalar_one())
                if not acquired:
                    raise RuntimeError("MIGRATION_ALREADY_RUNNING")
                try:
                    connection.execute(text("create schema if not exists evaluation"))
                    connection.commit()
                    config = self._alembic_config()
                    config.attributes["connection"] = connection
                    (self._alembic_command or command.upgrade)(config, "head")
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.execute(text("select pg_advisory_unlock(hashtext(:name))"), {"name": LOCK_NAME})
                    connection.commit()
        except Exception as exc:
            if _sqlstate(exc) == "42501":
                raise PermissionError(
                    "EVALUATION_SCHEMA_PERMISSION_DENIED"
                ) from None
            raise
        finally:
            engine.dispose()
        return self.status()
