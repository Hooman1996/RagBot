from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI

import internal_evaluation_api as internal_api
from answering_service import AnswerResult
from conversation_history import EVALUATION_EXECUTION_POLICY
from pipeline_observer import PipelineStage, PipelineStageResult, stable_hash
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.service_errors import InvalidRequestError, ServiceUnavailableError


SESSION_KEY = uuid.UUID("11111111-1111-4111-8111-111111111111")
TURN_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
STAGE_NAMES = [stage.value for stage in PipelineStage]


def _payload(**overrides):
    payload = {
        "evaluation_session_key": str(SESSION_KEY),
        "evaluation_turn_id": str(TURN_ID),
        "turn_index": 1,
        "query": "How do I open an account?",
        "documents": ["FAQ"],
        "agent_state_before": None,
    }
    payload.update(overrides)
    return payload


def _app(answering_service) -> FastAPI:
    app = FastAPI()
    app.include_router(internal_api.router)
    app.state.answering_service = answering_service
    return app


class SuccessfulAnsweringService:
    def __init__(self):
        self.call = None

    async def answer(
        self, request, *, history_provider, observer, execution_policy
    ) -> AnswerResult:
        self.call = {
            "request": request,
            "history_provider": history_provider,
            "observer": observer,
            "execution_policy": execution_policy,
        }
        before = await history_provider.load_rewrite_messages(
            request.conversation_key
        )
        snapshot = await history_provider.load_snapshot(request.conversation_key)
        final_state = dict(snapshot.agent_state)
        final_state["messages"] = [
            *before,
            {"role": "user", "content": request.original_query},
            {"role": "assistant", "content": "Use the mobile app."},
        ]
        final_state["feedback_needed"] = True
        await history_provider.save_snapshot(snapshot, final_state)
        observer.record(
            PipelineStageResult(
                stage=PipelineStage.NORMALIZATION,
                input_data={"raw_query": request.original_query},
                output_data={"normalized_query": "normalized"},
                duration_ms=1.25,
            )
        )
        observer.record(
            PipelineStageResult(
                stage=PipelineStage.GENERATION,
                output_data={"answer": "Use the mobile app."},
                metrics={"answer_hash": "answer-hash"},
                duration_ms=9.5,
            )
        )
        after = final_state["messages"]
        return AnswerResult(
            original_query=request.original_query,
            normalized_query="normalized",
            rewritten_query="rewritten",
            canonical_retrieval_query="canonical",
            final_retrieval_query="final",
            intent="general",
            intent_details={"confidence": 0.91, "scenario_id": None},
            answer="Use the mobile app.",
            related_questions=[{"question": "What documents are needed?"}],
            feedback_needed=True,
            timings_ms={"total": 12.5},
            fallback_reason="NO_RESULTS",
            history_before=before,
            history_after=after,
            history_before_hash=stable_hash(before),
            history_after_hash=stable_hash(after),
        )


class FailingAnsweringService:
    def __init__(self, error):
        self.error = error

    async def answer(
        self, request, *, history_provider, observer, execution_policy
    ):
        observer.record(
            PipelineStageResult(
                stage=PipelineStage.NORMALIZATION,
                output_data={"normalized_query": "normalized"},
            )
        )
        observer.record(PipelineStageResult(stage=PipelineStage.HISTORY))
        raise self.error


class TurnEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def _post(self, service, payload=None):
        transport = httpx.ASGITransport(app=_app(service))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/api/internal/evaluation/v1/turn",
                json=payload or _payload(),
            )

    async def test_success_uses_exact_evaluation_context_and_transports_result(self):
        service = SuccessfulAnsweringService()

        response = await self._post(service)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        context = service.call["request"]
        self.assertEqual(context.channel, "evaluation")
        self.assertIsNone(context.session_id)
        self.assertEqual(context.conversation_key, SESSION_KEY)
        self.assertTrue(context.use_history)
        self.assertTrue(context.persist_agent_state)
        self.assertTrue(context.include_related_questions)
        self.assertTrue(context.apply_mobile_empty_answer_fallback)
        self.assertEqual(
            context.timeout_seconds,
            PERFORMANCE_SETTINGS.application_request_timeout_seconds,
        )
        self.assertIs(
            service.call["execution_policy"], EVALUATION_EXECUTION_POLICY
        )
        self.assertFalse(
            service.call["execution_policy"].persist_real_chat_history
        )
        self.assertFalse(service.call["execution_policy"].allow_ticket_writes)
        self.assertFalse(service.call["execution_policy"].allow_feedback_writes)
        self.assertFalse(
            service.call["execution_policy"].allow_satisfaction_writes
        )
        self.assertFalse(
            service.call["execution_policy"].allow_user_state_modifications
        )
        self.assertEqual(service.call["history_provider"].namespace, "evaluation")
        self.assertTrue(service.call["observer"].pipeline_hashes_enabled)

        self.assertEqual(body["status"], "COMPLETED")
        self.assertEqual(body["evaluation_session_key"], str(SESSION_KEY))
        self.assertEqual(body["evaluation_turn_id"], str(TURN_ID))
        self.assertEqual(body["turn_index"], 1)
        self.assertEqual(body["original_query"], "How do I open an account?")
        self.assertEqual(body["answer"], "Use the mobile app.")
        self.assertEqual(body["normalized_query"], "normalized")
        self.assertEqual(body["rewritten_query"], "rewritten")
        self.assertEqual(body["canonical_retrieval_query"], "canonical")
        self.assertEqual(body["final_retrieval_query"], "final")
        self.assertEqual(body["intent"], "general")
        self.assertEqual(body["intent_details"]["confidence"], 0.91)
        self.assertEqual(
            body["related_questions"],
            [{"question": "What documents are needed?"}],
        )
        self.assertTrue(body["feedback_needed"])
        self.assertEqual(body["fallback_reason"], "NO_RESULTS")
        self.assertEqual(body["timings_ms"], {"total": 12.5})
        self.assertEqual(body["history_before"], [])
        self.assertEqual(body["history_before_hash"], stable_hash([]))
        self.assertEqual(body["history_after_hash"], stable_hash(body["history_after"]))
        self.assertEqual(
            body["agent_state_after"]["messages"], body["history_after"]
        )
        self.assertFalse(body["infrastructure_error"])
        self.assertIsNone(body["error_code"])

        self.assertEqual(
            [stage["stage_name"] for stage in body["stages"]], STAGE_NAMES
        )
        missing = {
            stage["stage_name"]: stage for stage in body["stages"]
        }
        self.assertEqual(missing["HISTORY"]["status"], "SKIPPED")
        self.assertEqual(
            missing["HISTORY"]["metrics"], {"reason": "NOT_APPLICABLE"}
        )
        self.assertEqual(missing["HISTORY"]["duration_ms"], 0.0)

    async def test_dependency_error_returns_complete_safe_partial_trace(self):
        secret_message = "postgresql://user:password@host/customer"
        response = await self._post(
            FailingAnsweringService(ServiceUnavailableError(secret_message))
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ERROR")
        self.assertTrue(body["infrastructure_error"])
        self.assertEqual(body["error_code"], "DEPENDENCY_UNAVAILABLE")
        self.assertEqual(
            body["error_data"], {"error_type": "ServiceUnavailableError"}
        )
        self.assertIsNone(body["agent_state_after"])
        self.assertIsNone(body["answer"])
        self.assertNotIn(secret_message, response.text)
        self.assertNotIn("Traceback", response.text)
        stages = {stage["stage_name"]: stage for stage in body["stages"]}
        self.assertEqual(list(stages), STAGE_NAMES)
        self.assertEqual(stages["NORMALIZATION"]["status"], "COMPLETED")
        self.assertEqual(stages["HISTORY"]["status"], "COMPLETED")
        self.assertEqual(stages["REWRITE"]["status"], "ERROR")
        self.assertEqual(
            stages["REWRITE"]["error_code"], "DEPENDENCY_UNAVAILABLE"
        )
        self.assertEqual(stages["INTENT"]["status"], "SKIPPED")

    async def test_invalid_request_error_is_not_infrastructure(self):
        response = await self._post(
            FailingAnsweringService(InvalidRequestError("unsafe query content"))
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ERROR")
        self.assertFalse(body["infrastructure_error"])
        self.assertEqual(body["error_code"], "INVALID_REQUEST")
        self.assertNotIn("unsafe query content", response.text)

    async def test_unknown_error_uses_bounded_generic_code(self):
        response = await self._post(
            FailingAnsweringService(RuntimeError("secret runtime details"))
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ERROR")
        self.assertFalse(body["infrastructure_error"])
        self.assertEqual(body["error_code"], "EVALUATION_TURN_ERROR")
        self.assertNotIn("secret runtime details", response.text)

    async def test_request_validation_rejects_blank_query_and_bad_turn_index(self):
        response = await self._post(
            SuccessfulAnsweringService(),
            _payload(query="  ", turn_index=0),
        )

        self.assertEqual(response.status_code, 422)


class HistoryProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_state_round_trip_is_json_safe_trimmed_and_request_local(self):
        turn_one = internal_api.RequestLocalEvaluationHistory(
            evaluation_session_key=SESSION_KEY,
            evaluation_turn_id=TURN_ID,
            turn_index=1,
            agent_state_before=None,
        )
        fresh = await turn_one.load_snapshot(SESSION_KEY)
        self.assertIsNone(fresh.actor_id)
        self.assertEqual(fresh.agent_state["messages"], [])
        final_state = dict(fresh.agent_state)
        final_state["messages"] = [
            {"role": "user", "content": str(index)} for index in range(12)
        ]
        final_state["tuple_value"] = ("json", "safe")
        await turn_one.save_snapshot(fresh, final_state)
        saved = turn_one.agent_state_after
        self.assertEqual(saved["tuple_value"], ["json", "safe"])

        final_state["messages"].append({"role": "user", "content": "mutated"})
        self.assertNotEqual(saved["messages"], final_state["messages"])

        turn_two = internal_api.RequestLocalEvaluationHistory(
            evaluation_session_key=SESSION_KEY,
            evaluation_turn_id=uuid.uuid4(),
            turn_index=2,
            agent_state_before=saved,
        )
        messages = await turn_two.load_rewrite_messages(SESSION_KEY)
        snapshot = await turn_two.load_snapshot(SESSION_KEY)
        self.assertEqual(len(messages), 10)
        self.assertEqual(messages[0]["content"], "2")
        self.assertEqual(snapshot.agent_state["messages"], messages)
        self.assertIsNone(turn_two.agent_state_after)


class TraceCollectorTests(unittest.TestCase):
    def test_all_stages_are_canonical_order_with_hashes(self):
        collector = internal_api.EvaluationTraceCollector()
        for stage in reversed(tuple(PipelineStage)):
            collector.record(
                PipelineStageResult(
                    stage=stage,
                    input_data={"stage": stage.value, "side": "input"},
                    output_data={"stage": stage.value, "side": "output"},
                )
            )

        serialized = internal_api._serialize_stages(collector)

        self.assertEqual([item.stage_name for item in serialized], STAGE_NAMES)
        self.assertEqual(
            [item.stage_order for item in serialized],
            sorted(item.stage_order for item in serialized),
        )
        self.assertTrue(all(item.input_hash for item in serialized))
        self.assertTrue(all(item.output_hash for item in serialized))

    def test_merge_matches_embedded_evaluator_semantics(self):
        collector = internal_api.EvaluationTraceCollector()
        collector.record(
            PipelineStageResult(
                stage=PipelineStage.REWRITE,
                status="FALLBACK",
                input_data={"nested": {"left": 1}, "items": [1]},
                metrics={"first": True},
                duration_ms=8.0,
                error_code="FIRST_ERROR",
                error_data={"left": 1, "nested": {"old": True}},
            )
        )
        collector.record(
            PipelineStageResult(
                stage=PipelineStage.REWRITE,
                status="COMPLETED",
                input_data={"nested": {"right": 2}, "items": [2]},
                metrics={"second": True},
                duration_ms=3.0,
                error_code="SECOND_ERROR",
                error_data={"right": 2, "nested": {"new": True}},
            )
        )
        collector.record(
            PipelineStageResult(
                stage=PipelineStage.REWRITE,
                status="ERROR",
                duration_ms=5.0,
            )
        )
        collector.record(
            PipelineStageResult(
                stage=PipelineStage.REWRITE,
                status="SKIPPED",
                duration_ms=4.0,
            )
        )

        record = collector.get(PipelineStage.REWRITE)
        self.assertEqual(record.status, "ERROR")
        self.assertEqual(
            record.input_data,
            {"nested": {"left": 1, "right": 2}, "items": [2]},
        )
        self.assertEqual(record.metrics, {"first": True, "second": True})
        self.assertEqual(record.duration_ms, 8.0)
        self.assertEqual(record.error_code, "SECOND_ERROR")
        self.assertEqual(
            record.error_data,
            {"left": 1, "right": 2, "nested": {"old": True, "new": True}},
        )


class RuntimeSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_uses_active_runtime_and_exposes_no_secret_env_values(self):
        class FakeRag:
            model_id = "test-generation-model"
            search_engine = SimpleNamespace(
                collection_name="test-collection",
                _expected_embedding_dimensions=768,
            )

            def answer(self):
                return None

        service = SimpleNamespace(
            agent_service=SimpleNamespace(rag_system=FakeRag()),
            intent_classifier=SimpleNamespace(
                model_path_basename="intent.bin",
                checkpoint_sha256="checkpoint-sha",
                threshold=0.8,
                device="cpu",
                embedding_dimension=768,
                embedding_role="query",
                embedding_prompt_name="classification",
            ),
            history_rewriting_service=SimpleNamespace(
                config=SimpleNamespace(QUERY_REWRITE_PROMPT="rewrite prompt")
            ),
        )
        secret = "do-not-expose-this-secret"
        transport = httpx.ASGITransport(app=_app(service))
        with patch.dict(
            "os.environ",
            {
                "POSTGRES_PASSWORD": secret,
                "QDRANT_API_KEY": secret,
                "VLLM_API_KEY": secret,
            },
            clear=False,
        ), patch.object(internal_api, "_git_commit_sha", return_value=None):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/internal/evaluation/v1/runtime-snapshot",
                    params=[("documents", "FAQ"), ("documents", "Cards")],
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        snapshot = body["config_snapshot"]
        self.assertEqual(
            set(snapshot),
            {
                "schema_version",
                "intent",
                "normalizer",
                "query_canonicalization",
                "rewrite",
                "embedding",
                "retrieval",
                "rerank",
                "generation",
                "git_commit_sha",
            },
        )
        self.assertEqual(snapshot["retrieval"]["knowledge_sources"], ["FAQ", "Cards"])
        self.assertEqual(snapshot["retrieval"]["qdrant_collection"], "test-collection")
        self.assertEqual(snapshot["generation"]["model"], "test-generation-model")
        self.assertIsNone(snapshot["git_commit_sha"])
        self.assertIsNone(body["git_commit_sha"])
        self.assertNotIn(secret, response.text)


class StaticIsolationTests(unittest.TestCase):
    def test_internal_module_has_no_production_history_or_session_calls(self):
        source = Path("internal_evaluation_api.py").read_text(encoding="utf-8")
        forbidden = (
            "ProductionHistoryProvider",
            "DatabaseManager",
            "ChatManager",
            "resolve_mobile_session",
            "get_or_create_mobile_session",
            "get_or_create_user_by_national_code",
            ".add_message(",
            "._create_ticket(",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertNotIn(name, source)


if __name__ == "__main__":
    unittest.main()
