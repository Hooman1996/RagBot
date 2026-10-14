#!/usr/bin/env python3
"""One paired A4 question-responsibility check on the frozen fictional boundary."""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


async def run(args):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=False);logging.disable(logging.CRITICAL)
    from knowledge_audit.runtime import confirm_staging
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.store import CoverageStore,now
    from knowledge_audit.privacy import AuditError,private_directory
    from knowledge_audit.recommendation_store import RecommendationStore
    from knowledge_audit.recommendation_fixtures import A4DispatchBudget
    from knowledge_audit.recommendations import analyst_input,validate_questions,safe_error
    from knowledge_audit.recommendation_prompts import messages
    from knowledge_audit.recommendation_schemas import SCHEMAS
    from knowledge_audit.model import AuditModel
    from knowledge_audit.export import _redact
    from utils.read_only_audit import canonical_sha256
    from utils.concurrency import BoundedBlockingRunner,AdmissionLimiter
    from utils.performance_config import PERFORMANCE_SETTINGS
    from utils.RagSystem import RAGSystem
    import httpx
    confirm_staging(confirmed=args.confirmed_staging,model=True)
    settings=load_coverage_settings();store=CoverageStore(settings.artifact_dir);recs=RecommendationStore(store)
    root=private_directory(store.root/'recommendation-pilots');lease=store.global_lease();runner=BoundedBlockingRunner(1);rag=None
    started=time.perf_counter();wire=0;usage=[]
    try:
        budget=A4DispatchBudget(store,root)
        artifact_name='a4-total-holdout.json' if args.final_heldout_check else 'a4-title-candidate.json' if args.metadata_normalization_check else 'a4-question-candidate.json'
        if (root/artifact_name).exists():raise AuditError('a4_candidate_already_executed')
        old=recs.owned(args.recommendation_revision_id,0);source=recs.source(args.recommendation_revision_id,0)
        if source['manifest']['settings'].get('selection_method')!='a4_fixed_fictional_cases':raise AuditError('a4_fictional_source_required')
        row=next(r for r in source['rows'] if r['source_row_id']==args.source_row_id)
        previous=recs.results(args.recommendation_revision_id,0)[args.source_row_id]
        if not (args.metadata_normalization_check or args.final_heldout_check) and previous.get('error_code')!='equivalent_title_requires_review':raise AuditError('a4_paired_boundary_required')
        partial=analyst_input(row,source['manifest'])
        gaps={'version':'gap-analysis-1','gaps':previous['gap_specifications']};lookup=previous['title_lookup']
        payload={'gap_specifications':gaps['gaps'],'resolved_question':partial['resolved_question'],
            'partial_support_relationships':partial['partial_support'],'title_lookup':lookup,'source':partial['source']}
        old_metric=next(m for m in previous['model_metrics'] if m['role']=='question_recommendation')
        if canonical_sha256(payload)!=old_metric['payload_sha256']:raise AuditError('a4_reconstruction_hash_mismatch')
        baseline_payload_sha256=canonical_sha256(payload)
        if args.metadata_normalization_check or args.final_heldout_check:
            from knowledge_audit.recommendations import MetadataIndex
            lookup=MetadataIndex(store.snapshot(old['snapshot_id'],0)).lookup(partial['resolved_question'],row['unresolved_aspects'],{s['entry_id'] for s in partial['partial_support']})
            if args.metadata_normalization_check and not any(t['exact_title_match'] for t in lookup['titles']):raise AuditError('a4_title_control_required')
            payload['title_lookup']=lookup
        meta=recs.create(old['source_run_id'],0,old['source_export_revision_id'],[args.source_row_id])
        meta.update(state='running',phase='paired_question_boundary',baseline_recommendation_revision_id=args.recommendation_revision_id,
            reused_gap_specifications_sha256=canonical_sha256(gaps),paired_payload_sha256=canonical_sha256(payload),
            operator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        _,redactor=store.dataset(store.owned('runs',old['source_run_id'],0)['dataset_id'],0)
        async with httpx.AsyncClient(timeout=PERFORMANCE_SETTINGS.vllm_http_read_timeout_seconds) as http:
            rag=await runner.run(RAGSystem,qdrant_client=None,blocking_runner=runner,tei_http_client=http)
            if rag.client.max_retries!=0:raise AuditError('a4_network_retry_forbidden')
            original=rag._completion
            async def dispatched(request):
                nonlocal wire
                if request.url.path.endswith('/chat/completions'):wire+=1
            rag.client._client.event_hooks['request'].append(dispatched)
            async def guarded(**kwargs):
                budget.reserve();result=await original(**kwargs)
                usage.append({'prompt_tokens':result.usage.prompt_tokens,'completion_tokens':result.usage.completion_tokens});return result
            rag._completion=guarded
            model=AuditModel(rag,http,os.environ['VLLM_URL'],settings,redactor,limiter=AdmissionLimiter(1,name='a4-candidate'),schemas=SCHEMAS,message_builder=messages,
                identity_fields={'related_faq_ids','equivalent_faq_ids','taxonomy_path_id'})
            model.metrics_path=recs.path(meta['recommendation_revision_id'])/'model-metrics.jsonl';await model.discover()
            if model.serving!=old['serving_identity']:raise AuditError('audit_serving_drift')
            if any(source['manifest']['settings'].get(k)!=v for k,v in settings.manifest().items()):raise AuditError('audit_runtime_identity_drift')
            meta.update(serving_identity=dict(model.serving),runtime_settings=settings.manifest())
            results=recs.results(meta['recommendation_revision_id'],0)
            rec=result=dict(results[args.source_row_id]);rec.update(gap_specifications=gaps['gaps'],title_lookup=lookup,
                reused_gap_analysis_from=args.recommendation_revision_id,recommendations=[])
            recs.save_progress(meta['recommendation_revision_id'],0,meta,results)
            try:
                response=validate_questions(await model.call('question_recommendation',payload),gaps,lookup,row)
                response=validate_questions(_redact(response,redactor),gaps,lookup,row)
                rec.update(recommendation_status='drafted',recommendations=response['recommendations'])
            except Exception as error:rec.update(recommendation_status='error',error_code=safe_error(error))
            rec['model_metrics']=model.metrics;results[args.source_row_id]=rec
            await model.discover()
            if model.serving!=meta['serving_identity']:
                rec.update(recommendation_status='error',error_code='audit_serving_drift',recommendations=[])
            meta.update(state='completed',phase='finished',candidate_dispatches=wire,duration_ms=round((time.perf_counter()-started)*1000))
            recs.finish(meta['recommendation_revision_id'],0,meta,results)
            exported=recs.compose(meta['recommendation_revision_id'],0,True)
            report={'version':'a4-question-candidate-1','baseline_recommendation_revision_id':args.recommendation_revision_id,
                'candidate_recommendation_revision_id':meta['recommendation_revision_id'],'source_row_id':args.source_row_id,
                'paired_payload_sha256':canonical_sha256(payload),'input_hash_verified':True,'changed_variable':'final_recommender_holdout_not_a_single_variable_comparison' if args.final_heldout_check else 'title_lookup_normalization_only' if args.metadata_normalization_check else 'question_recommender_prompt_only','baseline_payload_sha256':baseline_payload_sha256,
                'coverage_replayed':False,'gap_analysis_reused':True,'serving_identity_unchanged':True,'candidate_dispatches':wire,
                'returned_completions':len(usage),'unknown_server_usage':wire-len(usage),'a4_total_dispatches':budget.state['used'],
                'reported_tokens':{k:sum(u[k] for u in usage) for k in ('prompt_tokens','completion_tokens')},
                'recommendation_status':rec['recommendation_status'],'error_code':rec.get('error_code',''),
                'export_id':exported['export_id'],'csv_rows':exported['row_count'],'duration_ms':meta['duration_ms'],'created_at':now()}
            from knowledge_audit.privacy import private_json
            private_json(root/artifact_name,report);print(json.dumps(report,sort_keys=True))
    finally:
        try:
            if rag:await rag.aclose()
        finally:await runner.aclose();os.close(lease)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--recommendation-revision-id',required=True);p.add_argument('--source-row-id',required=True);p.add_argument('--confirmed-staging',action='store_true');p.add_argument('--metadata-normalization-check',action='store_true');p.add_argument('--final-heldout-check',action='store_true')
    try:asyncio.run(run(p.parse_args()))
    except Exception:
        print('{"status":"failed","error_code":"a4_candidate_operator_failed"}',file=sys.stderr);raise SystemExit(2)
