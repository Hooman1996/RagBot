"""A6.1 failure injection: fictional input and mocked inference only."""
import asyncio
import copy
import csv
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path

import pytest
from knowledge_audit.execution import VERSION
from knowledge_audit.jobs import CoverageJobs, versions
from knowledge_audit.privacy import AuditError
from knowledge_audit.recovery import RowJournal, CheckpointModel, unknown_records
from knowledge_audit.settings import load_coverage_settings
from tests.test_answering_service import ImmediateRunner
from tests.test_web_auth import setup
from tests.test_knowledge_coverage_access_jobs import seed, audit_runtime
from tests.test_knowledge_coverage_pipeline import LabeledModel, Retrieval
from knowledge_audit.pipeline import CoverageEvaluator
from knowledge_audit.inputs import CsvInputAdapter, ColumnMapping
from knowledge_audit.store import BytesInput
from knowledge_audit.preparation import prepare_dataset

from tests.test_knowledge_coverage_access_jobs import coverage_staging

pytestmark = pytest.mark.usefixtures("coverage_staging")


def synthetic_918(tmp_path):
    store,_,snap,old,_,redactor,preparer=seed(tmp_path)
    stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['query'])
    for i in range(918):writer.writerow(['' if i==7 else 'پرسش آزمایشی، "نیم‌فاصله"\nخط بعد؟'])
    dataset=CsvInputAdapter(BytesInput(stream.getvalue().encode('utf-8-sig')),ColumnMapping('query')).load(redactor)
    rows=asyncio.run(prepare_dataset(dataset,preparer,redactor))
    d=store.save_dataset(dataset,redactor,b'synthetic-only-private-key-1234567890',1,rows)
    return store,d,snap,old,dataset


def create(store, d, snap, old, mode, ids=(), key=None):
    return store.create_run(1, d['dataset_id'], snap['snapshot_id'], list(ids), old['settings'], versions(),
                            execution_mode=mode, idempotency_key=key)


