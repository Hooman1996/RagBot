from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from evaluation_system.backend.app.schemas.api import (
    ManualStabilityRequest,
    RunCreateRequest,
)
from evaluation_system.backend.app.services.provisional_snapshot import (
    build_provisional_snapshot,
)


EXPECTED_PENDING_SNAPSHOT = {
    "schema_version": "evaluation-pending-v1",
    "retrieval": {"knowledge_sources": ["Cards", "FAQ", "Cards"]},
    "runtime_snapshot_pending": True,
}


class ProvisionalSnapshotTests(unittest.TestCase):
    def test_snapshot_is_minimal_and_preserves_document_order(self):
        documents = ["Cards", "FAQ", "Cards"]
        snapshot = build_provisional_snapshot(documents)

        self.assertEqual(snapshot, EXPECTED_PENDING_SNAPSHOT)
        self.assertIsNot(snapshot["retrieval"]["knowledge_sources"], documents)
        self.assertNotIn("git_commit_sha", snapshot)
        for fabricated_section in (
            "intent",
            "normalizer",
            "rewrite",
            "embedding",
            "rerank",
            "generation",
        ):
            self.assertNotIn(fabricated_section, snapshot)


class RunCreationSnapshotTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _db():
        db = AsyncMock()
        db.commit.return_value = None
        return db

    @staticmethod
    def _run():
        return SimpleNamespace(
            id=uuid.uuid4(),
            status="PENDING",
            worker_task_id=None,
        )

    async def test_post_runs_stores_only_pending_snapshot_and_null_sha(self):
        from evaluation_system.backend.app.api import runs

        db = self._db()
        run = self._run()
        create_run = AsyncMock(return_value=run)
        body = RunCreateRequest(
            dataset_id=uuid.uuid4(),
            run_type="DATASET_INSPECTION",
            repeat_count=1,
            documents=["Cards", "FAQ", "Cards"],
        )
        with patch.object(runs, "get_dataset", AsyncMock(return_value=object())), \
             patch.object(runs, "create_run", create_run):
            response = await runs.start_run(body, object(), db)

        self.assertEqual(response.status, "PENDING")
        kwargs = create_run.await_args.kwargs
        self.assertEqual(kwargs["config_snapshot"], EXPECTED_PENDING_SNAPSHOT)
        self.assertIsNone(kwargs["git_commit_sha"])
        self.assertIsNone(run.worker_task_id)
        db.commit.assert_awaited_once()

    async def test_manual_stability_uses_same_pending_snapshot_and_null_sha(self):
        from evaluation_system.backend.app.api import stability

        db = self._db()
        run = self._run()
        create_run = AsyncMock(return_value=run)
        parsed = SimpleNamespace(valid_row_count=1)
        body = ManualStabilityRequest(
            queries=["question"],
            repeat_count=2,
            documents=["Cards", "FAQ", "Cards"],
        )
        with patch.object(stability, "parse_manual_dataset", return_value=parsed), \
             patch.object(
                 stability, "persist_parsed_dataset", AsyncMock(return_value=object())
             ), \
             patch.object(stability, "create_run", create_run):
            response = await stability.manual_stability(body, object(), db)

        self.assertEqual(response.status, "PENDING")
        kwargs = create_run.await_args.kwargs
        self.assertEqual(kwargs["run_type"], "STABILITY_QUERY")
        self.assertEqual(kwargs["config_snapshot"], EXPECTED_PENDING_SNAPSHOT)
        self.assertIsNone(kwargs["git_commit_sha"])
        self.assertIsNone(run.worker_task_id)
        db.commit.assert_awaited_once()


class IsolatedBackendImportTests(unittest.TestCase):
    def test_backend_imports_without_repository_source_tree(self):
        repository_root = Path(__file__).resolve().parents[3]
        backend_source = repository_root / "evaluation_system" / "backend"
        with tempfile.TemporaryDirectory() as temp_dir:
            isolated_backend = Path(temp_dir) / "backend"
            shutil.copytree(backend_source, isolated_backend)
            script = """
import importlib
import pathlib
import sys

repository_root = pathlib.Path(sys.argv[1]).resolve()
assert all(pathlib.Path(item or '.').resolve() != repository_root for item in sys.path)
modules = (
    'app.config',
    'app.clients.ragbot',
    'app.services.divergence',
    'app.worker.postgres_queue',
    'app.worker.postgres_worker',
    'app.worker.runner',
    'app.main',
)
for name in modules:
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path.cwd())
"""
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONPATH": str(isolated_backend),
                    "EVAL_ENABLED": "false",
                    "POSTGRES_HOST": "127.0.0.1",
                    "POSTGRES_DB": "isolated",
                    "POSTGRES_USER": "isolated",
                    "POSTGRES_PASSWORD": "placeholder",
                    "EVAL_REDIS_URL": "redis://127.0.0.1:6379/15",
                    "EVAL_RAGBOT_BASE_URL": "http://127.0.0.1:8080",
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", script, str(repository_root)],
                cwd=isolated_backend,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
