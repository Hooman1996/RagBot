"""Offline background correlation, lifecycle, and logging health contracts."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from mass_answer_jobs import MassAnswerJobManager
from mass_answer_service import MassAnswerRowResult
from pipeline_observer import TerminalPipelineObserver
from utils.performance_config import PipelineDebugSettings
from utils.concurrency import BoundedBlockingRunner
from utils.request_instrumentation import (
    OperationContext, RequestTrace, background_operation_context,
    current_operation, current_trace, reset_current_trace, set_current_trace,
)
from utils.structured_logging import LoggingSettings, log_event, start_logging


class BackgroundLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stream = io.StringIO()
        self.runtime = start_logging(LoggingSettings(environment="test"), self.stream)
        self.logger = logging.getLogger("test.background")

    async def asyncTearDown(self):
        self.runtime.close()

    def events(self):
        self.runtime.close()
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    async def test_http_and_background_thread_contexts_and_restoration(self):
        trace = RequestTrace(request_id="request-A", process_id=os.getpid())
        token = set_current_trace(trace)
        try:
            await asyncio.to_thread(log_event, self.logger, "http_thread")
            with background_operation_context(
                operation_id="job-B", parent_request_id="request-A",
                operation_type="mass_answer",
            ):
                self.assertIsNone(current_trace())
                self.assertEqual(current_operation().operation_id, "job-B")
                log_event(self.logger, "background_main", {"job_access": "private-token"})
                await asyncio.to_thread(log_event, self.logger, "background_thread")
                with self.assertRaisesRegex(ValueError, "test exit"):
                    with background_operation_context(
                        operation_id="nested-C", parent_request_id="request-A",
                        operation_type="nested",
                    ):
                        raise ValueError("test exit")
                self.assertEqual(current_operation().operation_id, "job-B")
            self.assertIsNone(current_operation())
            self.assertIs(current_trace(), trace)
            log_event(self.logger, "http_after")
        finally:
            reset_current_trace(token)
        events = self.events()
        self.assertEqual([e["event"] for e in events],
                         ["http_thread", "background_main", "background_thread", "http_after"])
        self.assertEqual([e["request_id"] for e in events],
                         ["request-A", None, None, "request-A"])
        self.assertEqual([e["operation_id"] for e in events],
                         [None, "job-B", "job-B", None])
        self.assertEqual(events[2]["parent_request_id"], "request-A")
        self.assertNotIn("private-token", self.stream.getvalue())

    async def test_http_trace_suppresses_inherited_operation_fields(self):
        trace = RequestTrace(request_id="request-http", process_id=1)
        token = set_current_trace(trace)
        try:
            with background_operation_context(
                operation_id="job-B", parent_request_id="request-A",
                operation_type="mass_answer",
            ):
                inner_token = set_current_trace(trace)
                try:
                    log_event(self.logger, "nested_http")
                finally:
                    reset_current_trace(inner_token)
        finally:
            reset_current_trace(token)
        event = self.events()[0]
        self.assertEqual(event["request_id"], "request-http")
        self.assertIsNone(event["operation_id"])
        self.assertIsNone(event["parent_request_id"])

    async def test_concurrent_jobs_and_thread_offloads_keep_distinct_parents(self):
        async def job(parent, operation_id):
            token = set_current_trace(RequestTrace(request_id=parent, process_id=1))
            try:
                with background_operation_context(
                    operation_id=operation_id, parent_request_id=parent,
                    operation_type="mass_answer",
                ):
                    await asyncio.sleep(0)
                    await asyncio.to_thread(log_event, self.logger, "job_thread")
            finally:
                reset_current_trace(token)

        await asyncio.gather(job("request-A", "job-A"), job("request-B", "job-B"))
        events = self.events()
        self.assertEqual({(e["operation_id"], e["parent_request_id"]) for e in events},
                         {("job-A", "request-A"), ("job-B", "request-B")})
        self.assertTrue(all(e["request_id"] is None for e in events))

    async def test_bounded_blocking_runner_copies_request_and_operation_context(self):
        runner = BoundedBlockingRunner(2)
        token = set_current_trace(RequestTrace(request_id="request-A", process_id=1))
        try:
            await runner.run(log_event, self.logger, "runner_http")
            with background_operation_context(
                operation_id="job-B", parent_request_id="request-A",
                operation_type="mass_answer",
            ):
                await runner.run(log_event, self.logger, "runner_background")
        finally:
            reset_current_trace(token)
            await runner.aclose()
        events = self.events()
        self.assertEqual([e["request_id"] for e in events], ["request-A", None])
        self.assertEqual([e["operation_id"] for e in events], [None, "job-B"])
        self.assertEqual(events[1]["parent_request_id"], "request-A")

    async def test_operation_values_are_bounded_and_immutable(self):
        context = OperationContext("job-123", "request-A", "mass_answer")
        self.assertEqual(context.operation_id, "job-123")
        for operation_id in ("bad\nvalue", "x" * 129, "09123456789@example.com"):
            with self.assertRaises(ValueError):
                OperationContext(operation_id, "request-A", "mass_answer")
        with self.assertRaises(ValueError):
            OperationContext("job-1", "bad\nparent", "mass_answer")
        with self.assertRaises(ValueError):
            OperationContext("job-1", "request-A", "bad/type")
        with self.assertRaises(AttributeError):
            context.operation_id = "changed"
        manager = MassAnswerJobManager()
        with self.assertRaises(ValueError):
            manager.start("bad\njob", lambda: asyncio.sleep(0))
        self.assertEqual(manager.active_job_ids, set())
        await manager.aclose()

    async def test_operation_ids_receive_defensive_formatter_scrubbing(self):
        with background_operation_context(
            operation_id="09123456789", parent_request_id="1234567891",
            operation_type="mass_answer",
        ):
            log_event(self.logger, "sensitive_correlation")
        event = self.events()[0]
        self.assertIsNone(event["request_id"])
        self.assertNotIn("09123456789", self.stream.getvalue())
        self.assertNotIn("1234567891", self.stream.getvalue())

    async def test_post_response_cleanup_detaches_http_trace(self):
        import main
        observed = []
        token = set_current_trace(RequestTrace(request_id="request-A", process_id=1))
        try:
            with mock.patch.object(main.os, "remove", side_effect=lambda path: observed.append(
                (path, current_trace(), current_operation())
            )):
                main._remove_mass_answer_artifact("/tmp/example", "request-A")
            self.assertEqual(current_trace().request_id, "request-A")
            self.assertIsNone(current_operation())
        finally:
            reset_current_trace(token)
        self.assertEqual(observed[0][0], "/tmp/example")
        self.assertIsNone(observed[0][1])
        self.assertEqual(observed[0][2].parent_request_id, "request-A")
        self.assertEqual(observed[0][2].operation_type, "mass_answer_cleanup")

    async def test_runtime_snapshot_and_metrics_endpoint_are_content_free(self):
        import main

        snapshot = self.runtime.snapshot()
        self.assertEqual(snapshot["queue_capacity"], 4096)
        self.assertGreaterEqual(snapshot["queue_depth"], 0)
        self.assertEqual(snapshot["overflow_count"], 0)
        self.assertEqual(snapshot["stdout_write_errors"], 0)
        self.assertTrue(snapshot["listener_alive"])
        self.assertNotIn("secret", json.dumps(snapshot))
        fake_limiter = SimpleNamespace(snapshot=lambda: SimpleNamespace(
            limiter_id="test", capacity=1, active=0, waiting=0,
            acquired_total=0, timeout_total=0, cancelled_total=0, released_total=0,
        ))
        fake_rag = SimpleNamespace(search_engine=SimpleNamespace())
        state = SimpleNamespace(
            request_limiter=fake_limiter,
            blocking_runner=SimpleNamespace(snapshot=lambda: {}),
            logging_runtime=self.runtime,
            answering_service=SimpleNamespace(agent_service=SimpleNamespace(rag_system=fake_rag)),
        )
        payload = await main.admission_metrics(SimpleNamespace(app=SimpleNamespace(state=state)))
        self.assertEqual(payload["logging"], snapshot)
        self.assertIn("admission", payload)
        self.assertIn("blocking", payload)
        self.runtime.close()
        self.assertFalse(self.runtime.snapshot()["listener_alive"])

    async def test_terminal_debug_cannot_print_content_under_json_runtime(self):
        observer = TerminalPipelineObserver(
            PipelineDebugSettings(enabled=True), raw_query="private banking query",
            session_id="private-session", channel="mobile", use_history=True,
        )
        observer.finish(result={"answer": "private answer"})
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["pipeline_debug_report_suppressed"])
        for raw in ("private banking query", "private-session", "private answer"):
            self.assertNotIn(raw, self.stream.getvalue())


class MassAnswerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import main
        self.main = main
        self.stream = io.StringIO()
        self.runtime = start_logging(LoggingSettings(environment="test"), self.stream)
        self.manager = MassAnswerJobManager()
        self.updates = []

        class FakeDb:
            def update_mass_answer_job(inner, job_id, fields):
                self.updates.append((job_id, fields))

            def create_mass_answer_job(inner, job):
                return True

        class FakeRunner:
            async def run(inner, func, *args, **kwargs):
                return func(*args)

        self.patches = (
            mock.patch.object(main, "db_manager", FakeDb()),
            mock.patch.object(main, "blocking_runner", FakeRunner()),
            mock.patch.object(main, "mass_answer_job_manager", self.manager),
        )
        for patch in self.patches:
            patch.start()

    async def asyncTearDown(self):
        await self.manager.aclose()
        for patch in reversed(self.patches):
            patch.stop()
        self.runtime.close()

    def events(self):
        self.runtime.close()
        return [json.loads(line) for line in self.stream.getvalue().splitlines()
                if json.loads(line)["event"].startswith("mass_answer_job_")]

    async def _run_case(self, processing, *, cancel=False):
        job_id = uuid.uuid4().hex
        parent = f"request-{job_id[:8]}"
        trace_token = set_current_trace(RequestTrace(request_id=parent, process_id=1))
        try:
            with mock.patch.object(self.main, "_process_mass_dataframe", side_effect=processing):
                self.manager.start(job_id, lambda: self.main._run_mass_answer_job(
                    job_id=job_id, df=None, question_col="question", docs_list=[],
                    ext=".csv", output_path="/tmp/not-written",
                ), parent_request_id=parent)
                if cancel:
                    await asyncio.sleep(0)
                    await self.manager.cancel(job_id)
                else:
                    for _ in range(50):
                        if job_id not in self.manager.active_job_ids:
                            break
                        await asyncio.sleep(0.001)
        finally:
            reset_current_trace(trace_token)
        return job_id, parent

    async def test_completed_failed_and_cancelled_terminal_events_and_db_state(self):
        async def success(**kwargs):
            return "/tmp/not-written", [MassAnswerRowResult(
                index=0, status="success", answer="private generated answer", processing_time_ms=3,
            )]

        async def failure(**kwargs):
            raise RuntimeError("private row question")

        async def hanging(**kwargs):
            await asyncio.Event().wait()

        success_id, success_parent = await self._run_case(success)
        failure_id, failure_parent = await self._run_case(failure)
        cancel_id, cancel_parent = await self._run_case(hanging, cancel=True)
        events = self.events()
        by_id = {job_id: [e for e in events if e["operation_id"] == job_id]
                 for job_id in (success_id, failure_id, cancel_id)}
        expected = {
            success_id: "mass_answer_job_completed",
            failure_id: "mass_answer_job_failed",
            cancel_id: "mass_answer_job_cancelled",
        }
        for job_id, terminal in expected.items():
            self.assertEqual([e["event"] for e in by_id[job_id]],
                             ["mass_answer_job_started", terminal])
            self.assertTrue(all(e["request_id"] is None for e in by_id[job_id]))
            self.assertTrue(all(e["parent_request_id"] == {
                success_id: success_parent, failure_id: failure_parent,
                cancel_id: cancel_parent,
            }[job_id] for e in by_id[job_id]))
        self.assertEqual(by_id[failure_id][-1]["data"]["error"]["type"], "RuntimeError")
        self.assertIn("completed", [fields["status"] for job, fields in self.updates if job == success_id])
        self.assertIn("failed", [fields["status"] for job, fields in self.updates if job == failure_id])
        self.assertIn("failed", [fields["status"] for job, fields in self.updates if job == cancel_id])
        self.assertNotIn("private row question", self.stream.getvalue())
        self.assertNotIn("private generated answer", self.stream.getvalue())

    async def test_create_job_keeps_api_contract_and_safe_queued_event(self):
        import pandas as pd
        frame = pd.DataFrame({"question": ["private source question"]})
        token = set_current_trace(RequestTrace(request_id="request-A", process_id=1))
        try:
            with tempfile.TemporaryDirectory() as directory, \
                 mock.patch.object(self.main.tempfile, "mkdtemp", return_value=directory), \
                 mock.patch.object(self.main, "job_access_token", return_value="private-job-access"), \
                 mock.patch.object(self.manager, "start") as start:
                response = await self.main._create_mass_answer_job(
                    df=frame, question_col="question", docs_list=["private-doc"],
                    ext=".csv", filename="alice@example.com.csv", user_id="private-user",
                )
        finally:
            reset_current_trace(token)
        content = json.loads(response.body)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(content["job_access"], "private-job-access")
        self.assertEqual(start.call_args.kwargs["parent_request_id"], "request-A")
        events = self.events()
        self.assertEqual([e["event"] for e in events], ["mass_answer_job_queued"])
        self.assertEqual(events[0]["request_id"], "request-A")
        self.assertIsNone(events[0]["operation_id"])
        self.assertEqual(events[0]["data"]["total_rows"], 1)
        for raw in ("private-job-access", "private source question", "private-doc",
                    "private-user", "alice@example.com"):
            self.assertNotIn(raw, self.stream.getvalue())


if __name__ == "__main__":
    unittest.main()
