"""Deterministic content-safe failure boundaries; no live services or real data."""
import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

import httpx
from openai import AsyncOpenAI
import pytest

from knowledge_audit.failures import category, safe_correlation
from knowledge_audit.model import AuditModel
from knowledge_audit.privacy import AuditError, Redactor
from knowledge_audit.settings import load_coverage_settings
from utils.concurrency import AdmissionLimiter
from utils.RagSystem import RAGSystem
from utils.service_errors import ServiceUnavailableError, ServiceTimeoutError, ServiceProtocolError

PRIVATE = "SyntheticSensitiveValue-do-not-persist"
GOOD = {'version':'scope-1','decision':'kb_question','self_contained':True,
        'context_sufficient':True,'explanation':'Fictional procedure.'}


def redactor():
    return Redactor(b'synthetic-only-01234567890123456789')


def model_fixture(transport, *, limiter=None, count_transport=None):
    def tokens(request):
        return httpx.Response(200,json={'count':400})
    http = httpx.AsyncClient(transport=httpx.MockTransport(count_transport or tokens))
    rag = RAGSystem.__new__(RAGSystem)
    rag._closed, rag._vllm_active, rag._vllm_timeout_total = False, 0, 0
    rag.model_id = 'fixture'
    rag.client = AsyncOpenAI(base_url='http://fixture/v1',api_key='synthetic-only',max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    model = AuditModel(rag,http,'http://fixture/v1',load_coverage_settings({}),redactor(),limiter=limiter)
    model.context_limit = 8192
    return model, rag, http


@pytest.mark.parametrize('kind,code',[(httpx.ReadTimeout,'model_read_timeout'),
    (httpx.ConnectTimeout,'model_connect_timeout'),(httpx.WriteTimeout,'model_write_timeout'),
    (httpx.PoolTimeout,'model_pool_timeout'),(httpx.ConnectError,'model_connection_failure'),
    (httpx.RemoteProtocolError,'model_protocol_rejection')])
def test_translated_sdk_causes_remain_specific_without_network_retries(kind,code):
    sent=[]
    def fail(request):
        sent.append(request)
        raise kind(PRIVATE,request=request)
    async def run():
        model,rag,http=model_fixture(fail,limiter=AdmissionLimiter(1))
        try:
            with pytest.raises(AuditError,match=code): await model.call('scope',{'question':'Synthetic'})
            metric=model.metrics[-1]
            assert metric['failure_category']==code and metric['boundary']=='completion'
            assert metric['dispatched'] is True and metric['completion_tokens'] is None
            assert metric['server_completion_state']=='unknown'
            assert metric['phase_timings_ms']['completion']>=0
            assert PRIVATE not in json.dumps(metric)
            assert len(sent)==1 and len(model.metrics)==1
            assert rag.metrics_snapshot()['vllm_active']==0
            stats=model.limiter.snapshot()
            assert stats.active==stats.waiting==0 and stats.acquired_total==stats.released_total==1
        finally: await rag.client.close(); await http.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('status',[400,429,500])
def test_http_rejection_correlation_never_retains_headers_urls_or_bodies(status):
    def reject(request):
        return httpx.Response(status,json={'error':{'message':PRIVATE}},headers={'x-request-id':PRIVATE,'x-secret':PRIVATE})
    async def run():
        model,rag,http=model_fixture(reject)
        try:
            with pytest.raises(AuditError,match='model_http_rejection'):await model.call('scope',{'question':'Synthetic'})
            metric=model.metrics[-1]
            assert metric['http_status']==status and metric['server_request_ref']
            assert PRIVATE not in json.dumps(metric) and 'x-secret' not in json.dumps(metric)
            assert len(model.metrics)==1
        finally: await rag.client.close();await http.aclose()
    asyncio.run(run())


def test_tokenization_timeout_is_not_a_completion_dispatch():
    def fail(request): raise httpx.ReadTimeout(PRIVATE,request=request)
    async def run():
        model,rag,http=model_fixture(lambda r:None,count_transport=fail)
        try:
            with pytest.raises(AuditError,match='model_read_timeout'):await model.call('scope',{'question':'Synthetic'})
            metric=model.metrics[-1]
            assert metric['boundary']=='tokenization' and metric['dispatched'] is False
            assert metric['prompt_tokens'] is None and rag.metrics_snapshot()['vllm_active']==0
        finally: await rag.client.close();await http.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('outer_first',[False,True])
def test_admission_and_outer_deadlines_are_distinct_and_include_wait(monkeypatch,outer_first):
    import knowledge_audit.model as module
    monkeypatch.setattr(module,'PERFORMANCE_SETTINGS',replace(module.PERFORMANCE_SETTINGS,
        application_request_timeout_seconds=.01 if outer_first else .2,
        request_admission_timeout_seconds=.2 if outer_first else .01))
    async def run():
        limiter=AdmissionLimiter(1)
        model,rag,http=model_fixture(lambda r:None,limiter=limiter)
        try:
            async with limiter.slot(acquire_timeout=1):
                code='outer_operation_deadline' if outer_first else 'admission_timeout'
                with pytest.raises(AuditError,match=code):await model.call('scope',{'question':'Synthetic'})
                metric=model.metrics[-1]
                assert metric['failure_category']==code and metric['boundary']=='admission'
                assert metric['dispatched'] is False and limiter.snapshot().active==1
            stats=limiter.snapshot()
            assert stats.active==stats.waiting==0 and stats.acquired_total==stats.released_total==1
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


def test_outer_completion_deadline_cancels_sdk_and_balances_counters(monkeypatch):
    import knowledge_audit.model as module
    monkeypatch.setattr(module,'PERFORMANCE_SETTINGS',replace(module.PERFORMANCE_SETTINGS,application_request_timeout_seconds=.01))
    async def block(request):await asyncio.Event().wait()
    async def run():
        model,rag,http=model_fixture(block,limiter=AdmissionLimiter(1))
        try:
            with pytest.raises(AuditError,match='outer_operation_deadline'):await model.call('scope',{'question':'Synthetic'})
            assert model.metrics[-1]['boundary']=='completion'
            assert rag.metrics_snapshot()['vllm_active']==model.limiter.snapshot().active==0
            assert len(model.metrics)==1
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('phase',['tokenization','admission','completion'])
def test_cancellation_preserved_with_no_recovery_and_balanced_permits(phase):
    async def run():
        entered=asyncio.Event()
        async def block(request):
            entered.set();await asyncio.Event().wait()
        limiter=AdmissionLimiter(1)
        model,rag,http=model_fixture(block,limiter=limiter,count_transport=block if phase=='tokenization' else None)
        async def perform(): await model.call('scope',{'question':'Synthetic'})
        try:
            if phase=='admission':
                async with limiter.slot(acquire_timeout=1):
                    task=asyncio.create_task(perform())
                    while limiter.snapshot().waiting==0:await asyncio.sleep(0)
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):await task
            else:
                task=asyncio.create_task(perform());await entered.wait();task.cancel()
                with pytest.raises(asyncio.CancelledError):await task
            metric=model.metrics[-1]
            assert metric['status']=='cancelled' and metric['failure_category']=='cancellation'
            assert metric['boundary']==phase and len(model.metrics)==1
            stats=limiter.snapshot()
            assert stats.active==stats.waiting==0 and stats.acquired_total==stats.released_total
            assert rag.metrics_snapshot()['vllm_active']==0
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('error,expected',[(ServiceUnavailableError(PRIVATE),'model_service_failure'),
    (ServiceTimeoutError(PRIVATE),'model_timeout_unknown'),(ServiceProtocolError(PRIVATE),'model_protocol_rejection'),
    (ValueError(PRIVATE),'audit_failed'),(TimeoutError(PRIVATE),'model_timeout_unknown')])
