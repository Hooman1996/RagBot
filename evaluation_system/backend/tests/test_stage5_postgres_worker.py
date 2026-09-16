from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql

from evaluation_system.backend.app.clients.ragbot import RagBotClientError


class FakeSession:
    def __init__(self, candidate):
        self.candidate = candidate
        self.committed = False
        self.state_at_commit = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def scalar(self, _statement):
        return self.candidate

    async def commit(self):
        self.committed = True
        if self.candidate is not None:
            self.state_at_commit = (
                self.candidate.status,
                self.candidate.worker_task_id,
                self.candidate.heartbeat_at,
            )


class PostgresClaimTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def make_run(*, status="PENDING", started_at=None, cancel_requested_at=None):
        return SimpleNamespace(
            id=uuid.uuid4(),
            status=status,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            started_at=started_at,
            heartbeat_at=None,
            worker_task_id=None,
            cancel_requested_at=cancel_requested_at,
        )

    async def test_fresh_pending_claim_sets_owner_heartbeat_and_start(self):
        from evaluation_system.backend.app.worker.postgres_queue import PostgresRunQueue

        run = self.make_run()
        session = FakeSession(run)
        queue = PostgresRunQueue(session_factory=lambda: session, stale_after_seconds=300)
        claimed = await queue.claim_next("worker-a")

        self.assertEqual(claimed, run.id)
        self.assertEqual(run.status, "RUNNING")
        self.assertEqual(run.worker_task_id, "worker-a")
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.heartbeat_at)
        self.assertEqual(session.state_at_commit[:2], ("RUNNING", "worker-a"))
        self.assertIsNotNone(session.state_at_commit[2])

    async def test_stale_running_claim_replaces_owner_and_preserves_start(self):
        from evaluation_system.backend.app.worker.postgres_queue import PostgresRunQueue

        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        run = self.make_run(status="RUNNING", started_at=started)
        run.worker_task_id = "worker-a"
        session = FakeSession(run)
        queue = PostgresRunQueue(session_factory=lambda: session, stale_after_seconds=300)

        await queue.claim_next("worker-b")

        self.assertEqual(run.worker_task_id, "worker-b")
        self.assertIs(run.started_at, started)
        self.assertIsNotNone(run.heartbeat_at)

    async def test_stale_running_with_cancel_request_is_claimed(self):
        from evaluation_system.backend.app.worker.postgres_queue import PostgresRunQueue

        run = self.make_run(
            status="RUNNING",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            cancel_requested_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        session = FakeSession(run)
        queue = PostgresRunQueue(session_factory=lambda: session, stale_after_seconds=300)

        self.assertEqual(await queue.claim_next("worker-b"), run.id)
        self.assertEqual(run.worker_task_id, "worker-b")

    async def test_no_candidate_does_not_commit(self):
        from evaluation_system.backend.app.worker.postgres_queue import PostgresRunQueue

        session = FakeSession(None)
        queue = PostgresRunQueue(session_factory=lambda: session, stale_after_seconds=300)
        self.assertIsNone(await queue.claim_next("worker-b"))
        self.assertFalse(session.committed)

    def test_claim_sql_is_locking_skip_locked_deterministic_and_stale_aware(self):
        from evaluation_system.backend.app.worker.postgres_queue import build_claim_statement

        cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
        sql = str(
            build_claim_statement(cutoff).compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).upper()
        self.assertIn("FOR UPDATE SKIP LOCKED", sql)
        self.assertIn(
            "ORDER BY EVALUATION.RUNS.CREATED_AT ASC, EVALUATION.RUNS.ID ASC",
            sql,
        )
        self.assertIn("STATUS = 'PENDING'", sql)
        self.assertIn("STATUS = 'RUNNING'", sql)
        self.assertIn(
            "COALESCE(EVALUATION.RUNS.HEARTBEAT_AT, EVALUATION.RUNS.STARTED_AT, EVALUATION.RUNS.CREATED_AT)",
            sql,
        )
        predicate = sql.split("WHERE ", 1)[1].split(" ORDER BY ", 1)[0]
        self.assertNotIn("CANCEL_REQUESTED_AT", predicate)


class WorkerLossResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_turn_is_not_reset_or_reexecuted(self):
        from evaluation_system.backend.app.worker.runner import EvaluationRunExecutor

        completed = SimpleNamespace(
            status="COMPLETED",
            fallback_used=False,
            infrastructure_error=False,
            total_latency_ms=10,
            metadata_json={"agent_state_after": {"preserved": True}},
        )
        session = FakeSession(completed)
        runner = EvaluationRunExecutor(
            session_factory=lambda: session,
            ragbot_client=AsyncMock(),
        )

        turn, should_execute = await runner._claim_turn(
            uuid.uuid4(),
            SimpleNamespace(id=uuid.uuid4(), turn_index=1, query="question"),
        )

        self.assertIs(turn, completed)
        self.assertFalse(should_execute)
        self.assertFalse(session.committed)
        self.assertEqual(
            completed.metadata_json,
            {"agent_state_after": {"preserved": True}},
        )


class RunnerPreparationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_http_runs_after_claim_commit_and_failure_is_durable(self):
        from evaluation_system.backend.app.worker.runner import (
            EvaluationRunExecutor,
            EvaluationRunFailed,
        )

        run = SimpleNamespace(
            id=uuid.uuid4(),
            status="RUNNING",
            worker_task_id="worker-a",
            started_at=datetime.now(timezone.utc),
            heartbeat_at=None,
            config_snapshot={
                "retrieval": {"knowledge_sources": ["A"]},
                "runtime_snapshot_pending": True,
            },
            git_commit_sha=None,
            finished_at=None,
            failure_code=None,
            metadata_json={},
        )

        class Session(FakeSession):
            in_context = False

            async def __aenter__(self):
                self.in_context = True
                return self

            async def __aexit__(self, *_args):
                self.in_context = False
                return False

            async def get(self, _model, _identity, **_kwargs):
                return self.candidate

        session = Session(run)
        client = AsyncMock()

        async def fail_snapshot(_documents):
            self.assertFalse(session.in_context)
            self.assertTrue(session.committed)
            raise RagBotClientError("RAGBOT_UNAVAILABLE", "connection")

        client.runtime_snapshot.side_effect = fail_snapshot
        runner = EvaluationRunExecutor(
            session_factory=lambda: session,
            ragbot_client=client,
        )

        with self.assertRaises(EvaluationRunFailed) as caught:
            await runner.execute(run.id, worker_task_id="worker-a")

        self.assertEqual(caught.exception.error_code, "RAGBOT_UNAVAILABLE")
        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.failure_code, "RAGBOT_UNAVAILABLE")
        self.assertIsNotNone(run.finished_at)


class WorkerLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_executor_for_two_runs_then_stops(self):
        from evaluation_system.backend.app.worker.postgres_worker import PostgresEvaluationWorker

        ids = [uuid.uuid4(), uuid.uuid4()]
        stop = asyncio.Event()
        queue = SimpleNamespace(claim_next=AsyncMock(side_effect=ids))
        executor = SimpleNamespace(execute=AsyncMock())

        async def execute(run_id, *, worker_task_id):
            if run_id == ids[-1]:
                stop.set()

        executor.execute.side_effect = execute
        worker = PostgresEvaluationWorker(
            queue=queue,
            executor=executor,
            worker_id="worker-a",
            poll_interval_seconds=1,
        )
        await worker.run(stop)

        self.assertEqual(executor.execute.await_count, 2)
        self.assertEqual(
            [call.args[0] for call in executor.execute.await_args_list], ids
        )
        self.assertTrue(
            all(
                call.kwargs["worker_task_id"] == "worker-a"
                for call in executor.execute.await_args_list
            )
        )

    async def test_graceful_stop_finishes_current_run_and_claims_no_more(self):
        from evaluation_system.backend.app.worker.postgres_worker import PostgresEvaluationWorker

        stop = asyncio.Event()
        queue = SimpleNamespace(claim_next=AsyncMock(return_value=uuid.uuid4()))
        completed = False

        async def execute(*_args, **_kwargs):
            nonlocal completed
            stop.set()
            await asyncio.sleep(0)
            completed = True

        worker = PostgresEvaluationWorker(
            queue=queue,
            executor=SimpleNamespace(execute=execute),
            worker_id="worker-a",
            poll_interval_seconds=1,
        )
        await worker.run(stop)

        self.assertTrue(completed)
        queue.claim_next.assert_awaited_once()

    def test_worker_identity_is_content_free_and_fits_owner_column(self):
        from evaluation_system.backend.app.worker.postgres_worker import create_worker_id

        worker_id = create_worker_id()
        self.assertTrue(worker_id.startswith("eval-worker:"))
        self.assertIn(f":{os.getpid()}:", worker_id)
        self.assertLess(len(worker_id), 256)


class WorkerResourceLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_closes_http_and_engine(self):
        from evaluation_system.backend.app.worker import postgres_worker

        client = SimpleNamespace(aclose=AsyncMock())
        fake_engine = SimpleNamespace(dispose=AsyncMock())
        settings = SimpleNamespace(
            enabled=True,
            ragbot_base_url="http://ragbot",
            ragbot_http_timeout_seconds=70,
            worker_stale_after_seconds=300,
            session_concurrency=1,
            worker_poll_interval_seconds=1,
        )

        with patch.object(postgres_worker, "RagBotEvaluationClient", return_value=client), \
             patch.object(postgres_worker, "engine", fake_engine), \
             patch.object(postgres_worker, "_install_signal_handlers"), \
             patch.object(postgres_worker.PostgresEvaluationWorker, "run", AsyncMock()):
            await postgres_worker.run_worker(
                settings=settings, stop_event=asyncio.Event()
            )

        client.aclose.assert_awaited_once()
        fake_engine.dispose.assert_awaited_once()


class WorkerSettingsTests(unittest.TestCase):
    def tearDown(self):
        from evaluation_system.backend.app.config import get_settings

        get_settings.cache_clear()

    def test_defaults_and_stale_timeout_validation(self):
        from evaluation_system.backend.app.config import get_settings

        with patch.dict(os.environ, {}, clear=True):
            get_settings.cache_clear()
            settings = get_settings()
            self.assertEqual(settings.worker_poll_interval_seconds, 1.0)
            self.assertEqual(settings.worker_stale_after_seconds, 300)

        with patch.dict(
            os.environ,
            {
                "EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS": "70",
                "EVAL_WORKER_STALE_AFTER_SECONDS": "70",
            },
            clear=True,
        ):
            get_settings.cache_clear()
            with self.assertRaisesRegex(ValueError, "must be greater"):
                get_settings()


if __name__ == "__main__":
    unittest.main()
