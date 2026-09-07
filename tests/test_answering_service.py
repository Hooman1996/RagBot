from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from answering_service import AnswerRequestContext, AnsweringService
from conversation_history import NO_CONVERSATION_HISTORY
from pipeline_observer import (
    PipelineStage,
    PipelineStageResult,
    emit_pipeline_stage_lazy,
)


class ImmediateRunner:
    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class Processor:
    def normalize(self, value):
        return str(value).strip().replace("ي", "ی")


class Classifier:
    def __init__(self, intent="general", events=None):
        self.intent = intent
        self.queries = []
        self.events = events

    async def classify(self, query):
        self.queries.append(query)
        if self.events is not None:
            self.events.append(("classify", query))
        return {"type": self.intent, "scenario_id": None}


class Rewriter:
    def __init__(
        self,
        history="User: قبلی",
        result="بازنویسی",
        events=None,
        emit_rewrite_stage=False,
    ):
        self.history = history
        self.result = result
        self.events = events
        self.emit_rewrite_stage = emit_rewrite_stage
        self.history_calls = []
        self.rewrite_calls = []

    def get_formatted_history_string(self, **kwargs):
        self.history_calls.append(kwargs)
        if self.events is not None:
            self.events.append(("history", kwargs.get("current_chat_id")))
        return self.history

    async def rewrite_query(self, **kwargs):
        self.rewrite_calls.append(kwargs)
        if self.events is not None:
            self.events.append(("rewrite", kwargs["current_query"]))
        if self.emit_rewrite_stage:
            emit_pipeline_stage_lazy(lambda: PipelineStageResult(
                stage=PipelineStage.REWRITE,
                input_data={"original_query": kwargs["current_query"]},
                output_data={"rewritten_query": self.result},
            ))
        return self.result


class HistoryProvider:
    namespace = "test"

    def __init__(self, messages, events=None):
        self.messages = messages
        self.events = events
        self.keys = []

    async def load_rewrite_messages(self, conversation_key):
        self.keys.append(conversation_key)
        if self.events is not None:
            self.events.append(("history", conversation_key))
        return self.messages


class Agent:
    def __init__(self, events=None):
        self.events = events
        self.persisted = []
        self.stateless = []
        self.general_calls = []
        self.chitchat_calls = []

    def _record_route(self, kwargs):
        intent = kwargs["preclassified_intent"]["type"]
        target = self.chitchat_calls if intent == "chitchat" else self.general_calls
        target.append(kwargs["retrieval_query"])
        if self.events is not None:
            self.events.append(("retrieval", kwargs["retrieval_query"]))

    async def process_message_detailed(self, **kwargs):
        self.persisted.append(kwargs)
        self._record_route(kwargs)
        return SimpleNamespace(
            answer="پاسخ",
            state={"related_questions": [{"question": "مرتبط"}], "feedback_needed": True},
        )

    async def process_stateless_message(self, **kwargs):
        self.stateless.append(kwargs)
        self._record_route(kwargs)
        return SimpleNamespace(
            answer="پاسخ",
            state={"related_questions": [], "feedback_needed": True},
        )


class Observer:
    def __init__(self):
        self.records = []

    def record(self, result):
        self.records.append(result)


class AnsweringServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_service(
        self,
        intent="general",
        selection_validator=None,
        *,
        classifier=None,
        rewriter=None,
        agent=None,
        history_provider=None,
    ):
        self.classifier = classifier or Classifier(intent)
        self.rewriter = rewriter or Rewriter()
        self.agent = agent or Agent()
        return AnsweringService(
            agent_service=self.agent,
            intent_classifier=self.classifier,
            history_rewriting_service=self.rewriter,
            text_processor=Processor(),
            blocking_runner=ImmediateRunner(),
            category_resolver=lambda _document: "FAQ",
            selection_validator=selection_validator,
            history_provider=history_provider,
        )

    async def test_online_turn_rewrites_before_single_classification(self):
        service = self.make_service()
        result = await service.answer(
            AnswerRequestContext(
                original_query="  يک سوال  ",
                selected_documents=("General_FAQ",),
                session_id="12",
            )
        )

        self.assertEqual(self.classifier.queries, ["بازنویسی"])
        self.assertEqual(len(self.rewriter.history_calls), 1)
        self.assertEqual(len(self.rewriter.rewrite_calls), 1)
        self.assertEqual(len(self.agent.persisted), 1)
        self.assertEqual(self.agent.persisted[0]["user_message"], "يک سوال")
        self.assertEqual(self.agent.persisted[0]["retrieval_query"], "بازنویسی")
        self.assertEqual(result.answer, "پاسخ")
        self.assertTrue(result.feedback_needed)

    async def test_chitchat_after_history_is_rewritten_then_skips_retrieval(self):
        service = self.make_service(intent="chitchat")
        await service.answer(
            AnswerRequestContext(original_query="خیلی ممنون", session_id="12")
        )
        self.assertEqual(len(self.rewriter.history_calls), 1)
        self.assertEqual(len(self.rewriter.rewrite_calls), 1)
        self.assertEqual(self.classifier.queries, ["بازنویسی"])
        self.assertEqual(self.agent.general_calls, [])
        self.assertEqual(self.agent.chitchat_calls, ["بازنویسی"])

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
        self.assertEqual(self.rewriter.rewrite_calls, [])
        self.assertEqual(self.classifier.queries, ["سوال مستقل"])
        self.assertEqual(self.agent.persisted, [])
        self.assertEqual(len(self.agent.stateless), 1)
        self.assertEqual(result.related_questions, [])

    async def test_contextual_banking_ellipsis_uses_rewrite_for_intent_and_retrieval(self):
        events = []
        rewritten = "تاریخ انقضای کارتم را چطور ببینم؟"
        provider = HistoryProvider([
            {"role": "user", "content": "cvv2 کارتمو چجوری ببینم؟"},
            {"role": "assistant", "content": "پاسخ درباره CVV2 کارت"},
        ], events)
        rewriter = Rewriter(result=rewritten, events=events)
        classifier = Classifier(events=events)
        agent = Agent(events=events)
        service = self.make_service(
            classifier=classifier,
            rewriter=rewriter,
            agent=agent,
            history_provider=provider,
        )

        def canonicalize(query):
            events.append(("canonicalize", query))
            return f"canonical:{query}"

        with mock.patch(
            "answering_service.canonicalize_retrieval_query",
            side_effect=canonicalize,
        ):
            result = await service.answer(AnswerRequestContext(
                original_query="انقضا چی",
                selected_documents=("General_FAQ",),
                session_id="12",
            ))

        self.assertEqual(provider.keys, ["12"])
        self.assertEqual(
            rewriter.rewrite_calls,
            [{
                "current_query": "انقضا چی",
                "current_summary": (
                    "User: cvv2 کارتمو چجوری ببینم؟\n"
                    "AI: پاسخ درباره CVV2 کارت"
                ),
            }],
        )
        self.assertEqual(classifier.queries, [rewritten])
        self.assertEqual(agent.chitchat_calls, [])
        self.assertEqual(agent.general_calls, [f"canonical:{rewritten}"])
        self.assertEqual(result.rewritten_query, rewritten)
        self.assertEqual(result.canonical_retrieval_query, f"canonical:{rewritten}")
        self.assertEqual(result.final_retrieval_query, f"canonical:{rewritten}")
        self.assertEqual(
            [name for name, _value in events],
            ["history", "rewrite", "classify", "canonicalize", "retrieval"],
        )

    async def test_contextual_banking_followup_is_classified_once_after_rewrite(self):
        rewritten = "فعال‌سازی رمز پویا برای کارت دوم هم امکان‌پذیر است؟"
        provider = HistoryProvider([
            {"role": "user", "content": "رمز پویا چطور فعال میشه؟"},
            {"role": "assistant", "content": "پاسخ فعال‌سازی"},
        ])
        service = self.make_service(
            rewriter=Rewriter(result=rewritten),
            history_provider=provider,
        )
        result = await service.answer(AnswerRequestContext(
            original_query="برای کارت دوم چی؟",
            selected_documents=("General_FAQ",),
            session_id="12",
        ))

        self.assertEqual(self.classifier.queries, [rewritten])
        self.assertEqual(len(self.rewriter.rewrite_calls), 1)
        self.assertEqual(result.intent, "general")

    async def test_contextual_chitchat_is_preserved_and_classified_once(self):
        query = "خیلی ممنون"
        observer = Observer()
        provider = HistoryProvider([
            {"role": "user", "content": "شرایط وام چیست؟"},
            {"role": "assistant", "content": "پاسخ شرایط وام"},
        ])
        service = self.make_service(
            intent="chitchat",
            rewriter=Rewriter(result=query, emit_rewrite_stage=True),
            history_provider=provider,
        )
        result = await service.answer(AnswerRequestContext(
            original_query=query,
            session_id="12",
        ), observer=observer)

        self.assertEqual(len(self.rewriter.rewrite_calls), 1)
        self.assertEqual(self.classifier.queries, [query])
        self.assertEqual(result.intent, "chitchat")
        self.assertEqual(self.agent.general_calls, [])
        self.assertEqual(self.agent.chitchat_calls, [query])
        self.assertEqual(
            [record.stage for record in observer.records],
            [
                PipelineStage.NORMALIZATION,
                PipelineStage.HISTORY,
                PipelineStage.REWRITE,
                PipelineStage.INTENT,
                PipelineStage.RETRIEVAL,
                PipelineStage.RERANK,
                PipelineStage.CONTEXT_SELECTION,
            ],
        )
        for record in observer.records[-3:]:
            self.assertEqual(record.status, "SKIPPED")

    async def test_standalone_topic_switch_is_preserved_by_history_rewriter(self):
        query = "چطور چک صیادی ثبت کنم؟"
        provider = HistoryProvider([
            {"role": "user", "content": "شرایط وام چیست؟"},
            {"role": "assistant", "content": "پاسخ شرایط وام"},
        ])
        service = self.make_service(
            rewriter=Rewriter(result=query),
            history_provider=provider,
        )
        result = await service.answer(AnswerRequestContext(
            original_query=query,
            selected_documents=("General_FAQ",),
            session_id="12",
        ))

        self.assertEqual(len(self.rewriter.rewrite_calls), 1)
        self.assertEqual(self.classifier.queries, [query])
        self.assertEqual(result.intent, "general")
        self.assertEqual(self.agent.general_calls, [query])

    async def test_no_prior_history_skips_rewrite_and_classifies_normalized_query(self):
        query = "چطور رمز پویا را فعال کنم؟"
        provider = HistoryProvider([])
        service = self.make_service(
            rewriter=Rewriter(history=NO_CONVERSATION_HISTORY),
            history_provider=provider,
        )
        result = await service.answer(AnswerRequestContext(
            original_query=query,
            selected_documents=("General_FAQ",),
            session_id="12",
        ))

        self.assertEqual(provider.keys, ["12"])
        self.assertEqual(self.rewriter.rewrite_calls, [])
        self.assertEqual(self.classifier.queries, [query])
        self.assertEqual(result.rewritten_query, query)
        self.assertEqual(self.agent.general_calls, [result.canonical_retrieval_query])

    async def test_history_disabled_does_not_read_or_rewrite(self):
        query = "چطور رمز پویا را فعال کنم؟"
        provider = HistoryProvider([
            {"role": "user", "content": "پیام قبلی"},
        ])
        service = self.make_service(history_provider=provider)
        await service.answer(AnswerRequestContext(
            original_query=query,
            selected_documents=("General_FAQ",),
            use_history=False,
            persist_agent_state=False,
        ))

        self.assertEqual(provider.keys, [])
        self.assertEqual(self.rewriter.history_calls, [])
        self.assertEqual(self.rewriter.rewrite_calls, [])
        self.assertEqual(self.classifier.queries, [query])
        self.assertEqual(len(self.agent.stateless), 1)

    async def test_empty_rewrite_falls_back_to_nonempty_normalized_query(self):
        provider = HistoryProvider([
            {"role": "user", "content": "شرایط وام چیست؟"},
        ])
        service = self.make_service(
            rewriter=Rewriter(result="  \n "),
            history_provider=provider,
        )
        result = await service.answer(AnswerRequestContext(
            original_query="انقضا چی",
            selected_documents=("General_FAQ",),
            session_id="12",
        ))

        self.assertEqual(len(self.rewriter.rewrite_calls), 1)
        self.assertEqual(self.classifier.queries, ["انقضا چی"])
        self.assertEqual(result.rewritten_query, "انقضا چی")
        self.assertTrue(result.final_retrieval_query)
        self.assertEqual(self.agent.general_calls, [result.final_retrieval_query])

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
        self.assertEqual(self.classifier.queries, ["میشه اسم حساب هارو بگی"])
        self.assertEqual(
            self.agent.persisted[0]["retrieval_query"],
            "میشه اسم حساب هارو بگی",
        )

    async def test_preclassified_intent_is_passed_to_graph_once(self):
        service = self.make_service()
        await service.answer(AnswerRequestContext(
            original_query="سوال مستقل",
            selected_documents=("General_FAQ",),
            use_history=False,
            persist_agent_state=False,
        ))

        self.assertEqual(self.classifier.queries, ["سوال مستقل"])
        self.assertEqual(
            self.agent.stateless[0]["preclassified_intent"],
            {"type": "general", "scenario_id": None},
        )


async def _async_value(value):
    return value


if __name__ == "__main__":
    unittest.main()
