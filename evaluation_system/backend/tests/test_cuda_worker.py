from __future__ import annotations

import os
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch


class WorkerCommandTests(unittest.TestCase):
    def tearDown(self):
        from evaluation_system.backend.app.config import get_settings

        get_settings.cache_clear()

    def test_worker_command_defaults_to_solo_concurrency_one(self):
        from evaluation_system.backend.app.config import get_settings
        from evaluation_system.backend.scripts.start_worker import build_worker_argv

        with patch.dict(os.environ, {"EVAL_ENABLED": "true"}, clear=True):
            get_settings.cache_clear()
            settings = get_settings()
            argv = build_worker_argv(settings)

        self.assertIn("--pool=solo", argv)
        self.assertIn("--concurrency=1", argv)
        self.assertIn("--queues=ragbot-evaluation", argv)

    def test_worker_command_honors_env_overrides(self):
        from evaluation_system.backend.app.config import get_settings
        from evaluation_system.backend.scripts.start_worker import build_worker_argv

        values = {
            "EVAL_ENABLED": "true",
            "EVAL_CELERY_POOL": "threads",
            "EVAL_CELERY_CONCURRENCY": "3",
            "EVAL_CELERY_QUEUE": "evaluation-test-queue",
        }
        with patch.dict(os.environ, values, clear=True):
            get_settings.cache_clear()
            argv = build_worker_argv(get_settings())

        self.assertIn("--pool=threads", argv)
        self.assertIn("--concurrency=3", argv)
        self.assertIn("--queues=evaluation-test-queue", argv)


class WorkerRuntimeLifecycleTests(unittest.TestCase):
    def test_worker_runtime_accessor_is_process_singleton(self):
        from evaluation_system.backend.app.worker.process_runtime import (
            close_worker_runtime,
            get_worker_runtime,
        )

        close_worker_runtime()
        try:
            self.assertIs(get_worker_runtime(), get_worker_runtime())
        finally:
            close_worker_runtime()

    def test_canonical_runtime_is_initialized_once_and_reused(self):
        from evaluation_system.backend.app.worker.process_runtime import (
            WorkerProcessRuntime,
        )

        events: list[str] = []
        service = object()

        @asynccontextmanager
        async def fake_runtime():
            events.append("enter")
            try:
                yield service
            finally:
                events.append("exit")

        runtime = WorkerProcessRuntime(runtime_factory=fake_runtime)

        async def identity(value):
            return value

        try:
            first = runtime.run_with_service(identity)
            second = runtime.run_with_service(identity)
            self.assertIs(first, service)
            self.assertIs(second, service)
            self.assertEqual(events, ["enter"])
            self.assertTrue(runtime.initialized)
        finally:
            runtime.close()

        self.assertEqual(events, ["enter", "exit"])

    def test_cuda_fork_error_gets_safe_initialization_code(self):
        from evaluation_system.backend.app.worker.process_runtime import (
            worker_initialization_error_code,
        )

        exc = RuntimeError(
            "Cannot re-initialize CUDA in forked subprocess. "
            "To use CUDA with multiprocessing, use the 'spawn' start method."
        )
        self.assertEqual(
            worker_initialization_error_code(exc),
            "CUDA_WORKER_INIT_FAILED",
        )


class WorkerFailureStateTests(unittest.TestCase):
    def test_task_boundary_attempts_durable_failure_update(self):
        from evaluation_system.backend.app.worker.process_runtime import (
            WorkerRuntimeInitializationError,
        )
        from evaluation_system.backend.app.worker.tasks import (
            EvaluationWorkerTaskFailed,
            execute_run_task,
        )

        class FailingRuntime:
            maintenance_called = False

            def run_with_service(self, _operation):
                raise WorkerRuntimeInitializationError(
                    "CUDA_WORKER_INIT_FAILED"
                )

            def run_maintenance(self, awaitable):
                self.maintenance_called = True
                awaitable.close()

        runtime = FailingRuntime()
        with patch(
            "evaluation_system.backend.app.worker.tasks.get_worker_runtime",
            return_value=runtime,
        ):
            with self.assertRaises(EvaluationWorkerTaskFailed) as caught:
                execute_run_task.run("7eab21ff-ddb9-4186-a578-937c3b49343d")

        self.assertTrue(runtime.maintenance_called)
        self.assertEqual(caught.exception.error_code, "CUDA_WORKER_INIT_FAILED")

    def test_failed_task_marks_nonterminal_run_failed(self):
        from evaluation_system.backend.app.worker.tasks import _mark_run_failed

        run = SimpleNamespace(
            status="RUNNING",
            failure_code=None,
            finished_at=None,
            metadata_json={"preserved": True},
        )
        finished = datetime.now(timezone.utc)
        code = _mark_run_failed(
            run,
            "CUDA_WORKER_INIT_FAILED",
            finished_at=finished,
        )

        self.assertEqual(code, "CUDA_WORKER_INIT_FAILED")
        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.failure_code, "CUDA_WORKER_INIT_FAILED")
        self.assertIs(run.finished_at, finished)
        self.assertEqual(
            run.metadata_json,
            {"preserved": True, "failure_code": "CUDA_WORKER_INIT_FAILED"},
        )


if __name__ == "__main__":
    unittest.main()
