from __future__ import annotations

import unittest
from types import SimpleNamespace

from answering_service import AnswerRequestContext, AnsweringService


class ImmediateRunner:
    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class Processor:
    def normalize(self, value):
        return str(value).strip().replace("ي", "ی")


class Classifier:
    def __init__(self, intent="general"):
        self.intent = intent
        self.queries = []

    async def classify(self, query):
        self.queries.append(query)
        return {"type": self.intent, "scenario_id": None}


class Rewriter:
    def __init__(self):
        self.history_calls = []
        self.rewrite_calls = []

    def get_formatted_history_string(self, **kwargs):
        self.history_calls.append(kwargs)
        return "User: قبلی"

    async def rewrite_query(self, **kwargs):
        self.rewrite_calls.append(kwargs)
        return "بازنویسی"


class Agent:
    def __init__(self):
        self.persisted = []
        self.stateless = []

    async def process_message_detailed(self, **kwargs):
        self.persisted.append(kwargs)
        return SimpleNamespace(
            answer="پاسخ",
            state={"related_questions": [{"question": "مرتبط"}], "feedback_needed": True},
        )

    async def process_stateless_message(self, **kwargs):
        self.stateless.append(kwargs)
        return SimpleNamespace(
            answer="پاسخ",
            state={"related_questions": [], "feedback_needed": True},
        )


class AnsweringServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, intent="general", selection_validator=None):
        self.classifier = Classifier(intent)
        self.rewriter = Rewriter()
        self.agent = Agent()
        return AnsweringService(
            agent_service=self.agent,
            intent_classifier=self.classifier,
            history_rewriting_service=self.rewriter,
            text_processor=Processor(),
            blocking_runner=ImmediateRunner(),
            category_resolver=lambda _document: "FAQ",
            selection_validator=selection_validator,
        )

    async def test_online_turn_classifies_once_and_uses_rewrite(self):
        service = self.make_service()
        result = await service.answer(
            AnswerRequestContext(
                original_query="  يک سوال  ",
                selected_documents=("General_FAQ",),
                session_id="12",
            )
        )

        self.assertEqual(self.classifier.queries, ["یک سوال"])
        self.assertEqual(len(self.rewriter.history_calls), 1)
        self.assertEqual(len(self.rewriter.rewrite_calls), 1)
        self.assertEqual(len(self.agent.persisted), 1)
        self.assertEqual(self.agent.persisted[0]["user_message"], "يک سوال")
        self.assertEqual(self.agent.persisted[0]["retrieval_query"], "بازنویسی")
        self.assertEqual(result.answer, "پاسخ")
        self.assertTrue(result.feedback_needed)

    async def test_chitchat_skips_history_and_rewrite(self):
        service = self.make_service(intent="chitchat")
        await service.answer(
            AnswerRequestContext(original_query="سلام", session_id="12")
        )
        self.assertEqual(self.rewriter.history_calls, [])
        self.assertEqual(self.rewriter.rewrite_calls, [])
        self.assertEqual(self.agent.persisted[0]["retrieval_query"], "سلام")

    async def test_batch_turn_is_stateless_and_has_no_history(self):
        service = self.make_service()
        result = await service.answer(
            AnswerRequestContext(
                original_query="سوال مستقل",
                selected_documents=("General_FAQ",),
                channel="mass_answer",
                use_history=False,
                persist_agent_state=False,
                include_related_questions=False,
            )
        )
        self.assertEqual(self.rewriter.history_calls, [])
        self.assertEqual(self.agent.persisted, [])
        self.assertEqual(len(self.agent.stateless), 1)
        self.assertEqual(result.related_questions, [])

    async def test_empty_query_is_rejected_before_model_work(self):
        service = self.make_service()
        with self.assertRaisesRegex(ValueError, "query is empty"):
            await service.answer(AnswerRequestContext(original_query="   "))
        self.assertEqual(self.classifier.queries, [])

    async def test_stale_document_selection_is_discarded_and_rejected(self):
        service = self.make_service(
            selection_validator=lambda documents: [
                document for document in documents if document == "current"
            ]
        )
        with self.assertRaisesRegex(ValueError, "current datasource"):
            await service.answer(
                AnswerRequestContext(
                    original_query="knowledge question",
                    selected_documents=("General_FAQ",),
                    session_id="12",
                )
            )
        self.assertEqual(self.agent.persisted, [])

    async def test_selection_validator_passes_only_current_documents(self):
        service = self.make_service(
            selection_validator=lambda _documents: ["current"]
        )
        await service.answer(
            AnswerRequestContext(
                original_query="knowledge question",
                selected_documents=("General_FAQ", "current"),
                session_id="12",
            )
        )
        self.assertEqual(self.agent.persisted[0]["selected_docs"], ["current"])

    async def test_online_and_batch_feed_equivalent_fresh_turn_inputs_to_graph(self):
        service = self.make_service()
        self.rewriter.get_formatted_history_string = lambda **_kwargs: (
            "[بدون مکالمه قبلی]"
        )
        self.rewriter.rewrite_query = lambda **kwargs: _async_value(
            kwargs["current_query"]
        )
        await service.answer(
            AnswerRequestContext(
                original_query="سؤال یکسان",
                selected_documents=("General_FAQ",),
                session_id="12",
                channel="web",
            )
        )
        await service.answer(
            AnswerRequestContext(
                original_query="سؤال یکسان",
                selected_documents=("General_FAQ",),
                channel="mass_answer",
                use_history=False,
                persist_agent_state=False,
            )
        )
        online = self.agent.persisted[0]
        batch = self.agent.stateless[0]
        for key in (
            "user_message", "selected_docs", "retrieval_query",
            "preclassified_intent", "doc_category",
        ):
            self.assertEqual(online[key], batch[key])

    async def test_rewrite_output_is_canonicalized_before_retrieval(self):
        service = self.make_service()
        self.rewriter.rewrite_query = lambda **_kwargs: _async_value(
            "میشه اسم حساب ها رو بگی"
        )
        result = await service.answer(
            AnswerRequestContext(
                original_query="میشه اسم حساب‌ها رو بگی",
                selected_documents=("General_FAQ",),
                session_id="12",
            )
        )

        self.assertEqual(result.normalized_query, "میشه اسم حساب هارو بگی")
        self.assertEqual(result.rewritten_query, "میشه اسم حساب هارو بگی")
        self.assertEqual(
            self.agent.persisted[0]["retrieval_query"],
            "میشه اسم حساب هارو بگی",
        )


async def _async_value(value):
    return value


if __name__ == "__main__":
    unittest.main()
