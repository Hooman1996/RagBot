"""Offline prompt construction and transport tests, not model-quality evaluation."""
import asyncio
import hashlib
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from new_architecture.app.config import (
    COMPANY_BACKGROUND,
    INTRODUCTION,
    MISSING_INFORMATION,
    OUT_OF_SCOPE,
    Config,
    NegahBoomPrompts,
)
from prompt_selection import PromptContext, select_prompt_context
from tests.test_p0_p1_repairs import ModulePatch, graph_import_stubs, load_module
from tests.test_rag_answer_prompt_roles import make_rag

ROOT = Path(__file__).resolve().parents[1]


def test_all_existing_config_prompt_bytes_unchanged():
    baseline = json.loads((ROOT / 'tests/fixtures/step2_existing_prompt_hashes.json').read_text())
    assert baseline
    for name, digest in baseline.items():
        assert hashlib.sha256(getattr(Config, name).encode()).hexdigest() == digest, name


@pytest.mark.parametrize('category', [None, 'FAQ', 'chitchat', 'قرارداد ها', 'ابلاغیه ها'])
def test_hibank_actual_messages_match_original_templates(category):
    async def run():
        rag = make_rag()
        arguments = {'user_question': 'پرسش', 'context': 'زمینه', 'recent_history': 'سابقه',
                         'current_summary': '', 'tone': 'friendly', 'response_type': 'normal', 'category': category}
        await rag.answer(**arguments)
        implicit = rag._completion.await_args.kwargs
        await rag.answer(**arguments, prompt_context=PromptContext('hibank'))
        assert rag._completion.await_args.kwargs == implicit
        if category == 'chitchat':
            system = Config.CHITCHAT_SYSTEM_PROMPT
            user = Config.CHITCHAT_USER_PROMPT.format(current_history='سابقه', question='پرسش')
        elif category in ('قرارداد ها', 'ابلاغیه ها'):
            system = Config.DOCUMENT_RAG_SYSTEM_PROMPT
            user = Config.DOCUMENT_RAG_USER_PROMPT.format(current_context='زمینه', current_history='سابقه', current_question='پرسش')
        else:
            system = Config.GENERAL_RAG_SYSTEM_PROMPT
            user = Config.GENERAL_RAG_USER_PROMPT.format(formatted_search_results='زمینه', question='پرسش')
        assert implicit['messages'] == [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
    asyncio.run(run())


@pytest.mark.parametrize('mode', [None, 'auto', 'hibank', 'negahboom', 'obsolete'])
def test_fixed_and_auto_session_context_reaches_fake_model(mode, monkeypatch):
    if mode is None:
        monkeypatch.delenv('CHATBOT_PLATFORM', raising=False)
    else:
        monkeypatch.setenv('CHATBOT_PLATFORM', mode)
    async def run():
        for platform in ('hibank', 'negahboom'):
            context = select_prompt_context(['NegahBoom_FAQ' if platform == 'negahboom' else 'General_FAQ'])
            rag = make_rag()
            for category in ('FAQ', 'chitchat'):
                await rag.answer('پرسش', 'زمینه', 'سابقه', '', 'friendly', 'normal',
                                 category=category, prompt_context=context)
                messages = rag._completion.await_args.kwargs['messages']
                expected = NegahBoomPrompts if platform == 'negahboom' else Config
                assert messages[0]['content'] == getattr(expected, 'CHITCHAT_SYSTEM_PROMPT' if category == 'chitchat' else 'GENERAL_RAG_SYSTEM_PROMPT')
                assert [m['role'] for m in messages] == ['system', 'user']
                if platform == 'negahboom':
                    assert 'Hibank' not in messages[0]['content']
                    assert 'NegahBoom' in messages[0]['content']
                    if category == 'FAQ':
                        assert INTRODUCTION in messages[0]['content']
                        assert COMPANY_BACKGROUND in messages[0]['content']
    asyncio.run(run())


def test_identity_and_neutral_user_templates():
    assert INTRODUCTION == 'من Hibot هستم، دستیار هوشمند بانکداری باز'
    assert NegahBoomPrompts.GENERAL_RAG_USER_PROMPT == Config.GENERAL_RAG_USER_PROMPT
    assert NegahBoomPrompts.CHITCHAT_USER_PROMPT == Config.CHITCHAT_USER_PROMPT
    prompt = NegahBoomPrompts.GENERAL_RAG_SYSTEM_PROMPT
    assert MISSING_INFORMATION in prompt
    assert OUT_OF_SCOPE in prompt
    assert 'NegahBoom is not a bank' in prompt
    assert 'untrusted data' in prompt
    assert 'Do not prepend this introduction to every answer.' in prompt
    prompt = NegahBoomPrompts.CHITCHAT_SYSTEM_PROMPT
    assert 'من Hibot، دستیار هوشمند NegahBoom هستم' in prompt
    assert 'NegahBoom' in prompt
    assert 'Hibank' not in prompt


def load_rewriter():
    transformers = ModuleType('transformers')
    transformers.AutoModelForCausalLM = object
    transformers.AutoTokenizer = object
    with ModulePatch({'torch': ModuleType('torch'), 'transformers': transformers}):
        return load_module('new_architecture.app.services.history.negahboom_rewriting_under_test', ROOT / 'new_architecture/app/services/history/rewriting.py').HistoryRewritingService


def test_rewrite_messages_to_fake_client_and_concurrent_isolation():
    async def run():
        rag = make_rag()
        calls = []
        async def completion(**kwargs):
            calls.append(kwargs)
            await asyncio.sleep(0)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='<rewrite>GET /v2/example API_X</rewrite>'))])
        rag._completion = completion
        service = load_rewriter()(rag, None)
        async def turn(platform):
            await rag.answer(platform, 'synthetic', '', '', 'friendly', 'normal', category='FAQ', prompt_context=PromptContext(platform))
            await service.rewrite_query('GET /v2/example API_X', 'User: synthetic', prompt_context=PromptContext(platform))
        await asyncio.gather(*(turn(p) for p in ('hibank', 'negahboom') * 10))
        answer_calls = [c for c in calls if c['messages'][0]['content'] != 'You are a helpful assistant.']
        rewrite_calls = [c for c in calls if c['messages'][0]['content'] == 'You are a helpful assistant.']
        assert len(answer_calls) == len(rewrite_calls) == 20
        for call in answer_calls:
            platform = 'negahboom' if '<user_question>\nnegahboom\n' in call['messages'][1]['content'] else 'hibank'
            expected = NegahBoomPrompts if platform == 'negahboom' else Config
            assert call['messages'][0]['content'] == expected.GENERAL_RAG_SYSTEM_PROMPT
        for platform, expected in (('hibank', Config), ('negahboom', NegahBoomPrompts)):
            prompt = expected.QUERY_REWRITE_PROMPT.format(current_history='User: synthetic', current_query='GET /v2/example API_X')
            selected = [c for c in rewrite_calls if c['messages'][1]['content'] == prompt]
            assert len(selected) == 10
        assert 'Preserve API names, identifiers, endpoint paths, versions, and relevant English terms exactly.' in NegahBoomPrompts.QUERY_REWRITE_PROMPT
        # No-history fast path stays model-free on both platforms.
        for platform in ('hibank', 'negahboom'):
            before = len(calls)
            await service.rewrite_query('API_X', '', prompt_context=PromptContext(platform))
            assert len(calls) == before
    asyncio.run(run())


