"""Synthetic deployment boundaries; no services or real credential values."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from dotenv import dotenv_values
from fastapi import FastAPI
import pytest

from knowledge_audit.privacy import AuditError
from knowledge_audit.settings import coverage_enabled, require_coverage_enabled
from scripts.check_tracked_secrets import secret_key

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('env,expected',[
    ({},False),({'KNOWLEDGE_COVERAGE_ENABLED':'false','ENVIRONMENT':'staging'},False),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'true'},False),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'true','ENVIRONMENT':'development'},False),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'true','ENVIRONMENT':'staging'},True),
    ({'KNOWLEDGE_COVERAGE_ENABLED':' TRUE ','ENVIRONMENT':' Staging '},True),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'1','ENVIRONMENT':'staging'},False),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'','ENVIRONMENT':''},False),
])
def test_coverage_enabled_truth_table(env,expected):
    assert coverage_enabled(env) is expected
    if expected:
        require_coverage_enabled(env)
    else:
        with pytest.raises(AuditError,match='^coverage_disabled$'):require_coverage_enabled(env)


def test_production_refuses_enabled_audit():
    env={'KNOWLEDGE_COVERAGE_ENABLED':' true ','ENVIRONMENT':' Production '}
    for check in (coverage_enabled,require_coverage_enabled):
        with pytest.raises(AuditError,match='^coverage_enabled_in_production$'):check(env)


@pytest.mark.parametrize('flag,environment,expected',[('false','staging',False),('true','staging',True),('true','production',None)])
def test_mount_only_on_staging(flag,environment,expected):
    from knowledge_audit.api import mount
    app=FastAPI();env={'KNOWLEDGE_COVERAGE_ENABLED':flag,'ENVIRONMENT':environment}
    if expected is None:
        with pytest.raises(AuditError,match='^coverage_enabled_in_production$'):mount(app,env)
        return
    assert mount(app,env) is expected
    paths={getattr(route,'path',None) for route in app.routes}
    for path in ('/knowledge-coverage','/api/knowledge-coverage/runs',
                 '/api/knowledge-coverage/recommendations/{revision_id}'):
        assert (path in paths) is expected


@pytest.mark.parametrize('entry',['runtime','coverage_jobs','recommendation_jobs','build_engine','confirm_staging'])
def test_entry_points_fail_before_work(monkeypatch,entry):
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED','false')
    monkeypatch.setenv('ENVIRONMENT','staging')
    from knowledge_audit import api
    from knowledge_audit.jobs import CoverageJobs
    from knowledge_audit.recommendation_jobs import RecommendationJobs
    from knowledge_audit.runtime import confirm_staging
    from knowledge_audit.service import build_engine
    load=Mock(side_effect=AssertionError('Settings must not load'))
    monkeypatch.setattr(api,'load_coverage_settings',load)
    with pytest.raises(AuditError,match='^coverage_disabled$'):
        if entry=='runtime':api.runtime(SimpleNamespace())
        elif entry=='coverage_jobs':CoverageJobs.start(SimpleNamespace(),None,None)
        elif entry=='recommendation_jobs':RecommendationJobs.start(SimpleNamespace(),None,None)
        elif entry=='build_engine':asyncio.run(build_engine(None,None,None,answering=None,runner=None,limiter=None))
        else:confirm_staging(confirmed=True)
    load.assert_not_called()


def test_cli_gate_coverage():
    paths=sorted({*ROOT.glob('scripts/knowledge_audit_*.py'),
                  *ROOT.glob('scripts/knowledge_coverage_*.py'),
                  *ROOT.glob('scripts/knowledge_recommendation_*.py')})
    assert len(paths)==10
    for path in paths:
        tree=ast.parse(path.read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        gates=[n for n in calls if n.func.id=='require_coverage_enabled']
        if path.name=='knowledge_coverage_cleanup.py':
            assert not gates
        else:
            assert len(gates)==1,path.name
            loaders=[n for n in calls if n.func.id=='load_dotenv']
            assert len(loaders)==1 and loaders[0].lineno<gates[0].lineno,path.name


@pytest.mark.parametrize('flag,environment,error,expected_loads',[
    ('false','staging',False,0),('true','production',False,0),
    ('true','staging',False,1),('true','staging',True,100)])
def test_permissions_cached_and_deny_by_default(monkeypatch,flag,environment,error,expected_loads):
    import web_permissions
    from knowledge_audit import settings
    web_permissions._coverage_grants.cache_clear()
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED',flag)
    monkeypatch.setenv('ENVIRONMENT',environment)
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS','{"1":["coverage_results_view"]}')
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ARTIFACT_DIR','/synthetic/audit')
    def load(environ=None):
        if error:raise AuditError('invalid_coverage_access_grants')
        return SimpleNamespace(access_grants={'1':['coverage_results_view']})
    counter=Mock(side_effect=load);monkeypatch.setattr(settings,'load_coverage_settings',counter)
    try:
        for _ in range(100):
            permissions=web_permissions.permissions_for_user('admin',1)
            expected=web_permissions.permissions_for('admin')
            if expected_loads==1:expected=expected|{'coverage_results_view'}
            assert permissions==expected
        assert counter.call_count==expected_loads
        if expected_loads==1:
            monkeypatch.setenv('KNOWLEDGE_COVERAGE_ARTIFACT_DIR','/synthetic/other')
            web_permissions.permissions_for_user('admin',1)
            assert counter.call_count==2
    finally:web_permissions._coverage_grants.cache_clear()


def test_environment_example_and_ignore_contract():
    example=ROOT/'Production_ENV.example'
    assert example.exists()
    values=dotenv_values(example,interpolate=False)
    assert all(value=='' for key,value in values.items() if secret_key(key))
    if (ROOT/'Production_ENV').exists():
        assert set(dotenv_values(ROOT/'Production_ENV',interpolate=False))==set(values)
    ignore=(ROOT/'.gitignore').read_text().splitlines()
    assert '/.env' in ignore and '/Production_ENV' in ignore


def test_validator_rejects_enabled_production(tmp_path):
    from scripts.validate_environment import analyze_environment
    path=tmp_path/'synthetic.env'
    path.write_text('KNOWLEDGE_COVERAGE_ENABLED=true\nENVIRONMENT=production\n')
    report=analyze_environment(path,'production',process_environment={})
    assert any(row['variable']=='KNOWLEDGE_COVERAGE_ENABLED' and row['severity']=='critical'
               for row in report['findings'])
