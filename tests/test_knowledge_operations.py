"""A6.2: exclusively synthetic resource/retention failure injection."""
import asyncio
import copy
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from tests.test_knowledge_coverage_access_jobs import seed
from knowledge_audit.operations import Budget, Limits, OperationalPause


def budget_fixture(tmp_path,**overrides):
    store,d,snap,old,*_=seed(tmp_path)
    limits=Limits(**overrides)
    from dataclasses import asdict
    from knowledge_audit.jobs import versions
    meta=store.create_run(1,d['dataset_id'],snap['snapshot_id'],old['selected_row_ids'],{**old['settings'],'operational_limits':asdict(limits)},versions())
    budget=Budget(store,store._path('runs',meta['run_id']),1,limits)
    return store,meta,budget


def test_completion_reservation_restart_unknown_and_checkpoint_reuse(tmp_path):
    store,meta,b=budget_fixture(tmp_path,completion_attempts=2,token_allowance=100)
    b.start();r=b.reserve('completion',60,'scope');b.dispatched(r)
    restored=Budget(store,b.path.parent,1,b.limits)
    assert restored.summary()['tokens_charged']==60
    assert restored.summary()['unknown_reservations']==1
    restored.acknowledge_unknown()
    with pytest.raises(OperationalPause,match='budget_tokens'):restored.reserve('completion',60,'batch')
    restored.finish(r,usage=30)
    r2=restored.reserve('completion',60,'batch');restored.dispatched(r2);restored.finish(r2,usage=40)
    assert restored.summary()['completion_attempts']==2
    assert restored.summary()['tokens_charged']==70
    with pytest.raises(OperationalPause,match='budget_completions'):restored.reserve('completion',1,'verification')
    assert restored.summary()['completion_attempts']==2


def test_low_disk_elapsed_and_failure_threshold_do_not_reset(tmp_path,monkeypatch):
    store,meta,b=budget_fixture(tmp_path,execution_seconds=1,consecutive_failures=2)
    monkeypatch.setattr('knowledge_audit.operations.shutil.disk_usage',lambda _:SimpleNamespace(free=0))
    with pytest.raises(OperationalPause,match='budget_disk'):b.start()
    monkeypatch.setattr('knowledge_audit.operations.shutil.disk_usage',lambda _:SimpleNamespace(free=10**12))
    b.start()
    for _ in range(2):
        rid=b.reserve('completion',10,'scope');b.dispatched(rid);b.finish(rid,usage=10,error='model_http_rejection')
    with pytest.raises(OperationalPause,match='budget_failures'):b.check()
    assert Budget(store,b.path.parent,1,b.limits).summary()['consecutive_failures']==2
    other=copy.deepcopy(b.read());other['consecutive_failures']=0;other['active_since']=time.time()-2;b.write(other)
    with pytest.raises(OperationalPause,match='budget_elapsed'):b.check()


def test_limits_strict_and_no_implicit_extension(tmp_path):
    for kwargs in ({'completion_attempts':0},{'token_allowance':True},{'execution_seconds':0},{'pace_ms':-1}):
        with pytest.raises(ValueError):Limits(**kwargs)
    store,meta,b=budget_fixture(tmp_path);b.start()
    with pytest.raises(ValueError,match='budget_identity_mismatch'):
        Budget(store,b.path.parent,1,Limits(completion_attempts=3))


@pytest.mark.parametrize('role',['scope','aspects','batch','reconciliation','verification','history_rewrite','gap_analysis','question_recommendation'])
def test_each_completion_boundary_reserves_and_blocks_without_dispatch(tmp_path,role):
    from utils.audit_dispatch import observe_audit,audit_dispatch,completion_metadata
    store,meta,b=budget_fixture(tmp_path,completion_attempts=1,token_allowance=100)
    b.start();calls=[]
    async def response():
        calls.append(role)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10,completion_tokens=5))
    async def run():
        with observe_audit(b),completion_metadata(role,10):
            await audit_dispatch('completion',response,output_tokens=20)
            with pytest.raises(OperationalPause,match='budget_completions'):
                await audit_dispatch('completion',response,output_tokens=20)
    asyncio.run(run())
    assert calls==[role] and b.summary()['completion_attempts']==1 and b.summary()['known_tokens']==15
    assert all(item['responsibility']==role for item in b.read()['requests'].values())


