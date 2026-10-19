"""Role-based audit access, identical in every environment; synthetic users and endpoints only."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import main
import web_permissions
from knowledge_audit.privacy import AuditError
from knowledge_audit.runtime import confirm_live_run
from knowledge_audit.settings import CAPABILITIES, coverage_enabled
from tests.test_web_auth import login, setup

ENVIRONMENTS = ["development", "staging", "production", None]
READ_CAPABILITIES = {"coverage_results_view", "coverage_evidence_view", "coverage_export_download"}
LIVE_KEYS = {"TEI_EMBED_URL": "http://10.0.0.5:8080", "VLLM_URL": "http://10.0.0.5:8000/v1",
             "POSTGRES_HOST": "10.0.0.6", "QDRANT_HOST": "10.0.0.7"}


def environ(environment, flag=None):
    env = {} if environment is None else {"ENVIRONMENT": environment}
    if flag is not None:
        env["KNOWLEDGE_COVERAGE_ENABLED"] = flag
    return env


def mounted(env):
    from knowledge_audit.api import mount
    app = FastAPI()
    mount(app, env)
    return "/knowledge-coverage" in {getattr(route, "path", None) for route in app.routes}


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_gate_is_the_flag_alone(environment):
    assert coverage_enabled(environ(environment)) is True and mounted(environ(environment))
    off = environ(environment, "false")
    assert coverage_enabled(off) is False and not mounted(off)
    for check in (coverage_enabled, mounted):
        with pytest.raises(AuditError, match="^invalid_coverage_flag$"):
            check(environ(environment, "maybe"))


def coverage_for(role):
    return web_permissions.permissions_for_user(role, 1) & CAPABILITIES


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_roles_grant_coverage_capabilities(monkeypatch, environment):
    monkeypatch.delenv("KNOWLEDGE_COVERAGE_ENABLED", raising=False)
    if environment is None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("ENVIRONMENT", environment)
    assert coverage_for("admin") == CAPABILITIES
    assert coverage_for("dashboard_viewer") == READ_CAPABILITIES
    for role in ("user", "moderator", "analytics_viewer", "knowledge_editor", "synthetic_unknown_role"):
        assert coverage_for(role) == frozenset(), role
    monkeypatch.setenv("KNOWLEDGE_COVERAGE_ENABLED", "false")
    for role in ("admin", "dashboard_viewer", "user", "synthetic_unknown_role"):
        assert coverage_for(role) == frozenset(), role
        assert web_permissions.permissions_for_user(role, 1) == web_permissions.permissions_for(role)


@pytest.fixture
def coverage_app(setup, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_COVERAGE_ENABLED", raising=False)
    monkeypatch.setenv("KNOWLEDGE_COVERAGE_ARTIFACT_DIR", "/synthetic/audit")
    if not any(getattr(route, "path", None) == "/knowledge-coverage" for route in main.app.routes):
        from knowledge_audit.api import mount
        mount(main.app)
    return setup


@pytest.mark.parametrize("role,page_status,link", [("dashboard_viewer", 200, True), ("user", 403, False)])
def test_page_and_sidebar_follow_role(coverage_app, role, page_status, link):
    coverage_app.users[1]["role"] = role
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        assert client.get("/knowledge-coverage").status_code == page_status
        app_page = client.get("/app")
        assert app_page.status_code == 200
        assert ("Knowledge coverage" in app_page.text) is link
        assert ('href="/knowledge-coverage"' in app_page.text) is link


def test_live_run_guard_uses_configured_endpoints(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_COVERAGE_ENABLED", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    for key, value in LIVE_KEYS.items():
        monkeypatch.setenv(key, value)
    confirm_live_run(confirmed=True, model=True, snapshot=True)
    for key in LIVE_KEYS:
        monkeypatch.setenv(key, "")
        with pytest.raises(AuditError, match="^audit_service_unconfigured$"):
            confirm_live_run(confirmed=True, model=True, snapshot=True)
        monkeypatch.setenv(key, LIVE_KEYS[key])
    with pytest.raises(AuditError, match="^live_run_confirmation_required$"):
        confirm_live_run(confirmed=False, model=True, snapshot=True)
