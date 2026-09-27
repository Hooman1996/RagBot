"""Role-to-route authorization through the real ASGI middleware and route matcher."""
from fastapi.routing import APIRoute
from datetime import datetime
from fastapi.responses import Response
from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
import pytest

import main
import kb_manager
from tests.test_web_auth import setup, login, csrf
from web_permissions import PERMISSIONS, ROLE_PERMISSIONS, route_permission


# Independent expected inventory: method and FastAPI route path -> grant.
EXPECTED = {
    ('GET', '/app'): 'chat', ('POST', '/api/query'): 'chat',
    ('GET', '/api/sessions'): 'sessions', ('POST', '/api/sessions'): 'sessions',
    ('GET', '/api/sessions/{session_id}'): 'sessions',
    ('DELETE', '/api/sessions/{session_id}'): 'sessions',
    ('POST', '/api/sessions/{session_id}/message'): 'sessions',
    ('GET', '/api/sessions/{session_id}/messages'): 'sessions',
    ('PATCH', '/api/sessions/{session_id}/pin'): 'sessions',
    ('POST', '/api/sessions/{session_id}/satisfaction'): 'sessions',
    ('GET', '/api/sessions/{session_id}/download'): 'downloads',
    ('PATCH', '/api/queries/{query_id}/feedback'): 'feedback',
    ('PATCH', '/api/queries/{query_id}/comment'): 'feedback',
    ('GET', '/api/documents'): 'documents',
    ('GET', '/api/ocr/status'): 'ocr', ('POST', '/api/ocr/extract'): 'ocr',
    ('GET', '/analytics'): 'analytics', ('GET', '/api/analytics'): 'analytics',
    ('GET', '/knowledge-base/'): 'kb_page',
    ('GET', '/knowledge-base/api/documents'): 'kb_read',
    ('GET', '/knowledge-base/api/chunks/{document_id}'): 'kb_read',
    ('GET', '/knowledge-base/api/chunks/{chunk_id}/versions'): 'kb_read',
    ('POST', '/knowledge-base/api/chunks/create'): 'kb_write',
    ('PUT', '/knowledge-base/api/chunks/update'): 'kb_write',
    ('DELETE', '/knowledge-base/api/chunks/delete/{chunk_id}'): 'kb_write',
    ('POST', '/knowledge-base/api/chunks/revert'): 'kb_write',
    ('POST', '/api/mass-answer'): 'batch',
    ('GET', '/api/mass-answer/jobs/{job_id}'): 'batch',
    ('GET', '/api/mass-answer/jobs/{job_id}/result'): 'batch',
    ('DELETE', '/api/mass-answer/jobs/{job_id}'): 'batch',
    ('POST', '/api/mass-answer/jobs/cleanup'): 'system',
    ('POST', '/api/initialize'): 'system',
    ('GET', '/api/metrics/admission'): 'system',
}
EXEMPT = {
    ('GET', '/'), ('POST', '/api/login'), ('GET', '/api/health'),
    ('GET', '/api/auth/me'), ('POST', '/api/auth/logout'),
    ('GET', '/access-denied'),
}


def concrete(path):
    for name in ('session_id', 'query_id', 'document_id', 'chunk_id', 'job_id'):
        path = path.replace('{' + name + '}', '123')
    return path


def test_complete_browser_route_inventory_matches_fastapi():
    seen = set()
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith(('/api/mobile/', '/api/internal/evaluation/')):
            continue
        for method in route.methods:
            key = (method, route.path)
            seen.add(key)
            assert key in EXPECTED or key in EXEMPT, key
            if key in EXPECTED:
                assert route_permission(method, concrete(route.path)) == EXPECTED[key], key
    assert seen == set(EXPECTED) | set(EXEMPT)
    assert set(ROLE_PERMISSIONS['admin']) == PERMISSIONS


@pytest.mark.parametrize('role', ['admin', 'user', 'analytics_viewer', 'knowledge_editor', 'dashboard_viewer', 'moderator', 'surprise_role'])
def test_role_by_api_route_matrix(setup, monkeypatch, role):
    # Stub only endpoint execution; middleware, route matching, cookies, and CSRF are real.
    async def endpoint_stub(scope, receive, send):
        await Response(status_code=204)(scope, receive, send)
    for route in main.app.routes:
        if isinstance(route, APIRoute) and any((m, route.path) in EXPECTED for m in route.methods):
            monkeypatch.setattr(route, 'app', endpoint_stub)
    setup.users[1]['role'] = role
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        grants = ROLE_PERMISSIONS.get(role, frozenset())
        for (method, path), permission in EXPECTED.items():
            if not path.startswith(('/api/', '/knowledge-base/api/')):
                continue
            headers = csrf(client) if method not in ('GET', 'HEAD') else {}
            response = client.request(method, concrete(path), headers=headers, json={} if method != 'GET' else None)
            assert response.status_code == (204 if permission in grants else 403), (role, method, path, response.status_code)
            if permission not in grants:
                assert response.json()['required_permission'] == permission