def test_unknown_cancel_reservation_no_network_retry_and_task_isolation(tmp_path):
    from utils.audit_dispatch import observe_audit,audit_dispatch,completion_metadata
    _,_,b=budget_fixture(tmp_path);b.start();entered=asyncio.Event();sent=[]
    async def hang():sent.append(True);entered.set();await asyncio.Event().wait()
    async def run():
        with observe_audit(b),completion_metadata('scope',10):
            task=asyncio.create_task(audit_dispatch('completion',hang,output_tokens=20))
            await entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        # Production/unbound context does not inherit another task's audit budget.
        assert await audit_dispatch('completion',lambda:asyncio.sleep(0,result=7),output_tokens=20)==7
        with pytest.raises(OperationalPause,match='unknown_remote_completion'):b.check()
    asyncio.run(run())
    assert len(sent)==1 and b.summary()['tokens_charged']==30 and b.summary()['unknown_reservations']==1


def test_checkpoint_replay_consumes_no_new_allowance(tmp_path):
    from utils.audit_dispatch import observe_audit,audit_dispatch,completion_metadata
    from knowledge_audit.recovery import RowJournal,CheckpointModel
    from tests.test_knowledge_execution_recovery import pinned
    from tests.test_answering_service import ImmediateRunner
    from tests.test_knowledge_coverage_reliability import model_fixture,GOOD
    import httpx
    store,_,_,meta,*_=seed(tmp_path);meta=pinned(store,meta)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1);row['attempt_count']=1
    b=Budget(store,store._path('runs',meta['run_id']),1,Limits());b.start()
    sends=[]
    def response(request):
        sends.append(True)
        return httpx.Response(200,json={'id':'synthetic','object':'chat.completion','created':0,'model':'fixture',
          'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(GOOD)}}],
          'usage':{'prompt_tokens':400,'completion_tokens':20,'total_tokens':420}})
    async def run():
        model,rag,http=model_fixture(response);b.token_counter=model.count_completion_tokens
        journal=RowJournal(store,meta,row,ImmediateRunner());wrapped=CheckpointModel(model,journal)
        try:
            with observe_audit(b):
                assert await wrapped.call('scope',{'question':'Synthetic?'})==GOOD
                assert await wrapped.call('scope',{'question':'Synthetic?'})==GOOD
            assert journal.hits==1 and len(sends)==1
            assert b.summary()['completion_attempts']==1 and b.summary()['known_tokens']==420
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


def test_service_post_and_metadata_counters_are_separate(tmp_path):
    from utils.audit_dispatch import observe_audit,audit_dispatch
    _,_,b=budget_fixture(tmp_path);b.start()
    async def run():
        with observe_audit(b):
            for kind in ('embedding','reranking','metadata','tokenization'):
                await audit_dispatch(kind,lambda:asyncio.sleep(0,result=SimpleNamespace(status_code=200)))
    asyncio.run(run())
    assert b.summary()['completion_attempts']==0
    assert {k:v['attempts'] for k,v in b.summary()['services'].items()}==dict.fromkeys(['embedding','reranking','metadata','tokenization'],1)


def expired(store,meta):
    value=store.owned('runs',meta['run_id'],1);value.update(state='completed',created_at='2000-01-01T00:00:00+00:00')
    store.write(store._path('runs',meta['run_id'])/'meta.json',value)
    return value


