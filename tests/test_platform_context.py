"""Correction regressions: real handlers/graph with synthetic in-memory services."""
import ast
import asyncio
import copy
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import main
from agent_service import AgentService
from answering_service import AnsweringService, AnswerRequestContext
from conversation_history import (
    EVALUATION_EXECUTION_POLICY,
    ConversationSnapshot,
)
from document_category import get_document_category
from mixed_source_prompts import MixedSourcePrompts
from new_architecture.app.config import Config, NegahBoomPrompts
from prompt_selection import select_prompt_context
from tests.test_answering_service import Classifier, ImmediateRunner, Processor
from tests.test_mobile_history_content import (
    StatefulCloseDatabase,
    database_module,
    mobile_api,
    request_with,
    session_row,
)
from tests.test_negahboom_prompts import load_rewriter
from tests.test_rag_answer_prompt_roles import make_rag
from tests.test_web_auth import csrf, login, setup  # noqa: F401
from utils.concurrency import AdmissionLimiter

SOURCES = ('General_FAQ', 'NegahBoom_FAQ', 'General_FAQ')


class MemoryDb:
    """Only records data locally; no database constructor or connection."""
    def __init__(self, binding=None):
        self.metadata = {'other': {'keep': True}}
        if binding is not None:
            self.metadata['chatbot_platform'] = binding
        self.metadata['agent_state'] = {
            'platform': binding or 'obsolete',
            'allowed_docs': ['STALE_FAQ'],
            'messages': [{'role': 'user', 'content': 'previous reference'},
                         {'role': 'assistant', 'content': 'old service details'}],
        }
        self.messages = []
        self.row = session_row(12, user_id=1, meta_data=self.metadata, uuid='mobile-uuid')

    def get_session_by_id(self, key):
        return self.row if int(key) == 12 else None

    def get_session_metadata(self, key):
        return copy.deepcopy(self.metadata)

    def update_session_metadata(self, key, metadata):
        self.metadata.update(copy.deepcopy(metadata))

    def get_session_by_uuid(self, key):
        return self.row if key == 'mobile-uuid' else None

    def get_or_create_user_by_national_code(self, code):
        return {'id': 1}

    _validate_mobile_session = staticmethod(database_module.DatabaseManager._validate_mobile_session)


class MemoryChats:
    def __init__(self, db): self.db = db

    def create_new_chat(self, user_id, **kwargs):
        assert not kwargs.get('platform_context')
        assert user_id == 1
        return self.db.row

    def resolve_mobile_session(self, user_id, uuid, require_active=True):
        self.db._validate_mobile_session(self.db.get_session_by_uuid(uuid), user_id, require_active)
        return '12'

    def add_message(self, session_id, role, content, **kwargs):
        assert str(session_id) == '12'
        msg = {'id': str(len(self.db.messages) + 1), 'role': role, 'content': content, 'created_at': None}
        self.db.messages.append(msg)
        return msg

    def get_messages(self, key): return self.db.messages
    def get_session(self, key): return self.db.row

    def get_user_sessions(self, user_id, *args):
        return {str(n): {**self.db.row, 'id': n, 'meta_data': binding}
                for n, binding in enumerate(({}, {'chatbot_platform': 'hibank'},
                                               {'chatbot_platform': 'negahboom'}), 12)}


def pipeline(db):
    rag = make_rag()
    async def retrieve(query, top_k, allowed_docs):
        return [SimpleNamespace(doc_id=title, score=1.0,
                                content=f'question: synthetic\nanswer: evidence_{title}')
                for title in allowed_docs]
    rag.retrieve = AsyncMock(side_effect=retrieve)
    rag.search_engine = SimpleNamespace(
        rerank=AsyncMock(side_effect=lambda q, items, **kw: items),
        rerank_search_results=AsyncMock(side_effect=lambda q, items, **kw: items),
    )
    rewriter = load_rewriter()(rag, None)
    chats = MemoryChats(db)
    agent = AgentService(rag, Classifier(), {}, db, chats,
                         blocking_runner=ImmediateRunner(), category_resolver=get_document_category)
    answerer = AnsweringService(
        agent_service=agent, intent_classifier=Classifier(),
        history_rewriting_service=rewriter, text_processor=Processor(),
        blocking_runner=ImmediateRunner(), category_resolver=get_document_category,
        selection_validator=lambda docs: [d for d in docs if d in (*SOURCES, 'New_FAQ')],
        history_provider=agent.history_provider,
    )
    return chats, rag, answerer


