"""Real HTTP authorization/CSRF with explicitly synthetic KB stores."""
from datetime import datetime
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
import main
import kb_manager
from tests.test_web_auth import setup,login,csrf
from tests import test_kb_manager_chunk_create as create_fixtures
from tests.test_faq_taxonomy import CONTENT,QUESTION,ANSWER
from tests.test_knowledge_update_consistency import SharedPostgresState,FakeRepository,FakeVectorStore,CacheInvalidator,fake_vector
from new_architecture.knowledge_update import KnowledgeUpdateCoordinator,VectorPoint
from utils.faq_content import parse_faq_content


@pytest.fixture
def stores(setup,monkeypatch):
    state=SharedPostgresState();state.content=CONTENT;state.vector=fake_vector(CONTENT);state.versions=[CONTENT]
    vectors=FakeVectorStore();vectors.point=VectorPoint(1,state.vector,dict(content=CONTENT,text=CONTENT))
    cache=CacheInvalidator()
    coordinator=KnowledgeUpdateCoordinator(repository_factory=lambda:FakeRepository(state),vector_store=vectors,
        embed_content=fake_vector,invalidate_local_cache=cache)
    monkeypatch.setattr(main,'rag_system',Mock())
    monkeypatch.setattr(main,'qdrant_client',Mock())
    monkeypatch.setattr(kb_manager,'_knowledge_update_coordinator',lambda module:coordinator)
    def connection():
        cursor=Mock()
        cursor.fetchone.return_value={'content': f'question: {QUESTION}\nanswer: historical fact'}
        conn=Mock();conn.cursor.return_value=cursor
        return conn
    monkeypatch.setattr(kb_manager,'get_db_connection',connection)
    return state,vectors,cache


def payload(**metadata):
    values=dict(chunk_id=1,is_qa=True,question=QUESTION,answer=ANSWER+' Changed.')
    values.update(metadata)
    return values


@pytest.mark.parametrize('role,expected',[('knowledge_editor',200),('admin',200),('dashboard_viewer',403),('user',403)])
def test_taxonomy_update_actual_handler_auth_csrf_and_store_consistency(setup,stores,role,expected):
    setup.users[1]['role']=role
    state,vectors,cache=stores
    with TestClient(main.app) as client:
        login(client,'alice')
        assert client.put('/knowledge-base/api/chunks/update',json=payload()).status_code==403
        response=client.put('/knowledge-base/api/chunks/update',headers=csrf(client),json=payload(main_category='other'))
        assert response.status_code==expected
        if expected==200:
            assert response.json()['main_category']=='other'
            assert response.json()['sub_category'] is None
            assert state.content==vectors.point.payload['content']==state.versions[-1]
            assert cache.calls==1
        else:
            assert state.content==CONTENT
            assert cache.calls==0


def test_payload_conflicts_and_legacy_ambiguity_reject_before_writes(setup,stores):
    setup.users[1]['role']='knowledge_editor'
    state,vectors,cache=stores
    with TestClient(main.app) as client:
        login(client,'alice')
        for data in [payload(category='a',main_category='b'),payload(main_category=None,sub_category='orphan'),
            payload(answer=ANSWER+'\nquestion category: one\nquestion category: two')]:
            response=client.put('/knowledge-base/api/chunks/update',headers=csrf(client),json=data)
            assert response.status_code==422
    assert state.content==CONTENT and vectors.upsert_count==0 and cache.calls==0


def test_actual_revert_handler_restores_uncategorized_version_without_current_taxonomy(setup,stores):
    setup.users[1]['role']='knowledge_editor'
    state,vectors,cache=stores
    with TestClient(main.app) as client:
        login(client,'alice')
        response=client.post('/knowledge-base/api/chunks/revert',headers=csrf(client),json={'chunk_id':1,'version_id':9})
        assert response.status_code==200
    assert parse_faq_content(state.content).main_category is None
    assert state.content==vectors.point.payload['content']==state.versions[-1]
    assert cache.calls==1


def test_read_responses_include_clean_taxonomy_and_version_specific_absence(setup,monkeypatch):
    setup.users[1]['role']='dashboard_viewer'
    def connection():
        cursor=Mock()
        rows=[{'id':1,'chunk_index':0,'content':CONTENT}]
        versions=[{'id':9,'content':CONTENT,'changed_by':'synthetic','created_at':datetime(2026,10,13)},
            {'id':8,'content':f'question: {QUESTION}\nanswer: historical fact','changed_by':'synthetic','created_at':datetime(2026,10,12)}]
        cursor.execute.side_effect=lambda sql,params:setattr(cursor,'data',versions if 'chunk_versions' in sql else rows)
        cursor.fetchall.side_effect=lambda:cursor.data
        conn=Mock();conn.cursor.return_value=cursor
        return conn
    monkeypatch.setattr(kb_manager,'get_db_connection',connection)
    with TestClient(main.app) as client:
        login(client,'alice')
        item=client.get('/knowledge-base/api/chunks/7').json()['chunks'][0]
        assert item['answer']==ANSWER and item['main_category']=='synthetic' and item['sub_category']=='review'
        versions=client.get('/knowledge-base/api/chunks/1/versions').json()['versions']
        assert versions[1]['main_category'] is None
        assert 'question category' not in versions[0]['answer']


def test_editor_labels_local_assets_and_read_only_controls(setup):
    with TestClient(main.app) as client:
        login(client,'alice')
        setup.users[1]['role']='knowledge_editor'
        soup=BeautifulSoup(client.get('/knowledge-base/').text,'html.parser')
        for field in ('new-chunk-main-category','new-chunk-sub-category'):
            assert soup.find('label',attrs={'for':field})
            assert soup.find(id=field)['dir']=='auto'
            assert soup.find(id=field)['aria-describedby']=='new-taxonomy-help'
        assert soup.find(id='global-toast')['aria-live']=='polite'
        setup.users[1]['role']='dashboard_viewer'
        soup=BeautifulSoup(client.get('/knowledge-base/').text,'html.parser')
        assert soup.find(id='new-chunk-main-category') is None
