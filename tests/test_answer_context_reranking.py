from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from pipeline_observer import (
    PipelineStage,
    TerminalPipelineObserver,
    bind_pipeline_observer,
)
from utils.performance_config import PipelineDebugSettings
from utils.rag_utils import (
    build_faq_rerank_text,
    parse_faq_relevance_fields,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKBOOK_QUESTION = "چگونه می توانم درخواست صدور دسته چک ثبت کنم؟"
CHECKBOOK_ANSWER = "کاربر گرامی درخواست دسته چک کاغذی..."
CHECKBOOK_CONTENT = (
    f"question : {CHECKBOOK_QUESTION}\n"
    f"answer : {CHECKBOOK_ANSWER}\n"
    "ادامه پاسخ که نباید به مدل بازرتبه‌بندی ارسال شود\n"
    "question category : ثبت چک. sub_category : درخواست دسته چک"
)
CHECKBOOK_RERANK_TEXT = (
    f"سوال: {CHECKBOOK_QUESTION}\n"
    "دسته‌بندی: ثبت چک\n"
    "زیردسته: درخواست دسته چک"
)


class ModulePatch:
    def __init__(self, replacements):
        self.replacements = replacements
        self.previous = {}

    def __enter__(self):
        for name, module in self.replacements.items():
            self.previous[name] = sys.modules.get(name)
            sys.modules[name] = module
        return self

    def __exit__(self, exc_type, exc, traceback):
        for name, previous in self.previous.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FaqRerankTextTests(unittest.TestCase):
    def test_extracts_question_main_category_and_subcategory(self):
        self.assertEqual(
            parse_faq_relevance_fields(CHECKBOOK_CONTENT),
            {
                "question": CHECKBOOK_QUESTION,
                "main_category": "ثبت چک",
                "sub_category": "درخواست دسته چک",
            },
        )

    def test_category_without_subcategory(self):
        content = (
            "answer : پاسخ قدیمی"
            "question category: خدمات حساب."
        )
        self.assertEqual(
            parse_faq_relevance_fields(content),
            {
                "question": "",
                "main_category": "خدمات حساب",
                "sub_category": "",
            },
        )
        self.assertEqual(
            build_faq_rerank_text(content),
            "دسته‌بندی: خدمات حساب",
        )

    def test_question_only(self):
        content = "question: شرایط افتتاح حساب چیست؟"
        self.assertEqual(
            build_faq_rerank_text(content),
            "سوال: شرایط افتتاح حساب چیست؟",
        )

    def test_unrecognized_content_falls_back_to_normalized_full_content(self):
        content = "متن آزاد  با فاصله‏های نامنظم"
        fields = parse_faq_relevance_fields(content)
        self.assertEqual(
            fields,
            {"question": "", "main_category": "", "sub_category": ""},
        )
        self.assertEqual(
            build_faq_rerank_text(content),
            "متن آزاد با فاصله‌های نامنظم",
        )

    def test_multiline_answer_never_leaks_into_structured_rerank_text(self):
        rerank_text = build_faq_rerank_text(CHECKBOOK_CONTENT)
        self.assertEqual(rerank_text, CHECKBOOK_RERANK_TEXT)
        self.assertNotIn(CHECKBOOK_ANSWER, rerank_text)
        self.assertNotIn("ادامه پاسخ", rerank_text)


class Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class RecordingHttp:
    def __init__(self, rankings):
        self.rankings = rankings
        self.calls = []

    async def post(self, url, json):
        self.calls.append((url, json))
        return Response(self.rankings)


class CollectingObserver:
    pipeline_hashes_enabled = False

    def __init__(self):
        self.records = []

    def record(self, result):
        self.records.append(result)


class AnswerContextRerankTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        numpy = types.ModuleType("numpy")
        numpy.ndarray = object
        parsivar = types.ModuleType("parsivar")
        parsivar.Normalizer = parsivar.Tokenizer = parsivar.FindStems = object
        rank_bm25 = types.ModuleType("rank_bm25")
        rank_bm25.BM25Okapi = object
        qdrant_client = types.ModuleType("qdrant_client")
        qdrant_client.QdrantClient = object
        qdrant_http = types.ModuleType("qdrant_client.http")
        qdrant_http.models = types.SimpleNamespace()
        qdrant_client.http = qdrant_http
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        self.patch = ModulePatch(
            {
                "numpy": numpy,
                "parsivar": parsivar,
                "rank_bm25": rank_bm25,
                "qdrant_client": qdrant_client,
                "qdrant_client.http": qdrant_http,
                "dotenv": dotenv,
            }
        )
        self.patch.__enter__()
        self.module_name = "answer_context_search_under_test"
        self.module = load_module(
            self.module_name, ROOT / "utils/persian_hybrid_search.py"
        )

    async def asyncTearDown(self):
        self.patch.__exit__(None, None, None)
        sys.modules.pop(self.module_name, None)

    def make_search(self, rankings):
        search = self.module.PersianHybridSearch.__new__(
            self.module.PersianHybridSearch
        )
        search._closed = False
        search._http = RecordingHttp(rankings)
        search.tei_rerank_url = "http://reranker.test"
        search._tei_reranker_active = 0
        search._tei_pool_timeout_total = 0
        return search

    def make_result(self, index, *, content=None, rank=None):
        numeric_index = int(index) if str(index).isdigit() else 0
        return self.module.SearchResult(
            doc_id=str(index),
            content=content or (
                f"question : پرسش {index}\nanswer : پاسخ بلند {index}\n"
                f"question category : دسته {index}. sub_category : زیردسته {index}"
            ),
            score=1.0 / (numeric_index + 1),
            bm25_score=float(numeric_index),
            semantic_score=float(numeric_index) / 10,
            metadata={"source": "General_FAQ"},
            original_rrf_rank=rank or numeric_index + 1,
        )

    async def test_tei_payload_excludes_answer_and_preserves_full_content(self):
        search = self.make_search([{"index": 0, "score": 0.91}])
        candidate = self.make_result(435, content=CHECKBOOK_CONTENT, rank=2)
        observer = CollectingObserver()

        with bind_pipeline_observer(observer):
            results = await search.rerank_search_results(
                "سلام . میخواهم دسته چک بانک کار آفرین بگیرم",
                [candidate],
                top_k=10,
            )

        self.assertEqual(len(search._http.calls), 1)
        _url, payload = search._http.calls[0]
        self.assertEqual(payload["texts"], [CHECKBOOK_RERANK_TEXT])
        self.assertFalse(payload["raw_scores"])
        self.assertNotIn(CHECKBOOK_ANSWER, payload["texts"][0])
        self.assertEqual(results[0].content, CHECKBOOK_CONTENT)

        rerank_record = next(
            record
            for record in observer.records
            if record.stage == PipelineStage.RERANK
        )
        input_row = rerank_record.input_data["candidates"][0]
        self.assertEqual(
            set(input_row),
            {
                "chunk_id",
                "original_rrf_rank",
                "hybrid_score",
                "bm25_score",
                "semantic_score",
                "rerank_text",
            },
        )
        self.assertEqual(input_row["rerank_text"], CHECKBOOK_RERANK_TEXT)
        output_row = rerank_record.output_data["rankings"][0]
        self.assertEqual(output_row["rerank_text"], CHECKBOOK_RERANK_TEXT)
        self.assertEqual(output_row["content"], CHECKBOOK_CONTENT)

    async def test_all_50_candidates_are_sent_once_and_top_10_are_selected(self):
        rankings = [
            {"index": index, "score": float(index)}
            for index in reversed(range(50))
        ]
        search = self.make_search(rankings)
        candidates = [self.make_result(index) for index in range(50)]

        results = await search.rerank_search_results(
            "پرسش بانکی", candidates, top_k=10
        )

        self.assertEqual(len(search._http.calls), 1)
        self.assertEqual(len(search._http.calls[0][1]["texts"]), 50)
        self.assertEqual(len(results), 10)
        self.assertEqual(
            [result.doc_id for result in results],
            [str(index) for index in range(49, 39, -1)],
        )
        for result in results:
            index = int(result.doc_id)
            self.assertIn(f"پاسخ بلند {index}", result.content)

    async def test_reordered_indexes_and_ties_keep_original_mapping(self):
        candidates = [
            self.make_result(20, rank=2),
            self.make_result(10, rank=1),
            self.make_result("b", rank=5),
            self.make_result("a", rank=5),
        ]
        search = self.make_search(
            [
                {"index": 2, "score": 0.5},
                {"index": 0, "score": 0.9},
                {"index": 3, "score": 0.5},
                {"index": 1, "score": 0.9},
            ]
        )

        results = await search.rerank_search_results(
            "پرسش", candidates, top_k=10
        )

        self.assertEqual(
            [result.doc_id for result in results], ["10", "20", "a", "b"]
        )
        for result in results:
            self.assertIn(f"پرسش {result.doc_id}", result.content)
            self.assertIn(f"پاسخ بلند {result.doc_id}", result.content)

    async def test_observed_failure_fixture_sends_only_each_faq_intent(self):
        contents = [
            CHECKBOOK_CONTENT,
            (
                "question : پس از تسویه کامل تسهیلات، چگونه می توانم چک ضمانت "
                "خود را دریافت کنم؟\nanswer : پاسخ طولانی نامرتبط الف\n"
                "question category : تسهیلات. sub_category : عودت چک"
            ),
            (
                "question : تسهیلات خود را تسویه کرده ام. چگونه می توانم چک "
                "ضمانت را دریافت کنم؟\nanswer : پاسخ طولانی نامرتبط ب\n"
                "question category : تسهیلات؛ sub_category : عودت چک"
            ),
        ]
        search = self.make_search(
            [{"index": index, "score": 1 - index / 10} for index in range(3)]
        )

        await search.rerank_search_results(
            "سلام . میخواهم دسته چک بانک کار آفرین بگیرم",
            [
                self.make_result(index, content=content)
                for index, content in enumerate(contents)
            ],
            top_k=10,
        )

        texts = search._http.calls[0][1]["texts"]
        self.assertEqual(texts[0], CHECKBOOK_RERANK_TEXT)
        self.assertIn("چک ضمانت", texts[1])
        self.assertIn("دسته‌بندی: تسهیلات", texts[1])
        self.assertIn("زیردسته: عودت چک", texts[1])
        self.assertIn("چک ضمانت", texts[2])
        self.assertNotIn("پاسخ طولانی", "\n".join(texts))


class TerminalRerankRenderingTests(unittest.TestCase):
    def test_report_shows_bge_input_and_original_content(self):
        observer = TerminalPipelineObserver(
            PipelineDebugSettings(enabled=True, rerank=True),
            raw_query="پرسش",
            session_id="session",
            channel="web",
            use_history=False,
            request_id="request",
        )
        observer.record(types.SimpleNamespace(
            stage=PipelineStage.RERANK,
            status="COMPLETED",
            input_data={"candidates": []},
            output_data={
                "rankings": [{
                    "chunk_id": "435",
                    "original_rrf_rank": 2,
                    "hybrid_score": 0.1,
                    "reranker_score": 0.9,
                    "reranker_rank": 1,
                    "selected": True,
                    "rerank_text": CHECKBOOK_RERANK_TEXT,
                    "content": CHECKBOOK_CONTENT,
                    "metadata": {},
                }]
            },
            metrics={"purpose": "answer_context"},
            duration_ms=1.0,
        ))

        report = observer.build_report()

        self.assertIn("BGE INPUT:", report)
        self.assertIn(CHECKBOOK_RERANK_TEXT, report)
        self.assertIn("ORIGINAL CONTENT:", report)
        self.assertIn(CHECKBOOK_ANSWER, report)


class FaqContextCountTests(unittest.IsolatedAsyncioTestCase):
    async def test_faq_sends_all_10_full_reranked_chunks_to_generation(self):
        graph_module = types.ModuleType("langgraph.graph")
        graph_module.StateGraph = object
        graph_module.END = object()
        langgraph = types.ModuleType("langgraph")
        langgraph.graph = graph_module
        performance_config = types.ModuleType("utils.performance_config")
        performance_config.PERFORMANCE_SETTINGS = types.SimpleNamespace(
            rag_retrieval_top_k=50,
            rag_context_rerank_enabled=True,
            rag_context_rerank_top_k=10,
            rag_related_questions_rerank_threshold=0.1,
        )
        patch = ModulePatch({
            "langgraph": langgraph,
            "langgraph.graph": graph_module,
            "utils.performance_config": performance_config,
        })
        with patch:
            module_name = "answer_context_agent_graph_under_test"
            graph = load_module(module_name, ROOT / "agent_graph.py")
            try:
                results = [
                    types.SimpleNamespace(
                        doc_id=str(index),
                        content=(
                            f"question : پرسش {index}\nanswer : پاسخ کامل {index}\n"
                            "question category : دسته. sub_category : زیردسته"
                        ),
                    )
                    for index in range(50)
                ]

                class SearchEngine:
                    async def rerank_search_results(self, query, candidates, top_k):
                        self.answer_call = (query, list(candidates), top_k)
                        return list(reversed(candidates))[:top_k]

                    async def rerank(self, query, candidates, threshold):
                        return candidates

                class Rag:
                    def __init__(self):
                        self.search_engine = SearchEngine()
                        self.generated_results = None
                        self.answer_context = None

                    async def retrieve(self, query, top_k, allowed_docs):
                        self.retrieve_call = (query, top_k, allowed_docs)
                        return results

                    def generate_context(self, selected):
                        self.generated_results = list(selected)
                        return "\n".join(item.content for item in selected)

                    async def answer(self, **kwargs):
                        self.answer_context = kwargs["context"]
                        return "پاسخ"

                rag = Rag()
                state = {
                    "messages": [{"role": "user", "content": "پرسش بانکی"}],
                    "retrieval_query": "پرسش بانکی",
                    "allowed_docs": ["General_FAQ"],
                    "doc_category": "FAQ",
                }

                await graph.make_handle_general(rag)(state)

                self.assertEqual(rag.retrieve_call[1], 50)
                self.assertEqual(len(rag.search_engine.answer_call[1]), 50)
                self.assertEqual(rag.search_engine.answer_call[2], 10)
                self.assertEqual(len(rag.generated_results), 10)
                self.assertEqual(rag.answer_context.count("answer : پاسخ کامل"), 10)
            finally:
                sys.modules.pop(module_name, None)


if __name__ == "__main__":
    unittest.main()
