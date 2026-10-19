"""Planner counterexamples: fictional facts only, fixed independent expectations."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from knowledge_audit.jobs import CoverageJobs
from tests.test_answering_service import ImmediateRunner
from tests.test_knowledge_coverage_pipeline import snapshot, LabeledModel, Retrieval, evaluate
from tests.test_knowledge_coverage_access_jobs import seed
from tests.test_knowledge_coverage_access_jobs import audit_runtime
from tests.test_web_auth import setup, login, csrf

from tests.test_knowledge_coverage_access_jobs import coverage_staging

pytestmark = pytest.mark.usefixtures("coverage_staging")


def test_verified_production_full_cannot_be_overwritten_by_audit_miss():
    snap=snapshot({'1':'Synthetic duration and cutoff.','2':'Unrelated synthetic fact.'})
    model=LabeledModel(snap,{'1':['a1','a2']})
    row=evaluate(snap,model,Retrieval(['1'],['2']))[0]
    assert row['outcome']=='covered_reachable'
    assert row['coverage_status']=='full' and row['production_context_sufficiency']=='full'
    assert row['supporting_chunk_ids']==['1']


def test_initial_uncertainty_survives_identical_broader_candidates():
    snap=snapshot({'1':'An ambiguous synthetic policy.'})
    class Uncertain(LabeledModel):
        async def call(self,role,data):
            answer=await super().call(role,data)
            if role=='batch': answer['coverage']='uncertain'
            return answer
    row=evaluate(snap,Uncertain(snap,{}),Retrieval([],['1'],['1']))[0]
    assert row['coverage_status']=='uncertain'
    assert row['processing_status']=='needs_review'
    assert row['outcome'] not in {'possible_gap','possible_partial_gap'}


def test_compatible_complementary_evidence_spans_production_and_audit():
    snap=snapshot({'1':'Synthetic duration is two days.','2':'Synthetic cutoff is 18:00.'})
    model=LabeledModel(snap,{'1':['a1'],'2':['a2']})
    row=evaluate(snap,model,Retrieval(['1'],['2']))[0]
    assert row['coverage_status']=='full' and row['outcome']=='covered_not_reachable'
    assert row['production_context_sufficiency']=='partial'
    assert set(row['supporting_chunk_ids'])=={'1','2'}
    assert any({e['chunk_id'] for e in data['source_evidence']}=={'1','2'}
               for role,data in model.calls if role=='reconciliation')


def test_apparent_all_aspects_without_compatible_verified_proof_needs_review():
    snap=snapshot({str(i):'Synthetic duration.' if i==1 else 'Synthetic cutoff.' for i in range(1,7)})
    class NoProof(LabeledModel):
        async def call(self,role,data):
            answer=await super().call(role,data)
            if role=='reconciliation':
                answer.update(coverage='partial',compatible=True,conflicts=[],unresolved_aspect_ids=[])
            return answer
    row=evaluate(snap,NoProof(snap,{'1':['a1'],'6':['a2']}),Retrieval([],list(str(i) for i in range(1,7))))[0]
    assert row['processing_status']=='needs_review'
    assert row['outcome'] not in {'possible_gap','possible_partial_gap'}
    assert row['review_codes']


def test_production_schema_failure_does_not_destroy_independent_audit_full_proof():
    from knowledge_audit.privacy import AuditError
    snap=snapshot({'1':'Synthetic failed assessment.','2':'Synthetic duration and cutoff.'})
    class ProductionFailure(LabeledModel):
        async def call(self,role,data):
            if role=='batch' and data['entries'][0]['chunk_id']=='1':
                raise AuditError('invalid_model_schema')
            return await super().call(role,data)
    row=evaluate(snap,ProductionFailure(snap,{'2':['a1','a2']}),Retrieval(['1'],['2']))[0]
    assert row['coverage_status']=='full' and row['verification_result']=='accepted'
    assert row['production_context_sufficiency']=='uncertain'
    assert row['production_reachability']=='uncertain' and row['outcome']=='needs_review'
    assert row['evaluated_entry_count']==2
    assert row['phase_assessments']['production']['review_codes']==['production_evaluation_failed']


def test_subset_of_joint_batch_cannot_reuse_full_verdict_or_spend_entries_twice():
    snap=snapshot({'1':'Duration only.','2':'Cutoff only.','3':'Independent complete synthetic facts.'})
    model=LabeledModel(snap,{'1':['a1'],'2':['a2'],'3':['a1','a2']},verification='rejected')
    row=evaluate(snap,model,Retrieval(['1','2'],['1'],['1']))[0]
    assert row['outcome']=='needs_review' and row['coverage_status']!='full'
    assert row['phase_assessments']['initial']['supported_aspect_ids']==['a1']
    assert row['phase_assessments']['initial']['unresolved_aspect_ids']==['a2']
    assert row['evaluated_entry_count']==2
    assert len([c for c in model.calls if c[0]=='batch'])==1
    assert len([c for c in model.calls if c[0]=='verification'])==1


def test_immutable_export_pair_survives_row_mutation_and_repeated_downloads(audit_runtime,setup,monkeypatch):
    from fastapi.testclient import TestClient
    import hashlib
    import main
    from knowledge_audit.settings import CAPABILITIES
    store,d,s,meta,jobs=audit_runtime
    import web_permissions
    setup.users[1]['role']='admin'
    url='/api/knowledge-coverage/runs/'+meta['run_id']
    with TestClient(main.app,raise_server_exceptions=False) as client:
        login(client,'alice')
        first=client.get(url+'/export'); assert first.status_code==200
        row=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
        row.update(processing_status='completed',coverage_status='full',outcome='covered_reachable')
        store.save_row(meta['run_id'],row,1)
        manifest=client.get(url+'/export-manifest').json()
        assert first.headers['x-coverage-export-id']==manifest['export_id']
        assert hashlib.sha256(first.content).hexdigest()==manifest['csv_sha256']
        assert client.get(url+'/export').content==first.content
        assert client.post(url+'/export-revisions').status_code==403
        fresh=client.post(url+'/export-revisions',headers=csrf(client)); assert fresh.status_code==201
        revision=fresh.json()['export_revision_id']
        second=client.get(url+'/export?revision_id='+revision)
        assert second.content!=first.content
        frozen=client.get(url+'/export-manifest?revision_id='+revision).json()
        assert second.headers['x-coverage-export-id']==frozen['export_id']
        assert hashlib.sha256(second.content).hexdigest()==frozen['csv_sha256']
        old=client.get(url+'/export?revision_id='+manifest['export_revision_id'])
        assert old.content==first.content and manifest['state']=='queued'
        # No real role lacks evidence view while keeping export, so restrict the role map for this check.
        monkeypatch.setitem(web_permissions.COVERAGE_ROLE_CAPABILITIES,'admin',frozenset(CAPABILITIES-{'coverage_evidence_view'}))
        assert client.get(url+'/export?revision_id='+revision).status_code==404


@pytest.mark.parametrize('stage',['before_redaction','after_redaction'])
def test_validation_diagnostics_never_save_values_or_arbitrary_field_names(stage):
    import httpx
    from knowledge_audit.model import AuditModel
    from knowledge_audit.privacy import Redactor, AuditError
    from knowledge_audit.settings import load_coverage_settings
    answer={'version':'scope-1','decision':'kb_question','self_contained':True,'context_sufficient':True,'explanation':'Synthetic.'}
    if stage=='before_redaction': answer['SyntheticSensitiveField']='SyntheticPrivateValue'
    else: answer['explanation']='x'*585+' a@b.co'
    sent=[]
    class Rag:
        model_id='fixture'
        async def _completion(self,**kwargs):
            sent.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(answer)))],
                usage=SimpleNamespace(prompt_tokens=400,completion_tokens=20))
    def handle(request):
        if request.url.path=='/v1/models': return httpx.Response(200,json={'data':[{'id':'fixture','max_model_len':8192}]})
        if request.url.path=='/version': return httpx.Response(200,json={'version':'synthetic'})
        return httpx.Response(200,json={'count':400})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            model=AuditModel(Rag(),http,'http://fixture/v1',load_coverage_settings({}),Redactor(b'synthetic-key-12345678901234567890'))
            await model.discover()
            with pytest.raises(AuditError,match='invalid_model_schema'): await model.call('scope',{'question':'Synthetic.'})
            diag=model.metrics[-1]['validation_diagnostics']; assert diag and diag[0]['stage']==stage
            serialized=json.dumps(diag)
            for private in ('SyntheticSensitiveField','SyntheticPrivateValue','a@b.co','x'*585): assert private not in serialized
            assert diag[0]['field_path']==(['*'] if stage=='before_redaction' else ['explanation'])
            assert diag[0]['finish_reason']=='stop' and diag[0]['prompt_tokens']==400
            assert sent[0]['response_format']['type']=='json_schema'
            assert sent[0]['response_format']['json_schema']['strict'] is True
    asyncio.run(run())


@pytest.mark.parametrize('recovers',[True,False])
def test_json_syntax_recovery_is_exactly_one_fresh_response_without_repair(recovers):
    import httpx
    from knowledge_audit.model import AuditModel
    from knowledge_audit.privacy import Redactor, AuditError
    from knowledge_audit.settings import load_coverage_settings
    good={'version':'scope-1','decision':'kb_question','self_contained':True,'context_sufficient':True,'explanation':'Synthetic.'}
    calls=[]
    class Rag:
        model_id='fixture'
        async def _completion(self,**kwargs):
            calls.append(copy.deepcopy(kwargs))
            content=json.dumps(good) if recovers and len(calls)==2 else '{'
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(prompt_tokens=400,completion_tokens=20))
    def handle(request):
        if request.url.path=='/v1/models': return httpx.Response(200,json={'data':[{'id':'fixture','max_model_len':8192}]})
        if request.url.path=='/version': return httpx.Response(200,json={'version':'synthetic'})
        return httpx.Response(200,json={'count':400})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            model=AuditModel(Rag(),http,'http://fixture/v1',load_coverage_settings({}),Redactor(b'synthetic-key-12345678901234567890'))
            await model.discover()
            if recovers: assert (await model.call('scope',{'question':'Synthetic'}))==good
            else:
                with pytest.raises(AuditError,match='invalid_model_schema'): await model.call('scope',{'question':'Synthetic'})
            assert len(calls)==2 and calls[0]==calls[1]
            assert [m['attempt'] for m in model.metrics]==[1,2]
            assert len({m['call_id'] for m in model.metrics})==1
            assert model.metrics[0]['json_syntax']['at_end'] is True
            assert model.metrics[0]['validation_diagnostics'][0]['error_type']=='json_invalid'
    asyncio.run(run())


def test_verified_full_stops_before_remaining_candidates_are_evaluated():
    entries={str(i):'Synthetic fact.' for i in range(1,11)}
    snap=snapshot(entries)
    row=evaluate(snap,LabeledModel(snap,{'1':['a1','a2']}),Retrieval(list(entries),list(entries)))[0]
    assert row['coverage_status']=='full' and row['evaluated_entry_count']==2
    assert row['phase_assessments']['production']['candidates_exhausted'] is False
    assert row['stopping_reason']=='verified_full'


@pytest.mark.parametrize('code,finish,stage,kind',[
    ('incomplete_structured_output','length','before_redaction','json_invalid'),
    ('invalid_model_schema','stop','before_redaction','extra_forbidden'),
    ('invalid_model_schema','stop','after_redaction','json_invalid'),
    ('invalid_citation','stop','before_redaction','json_invalid'),
])
def test_recovery_does_not_retry_length_semantic_or_redaction_failures(code,finish,stage,kind):
    from knowledge_audit.model import AuditModel
    from knowledge_audit.privacy import AuditError
    from knowledge_audit.settings import load_coverage_settings
    model=AuditModel(SimpleNamespace(),None,'http://synthetic/v1',load_coverage_settings({}),None)
    attempts=[]
    async def once(role,data,**kwargs):
        attempts.append(kwargs['attempt'])
        model.metrics.append({'finish_reason':finish,'validation_diagnostics':[{'stage':stage,'error_type':kind}]})
        raise AuditError(code)
    model._call_once=once
    async def run():
        with pytest.raises(AuditError,match=code): await model.call('scope',{'question':'Synthetic'})
        assert attempts==[1]
    asyncio.run(run())


@pytest.mark.parametrize('change',['unchanged','serving','runtime','audit_settings','batch_cap'])
def test_resume_pins_original_identities_before_retaining_completed_rows(tmp_path,change):
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    meta['selected_row_ids']=[e.source_row_id for e in data.selected[:2]]
    meta['processing_row_ids']=meta['selected_row_ids'].copy()
    store.write(store._path('runs',meta['run_id'])/'meta.json',meta)
    current={'serving':{'fixture':'version1'},'runtime':{'production_depth':50,'alias_version':'synthetic-v1'}}
    calls=[]
    class Engine:
        dataset=data
        def __init__(self):
            self.model=LabeledModel(snapshot({'1':'Synthetic.'}),{})
            self.model.serving=copy.deepcopy(current['serving'])
            self.runtime_configuration=copy.deepcopy(current['runtime'])
        async def evaluate(self,event,row):
            calls.append(event.source_row_id)
            return {**row,'processing_status':'completed' if event==data.selected[0] else 'failed',
                    'coverage_status':'full' if event==data.selected[0] else 'uncertain',
                    'outcome':'covered_reachable' if event==data.selected[0] else 'error'}
    async def run():
        async def factory(meta): return Engine()
        jobs=CoverageJobs(store,factory,ImmediateRunner())
        jobs.start(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        original=copy.deepcopy(store.owned('runs',meta['run_id'],1)['versions'])
        original_identity=copy.deepcopy(store.owned('runs',meta['run_id'],1)['run_identities'])
        if change=='serving': current['serving']={'fixture':'version2'}
        if change=='runtime': current['runtime']['production_depth']=150
        if change=='audit_settings':
            edited=store.owned('runs',meta['run_id'],1)
            edited['settings']['entry_budget']=299
            store.update_run(meta['run_id'],1,edited)
        if change=='batch_cap':
            edited=store.owned('runs',meta['run_id'],1)
            edited['settings']['batch_max_entries']=5
            store.update_run(meta['run_id'],1,edited)
        await jobs.recover(meta['run_id'],1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        final=store.owned('runs',meta['run_id'],1)
        assert final['versions']['serving']==original['serving']
        assert final['versions']['runtime_configuration']==original['runtime_configuration']
        assert final['run_identities']['runtime_configuration']==original['runtime_configuration']
        assert final['run_identity_id']
        _,manifest=store.export_revision(meta['run_id'],1,True,create=True)
        assert manifest['run_identities']==original_identity
        assert manifest['run_identity_id']==final['run_identity_id']
        assert manifest['identity_status']=='pinned_before_evaluation'
        if change=='unchanged':
            assert final['state']=='completed' and calls==[data.selected[0].source_row_id,data.selected[1].source_row_id,data.selected[1].source_row_id]
        else:
            assert final['state']=='incompatible'
            assert store.row(meta['run_id'],data.selected[0].source_row_id,1)['outcome']=='needs_review'
            assert calls==[data.selected[0].source_row_id,data.selected[1].source_row_id]
        await jobs.aclose()
    asyncio.run(run())
