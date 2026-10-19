#!/usr/bin/env python3
"""One A4 fictional staging pilot, hard 40 completions; never evaluates customers."""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


async def run(confirmed):
    logging.disable(logging.CRITICAL)
    from knowledge_audit.runtime import confirm_live_run,live_components,code_identity,serving_identity,configuration_identity
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.store import CoverageStore,now
    from knowledge_audit.privacy import Redactor,private_directory,private_json,AuditError
    from knowledge_audit.recommendation_fixtures import inputs,snapshot,dataset,A4DispatchBudget
    from knowledge_audit.calibration import ControlledCandidates
    from knowledge_audit.preparation import QueryPreparer,prepare_dataset
    from knowledge_audit.pipeline import CoverageEvaluator
    from knowledge_audit.model import AuditModel
    from knowledge_audit.jobs import versions
    from knowledge_audit.recommendation_store import RecommendationStore
    from knowledge_audit.recommendations import RecommendationEngine
    from knowledge_audit.recommendation_schemas import SCHEMAS
    from knowledge_audit.recommendation_prompts import messages
    from utils.read_only_audit import canonical_sha256
    from utils.concurrency import BoundedBlockingRunner,AdmissionLimiter
    from utils.performance_config import PERFORMANCE_SETTINGS
    import httpx
    confirm_live_run(confirmed=confirmed,model=True)
    settings=load_coverage_settings();store=CoverageStore(settings.artifact_dir)
    pilot_root=private_directory(store.root/'recommendation-pilots');lease=store.global_lease();runner=BoundedBlockingRunner(1)
    rag=None;budget=None;meta=None;usage=[];wire=0;started=time.perf_counter()
    try:
        budget=A4DispatchBudget(store,pilot_root)
        if budget.state['used']:raise AuditError('a4_pilot_already_dispatched')
        spec,lock=inputs();snap=snapshot(spec);key=secrets.token_bytes(32);redactor=Redactor(key);data=dataset(spec,redactor)
        directory=private_directory(pilot_root/('a4_'+secrets.token_hex(16)))
        meta={'version':'a4-live-pilot-1','state':'preparing','created_at':now(),'fixture_lock':lock,
            'scope':'fictional_controlled_candidates_no_customer_queries','operator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        private_json(directory/'kb-snapshot.json',snap)
        private_json(directory/'kb-snapshot-manifest.json',{'snapshot_id':snap['snapshot_id'],'content_file_sha256':hashlib.sha256((directory/'kb-snapshot.json').read_bytes()).hexdigest()})
        registered=store.register_snapshot(directory/'kb-snapshot.json',directory/'kb-snapshot-manifest.json',0)
        async with httpx.AsyncClient(timeout=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds) as http:
            rag,rewriter,classifier=await live_components(runner,http)
            if rag.client.max_retries!=0:raise AuditError('a4_network_retry_forbidden')
            original=rag._completion
            async def dispatched(request):
                nonlocal wire
                if request.url.path.endswith('/chat/completions'):wire+=1
            rag.client._client.event_hooks['request'].append(dispatched)
            async def guarded(**kwargs):
                budget.reserve();result=await original(**kwargs)
                usage.append({'prompt_tokens':result.usage.prompt_tokens,'completion_tokens':result.usage.completion_tokens})
                return result
            rag._completion=guarded
            preparer=QueryPreparer(rag.search_engine.processor,runner,rewriter,classifier)
            prepared=await prepare_dataset(data,preparer,redactor)
            imported=store.save_dataset(data,redactor,key,0,prepared)
            ids=[e.source_row_id for e,c in zip(data.selected,spec['cases']) if c['model_selected']]
            coverage=store.create_run(0,imported['dataset_id'],snap['snapshot_id'],ids,{**settings.manifest(),'entry_budget':settings.max_entry_budget,'documents':['Synthetic_FableBank'],'selection_method':'a4_fixed_fictional_cases'},versions())
            model=AuditModel(rag,http,os.environ['VLLM_URL'],settings,redactor,limiter=AdmissionLimiter(1,name='a4-coverage'))
            await model.discover();model.metrics_path=store._path('runs',coverage['run_id'])/'model-metrics.jsonl'
            identities={'serving':dict(model.serving),'runtime_configuration':configuration_identity(data.timestamp_policy,len(ids),redactor),
                'audit_settings':coverage['settings'],'fixture_lock':lock,'retrieval_scope':'controlled_candidates','code':code_identity(),
                'obtainable_serving':await serving_identity(http,redactor)}
            coverage.update(state='running',run_identities=identities,run_identity_id=canonical_sha256(identities),run_identity_captured_at=now())
            store.update_run(coverage['run_id'],0,coverage)
            meta.update(state='running',coverage_run_id=coverage['run_id'],dataset_id=imported['dataset_id'],snapshot_id=snap['snapshot_id'],run_identities=identities)
            store.write(directory/'meta.json',meta)
            for event,case in zip(data.selected,spec['cases']):
                if not case['model_selected']:continue
                if budget.state['used']>=40:continue
                engine=CoverageEvaluator(snapshot=snap,model=model,retrieval=ControlledCandidates(snap,case,initial_depth=settings.initial_depth),preparer=preparer,redactor=redactor,dataset=data,batch_max_entries=settings.batch_max_entries,initial_depth=settings.initial_depth,broader_depth=settings.broader_depth,max_entry_budget=settings.max_entry_budget)
                row=await engine.evaluate(event,store.row(coverage['run_id'],event.source_row_id,0))
                store.save_row(coverage['run_id'],row,0)
                await model.discover()
                if model.serving!=identities['serving']:raise AuditError('audit_serving_drift')
                print(json.dumps({'case_id':case['case_id'],'outcome':row['outcome'],'dispatches':budget.state['used']}),flush=True)
            coverage.update(state='completed',stage='finished',completed_pilot_rows=sum(store.row(coverage['run_id'],i,0)['processing_status']!='pending' for i in ids))
            store.update_run(coverage['run_id'],0,coverage)
            _,source_manifest=store.export_revision(coverage['run_id'],0,True,create=True)
            recs=RecommendationStore(store);revision=recs.create(coverage['run_id'],0,source_manifest['export_revision_id'],ids)
            revision.update(state='running',phase='drafting')
            draft_model=AuditModel(rag,http,os.environ['VLLM_URL'],settings,redactor,limiter=AdmissionLimiter(1,name='a4-recommendation'),
                schemas=SCHEMAS,message_builder=messages,identity_fields={'related_faq_ids','equivalent_faq_ids','taxonomy_path_id'})
            await draft_model.discover();draft_model.metrics_path=recs.path(revision['recommendation_revision_id'])/'model-metrics.jsonl'
            revision['serving_identity']=dict(draft_model.serving)
            draft_engine=RecommendationEngine(draft_model,snap,redactor);source=recs.source(revision['recommendation_revision_id'],0);results=recs.results(revision['recommendation_revision_id'],0)
            for row in source['rows']:
                if row['source_row_id'] not in ids:continue
                if budget.state['used']>=40:
                    results[row['source_row_id']].update(recommendation_status='not_executed',error_code='diagnostic_budget_exhausted');continue
                results[row['source_row_id']]=await draft_engine.draft(row,source['manifest'],recs.observations(source['manifest'],row,0))
                await draft_model.discover()
                if draft_model.serving!=revision['serving_identity']:raise AuditError('audit_serving_drift')
                recs.save_progress(revision['recommendation_revision_id'],0,revision,results)
            revision.update(state='completed',phase='finished');recs.finish(revision['recommendation_revision_id'],0,revision,results)
            evidence=recs.compose(revision['recommendation_revision_id'],0,True);restricted=recs.compose(revision['recommendation_revision_id'],0,False)
            # Hidden fixture labels are loaded only after all model work.
            labels_body=(__import__('knowledge_audit.recommendation_fixtures',fromlist=['ROOT']).ROOT/'labels.hidden.json').read_bytes()
            if hashlib.sha256(labels_body).hexdigest()!=lock['files']['labels.hidden.json']:raise AuditError('a4_label_drift')
            labels=json.loads(labels_body)
            rows=store.rows(coverage['run_id'],0)
            summary=[{'case_id':case['case_id'],'source_row_id':row['source_row_id'],'outcome':row['outcome'],
                'coverage_status':row['coverage_status'],'scope_status':row.get('scope_status'),
                'recommendation_status':results.get(row['source_row_id'],{}).get('recommendation_status','not_selected'),
                'recommendation_error':results.get(row['source_row_id'],{}).get('error_code',''),
                'expected_outcome':labels['cases'][case['case_id']]['expected_outcome']} for case,row in zip(spec['cases'],rows)]
            meta.update(state='completed',finished_at=now(),duration_ms=round((time.perf_counter()-started)*1000),
                dispatches=budget.state['used'],actual_http_dispatches=wire,returned_completions=len(usage),unknown_server_usage=wire-len(usage),
                reported_tokens={k:sum(u[k] for u in usage) for k in ('prompt_tokens','completion_tokens')},
                recommendation_revision_id=revision['recommendation_revision_id'],evidence_export=evidence['export_id'],
                restricted_export=restricted['export_id'],csv_rows=evidence['row_count'],summary=summary)
            store.write(directory/'meta.json',meta)
            print(json.dumps({k:meta[k] for k in ('state','coverage_run_id','recommendation_revision_id','dispatches','actual_http_dispatches','reported_tokens','csv_rows','summary')},sort_keys=True))
    except BaseException:
        if meta is not None:
            meta.update(state='interrupted',dispatches=budget.state['used'],actual_http_dispatches=wire,returned_completions=len(usage))
            store.write(directory/'meta.json',meta)
        raise
    finally:
        try:
            if rag is not None:await rag.aclose()
        finally:
            await runner.aclose();os.close(lease)


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    from knowledge_audit.settings import require_coverage_enabled
    from knowledge_audit.privacy import AuditError
    try:
        require_coverage_enabled()
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--confirmed',action='store_true',dest='confirmed',help='confirm live audit work against the configured services');parser.add_argument('--confirmed-staging',action='store_true',dest='confirmed',help=argparse.SUPPRESS)
    try:asyncio.run(run(parser.parse_args().confirmed))
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print('{"status":"failed","error_code":"a4_pilot_operator_failed"}',file=sys.stderr);raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