def test_unknown_causes_do_not_claim_read_timeout(error,expected):
    assert category(error)==expected


def test_cause_cycle_is_bounded_and_correlation_is_opaque():
    error=ValueError(PRIVATE);error.__cause__=error
    assert category(error)=='audit_failed'
    result=safe_correlation(SimpleNamespace(_request_id=PRIVATE),redactor())
    assert PRIVATE not in json.dumps(result)


def test_numeric_telemetry_never_copies_labels_or_unrecognized_metrics():
    from knowledge_audit.telemetry import numeric_metrics
    result=numeric_metrics('vllm:num_requests_running{model_name="'+PRIVATE+'"} 2\n'
        'vllm:num_requests_waiting 3\nsecret_metric{token="'+PRIVATE+'"} 8\nvllm:prompt_tokens_total NaN')
    assert result=={'num_requests_running':2,'num_requests_waiting':3}
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize('valid_audit',[False,True])
def test_production_transport_failure_cannot_prove_a_gap_or_negative_reachability(valid_audit):
    from tests.test_knowledge_coverage_pipeline import snapshot,LabeledModel,Retrieval,evaluate
    snap=snapshot({'1':'Fictional unrelated.','2':'Fictional duration and cutoff.'})
    class Failure(LabeledModel):
        async def call(self,role,data):
            if role=='batch' and data['entries'][0]['chunk_id']=='1':
                raise AuditError('model_read_timeout')
            return await super().call(role,data)
    result=evaluate(snap,Failure(snap,{'2':['a1','a2']} if valid_audit else {}),Retrieval(['1'],['2']))[0]
    assert result['outcome']=='needs_review'
    assert result['production_reachability'] not in {'sufficient','insufficient'}
    assert result['coverage_status']==('full' if valid_audit else 'uncertain')


