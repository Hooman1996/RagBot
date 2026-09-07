from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from new_architecture.app.config import Config
from evaluation_system.backend.app.services.config_snapshot import build_config_snapshot
from pipeline_observer import (
    PipelineStage,
    bind_pipeline_observer,
    stable_hash,
)
from utils.performance_config import PERFORMANCE_SETTINGS


ROOT = Path(__file__).resolve().parents[1]


def load_rag_system_class():
    qdrant_client = types.ModuleType("qdrant_client")
    qdrant_client.QdrantClient = object
    hybrid_search = types.ModuleType("utils.persian_hybrid_search")
    hybrid_search.PersianHybridSearch = object
    langchain = types.ModuleType("langchain_classic")
    langchain_chains = types.ModuleType("langchain_classic.chains")
    langchain_chains.RetrievalQA = object
    openai = types.ModuleType("openai")
    openai.APIConnectionError = type("APIConnectionError", (Exception,), {})
    openai.APIStatusError = type("APIStatusError", (Exception,), {})
    openai.APITimeoutError = type("APITimeoutError", (Exception,), {})
    openai.AsyncOpenAI = object
    httpx = types.ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.Client = object
    replacements = {
        "qdrant_client": qdrant_client,
        "numpy": types.ModuleType("numpy"),
        "torch": types.ModuleType("torch"),
        "openai": openai,
        "httpx": httpx,
        "utils.persian_hybrid_search": hybrid_search,
        "langchain_classic": langchain,
        "langchain_classic.chains": langchain_chains,
    }
    previous = {name: sys.modules.get(name) for name in replacements}
    try:
        sys.modules.update(replacements)
        spec = importlib.util.spec_from_file_location(
            "utils.RagSystem_prompt_roles_under_test", ROOT / "utils" / "RagSystem.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load RAGSystem for prompt-role tests")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.RAGSystem
    finally:
        for name, original in previous.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


RAGSystem = load_rag_system_class()


PROMPT_CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures" / "rag_answer_prompt_contract.json").read_text(
        encoding="utf-8"
    )
)


class RecordingObserver:
    pipeline_hashes_enabled = True

    def __init__(self) -> None:
        self.records = []

    def record(self, result) -> None:
        self.records.append(result)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_rag() -> RAGSystem:
    rag = RAGSystem.__new__(RAGSystem)
    rag.model_id = "/test/model"
    rag._completion = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="پاسخ آزمایشی"))]
        )
    )
    return rag


async def invoke_answer(rag: RAGSystem, *, category=None, max_new_tokens=137):
    observer = RecordingObserver()
    with bind_pipeline_observer(observer):
        answer = await rag.answer(
            user_question="پرسش یکتای کاربر",
            context="زمینه یکتای بازیابی‌شده",
            recent_history="تاریخچه یکتای گفتگو",
            current_summary="خلاصه استفاده‌نشده",
            tone="friendly",
            response_type="normal",
            max_new_tokens=max_new_tokens,
            enable_history=True,
            category=category,
        )
    prompt_record = next(
        record for record in observer.records if record.stage == PipelineStage.PROMPT_BUILD
    )
    return answer, rag._completion.await_args.kwargs, prompt_record


class PromptTextPreservationTests(unittest.TestCase):
    def test_pre_refactor_invariant_prompt_bytes_are_preserved(self):
        route_prompts = {
            "chitchat": Config.CHITCHAT_SYSTEM_PROMPT,
            "document": Config.DOCUMENT_RAG_SYSTEM_PROMPT,
            "general": Config.GENERAL_RAG_SYSTEM_PROMPT,
        }
        for route, system_prompt in route_prompts.items():
            with self.subTest(route=route):
                fixture = PROMPT_CONTRACT[route]
                self.assertEqual(sha256(system_prompt), fixture["system_sha256"])
                for exact_text in fixture["invariant_text"]:
                    self.assertIn(exact_text, system_prompt)

    def test_pre_refactor_dynamic_templates_are_preserved_where_they_existed(self):
        self.assertEqual(
            sha256(Config.DOCUMENT_RAG_USER_PROMPT),
            PROMPT_CONTRACT["document"]["user_template_sha256"],
        )
        self.assertEqual(
            sha256(Config.GENERAL_RAG_USER_PROMPT),
            PROMPT_CONTRACT["general"]["user_template_sha256"],
        )

    def test_policy_is_not_duplicated_in_user_templates(self):
        user_templates = {
            "chitchat": Config.CHITCHAT_USER_PROMPT,
            "document": Config.DOCUMENT_RAG_USER_PROMPT,
            "general": Config.GENERAL_RAG_USER_PROMPT,
        }
        for route, user_template in user_templates.items():
            with self.subTest(route=route):
                for exact_text in PROMPT_CONTRACT[route]["invariant_text"]:
                    self.assertNotIn(exact_text, user_template)

    def test_only_request_data_placeholders_live_in_user_templates(self):
        self.assertIn("{current_history}", Config.CHITCHAT_USER_PROMPT)
        self.assertIn("{question}", Config.CHITCHAT_USER_PROMPT)
        self.assertIn("{current_context}", Config.DOCUMENT_RAG_USER_PROMPT)
        self.assertIn("{current_history}", Config.DOCUMENT_RAG_USER_PROMPT)
        self.assertIn("{current_question}", Config.DOCUMENT_RAG_USER_PROMPT)
        self.assertIn("{formatted_search_results}", Config.GENERAL_RAG_USER_PROMPT)
        self.assertIn("{question}", Config.GENERAL_RAG_USER_PROMPT)

    def test_evaluation_source_hash_tracks_configured_answer_prompts(self):
        class SnapshotRag:
            model_id = "/test/model"
            search_engine = None

            async def answer(self):
                return None

        service = SimpleNamespace(
            agent_service=SimpleNamespace(rag_system=SnapshotRag()),
            intent_classifier=None,
            history_rewriting_service=None,
        )
        original_hash = build_config_snapshot(
            answering_service=service
        )["generation"]["answer_prompt_source_hash"]
        with patch.object(
            Config,
            "GENERAL_RAG_SYSTEM_PROMPT",
            Config.GENERAL_RAG_SYSTEM_PROMPT + "changed",
        ):
            changed_hash = build_config_snapshot(
                answering_service=service
            )["generation"]["answer_prompt_source_hash"]
        self.assertNotEqual(original_hash, changed_hash)


