from __future__ import annotations

import json
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from evaluation_system.backend.app.clients.ragbot import (
    EvaluationStageResponse,
    EvaluationTurnResponse,
    RagBotClientError,
    RagBotEvaluationClient,
    RuntimeSnapshotResponse,
)


SESSION_KEY = uuid.UUID("11111111-1111-4111-8111-111111111111")
TURN_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def stage_payload(name: str, order: int, *, status: str = "COMPLETED") -> dict:
    return {
        "stage_name": name,
        "stage_order": order,
        "status": status,
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
        "duration_ms": 1.5,
        "input_data": {"input": name},
        "output_data": {"output": name},
        "metrics": {"selected_context_hash": "c" * 64}
        if name == "CONTEXT_SELECTION" else {},
        "error_code": None,
        "error_data": None,
    }


def turn_payload(*, status: str = "COMPLETED") -> dict:
    stages = [
        stage_payload(name, index * 10)
        for index, name in enumerate(
            (
                "NORMALIZATION", "HISTORY", "REWRITE", "INTENT", "RETRIEVAL",
                "RERANK", "CONTEXT_SELECTION", "PROMPT_BUILD", "GENERATION",
            ),
            start=1,
        )
    ]
    if status == "ERROR":
        stages[4]["status"] = "ERROR"
        stages[4]["error_code"] = "DEPENDENCY_TIMEOUT"
        stages[4]["error_data"] = {"error_type": "ServiceTimeoutError"}
        for stage in stages[5:]:
            stage["status"] = "SKIPPED"
        answer = None
        state_after = None
    else:
        answer = "answer"
        state_after = {"messages": [{"role": "assistant", "content": "answer"}]}
    return {
        "status": status,
        "evaluation_session_key": str(SESSION_KEY),
        "evaluation_turn_id": str(TURN_ID),
        "turn_index": 2,
        "original_query": "question",
        "answer": answer,
        "normalized_query": "normalized",
        "rewritten_query": "rewritten",
        "canonical_retrieval_query": "canonical",
        "final_retrieval_query": "final",
        "intent": "general",
        "intent_details": {"confidence": 0.91},
        "related_questions": [],
        "feedback_needed": True,
        "fallback_reason": None,
        "timings_ms": {"total": 123.0},
        "history_before": [],
        "history_after": [],
        "history_before_hash": "d" * 64,
        "history_after_hash": "e" * 64,
        "agent_state_after": state_after,
        "infrastructure_error": status == "ERROR",
        "error_code": "DEPENDENCY_TIMEOUT" if status == "ERROR" else None,
        "error_data": {"error_type": "ServiceTimeoutError"} if status == "ERROR" else None,
        "stages": stages,
        "future_field": "accepted",
    }


