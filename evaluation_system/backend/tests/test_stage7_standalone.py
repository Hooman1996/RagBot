from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_SOURCE = Path(__file__).resolve().parents[1]


class StandaloneBackendTests(unittest.TestCase):
    def test_copied_backend_imports_and_exposes_routes_in_isolation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            isolated_backend = Path(temp_dir) / "backend"
            shutil.copytree(
                BACKEND_SOURCE,
                isolated_backend,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            script = r"""
import importlib
import importlib.abc
import pathlib
import sys

source_parent = pathlib.Path(sys.argv[1]).resolve()
assert source_parent not in {
    pathlib.Path(item or ".").resolve() for item in sys.path
}

blocked = {
    "ragbot" + "_auth",
    "redis",
    "celery",
    "qdrant" + "_client",
    "openai",
    "torch",
    "langgraph",
    "agent" + "_service",
    "answering" + "_service",
    "conversation" + "_history",
    "pipeline" + "_observer",
    "mobile" + "_api",
    "kb" + "_manager",
    "new" + "_architecture",
    "main",
}

class RejectEmbeddedImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        for name in blocked:
            if fullname == name or fullname.startswith(name + "."):
                raise AssertionError(f"forbidden import attempted: {fullname}")
        if fullname == "app." + ("ragbot" + "_auth"):
            raise AssertionError(f"forbidden import attempted: {fullname}")
        return None

sys.meta_path.insert(0, RejectEmbeddedImports())
api = importlib.import_module("app.main")
worker = importlib.import_module("app.worker.postgres_worker")
for module in (api, worker):
    assert pathlib.Path(module.__file__).resolve().is_relative_to(pathlib.Path.cwd())

from app.services.migrations import MigrationService

migrations = MigrationService(api.settings)
assert migrations.ini_path == pathlib.Path.cwd() / "alembic.ini"
assert migrations.required_revision() == "20260831_0001"

paths = {getattr(route, "path", "") for route in api.app.routes}
expected = {
    "/api/v1/evaluation/openapi.json",
    "/api/v1/evaluation/system/database-status",
    "/api/v1/evaluation/system/database-initialize",
    "/api/v1/evaluation/system/capabilities",
    "/api/v1/evaluation/datasets/import",
    "/api/v1/evaluation/datasets",
    "/api/v1/evaluation/datasets/{dataset_id}",
    "/api/v1/evaluation/datasets/{dataset_id}/sessions",
    "/api/v1/evaluation/datasets/sessions/{dataset_session_id}/turns",
    "/api/v1/evaluation/datasources",
    "/api/v1/evaluation/runs",
    "/api/v1/evaluation/runs/{run_id}",
    "/api/v1/evaluation/runs/{run_id}/cancel",
    "/api/v1/evaluation/runs/{run_id}/sessions",
    "/api/v1/evaluation/run-sessions/{run_session_id}",
    "/api/v1/evaluation/run-turns/{run_turn_id}/trace",
    "/api/v1/evaluation/stability/manual",
    "/api/v1/evaluation/runs/{run_id}/events",
}
assert expected <= paths, expected - paths

old_dependency_names = {
    "require_ragbot" + "_user",
    "Authenticated" + "UserDep",
}
for route in api.app.routes:
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        continue
    pending = list(dependant.dependencies)
    while pending:
        dependency = pending.pop()
        call = getattr(dependency, "call", None)
        assert getattr(call, "__name__", None) not in old_dependency_names
        pending.extend(dependency.dependencies)
"""
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONPATH": str(isolated_backend),
                    "EVAL_ENABLED": "true",
                    "POSTGRES_HOST": "127.0.0.1",
                    "POSTGRES_DB": "isolated",
                    "POSTGRES_USER": "isolated",
                    "POSTGRES_PASSWORD": "placeholder",
                    "EVAL_RAGBOT_BASE_URL": "http://127.0.0.1:8080",
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", script, str(BACKEND_SOURCE.parent)],
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