def test_review_package_has_blank_human_labels_full_sources_and_escaped_html(tmp_path):
    from tests.test_knowledge_coverage_access_jobs import seed
    from knowledge_audit.review import review_package,REVIEW_FIELDS
    import hashlib
    store,d,s,meta,data,redactor,prep=seed(tmp_path,queries=tuple('Fictional card question '+str(i) for i in range(5)))
    from knowledge_audit.jobs import versions
    run=store.create_run(1,d['dataset_id'],s['snapshot_id'],[e.source_row_id for e in data.selected],meta['settings'],versions())
    row=store.row(run['run_id'],run['selected_row_ids'][0],1)
    row['standalone_query_redacted']='<script>synthetic()</script>'
    row['production_context_ids']=['1'];store.save_row(run['run_id'],row,1)
    result=review_package(store,[run['run_id']],1)
    from pathlib import Path
    directory=Path(result['directory']);manifest=json.loads((directory/'manifest.json').read_text())
    assert manifest['human_labels_provided'] is False and len(manifest['row_ids'])==5
    for name,sha in manifest['files'].items(): assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==sha
    first=json.loads((directory/(row['source_row_id']+'.json')).read_text())
    assert first['reviewer_fields']=={k:'' for k in REVIEW_FIELDS}
    assert first['observations'][0]['production_selected_evidence'][0]['sentences']
    page=(directory/'index.html').read_text()
    assert '<script>' not in page and '&lt;script&gt;' in page
    assert 'No independent human labels' in page


def test_two_entry_policy_preserves_complete_entries_and_distinct_budget():
    from tests.test_knowledge_coverage_pipeline import snapshot,LabeledModel,Retrieval,evaluate
    from knowledge_audit.settings import BATCH_ENTRY_LIMIT
    answers={str(i):'Fictional fact '+str(i)+'\nCondition: fictional scope only.' for i in range(1,10)}
    snap=snapshot(answers);model=LabeledModel(snap,{})
    row=evaluate(snap,model,Retrieval([],list(answers),list(answers)))[0]
    batches=[data['entries'] for role,data in model.calls if role=='batch']
    assert BATCH_ENTRY_LIMIT==2 and max(map(len,batches))==2
    assert [e['chunk_id'] for b in batches for e in b]==list(answers)
    assert all(e['answer']==answers[e['chunk_id']] for b in batches for e in b)
    assert row['evaluated_entry_count']==9
    assert load_coverage_settings({}).manifest()['batch_policy']=='full-entries-two-1'


