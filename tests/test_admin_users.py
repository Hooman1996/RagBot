"""Real HTTP/session policy and provisioning/authentication with synthetic in-memory SQL."""
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import Mock
import asyncio
import json
import threading

import bcrypt
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import psycopg2
import pytest

import main
import web_user_accounts as accounts
from new_architecture.app.services.authentication.authentication import AuthenticationService
from tests.test_web_auth import setup, login, csrf
from utils.concurrency import BoundedBlockingRunner
from utils.http_logging_middleware import HttpLoggingMiddleware, route_log_policy
from utils.structured_logging import LoggingSettings
from web_auth import SESSION_COOKIE
from web_permissions import ROLE_PERMISSIONS, permissions_for_user


PAYLOAD = dict(username='New.User', email='New.User@example.test', full_name=' New User ',
               role='user', password='رمز🔑é', confirm_password='رمز🔑é')


class UniqueViolation(psycopg2.errors.UniqueViolation):
    pgcode = '23505'

    def __init__(self, field):
        self.field = field

    @property
    def diag(self):
        return SimpleNamespace(constraint_name='users_' + self.field + '_key')


class Connection:
    def __init__(self, records, failure=None):
        self.records, self.failure = records, failure
        self.queries, self.pending, self.cursors = [], None, []
        self.commits = self.rollbacks = 0
        self.closed = False

    def cursor(self, **kwargs):
        cursor = Cursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        if self.failure == 'commit':
            raise psycopg2.OperationalError('private-db-credential')
        self.commits += 1
        if self.pending:
            self.records.append(self.pending)
        self.pending = None

    def rollback(self):
        self.rollbacks += 1
        self.pending = None

    def close(self):
        self.closed = True


class Cursor:
    def __init__(self, conn):
        self.conn, self.result, self.closed = conn, None, False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def execute(self, sql, params):
        self.conn.queries.append((sql, params))
        if 'SELECT username, email' in sql:
            self.result = [(r['username'], r['email']) for r in self.conn.records
                           if r['username'] == params[0] or r['email'] == params[1]]
        elif 'INSERT INTO users' in sql:
            if self.conn.failure in ('username', 'email', 'uuid'):
                raise UniqueViolation(self.conn.failure)
            if self.conn.failure == 'insert':
                raise psycopg2.OperationalError('private-db-credential')
            self.conn.pending = dict(zip(('uuid', 'email', 'username', 'password_hash', 'full_name',
                                         'role', 'settings', 'created_at', 'updated_at'), params))
            self.conn.pending.update(id=101, is_active=True, is_verified=False, last_login_at=None)
            self.result = (101,)
        elif 'SELECT id,' in sql and 'password_hash' in sql:
            self.result = next((dict(r) for r in self.conn.records if r['username'] == params[0]), None)
        elif 'UPDATE users' in sql and 'last_login_at' in sql:
            next(r for r in self.conn.records if r['id'] == params[1])['last_login_at'] = params[0]
        else:
            raise AssertionError('Unexpected SQL')

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result


@pytest.fixture
def provision(setup, monkeypatch):
    setup.users[1]['role'] = 'admin'
    records, connections = [], []

    def get_connection():
        conn = Connection(records)
        connections.append(conn)
        return conn

    monkeypatch.setattr(setup, 'get_connection', get_connection, raising=False)
    return setup, records, connections


