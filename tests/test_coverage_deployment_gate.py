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
    ({},True),({'KNOWLEDGE_COVERAGE_ENABLED':'false','ENVIRONMENT':'staging'},False),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'true'},True),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'true','ENVIRONMENT':'development'},True),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'true','ENVIRONMENT':'staging'},True),
    ({'KNOWLEDGE_COVERAGE_ENABLED':' TRUE ','ENVIRONMENT':' Staging '},True),
    ({'KNOWLEDGE_COVERAGE_ENABLED':' False ','ENVIRONMENT':'production'},False),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'1','ENVIRONMENT':'staging'},None),
    ({'KNOWLEDGE_COVERAGE_ENABLED':'','ENVIRONMENT':''},None),
])
def test_coverage_enabled_truth_table(env,expected):
    if expected is None:
        for check in (coverage_enabled,require_coverage_enabled):
            with pytest.raises(AuditError,match='^invalid_coverage_flag$'):check(env)
        return
    assert coverage_enabled(env) is expected
    if expected:
        require_coverage_enabled(env)
    else:
        with pytest.raises(AuditError,match='^coverage_disabled$'):require_coverage_enabled(env)


def test_production_runs_enabled_audit():
    env={'KNOWLEDGE_COVERAGE_ENABLED':' true ','ENVIRONMENT':' Production '}
    assert coverage_enabled(env) is True
    require_coverage_enabled(env)


@pytest.mark.parametrize('flag,environment,expected',[('false','staging',False),('true','staging',True),
    ('true','production',True),('false','production',False),(None,'production',True),(None,'development',True)])
def test_mount_follows_flag_in_every_environment(flag,environment,expected):
    from knowledge_audit.api import mount
    app=FastAPI();env={'ENVIRONMENT':environment}
    if flag is not None:env['KNOWLEDGE_COVERAGE_ENABLED']=flag
    assert mount(app,env) is expected
    paths={getattr(route,'path',None) for route in app.routes}
    for path in ('/knowledge-coverage','/api/knowledge-coverage/runs',
                 '/api/knowledge-coverage/recommendations/{revision_id}'):
        assert (path in paths) is expected


@pytest.mark.parametrize('entry',['runtime','coverage_jobs','recommendation_jobs','build_engine','confirm_live_run'])
def test_entry_points_fail_before_work(monkeypatch,entry):
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED','false')
    monkeypatch.setenv('ENVIRONMENT','staging')
    from knowledge_audit import api
    from knowledge_audit.jobs import CoverageJobs
    from knowledge_audit.recommendation_jobs import RecommendationJobs
    from knowledge_audit.runtime import confirm_live_run
    from knowledge_audit.service import build_engine
    load=Mock(side_effect=AssertionError('Settings must not load'))
    monkeypatch.setattr(api,'load_coverage_settings',load)
    with pytest.raises(AuditError,match='^coverage_disabled$'):
        if entry=='runtime':api.runtime(SimpleNamespace())
        elif entry=='coverage_jobs':CoverageJobs.start(SimpleNamespace(),None,None)
        elif entry=='recommendation_jobs':RecommendationJobs.start(SimpleNamespace(),None,None)
        elif entry=='build_engine':asyncio.run(build_engine(None,None,None,answering=None,runner=None,limiter=None))
        else:confirm_live_run(confirmed=True)
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


@pytest.mark.parametrize('flag,environment,granted',[
    ('false','staging',False),('true','production',True),
    ('true','staging',True),('maybe','staging',False)])
def test_permissions_from_role_without_loading_settings(monkeypatch,flag,environment,granted):
    import web_permissions
    from knowledge_audit import settings
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED',flag)
    monkeypatch.setenv('ENVIRONMENT',environment)
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ARTIFACT_DIR','/synthetic/audit')
    counter=Mock(side_effect=AssertionError('Settings must not load'))
    monkeypatch.setattr(settings,'load_coverage_settings',counter)
    for _ in range(100):
        expected=web_permissions.permissions_for('admin')
        if granted:expected=expected|web_permissions.COVERAGE_ROLE_CAPABILITIES['admin']
        assert web_permissions.permissions_for_user('admin',1)==expected
    counter.assert_not_called()


def test_environment_example_and_ignore_contract():
    example=ROOT/'Production_ENV.example'
    assert example.exists()
    values=dotenv_values(example,interpolate=False)
    assert all(value=='' for key,value in values.items() if secret_key(key))
    if (ROOT/'Production_ENV').exists():
        assert set(dotenv_values(ROOT/'Production_ENV',interpolate=False))==set(values)
    ignore=(ROOT/'.gitignore').read_text().splitlines()
    assert '/.env' in ignore and '/Production_ENV' in ignore


@pytest.mark.parametrize('value,rejected',[('true',False),('false',False),('1',True),('maybe',True)])
def test_validator_accepts_enabled_production(tmp_path,value,rejected):
    from scripts.validate_environment import analyze_environment
    path=tmp_path/'synthetic.env'
    path.write_text(f'KNOWLEDGE_COVERAGE_ENABLED={value}\nENVIRONMENT=production\n')
    report=analyze_environment(path,'production',process_environment={})
    assert any(row['variable']=='KNOWLEDGE_COVERAGE_ENABLED' and row['severity']=='critical'
               for row in report['findings']) is rejected