def test_graph_passes_context_preserves_faq_related_questions_and_fallback():
    with ModulePatch(graph_import_stubs()):
        graph = load_module('negahboom_graph_under_test', ROOT / 'agent_graph.py')
    async def run():
        for platform in ('hibank', 'negahboom'):
            rag = make_rag()
            result = SimpleNamespace(content='question: نمونه\nanswer: پاسخ', doc_id='synthetic', score=1.0)
            rag.retrieve = AsyncMock(return_value=[result])
            rag.search_engine = SimpleNamespace(
                rerank=AsyncMock(side_effect=lambda query, candidates, **kwargs: candidates),
                rerank_search_results=AsyncMock(side_effect=lambda query, candidates, **kwargs: candidates),
            )
            rag.generate_context = lambda results: 'synthetic context'
            state = {'platform': platform, 'messages': [{'role':'user','content':'نمونه'}],
                         'allowed_docs': ['NegahBoom_FAQ' if platform == 'negahboom' else 'General_FAQ'], 'doc_category': 'FAQ'}
            output = await graph.make_handle_general(rag)(state)
            assert output['last_answer'] == 'پاسخ آزمایشی'
            assert output['related_questions']
            assert output['related_questions'][0]['question'] == 'نمونه'
            assert output['feedback_needed'] is True
            prompt = rag._completion.await_args.kwargs['messages'][0]['content']
            assert prompt == (NegahBoomPrompts if platform == 'negahboom' else Config).GENERAL_RAG_SYSTEM_PROMPT
            if platform == 'negahboom':
                rag._completion.return_value.choices[0].message.content = MISSING_INFORMATION
                output = await graph.make_handle_general(rag)(state)
                assert output['fallback_reason'] == 'LLM_CONTEXT_REFUSAL'
            await graph.make_handle_chitchat(rag)(state)
            assert rag._completion.await_args.kwargs['messages'][0]['content'] == (NegahBoomPrompts if platform == 'negahboom' else Config).CHITCHAT_SYSTEM_PROMPT
            assert state['related_questions'] == []
    asyncio.run(run())


def test_workflow_templates_keep_existing_category_fallback():
    async def run():
        rag = make_rag()
        await rag.answer('', '', '', '', '', '', category='قرارداد ها', prompt_context=PromptContext('negahboom'))
        assert rag._completion.await_args.kwargs['messages'][0]['content'] == Config.DOCUMENT_RAG_SYSTEM_PROMPT
    asyncio.run(run())