class AnswerMessageRoleTests(unittest.IsolatedAsyncioTestCase):
    def assert_common_message_contract(self, rag, kwargs, prompt_record):
        self.assertEqual(rag._completion.await_count, 1)
        messages = kwargs["messages"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertNotEqual(messages[0]["content"], "You are a helpful assistant.")
        self.assertEqual(prompt_record.output_data["system_message"], messages[0]["content"])
        self.assertEqual(prompt_record.output_data["user_prompt"], messages[1]["content"])
        self.assertEqual(prompt_record.output_data["prompt"], messages)
        self.assertEqual(prompt_record.metrics["prompt_hash"], stable_hash(messages))

    async def test_general_route_uses_system_and_user_roles(self):
        rag = make_rag()
        _answer, kwargs, prompt_record = await invoke_answer(rag)
        self.assert_common_message_contract(rag, kwargs, prompt_record)
        system_message, user_prompt = (item["content"] for item in kwargs["messages"])
        self.assertIn("You are Hibot, a high-precision corporate banking assistant", system_message)
        self.assertIn("زمینه یکتای بازیابی‌شده", user_prompt)
        self.assertIn("پرسش یکتای کاربر", user_prompt)
        self.assertNotIn("زمینه یکتای بازیابی‌شده", system_message)
        self.assertNotIn("پرسش یکتای کاربر", system_message)
        self.assertEqual(kwargs["max_tokens"], 137)
        self.assertEqual(kwargs["temperature"], PERFORMANCE_SETTINGS.rag_answer_temperature)
        self.assertEqual(kwargs["top_p"], PERFORMANCE_SETTINGS.rag_answer_top_p)
        self.assertEqual(kwargs["seed"], PERFORMANCE_SETTINGS.rag_answer_seed)

    async def test_chitchat_route_uses_system_and_user_roles(self):
        rag = make_rag()
        _answer, kwargs, prompt_record = await invoke_answer(rag, category="chitchat")
        self.assert_common_message_contract(rag, kwargs, prompt_record)
        system_message, user_prompt = (item["content"] for item in kwargs["messages"])
        self.assertIn("<decision_policy>", system_message)
        self.assertIn("با عرض پوزش، در این زمینه اطلاعاتی ندارم.", system_message)
        self.assertIn("تاریخچه یکتای گفتگو", user_prompt)
        self.assertIn("پرسش یکتای کاربر", user_prompt)
        self.assertNotIn("<decision_policy>", user_prompt)
        self.assertEqual(
            kwargs["max_tokens"], PERFORMANCE_SETTINGS.rag_chitchat_max_new_tokens
        )
        self.assertEqual(
            kwargs["temperature"], PERFORMANCE_SETTINGS.rag_chitchat_temperature
        )
        self.assertEqual(kwargs["top_p"], PERFORMANCE_SETTINGS.rag_chitchat_top_p)
        self.assertEqual(kwargs["seed"], PERFORMANCE_SETTINGS.rag_chitchat_seed)

    async def test_document_route_uses_system_and_user_roles(self):
        for category in ("ابلاغیه ها", "قرارداد ها"):
            with self.subTest(category=category):
                rag = make_rag()
                _answer, kwargs, prompt_record = await invoke_answer(
                    rag, category=category
                )
                self.assert_common_message_contract(rag, kwargs, prompt_record)
                system_message, user_prompt = (
                    item["content"] for item in kwargs["messages"]
                )
                self.assertIn("ZERO HALLUCINATION (CRITICAL)", system_message)
                self.assertIn("متأسفانه اطلاعات مربوط به این پرسش", system_message)
                self.assertIn("زمینه یکتای بازیابی‌شده", user_prompt)
                self.assertIn("تاریخچه یکتای گفتگو", user_prompt)
                self.assertIn("پرسش یکتای کاربر", user_prompt)
                self.assertNotIn("ZERO HALLUCINATION (CRITICAL)", user_prompt)
                self.assertEqual(kwargs["max_tokens"], 137)
                self.assertEqual(
                    kwargs["temperature"], PERFORMANCE_SETTINGS.rag_answer_temperature
                )
                self.assertEqual(kwargs["top_p"], PERFORMANCE_SETTINGS.rag_answer_top_p)
                self.assertEqual(kwargs["seed"], PERFORMANCE_SETTINGS.rag_answer_seed)

    async def test_hashing_stays_disabled_for_non_hashing_observer(self):
        class NonHashingObserver(RecordingObserver):
            pipeline_hashes_enabled = False

        rag = make_rag()
        observer = NonHashingObserver()
        with patch(f"{RAGSystem.__module__}.stable_hash") as prompt_hash, bind_pipeline_observer(
            observer
        ):
            await rag.answer(
                user_question="پرسش",
                context="زمینه",
                recent_history="تاریخچه",
                current_summary="",
                tone="friendly",
                response_type="normal",
            )
        prompt_hash.assert_not_called()

    def test_answer_has_no_shared_template_mutation(self):
        self.assertNotIn("self.template", inspect.getsource(RAGSystem.answer))


if __name__ == "__main__":
    unittest.main()
