"""Fictional, independently specified calibration and private review controls."""
import asyncio
import copy
import csv
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from knowledge_audit.calibration import (load_inputs, snapshot_variant, input_dataset,
    ControlledCandidates, CampaignBudget, CalibrationArtifacts, FrozenResponsibilities)
from knowledge_audit.calibration_scores import load_labels, score
from knowledge_audit.human_labels import Review, Reviewer, template, import_labels
from knowledge_audit.pipeline import CoverageEvaluator
from knowledge_audit.preparation import QueryPreparer
from knowledge_audit.privacy import AuditError, Redactor, private_json, private_directory
from knowledge_audit.settings import load_coverage_settings, CAPABILITIES
from knowledge_audit.store import CoverageStore
from tests.test_answering_service import Processor, ImmediateRunner, Rewriter, Classifier
from tests.test_knowledge_coverage_pipeline import LabeledModel
from tests.test_knowledge_coverage_access_jobs import audit_runtime
from tests.test_web_auth import setup, login

from tests.test_knowledge_coverage_access_jobs import coverage_staging

pytestmark = pytest.mark.usefixtures("coverage_staging")

REDACTOR=Redactor(b'fictional-calibration-test-key-only-12345678')


def test_default_range_validation_and_template_propagation():
    assert load_coverage_settings({}).batch_max_entries==2
    for cap in range(1,6):
        settings=load_coverage_settings({'KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES':str(cap)})
        assert settings.manifest()['batch_max_entries']==cap
        assert settings.manifest()['batch_entries']==cap
    root=Path(__file__).resolve().parents[1]
    for name in ('env.example','env.review.example','Production_ENV.example','.env.example.generated'):
        assert (root/name).read_text().count('KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES=2')==1
    for name in ('env.example','env.review.example'):
        assert 'POSTGRES_USER=CHANGE_ME_POSTGRES_USER' in (root/name).read_text()
        assert 'DEFAULT_DB_USER=CHANGE_ME_POSTGRES_USER' in (root/name).read_text()


@pytest.mark.parametrize('value',['0','6','-1','2.5','abc','',True,2.0,None])
def test_invalid_batch_setting(value):
    with pytest.raises(AuditError):load_coverage_settings({'KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES':value})
    if type(value) is not str:
        with pytest.raises(AuditError):replace(load_coverage_settings({}),batch_max_entries=value)


def test_frozen_fixture_and_label_hashes_and_hidden_inputs(tmp_path):
    spec,lock=load_inputs();labels=load_labels(lock)
    assert len(spec['live_selection'])==12 and len(spec['cases'])==16
    assert labels['authority']=='literal-fictional-fixture-specification'
    assert labels['independent_human_labels'] is False
    assert not {'expected_coverage','expected_scope','support_relationships','missing_aspect_ids'} & set(spec)
    fixture=Path(__file__).resolve().parents[1]/'fixtures/knowledge_coverage_calibration'
    for name in ('inputs.json','labels.hidden.json','lock.json'):
        (tmp_path/name).write_bytes((fixture/name).read_bytes())
    (tmp_path/'inputs.json').write_text('{}')
    with pytest.raises(AuditError,match='fixture_drift'):load_inputs(tmp_path)
    (tmp_path/'labels.hidden.json').write_text('{}')
    with pytest.raises(AuditError,match='label_drift'):load_labels(lock,tmp_path)


def test_seeded_variants_preserve_unrelated_taxonomy_and_equivalent_support():
    spec,lock=load_inputs();cases={c['case_id']:c for c in spec['cases']}
    for case in spec['cases']:
        original=copy.deepcopy(spec)
        baseline,variant=snapshot_variant(spec,case)
        old={r['chunk_id']:r for r in baseline['records']}
        new={r['chunk_id']:r for r in variant['records']}
        assert set(new)==set(old)-set(case['removed_ids'])
        assert all(r==old[cid] for cid,r in new.items()) and spec==original
    assert snapshot_variant(spec,cases['c03'])[0]['snapshot_id']==snapshot_variant(spec,cases['c04'])[0]['snapshot_id']==snapshot_variant(spec,cases['c05'])[0]['snapshot_id']
    baseline,variant=snapshot_variant(spec,cases['c06'])
    assert {'f01','f02'} <= {r['chunk_id'] for r in baseline['records']}
    assert 'f01' not in {r['chunk_id'] for r in variant['records']} and 'f02' in {r['chunk_id'] for r in variant['records']}


