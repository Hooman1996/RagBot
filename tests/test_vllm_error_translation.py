from __future__ import annotations

import unittest

import httpx
from openai import APIStatusError

from utils.RagSystem import RAGSystem
from utils.service_errors import (
    ModelContextLengthError,
    ServiceProtocolError,
    ServiceUnavailableError,
)


class FailingCompletions:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.body = body

    async def create(self, **_kwargs):
        request = httpx.Request("POST", "http://vllm.test/v1/chat/completions")
        response = httpx.Response(self.status_code, request=request)
        raise APIStatusError(
            "synthetic vLLM error",
            response=response,
            body=self.body,
        )


class FakeClient:
    def __init__(self, status_code: int, body: dict):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FailingCompletions(status_code, body)


def make_rag(status_code: int, body: dict) -> RAGSystem:
    rag = RAGSystem.__new__(RAGSystem)
    rag._closed = False
    rag._vllm_active = 0
    rag._vllm_timeout_total = 0
    rag.client = FakeClient(status_code, body)
    return rag


class VllmErrorTranslationTests(unittest.IsolatedAsyncioTestCase):
    async def test_input_token_rejection_has_specific_context_error(self):
        rag = make_rag(
            400,
            {
                "type": "BadRequestError",
                "param": "input_tokens",
                "code": 400,
            },
        )

        with self.assertRaises(ModelContextLengthError):
            await rag._completion()

    async def test_other_client_rejection_is_protocol_error(self):
        rag = make_rag(422, {"param": "messages", "code": 422})

        with self.assertRaises(ServiceProtocolError):
            await rag._completion()

    async def test_server_error_remains_unavailable(self):
        rag = make_rag(503, {"code": 503})

        with self.assertRaises(ServiceUnavailableError):
            await rag._completion()


if __name__ == "__main__":
    unittest.main()