def test_full_918_selection_idempotency_chronology_export_and_mock_run(tmp_path):
    store,d,snap,meta,dataset = synthetic_918(tmp_path)
    run=create(store,d,snap,meta,'full_input',key='synthetic_full_918_key')
    same=create(store,d,snap,meta,'full_input',key='synthetic_full_918_key')
    assert run['run_id']==same['run_id'] and len(run['selected_row_ids'])==918
    assert run['processing_row_ids']==[e.source_row_id for e in dataset.processing_order()]
    assert len(set(run['selected_row_ids']))==918  # identical wording is retained
    calls=[]; blocked=[False]; entered=None
    class Engine:
        def __init__(self):
            self.dataset=dataset;self.model=LabeledModel(store.snapshot(snap['snapshot_id'],1),{})
        async def evaluate(self,event,row):
            calls.append(event.source_row_id)
            if len(calls)==300 and not blocked[0]:
                blocked[0]=True;entered.set();await asyncio.sleep(60)
            return {**row,'processing_status':'completed','coverage_status':'not_evaluated','outcome':'excluded'}
    async def execute():
        nonlocal entered
        entered=asyncio.Event()
        async def factory(meta):return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner())
        jobs.start(run['run_id'],1);jobs.start(run['run_id'],1)
        await asyncio.wait_for(entered.wait(),120)
        await jobs.cancel(run['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()),return_exceptions=True)
        partial,partial_manifest=store.export_revision(run['run_id'],1,True,create=True)
        assert partial_manifest['row_count']==918 and partial_manifest['state']=='cancelled'
        await jobs.recover(run['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        assert store.export_revision(run['run_id'],1,True,partial_manifest['export_revision_id'])[0]==partial
        await jobs.aclose()
    asyncio.run(execute())
    counts=store.progress(run['run_id'],1)
    assert counts['processed_rows']==918 and counts['pending_rows']==0
    assert len(calls)==918 and len(set(calls))==917  # the invalid row is accounted without inference
    body,manifest=store.export_revision(run['run_id'],1,True,create=True)
    rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    assert len(rows)==918 and [r['source_row_id'] for r in rows]==run['row_ids']
    assert manifest['input_scope']=='full_input' and 'pilot_selected_row_ids' not in manifest
    assert all(r['execution_mode']=='full_input' for r in rows)
    assert hashlib.sha256(body).hexdigest()==manifest['csv_sha256']
    assert store.owned('runs',run['run_id'],1)['completion_quality']=='finished_with_errors'
    with pytest.raises(AuditError,match='idempotency_request_conflict'):
        create(store,d,snap,meta,'subset',run['row_ids'][:500],key='synthetic_full_918_key')
    subset=create(store,d,snap,meta,'subset',run['row_ids'][:500])
    assert len(subset['selected_row_ids'])==500
    with pytest.raises(AuditError,match='full_input_selection_is_server_resolved'):
        create(store,d,snap,meta,'full_input',run['row_ids'][:1])


def test_selection_validation_and_default_pilot(tmp_path):
    store,d,s,meta,data,_,_=seed(tmp_path)
    assert meta['execution_mode']=='pilot' and len(meta['selected_row_ids'])==1
    for mode,ids,code in [('subset',['unknown'],'invalid_run_selection'),('subset',[],'invalid_run_selection'),
                         ('unknown',[],'invalid_execution_mode')]:
        with pytest.raises(AuditError,match=code):create(store,d,s,meta,mode,ids)
    with pytest.raises(AuditError,match='artifact_not_found'):
        store.create_run(2,d['dataset_id'],s['snapshot_id'],[],meta['settings'],versions(),execution_mode='full_input')
    with pytest.raises(AuditError,match='invalid_idempotency_key'):
        create(store,d,s,meta,'full_input',key='../../bad')


@pytest.mark.parametrize('value',['0','4','100001','x',True,2.5])
def test_invalid_run_maximum(value):
    with pytest.raises(AuditError):load_coverage_settings({'KNOWLEDGE_COVERAGE_MAX_RUN_ROWS':value})


def test_default_policy_and_size_limit(tmp_path):
    settings=load_coverage_settings({})
    assert settings.max_run_rows==10000 and settings.batch_max_entries==2
    assert settings.manifest()['maximum_distinct_entries']==300 and settings.manifest()['model_concurrency']==1
    store,d,s,meta,data,_,_=seed(tmp_path,queries=tuple('Synthetic?' for _ in range(6)))
    with pytest.raises(AuditError,match='invalid_pilot_selection'):
        create(store,d,s,meta,'pilot',[e.source_row_id for e in data.selected])
    with pytest.raises(AuditError,match='run_selection_exceeds_maximum'):
        store.create_run(1,d['dataset_id'],s['snapshot_id'],[],{'max_run_rows':5},versions(),execution_mode='full_input')


def pinned(store,meta):
    identities={'serving':{'fixture':'synthetic'},'runtime_configuration':{'status':'unavailable'},'audit_settings':meta['settings']}
    from utils.read_only_audit import canonical_sha256
    return store.update_run(meta['run_id'],1,{'run_identities':identities,'run_identity_id':canonical_sha256(identities)})


def test_unknown_journal_requires_explicit_retry_and_keeps_attempts(tmp_path):
    store,d,s,meta,data,_,_=seed(tmp_path);meta=pinned(store,meta)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row.update(attempt_count=1,processing_status='interrupted')
    store.save_row(meta['run_id'],row,1)
    journal=RowJournal(store,meta,row,ImmediateRunner())
    key=journal.key('batch',{'synthetic':'safe'},'initial');journal.begin(key,'batch');journal.update(state='dispatched',dispatches=1)
    async def run():
        with pytest.raises(AuditError,match='unknown_remote_completion_requires_choice'):
            await journal.invoke('batch',{'synthetic':'safe'},lambda:None,phase='initial')
        jobs=CoverageJobs(store,lambda _:None,ImmediateRunner())
        jobs.start=lambda *a:None
        with pytest.raises(AuditError,match='unknown_remote_completion_requires_choice'):await jobs.recover(meta['run_id'],1)
        await jobs.recover(meta['run_id'],1,unknown_policy='skip_unknown')
        assert store.row(meta['run_id'],row['source_row_id'],1)['processing_status']=='interrupted'
        await jobs.recover(meta['run_id'],1,unknown_policy='retry_unknown')
        current=store.owned('runs',meta['run_id'],1)
        assert current['retry_unknown_authorized']
        retry=RowJournal(store,current,{**row,'attempt_count':2},ImmediateRunner())
        assert await retry.invoke('batch',{'synthetic':'safe'},lambda:asyncio.sleep(0,result={'synthetic':'result'}),phase='initial')=={'synthetic':'result'}
        assert len(retry.records())==2 and retry.records()[0]['state'] in {'dispatched','validated'}
        assert len(retry.unknowns())==1
    asyncio.run(run())


def test_progress_no_full_row_reads_dirty_rebuild_and_cancellation_race(tmp_path,monkeypatch):
    store,d,s,meta,data,_,_=seed(tmp_path)
    original=store.rows
    monkeypatch.setattr(store,'rows',lambda *a:pytest.fail('progress scanned all result rows'))
    assert store.progress(meta['run_id'],1)['selected_rows']==1
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row.update(processing_status='completed',outcome='excluded')
    store.save_row(meta['run_id'],row,1)
    assert store.progress(meta['run_id'],1)['processed_rows']==1
    monkeypatch.setattr(store,'rows',original)
    path=store._path('runs',meta['run_id'])
    store.write(path/'progress-dirty.json',{})
    assert store.progress(meta['run_id'],1)['processed_rows']==1 and not (path/'progress-dirty.json').exists()
    store.update_run(meta['run_id'],1,{'state':'cancelled','cancel_requested':True})
    store.update_run(meta['run_id'],1,{'state':'completed','cancel_requested':False,'stage':'finished'})
    assert store.owned('runs',meta['run_id'],1)['state']=='cancelled'
    assert store.result_page(meta['run_id'],1,0,1)['source_total']==3


def test_disk_failure_leaves_authoritative_completed_row_rebuildable(tmp_path,monkeypatch):
    store,_,_,meta,_,_,_=seed(tmp_path);write=store.write
    def failing(path,payload):
        if path.name=='progress.json':raise OSError('Synthetic disk failure')
        return write(path,payload)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row.update(processing_status='completed',outcome='excluded')
    monkeypatch.setattr(store,'write',failing)
    with pytest.raises(OSError):store.save_row(meta['run_id'],row,1)
    monkeypatch.setattr(store,'write',write)
    assert store.row(meta['run_id'],row['source_row_id'],1)['processing_status']=='completed'
    assert store.progress(meta['run_id'],1)['processed_rows']==1


def crash_lease(root,rid,send):
    from knowledge_audit.store import CoverageStore
    store=CoverageStore(Path(root),ephemeral_test_store=True)
    lease=store.lease(rid);gate=store.global_lease()
    send.send('leased');send.close();os._exit(17)


def test_abrupt_process_releases_real_os_leases(tmp_path):
    store,_,_,meta,_,_,_=seed(tmp_path)
    parent,child=multiprocessing.Pipe(False)
    process=multiprocessing.Process(target=crash_lease,args=(str(store.root),meta['run_id'],child))
    process.start();assert parent.poll(10) and parent.recv()=='leased';process.join(10)
    assert process.exitcode==17
    for lease in (store.lease(meta['run_id']),store.global_lease()):os.close(lease)


@pytest.mark.parametrize('cut',['batch','verification'])
def test_completed_boundary_survives_process_death_without_repeat(tmp_path,cut):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    snap=store.snapshot(s['snapshot_id'],1)
    calls=tmp_path/'dispatches.jsonl'
    def engine_factory():
        class Model(LabeledModel):
            async def call(self,role,payload):
                with calls.open('a') as stream:stream.write(role+'\n')
                return await super().call(role,payload)
        return CoverageEvaluator(snapshot=snap,model=Model(snap,{'1':['a1','a2']}),retrieval=Retrieval(['1'],['1']),
                                 preparer=prep,redactor=redactor,dataset=data)
    def worker():
        real=store.write
        def kill_after(path,value):
            real(path,value)
            if path.name.startswith('request_') and value.get('state')=='validated' and value.get('responsibility')==cut:
                os._exit(23)
        store.write=kill_after
        async def run():
            async def factory(meta):return engine_factory()
            jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
            await asyncio.gather(*jobs.tasks._tasks.values())
        asyncio.run(run())
    process=multiprocessing.Process(target=worker);process.start();process.join(20)
    if process.is_alive():process.kill();process.join();pytest.fail('synthetic child did not terminate')
    assert process.exitcode==23
    async def recover():
        async def factory(meta):return engine_factory()
        jobs=CoverageJobs(store,factory,ImmediateRunner())
        assert (await jobs.inspect_state(meta['run_id'],1))['state']=='interrupted'
        await jobs.recover(meta['run_id'],1)
        await asyncio.gather(*jobs.tasks._tasks.values());await jobs.aclose()
    asyncio.run(recover())
    result=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
    assert result['outcome']=='covered_reachable' and result['attempt_count']==2
    assert result['checkpoint_reuse_count']>=3
    recorded=calls.read_text().splitlines()
    assert recorded.count('scope')==recorded.count('aspects')==recorded.count('batch')==recorded.count('verification')==1
    assert len(store.rows(meta['run_id'],1))==3


def test_global_busy_stays_queued_and_queued_cancel_never_calls_factory(tmp_path):
    store,_,_,meta,_,_,_=seed(tmp_path);gate=store.global_lease();calls=[]
    async def run():
        async def factory(meta):calls.append(1);raise AssertionError('must not start')
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.sleep(.2)
        live=store.owned('runs',meta['run_id'],1)
        assert live['state']=='queued' and live['stage']=='waiting_for_worker'
        await jobs.cancel(meta['run_id'],1);os.close(gate)
        jobs.start(meta['run_id'],1);await asyncio.sleep(.02)
        assert store.owned('runs',meta['run_id'],1)['state']=='cancelled' and not calls
        await jobs.aclose()
    asyncio.run(run())


def test_historical_identity_recovery_refused_and_immutable_export(tmp_path):
    store,_,_,meta,_,_,_=seed(tmp_path)
    oldbody,old=store.export_revision(meta['run_id'],1,True,create=True)
    edited=store.owned('runs',meta['run_id'],1);edited.pop('execution_version');store.write(store._path('runs',meta['run_id'])/'meta.json',edited)
    async def run():
        jobs=CoverageJobs(store,lambda _:None,ImmediateRunner())
        with pytest.raises(AuditError,match='incompatible_run'):await jobs.recover(meta['run_id'],1)
    asyncio.run(run())
    assert store.export_revision(meta['run_id'],1,True,old['export_revision_id'])[0]==oldbody


def test_creation_failure_retry_uses_same_run_identity(tmp_path,monkeypatch):
    store,d,s,meta,data,_,_=seed(tmp_path);write=store.write;once=[False]
    def fail(path,value):
        if path.name=='meta.json' and path.parent.parent.name=='runs' and not once[0]:
            once[0]=True;raise OSError('Synthetic write failure')
        return write(path,value)
    monkeypatch.setattr(store,'write',fail)
    with pytest.raises(OSError):create(store,d,s,meta,'full_input',key='synthetic_creation_retry')
    monkeypatch.setattr(store,'write',write)
    result=create(store,d,s,meta,'full_input',key='synthetic_creation_retry')
    assert len(list((store.root/'runs').iterdir()))==2
    assert len(store.rows(result['run_id'],1))==3


def test_full_mode_api_idempotency_csrf_owner_and_revoked_grant(audit_runtime,setup,monkeypatch):
    import main
    from fastapi.testclient import TestClient
    from knowledge_audit.settings import CAPABILITIES
    from tests.test_web_auth import login,csrf
    store,d,s,meta,jobs=audit_runtime
    setup.users[1]['role']=setup.users[2]['role']='admin'
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS',json.dumps({'1':sorted(CAPABILITIES),'2':sorted(CAPABILITIES)}))
    monkeypatch.setattr(jobs,'start',lambda *a:None)
    payload={'dataset_id':d['dataset_id'],'snapshot_id':s['snapshot_id'],'execution_mode':'full_input','budget_acknowledged':True,
             'idempotency_key':'synthetic_api_idempotency','documents':['Synthetic_FAQ']}
    with TestClient(main.app,raise_server_exceptions=False) as client:
        login(client,'alice')
        assert client.post('/api/knowledge-coverage/runs',json=payload).status_code==403
        first=client.post('/api/knowledge-coverage/runs',json=payload,headers=csrf(client));assert first.status_code==202
        second=client.post('/api/knowledge-coverage/runs',json=payload,headers=csrf(client))
        assert second.status_code==202 and first.json()['run_id']==second.json()['run_id']
        assert len(first.json()['selected_row_ids'])==3
        changed=client.post('/api/knowledge-coverage/runs',json={**payload,'entry_budget':299},headers=csrf(client))
        assert changed.status_code==409 and changed.json()['detail']=='idempotency_request_conflict'
        assert client.post('/api/knowledge-coverage/runs',json={**payload,'selected_count':918},headers=csrf(client)).status_code==422
        login(client,'bob')
        assert client.post('/api/knowledge-coverage/runs',json=payload,headers=csrf(client)).status_code==404
        login(client,'alice');monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS','{}')
        assert client.post('/api/knowledge-coverage/runs/'+first.json()['run_id']+'/retry',headers=csrf(client)).status_code==403


def test_precise_model_dispatch_journal_read_timeout_and_cancellation(tmp_path):
    import httpx
    from tests.test_knowledge_coverage_reliability import model_fixture,PRIVATE
    store,_,_,meta,_,_,_=seed(tmp_path);meta=pinned(store,meta)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row['attempt_count']=1
    async def run():
        async def timeout(request):raise httpx.ReadTimeout(PRIVATE,request=request)
        model,rag,http=model_fixture(timeout)
        journal=RowJournal(store,meta,row,ImmediateRunner())
        try:
            with pytest.raises(AuditError,match='model_read_timeout'):
                await CheckpointModel(model,journal).call('scope',{'question':'Synthetic procedure?'})
            records=journal.records();assert len(records)==1 and records[0]['dispatches']==1
            assert records[0]['state']=='unknown' and records[0]['failure_category']=='model_read_timeout'
            assert PRIVATE not in json.dumps(records)
            assert rag.metrics_snapshot()['vllm_active']==0
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


def test_restored_structured_output_still_checks_citations_and_hash(tmp_path):
    store,_,snap,meta,data,redactor,prep=seed(tmp_path);meta=pinned(store,meta)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row['attempt_count']=1
    journal=RowJournal(store,meta,row,ImmediateRunner())
    model=LabeledModel(store.snapshot(snap['snapshot_id'],1),{'1':['a1','a2']},invalid_citation=True)
    engine=CoverageEvaluator(snapshot=model.snap,model=CheckpointModel(model,journal),retrieval=Retrieval([],['1']),
                             preparer=prep,redactor=redactor,dataset=data)
    async def run():
        for _ in range(2):
            result=await engine.evaluate(data.selected[0],row)
            assert result['outcome']=='error' and result['error_code']=='invalid_citation'
            assert result['outcome'] not in {'possible_gap','covered_reachable'}
        assert len([role for role,_ in model.calls if role=='batch'])==1
    asyncio.run(run())
    path=next(p for p in journal.paths() if store.read(p)['state']=='validated')
    record=store.read(path);record['result']['version']='synthetic-tamper';store.write(path,record)
    with pytest.raises(AuditError,match='checkpoint_content_mismatch'):journal.restored(record['key'])


def test_legacy_read_only_progress_adds_no_artifacts(tmp_path):
    store,_,_,meta,_,_,_=seed(tmp_path);path=store._path('runs',meta['run_id'])
    edited=store.owned('runs',meta['run_id'],1);edited.pop('execution_version');store.write(path/'meta.json',edited)
    (path/'progress.json').unlink()
    before={str(p):p.read_bytes() for p in path.rglob('*') if p.is_file()}
    store.progress(meta['run_id'],1)
    async def run():
        jobs=CoverageJobs(store,lambda _:None,ImmediateRunner());await jobs.inspect_state(meta['run_id'],1)
    asyncio.run(run())
    after={str(p):p.read_bytes() for p in path.rglob('*') if p.is_file()}
    assert before==after


def test_competing_processes_and_cross_process_active_cancel(tmp_path):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    second=create(store,d,s,meta,'subset',[data.selected[1].source_row_id])
    entered=multiprocessing.Event();done=multiprocessing.Event()
    calls=tmp_path/'synthetic-factory-calls'
    def worker(rid):
        class Slow(LabeledModel):
            async def call(self,role,payload):
                entered.set();await asyncio.sleep(60)
        class Engine:
            dataset=data
            def __init__(self):self.model=Slow(store.snapshot(s['snapshot_id'],1),{})
            async def evaluate(self,event,row):
                await self.model.call('scope',{'question':'Synthetic procedure?'})
                raise AssertionError('cancel should interrupt')
        async def run():
            async def factory(meta):
                with calls.open('a') as stream:stream.write(rid+'\n')
                return Engine()
            jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(rid,1)
            await asyncio.gather(*list(jobs.tasks._tasks.values()),return_exceptions=True)
        asyncio.run(run());done.set()
    first=multiprocessing.Process(target=worker,args=(meta['run_id'],))
    queued=multiprocessing.Process(target=worker,args=(second['run_id'],))
    first.start()
    try:
        assert entered.wait(10)
        queued.start()
        import time
        deadline=time.monotonic()+10
        while store.owned('runs',second['run_id'],1).get('stage')!='waiting_for_worker' and time.monotonic()<deadline:time.sleep(.02)
        assert store.owned('runs',second['run_id'],1)['state']=='queued'
        # A second process's repeated start cannot steal the run lease.
        async def cancel_both():
            jobs=CoverageJobs(store,lambda _:None,ImmediateRunner())
            jobs.start(meta['run_id'],1)
            await jobs.cancel(second['run_id'],1)
            await jobs.cancel(meta['run_id'],1)
            await jobs.aclose()
        asyncio.run(cancel_both())
        first.join(10);queued.join(10)
        assert not first.is_alive() and not queued.is_alive()
        assert calls.read_text().splitlines()==[meta['run_id']]
        row=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
        assert row['processing_status']=='cancelled' and row['unknown_completion_count']==1
        assert store.owned('runs',second['run_id'],1)['state']=='cancelled'
        for lease in (store.lease(meta['run_id']),store.global_lease()):os.close(lease)
    finally:
        for process in (first,queued):
            if process.pid and process.is_alive():process.kill();process.join()


def test_retry_effective_result_clears_old_error_but_keeps_attempt(tmp_path):
    store,_,_,meta,data,_,_=seed(tmp_path);calls=[]
    class Engine:
        dataset=data
        def __init__(self):self.model=LabeledModel({}, {})
        async def evaluate(self,event,row):
            calls.append(1)
            assert not row.get('error_code') and not row.get('supporting_sentence_refs')
            if len(calls)==1:return {**row,'processing_status':'failed','outcome':'error','error_code':'invalid_model_schema','coverage_status':'uncertain'}
            return {**row,'processing_status':'completed','outcome':'excluded','coverage_status':'not_evaluated'}
    async def run():
        async def factory(meta):return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        old,manifest=store.export_revision(meta['run_id'],1,True,create=True)
        await jobs.recover(meta['run_id'],1);await asyncio.gather(*list(jobs.tasks._tasks.values()))
        row=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
        assert row['outcome']=='excluded' and not row.get('error_code') and row['attempt_count']==2
        directory=store._path('runs',meta['run_id'])/'attempts'/row['source_row_id']
        assert store.read(directory/'row-attempt-1.json')['result']['error_code']=='invalid_model_schema'
        assert store.export_revision(meta['run_id'],1,True,manifest['export_revision_id'])[0]==old
        await jobs.aclose()
    asyncio.run(run())


def test_retrieval_checkpoint_pins_membership_and_rechecks_drift(tmp_path):
    from knowledge_audit.recovery import CheckpointRetrieval
    store,_,_,meta,_,_,_=seed(tmp_path);meta=pinned(store,meta)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row['attempt_count']=1
    journal=RowJournal(store,meta,row,ImmediateRunner())
    underlying=Retrieval(['1'],['1']);wrapped=CheckpointRetrieval(underlying,journal,['1','2'])
    async def run():
        first=await wrapped.fetch('Synthetic',depth=150)
        underlying.initial=['2']
        assert (await wrapped.fetch('Synthetic',depth=150))['selected_ids']==first['selected_ids']==['1']
        assert wrapped.metrics[-1]['checkpoint_reused']
        underlying.drift=True
        with pytest.raises(AuditError,match='source_or_index_drift'):await wrapped.fetch('Synthetic',depth=150)
    asyncio.run(run())


def test_prior_distinct_entries_count_against_same_budget():
    from tests.test_knowledge_coverage_pipeline import snapshot,input_dataset
    from tests.test_answering_service import Processor,Rewriter,Classifier
    from knowledge_audit.preparation import QueryPreparer
    from knowledge_audit.privacy import Redactor
    snap=snapshot({'1':'Unrelated synthetic fact.','2':'Synthetic duration and cutoff.'})
    model=LabeledModel(snap,{'2':['a1','a2']})
    engine=CoverageEvaluator(snapshot=snap,model=model,retrieval=Retrieval([],['2']),
        preparer=QueryPreparer(Processor(),ImmediateRunner(),Rewriter(),Classifier()),
        redactor=Redactor(b'synthetic-only-private-key-1234567890'),dataset=input_dataset(),entry_budget=1)
    engine.prior_evaluated_entry_ids={'1'}
    result=asyncio.run(engine.evaluate(engine.dataset.selected[0],{}))
    assert not any(role=='batch' for role,payload in model.calls)
    assert result['coverage_status']!='full'


def test_progress_remains_available_during_active_attempt(tmp_path):
    store,_,_,meta,data,_,_=seed(tmp_path)
    async def run():
        entered=asyncio.Event()
        class Engine:
            dataset=data
            def __init__(self):self.model=LabeledModel({}, {})
            async def evaluate(self,event,row):entered.set();await asyncio.sleep(60)
        async def factory(meta):return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        try:
            await asyncio.wait_for(entered.wait(),5)
            counts=store.progress(meta['run_id'],1)
            assert counts['selected_rows']==1 and counts['pending_rows']==1 and counts['outcome_counts']['pending']==3
        finally:await jobs.cancel(meta['run_id'],1);await jobs.aclose()
    asyncio.run(run())


def test_result_archive_survives_effective_row_write_failure(tmp_path,monkeypatch):
    store,_,_,meta,data,_,_=seed(tmp_path);write=store.write;failed=[False]
    class Engine:
        dataset=data
        def __init__(self):self.model=LabeledModel({}, {})
        async def evaluate(self,event,row):return {**row,'processing_status':'completed','outcome':'excluded','coverage_status':'not_evaluated'}
    def fail_once(path,value):
        if path.parent.name=='rows' and value.get('processing_status')=='completed' and not failed[0]:
            failed[0]=True;raise OSError('Synthetic row write failure')
        return write(path,value)
    monkeypatch.setattr(store,'write',fail_once)
    async def run():
        async def factory(meta):return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()));await jobs.aclose()
    asyncio.run(run())
    directory=store._path('runs',meta['run_id'])/'attempts'/meta['selected_row_ids'][0]
    assert store.read(directory/'row-attempt-1.json')['result']['processing_status']=='completed'
    assert list(directory.glob('*interruption*.json'))
    assert store.row(meta['run_id'],meta['selected_row_ids'][0],1)['processing_status']=='interrupted'


def test_cancellation_drains_checkpoint_thread_before_worker_lease_release(tmp_path,monkeypatch):
    import threading
    from utils.concurrency import BoundedBlockingRunner
    store,_,_,meta,data,_,_=seed(tmp_path);save=store.save_row
    entered=threading.Event();release=threading.Event()
    def delayed(rid,row,owner):
        if row['processing_status']=='running':entered.set();release.wait(5)
        return save(rid,row,owner)
    monkeypatch.setattr(store,'save_row',delayed)
    async def run():
        runner=BoundedBlockingRunner(4)
        class Engine:
            dataset=data
            def __init__(self):self.model=LabeledModel({}, {})
            async def evaluate(self,event,row):raise AssertionError('cancel before evaluation')
        async def factory(meta):return Engine()
        jobs=CoverageJobs(store,factory,runner);jobs.start(meta['run_id'],1)
        try:
            for _ in range(100):
                if entered.is_set():break
                await asyncio.sleep(.02)
            assert entered.is_set()
            task=jobs.tasks._tasks[meta['run_id']];task.cancel();await asyncio.sleep(.05)
            with pytest.raises(AuditError,match='run_already_owned'):store.lease(meta['run_id'])
            assert not task.done()
            release.set();await asyncio.gather(task,return_exceptions=True)
            fd=store.lease(meta['run_id']);os.close(fd)
            assert runner.snapshot()['active']==0
            assert store.row(meta['run_id'],meta['selected_row_ids'][0],1)['processing_status']=='cancelled'
        finally:release.set();await jobs.aclose();await runner.aclose()
    asyncio.run(run())


def test_cancelled_lease_acquisition_closes_undelivered_descriptor(tmp_path):
    import threading
    from utils.concurrency import BoundedBlockingRunner
    from knowledge_audit.durable_io import DurableIO
    store,_,_,meta,_,_,_=seed(tmp_path);entered=threading.Event();release=threading.Event()
    def lease():
        fd=store.lease(meta['run_id']);entered.set();release.wait(5);return fd
    async def run():
        runner=BoundedBlockingRunner(1);adapter=DurableIO(runner)
        task=asyncio.create_task(adapter.run(lease))
        for _ in range(100):
            if entered.is_set():break
            await asyncio.sleep(.01)
        assert entered.is_set();task.cancel();await asyncio.sleep(.02);release.set()
        with pytest.raises(asyncio.CancelledError):await task
        fd=store.lease(meta['run_id']);os.close(fd)
        stats=runner.snapshot();assert stats['active']==0 and stats['acquired_total']==stats['released_total']==1
        await runner.aclose()
    asyncio.run(run())


def test_revoked_background_access_dispatches_nothing(tmp_path):
    store,_,_,meta,_,_,_=seed(tmp_path);calls=[]
    async def run():
        async def denied(owner):return False
        async def factory(meta):calls.append(1);raise AssertionError('not authorized')
        jobs=CoverageJobs(store,factory,ImmediateRunner(),access_guard=denied)
        jobs.start(meta['run_id'],1);await asyncio.gather(*list(jobs.tasks._tasks.values()));await jobs.aclose()
    asyncio.run(run())
    assert calls==[]
    current=store.owned('runs',meta['run_id'],1)
    assert current['state']=='failed' and current['error_code']=='audit_access_revoked'


def test_crash_before_dispatch_is_not_completed_or_unknown(tmp_path):
    store,_,_,meta,_,_,_=seed(tmp_path);meta=pinned(store,meta)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row['attempt_count']=1
    prior=RowJournal(store,meta,row,ImmediateRunner());key=prior.key('scope',{'synthetic':True},'unknown')
    prior.begin(key,'scope')  # process died here: no dispatch/completed result
    assert not prior.unknowns() and prior.restored(key) is None
    calls=[]
    async def dispatch():calls.append(1);return {'safe':'synthetic'}
    async def run():
        restored=RowJournal(store,meta,{**row,'attempt_count':2},ImmediateRunner())
        assert await restored.invoke('scope',{'synthetic':True},dispatch)=={'safe':'synthetic'}
        records=restored.records();assert len(records)==2 and {r['state'] for r in records}=={'prepared','validated'}
    asyncio.run(run());assert calls==[1]


def test_changed_code_recovery_rejected_without_mutating_original_identity(tmp_path,monkeypatch):
    import knowledge_audit.jobs as module
    store,_,_,meta,_,_,_=seed(tmp_path);original=store.owned('runs',meta['run_id'],1)
    changed=copy.deepcopy(versions());changed['code']['file_sha256']['synthetic.py']='0'*64
    monkeypatch.setattr(module,'versions',lambda:changed)
    async def run():
        jobs=CoverageJobs(store,lambda _:None,ImmediateRunner())
        with pytest.raises(AuditError,match='audit_version_drift'):await jobs.recover(meta['run_id'],1)
    asyncio.run(run())
    assert store.owned('runs',meta['run_id'],1)==original


def test_changed_snapshot_recovery_stops_before_new_evaluation(tmp_path):
    store,_,s,meta,data,_,_=seed(tmp_path);calls=[]
    class Engine:
        dataset=data
        def __init__(self):self.model=LabeledModel({}, {})
        async def evaluate(self,event,row):calls.append(1);return {**row,'processing_status':'failed','outcome':'error','error_code':'invalid_model_schema'}
    async def run():
        async def factory(meta):store.snapshot(meta['snapshot_id'],1);return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        pinned=copy.deepcopy(store.owned('runs',meta['run_id'],1)['run_identities'])
        snapshot_path=store._path('snapshots',s['snapshot_id'])/'kb-snapshot.json'
        with snapshot_path.open('ab') as stream:stream.write(b'\n')  # isolated corruption, never shared KB edits
        await jobs.recover(meta['run_id'],1);await asyncio.gather(*list(jobs.tasks._tasks.values()))
        current=store.owned('runs',meta['run_id'],1)
        assert current['state']=='incompatible' and current['run_identities']==pinned and calls==[1]
        await jobs.aclose()
    asyncio.run(run())


def test_recommendation_worker_does_not_replay_completed_revision_after_gate(tmp_path):
    from tests.test_knowledge_recommendations import seed_gap_store
    from knowledge_audit.recommendation_jobs import RecommendationJobs
    store,recs,meta,_,_,_=seed_gap_store(tmp_path);rid=meta['recommendation_revision_id']
    results=recs.results(rid,1);meta['state']='completed';recs.finish(rid,1,meta,results)
    path=recs.path(rid)/'results.final.json';before=path.read_bytes();calls=[]
    async def run():
        coverage=CoverageJobs(store,None,ImmediateRunner())
        async def factory(meta):calls.append(1);raise AssertionError('must not replay')
        jobs=RecommendationJobs(recs,coverage,ImmediateRunner(),factory)
        await jobs.work(rid,1);await coverage.aclose()
    asyncio.run(run())
    assert not calls and path.read_bytes()==before and recs.owned(rid,1)['state']=='completed'


def test_truthful_model_counts_distinguish_attempts_dispatch_and_validated_findings(tmp_path):
    store,d,s,old,data,redactor,prep=seed(tmp_path)
    meta=create(store,d,s,old,'full_input');snap=store.snapshot(s['snapshot_id'],1)
    async def run():
        class Model(LabeledModel):
            async def call(self,role,payload):
                if role=='scope':self.reject=payload.get('original_question')=='Duplicate?'
                if role=='batch' and getattr(self,'reject',False):raise AuditError('model_read_timeout')
                return await super().call(role,payload)
        async def factory(meta):
            return CoverageEvaluator(snapshot=snap,model=Model(snap,{'1':['a1','a2']}),retrieval=Retrieval([],['1']),
                                     preparer=prep,redactor=redactor,dataset=data)
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()));await jobs.aclose()
    asyncio.run(run())
    counts=store.progress(meta['run_id'],1)
    assert counts['entry_evaluation_attempted_rows']==3 and counts['model_dispatched_rows']==3
    assert counts['model_evaluated_rows']==1 and counts['processed_rows']==3
    body,manifest=store.export_revision(meta['run_id'],1,False,create=True)
    assert manifest['execution_counts']['model_evaluated_rows']==1
    assert manifest['execution_counts']['model_dispatched_rows']==3
    from knowledge_audit.execution import attempt_seed
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
    assert attempt_seed(row)['evaluated_entry_count']==row['evaluated_entry_count']
    assert attempt_seed(row)['model_evaluated'] is True


def test_cancel_monitor_does_not_recancel_durable_interruption(tmp_path):
    store,_,_,meta,data,_,_=seed(tmp_path)
    async def scenario():
        entered=asyncio.Event()
        class Engine:
            dataset=data
            model=LabeledModel(store.snapshot(meta['snapshot_id'],1),{})
            async def evaluate(self,event,row):
                entered.set()
                await asyncio.sleep(60)
        async def factory(_):return Engine()
        class SlowInterruption(CoverageJobs):
            async def interrupt(self,*args,**kwargs):
                # Let the cross-process watcher observe the persisted intent while
                # local cancellation is already saving its durable interruption.
                await asyncio.sleep(.25)
                await super().interrupt(*args,**kwargs)
        jobs=SlowInterruption(store,factory,ImmediateRunner())
        jobs.start(meta['run_id'],1)
        await asyncio.wait_for(entered.wait(),5)
        await jobs.cancel(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()),return_exceptions=True)
        row=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
        assert row['processing_status']=='cancelled'
        assert not store.owned('runs',meta['run_id'],1).get('active_row_id')
        await jobs.aclose()
    asyncio.run(scenario())
