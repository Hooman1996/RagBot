from __future__ import annotations

import unittest
from types import SimpleNamespace

from answering_service import AnswerRequestContext, AnsweringService
from conversation_history import (
    EVALUATION_EXECUTION_POLICY,
    format_answer_prompt_history,
    format_rewrite_history,
    select_answer_prompt_history,
    trim_agent_messages,
    messages_from_turn_records,
)
from evaluation_system.backend.app.core_adapter.history_state import (
    exact_messages_from_turns,
)


class ImmediateRunner:
    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class HistoryProvider:
    def __init__(self, namespace, messages):
        self.namespace = namespace
        self.messages = messages
        self.keys = []

    async def load_rewrite_messages(self, key):
        self.keys.append(key)
        return self.messages


class Classifier:
    threshold = 0.875
    async def classify_detailed(self, query):
        return {
            "type": "general",
            "scenario_id": None,
            "confidence": 0.91,
            "probability_actionable": 0.91,
            "probability_chitchat": 0.09,
        }


class Rewriter:
    async def rewrite_query(self, current_query, current_summary):
        return f"{current_query}|{current_summary}"


class Agent:
    def __init__(self):
        self.calls = []
    async def process_message_detailed(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(answer="A", state={
            "messages": [
                {"role": "user", "content": "Q1"},
                {"role": "assistant", "content": "A1"},
                {"role": "user", "content": kwargs["user_message"]},
                {"role": "assistant", "content": "A"},
            ],
            "related_questions": [], "feedback_needed": True,
        })


class Processor:
    def normalize(self, value): return value


class SharedHistoryRuleTests(unittest.TestCase):
    def test_rewrite_rules_are_shared_exactly(self):
        messages = [
            {"role": "user", "content": "same"},
            {"role": "assistant", "content": "same"},
            {"role": "assistant", "content": "answer"},
        ]
        self.assertEqual(format_rewrite_history(messages), "User: same\nAI: answer")

    def test_prompt_selection_and_formatting_are_single_shared_functions(self):
        messages = [{"role": "user", "content": str(index)} for index in range(9)]
        selected = select_answer_prompt_history(messages)
        self.assertEqual([item["content"] for item in selected], ["2", "3", "4", "5", "6", "7"])
        self.assertEqual(format_answer_prompt_history(selected).splitlines()[0], "کاربر: 2")

    def test_state_trim_is_last_ten(self):
        messages = [{"role": "user", "content": str(index)} for index in range(12)]
        self.assertEqual(trim_agent_messages(messages)[0]["content"], "2")

    def test_turn_two_and_three_reconstruct_generated_answers_in_order(self):
        prior = [
            {"raw_query": "Q1", "actual_answer": "A1"},
            {"raw_query": "Q2", "actual_answer": "A2"},
        ]
        self.assertEqual(messages_from_turn_records(prior[:1]), [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ])
        self.assertEqual(messages_from_turn_records(prior), [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ])

    def test_client_only_fallback_is_not_synthesized_into_history(self):
        turns = [{
            "raw_query": "Q1",
            "actual_answer": "client fallback",
            "metadata": {
                "agent_state_after": {
                    "messages": [{"role": "user", "content": "Q1"}],
                }
            },
        }]
        self.assertEqual(
            exact_messages_from_turns(turns),
            [{"role": "user", "content": "Q1"}],
        )


class CoreParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_evaluation_policy_rejects_production_history_before_lookup(self):
        production = HistoryProvider("production", [])
        service = AnsweringService(
            agent_service=Agent(), intent_classifier=Classifier(),
            history_rewriting_service=Rewriter(), text_processor=Processor(),
            blocking_runner=ImmediateRunner(), category_resolver=lambda _doc: "FAQ",
        )
        with self.assertRaisesRegex(
            RuntimeError, "EVALUATION_PRODUCTION_HISTORY_FORBIDDEN"
        ):
            await service.answer(
                AnswerRequestContext(
                    original_query="Q",
                    selected_documents=("General_FAQ",),
            conversation_key="REAL_LOOKING_SESSION_12345",
                    session_id=None,
                ),
                history_provider=production,
                execution_policy=EVALUATION_EXECUTION_POLICY,
            )
        self.assertEqual(production.keys, [])

    async def test_production_and_evaluation_use_same_executor_dependencies(self):
        agent = Agent()
        service = AnsweringService(
            agent_service=agent, intent_classifier=Classifier(),
            history_rewriting_service=Rewriter(), text_processor=Processor(),
            blocking_runner=ImmediateRunner(), category_resolver=lambda _doc: "FAQ",
        )
        messages = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        production = HistoryProvider("production", messages)
        evaluation = HistoryProvider("evaluation", messages)
        source_session_id = "REAL_LOOKING_SESSION_12345"
        evaluation_key = object()
        common = AnswerRequestContext(
            original_query="Q2", selected_documents=("General_FAQ",),
            session_id=source_session_id,
        )
        production_result = await service.answer(common, history_provider=production)
        evaluation_result = await service.answer(
            AnswerRequestContext(
                original_query="Q2", selected_documents=("General_FAQ",),
                conversation_key=evaluation_key, session_id=None,
            ),
            history_provider=evaluation,
            execution_policy=EVALUATION_EXECUTION_POLICY,
        )
        self.assertEqual(production_result.rewritten_query, evaluation_result.rewritten_query)
        self.assertEqual(production.keys, [source_session_id])
        self.assertEqual(evaluation.keys, [evaluation_key])
        self.assertNotIn(source_session_id, evaluation.keys)
        self.assertEqual(agent.calls[0]["retrieval_query"], agent.calls[1]["retrieval_query"])
        self.assertIs(agent.calls[1]["execution_policy"], EVALUATION_EXECUTION_POLICY)
        self.assertEqual(production_result.intent_details["confidence"], 0.91)
        self.assertEqual(evaluation_result.intent_details["confidence"], 0.91)


if __name__ == "__main__":
    unittest.main()
