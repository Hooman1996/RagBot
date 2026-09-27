"""Signed browser sessions against real FastAPI routes and isolated user records."""
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import main
import web_auth
from web_auth import CSRF_COOKIE, SESSION_COOKIE, job_access_token, web_route


class FakeDatabase:
    def __init__(self):
        self.chats = {10: {"id": 10, "user_id": 1}, 20: {"id": 20, "user_id": 2}}
        self.users = {
            1: {"id": 1, "username": "alice", "full_name": "Alice", "role": "user", "is_active": True},
            2: {"id": 2, "username": "bob", "full_name": "Bob", "role": "user", "is_active": True},
        }

    def get_web_user_by_id(self, user_id):
        return self.users.get(user_id)

    def get_session_by_id(self, session_id):
        return self.chats.get(session_id)

    def query_owned_by_user(self, query_id, user_id):
        return query_id == (100 if user_id == 1 else 200)

    def get_mass_answer_job(self, job_id):
        if job_id == "test-job":
            return {"id": job_id, "status": "running", "input_filename": "sample.csv",
                    "total_rows": 1, "valid_rows": 1}
        return None


class FakeRunner:
    async def run(self, function, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class FakeAuthentication:
    def authenticate(self, username, password):
        if password != "secret" or username not in ("alice", "bob"):
            return None
        user_id = 1 if username == "alice" else 2
        return {"id": user_id, "username": username, "full_name": username.title(),
                "role": "user", "password_hash": "SENSITIVE", "email": "private@example.test",
                "is_active": True}


class FakeChats:
    def get_user_sessions(self, user_id):
        return {str(user_id): {"id": str(user_id), "title": "private"}}


class FakeJobManager:
    def get_progress(self, job_id):
        return None


@pytest.fixture
def setup(monkeypatch):
    db = FakeDatabase()
    monkeypatch.setenv("WEB_ENVIRONMENT", "development")
    monkeypatch.setenv("WEB_COOKIE_MODE", "local-http")
    monkeypatch.setenv("WEB_PUBLIC_ORIGIN", "http://localhost:8000")
    monkeypatch.setenv("WEB_SESSION_SECONDS", "900")
    monkeypatch.setenv("WEB_SESSION_SECRET", "test-only-secret-" + "x" * 48)
    monkeypatch.setattr(main, "db_manager", db)
    monkeypatch.setattr(main, "blocking_runner", FakeRunner())
    monkeypatch.setattr(main, "authentication_service", FakeAuthentication())
    monkeypatch.setattr(main, "chat_manager", FakeChats())
    monkeypatch.setattr(main, "mass_answer_job_manager", FakeJobManager())

    @asynccontextmanager
    async def isolated_lifespan(app):
        yield
    monkeypatch.setattr(main.app.router, "lifespan_context", isolated_lifespan)
    return db


def login(client, username):
    response = client.post("/api/login", json={"username": username, "password": "secret"})
    assert response.status_code == 200
    return response


def csrf(client):
    return {"X-CSRF-Token": client.cookies[CSRF_COOKIE]}


def test_unauthenticated_web_routes_and_separate_contracts(setup):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        for path in ("/app", "/analytics", "/knowledge-base/"):
            assert client.get(path, follow_redirects=False).status_code == 303
        for path in ("/api/auth/me", "/api/sessions", "/api/documents",
                     "/api/analytics", "/api/initialize", "/api/ocr/status",
                     "/api/mass-answer/jobs/example", "/knowledge-base/api/documents",
                     "/api/metrics/admission"):
            assert client.get(path).status_code == 401, path
        assert client.get("/api/health").status_code != 401
        assert web_route("/api/mobile/v1/history") is False
        assert web_route("/api/internal/evaluation/v1/runtime-snapshot") is False
        assert client.post("/api/mobile/v1/talk", json={}).status_code != 401
        assert client.post("/api/internal/evaluation/v1/turn", json={}).status_code != 401


def test_two_users_redaction_ownership_and_csrf(setup):
    with TestClient(main.app, raise_server_exceptions=False) as alice, TestClient(main.app, raise_server_exceptions=False) as bob:
        response = login(alice, "alice")
        assert response.json() == {"success": True, "landing_path": "/app", "user": {
            "id": 1, "username": "alice", "display_name": "Alice", "role": "user",
            "permissions": ["chat", "documents", "downloads", "feedback", "ocr", "sessions"],
            "landing_path": "/app"}}
        assert "SENSITIVE" not in response.text and "private@example.test" not in response.text
        assert "httponly" in response.headers["set-cookie"].lower()
        alice_token = alice.cookies[SESSION_COOKIE]
        assert alice_token != login(bob, "bob").cookies.get(SESSION_COOKIE, "different")
        assert "SENSITIVE" not in alice_token and "Alice" not in alice_token
        assert web_auth.verify_session(alice_token)["uid"] == 1
        assert alice.get("/api/auth/me").json()["user"]["id"] == 1
        assert bob.get("/api/auth/me").json()["user"]["id"] == 2
        assert alice.get("/api/sessions").json()["sessions"][0]["id"] == "1"
        assert bob.get("/api/sessions").json()["sessions"][0]["id"] == "2"
        for path in ("/api/sessions/20", "/api/sessions/20/messages", "/api/sessions/20/download"):
            assert alice.get(path).status_code == 404
        for method, path, body in (
            ("post", "/api/sessions/20/message", {"role": "user", "content": "hello"}),
            ("delete", "/api/sessions/20", None),
            ("patch", "/api/sessions/20/pin", None),
            ("post", "/api/sessions/20/satisfaction", {"satisfied": True}),
            ("patch", "/api/queries/200/feedback", {"is_helpful": 1}),
            ("patch", "/api/queries/200/comment", {"comment": "test"}),
        ):
            assert alice.request(method.upper(), path, json=body, headers=csrf(alice)).status_code == 404, path
        assert alice.post("/api/query", json={"query": "hello", "session_id": 20}, headers=csrf(alice)).status_code == 404
        assert alice.post("/api/sessions", json={}).status_code == 403
        assert alice.post("/api/sessions", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
        assert alice.post("/api/sessions", json={}, headers=csrf(alice)).status_code != 403
        assert alice.post("/api/login", json={"username": "alice", "password": "secret"},
                          headers={"Origin": "https://other.example"}).status_code == 403
        setup.users[1]["role"] = "admin"
        setup.users[2]["role"] = "admin"
        job_access = job_access_token("test-job", 1)
        assert alice.get("/api/mass-answer/jobs/test-job", headers={"X-Job-Access": job_access}).status_code == 200
        assert bob.get("/api/mass-answer/jobs/test-job", headers={"X-Job-Access": job_access}).status_code == 404
        assert alice.get("/api/mass-answer/jobs/test-job").status_code == 404
        assert bob.delete("/api/mass-answer/jobs/test-job", headers={**csrf(bob), "X-Job-Access": job_access}).status_code == 404


def test_expiry_inactive_user_logout_and_copied_cookie_limit(setup, monkeypatch):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        copied_token = client.cookies[SESSION_COOKIE]
        assert client.get("/app").status_code == 200
        setup.users[1]["is_active"] = False
        assert client.get("/api/auth/me").status_code == 401
        setup.users[1]["is_active"] = True
        assert client.post("/api/auth/logout", headers=csrf(client)).status_code == 200
        assert SESSION_COOKIE not in client.cookies
        assert client.get("/api/auth/me").status_code == 401
        # Stateless logout clears this browser; a copied cookie is valid until expiry.
        client.cookies.set(SESSION_COOKIE, copied_token)
        assert client.get("/api/auth/me").status_code == 200
        expiry = web_auth.verify_session(copied_token)["exp"]
        monkeypatch.setattr(web_auth.time, "time", lambda: expiry + 1)
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/app", follow_redirects=False).status_code == 303


def test_tamper_secret_and_cookie_configuration(setup, monkeypatch):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        token = client.cookies[SESSION_COOKIE]
        client.cookies.set(SESSION_COOKIE, token[:-1] + ("A" if token[-1] != "A" else "B"))
        assert client.get("/api/auth/me").status_code == 401
        client.cookies.set(SESSION_COOKIE, token)
        monkeypatch.setenv("WEB_SESSION_SECRET", "rotated-secret-" + "z" * 48)
        assert client.get("/api/auth/me").status_code == 401
    monkeypatch.setenv("WEB_ENVIRONMENT", "production")
    monkeypatch.setenv("WEB_COOKIE_MODE", "local-http")
    with pytest.raises(RuntimeError):
        web_auth.cookie_secure()
    monkeypatch.setenv("WEB_COOKIE_MODE", "https")
    monkeypatch.setenv("WEB_PUBLIC_ORIGIN", "http://insecure.example")
    with pytest.raises(RuntimeError):
        web_auth.cookie_secure()
    monkeypatch.setenv("WEB_PUBLIC_ORIGIN", "https://ragbot.example")
    assert web_auth.cookie_secure() is True