@pytest.mark.parametrize('role,landing,allowed_page,forbidden_page', [
    ('admin', '/app', '/app', None),
    ('user', '/app', '/app', '/analytics'),
    ('moderator', '/app', '/app', '/knowledge-base/'),
    ('analytics_viewer', '/analytics', '/analytics', '/app'),
    ('knowledge_editor', '/knowledge-base/', '/knowledge-base/', '/analytics'),
    ('dashboard_viewer', '/app', '/app', None),
    ('surprise_role', '/access-denied', '/access-denied', '/app'),
])
def test_login_landing_pages_and_forged_links(setup, role, landing, allowed_page, forbidden_page):
    setup.users[1]['role'] = role
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = login(client, 'alice')
        assert response.json()['landing_path'] == landing
        assert response.json()['user']['landing_path'] == landing
        assert client.get('/api/auth/me').json()['user']['permissions'] == sorted(ROLE_PERMISSIONS.get(role, ()))
        assert client.get(allowed_page).status_code == 200
        if forbidden_page:
            forbidden = client.get(forbidden_page, follow_redirects=False)
            assert forbidden.status_code == 403
            assert 'Access denied' in forbidden.text
        unknown = client.get('/api/hidden-admin/export')
        assert unknown.status_code == 403
        assert unknown.json()['required_permission'] is None
        assert client.get('/new-protected-page', follow_redirects=False).status_code == 403
        assert client.post('/api/auth/me', headers=csrf(client)).status_code == 403
        assert client.get('/api/login').status_code == 403
        assert client.get('/api/internal/evaluation/v2/future').status_code == 403


def test_unauthenticated_and_current_role_changes(setup):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.get('/api/analytics').status_code == 401
        assert client.get('/new-protected-page', follow_redirects=False).status_code == 303
        login(client, 'alice')
        assert client.get('/api/analytics').status_code == 403
        setup.users[1]['role'] = 'analytics_viewer'
        assert client.get('/app', follow_redirects=False).status_code == 403
        assert client.get('/api/auth/me').json()['user']['landing_path'] == '/analytics'
        setup.users[1]['is_active'] = False
        assert client.get('/api/auth/me').status_code == 401


def test_csrf_and_separate_mobile_evaluation_contracts(setup):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        assert client.post('/api/sessions', json={}).status_code == 403
        assert client.post('/api/sessions', json={}, headers=csrf(client)).status_code != 403
        forbidden = client.post('/api/initialize', json={}, headers=csrf(client))
        assert forbidden.status_code == 403
        assert forbidden.json()['required_permission'] == 'system'
        forged = client.get('/api/analytics?role=admin', headers={'X-Role': 'admin', 'X-Permissions': 'analytics', 'X-User-Id': '2'})
        assert forged.status_code == 403
        assert client.post('/api/mobile/v1/talk', json={}).status_code != 403
        assert client.post('/api/internal/evaluation/v1/turn', json={}).status_code != 403


def test_logout_controls_and_permission_aware_links(setup):
    pages = [('/app', 'Log out', '.topbar__actions'),
             ('/analytics', 'Log out', '.topbar__actions'),
             ('/knowledge-base/', 'خروج', 'header')]
    setup.users[1]['role'] = 'admin'
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        for path, label, container in pages:
            soup = BeautifulSoup(client.get(path).text, 'html.parser')
            group = soup.select_one(container + ' .web-header-controls')
            assert group is not None, path
            buttons = group.select('button.web-logout')
            assert len(buttons) == 1, path
            button = buttons[0]
            assert button.get('type') == 'button'
            assert button.get('title') == button.get('aria-label') == label
            assert button.select_one('svg[aria-hidden="true"]') is not None
            assert label in button.get_text()
        assert BeautifulSoup(client.get('/analytics').text, 'html.parser').select_one('a[href="/knowledge-base"]')
        setup.users[1]['role'] = 'user'
        soup = BeautifulSoup(client.get('/app').text, 'html.parser')
        assert not soup.select('a[href="/analytics"], a[href="/knowledge-base"], #batch-upload-btn')
        css = client.get('/static/css/web_controls.css').text
        assert '.web-logout:focus-visible' in css
        assert '@media (max-width: 700px)' in css
        assert 'body.light-mode .web-logout' in css
        assert 'body.rtl .web-logout svg' in css
        assert 'position: static' in css  # language control stays in its header group
        assert 'body[data-can-write="false"] .kb-write-action' in css
        login_html = client.get('/').text
        assert 'window.location.href = result.landing_path' in login_html
        assert 'data-i18n="logout"' in client.get('/app').text