def test_cleanup_dry_run_dependencies_holds_and_actual_synthetic_delete(tmp_path):
    from knowledge_audit.retention import plan_cleanup,apply_cleanup
    store,d,s,meta,*_=seed(tmp_path);expired(store,meta)
    before={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    plan=plan_cleanup(store.root,1,30)
    assert plan['candidates']==[meta['run_id']]
    assert before=={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError,match='cleanup_plan_identity'):apply_cleanup(store,plan,'wrong')
    result=apply_cleanup(store,plan,plan['plan_id'])
    assert result['deleted_count']==1 and not store._path('runs',meta['run_id']).exists()
    assert store._path('datasets',d['dataset_id']).exists() and store._path('snapshots',s['snapshot_id']).exists()


def test_retained_recommendation_and_protected_review_package_hold_dependencies(tmp_path):
    from knowledge_audit.retention import plan_cleanup
    from knowledge_audit.privacy import private_directory,private_json
    store,d,s,meta,*_=seed(tmp_path);expired(store,meta)
    for kind,identifier in [('datasets',d['dataset_id']),('snapshots',s['snapshot_id'])]:
        p=store._path(kind,identifier)/'meta.json';m=store.read(p);m['created_at']='2000-01-01T00:00:00+00:00';store.write(p,m)
    package=private_directory(private_directory(store.root/'reviews')/'synthetic_review')
    private_json(package/'manifest.json',{'source_run_id':meta['run_id']})
    plan=plan_cleanup(store.root,1,30)
    assert plan['candidates']==[]
    assert plan['nodes'][meta['run_id']]['reasons']==['referenced_by_retained_artifact']


@pytest.mark.parametrize('mutation',['hold','symlink','new_reference','owner','lease','new_file'])
def test_cleanup_revalidates_and_refuses_races_and_attacks(tmp_path,mutation):
    from knowledge_audit.retention import plan_cleanup,apply_cleanup
    from knowledge_audit.privacy import private_directory,private_json
    store,_,_,meta,*_=seed(tmp_path);expired(store,meta);path=store._path('runs',meta['run_id'])
    plan=plan_cleanup(store.root,1,30);lease=None
    if mutation=='hold':(path/'.hold').touch(mode=0o600)
    if mutation=='symlink':(path/'evil').symlink_to(tmp_path)
    if mutation=='new_reference':
        directory=private_directory(private_directory(store.root/'reviews')/'new');private_json(directory/'manifest.json',{'run_id':meta['run_id']})
    if mutation=='owner':
        m=store.read(path/'meta.json');m['owner_id']=2;store.write(path/'meta.json',m)
    if mutation=='new_file':(path/'unknown.bin').write_bytes(b'synthetic')
    if mutation=='lease':lease=store.lease(meta['run_id'])
    try:
        with pytest.raises(ValueError):apply_cleanup(store,plan,plan['plan_id'])
        assert path.exists()
    finally:
        if lease is not None:os.close(lease)


@pytest.mark.parametrize('before_question',[False,True])
def test_918_budget_pause_retains_boundaries_rows_and_immutable_export(tmp_path,before_question):
    from tests.test_knowledge_execution_recovery import synthetic_918,create
    from tests.test_knowledge_coverage_pipeline import LabeledModel,Retrieval
    from tests.test_answering_service import ImmediateRunner
    from knowledge_audit.jobs import CoverageJobs
    from knowledge_audit.pipeline import CoverageEvaluator
    from utils.audit_dispatch import current_audit,audit_dispatch,completion_metadata
    from dataclasses import asdict
    store,d,s,old,data=synthetic_918(tmp_path)
    limits=Limits(completion_attempts=1 if before_question else 2,pace_ms=0)
    old['settings']['operational_limits']=asdict(limits)
    meta=create(store,d,s,old,'full_input')
    budget=Budget(store,store._path('runs',meta['run_id']),1,limits)
    if before_question:
        request=budget.reserve('completion',20,'scope');budget.dispatched(request);budget.finish(request,usage=20)
    calls=[]
    class Model(LabeledModel):
        async def call(self,role,payload):
            async def operation():
                calls.append(role)
                return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10,completion_tokens=10))
            with completion_metadata(role,10):await audit_dispatch('completion',operation,output_tokens=20)
            return await super().call(role,payload)
    async def factory(_):
        dataset,redactor=store.dataset(meta['dataset_id'],1)
        from tests.test_answering_service import Processor,Rewriter,Classifier
        from knowledge_audit.preparation import QueryPreparer
        return CoverageEvaluator(snapshot=store.snapshot(meta['snapshot_id'],1),model=Model(store.snapshot(meta['snapshot_id'],1),{'1':['a1','a2']}),
            retrieval=Retrieval(['1'],['1']),preparer=QueryPreparer(Processor(),ImmediateRunner(),Rewriter(),Classifier()),redactor=redactor,dataset=dataset)
    async def run():
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        live=store.owned('runs',meta['run_id'],1)
        assert live['state']=='paused' and live['pause_reason']=='budget_completions'
        assert len(calls)==(0 if before_question else 2)
        row=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
        assert row['outcome']=='pending' and row['processing_status']=='interrupted'
        assert row['unknown_completion_count']==0
        assert row['validated_checkpoint_count']==(1 if before_question else 5) # preparation; scope/aspects and two retrieval manifests
        body,m=store.export_revision(meta['run_id'],1,True,create=True)
        assert m['row_count']==918 and m['state']=='paused' and m['execution_counts']['pending_rows']==917
        assert m['operational_budget']['completion_attempts']==limits.completion_attempts
        with pytest.raises(ValueError,match='budget_new_run_required'):await jobs.recover(meta['run_id'],1)
        assert store.export_revision(meta['run_id'],1,True,m['export_revision_id'])[0]==body
        assert budget.summary()['completion_attempts']==limits.completion_attempts
        await jobs.aclose()
    asyncio.run(run())