@pytest.mark.parametrize('binding', [None, 'hibank', 'negahboom', 'obsolete'])
@pytest.mark.parametrize('mode', [None, 'hibank', 'negahboom', 'auto', 'obsolete'])
def test_real_web_session_switches_with_history_and_scoped_evidence(setup, monkeypatch, mode, binding):  # noqa: F811
    if mode is None: monkeypatch.delenv('CHATBOT_PLATFORM', raising=False)
    else: monkeypatch.setenv('CHATBOT_PLATFORM', mode)
    db = MemoryDb(binding)
    chats, rag, answerer = pipeline(db)
    monkeypatch.setattr(main, 'db_manager', db)
    monkeypatch.setattr(main, 'chat_manager', chats)
    monkeypatch.setattr(main, 'agent_service', answerer.agent_service)
    monkeypatch.setattr(main, 'answering_service', answerer)
    monkeypatch.setattr(main.app.state, 'request_limiter', AdmissionLimiter(2), raising=False)
    # Authentication continues using the isolated fixture's user registry.
    db.get_web_user_by_id = setup.get_web_user_by_id
    with TestClient(main.app) as client:
        login(client, 'alice')
        created = client.post('/api/sessions', json={}, headers=csrf(client))
        assert created.status_code == 200 and created.json()['id'] == 12
        for i, title in enumerate((*SOURCES, 'New_FAQ')):
            headers = csrf(client)
            if i: headers['X-Chatbot-Platform'] = ('hibank', 'obsolete', 'negahboom')[i-1]
            response = client.post('/api/query', json={'session_id': 12, 'query': 'synthetic', 'documents': [title]}, headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()['related_questions']
            # Actual FAQ model message contains current evidence only, no previous assistant data.
            call = rag._completion.await_args.kwargs['messages']
            expected = NegahBoomPrompts if title == 'NegahBoom_FAQ' else Config
            assert call[0]['content'] == expected.GENERAL_RAG_SYSTEM_PROMPT
            assert f'evidence_{title}' in call[1]['content']
            assert 'old service details' not in call[1]['content']
            assert all(f'evidence_{other}' not in call[1]['content'] for other in set(SOURCES) - {title})
        assert len(db.messages) == 8
        assert len(db.metadata['agent_state']['messages']) == 10
        assert db.metadata['agent_state']['messages'][0]['content'] == 'previous reference'
        assert db.metadata['other'] == {'keep': True}
        assert db.metadata.get('chatbot_platform') == binding
        assert db.metadata['agent_state']['platform'] == (binding or 'obsolete')
        assert len(client.get('/api/sessions', headers={'X-Chatbot-Platform': 'obsolete'}).json()['sessions']) == 3
        assert len(client.get('/api/sessions/12/messages').json()['messages']) == 8
        assert client.get('/api/sessions/12/download').status_code == 200
        assert [c.kwargs['allowed_docs'] for c in rag.retrieve.await_args_list] == [[t] for t in (*SOURCES, 'New_FAQ')]
        # Rewriter precedes answer and uses this turn's family even with legacy binding.
        rewrite_calls = [c.kwargs['messages'][1]['content'] for c in rag._completion.await_args_list
                         if c.kwargs['messages'][0]['content'] == 'You are a helpful assistant.']
        assert len(rewrite_calls) == 4
        assert NegahBoomPrompts.QUERY_REWRITE_PROMPT.format(current_query='synthetic', current_history='SENTINEL').split('SENTINEL')[0] in rewrite_calls[1]
        assert Config.QUERY_REWRITE_PROMPT.format(current_query='synthetic', current_history='SENTINEL').split('SENTINEL')[0] in rewrite_calls[2]


@pytest.mark.parametrize('binding', [None, 'hibank', 'negahboom'])
def test_same_mobile_uuid_source_switches(binding, monkeypatch):
    monkeypatch.setattr(mobile_api, "AnswerRequestContext", AnswerRequestContext)
    async def run():
        db = MemoryDb(binding)
        chats, rag, answerer = pipeline(db)
        req = request_with(chats, answerer)
        for i, title in enumerate(SOURCES):
            req.headers = {} if not i else {'X-Chatbot-Platform': 'obsolete'}
            reply = await mobile_api.gateway_talk(mobile_api.TalkRequest(
                session_id='mobile-uuid', national_code='synthetic', query='synthetic', documents=[title]), req)
            assert reply.session_id == 'mobile-uuid'
            assert reply.related_questions
        assert len(db.messages) == 6
        assert [c.kwargs['allowed_docs'] for c in rag.retrieve.await_args_list] == [[s] for s in SOURCES]
        history = await mobile_api.gateway_history(req, 'synthetic', 'mobile-uuid')
        assert len(history['messages']) == 6
        assert len((await mobile_api.gateway_history(req, 'synthetic'))['sessions']) == 3
    asyncio.run(run())


def test_mixed_and_optional_source_fallback_are_order_independent():
    for docs in [('General_FAQ','NegahBoom_FAQ'), ('NegahBoom_FAQ','General_FAQ'),
                 ('NegahBoom_FAQ','New_FAQ')]:
        assert select_prompt_context(docs).family == 'mixed'
    assert select_prompt_context(['New_FAQ']).family == 'hibank'
    assert select_prompt_context([]).family == 'hibank'
    assert select_prompt_context(['NegahBoom_FAQ'] * 2).family == 'negahboom'
    assert all(get_document_category(title) == 'FAQ' for title in SOURCES)


def test_mixed_fake_model_answer_chitchat_rewrite_and_concurrency():
    async def run():
        rag = make_rag()
        rewriter = load_rewriter()(rag, None)
        response = rag._completion.return_value
        async def completion(**kwargs):
            await asyncio.sleep(0)
            return response
        rag._completion.side_effect = completion
        for docs in [('General_FAQ', 'NegahBoom_FAQ'), ('NegahBoom_FAQ', 'General_FAQ')]:
            context = select_prompt_context(docs)
            for category in ('FAQ','chitchat', 'قرارداد ها', 'ابلاغیه ها'):
                await rag.answer('synthetic', 'current evidence', '', '', '', '', category=category, prompt_context=context)
                messages = rag._completion.await_args.kwargs['messages']
                expected = (MixedSourcePrompts.GENERAL_RAG_SYSTEM_PROMPT if category == 'FAQ' else MixedSourcePrompts.CHITCHAT_SYSTEM_PROMPT if category == 'chitchat' else MixedSourcePrompts.DOCUMENT_RAG_SYSTEM_PROMPT)
                assert messages[0]['content'] == expected
            await rewriter.rewrite_query('synthetic', 'User: reference', prompt_context=context)
            assert rag._completion.await_args.kwargs['messages'][1]['content'] == MixedSourcePrompts.QUERY_REWRITE_PROMPT.format(current_query='synthetic',current_history='User: reference')
        # Same shared clients, independent local bundles.
        async def turn(docs):
            await rag.answer(str(docs), 'evidence', '', '', '', '', category='FAQ', prompt_context=select_prompt_context(docs))
        await asyncio.gather(*(turn(docs) for docs in [('General_FAQ',), ('NegahBoom_FAQ',), SOURCES[:2]] * 10))
        expected = {'hibank': Config, 'negahboom': NegahBoomPrompts, 'mixed': MixedSourcePrompts}
        for call in rag._completion.await_args_list[-30:]:
            messages = call.kwargs['messages']
            user = messages[1]['content']
            family = 'mixed' if 'General_FAQ' in user and 'NegahBoom_FAQ' in user else 'negahboom' if 'NegahBoom_FAQ' in user else 'hibank'
            assert messages[0]['content'] == expected[family].GENERAL_RAG_SYSTEM_PROMPT
    asyncio.run(run())


class RacingDatabase(database_module.DatabaseManager):
    def __init__(self):
        self.row = None
        self.lock = threading.Lock()
        self.first_reads = threading.Barrier(2)
        self.local = threading.local()

    def get_session_by_uuid(self, uuid):
        if not getattr(self.local, 'read', False):
            self.local.read = True
            self.first_reads.wait(timeout=5)
            return None
        with self.lock: return copy.deepcopy(self.row)

    def _execute(self, sql, params=None, fetch=None):
        with self.lock:
            if 'INSERT' in sql:
                assert 'ON CONFLICT (uuid) DO NOTHING' in sql
                if self.row: return None
                self.row = session_row(12, user_id=params[1], meta_data=json.loads(params[3]))
                return copy.deepcopy(self.row)
            assert "COALESCE(meta_data::jsonb, '{}'::jsonb) || %s::jsonb" in sql
            self.row['meta_data'].update(json.loads(params[0]))


@pytest.mark.parametrize('users', [(7,7), (7,25)])
def test_concurrent_uuid_creation_and_atomic_unrelated_metadata_merge(users):
    db = RacingDatabase()
    def create(user):
        try: return db.get_or_create_mobile_session(user, 'synthetic-uuid')
        except database_module.SessionUnavailableError: return None
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(create, users))
    assert sum(r is not None for r in results) == (2 if users[0] == users[1] else 1)
    assert all(r['user_id'] == db.row['user_id'] for r in results if r)
    assert db.row['meta_data'] == {}
    db.row['meta_data'] = {'chatbot_platform': 'obsolete', 'other': True}
    db.update_session_metadata(12, {'agent_state': {'messages': []}})
    assert db.row['meta_data'] == {'chatbot_platform': 'obsolete', 'other': True, 'agent_state': {'messages': []}}