def test_failure_categories_survive_restricted_immutable_csv_projection(tmp_path):
    from tests.test_knowledge_coverage_access_jobs import seed
    import csv,io
    store,d,s,meta,data,redactor,prep=seed(tmp_path)
    row=store.row(meta['run_id'],meta['selected_row_ids'][0],1)
    row.update(processing_status='failed',coverage_status='uncertain',outcome='error',error_code='model_read_timeout',
        failure_diagnostics=[{'failure_policy':'audit-failures-1','failure_category':'model_read_timeout',
            'boundary':'completion','server_completion_state':'unknown','attempt':1}])
    store.save_row(meta['run_id'],row,1)
    body,manifest=store.export_revision(meta['run_id'],1,False,create=True)
    rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    assert rows[0]['schema_version']=='coverage-csv-3' and rows[0]['error_code']=='model_read_timeout'
    assert json.loads(rows[0]['failure_diagnostics'])==row['failure_diagnostics']
    assert all(r['export_id']==manifest['export_id'] for r in rows)


def test_length_termination_retains_only_output_shape_and_reported_usage():
    sent=[]
    def reply(request):
        sent.append(request)
        return httpx.Response(200,json={'id':'synthetic','object':'chat.completion','created':1,'model':'fixture',
            'choices':[{'index':0,'message':{'role':'assistant','content':PRIVATE,'reasoning_content':PRIVATE},'finish_reason':'length'}],
            'usage':{'prompt_tokens':400,'completion_tokens':1200,'total_tokens':1600,
                     'completion_tokens_details':{'reasoning_tokens':1100}}})
    async def run():
        model,rag,http=model_fixture(reply)
        try:
            with pytest.raises(AuditError,match='incomplete_structured_output'):await model.call('scope',{'question':'Synthetic'})
            metric=model.metrics[-1]
            assert metric['failure_category']=='output_length' and metric['completion_tokens']==1200
            assert metric['server_completion_state']=='response_received' and metric['reasoning_tokens']==1100
            assert metric['content_characters']==metric['reasoning_characters']==len(PRIVATE)
            assert len(sent)==1 and PRIVATE not in json.dumps(metric)
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


def test_budget_guard_never_dispatches_a_network_recovery():
    async def run():
        model,rag,http=model_fixture(lambda r:pytest.fail('budget guard must precede SDK'))
        async def exhausted(**kwargs):raise AuditError('diagnostic_budget_exhausted')
        rag._completion=exhausted
        try:
            with pytest.raises(AuditError):await model.call('scope',{'question':'Synthetic'})
            metric=model.metrics[-1]
            assert metric['status']=='blocked' and metric['dispatched'] is False
            assert metric['server_completion_state']=='not_dispatched' and len(model.metrics)==1
            assert rag.metrics_snapshot()['vllm_active']==0
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


def test_nested_transport_timeout_is_not_mislabeled_as_outer_deadline():
    def fail(request):raise TimeoutError(PRIVATE)
    async def run():
        model,rag,http=model_fixture(fail)
        try:
            with pytest.raises(AuditError,match='model_timeout_unknown'):await model.call('scope',{'question':'Synthetic'})
            assert model.metrics[-1]['failure_category']=='model_timeout_unknown'
            assert rag.metrics_snapshot()['vllm_active']==0
        finally:await rag.client.close();await http.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('invalid_citation',[True,False])
def test_citation_and_semantic_validation_have_distinct_row_diagnostics(invalid_citation):
    from tests.test_knowledge_coverage_pipeline import snapshot,LabeledModel,Retrieval,evaluate
    snap=snapshot({'1':'Fictional duration and cutoff.'})
    class Bad(LabeledModel):
        async def call(self,role,data):
            result=await super().call(role,data)
            if role=='batch':
                if invalid_citation:result['supports'][0]['citations'][0]['sentence_number']=999
                else:result['supports'][0]['aspect_id']='a999'
            return result
    row=evaluate(snap,Bad(snap,{'1':['a1','a2']}),Retrieval([],['1']))[0]
    assert row['outcome']=='error' and row['coverage_status']=='uncertain'
    expected='citation_validation' if invalid_citation else 'semantic_validation'
    assert row['failure_diagnostics'][0]['failure_category']==expected