def test_concurrent_reservation_and_cleanup_coordination(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from knowledge_audit.retention import artifact_access,plan_cleanup,apply_cleanup
    store,meta,b=budget_fixture(tmp_path,completion_attempts=1)
    def reserve():
        try:return b.reserve('completion',10,'scope')
        except OperationalPause:return None
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:reserve(),range(2)))
    assert sum(r is not None for r in results)==1 and b.summary()['completion_attempts']==1
    expired(store,meta);plan=plan_cleanup(store.root,1,30)
    # Emulate a separate worker/thread holding artifact access while cleanup tries.
    import threading
    ready=threading.Event();release=threading.Event()
    def active():
        with artifact_access(store.root):ready.set();release.wait(5)
    thread=threading.Thread(target=active);thread.start();assert ready.wait(5)
    try:
        with pytest.raises(ValueError,match='cleanup_artifacts_busy'):apply_cleanup(store,plan,plan['plan_id'])
    finally:release.set();thread.join(5)


def test_elapsed_deadline_and_failed_budget_write_prevent_inference(tmp_path,monkeypatch):
    from utils.audit_dispatch import observe_audit,audit_dispatch,completion_metadata
    store,meta,b=budget_fixture(tmp_path,execution_seconds=1);b.start()
    entered=[]
    async def operation():entered.append(True);await asyncio.sleep(3)
    async def run():
        with observe_audit(b),completion_metadata('history_rewrite',10):
            with pytest.raises(OperationalPause,match='budget_elapsed'):await audit_dispatch('completion',operation,output_tokens=10)
    asyncio.run(run());assert entered==[True] and b.summary()['unknown_reservations']==1
    # A failure to persist a fresh allowance prevents the SDK call completely.
    store2,meta2,b2=budget_fixture(tmp_path/'second');b2.start();entered.clear()
    monkeypatch.setattr(b2,'write',lambda _:(_ for _ in ()).throw(OSError('synthetic storage error')))
    async def blocked():
        with observe_audit(b2),completion_metadata('scope',10):
            with pytest.raises(OSError):await audit_dispatch('completion',operation,output_tokens=10)
    asyncio.run(blocked());assert not entered


def test_whole_run_elapsed_watch_cancels_silent_factory_and_releases_leases(tmp_path):
    from dataclasses import asdict
    from knowledge_audit.jobs import CoverageJobs,versions
    from tests.test_answering_service import ImmediateRunner
    store,d,s,old,*_=seed(tmp_path)
    meta=store.create_run(1,d['dataset_id'],s['snapshot_id'],old['selected_row_ids'],
        {**old['settings'],'operational_limits':asdict(Limits(execution_seconds=1))},versions())
    async def factory(_):await asyncio.sleep(10)
    async def run():
        jobs=CoverageJobs(store,factory,ImmediateRunner());jobs.start(meta['run_id'],1)
        await asyncio.wait_for(asyncio.gather(*list(jobs.tasks._tasks.values()),return_exceptions=True),4)
        value=store.owned('runs',meta['run_id'],1)
        assert value['state']=='paused' and value['pause_reason']=='budget_elapsed'
        lease=store.lease(meta['run_id']);gate=store.global_lease();os.close(lease);os.close(gate)
        await jobs.aclose()
    asyncio.run(run())


