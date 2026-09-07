from __future__ import annotations

import ast
import importlib.util
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from evaluation_system.backend.app.services.migrations import (
    CONFIRMATION,
    EXPECTED_INDEXES,
    EXPECTED_TABLES,
    MigrationService,
    classify_database_status,
)
from pipeline_observer import PipelineStage, STAGE_ORDER


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "evaluation_system/backend/alembic/versions/20260831_0001_evaluation_v1.py"
MODELS = ROOT / "evaluation_system/backend/app/db/models.py"
ALEMBIC_ENV = ROOT / "evaluation_system/backend/alembic/env.py"
MIGRATION_SERVICE = ROOT / "evaluation_system/backend/app/services/migrations.py"


def check_constraint_values(path: Path, constraint_name: str) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        is_check_constraint = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "CheckConstraint"
        ) or (
            isinstance(node.func, ast.Name)
            and node.func.id == "CheckConstraint"
        )
        if not is_check_constraint:
            continue
        name = next(
            (
                keyword.value.value
                for keyword in node.keywords
                if keyword.arg == "name"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ),
            None,
        )
        if name == constraint_name:
            expression = ast.literal_eval(node.args[0])
            return tuple(re.findall(r"'([^']+)'", expression))
    raise AssertionError(f"constraint {constraint_name!r} not found in {path}")


def migration_object_names(method_name: str) -> set[str]:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == method_name
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def migration_index_names() -> set[str]:
    source = MIGRATION.read_text(encoding="utf-8")
    return set(re.findall(r'"(ix_[a-z0-9_]+)"', source))


class MigrationStaticSafetyTests(unittest.TestCase):
    def test_v1_stage_constraint_matches_every_current_pipeline_stage(self):
        allowed = check_constraint_values(MIGRATION, "ck_stage_results_name")
        self.assertIn(PipelineStage.HISTORY.value, allowed)
        self.assertEqual(set(allowed), {stage.value for stage in PipelineStage})

    def test_model_stage_constraint_matches_v1_and_pipeline_enum(self):
        migration_allowed = check_constraint_values(
            MIGRATION, "ck_stage_results_name"
        )
        model_allowed = check_constraint_values(MODELS, "ck_stage_results_name")
        self.assertEqual(model_allowed, migration_allowed)
        self.assertEqual(set(model_allowed), {stage.value for stage in PipelineStage})

    def test_current_pipeline_stage_order(self):
        self.assertEqual(
            STAGE_ORDER,
            {
                PipelineStage.NORMALIZATION: 10,
                PipelineStage.HISTORY: 20,
                PipelineStage.REWRITE: 30,
                PipelineStage.INTENT: 40,
                PipelineStage.RETRIEVAL: 50,
                PipelineStage.RERANK: 60,
                PipelineStage.CONTEXT_SELECTION: 70,
                PipelineStage.PROMPT_BUILD: 80,
                PipelineStage.GENERATION: 90,
            },
        )

    def test_initializer_expects_exact_v1_evaluation_objects(self):
        self.assertEqual(
            EXPECTED_TABLES,
            migration_object_names("create_table") | {"alembic_version"},
        )
        self.assertEqual(EXPECTED_INDEXES, migration_index_names())

    def test_alembic_and_initializer_are_restricted_to_evaluation_schema(self):
        env_source = ALEMBIC_ENV.read_text(encoding="utf-8")
        service_source = MIGRATION_SERVICE.read_text(encoding="utf-8")
        self.assertIn("return name == EVALUATION_SCHEMA", env_source)
        self.assertIn("include_schemas=True", env_source)
        self.assertIn("include_name=include_name", env_source)
        self.assertIn("include_object=include_object", env_source)
        self.assertIn("version_table_schema=EVALUATION_SCHEMA", env_source)
        self.assertIn("create schema if not exists evaluation", service_source)
        self.assertNotIn("public.", service_source)

    def test_migration_references_only_evaluation_foreign_keys(self):
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertNotIn("public.", text)
        for forbidden in ("users.id", "chat_sessions.id", "queries.id", "drop_all"):
            self.assertNotIn(forbidden, text)
        for reference in (
            "evaluation.datasets.id", "evaluation.dataset_sessions.id",
            "evaluation.runs.id", "evaluation.run_sessions.id",
            "evaluation.run_turns.id",
        ):
            self.assertIn(reference, text)

    def test_initialization_is_disabled_before_any_database_import(self):
        settings = SimpleNamespace(allow_db_init=False)
        with self.assertRaisesRegex(PermissionError, "EVALUATION_DB_INIT_DISABLED"):
            MigrationService(settings).initialize(CONFIRMATION)

    def test_arbitrary_confirmation_is_rejected(self):
        settings = SimpleNamespace(allow_db_init=True)
        with self.assertRaisesRegex(ValueError, "INVALID_CONFIRMATION"):
            MigrationService(settings).initialize("select * from users")

    def test_migration_status_classification(self):
        common = {
            "required_revision": "head",
            "allow_initialize": False,
        }
        missing = classify_database_status(
            schema_exists=False, tables=set(), indexes=set(),
            current_revision=None, **common,
        )
        self.assertEqual(missing.status, "NOT_INITIALIZED")
        ready = classify_database_status(
            schema_exists=True, tables=set(EXPECTED_TABLES),
            indexes=set(EXPECTED_INDEXES), current_revision="head", **common,
        )
        self.assertEqual(ready.status, "READY")
        behind = classify_database_status(
            schema_exists=True, tables=set(EXPECTED_TABLES),
            indexes=set(EXPECTED_INDEXES), current_revision="old", **common,
        )
        self.assertEqual(behind.status, "UPGRADE_REQUIRED")
        damaged = classify_database_status(
            schema_exists=True, tables=set(EXPECTED_TABLES) - {"run_turns"},
            indexes=set(EXPECTED_INDEXES), current_revision="head", **common,
        )
        self.assertEqual(damaged.status, "UPGRADE_REQUIRED")
        self.assertIn("table:run_turns", damaged.missing_objects)


@unittest.skipUnless(importlib.util.find_spec("sqlalchemy"), "SQLAlchemy is not installed")
class MetadataSafetyTests(unittest.TestCase):
    def test_metadata_contains_only_evaluation_tables_and_foreign_keys(self):
        from evaluation_system.backend.app.db.base import EvaluationBase
        from evaluation_system.backend.app.db import models  # noqa: F401
        self.assertEqual(
            set(EvaluationBase.metadata.tables),
            {
                "evaluation.datasets", "evaluation.dataset_sessions",
                "evaluation.dataset_turns", "evaluation.runs",
                "evaluation.run_sessions", "evaluation.run_turns",
                "evaluation.stage_results",
            },
        )
        for table in EvaluationBase.metadata.tables.values():
            self.assertEqual(table.schema, "evaluation")
            for foreign_key in table.foreign_keys:
                self.assertTrue(foreign_key.target_fullname.startswith("evaluation."))


if __name__ == "__main__":
    unittest.main()
