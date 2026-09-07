from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from answering_service import AnswerRequestContext, AnsweringService
from conversation_history import NO_CONVERSATION_HISTORY, format_rewrite_history
from evaluation_system.backend.app.services.config_snapshot import (
    build_config_snapshot,
)
from pipeline_observer import PipelineStage, bind_pipeline_observer
from scripts.validate_environment import parse_env_file
from utils.persian_hybrid_search import PersianHybridSearch
import utils.retrieval_query_canonicalizer as canonicalizer_module
from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query


ROOT = Path(__file__).resolve().parents[1]


class _ImmediateRunner:
    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class _Processor:
    def normalize(self, value):
        return str(value).strip()


class _Classifier:
    threshold = 0.5

    def __init__(self, intent="general"):
        self.intent = intent
        self.queries = []

    async def classify_detailed(self, query):
        self.queries.append(query)
        return {
            "type": self.intent,
            "scenario_id": None,
            "probability_actionable": 0.9,
            "probability_chitchat": 0.1,
        }


class _Rewriter:
    def __init__(self, history=NO_CONVERSATION_HISTORY, result="بازنویسی نهایی"):
        self.history = history
        self.result = result
        self.rewrite_calls = []

    def get_formatted_history_string(self, **_kwargs):
        return self.history

    async def rewrite_query(self, **kwargs):
        self.rewrite_calls.append(kwargs)
        return self.result


class _Agent:
    def __init__(self):
        self.calls = []

    async def process_stateless_message(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            answer="پاسخ",
            state={"messages": [], "related_questions": []},
        )

    async def process_message_detailed(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            answer="پاسخ",
            state={"messages": [], "related_questions": []},
        )


class _Observer:
    def __init__(self):
        self.records = []

    def record(self, result):
        self.records.append(result)


def _service(*, classifier=None, rewriter=None):
    agent = _Agent()
    classifier = classifier or _Classifier()
    rewriter = rewriter or _Rewriter()
    return (
        AnsweringService(
            agent_service=agent,
            intent_classifier=classifier,
            history_rewriting_service=rewriter,
            text_processor=_Processor(),
            blocking_runner=_ImmediateRunner(),
            category_resolver=lambda _document: "FAQ",
        ),
        agent,
        classifier,
        rewriter,
    )


class RetrievalQueryAliasTests(unittest.TestCase):
    def test_only_active_approved_aliases_are_applied(self):
        self.assertEqual(
            canonicalize_retrieval_query("اس ام اس رمز پویا نمیاد"),
            "پیامک رمز پویا نمیاد",
        )
        self.assertEqual(canonicalize_retrieval_query("رمزم خرابه"), "رمز من خرابه")
        self.assertEqual(
            canonicalize_retrieval_query("انگشتم کار نمیکنه"),
            "اثر انگشت من سنسور زیستی کار نمیکنه",
        )
        expected_existing_slang = {
            "رمزمو بگو": "رمز من رو بگو",
            "قسطمو بده": "قسط م رو بده",
            "واممو ببین": "وام من رو ببین",
            "حسابمو باز کن": "حساب من رو باز کن",
            "کارتش خرابه": "کارت اش رو خرابه",
        }
        for query, expected in expected_existing_slang.items():
            with self.subTest(query=query):
                self.assertEqual(canonicalize_retrieval_query(query), expected)

    def test_unapproved_inputs_are_preserved(self):
        unchanged = (
            "روش افتتاح حساب چیست",
            "واژهناشناخته",
            "ژغکپ",
            "شناسه ABC-123 در https://example.com/path",
        )
        for query in unchanged:
            with self.subTest(query=query):
                self.assertEqual(canonicalize_retrieval_query(query), query)

    def test_disabled_policy_returns_input_unchanged(self):
        query = "اس ام اس رمز پویا نمیاد"
        disabled = SimpleNamespace(rag_query_canonicalization_enabled=False)
        with mock.patch.object(
            canonicalizer_module, "PERFORMANCE_SETTINGS", disabled
        ):
            self.assertEqual(canonicalize_retrieval_query(query), query)


class QueryPreparationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_standalone_query_is_canonicalized_after_intent_without_rewrite(self):
        service, agent, classifier, rewriter = _service()
        observer = _Observer()
        result = await service.answer(
            AnswerRequestContext(
                original_query="اس ام اس رمز پویا نمیاد",
                selected_documents=("General_FAQ",),
                use_history=False,
                persist_agent_state=False,
            ),
            observer=observer,
        )

        self.assertEqual(classifier.queries, ["اس ام اس رمز پویا نمیاد"])
        self.assertEqual(result.normalized_query, "اس ام اس رمز پویا نمیاد")
        self.assertEqual(result.canonical_retrieval_query, "پیامک رمز پویا نمیاد")
        self.assertEqual(result.final_retrieval_query, "پیامک رمز پویا نمیاد")
        self.assertEqual(agent.calls[0]["retrieval_query"], result.final_retrieval_query)
        self.assertEqual(rewriter.rewrite_calls, [])
        rewrite = next(item for item in observer.records if item.stage is PipelineStage.REWRITE)
        normalization = next(
            item for item in observer.records
            if item.stage is PipelineStage.NORMALIZATION
        )
        self.assertEqual(
            normalization.output_data["normalized_query"],
            result.normalized_query,
        )
        self.assertFalse(rewrite.metrics["rewrite_used"])
        self.assertEqual(
            rewrite.output_data["classification_query"],
            result.normalized_query,
        )

    async def test_empty_history_does_not_invoke_rewriter(self):
        rewriter = _Rewriter(history=NO_CONVERSATION_HISTORY)
        service, agent, _classifier, rewriter = _service(rewriter=rewriter)
        result = await service.answer(
            AnswerRequestContext(
                original_query="رمزم خرابه",
                selected_documents=("General_FAQ",),
                session_id="7",
            )
        )

        self.assertEqual(rewriter.rewrite_calls, [])
        self.assertEqual(result.final_retrieval_query, "رمز من خرابه")
        self.assertEqual(agent.calls[0]["retrieval_query"], "رمز من خرابه")

    async def test_history_rewriter_precedes_classification_and_canonicalization(self):
        rewriter = _Rewriter(
            history="User: پرسش قبلی",
            result="اس ام اس نمیاد",
        )
        service, agent, classifier, rewriter = _service(rewriter=rewriter)
        result = await service.answer(
            AnswerRequestContext(
                original_query="رمزم خرابه",
                selected_documents=("General_FAQ",),
                session_id="7",
            )
        )

        self.assertEqual(classifier.queries, ["اس ام اس نمیاد"])
        self.assertEqual(
            rewriter.rewrite_calls[0]["current_query"], "رمزم خرابه"
        )
        self.assertEqual(result.rewritten_query, "اس ام اس نمیاد")
        self.assertEqual(result.canonical_retrieval_query, "پیامک نمیاد")
        self.assertEqual(result.final_retrieval_query, "پیامک نمیاد")
        self.assertEqual(agent.calls[0]["retrieval_query"], "پیامک نمیاد")

    async def test_chitchat_is_not_canonicalized(self):
        classifier = _Classifier(intent="chitchat")
        service, agent, classifier, rewriter = _service(classifier=classifier)
        result = await service.answer(
            AnswerRequestContext(
                original_query="اس ام اس",
                session_id="7",
            )
        )

        self.assertEqual(classifier.queries, ["اس ام اس"])
        self.assertEqual(result.canonical_retrieval_query, "اس ام اس")
        self.assertEqual(agent.calls[0]["retrieval_query"], "اس ام اس")
        self.assertEqual(rewriter.rewrite_calls, [])


class SearchAndHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_consumes_supplied_query_without_alias_expansion(self):
        search = PersianHybridSearch.__new__(PersianHybridSearch)
        search._blocking_runner = _ImmediateRunner()
        captured = {}
        search._get_or_build_bm25 = lambda _docs: (
            object(),
            ["chunk-1"],
            {"chunk-1": {"text": "content", "document_name": "General_FAQ"}},
        )

        def process(query):
            captured["bm25"] = query
            return [query]

        def normalise(query):
            captured["semantic_input"] = query
            return query

        async def semantic(query, _docs, top_k):
            captured["semantic"] = query
            captured["top_k"] = top_k
            return {"chunk-1": 1.0}

        search._process_query = process
        search._normalise_query = normalise
        search._score_bm25 = lambda _bm25, _ids, _tokens: (
            np.array([1.0]),
            [("chunk-1", 1.0)],
        )
        search._semantic_search = semantic

        query = "اس ام اس بدون تغییر دوم"
        observer = _Observer()
        with bind_pipeline_observer(observer):
            await search.search(query, top_k=50, allowed_docs=["General_FAQ"])

        self.assertEqual(captured["bm25"], query)
        self.assertEqual(captured["semantic_input"], query)
        self.assertEqual(captured["semantic"], query)
        retrieval = next(
            item for item in observer.records
            if item.stage is PipelineStage.RETRIEVAL
        )
        self.assertEqual(retrieval.input_data["retrieval_query"], query)
        self.assertFalse(hasattr(PersianHybridSearch, "_expand_query_intent"))
        self.assertNotIn(
            "canonicalize_retrieval_query",
            inspect.getsource(PersianHybridSearch.search),
        )
        self.assertIn(
            "apply_document_overrides=False",
            inspect.getsource(PersianHybridSearch._process_query),
        )

    async def test_repeated_nonadjacent_messages_and_chronology_are_preserved(self):
        messages = [
            {"role": "user", "content": "بله"},
            {"role": "assistant", "content": "ادامه می‌دهم"},
            {"role": "user", "content": "بله"},
        ]
        self.assertEqual(
            format_rewrite_history(messages),
            "User: بله\nAI: ادامه می‌دهم\nUser: بله",
        )
        self.assertEqual(
            format_rewrite_history([
                {"role": "assistant", "content": "ابتدا"},
                {"role": "user", "content": "سپس"},
            ]),
            "AI: ابتدا\nUser: سپس",
        )


class SharedPathAndEnvironmentTests(unittest.TestCase):
    def test_all_interfaces_use_shared_answering_service(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        mobile = (ROOT / "mobile_api.py").read_text(encoding="utf-8")
        mass = (ROOT / "mass_answer_service.py").read_text(encoding="utf-8")
        evaluation = (
            ROOT / "evaluation_system/backend/app/core_adapter/runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn("AnsweringService(", main)
        self.assertIn("answering_service.answer(", mobile)
        self.assertIn("self.answering_service.answer(", mass)
        self.assertIn("AnsweringService(", evaluation)

    def test_dev_production_and_example_enable_same_policy(self):
        values = [
            parse_env_file(ROOT / name).values[
                "RAG_QUERY_CANONICALIZATION_ENABLED"
            ].lower()
            for name in (".env", "Production_ENV", ".env.example.generated")
        ]
        self.assertEqual(values, ["true", "true", "true"])
        dev_keys = set(parse_env_file(ROOT / ".env").values)
        production_keys = set(parse_env_file(ROOT / "Production_ENV").values)
        self.assertFalse(dev_keys - production_keys)

    def test_config_snapshot_identifies_alias_policy(self):
        policy = build_config_snapshot()["query_canonicalization"]
        self.assertTrue(policy["RAG_QUERY_CANONICALIZATION_ENABLED"])
        self.assertEqual(
            policy["artifact_basename"], "retrieval_query_aliases.json"
        )
        self.assertEqual(policy["schema_version"], 1)
        self.assertEqual(len(policy["artifact_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