def test_shared_snapshot_hold_and_cleanup_partial_failure_outcome(tmp_path,monkeypatch):
    from knowledge_audit.retention import plan_cleanup,apply_cleanup
    store,d,s,meta,*_=seed(tmp_path);expired(store,meta)
    p=store._path('snapshots',s['snapshot_id'])/'meta.json';m=store.read(p);m.update(authorized_owners=[1,2],created_at='2000-01-01T00:00:00+00:00');store.write(p,m)
    plan=plan_cleanup(store.root,1,30)
    assert s['snapshot_id'] not in plan['candidates']
    monkeypatch.setattr('knowledge_audit.retention.shutil.rmtree',lambda _:(_ for _ in ()).throw(OSError('synthetic-only')))
    # Preserve the platform's safe-delete capability marker on the failure double.
    import shutil
    shutil.rmtree.avoids_symlink_attacks=True
    with pytest.raises(OSError):apply_cleanup(store,plan,plan['plan_id'])
    outcome=store.read(store.root/'cleanup-outcomes'/(plan['plan_id']+'.json'))
    assert outcome['state']=='interrupted_or_failed' and outcome['deleted_count']==0
    assert 'synthetic-only' not in json.dumps(outcome)


def test_unknown_reservation_before_row_dispatch_marker_requires_choice_and_skip(tmp_path):
    from knowledge_audit.jobs import CoverageJobs
    from tests.test_answering_service import ImmediateRunner
    store,_,_,meta,*_=seed(tmp_path)
    b=Budget(store,store._path('runs',meta['run_id']),1,Limits());b.row_id=meta['selected_row_ids'][0]
    b.reserve('completion',30,'scope')  # process died before per-row dispatch marker
    m=store.owned('runs',meta['run_id'],1);m['state']='paused';store.write(store._path('runs',meta['run_id'])/'meta.json',m)
    row=store.row(meta['run_id'],b.row_id,1);row['processing_status']='interrupted';store.save_row(meta['run_id'],row,1)
    async def run():
        jobs=CoverageJobs(store,lambda _:None,ImmediateRunner())
        # Do not schedule work in this recovery-selection regression.
        jobs.start=lambda *_:None
        with pytest.raises(ValueError,match='unknown_remote_completion_requires_choice'):await jobs.recover(meta['run_id'],1)
        await jobs.recover(meta['run_id'],1,unknown_policy='skip_unknown')
        recovered=store.owned('runs',meta['run_id'],1)
        assert recovered['skip_unknown_row_ids']==[b.row_id]
        assert b.summary()['completion_attempts']==1 and b.summary()['tokens_charged']==30
        assert b.read()['requests'][next(iter(b.read()['requests']))]['acknowledgement_revision_id']==recovered['recovery_revision_id']
        await jobs.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('key',['KNOWLEDGE_COVERAGE_MAX_COMPLETIONS','KNOWLEDGE_COVERAGE_MAX_TOKENS','KNOWLEDGE_COVERAGE_MAX_EXECUTION_SECONDS','KNOWLEDGE_COVERAGE_MAX_CONSECUTIVE_FAILURES','KNOWLEDGE_COVERAGE_MIN_FREE_BYTES','KNOWLEDGE_COVERAGE_PACE_MS','KNOWLEDGE_RECOMMENDATION_MAX_COMPLETIONS','KNOWLEDGE_COVERAGE_RETENTION_DAYS'])
def test_operational_env_validation_and_manifest(key):
    from knowledge_audit.settings import load_coverage_settings
    for invalid in ['-1','not_an_integer',True,1.5]:
        with pytest.raises(ValueError):load_coverage_settings({key:invalid})
    settings=load_coverage_settings({});manifest=settings.manifest()
    assert manifest['operational_limits']['completion_attempts']==200
    assert manifest['retention_policy']['automatic_deletion'] is False