def make_engine(case_id,cap=2):
    spec,lock=load_inputs();case=next(c for c in spec['cases'] if c['case_id']==case_id)
    _,snap=snapshot_variant(spec,case)
    # Mock supports derive from explicit record facts, never evaluator outcomes.
    supports={'f01':['a1','a2'],'f02':['a1','a2'],'f03':['a1'],'f04':['a2'],
        'f05':['a1'],'f06':['a2'],'f07':['a1']}
    scope={'c11':'needs_context','c12':'out_of_scope','c15':'private_account','c16':'chitchat'}.get(case_id,'kb_question')
    class Model(LabeledModel):
        async def call(self,role,data):
            assert not any(key in json.dumps(data) for key in ('expected_coverage','support_relationships','label_version'))
            if case_id=='c13' and role=='batch':raise AuditError('invalid_model_schema')
            return await super().call(role,data)
    model=Model(snap,supports,aspects=1 if case_id=='c08' else 2,scope=scope,
        invalid_citation=case_id=='c14',conflicts=case_id=='c07',verification='rejected' if case_id=='c07' else 'accepted')
    dataset=input_dataset(case,REDACTOR)
    preparer=QueryPreparer(Processor(),ImmediateRunner(),Rewriter(),Classifier())
    engine=CoverageEvaluator(snapshot=snap,model=model,retrieval=ControlledCandidates(snap,case),
        preparer=preparer,redactor=REDACTOR,dataset=dataset,batch_max_entries=cap)
    return engine,model,dataset


@pytest.mark.parametrize('case_id',[f'c{i:02}' for i in range(1,17)])
def test_all_controlled_families_deterministic_end_to_end(case_id):
    engine,model,data=make_engine(case_id)
    row=asyncio.run(engine.evaluate(data.selected[0],{}))
    label=load_labels(load_inputs()[1])['cases'][case_id]
    if label['expected_scope']=='error':
        assert row['outcome']=='error' and row['coverage_status']=='uncertain'
    elif label['expected_scope'] in {'private_account','chitchat','out_of_scope'}:
        assert row['outcome']=='excluded' and row['scope_status']==label['expected_scope']
    else:
        assert row['coverage_status']==label['expected_coverage'],(case_id,row['outcome'],row.get('review_codes'))
        assert row['production_context_sufficiency']==label['expected_production']
        if label['missing_aspect_ids']:
            assert [a['aspect_id'] for a in row['unresolved_aspects']]==label['missing_aspect_ids']
    assert row['recommendation_status']=='unassessed'
    if row['coverage_status']=='full':
        assert row['verification_result']=='accepted' and row['supporting_sentence_refs']
    assert max((len(d['entries']) for role,d in model.calls if role=='batch'),default=0)<=2


def test_isolated_batch_caps_parity_frozen_responsibilities_and_token_packing():
    async def run():
        left,lmodel,ld=make_engine('c03',2)
        right,rmodel,rd=make_engine('c03',5)
        a,b=await asyncio.gather(left.evaluate(ld.selected[0],{}),right.evaluate(rd.selected[0],{}))
        assert a['coverage_status']==b['coverage_status']=='full'
        assert max(len(d['entries']) for role,d in lmodel.calls if role=='batch')==2
        assert max(len(d['entries']) for role,d in rmodel.calls if role=='batch')==3
        frozen=FrozenResponsibilities(rmodel,a)
        assert await frozen.call('aspects',{'question':'unchanged'})==a['aspect_checklist']
        assert await frozen.call('scope',{})==a['scope_decision']
        # The compatible token counter may force fewer than the configured cap.
        packed,pm,pd=make_engine('c03',5)
        async def fits(role,data):return len(data.get('entries',[]))<=1
        pm.fits=fits
        c=await packed.evaluate(pd.selected[0],{})
        assert c['coverage_status']=='full'
        assert all(len(d['entries'])==1 for role,d in pm.calls if role=='batch')
    asyncio.run(run())


