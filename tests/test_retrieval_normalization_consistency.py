from __future__ import annotations

import json
import importlib.util
import unittest
from pathlib import Path

import httpx
import numpy as np
import torch

from agent_graph import make_handle_general
from utils.persian_hybrid_search import PersianHybridSearch
from utils.tei_embedding_client import build_query_payload
from utils.request_instrumentation import RequestTrace, trace_summary


VARIANTS = (
    "میشه اسم حساب هارو بگی",
    "میشه اسم حساب ها رو بگی",
    "میشه اسم حساب‌ها رو بگی",
    "میشه اسم حسابها رو بگی",
)

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "application_intent_classifier", ROOT / "intent_classifier.py"
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Unable to load application intent classifier")
_INTENT_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_INTENT_MODULE)
IntentClassifier = _INTENT_MODULE.IntentClassifier
JINA_DIM = _INTENT_MODULE.JINA_DIM


class FixedActionableNetwork(torch.nn.Module):
    def forward(self, features):
        return torch.tensor([[8.0, -8.0]], dtype=torch.float32).repeat(
            features.shape[0], 1
        )


class InlineRunner:
    async def run(self, function, *args, **_kwargs):
        return function(*args)


class RetrievalNormalizationConsistencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_classifier_receives_same_text_and_keeps_same_route(self):
        seen = []

        async def embedding(text):
            seen.append(text)
            return np.zeros(JINA_DIM, dtype=np.float32).tolist()

        classifier = IntentClassifier(
            embedding_model=embedding,
            classifier_model_path=None,
            device="cpu",
            blocking_runner=InlineRunner(),
        )
        classifier.classifier = FixedActionableNetwork()

        results = [await classifier.classify_detailed(text) for text in VARIANTS]
        self.assertEqual(set(seen), {"میشه اسم حساب هارو بگی"})
        self.assertEqual({result["type"] for result in results}, {"general"})
        self.assertEqual(
            {result["preprocessed_query"] for result in results},
            {"میشه اسم حساب هارو بگی"},
        )

    def test_tei_embedding_payloads_are_identical(self):
        payloads = [build_query_payload(text) for text in VARIANTS]
        self.assertTrue(all(payload == payloads[0] for payload in payloads))
        self.assertEqual(payloads[0]["inputs"], "میشه اسم حساب هارو بگی")

    async def test_reranker_receives_same_query_and_candidate_texts(self):
        requests = []

        async def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                json=[{"index": 0, "score": 0.75}],
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = object.__new__(PersianHybridSearch)
            search._closed = False
            search._http = client
            search.tei_rerank_url = "http://reranker.test"
            search._tei_reranker_active = 0
            search._tei_pool_timeout_total = 0
            for variant in VARIANTS:
                result = await search.rerank(
                    variant,
                    [{"question": "اسم حساب ها چیست؟", "answer": ""}],
                    threshold=0.1,
                )
                self.assertEqual(len(result), 1)

        self.assertEqual(
            {request["query"] for request in requests},
            {"میشه اسم حساب هارو بگی"},
        )
        self.assertEqual(
            {tuple(request["texts"]) for request in requests},
            {("اسم حساب هارو بگی",)},
        )

    async def test_empty_retrieval_has_stable_fallback_reason(self):
        class SearchEngine:
            async def rerank(self, *_args, **_kwargs):
                return []

        class Rag:
            search_engine = SearchEngine()

            async def retrieve(self, *_args, **_kwargs):
                return []

            def generate_context(self, _results):
                return ""

            async def answer(self, **_kwargs):
                return (
                    "متاسفانه اطلاعات دقیقی در این زمینه ندارم. "
                    "لطفا اقدام به ثبت تیکت کنید."
                )

        state = {
            "messages": [{"role": "user", "content": VARIANTS[0]}],
            "retrieval_query": VARIANTS[0],
            "allowed_docs": ["General_FAQ"],
            "doc_category": "FAQ",
        }
        result = await make_handle_general(Rag())(state)
        self.assertEqual(result["fallback_reason"], "NO_RETRIEVAL_RESULTS")

    def test_request_trace_keeps_content_free_diagnostics(self):
        trace = RequestTrace(request_id="trace-test", process_id=1)
        trace.set_diagnostic("raw_query_fingerprint", "0123456789abcdef")
        trace.set_diagnostic(
            "retrieval_top", [{"candidate_id": "173", "hybrid_score": 0.1}]
        )
        summary = trace_summary(trace)
        self.assertEqual(
            summary["diagnostics"]["raw_query_fingerprint"],
            "0123456789abcdef",
        )
        self.assertNotIn("query", summary)


if __name__ == "__main__":
    unittest.main()
