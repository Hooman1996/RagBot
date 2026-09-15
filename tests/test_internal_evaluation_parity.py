from __future__ import annotations

import unittest
import uuid
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import internal_evaluation_api as internal_api
from answering_service import AnswerResult
from conversation_history import EVALUATION_EXECUTION_POLICY
from evaluation_system.backend.app.services.history_state import (
    exact_agent_state_from_turns,
)
from utils.performance_config import PERFORMANCE_SETTINGS


SESSION_KEY = uuid.UUID("11111111-1111-4111-8111-111111111111")
TURN_ONE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


class HistoryStateBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_eval_transports_exact_state_and_ragbot_hydrates_it(self):
        stored_state = {
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
        persisted = {"metadata": {"agent_state_after": stored_state}}
        transported = exact_agent_state_from_turns([persisted])

        self.assertEqual(transported, stored_state)
        self.assertIsNot(transported, stored_state)
        before_hydration = deepcopy(stored_state)
        turn_two = internal_api.RequestLocalEvaluationHistory(
            evaluation_session_key=SESSION_KEY,
            evaluation_turn_id=uuid.uuid4(),
            turn_index=2,
            agent_state_before=transported,
        )
        snapshot = await turn_two.load_snapshot(SESSION_KEY)

        self.assertEqual(stored_state, before_hydration)
        self.assertEqual(snapshot.agent_state["slots"], {"card": "debit"})
        self.assertLessEqual(len(snapshot.agent_state["messages"]), 10)
        self.assertEqual(
            await turn_two.load_rewrite_messages(SESSION_KEY),
            snapshot.agent_state["messages"],
        )
        self.assertIsNone(snapshot.actor_id)

    async def test_first_turn_and_session_identity_remain_isolated(self):
        isolated_key = uuid.uuid4()
        isolated = internal_api.RequestLocalEvaluationHistory(
            evaluation_session_key=isolated_key,
            evaluation_turn_id=TURN_ONE_ID,
            turn_index=1,
            agent_state_before=None,
        )
        snapshot = await isolated.load_snapshot(isolated_key)
        self.assertEqual(snapshot.agent_state["messages"], [])
        self.assertIsNone(isolated.agent_state_after)


class RequestContextParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_context_matches_embedded_executor_contract(self):
        class CapturingService:
            async def answer(
                self,
                request,
                *,
                history_provider,
                observer,
                execution_policy,
            ):
                self.context = request
                self.provider = history_provider
                self.observer = observer
                self.policy = execution_policy
                snapshot = await history_provider.load_snapshot(
                    request.conversation_key
                )
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
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(answering_service=service))
        )

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


class RuntimeSnapshotOwnershipTests(unittest.TestCase):
    def test_authoritative_snapshot_is_owned_by_ragbot_endpoint(self):
        self.assertTrue(callable(internal_api.build_runtime_snapshot))
        self.assertFalse(
            Path(
                "evaluation_system/backend/app/services/config_snapshot.py"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
