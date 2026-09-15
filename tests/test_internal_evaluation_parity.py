from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import internal_evaluation_api as internal_api
from answering_service import AnswerResult
from conversation_history import EVALUATION_EXECUTION_POLICY
from evaluation_system.backend.app.core_adapter.history_state import (
    exact_agent_state_from_turns,
    exact_messages_from_turns,
)
from evaluation_system.backend.app.services import config_snapshot as old_snapshot
from evaluation_system.backend.app.tracing.collector import (
    EvaluationTraceCollector as OldEvaluationTraceCollector,
)
from pipeline_observer import PipelineStage, PipelineStageResult, json_safe
from utils.performance_config import PERFORMANCE_SETTINGS


SESSION_KEY = uuid.UUID("11111111-1111-4111-8111-111111111111")
TURN_ONE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def _serialized_records(collector):
    return [
        {
            "stage_name": record.stage.value,
            "stage_order": record.stage_order,
            "status": record.status,
            "input_data": record.input_data,
            "output_data": record.output_data,
            "metrics": record.metrics,
            "input_hash": record.input_hash,
            "output_hash": record.output_hash,
            "duration_ms": record.duration_ms,
            "error_code": record.error_code,
            "error_data": record.error_data,
        }
        for record in collector.records
    ]


class CollectorParityTests(unittest.TestCase):
    def test_actual_collectors_merge_the_same_representative_sequence(self):
        sequence = [
            PipelineStageResult(
                stage=PipelineStage.NORMALIZATION,
                input_data={"query": "raw"},
                output_data={"query": "normalized"},
                duration_ms=1.0,
            ),
            PipelineStageResult(
                stage=PipelineStage.HISTORY,
                output_data={"messages": []},
                duration_ms=2.0,
            ),
            PipelineStageResult(
                stage=PipelineStage.REWRITE,
                status="FALLBACK",
                input_data={"nested": {"old": 1}, "items": [1], "scalar": "old"},
                output_data={"query": "first"},
                metrics={"nested": {"first": True}},
                duration_ms=8.0,
                error_code="REWRITE_FALLBACK",
                error_data={"nested": {"old": True}, "items": ["old"]},
            ),
            PipelineStageResult(
                stage=PipelineStage.REWRITE,
                input_data={"nested": {"new": 2}, "items": [2], "scalar": "new"},
                output_data={"query": "second", "nested": {"kept": True}},
                metrics={"nested": {"second": True}},
                duration_ms=3.0,
                error_data={"nested": {"new": True}, "items": ["new"]},
            ),
            PipelineStageResult(stage=PipelineStage.INTENT, output_data={"intent": "general"}),
            PipelineStageResult(stage=PipelineStage.RETRIEVAL, output_data={"ids": [1, 2]}),
            PipelineStageResult(
                stage=PipelineStage.RERANK,
                output_data={"ids": [2, 1], "nested": {"first": 1}},
                metrics={"purpose": "answer_context", "scores": [0.9, 0.8]},
                duration_ms=4.0,
            ),
            PipelineStageResult(
                stage=PipelineStage.RERANK,
                output_data={"ids": [2], "nested": {"second": 2}},
                metrics={"scores": [0.91]},
                duration_ms=6.0,
            ),
            PipelineStageResult(stage=PipelineStage.CONTEXT_SELECTION, output_data={"ids": [2]}),
            PipelineStageResult(stage=PipelineStage.PROMPT_BUILD, metrics={"prompt_hash": "p"}),
            PipelineStageResult(stage=PipelineStage.GENERATION, output_data={"answer": "answer"}),
        ]
        old = OldEvaluationTraceCollector()
        new = internal_api.EvaluationTraceCollector()

        for result in sequence:
            old.record(result)
            new.record(result)

        self.assertEqual(_serialized_records(new), _serialized_records(old))
        rewrite = new.get(PipelineStage.REWRITE)
        self.assertEqual(rewrite.status, "FALLBACK")
        self.assertEqual(rewrite.duration_ms, 8.0)
        self.assertEqual(
            rewrite.input_data,
            {"nested": {"old": 1, "new": 2}, "items": [2], "scalar": "new"},
        )
        self.assertEqual(
            rewrite.error_data,
            {"nested": {"old": True, "new": True}, "items": ["new"]},
        )

        error = PipelineStageResult(
            stage=PipelineStage.REWRITE,
            status="ERROR",
            error_code="REWRITE_ERROR",
        )
        completed = PipelineStageResult(stage=PipelineStage.REWRITE, status="COMPLETED")
        for result in (error, completed):
            old.record(result)
            new.record(result)
        self.assertEqual(_serialized_records(new), _serialized_records(old))
        self.assertEqual(new.get(PipelineStage.REWRITE).status, "ERROR")


class HistoryStateParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_turn_state_matches_embedded_exact_state_helpers(self):
        turn_one = internal_api.RequestLocalEvaluationHistory(
            evaluation_session_key=SESSION_KEY,
            evaluation_turn_id=TURN_ONE_ID,
            turn_index=1,
            agent_state_before=None,
        )
        first_snapshot = await turn_one.load_snapshot(SESSION_KEY)
        self.assertIsNone(first_snapshot.actor_id)
        self.assertEqual(first_snapshot.agent_state["messages"], [])

        final_state = {
            **first_snapshot.agent_state,
            "messages": [
                {"role": "user", "content": str(index), "ignored": True}
                for index in range(11)
            ]
            + [{"role": "assistant", "content": "answer"}],
            "slots": {"card": "debit"},
            "current_scenario": "card_help",
            "feedback_needed": True,
            "asked_feedback": True,
            "related_questions": [{"question": "Next?"}],
            "allowed_docs": ["Cards"],
            "fallback_reason": "NO_RESULTS",
        }
        await turn_one.save_snapshot(first_snapshot, final_state)
        state_after = turn_one.agent_state_after
        old_turns = [{"metadata": {"agent_state_after": state_after}}]
        expected_state = exact_agent_state_from_turns(old_turns)
        expected_messages = exact_messages_from_turns(old_turns)

        turn_two = internal_api.RequestLocalEvaluationHistory(
            evaluation_session_key=SESSION_KEY,
            evaluation_turn_id=uuid.uuid4(),
            turn_index=2,
            agent_state_before=state_after,
        )
        second_snapshot = await turn_two.load_snapshot(SESSION_KEY)

        self.assertEqual(second_snapshot.agent_state, expected_state)
        self.assertEqual(
            await turn_two.load_rewrite_messages(SESSION_KEY), expected_messages
        )
        self.assertIsNone(second_snapshot.actor_id)
        self.assertIsNone(turn_two.agent_state_after)
        final_state["slots"]["card"] = "mutated"
        self.assertEqual(second_snapshot.agent_state["slots"], {"card": "debit"})

        isolated_key = uuid.uuid4()
        isolated = internal_api.RequestLocalEvaluationHistory(
            evaluation_session_key=isolated_key,
            evaluation_turn_id=uuid.uuid4(),
            turn_index=1,
            agent_state_before=None,
        )
        self.assertEqual(
            (await isolated.load_snapshot(isolated_key)).agent_state["messages"], []
        )


class RequestContextParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_context_matches_embedded_executor_contract(self):
        class CapturingService:
            async def answer(self, request, *, history_provider, observer, execution_policy):
                self.context = request
                self.provider = history_provider
                self.observer = observer
                self.policy = execution_policy
                snapshot = await history_provider.load_snapshot(request.conversation_key)
                await history_provider.save_snapshot(snapshot, snapshot.agent_state)
                return AnswerResult(
                    original_query=request.original_query,
                    normalized_query="normalized",
                    canonical_retrieval_query="canonical",
                    final_retrieval_query="final",
                    rewritten_query="rewritten",
                    intent="general",
                    answer="answer",
                )

        service = CapturingService()
        payload = internal_api.EvaluationTurnRequest(
            evaluation_session_key=SESSION_KEY,
            evaluation_turn_id=TURN_ONE_ID,
            turn_index=1,
            query="question",
            documents=["FAQ", "Cards"],
        )
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(answering_service=service)))

        response = await internal_api.execute_evaluation_turn(payload, request)

        self.assertEqual(response.status, "COMPLETED")
        self.assertEqual(service.context.selected_documents, ("FAQ", "Cards"))
        self.assertEqual(service.context.channel, "evaluation")
        self.assertIsNone(service.context.session_id)
        self.assertEqual(service.context.conversation_key, SESSION_KEY)
        self.assertTrue(service.context.use_history)
        self.assertTrue(service.context.persist_agent_state)
        self.assertTrue(service.context.include_related_questions)
        self.assertEqual(
            service.context.timeout_seconds,
            PERFORMANCE_SETTINGS.application_request_timeout_seconds,
        )
        self.assertTrue(service.context.apply_mobile_empty_answer_fallback)
        self.assertIs(service.policy, EVALUATION_EXECUTION_POLICY)
        self.assertEqual(service.provider.namespace, "evaluation")


class RuntimeSnapshotParityTests(unittest.TestCase):
    def test_runtime_snapshot_matches_embedded_snapshot_builder(self):
        class FakeRag:
            model_id = "generation-model"
            search_engine = SimpleNamespace(
                collection_name="knowledge",
                _expected_embedding_dimensions=768,
            )

            def answer(self):
                return None

        service = SimpleNamespace(
            agent_service=SimpleNamespace(rag_system=FakeRag()),
            intent_classifier=SimpleNamespace(
                model_path_basename="intent.bin",
                checkpoint_sha256="checkpoint",
                threshold=0.75,
                device="cpu",
                embedding_dimension=768,
                embedding_role="query",
                embedding_prompt_name="classification",
            ),
            history_rewriting_service=SimpleNamespace(
                config=SimpleNamespace(QUERY_REWRITE_PROMPT="rewrite prompt")
            ),
        )
        environment = {
            "EMBEDDING_MODEL": "embedding-model",
            "RERANKER_MODEL": "reranker-model",
            "LLM_MODEL": "environment-fallback-model",
            "QDRANT_COLLECTION": "environment-fallback-collection",
        }
        with patch.dict("os.environ", environment, clear=False), patch.object(
            old_snapshot, "git_commit_sha", return_value="ragbot-sha"
        ), patch.object(internal_api, "_git_commit_sha", return_value="ragbot-sha"):
            old = old_snapshot.build_config_snapshot(
                answering_service=service, selected_documents=["FAQ", "Cards"]
            )
            new = internal_api.build_runtime_snapshot(
                answering_service=service, selected_documents=["FAQ", "Cards"]
            )

        self.assertEqual(json_safe(new), json_safe(old))
        self.assertEqual(
            set(new),
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


if __name__ == "__main__":
    unittest.main()