def test_web_creation_sql_has_empty_metadata():
    db = database_module.DatabaseManager.__new__(database_module.DatabaseManager)
    captured = []
    db._execute = lambda sql, params, **kw: captured.append((sql, params)) or {'meta_data': json.loads(params[5])}
    assert db.create_session(7)['meta_data'] == {}
    assert 'chatbot_platform' not in captured[0][0]


@pytest.mark.parametrize('binding', ['hibank', 'negahboom', None])
def test_old_header_cannot_block_mobile_close_or_override_owner(binding):
    async def run():
        row = session_row(12, uuid='mobile-uuid', meta_data={'chatbot_platform': binding})
        db = StatefulCloseDatabase(row)
        chats = database_module.ChatManager(db)
        req = request_with(chats)
        req.headers = {'X-Chatbot-Platform': 'obsolete'}
        db.row['user_id'] = 99
        with pytest.raises(database_module.SessionUnavailableError):
            await mobile_api.gateway_close_session('mobile-uuid', mobile_api.CloseSessionRequest(national_code='synthetic'), req)
        assert db.row['status'] == 'active'
        db.row['user_id'] = 7
        await mobile_api.gateway_close_session('mobile-uuid', mobile_api.CloseSessionRequest(national_code='synthetic'), req)
        assert db.row['status'] == 'closed' and db.row['meta_data'] == row['meta_data']
    asyncio.run(run())