def test_admin_creates_with_generated_fields_and_existing_login_path(provision):
    db, records, connections = provision
    with TestClient(main.app) as client:
        login(client, 'alice')
        token = client.cookies[SESSION_COOKIE]
        page = client.get('/admin/users')
        assert page.status_code == 200 and page.headers['cache-control'] == 'no-store'
        soup = BeautifulSoup(page.text, 'html.parser')
        assert {o['value'] for o in soup.select('#user-role option')} == set(ROLE_PERMISSIONS)
        assert soup.select_one('#user-role option[selected]')['value'] == 'user'
        for field in accounts.CREATION_FIELDS:
            assert soup.select_one(f'label[for="user-{field}"]')
        response = client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client))
        assert response.status_code == 201
        summary = response.json()['user']
        assert set(summary) == {'id', 'uuid', 'username', 'email', 'full_name', 'role', 'is_active', 'is_verified'}
        assert summary['username'] == PAYLOAD['username'] and summary['email'] == PAYLOAD['email']
        assert summary['full_name'] == 'New User' and summary['role'] == 'user'
        assert type(summary['id']) is int and summary['is_active'] is True and summary['is_verified'] is False
        assert UUID(summary['uuid']).version == 4
        assert response.headers['cache-control'] == 'no-store' and 'set-cookie' not in response.headers
        assert client.cookies[SESSION_COOKIE] == token
        assert client.get('/api/auth/me').json()['user']['id'] == 1
        record = records[0]
        assert record['settings'] == '{}' and record['last_login_at'] is None
        assert record['created_at'] == record['updated_at'] and record['created_at'].tzinfo is None
        assert abs((accounts.datetime.now(accounts.timezone.utc).replace(tzinfo=None) - record['created_at']).total_seconds()) < 5
        insert, params = next((s, p) for s, p in connections[0].queries if 'INSERT' in s)
        assert 'id,' not in insert.replace('uuid,', '') and 'last_login_at' not in insert
        assert 'TRUE, FALSE, %s::jsonb' in insert
        assert not any(field in insert for field in ('national_code', 'bio', 'avatar_url'))
        assert PAYLOAD['username'] not in insert and '%s' in insert
        assert record['password_hash'] not in response.text and PAYLOAD['password'] not in response.text
        assert AuthenticationService(db).authenticate(PAYLOAD['username'], PAYLOAD['password'])['id'] == 101
        assert record['last_login_at'] is not None
        assert AuthenticationService(db).authenticate(PAYLOAD['username'], 'incorrect') is None
    assert all(c.closed and all(cur.closed for cur in c.cursors) for c in connections)
    assert connections[0].commits == 1


@pytest.mark.parametrize('role', list(ROLE_PERMISSIONS) + ['unknown'])
def test_all_role_page_and_creation_authorization(provision, role):
    db, records, connections = provision
    db.users[1]['role'] = role
    with TestClient(main.app) as client:
        login(client, 'alice')
        page = client.get('/admin/users', follow_redirects=False)
        response = client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client))
        assert page.status_code == (200 if role == 'admin' else 403)
        assert response.status_code == (201 if role == 'admin' else 403)
        assert 'no-store' in page.headers['cache-control']
    assert bool(records) == (role == 'admin')


@pytest.mark.parametrize('role', list(ROLE_PERMISSIONS) + ['unknown'])
def test_navigation_on_all_affected_pages(provision, monkeypatch, role):
    db, _, _ = provision
    db.users[1]['role'] = role
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED', 'true')
    from coverage_check import api
    if not any(getattr(route, 'path', None) == '/knowledge-coverage' for route in main.app.routes):
        api.mount(main.app)
    runtime = SimpleNamespace(settings=SimpleNamespace(run=SimpleNamespace(as_dict=lambda: {}),
                                                       upload_max_bytes=1000, max_rows=100))
    monkeypatch.setattr(main.app.state, 'coverage_check', runtime, raising=False)
    with TestClient(main.app) as client:
        login(client, 'alice')
        for page in ('/app', '/analytics', '/knowledge-base/', '/knowledge-coverage', '/admin/users'):
            response = client.get(page, follow_redirects=False)
            assert response.status_code in (200, 403), (role, page)
            if response.status_code == 200:
                links = BeautifulSoup(response.text, 'html.parser').select('a[href="/admin/users"]')
                assert len(links) == (1 if role == 'admin' else 0), (role, page)


def test_unauthenticated_csrf_origin_and_role_change(provision):
    db, records, connections = provision
    with TestClient(main.app) as client:
        assert client.get('/admin/users', follow_redirects=False).status_code == 303
        response = client.post('/api/admin/users', json=PAYLOAD)
        assert response.status_code == 401 and response.headers['cache-control'] == 'no-store'
        login(client, 'alice')
        for headers in ({}, {'X-CSRF-Token': 'wrong'}, {**csrf(client), 'Origin': 'https://evil.invalid'}):
            response = client.post('/api/admin/users', json=PAYLOAD, headers=headers)
            assert response.status_code == 403 and response.headers['cache-control'] == 'no-store'
        db.users[1]['role'] = 'user'
        assert client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client)).status_code == 403
    assert records == [] and connections == []