def test_unknown_nested_artifact_is_held_before_planning(tmp_path):
    from knowledge_audit.retention import plan_cleanup
    store,_,_,meta,*_=seed(tmp_path);expired(store,meta)
    path=store._path('runs',meta['run_id'])/'rows'/'unrecognized-private-kind.bin'
    path.write_bytes(b'fictional-only');path.chmod(0o600)
    plan=plan_cleanup(store.root,1,30)
    assert meta['run_id'] not in plan['candidates']
    assert 'unknown_artifact_type' in plan['nodes'][meta['run_id']]['reasons']


def test_audit_local_admission_preserves_spare_normal_slot():
    from utils.concurrency import AdmissionLimiter
    from knowledge_audit.operations import AuditAdmission
    from utils.service_errors import ServiceOverloadedError
    async def run():
        shared=AdmissionLimiter(2);audit=AuditAdmission(shared,0)
        async with shared.slot(acquire_timeout=1):
            with pytest.raises(ServiceOverloadedError):await audit.run(lambda:asyncio.sleep(0),acquire_timeout=.06)
            assert await shared.run(lambda:asyncio.sleep(0,result='normal'),acquire_timeout=.1)=='normal'
        assert await audit.run(lambda:asyncio.sleep(0,result='audit'),acquire_timeout=.1)=='audit'
        assert shared.snapshot().active==shared.snapshot().waiting==0
        assert shared.snapshot().acquired_total==shared.snapshot().released_total
    asyncio.run(run())


def test_cleanup_coordination_never_blocks_new_artifact_readers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from knowledge_audit.retention import artifact_access
    from knowledge_audit.privacy import AuditError
    store,_,_,meta,*_=seed(tmp_path)
    with ThreadPoolExecutor(1) as pool:
        with artifact_access(store.root,exclusive=True):
            future=pool.submit(store.row,meta['run_id'],meta['selected_row_ids'][0],1)
            with pytest.raises(AuditError,match='cleanup_artifacts_busy'):future.result(timeout=.2)


def test_missing_published_ledger_cannot_recreate_fresh_allowance(tmp_path):
    store,meta,b=budget_fixture(tmp_path)
    request=b.reserve('completion',30,'scope');b.dispatched(request);b.finish(request,usage=20)
    b.path.unlink() # synthetic filesystem loss after publication/consumed work
    with pytest.raises(ValueError,match='budget_ledger_missing'):
        Budget(store,b.path.parent,1,b.limits)
    assert not b.path.exists()


@pytest.mark.parametrize('reference_kind',['input_id','export_revision'])
def test_review_packages_protect_input_and_export_identity_aliases(tmp_path,reference_kind):
    from knowledge_audit.retention import plan_cleanup
    from knowledge_audit.privacy import private_directory,private_json
    store,d,s,meta,*_=seed(tmp_path);expired(store,meta)
    path=store._path('datasets',d['dataset_id'])/'meta.json';value=store.read(path);value['created_at']='2000-01-01T00:00:00+00:00';store.write(path,value)
    package=private_directory(private_directory(store.root/'reviews')/'synthetic_alias_package')
    if reference_kind=='input_id':
        private_json(package/'manifest.json',{'input_id':d['input_id']});protected=d['dataset_id']
    else:
        _,manifest=store.export_revision(meta['run_id'],1,True,create=True)
        private_json(package/'manifest.json',{'coverage_export_revision_id':manifest['export_revision_id']});protected=meta['run_id']
    plan=plan_cleanup(store.root,1,30)
    assert protected not in plan['candidates']


def test_retained_run_preserves_comparable_historical_counterproofs(tmp_path):
    from knowledge_audit.jobs import versions
    from knowledge_audit.retention import plan_cleanup
    store,d,s,old,*_=seed(tmp_path);expired(store,old)
    current=store.create_run(1,d['dataset_id'],s['snapshot_id'],old['selected_row_ids'],old['settings'],versions())
    value=store.owned('runs',current['run_id'],1);value['state']='completed';store.write(store._path('runs',current['run_id'])/'meta.json',value)
    plan=plan_cleanup(store.root,1,30)
    # A4 eligibility compares older observations of the same input/snapshot.
    # An unexpired retained run must keep an expired possible counterproof.
    assert old['run_id'] not in plan['candidates']