def test_original_prompt_definitions_are_identical_to_head():
    current = ast.parse(Path('new_architecture/app/config.py').read_text())
    definitions = {
        node.name if isinstance(node, ast.ClassDef) else node.targets[0].id: node
        for node in current.body if isinstance(node, (ast.ClassDef, ast.Assign))
    }
    for name in ('new_architecture/app/config.py',):
        original = ast.parse(subprocess.check_output(['git', 'show', f'HEAD:{name}']))
        for node in original.body:
            if isinstance(node, (ast.ClassDef, ast.Assign)):
                key = node.name if isinstance(node, ast.ClassDef) else node.targets[0].id
                assert ast.dump(definitions[key]) == ast.dump(node), key


def test_evaluation_legacy_state_switches_and_batch_is_stateless():
    class Provider:
        namespace = 'evaluation'
        def __init__(self):
            self.state = {'platform': 'obsolete', 'allowed_docs': ['STALE_FAQ'],
                          'messages': [{'role':'user', 'content':'reference'},
                                       {'role':'assistant', 'content':'old service details'}]}
        async def load_snapshot(self, key):
            return ConversationSnapshot(key, 1, copy.deepcopy(self.state), {'chatbot_platform':'negahboom'})
        async def load_rewrite_messages(self, key): return self.state['messages']
        async def save_snapshot(self, snapshot, final_state): self.state = copy.deepcopy(final_state)

    async def run():
        db = MemoryDb('hibank')
        _, rag, service = pipeline(db)
        provider = Provider()
        before = copy.deepcopy(db.metadata)
        for title in SOURCES:
            result = await service.answer(AnswerRequestContext(
                original_query='synthetic', selected_documents=(title,),
                conversation_key=('eval-session','synthetic'), channel='evaluation'),
                history_provider=provider, execution_policy=EVALUATION_EXECUTION_POLICY)
            assert result.related_questions
        assert len(provider.state['messages']) == 8
        assert db.metadata == before and db.messages == []
        for title in SOURCES:
            await service.answer(AnswerRequestContext(
                original_query='synthetic', selected_documents=(title,), channel='mass_answer',
                use_history=False, persist_agent_state=False))
        assert db.metadata == before
        assert [c.kwargs['allowed_docs'] for c in rag.retrieve.await_args_list] == [[t] for t in SOURCES * 2]
        assert rag._completion.await_args.kwargs['messages'][0]['content'] == Config.GENERAL_RAG_SYSTEM_PROMPT
    asyncio.run(run())


