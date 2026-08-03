from __future__ import annotations

import math
import json
import unittest
from pathlib import Path

import httpx

from utils.service_errors import ServiceProtocolError
from utils.tei_embedding_batches import (
    DocumentEmbeddingBatchError,
    embed_documents_in_batches,
)
from utils.tei_embedding_client import TeiEmbeddingClient


ROOT = Path(__file__).resolve().parents[1]
DIMENSION = 1024


def unit_vector(marker: float = 1.0) -> list[float]:
    vector = [0.0] * DIMENSION
    vector[0] = marker
    return vector


class TeiEmbeddingPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            body = request.content
            import json

            payload = json.loads(body)
            inputs = payload["inputs"]
            count = 1 if isinstance(inputs, str) else len(inputs)
            return httpx.Response(
                200,
                json=[unit_vector(index + 1.0) for index in range(count)],
            )

        self.http = httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        )
        self.client = TeiEmbeddingClient(
            "http://tei.test/",
            self.http,
            expected_dimension=DIMENSION,
        )

    async def asyncTearDown(self):
        await self.http.aclose()

    def request_json(self, index: int = -1):
        import json

        return json.loads(self.requests[index].content)

    async def test_query_request_uses_query_prompt_and_normalization_only(self):
        vector = await self.client.embed_query("چگونه کارت بگیرم؟")

        self.assertEqual(len(vector), DIMENSION)
        self.assertEqual(
            self.request_json(),
            {
                "inputs": "چگونه کارت بگیرم؟",
                "prompt_name": "query",
                "normalize": True,
            },
        )
        self.assertFalse(self.request_json()["inputs"].startswith("Query: "))

    async def test_document_request_is_raw_normalized_batch_in_input_order(self):
        vectors = await self.client.embed_documents(["سند اول", "سند دوم"])

        self.assertEqual([vector[0] for vector in vectors], [1.0, 2.0])
        payload = self.request_json()
        self.assertEqual(
            payload, {"inputs": ["سند اول", "سند دوم"], "normalize": True}
        )
        self.assertNotIn("prompt_name", payload)
        self.assertTrue(
            all(not text.startswith("Document: ") for text in payload["inputs"])
        )

    async def test_single_query_and_batched_document_response_extraction(self):
        query = await self.client.embed_query("پرسش")
        documents = await self.client.embed_documents(["الف", "ب"])

        self.assertEqual(query[0], 1.0)
        self.assertEqual([vector[0] for vector in documents], [1.0, 2.0])

    async def test_empty_query_is_rejected_without_request(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    await self.client.embed_query(value)  # type: ignore[arg-type]
        self.assertEqual(self.requests, [])

    async def test_empty_document_batch_returns_without_request(self):
        self.assertEqual(await self.client.embed_documents([]), [])
        self.assertEqual(self.requests, [])

    async def test_invalid_response_shapes_are_rejected(self):
        invalid_payloads = (unit_vector(), [unit_vector(), unit_vector()])
        for payload in invalid_payloads:
            async def handler(_request, payload=payload):
                return httpx.Response(200, json=payload)

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as http:
                client = TeiEmbeddingClient("http://tei", http)
                with self.subTest(payload_type=type(payload).__name__):
                    with self.assertRaises(ServiceProtocolError):
                        await client.embed_query("پرسش")

    async def test_wrong_dimension_is_rejected(self):
        async def handler(_request):
            return httpx.Response(200, json=[[0.0] * (DIMENSION - 1)])

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http:
            with self.assertRaises(ServiceProtocolError):
                await TeiEmbeddingClient("http://tei", http).embed_query("x")

    async def test_document_response_count_must_match_batch(self):
        async def handler(_request):
            return httpx.Response(200, json=[unit_vector()])

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http:
            client = TeiEmbeddingClient("http://tei", http)
            with self.assertRaises(ServiceProtocolError):
                await client.embed_documents(["first", "second"])

    async def test_nan_infinity_non_numeric_and_bool_are_rejected(self):
        for invalid in (math.nan, math.inf, -math.inf, "1", True):
            vector = unit_vector()
            vector[4] = invalid  # type: ignore[assignment]

            async def handler(_request, vector=vector):
                return httpx.Response(
                    200,
                    content=json.dumps([vector], allow_nan=True),
                    headers={"content-type": "application/json"},
                )

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as http:
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ServiceProtocolError):
                        await TeiEmbeddingClient(
                            "http://tei", http
                        ).embed_query("x")

    async def test_http_failure_is_raised(self):
        async def handler(_request):
            return httpx.Response(422, json={"error": "bad prompt"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http:
            with self.assertRaises(httpx.HTTPStatusError):
                await TeiEmbeddingClient("http://tei", http).embed_query("x")

    async def test_batching_boundaries_preserve_order_and_context(self):
        vectors = await embed_documents_in_batches(
            self.client,
            ["a", "b", "c", "d", "e"],
            [10, 11, 12, 13, 14],
            batch_size=2,
        )
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(
            [self.request_json(index)["inputs"] for index in range(3)],
            [["a", "b"], ["c", "d"], ["e"]],
        )
        self.assertEqual([vector[0] for vector in vectors], [1, 2, 1, 2, 1])

        with self.assertRaises(ValueError):
            await embed_documents_in_batches(
                self.client, ["a"], [1], batch_size=0
            )

    async def test_batch_failure_reports_batch_number_size_and_record_ids(self):
        call_count = 0

        async def handler(_request):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return httpx.Response(503)
            return httpx.Response(200, json=[unit_vector(), unit_vector()])

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http:
            client = TeiEmbeddingClient("http://tei", http)
            with self.assertRaises(DocumentEmbeddingBatchError) as raised:
                await embed_documents_in_batches(
                    client, ["a", "b", "c"], [101, 102, 103], batch_size=2
                )
        self.assertEqual(raised.exception.batch_number, 2)
        self.assertEqual(raised.exception.batch_size, 1)
        self.assertEqual(raised.exception.source_record_ids, [103])

    async def test_persistent_http_client_is_reused(self):
        client_identity = id(self.client._http)
        await self.client.embed_query("q1")
        await self.client.embed_query("q2")
        await self.client.embed_documents(["d1", "d2"])

        self.assertEqual(id(self.client._http), client_identity)
        self.assertEqual(len(self.requests), 3)


class EmbeddingPolicyStaticTests(unittest.TestCase):
    def test_active_insertion_paths_have_no_sentence_transformer_inference(self):
        for relative in (
            "utils/persian_hybrid_search.py",
            "new_architecture/data_insertion_with_api.py",
            "new_architecture/insert_data.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("from sentence_transformers import", source)
            self.assertNotIn("model.encode(", source)

    def test_qdrant_payload_fields_and_schema_policy_are_unchanged(self):
        for relative in (
            "new_architecture/data_insertion_with_api.py",
            "new_architecture/insert_data.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            for field in (
                '"chunk_id": c_id',
                '"chunk_index": c_index',
                '"document_id": doc_id',
                '"document": doc_title',
            ):
                self.assertIn(field, source)
            self.assertIn("QDRANT_VECTOR_SIZE = int(", source)
            self.assertIn("distance=Distance.COSINE", source)

    def test_setup_dbs_remains_schema_only_for_postgres(self):
        source = (
            ROOT / "new_architecture/setup_dbs.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("QdrantClient", source)
        self.assertNotIn("/embed", source)
        self.assertNotIn("SentenceTransformer", source)


if __name__ == "__main__":
    unittest.main()