def test_controlled_adapter_detects_mutation_and_never_calls_live_retrieval():
    engine,_,_=make_engine('c03')
    adapter=engine.retrieval
    initial=asyncio.run(adapter.fetch('fictional',depth=150))
    assert initial['scope']=='controlled_candidate_manifest'
    adapter.snapshot['records'][0]['answer']='altered'
    with pytest.raises(AuditError,match='source_or_index_drift'):asyncio.run(adapter.check())


def test_dispatch_budget_is_durable_and_cannot_reset_for_recovery(tmp_path):
    store=CoverageStore(tmp_path,ephemeral_test_store=True)
    directory=private_directory(tmp_path/'calibrations')
    budget=CampaignBudget(store,directory)
    for _ in range(119):budget.reserve()
    fresh=CampaignBudget(store,directory);fresh.reserve()
    with pytest.raises(AuditError,match='budget_exhausted'):fresh.reserve()
    assert CampaignBudget(store,directory).state=={'version':'a3-dispatch-budget-1','limit':120,'used':120,'blocked':1}


def fixture_artifacts(store,owner=1):
    artifacts=CalibrationArtifacts(store)
    meta=artifacts.create(owner,load_coverage_settings({}).manifest(),load_inputs()[1],[])
    meta.update(state='completed',run_identity_id='a'*64)
    store.write(artifacts.path(meta['calibration_id'])/'meta.json',meta)
    rows=[{'source_row_id':'row_'+f'{i:032x}','case_id':f'c{i:02}','batch_max_entries':2,
        'source_record_ordinal':i,'state':'unexecuted','query':'=SUM(1,2)\nپرسش، آزمایشی',
        'prediction':{'processing_status':'failed','outcome':'error','coverage_status':'uncertain',
            'error_code':'invalid_model_schema','supporting_sentence_refs':[{'fictional':True}],
            'unresolved_aspects':[{'aspect_id':'a1'}]}} for i in range(1,4)]
    artifacts.freeze(meta,rows)
    return artifacts,meta,rows


def test_immutable_calibration_export_identity_order_permissions_and_errors(tmp_path):
    store=CoverageStore(tmp_path,ephemeral_test_store=True);artifacts,meta,rows=fixture_artifacts(store)
    body,manifest=artifacts.download(meta['calibration_id'],1,True)
    assert body.startswith(b'\xef\xbb\xbf')
    parsed=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    assert [r['source_row_id'] for r in parsed]==[r['source_row_id'] for r in rows]
    assert all(r['export_id']==manifest['export_id'] and r['query'].startswith("'=") and r['outcome']=='error' for r in parsed)
    rows[0]['prediction']['outcome']='covered_reachable'
    store.write(artifacts.path(meta['calibration_id'])/'rows.json',rows)
    assert artifacts.download(meta['calibration_id'],1,True)==(body,manifest)
    restricted,rm=artifacts.download(meta['calibration_id'],1,False)
    assert rm['export_id']!=manifest['export_id'] and rm['evidence_visible'] is False
    assert all(json.loads(r['evidence'])==[] for r in csv.DictReader(io.StringIO(restricted.decode('utf-8-sig'))))
    with pytest.raises(AuditError,match='artifact_not_found'):artifacts.download(meta['calibration_id'],2,True)
    with pytest.raises(FileExistsError):artifacts.freeze(meta,rows)
    path=artifacts.path(meta['calibration_id'])/'evidence.csv'
    path.chmod(0o644)
    with pytest.raises(AuditError,match='permissions'):artifacts.download(meta['calibration_id'],1,True)


def test_metrics_keep_errors_and_unexecuted_in_denominators():
    labels=load_labels(load_inputs()[1]);rows=[]
    for i,outcome,coverage,status in [(1,'possible_gap','unsupported','completed'),(4,'covered_reachable','full','completed'),
            (5,'error','uncertain','failed'),(7,'error','uncertain','failed'),(9,'pending','not_evaluated','pending')]:
        rows.append({'case_id':f'c{i:02}','state':'unexecuted' if i==9 else 'error' if outcome=='error' else 'completed',
            'prediction':{'outcome':outcome,'coverage_status':coverage,'processing_status':status}})
    metrics=score(rows,labels)
    assert metrics['completed']['count']==2 and metrics['completed']['denominator']==5
    assert metrics['errors']['count']==2 and metrics['unexecuted']['count']==1
    assert metrics['false_full_case_ids']==['c04'] and metrics['false_gap_case_ids']==['c01']
    assert metrics['coverage_all_selected_kb']=={'count':0,'denominator':5,'fraction':0}
    assert metrics['coverage_completed_kb']['denominator']==2


