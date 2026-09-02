from __future__ import annotations

import importlib.util
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


ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "evaluation_system/backend/alembic/versions/20260831_0001_evaluation_v1.py"


class MigrationStaticSafetyTests(unittest.TestCase):
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