def test_dashboard_viewer_exact_grants_navigation_and_read_only_template(setup):
    expected = ROLE_PERMISSIONS['user'] | {'analytics', 'kb_page', 'kb_read'}
    assert ROLE_PERMISSIONS['dashboard_viewer'] == expected
    assert not expected & {'kb_write', 'batch', 'system'}
    setup.users[1]['role'] = 'dashboard_viewer'
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        me = client.get('/api/auth/me').json()['user']
        assert me['role'] == 'dashboard_viewer'
        assert me['permissions'] == sorted(expected)
        assert me['landing_path'] == '/app'
        for page, links in (('/app', ('/analytics', '/knowledge-base')),
                            ('/analytics', ('/app', '/knowledge-base')),
                            ('/knowledge-base/', ('/app', '/analytics'))):
            soup = BeautifulSoup(client.get(page).text, 'html.parser')
            for link in links:
                assert soup.select_one(f'a[href="{link}"]'), (page, link)
        kb = BeautifulSoup(client.get('/knowledge-base/').text, 'html.parser')
        assert kb.select_one('#kb-read-only-indicator')
        assert kb.body['data-can-write'] == 'false'
        assert not kb.select('textarea, #new-chunk-operator-name, #add-chunk-modal-overlay')
        assert kb.select_one('#history-modal-overlay')
        setup.users[1]['role'] = 'user'
        assert client.get('/api/auth/me').json()['user']['permissions'] == sorted(ROLE_PERMISSIONS['user'])
        assert client.get('/knowledge-base/', follow_redirects=False).status_code == 403


def test_dashboard_viewer_chat_ownership_and_csrf_remain_in_force(setup):
    setup.users[1]['role'] = 'dashboard_viewer'
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        assert client.get('/api/sessions').status_code == 200
        assert client.get('/api/sessions/20').status_code == 404
        assert client.get('/api/sessions/20/messages').status_code == 404
        assert client.get('/api/sessions/20/download').status_code == 404
        assert client.patch('/api/queries/200/feedback', json={'is_helpful': 1}, headers=csrf(client)).status_code == 404
        assert client.post('/api/sessions', json={}).status_code == 403
        assert client.post('/api/sessions', json={}, headers=csrf(client)).status_code != 403


@pytest.mark.parametrize('role', ['admin', 'knowledge_editor'])
def test_kb_editors_keep_write_interface(setup, role):
    setup.users[1]['role'] = role
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        kb = BeautifulSoup(client.get('/knowledge-base/').text, 'html.parser')
        assert kb.body['data-can-write'] == 'true'
        assert kb.select_one('#add-chunk-modal-overlay textarea')
        assert kb.select_one('#new-chunk-operator-name')
        assert not kb.select_one('#kb-read-only-indicator')


@pytest.mark.parametrize('populated', [False, True])
def test_dashboard_viewer_kb_read_endpoints_return_empty_or_populated_data(setup, monkeypatch, populated):
    class Cursor:
        def execute(self, query, params=None):
            self.query = query

        def fetchall(self):
            if not populated:
                return []
            if 'FROM chunk_versions' in self.query:
                return [{'id': 9, 'content': 'question: How?\nanswer: Safely.',
                         'changed_by': 'Editor', 'created_at': datetime(2026, 9, 27)}]
            if 'FROM chunks' in self.query:
                return [{'id': 7, 'content': 'Full chunk content', 'chunk_index': 0}]
            return [{'id': 3, 'title': 'Document', 'filename': 'document.pdf'}]

        def close(self):
            pass

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(kb_manager, 'get_db_connection', Connection)
    setup.users[1]['role'] = 'dashboard_viewer'
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        documents = client.get('/knowledge-base/api/documents')
        chunks = client.get('/knowledge-base/api/chunks/3?search=Full')
        versions = client.get('/knowledge-base/api/chunks/7/versions')
        assert (documents.status_code, chunks.status_code, versions.status_code) == (200, 200, 200)
        assert len(documents.json()['documents']) == int(populated)
        assert len(chunks.json()['chunks']) == int(populated)
        assert len(versions.json()['versions']) == int(populated)
        if populated:
            assert chunks.json()['chunks'][0]['answer'] == 'Full chunk content'
            assert versions.json()['versions'][0]['answer'] == 'Safely.'