def test_calibration_api_default_deny_ownership_export_projection(audit_runtime,setup,monkeypatch):
    import main
    store,*_=audit_runtime;artifacts,meta,rows=fixture_artifacts(store)
    url='/api/knowledge-coverage/calibrations/'+meta['calibration_id']
    import web_permissions
    setup.users[1]['role']='user';setup.users[2]['role']='admin'
    with TestClient(main.app,raise_server_exceptions=False) as client:
        assert client.get(url).status_code==401
        login(client,'alice')
        assert client.get(url).status_code==403
        setup.users[1]['role']='admin'
        assert client.get('/api/knowledge-coverage/calibrations').json()[0]['scope']=='controlled_candidates_fictional_only'
        assert client.get(url).json()['configuration']['batch_max_entries']==2
        body=client.get(url+'/export').content;manifest=client.get(url+'/export-manifest').json()
        assert hashlib.sha256(body).hexdigest()==manifest['csv_sha256']
        # No real role has these partial sets, so restrict the role map for these checks.
        monkeypatch.setitem(web_permissions.COVERAGE_ROLE_CAPABILITIES,'admin',frozenset({'coverage_export_download'}))
        assert client.get(url).status_code==403
        assert client.get(url+'/export').status_code==403
        monkeypatch.setitem(web_permissions.COVERAGE_ROLE_CAPABILITIES,'admin',frozenset({'coverage_export_download','coverage_results_view'}))
        assert client.get(url+'/export-manifest').json()['evidence_visible'] is False
        monkeypatch.setitem(web_permissions.COVERAGE_ROLE_CAPABILITIES,'admin',frozenset(CAPABILITIES))
        setup.users[1]['role']='user'
        login(client,'bob')
        for suffix in ('','/export','/export-manifest'):assert client.get(url+suffix).status_code==404
        assert client.get('/api/knowledge-coverage/calibrations').json()==[]


def review_package(store,meta,data,snapshot):
    package_id='review_'+'1'*32
    path=private_directory(private_directory(store.root/'reviews')/package_id)
    row={'source_row_id':data.selected[0].source_row_id,'observations':[{'run_id':meta['run_id'],
        'snapshot_id':snapshot['snapshot_id'],'coverage_status':'full','outcome':'covered_reachable',
        'production_context_sufficiency':'full'}]}
    private_json(path/'row.json',row)
    private_json(path/'manifest.json',{'files':{'row.json':hashlib.sha256((path/'row.json').read_bytes()).hexdigest()}})
    return package_id