def test_no_documents_ignores_old_identity_and_general_requires_current_selection():
    async def run():
        db = MemoryDb('negahboom')
        _, rag, service = pipeline(db)
        service.intent_classifier = Classifier('chitchat')
        result = await service.answer(AnswerRequestContext(original_query='hello',session_id='12'))
        assert result.related_questions == []
        assert rag._completion.await_args.kwargs['messages'][0]['content'] == Config.CHITCHAT_SYSTEM_PROMPT
        rag.retrieve.assert_not_awaited()
        service.intent_classifier = Classifier('general')
        with pytest.raises(ValueError, match='current datasource'):
            await service.answer(AnswerRequestContext(original_query='synthetic', session_id='12'))
        rag.retrieve.assert_not_awaited()
    asyncio.run(run())


def test_optional_association_and_unregistered_category_fallback(monkeypatch):
    import prompt_selection
    monkeypatch.setattr(prompt_selection, 'SOURCE_PROMPT_FAMILIES', {
        **prompt_selection.SOURCE_PROMPT_FAMILIES, 'Additional_FAQ': 'negahboom',
    })
    for docs in [('Additional_FAQ', 'NegahBoom_FAQ'), ('NegahBoom_FAQ', 'Additional_FAQ')]:
        assert select_prompt_context(docs).family == 'negahboom'
    for title in ['Unregistered source', 'قرارداد نمونه', 'ابلاغیه نمونه', 'Other_FAQ']:
        assert select_prompt_context([title]).family == 'hibank'


def test_mixed_selection_runs_real_graph_with_both_current_sources():
    async def run():
        db = MemoryDb('hibank')
        _, rag, service = pipeline(db)
        for docs in [('General_FAQ', 'NegahBoom_FAQ'), ('NegahBoom_FAQ', 'General_FAQ')]:
            result = await service.answer(AnswerRequestContext(
                original_query='synthetic', session_id='12', selected_documents=docs))
            assert result.related_questions
            messages = rag._completion.await_args.kwargs['messages']
            assert messages[0]['content'] == MixedSourcePrompts.GENERAL_RAG_SYSTEM_PROMPT
            assert all(f'evidence_{title}' in messages[1]['content'] for title in docs)
            assert 'old service details' not in messages[1]['content']
        assert len(db.metadata['agent_state']['messages']) == 6
    asyncio.run(run())