@pytest.mark.parametrize('field,value', [
    ('username', ''), ('username', ' x'), ('username', 'x y'), ('username', 'x\x7fy'), ('username', 'x'*101),
    ('email', 'a@b'), ('email', 'a@@b.c'), ('email', 'x'*250+'@a.test'), ('email', ' a@b.c'),
    ('full_name', '  '), ('full_name', 'x'*256), ('full_name', 'x\ny'),
    ('role', 'Admin'), ('role', 'unknown'), ('role', 'user '),
    ('password', ''), ('password', 'abc\x00def'), ('password', 'é'*37), ('password', 'a'*73),
    ('password', '\ud800'), ('confirm_password', 'رمز🔑e'),
    ('username', 3), ('role', ['admin']), ('password', {'secret': 'do-not-echo'}),
])
def test_invalid_fields_are_safe_and_never_open_database(provision, field, value, caplog):
    _, records, connections = provision
    payload = {**PAYLOAD, field: value}
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', content=json.dumps(payload),
                               headers={**csrf(client), 'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert set(response.json()) == {'detail', 'errors'}
    assert response.json()['errors']
    assert PAYLOAD['password'] not in response.text + caplog.text
    assert 'do-not-echo' not in response.text + caplog.text
    assert records == [] and connections == []


@pytest.mark.parametrize('payload', [[], None, {}, {**PAYLOAD, 'permissions': ['users_manage']},
    {**PAYLOAD, 'id': 42}, {**PAYLOAD, 'password_hash': 'private-hash'},
    {k: v for k, v in PAYLOAD.items() if k != 'email'}])
def test_only_documented_creation_fields(provision, payload):
    _, _, connections = provision
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', json=payload, headers=csrf(client))
        assert response.status_code == 422 and 'private-hash' not in response.text
    assert not connections


@pytest.mark.parametrize('field', ['username', 'email'])
def test_duplicates_never_overwrite(provision, field):
    _, records, connections = provision
    records.append({**PAYLOAD, 'username': 'existing', field: PAYLOAD[field]})
    original = records[0].copy()
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client))
        assert response.status_code == 409 and response.json()['errors'] == {field: 'duplicate'}
    assert records == [original] and connections[0].rollbacks == 1 and connections[0].closed


@pytest.mark.parametrize('failure,status,field', [('username',409,'username'), ('email',409,'email'),
    ('uuid',409,'form'), ('insert',503,None), ('commit',503,None), ('connect',503,None)])
def test_unique_race_and_database_failure_cleanup(provision, monkeypatch, failure, status, field, caplog):
    db, records, _ = provision
    conn = Connection(records, failure)
    def connect():
        if failure == 'connect':
            raise psycopg2.OperationalError('private-db-credential')
        return conn
    monkeypatch.setattr(db, 'get_connection', connect)
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client))
    assert response.status_code == status
    assert response.headers['cache-control'] == 'no-store'
    if field:
        assert response.json()['errors'] == {field: 'duplicate'}
    else:
        assert response.json()['errorCode'] == 'DEPENDENCY_UNAVAILABLE'
    assert 'private-db-credential' not in response.text + caplog.text
    assert records == []
    if failure != 'connect':
        assert conn.rollbacks == 1 and conn.closed and all(c.closed for c in conn.cursors)


@pytest.mark.parametrize('password', ['a'*72, 'é'*36, '🔑'*18, 'رمز کوتاه'])
def test_unicode_and_bcrypt_boundary(provision, password):
    _, records, _ = provision
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', json={**PAYLOAD, 'password': password,
                              'confirm_password': password}, headers=csrf(client))
    assert response.status_code == 201
    assert bcrypt.checkpw(password.encode(), records[0]['password_hash'].encode())