def test_review_blank_pending_declared_provenance_and_strict_citations(tmp_path):
    from tests.test_knowledge_coverage_access_jobs import seed
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    snap=store.snapshot(s['snapshot_id'],1)
    package_id=review_package(store,meta,data,snap)
    blank=template(store,package_id)
    pending=import_labels(store,package_id,blank,owner=1)
    assert pending['summary']['status']=='pending_not_reviewed'
    assert pending['summary']['coverage_agreement']['fraction'] is None
    assert blank['reviewer'] is None and all(r['status']=='not_reviewed' for r in blank['reviews'])
    completed=copy.deepcopy(blank)
    row=completed['reviews'][0]
    row.update(status='completed',intended_question='Synthetic duration?',aspect_agreement='agree',
        aspects=[{'aspect_id':'a1','description':'Duration','conditions':[]}],coverage='full',
        production_context_sufficiency='full',evidence=[{'aspect_id':'a1','applicability':'applicable','conditions':[],
            'citations':[{'snapshot_id':snap['snapshot_id'],'faq_entry_id':'1','chunk_id':'1','sentence_number':1}]}])
    with pytest.raises(AuditError,match='human_reviewer_required'):import_labels(store,package_id,completed,owner=1)
    completed['reviewer']={'identity':'Synthetic reviewer fixture','provenance':'declared_independent_human',
        'attests_independent_human_review':True,'affiliation':'Fictional testing only'}
    good=import_labels(store,package_id,completed,owner=1)
    assert good['summary']['completed_observations']==1 and good['summary']['coverage_agreement']['count']==1
    bad=copy.deepcopy(completed);bad['reviews'][0]['evidence'][0]['citations'][0]['sentence_number']=999
    with pytest.raises(AuditError,match='invalid_citation'):import_labels(store,package_id,bad,owner=1)
    bad=copy.deepcopy(completed);bad['reviews'][0]['snapshot_id']='f'*64
    with pytest.raises(AuditError,match='observation_mismatch'):import_labels(store,package_id,bad,owner=1)
    bad=copy.deepcopy(completed);bad['reviews'].append(bad['reviews'][0])
    with pytest.raises(AuditError,match='observation_mismatch'):import_labels(store,package_id,bad,owner=1)
    bad=copy.deepcopy(completed);bad['reviewer']['provenance']='model'
    with pytest.raises(AuditError,match='invalid_human_labels'):import_labels(store,package_id,bad,owner=1)
    bad=copy.deepcopy(blank);bad['reviews'][0]['notes']='not actually blank'
    with pytest.raises(AuditError,match='invalid_human_labels'):import_labels(store,package_id,bad,owner=1)


def test_incompatible_calibration_cannot_export_a_covered_outcome(tmp_path):
    store=CoverageStore(tmp_path,ephemeral_test_store=True)
    artifacts=CalibrationArtifacts(store)
    meta=artifacts.create(1,load_coverage_settings({}).manifest(),load_inputs()[1],[])
    meta['state']='incompatible'
    store.write(artifacts.path(meta['calibration_id'])/'meta.json',meta)
    artifacts.freeze(meta,[{'source_row_id':'row_'+'1'*32,'case_id':'c01','state':'completed',
        'prediction':{'coverage_status':'full','outcome':'covered_reachable'}}])
    body,manifest=artifacts.download(meta['calibration_id'],1,True)
    row=next(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    assert manifest['state']=='incompatible' and row['coverage_status']=='uncertain'
    assert row['outcome']=='needs_review' and row['error_code']=='calibration_identity_drift'


def test_environment_validator_enforces_new_batch_setting(tmp_path):
    from scripts.validate_environment import analyze_environment
    from tests.test_validate_environment import minimum_environment
    for value,invalid in [('0',True),('6',True),('2.5',True),('1',False),('2',False),('5',False)]:
        path=tmp_path/'env.synthetic'
        path.write_text(minimum_environment()+'KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES='+value+'\n')
        result=analyze_environment(path,'staging',show_optional=True,process_environment={})
        errors=[f for f in result['findings'] if f['severity']=='critical' and f['variable']=='KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES']
        assert bool(errors)==invalid


def test_full_label_requires_every_authored_fact_sentence():
    labels=load_labels(load_inputs()[1])
    prediction={'outcome':'covered_reachable','coverage_status':'full','processing_status':'completed',
        'supporting_sentence_refs':[{'chunk_id':'f01','sentence_number':1}]}
    rows=[{'case_id':'c01','state':'completed','prediction':prediction}]
    metrics=score(rows,labels)
    assert metrics['coverage_completed_kb']['count']==1
    assert metrics['full_required_fact_citations_present']['count']==0
    prediction['supporting_sentence_refs'].append({'chunk_id':'f01','sentence_number':2})
    assert score(rows,labels)['full_required_fact_citations_present']['count']==1


@pytest.mark.parametrize('cap',[2,5])
@pytest.mark.parametrize('case_id,expected',[('c07','needs_review'),('c09','possible_gap')])
def test_referral_and_condition_hazards_at_both_batch_caps(cap,case_id,expected):
    engine,model,data=make_engine(case_id,cap)
    row=asyncio.run(engine.evaluate(data.selected[0],{}))
    assert row['outcome']==expected and row['coverage_status']!='full'
    assert row['evaluated_entry_count']==4
    if case_id=='c07':assert any(role=='reconciliation' for role,_ in model.calls) or any(v['verdict']=='rejected' for v in row['verifications'])
