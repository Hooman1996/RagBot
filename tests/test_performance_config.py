import os
import unittest
from pathlib import Path
from unittest import mock

from utils.performance_config import load_performance_settings


ROOT = Path(__file__).resolve().parents[1]


class PerformanceSettingsTests(unittest.TestCase):
    def test_defaults_preserve_existing_limits_and_set_admission_experiment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = load_performance_settings()

        self.assertEqual(settings.application_request_timeout_seconds, 50.0)
        self.assertEqual(settings.request_concurrency_limit, 32)
        self.assertEqual(settings.request_admission_timeout_seconds, 12.0)
        self.assertEqual(settings.blocking_concurrency_limit, 16)
        self.assertEqual(settings.tei_http_max_connections, 32)
        self.assertEqual(settings.tei_embed_insert_batch_size, 32)
        self.assertEqual(settings.tei_embed_max_client_batch_size, 50)
        self.assertEqual(settings.vllm_http_max_connections, 32)
        self.assertEqual(settings.qdrant_concurrency, 4)
        self.assertEqual(settings.rag_retrieval_top_k, 10)
        self.assertEqual(settings.rag_semantic_candidate_limit, 50)
        self.assertEqual(
            settings.mobile_related_questions_rerank_threshold, 0.5
        )
        self.assertEqual(settings.rag_max_new_tokens, 500)

    def test_environment_overrides_are_loaded(self):
        overrides = {
            "REQUEST_CONCURRENCY_LIMIT": "40",
            "REQUEST_ADMISSION_TIMEOUT_SECONDS": "9.5",
            "TEI_HTTP_MAX_CONNECTIONS": "48",
            "TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS": "24",
            "TEI_EMBED_INSERT_BATCH_SIZE": "40",
            "TEI_EMBED_MAX_CLIENT_BATCH_SIZE": "50",
            "VLLM_HTTP_MAX_CONNECTIONS": "50",
            "VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS": "25",
            "QDRANT_CONCURRENCY": "8",
            "RAG_RETRIEVAL_TOP_K": "12",
            "RAG_SEMANTIC_CANDIDATE_LIMIT": "60",
            "RAG_MAX_NEW_TOKENS": "400",
        }
        with mock.patch.dict(os.environ, overrides, clear=True):
            settings = load_performance_settings()

        self.assertEqual(settings.request_concurrency_limit, 40)
        self.assertEqual(settings.request_admission_timeout_seconds, 9.5)
        self.assertEqual(settings.tei_http_max_connections, 48)
        self.assertEqual(settings.tei_embed_insert_batch_size, 40)
        self.assertEqual(settings.vllm_http_max_connections, 50)
        self.assertEqual(settings.qdrant_concurrency, 8)
        self.assertEqual(settings.rag_retrieval_top_k, 12)
        self.assertEqual(settings.rag_semantic_candidate_limit, 60)
        self.assertEqual(settings.rag_max_new_tokens, 400)

    def test_invalid_values_fail_fast(self):
        cases = [
            {"REQUEST_CONCURRENCY_LIMIT": "0"},
            {"REQUEST_ADMISSION_TIMEOUT_SECONDS": "not-a-number"},
            {"APPLICATION_REQUEST_TIMEOUT_SECONDS": "51"},
            {
                "TEI_HTTP_MAX_CONNECTIONS": "10",
                "TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS": "11",
            },
            {
                "RAG_RETRIEVAL_TOP_K": "51",
                "RAG_SEMANTIC_CANDIDATE_LIMIT": "50",
            },
            {
                "TEI_EMBED_INSERT_BATCH_SIZE": "51",
                "TEI_EMBED_MAX_CLIENT_BATCH_SIZE": "50",
            },
            {"RAG_RELATED_QUESTIONS_RERANK_THRESHOLD": "1.1"},
        ]
        for environment in cases:
            with self.subTest(environment=environment):
                with mock.patch.dict(os.environ, environment, clear=True):
                    with self.assertRaises(ValueError):
                        load_performance_settings()

    def test_mobile_endpoint_uses_configured_admission_timeout(self):
        source = (ROOT / "mobile_api.py").read_text(encoding="utf-8")

        self.assertIn(
            "PERFORMANCE_SETTINGS.request_admission_timeout_seconds", source
        )
        self.assertIn(
            "PERFORMANCE_SETTINGS.application_request_timeout_seconds", source
        )
        self.assertIn(
            "await asyncio.wait_for(\n            run_with_limit(", source
        )
        self.assertNotIn("acquire_timeout=2.0", source)


if __name__ == "__main__":
    unittest.main()
