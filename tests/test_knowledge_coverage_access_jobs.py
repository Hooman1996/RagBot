"""Protected persistence, real browser middleware, cancellation and recovery."""
from __future__ import annotations
import asyncio
import base64
import csv
import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import main
from knowledge_audit.api import runtime
from knowledge_audit.export import coverage_export
from knowledge_audit.jobs import CoverageJobs, versions
from knowledge_audit.privacy import Redactor, private_json
from knowledge_audit.preparation import QueryPreparer, prepare_dataset
from knowledge_audit.settings import load_coverage_settings, CAPABILITIES
from knowledge_audit.store import CoverageStore
from tests.test_answering_service import Processor, ImmediateRunner, Rewriter, Classifier
from tests.test_knowledge_coverage_pipeline import snapshot, input_dataset, Retrieval, LabeledModel
from tests.test_web_auth import setup, login, csrf
from utils.read_only_audit import canonical_sha256
from knowledge_audit.pipeline import CoverageEvaluator


@pytest.fixture
def coverage_staging(monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED','true')
    monkeypatch.setenv('ENVIRONMENT','staging')
    from knowledge_audit.api import mount
    if not any(getattr(route,'path',None)=='/knowledge-coverage' for route in main.app.routes):
        mount(main.app)


@pytest.fixture(autouse=True)
def enabled_coverage(coverage_staging):
    pass


def seed(tmp_path, *, owner=1, queries=('What is the duration and cutoff?','Duplicate?','Duplicate?')):
    store=CoverageStore(tmp_path/'store',ephemeral_test_store=True)
    key=b'synthetic-only-private-key-1234567890'
    redactor=Redactor(key); data=input_dataset(queries)
    prep=QueryPreparer(Processor(),ImmediateRunner(),Rewriter(),Classifier())
    rows=asyncio.run(prepare_dataset(data,prep,redactor))
    d=store.save_dataset(data,redactor,key,owner,rows)
    snap=snapshot({'1':'Duration two days, cutoff 18:00.'})
    # Fixture snapshot uses the complete versioned A1 identity envelope.
    snap.update(schema_version='a1-kb-snapshot-1',source_signature={},retrieval_frozen=False)
    snap.pop('snapshot_id'); snap['snapshot_id']=canonical_sha256(snap)
    capture=tmp_path/'capture'; capture.mkdir(mode=0o700)
    private_json(capture/'kb-snapshot.json',snap)
    import hashlib
    private_json(capture/'kb-snapshot-manifest.json',{'snapshot_id':snap['snapshot_id'],
        'content_file_sha256':hashlib.sha256((capture/'kb-snapshot.json').read_bytes()).hexdigest()})
    s=store.register_snapshot(capture/'kb-snapshot.json',capture/'kb-snapshot-manifest.json',owner)
    config={'entry_budget':300,'documents':['Synthetic_FAQ']}
    meta=store.create_run(owner,d['dataset_id'],s['snapshot_id'],[data.selected[0].source_row_id],config,versions())
    return store,d,s,meta,data,redactor,prep


def test_atomic_store_ownership_export_and_pending_conservation(tmp_path):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    with pytest.raises(ValueError,match='artifact_not_found'):
        store.owned('runs',meta['run_id'],2)
    restored,r=store.dataset(d['dataset_id'],1)
    assert [e.source_row_id for e in restored.selected]==[e.source_row_id for e in data.selected]
    rows=store.rows(meta['run_id'],1)
    assert [r['model_selected'] for r in rows] == [True, False, False]
    rows[0].update(explanation='=untrusted explanation',supporting_sentence_refs=[{'snapshot_id':s['snapshot_id'],'chunk_id':'1','faq_entry_id':'1','sentence_number':1}],recommendations=[])
    for visible in (True,False):
        body,manifest=coverage_export(meta,rows,redactor,evidence_visible=visible)
        parsed=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'),newline='')))
        assert len(parsed)==3 and [x['source_row_id'] for x in parsed]==meta['row_ids']
        assert all(x['export_id']==manifest['export_id'] and x['recommendation_status']=='unassessed' for x in parsed)
        assert all(x['coverage_status']=='not_evaluated' for x in parsed)
        assert parsed[0]['explanation']==("'=untrusted explanation" if visible else '')
        assert json.loads(parsed[0]['supporting_sentence_refs'])== (rows[0]['supporting_sentence_refs'] if visible else [])
        assert parsed[0]['evidence_visibility']==('visible' if visible else 'restricted')
    with pytest.raises(ValueError): store.owned('runs','../../private',1)


def test_snapshot_access_requires_explicit_validated_registration(tmp_path):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    with pytest.raises(ValueError,match='artifact_not_found'):
        store.snapshot(s['snapshot_id'],2)
    assert store.list_owned('snapshots',2)==[]
    capture=tmp_path/'capture'
    store.register_snapshot(capture/'kb-snapshot.json',capture/'kb-snapshot-manifest.json',2)
    assert store.snapshot(s['snapshot_id'],2)['snapshot_id']==s['snapshot_id']
    assert len(store.list_owned('snapshots',2))==1
    for kind,identifier in [('datasets',d['dataset_id']),('runs',meta['run_id'])]:
        with pytest.raises(ValueError,match='artifact_not_found'):
            store.owned(kind,identifier,2)


def test_cancel_and_interrupted_recovery_skip_completed_rows(tmp_path):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    # Select two rows and pre-complete one to test durable skip behavior.
    meta['selected_row_ids']=[e.source_row_id for e in data.selected[:2]]
    meta['processing_row_ids']=meta['selected_row_ids'].copy()
    store.write(store._path('runs',meta['run_id'])/'meta.json',meta)
    completed=store.row(meta['run_id'],data.selected[0].source_row_id,1)
    completed.update(processing_status='completed',outcome='covered_reachable',coverage_status='full')
    store.save_row(meta['run_id'],completed,1)
    calls=[]
    async def run():
        entered=asyncio.Event()
        class Engine:
            dataset=data
            model=LabeledModel(snapshot({'1':'synthetic'}),{})
            async def evaluate(self,event,row):
                calls.append(event.source_row_id); entered.set(); await asyncio.sleep(60)
        async def factory(meta): return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner())
        jobs.start(meta['run_id'],1)
        await entered.wait()
        await jobs.cancel(meta['run_id'],1)
        assert store.owned('runs',meta['run_id'],1)['state']=='cancelled'
        assert store.row(meta['run_id'],data.selected[0].source_row_id,1)['processing_status']=='completed'
        assert store.row(meta['run_id'],data.selected[1].source_row_id,1)['processing_status']=='cancelled'
        class Finish:
            dataset=data
            model=LabeledModel(snapshot({'1':'synthetic'}),{})
            async def evaluate(self,event,row):
                calls.append(event.source_row_id)
                return {**row,'processing_status':'completed','coverage_status':'partial','outcome':'possible_partial_gap'}
        async def recovered(meta): return Finish()
        jobs.factory=recovered
        await jobs.recover(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        assert store.owned('runs',meta['run_id'],1)['state']=='completed'
        assert calls==[data.selected[1].source_row_id]*2
        assert len(store.rows(meta['run_id'],1))==3
        assert store.row(meta['run_id'],data.selected[1].source_row_id,1)['attempt_count']==2
        await jobs.aclose()
    asyncio.run(run())


def test_os_lease_blocks_double_worker_and_stale_running_recovers(tmp_path):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    lease=store.lease(meta['run_id'])
    try:
        with pytest.raises(ValueError,match='run_already_owned'): store.lease(meta['run_id'])
    finally: __import__('os').close(lease)
    row=store.row(meta['run_id'],data.selected[0].source_row_id,1)
    row['processing_status']='running'; store.save_row(meta['run_id'],row,1)
    meta['state']='running'; store.write(store._path('runs',meta['run_id'])/'meta.json',meta)
    class Engine:
        dataset=data
        model=LabeledModel(snapshot({'1':'synthetic'}),{})
        async def evaluate(self,event,row): return {**row,'processing_status':'completed','outcome':'pending'}
    async def run():
        async def factory(meta): return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner()); await jobs.recover(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        assert store.owned('runs',meta['run_id'],1)['state']=='completed'
        await jobs.aclose()
    asyncio.run(run())


@pytest.fixture
def audit_runtime(setup,monkeypatch,tmp_path,coverage_staging):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    settings=load_coverage_settings({})
    async def factory(run):
        saved,redactor=store.dataset(run['dataset_id'],run['owner_id']); snap=store.snapshot(run['snapshot_id'],run['owner_id'])
        model=LabeledModel(snap,{'1':['a1','a2']})
        return CoverageEvaluator(snapshot=snap,model=model,retrieval=Retrieval(['1'],['1']),preparer=prep,redactor=redactor,dataset=saved)
    jobs=CoverageJobs(store,factory,ImmediateRunner())
    monkeypatch.setattr(main.app.state,'coverage_runtime',(settings,store,jobs),raising=False)
    monkeypatch.setattr(main.app.state,'answering_service',SimpleNamespace(text_processor=Processor(),blocking_runner=ImmediateRunner(),
        history_rewriting_service=Rewriter(),intent_classifier=Classifier()),raising=False)
    return store,d,s,meta,jobs


from types import SimpleNamespace


def test_default_deny_real_auth_owner_csrf_and_restricted_export(audit_runtime,setup,monkeypatch):
    store,d,s,meta,jobs=audit_runtime
    setup.users[1]['role']='admin'; setup.users[2]['role']='admin'
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS','{}')
    with TestClient(main.app,raise_server_exceptions=False) as client:
        assert client.get('/api/knowledge-coverage/runs').status_code==401
        login(client,'alice')
        assert client.get('/knowledge-coverage').status_code==403
        assert client.get('/api/knowledge-coverage/runs').status_code==403
        grants={'1':sorted(CAPABILITIES),'2':sorted(CAPABILITIES)}
        monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS',json.dumps(grants))
        page=client.get('/knowledge-coverage'); assert page.status_code==200
        assert '/knowledge-coverage' in client.get('/app').text
        assert client.post('/api/knowledge-coverage/runs',json={}).status_code==403
        assert client.get('/api/knowledge-coverage/runs/'+meta['run_id']).status_code==200
        assert client.get('/api/knowledge-coverage/runs/'+meta['run_id']+'/rows/'+meta['row_ids'][0]).status_code==200
        export=client.get('/api/knowledge-coverage/runs/'+meta['run_id']+'/export'); assert export.status_code==200
        manifest=client.get('/api/knowledge-coverage/runs/'+meta['run_id']+'/export-manifest').json()
        assert export.headers['x-coverage-export-id']==manifest['export_id']
        grants['1'].remove('coverage_evidence_view'); monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS',json.dumps(grants))
        assert client.get('/api/knowledge-coverage/runs/'+meta['run_id']+'/rows/'+meta['row_ids'][0]).status_code==403
        restricted=client.get('/api/knowledge-coverage/runs/'+meta['run_id']+'/export')
        assert b'restricted' in restricted.content
        login(client,'bob')
        for suffix in ('','/results','/export','/export-manifest','/rows/'+meta['row_ids'][0]):
            assert client.get('/api/knowledge-coverage/runs/'+meta['run_id']+suffix).status_code==404
        assert client.post('/api/knowledge-coverage/runs/'+meta['run_id']+'/cancel',headers=csrf(client)).status_code==404
        assert client.post('/api/knowledge-coverage/runs/'+meta['run_id']+'/retry',headers=csrf(client)).status_code==404


def test_upload_mapping_no_arbitrary_paths_and_full_input_pilot_export(audit_runtime,setup,monkeypatch):
    store,d,s,meta,jobs=audit_runtime
    setup.users[1]['role']='admin'; monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS',json.dumps({'1':sorted(CAPABILITIES)}))
    with TestClient(main.app,raise_server_exceptions=False) as client:
        login(client,'alice')
        raw='query,session,timestamp\r\n"سؤال، یک\nخط",a,2026-01-01T12:00:00Z\r\n"=untrusted formula",a,2026-01-01T13:00:00Z\r\n, a,broken\r\n'
        payload={'csv_base64':base64.b64encode(raw.encode('utf-8-sig')).decode(),
                 'mapping':{'query':'query','session':'session','timestamp':'timestamp'}}
        assert client.post('/api/knowledge-coverage/datasets',json={**payload,'server_path':'/etc/private'},headers=csrf(client)).status_code==422
        created=client.post('/api/knowledge-coverage/datasets',json=payload,headers=csrf(client)); assert created.status_code==201,created.text
        did=created.json()['dataset_id']
        import time
        for _ in range(50):
            data=client.get('/api/knowledge-coverage/datasets/'+did+'/rows').json()
            if data['state']=='ready': break
            time.sleep(.01)
        assert data['total']==3
        body={'dataset_id':did,'snapshot_id':s['snapshot_id'],'row_ids':[data['rows'][0]['source_row_id']],
              'entry_budget':300,'documents':['Synthetic_FAQ']}
        assert client.post('/api/knowledge-coverage/runs',json=body,headers={**csrf(client),'Origin':'http://wrong-origin'}).status_code==403
        response=client.post('/api/knowledge-coverage/runs',json=body,headers=csrf(client)); assert response.status_code==202,response.text
        rid=response.json()['run_id']
        for _ in range(50):
            state=client.get('/api/knowledge-coverage/runs/'+rid).json()
            if state['state']=='completed': break
            time.sleep(.01)
        assert state['state']=='completed'
        parsed=list(csv.DictReader(io.StringIO(client.get('/api/knowledge-coverage/runs/'+rid+'/export').content.decode('utf-8-sig'))))
        assert len(parsed)==3
        assert parsed[1]['input_query_redacted']=="'=untrusted formula"
        assert parsed[1]['coverage_status']=='not_evaluated' and parsed[2]['processing_status']=='invalid_input'
        assert client.get('/api/knowledge-coverage/runs/'+rid+'/results?outcome=covered_reachable').json()['total']==1


@pytest.mark.parametrize('key,value',[('KNOWLEDGE_COVERAGE_MODEL_MAX_TOKENS','0'),('KNOWLEDGE_COVERAGE_TOKEN_MARGIN','-1'),
    ('KNOWLEDGE_COVERAGE_UPLOAD_MAX_BYTES','999999999'),('KNOWLEDGE_COVERAGE_ACCESS_GRANTS','{"1":["kb_write"]}'),
    ('KNOWLEDGE_COVERAGE_ARTIFACT_DIR','/tmp/ephemeral'),('KNOWLEDGE_COVERAGE_ARTIFACT_DIR',str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'static' / 'private'))])
