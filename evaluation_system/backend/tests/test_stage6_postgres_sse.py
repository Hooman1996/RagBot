from __future__ import annotations

import asyncio
import importlib
import json
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from evaluation_system.backend.app.api import events


def projection(
    *,
    status: str = "RUNNING",
    completed_turns: int = 0,
    sessions=(),
    turns=(),
    stages=(),
) -> events.DurableProjection:
    return events.DurableProjection(
        run={
            "run_id": "run-1",
            "status": status,
            "completed_sessions": int(status == "COMPLETED"),
            "total_sessions": 1,
            "completed_turns": completed_turns,
            "total_turns": 1,
            "fallback_count": 0,
            "error_count": int(status == "FAILED"),
            "infrastructure_error_count": 0,
            "heartbeat_at": None,
        },
        sessions=tuple(sessions),
        turns=tuple(turns),
        stages=tuple(stages),
    )


def session(status: str) -> events.SessionProjection:
    return events.SessionProjection(
        id="session-1",
        status=status,
        repeat_index=1,
        total_latency_ms=12.5,
        started_at=None,
        finished_at=None,
    )


def turn(status: str) -> events.TurnProjection:
    return events.TurnProjection(
        id="turn-1",
        run_session_id="session-1",
        status=status,
        turn_index=1,
        started_at=None,
        finished_at=None,
    )


def stage() -> events.StageProjection:
    return events.StageProjection(
        id="stage-1",
        run_turn_id="turn-1",
        stage_name="INTENT",
        stage_order=2,
        status="COMPLETED",
        duration_ms=4.5,
        error_code=None,
        created_at=None,
    )


def decode_chunk(chunk: bytes) -> tuple[str | None, dict]:
    text = chunk.decode()
    if text.startswith(":"):
        return None, {"comment": text.strip()}
    name = next(line[7:] for line in text.splitlines() if line.startswith("event: "))
    data = next(line[6:] for line in text.splitlines() if line.startswith("data: "))
    return name, json.loads(data)


class FakeRequest:
    def __init__(self, *, headers=None, disconnects=None):
        self.headers = headers or {}
        self._disconnects = iter(disconnects or ())

    async def is_disconnected(self):
        return next(self._disconnects, False)


class ProjectionChangeTests(unittest.TestCase):
    def test_existing_history_is_baseline_and_unchanged_poll_is_silent(self):
        baseline = projection(
            sessions=(session("RUNNING"),),
            turns=(turn("RUNNING"),),
            stages=(stage(),),
        )
        self.assertEqual(events.project_changes(baseline, baseline), [])

    def test_progress_stage_and_transitions_emit_once_in_logical_order(self):
        baseline = projection(
            sessions=(session("PENDING"),),
            turns=(),
        )
        current = projection(
            completed_turns=1,
            sessions=(session("RUNNING"),),
            turns=(turn("COMPLETED"),),
            stages=(stage(),),
        )
        changes = events.project_changes(baseline, current)
        self.assertEqual(
            [name for name, _payload in changes],
            [
                "session_started",
                "stage_completed",
                "turn_completed",
                "progress",
            ],
        )
        stage_payload = changes[1][1]
        self.assertEqual(stage_payload["run_session_id"], "session-1")
        self.assertEqual(stage_payload["run_turn_id"], "turn-1")
        self.assertEqual(stage_payload["stage_name"], "INTENT")
        self.assertEqual(stage_payload["status"], "COMPLETED")
        self.assertEqual(stage_payload["duration_ms"], 4.5)
        self.assertIsNone(stage_payload["error_code"])
        self.assertEqual(events.project_changes(current, current), [])

    def test_session_and_turn_start_and_terminal_transitions(self):
        pending = projection(
            sessions=(session("PENDING"),), turns=(turn("PENDING"),)
        )
        running = projection(
            sessions=(session("RUNNING"),), turns=(turn("RUNNING"),)
        )
        self.assertEqual(
            [name for name, _ in events.project_changes(pending, running)],
            ["session_started", "turn_started"],
        )
        finished = projection(
            completed_turns=1,
            sessions=(session("COMPLETED"),),
            turns=(turn("ERROR"),),
        )
        names = [name for name, _ in events.project_changes(running, finished)]
        self.assertEqual(names, ["turn_completed", "session_completed", "progress"])
        self.assertEqual(events.project_changes(finished, finished), [])

    def test_each_run_terminal_status_has_matching_event(self):
        for status, expected in (
            ("COMPLETED", "run_completed"),
            ("FAILED", "run_failed"),
            ("CANCELLED", "run_cancelled"),
        ):
            with self.subTest(status=status):
                names = [
                    name
                    for name, _ in events.project_changes(
                        projection(), projection(status=status)
                    )
                ]
                self.assertEqual(names[-1], expected)


class SseStreamTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, response):
        return [chunk async for chunk in response.body_iterator]

    async def test_initial_snapshot_is_first_and_existing_stages_are_not_replayed(self):
        initial = projection(
            sessions=(session("RUNNING"),),
            turns=(turn("RUNNING"),),
            stages=(stage(),),
        )
        reader = AsyncMock(return_value=initial)
        request = FakeRequest(
            headers={"last-event-id": "obsolete-cursor"}, disconnects=[True]
        )
        with patch.object(events, "read_projection", reader), patch.object(
            events, "get_settings", return_value=SimpleNamespace(sse_poll_interval_seconds=0.01)
        ):
            response = await events.run_events(uuid.uuid4(), request)
            chunks = await self.collect(response)
        self.assertEqual(len(chunks), 1)
        name, payload = decode_chunk(chunks[0])
        self.assertEqual(name, "snapshot")
        self.assertEqual(payload["completed_turns"], 0)
        reader.assert_awaited_once()

    async def test_live_progress_terminal_event_and_stream_stop(self):
        initial = projection()
        completed = projection(status="COMPLETED", completed_turns=1)
        reader = AsyncMock(side_effect=[initial, completed])
        with patch.object(events, "read_projection", reader), patch.object(
            events, "get_settings", return_value=SimpleNamespace(sse_poll_interval_seconds=0.01)
        ), patch.object(events.asyncio, "sleep", AsyncMock()):
            response = await events.run_events(
                uuid.uuid4(), FakeRequest(disconnects=[False, False])
            )
            chunks = await self.collect(response)
        decoded = [decode_chunk(chunk)[0] for chunk in chunks]
        self.assertEqual(decoded, ["snapshot", "progress", "run_completed"])
        self.assertEqual(reader.await_count, 2)

    async def test_already_terminal_run_emits_snapshot_only(self):
        reader = AsyncMock(return_value=projection(status="FAILED"))
        with patch.object(events, "read_projection", reader), patch.object(
            events, "get_settings", return_value=SimpleNamespace(sse_poll_interval_seconds=1)
        ):
            response = await events.run_events(
                uuid.uuid4(), FakeRequest()
            )
            chunks = await self.collect(response)
        self.assertEqual([decode_chunk(chunk)[0] for chunk in chunks], ["snapshot"])

    async def test_database_failure_is_safe_and_retried(self):
        initial = projection()
        completed = projection(status="CANCELLED")
        reader = AsyncMock(side_effect=[initial, RuntimeError("database secret"), completed])
        with patch.object(events, "read_projection", reader), patch.object(
            events, "get_settings", return_value=SimpleNamespace(sse_poll_interval_seconds=0.01)
        ), patch.object(events.asyncio, "sleep", AsyncMock()):
            response = await events.run_events(
                uuid.uuid4(), FakeRequest(disconnects=[False] * 4)
            )
            chunks = await self.collect(response)
        rendered = b"".join(chunks)
        self.assertIn(b": evaluation state temporarily unavailable", rendered)
        self.assertNotIn(b"database secret", rendered)
        self.assertIn(b"event: run_cancelled", rendered)

    async def test_disconnect_stops_before_another_database_read(self):
        reader = AsyncMock(return_value=projection())
        with patch.object(events, "read_projection", reader), patch.object(
            events, "get_settings", return_value=SimpleNamespace(sse_poll_interval_seconds=1)
        ):
            response = await events.run_events(
                uuid.uuid4(), FakeRequest(disconnects=[True])
            )
            await self.collect(response)
        reader.assert_awaited_once()

    async def test_missing_run_is_normal_http_404_before_streaming(self):
        with patch.object(
            events, "read_projection", AsyncMock(side_effect=events.ProjectionNotFound())
        ):
            with self.assertRaises(HTTPException) as caught:
                await events.run_events(uuid.uuid4(), FakeRequest())
        self.assertEqual(caught.exception.status_code, 404)


class RedisFreeStartupTests(unittest.TestCase):
    def test_main_eval_lifecycle_has_no_stale_redis_or_celery_settings(self):
        source = Path("main.py").read_text(encoding="utf-8")
        for stale in (
            "evaluation_settings.use_celery",
            "evaluation_settings.redis_url",
            "Redis.from_url",
            "app.state.redis",
            "evaluation_redis",
        ):
            self.assertNotIn(stale, source)

    def test_standalone_app_and_worker_import_without_redis_package(self):
        modules = (
            "evaluation_system.backend.app.main",
            "evaluation_system.backend.app.worker.postgres_worker",
        )
        saved = {name: sys.modules.pop(name, None) for name in modules}
        real_import = __import__

        def no_redis(name, *args, **kwargs):
            if name == "redis" or name.startswith("redis."):
                raise AssertionError("Redis import attempted")
            return real_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=no_redis):
                for name in modules:
                    importlib.import_module(name)
        finally:
            for name, module in saved.items():
                if module is not None:
                    sys.modules[name] = module


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_cancellation_is_committed_without_event_transport(self):
        from evaluation_system.backend.app.api.runs import cancel_run

        row = SimpleNamespace(
            id=uuid.uuid4(),
            status="PENDING",
            cancel_requested_at=None,
            finished_at=None,
        )
        database = SimpleNamespace(
            get=AsyncMock(return_value=row), commit=AsyncMock()
        )
        result = await cancel_run(row.id, database)
        self.assertEqual(row.status, "CANCELLED")
        self.assertIs(row.finished_at, row.cancel_requested_at)
        self.assertEqual(result["status"], "CANCELLED")
        database.commit.assert_awaited_once()


class SettingsTests(unittest.TestCase):
    def test_sse_poll_interval_must_be_positive(self):
        from evaluation_system.backend.app.config import EvaluationSettings

        with patch.dict("os.environ", {"EVAL_SSE_POLL_INTERVAL_SECONDS": "0"}):
            with self.assertRaisesRegex(ValueError, "must be positive"):
                EvaluationSettings.from_environment()


if __name__ == "__main__":
    unittest.main()