class RagBotClientContractTests(unittest.IsolatedAsyncioTestCase):
    async def _client(self, handler):
        return RagBotEvaluationClient(
            base_url="http://ragbot.test///",
            timeout_seconds=70,
            transport=httpx.MockTransport(handler),
        )

    async def test_turn_serialization_state_and_success_parsing(self):
        state = {"messages": [{"role": "user", "content": "prior"}]}

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, RagBotEvaluationClient.TURN_PATH)
            body = json.loads(request.content)
            self.assertEqual(body, {
                "evaluation_session_key": str(SESSION_KEY),
                "evaluation_turn_id": str(TURN_ID),
                "turn_index": 2,
                "query": "question",
                "documents": ["A", "B"],
                "agent_state_before": state,
            })
            return httpx.Response(200, json=turn_payload())

        client = await self._client(handler)
        try:
            result = await client.evaluate_turn(
                evaluation_session_key=SESSION_KEY,
                evaluation_turn_id=TURN_ID,
                turn_index=2,
                query="question",
                documents=["A", "B"],
                agent_state_before=state,
            )
        finally:
            await client.aclose()
        self.assertEqual(result.answer, "answer")
        self.assertEqual(result.agent_state_after["messages"][0]["content"], "answer")
        self.assertEqual(len(result.stages), 9)

    async def test_structured_error_is_returned_not_raised(self):
        client = await self._client(
            lambda _request: httpx.Response(200, json=turn_payload(status="ERROR"))
        )
        try:
            result = await client.evaluate_turn(
                evaluation_session_key=SESSION_KEY,
                evaluation_turn_id=TURN_ID,
                turn_index=2,
                query="question",
                documents=[],
                agent_state_before=None,
            )
        finally:
            await client.aclose()
        self.assertEqual(result.status, "ERROR")
        self.assertEqual(result.error_code, "DEPENDENCY_TIMEOUT")
        self.assertEqual(result.stages[4].status, "ERROR")

    async def test_returned_stage_hashes_are_preserved_verbatim(self):
        payload = turn_payload()
        payload["stages"][0]["input_hash"] = "f" * 64
        client = await self._client(
            lambda _request: httpx.Response(200, json=payload)
        )
        try:
            result = await client.evaluate_turn(
                evaluation_session_key=SESSION_KEY,
                evaluation_turn_id=TURN_ID,
                turn_index=2,
                query="question",
                documents=[],
                agent_state_before=None,
            )
        finally:
            await client.aclose()
        self.assertEqual(
            result.stages[0].input_hash,
            "f" * 64,
        )

    async def test_runtime_snapshot_uses_repeated_document_parameters(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, RagBotEvaluationClient.SNAPSHOT_PATH)
            self.assertEqual(request.url.params.get_list("documents"), ["A", "B"])
            return httpx.Response(200, json={
                "config_snapshot": {"retrieval": {"knowledge_sources": ["A", "B"]}},
                "git_commit_sha": "abc123",
            })
        client = await self._client(handler)
        try:
            result = await client.runtime_snapshot(["A", "B"])
        finally:
            await client.aclose()
        self.assertEqual(result.git_commit_sha, "abc123")

    async def test_datasource_shape_is_parsed(self):
        client = await self._client(lambda request: httpx.Response(200, json={
            "documents": [{"name": "General_FAQ", "category": "FAQ"}],
            "count": 1,
            "categories": ["FAQ"],
        }))
        try:
            result = await client.list_datasources()
        finally:
            await client.aclose()
        self.assertEqual(result.documents[0].name, "General_FAQ")

    async def test_transport_failures_map_to_safe_codes(self):
        cases = (
            (httpx.ConnectTimeout("secret URL"), "RAGBOT_TIMEOUT", "timeout"),
            (httpx.ConnectError("secret URL"), "RAGBOT_UNAVAILABLE", "connection"),
        )
        for exception, code, kind in cases:
            with self.subTest(code=code):
                client = await self._client(lambda _request, exc=exception: (_ for _ in ()).throw(exc))
                try:
                    with self.assertRaises(RagBotClientError) as caught:
                        await client.list_datasources()
                finally:
                    await client.aclose()
                self.assertEqual(caught.exception.error_code, code)
                self.assertEqual(caught.exception.error_data, {"failure_kind": kind})
                self.assertNotIn("secret", str(caught.exception))

    async def test_5xx_malformed_missing_and_422_are_safely_classified(self):
        cases = (
            (httpx.Response(503, text="secret upstream body"), "RAGBOT_UNAVAILABLE"),
            (httpx.Response(200, content=b"not-json"), "RAGBOT_INVALID_RESPONSE"),
            (httpx.Response(200, json={"count": 0}), "RAGBOT_INVALID_RESPONSE"),
            (httpx.Response(422, text="secret contract body"), "RAGBOT_REQUEST_REJECTED"),
        )
        for response, code in cases:
            with self.subTest(code=code):
                client = await self._client(lambda _request, value=response: value)
                try:
                    with self.assertRaises(RagBotClientError) as caught:
                        await client.list_datasources()
                finally:
                    await client.aclose()
                self.assertEqual(caught.exception.error_code, code)
                self.assertNotIn("secret", str(caught.exception))


class FakeSession:
    def __init__(self, turn=None, scalar_value=None, scalar_rows=None):
        self.turn = turn
        self.scalar_value = scalar_value
        self.scalar_rows = scalar_rows or []
        self.added = []

    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return False
    async def get(self, _model, _identity, **_kwargs): return self.turn
    async def scalar(self, _query): return self.scalar_value
    async def scalars(self, _query): return self.scalar_rows
    def add(self, value): self.added.append(value)
    async def commit(self): return None


class RunnerHttpBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def _runner(self, session, client=None):
        from evaluation_system.backend.app.worker.runner import EvaluationRunExecutor
        return EvaluationRunExecutor(
            session_factory=lambda: session,
            ragbot_client=client or AsyncMock(),
        )

    async def test_remote_turn_uses_only_evaluation_identifiers_and_exact_state(self):
        client = AsyncMock()
        client.evaluate_turn.return_value = EvaluationTurnResponse.model_validate(turn_payload())
        runner = self._runner(FakeSession(), client)
        source = SimpleNamespace(turn_index=2, query="question")
        run_session = SimpleNamespace(
            evaluation_session_key=SESSION_KEY,
            source_session_id="PRODUCTION_SESSION_MUST_NOT_TRAVEL",
        )
        state = {"messages": [{"role": "assistant", "content": "STATE_1"}]}
        await runner._evaluate_remote_turn(
            run_session, SimpleNamespace(id=TURN_ID), source, ["A"], state
        )
        client.evaluate_turn.assert_awaited_once_with(
            evaluation_session_key=SESSION_KEY,
            evaluation_turn_id=TURN_ID,
            turn_index=2,
            query="question",
            documents=["A"],
            agent_state_before=state,
        )
        self.assertNotIn(
            "PRODUCTION_SESSION_MUST_NOT_TRAVEL",
            repr(client.evaluate_turn.await_args),
        )

    async def test_exact_previous_success_state_is_used_and_repetitions_isolate(self):
        state_1 = {"messages": [{"role": "assistant", "content": "STATE_1"}]}
        prior = SimpleNamespace(metadata_json={"agent_state_after": state_1})
        runner = self._runner(FakeSession(scalar_rows=[prior]))
        restored = await runner._state_before(uuid.uuid4(), 2)
        self.assertEqual(restored, state_1)
        fresh = await self._runner(FakeSession(scalar_rows=[]))._state_before(uuid.uuid4(), 1)
        self.assertIsNone(fresh)

    async def test_success_persists_existing_turn_and_all_stage_fields(self):
        turn = SimpleNamespace(metadata_json={"preserved": True})
        session = FakeSession(turn=turn)
        runner = self._runner(session)
        result = EvaluationTurnResponse.model_validate(turn_payload())
        await runner._complete_turn(TURN_ID, result)
        self.assertEqual(turn.normalized_query, "normalized")
        self.assertEqual(turn.rewritten_query, "rewritten")
        self.assertEqual(turn.actual_intent, "general")
        self.assertEqual(turn.intent_score, 0.91)
        self.assertEqual(turn.actual_answer, "answer")
        self.assertFalse(turn.fallback_used)
        self.assertEqual(turn.history_before_hash, "d" * 64)
        self.assertEqual(turn.history_after_hash, "e" * 64)
        self.assertEqual(turn.selected_context_hash, "c" * 64)
        self.assertEqual(turn.total_latency_ms, 123.0)
        self.assertEqual(turn.metadata_json["agent_state_after"], result.agent_state_after)
        self.assertEqual(len(session.added), 9)
        self.assertEqual(session.added[6].input_hash, "a" * 64)
        self.assertEqual(session.added[6].output_hash, "b" * 64)

    async def test_structured_error_preserves_exact_trace_and_suppresses_state(self):
        turn = SimpleNamespace(metadata_json={"agent_state_after": {"stale": True}})
        session = FakeSession(turn=turn)
        runner = self._runner(session)
        result = EvaluationTurnResponse.model_validate(turn_payload(status="ERROR"))
        await runner._structured_error_turn(
            TURN_ID, result=result, total_latency_ms=123.0
        )
        self.assertEqual(turn.status, "ERROR")
        self.assertTrue(turn.infrastructure_error)
        self.assertEqual(turn.error_code, "DEPENDENCY_TIMEOUT")
        self.assertEqual(turn.error_data, {"error_type": "ServiceTimeoutError"})
        self.assertNotIn("agent_state_after", turn.metadata_json)
        self.assertEqual(
            [(item.stage_name, item.status) for item in session.added],
            [(item.stage_name, item.status) for item in result.stages],
        )

    async def test_transport_error_is_safe_and_infrastructure(self):
        turn = SimpleNamespace(metadata_json={"agent_state_after": {"stale": True}})
        session = FakeSession(turn=turn)
        runner = self._runner(session)
        error = RagBotClientError("RAGBOT_UNAVAILABLE", "connection")
        stages = runner._transport_error_stages(error)
        await runner._transport_error_turn(
            TURN_ID, error, stages, infrastructure=True, total_latency_ms=9.0
        )
        self.assertTrue(turn.infrastructure_error)
        self.assertEqual(turn.error_code, "RAGBOT_UNAVAILABLE")
        self.assertEqual(turn.error_data, {"failure_kind": "connection"})
        self.assertNotIn("agent_state_after", turn.metadata_json)
        self.assertEqual(len(session.added), 9)

    async def test_claim_uses_remote_runtime_snapshot_and_git_sha(self):
        run = SimpleNamespace(
            status="PENDING",
            started_at=None,
            worker_task_id=None,
            config_snapshot={
                "schema_version": "evaluation-pending-v1",
                "retrieval": {"knowledge_sources": ["A", "B"]},
                "runtime_snapshot_pending": True,
            },
            git_commit_sha=None,
        )
        client = AsyncMock()
        client.runtime_snapshot.return_value = RuntimeSnapshotResponse(
            config_snapshot={"retrieval": {"knowledge_sources": ["A", "B"]}, "remote": True},
            git_commit_sha="ragbot-sha",
        )
        runner = self._runner(FakeSession(scalar_value=run), client)
        result = await runner._claim_run(uuid.uuid4(), "task-1")
        self.assertIs(result, run)
        client.runtime_snapshot.assert_awaited_once_with(["A", "B"])
        self.assertTrue(run.config_snapshot["remote"])
        self.assertEqual(run.git_commit_sha, "ragbot-sha")

    async def test_preclaimed_run_still_replaces_pending_runtime_snapshot(self):
        run = SimpleNamespace(
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            worker_task_id="worker-a",
            heartbeat_at=None,
            config_snapshot={
                "retrieval": {"knowledge_sources": ["A"]},
                "runtime_snapshot_pending": True,
            },
            git_commit_sha=None,
        )
        client = AsyncMock()
        client.runtime_snapshot.return_value = RuntimeSnapshotResponse(
            config_snapshot={"authoritative": True},
            git_commit_sha="ragbot-sha",
        )
        runner = self._runner(FakeSession(scalar_value=run), client)

        result = await runner._claim_run(uuid.uuid4(), "worker-a")

        self.assertIs(result, run)
        client.runtime_snapshot.assert_awaited_once_with(["A"])
        self.assertEqual(run.config_snapshot, {"authoritative": True})
        self.assertEqual(run.git_commit_sha, "ragbot-sha")


class DatasourceAndStaticMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_eval_datasource_endpoint_keeps_frontend_shape(self):
        from evaluation_system.backend.app.api import datasources

        response = SimpleNamespace(documents=[SimpleNamespace(name="General_FAQ")])
        fake_client = AsyncMock()
        fake_client.list_datasources.return_value = response
        fake_context = AsyncMock()
        fake_context.__aenter__.return_value = fake_client
        with patch.object(datasources, "RagBotEvaluationClient", return_value=fake_context):
            result = await datasources.list_datasources()
        self.assertEqual(result, [{"title": "General_FAQ"}])

    def test_active_worker_path_has_no_local_ragbot_runtime_imports(self):
        worker_sources = "\n".join(
            Path(path).read_text(encoding="utf-8")
            for path in (
                "evaluation_system/backend/app/worker/postgres_queue.py",
                "evaluation_system/backend/app/worker/postgres_worker.py",
            )
        )
        forbidden = (
            "core_adapter.runtime", "canonical_turn_runtime", "RAGSystem",
            "AgentService", "AnsweringService", "QdrantClient", "AsyncOpenAI",
        )
        for name in forbidden:
            self.assertNotIn(name, worker_sources)

    def test_http_client_has_no_chatbot_execution_dependencies(self):
        source = Path(
            "evaluation_system/backend/app/clients/ragbot.py"
        ).read_text(encoding="utf-8")
        forbidden = (
            "AnsweringService", "AgentService", "RAGSystem",
            "HistoryRewritingService", "intent_classifier_factory",
            "DatabaseManager", "ChatManager", "ProductionHistoryProvider",
            "QdrantClient", "AsyncOpenAI", "torch", "CUDA",
        )
        for name in forbidden:
            self.assertNotIn(name, source)


class Stage3ConfigurationTests(unittest.TestCase):
    def tearDown(self):
        from evaluation_system.backend.app.config import get_settings
        get_settings.cache_clear()

    def test_ragbot_connection_settings_normalize_and_validate(self):
        from evaluation_system.backend.app.config import get_settings

        with patch.dict("os.environ", {
            "EVAL_RAGBOT_BASE_URL": "  http://ragbot.internal:8000///  ",
            "EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS": "75",
        }, clear=False):
            get_settings.cache_clear()
            settings = get_settings()
            self.assertEqual(settings.ragbot_base_url, "http://ragbot.internal:8000")
            self.assertEqual(settings.ragbot_http_timeout_seconds, 75.0)

        with patch.dict("os.environ", {"EVAL_RAGBOT_BASE_URL": "   "}, clear=False):
            get_settings.cache_clear()
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                get_settings()


if __name__ == "__main__":
    unittest.main()