def test_configuration_validation_and_propagation(key,value):
    with pytest.raises(ValueError): load_coverage_settings({key:value})
    from scripts.validate_environment import SPECS
    from pathlib import Path
    for name in ('env.example','Production_ENV.example','.env.example.generated'):
        text=Path(name).read_text()
        assert key+'=' in text and key in SPECS


def test_audit_http_bodies_never_log_base64_messages_or_evidence():
    from utils.http_logging_middleware import route_log_policy
    for path in ('/knowledge-coverage','/api/knowledge-coverage/datasets','/api/knowledge-coverage/runs/r_x/rows/row_x','/api/knowledge-coverage/runs/r_x/export'):
        policy=route_log_policy(path)
        assert policy.emit_events and not policy.request_body and not policy.response_body


@pytest.mark.parametrize('result',[None,32,RuntimeError('synthetic'),asyncio.CancelledError()])
def test_require_reranker_capability(monkeypatch,result):
    from knowledge_audit.privacy import AuditError
    from knowledge_audit.service import _require_reranker_capability
    search=SimpleNamespace()
    async def capability():
        if isinstance(result,BaseException):raise result
        return result
    monkeypatch.setattr(search,'rerank_capability',capability,raising=False)
    if isinstance(result,asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):asyncio.run(_require_reranker_capability(search))
    elif result is None or isinstance(result,Exception):
        with pytest.raises(AuditError,match='^reranker_capability_unavailable$'):
            asyncio.run(_require_reranker_capability(search))
    else:
        asyncio.run(_require_reranker_capability(search))