def test_logging_omits_even_malformed_bodies(provision):
    db, records, _ = provision
    logger = Mock()
    app = HttpLoggingMiddleware(main.app, settings=LoggingSettings(
        environment='test', request_body=True, response_body=True), logger=logger)
    assert not route_log_policy('/api/admin/users').request_body
    assert not route_log_policy('/api/admin/users').response_body
    with TestClient(app) as client:
        login(client, 'alice')
        for body in ('{"password":"NEVER-LOG-THIS", bad}', '["NEVER-LOG-THIS"]'):
            response = client.post('/api/admin/users', content=body,
                                   headers={**csrf(client), 'Content-Type': 'application/json'})
            assert response.status_code == 422 and 'NEVER-LOG-THIS' not in response.text
        response = client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client))
        assert response.status_code == 201
    logged = str(logger.mock_calls)
    for secret in ('NEVER-LOG-THIS', PAYLOAD['password'], records[0]['password_hash'], PAYLOAD['username']):
        assert secret not in logged


def test_hash_before_connection_and_write_uses_bounded_worker(provision, monkeypatch):
    db, records, _ = provision
    events = []
    original_hash, original_connect = accounts.hash_password, db.get_connection
    def hash_password(value):
        events.append(('hash', threading.get_ident()))
        return original_hash(value)
    def connect():
        events.append(('connect', threading.get_ident()))
        return original_connect()
    monkeypatch.setattr(accounts, 'hash_password', hash_password)
    monkeypatch.setattr(db, 'get_connection', connect)
    runner_options = []
    class Runner:
        async def run(self, function, *args, **kwargs):
            if function is accounts.create_browser_account:
                runner_options.append(kwargs)
            events.append(('loop', threading.get_ident()))
            runner = BoundedBlockingRunner(1)
            try:
                return await runner.run(function, *args, **kwargs)
            finally:
                await runner.aclose()
    monkeypatch.setattr(main, 'blocking_runner', Runner())
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client))
        assert response.status_code == 201
    assert runner_options == [{'wait_for_completion_on_cancel': True}]
    work = [(name, thread) for name, thread in events if name != 'loop']
    assert [name for name, _ in work] == ['hash', 'connect']
    assert work[0][1] == work[1][1]
    assert all(thread != work[0][1] for name, thread in events if name == 'loop')


def test_cancellation_waits_for_transaction_cleanup(provision, monkeypatch):
    db, records, _ = provision
    started, finish = threading.Event(), threading.Event()
    conn = Connection(records)
    original = conn.commit
    def commit():
        started.set()
        assert finish.wait(5)
        original()
    conn.commit = commit
    monkeypatch.setattr(db, 'get_connection', lambda: conn)
    async def scenario():
        runner = BoundedBlockingRunner(1)
        task = asyncio.create_task(runner.run(accounts.create_browser_account, db,
            accounts.validate_creation(PAYLOAD), wait_for_completion_on_cancel=True))
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(.01)
        assert not task.done() and runner.active_count == 1
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await runner.aclose()
        assert runner.active_count == 0
    asyncio.run(scenario())
    assert conn.closed and conn.commits == 1 and len(records) == 1



@pytest.mark.parametrize('role', list(ROLE_PERMISSIONS))
def test_admin_may_assign_each_supported_role(provision, role):
    _, records, _ = provision
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', json={**PAYLOAD, 'role': role}, headers=csrf(client))
        assert response.status_code == 201 and response.json()['user']['role'] == role
    assert records[0]['role'] == role


@pytest.mark.parametrize('failure', ['rollback', 'close', 'hash'])
def test_cleanup_and_hash_failures_never_expose_exception_details(provision, monkeypatch, failure, caplog):
    db, records, _ = provision
    conn = Connection(records, 'insert')
    monkeypatch.setattr(db, 'get_connection', lambda: conn)
    def fail(*args):
        raise RuntimeError('private-cleanup-credential')
    if failure == 'hash':
        monkeypatch.setattr(accounts, 'hash_password', fail)
    else:
        monkeypatch.setattr(conn, failure, fail)
    with TestClient(main.app) as client:
        login(client, 'alice')
        response = client.post('/api/admin/users', json=PAYLOAD, headers=csrf(client))
        assert response.status_code == 503
    assert 'private-cleanup-credential' not in response.text + caplog.text
    assert records == []
    if failure == 'rollback':
        assert conn.closed
    if failure == 'close':
        assert conn.rollbacks == 1
