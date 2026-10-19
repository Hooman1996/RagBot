from __future__ import annotations

import asyncio
import json
import unittest

import httpx
from openai import APIStatusError, AsyncOpenAI

from utils.RagSystem import RAGSystem
from utils.service_errors import (
    ModelContextLengthError,
    ServiceProtocolError,
    ServiceTimeoutError,
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


def sdk_rag(handler) -> RAGSystem:
    """A real SDK client over a mocked transport, with SDK retries off."""
    rag = RAGSystem.__new__(RAGSystem)
    rag._closed = False
    rag._vllm_active = 0
    rag._vllm_timeout_total = 0
    rag.client = AsyncOpenAI(
        base_url="http://vllm.test/v1",
        api_key="synthetic-only",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return rag


ARGUMENTS = {
    "model": "fixture",
    "messages": [{"role": "user", "content": "synthetic"}],
    "max_tokens": 5,
}


class CompletionCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_sends_the_arguments_once(self):
        sent = []

        def reply(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "synthetic", "object": "chat.completion", "created": 0, "model": "fixture",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "synthetic answer"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            })

        rag = sdk_rag(reply)
        try:
            response = await rag._completion(**ARGUMENTS)
        finally:
            await rag.client.close()
        self.assertEqual(response.choices[0].message.content, "synthetic answer")
        self.assertEqual(len(sent), 1)
        self.assertEqual({key: sent[0][key] for key in ARGUMENTS}, ARGUMENTS)
        self.assertEqual(rag.metrics_snapshot(), {"vllm_active": 0, "vllm_timeout_total": 0})

    async def test_timeout_is_counted_and_releases_the_active_slot(self):
        sent = []

        def fail(request):
            sent.append(request)
            raise httpx.ReadTimeout("synthetic", request=request)

        rag = sdk_rag(fail)
        try:
            with self.assertRaises(ServiceTimeoutError):
                await rag._completion(**ARGUMENTS)
        finally:
            await rag.client.close()
        self.assertEqual(len(sent), 1)
        self.assertEqual(rag.metrics_snapshot(), {"vllm_active": 0, "vllm_timeout_total": 1})

    async def test_refused_connection_releases_the_active_slot(self):
        def refuse(request):
            raise httpx.ConnectError("synthetic", request=request)

        rag = sdk_rag(refuse)
        try:
            with self.assertRaises(ServiceUnavailableError):
                await rag._completion(**ARGUMENTS)
        finally:
            await rag.client.close()
        self.assertEqual(rag.metrics_snapshot(), {"vllm_active": 0, "vllm_timeout_total": 0})

    async def test_cancellation_releases_the_active_slot(self):
        entered = asyncio.Event()

        async def block(request):
            entered.set()
            await asyncio.Event().wait()

        rag = sdk_rag(block)
        try:
            task = asyncio.create_task(rag._completion(**ARGUMENTS))
            await entered.wait()
            self.assertEqual(rag.metrics_snapshot()["vllm_active"], 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            await rag.client.close()
        self.assertEqual(rag.metrics_snapshot(), {"vllm_active": 0, "vllm_timeout_total": 0})


if __name__ == "__main__":
    unittest.main()
