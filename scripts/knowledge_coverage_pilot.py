#!/usr/bin/env python3
"""Trusted local A2 operator: archive A1 and run at most five selected queries."""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
import hashlib
import json
import logging
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def selection(dataset, preparations):
    """Outcome-independent fixed hash/length/history strata; never inspect answers.

    Exclude invalid and A1 unresolved-preparation rows from this initial eligible
    candidate pool, while retaining them in the full export. Banking vocabulary
    is a reproducible sampling hint, not a scope decision or quality label.
    """
    from knowledge_audit.pipeline import explicit_subject
    by_id={r['source_row_id']:r for r in preparations}
    candidates=[e for e in dataset.selected if by_id[e.source_row_id]['preparation_status'] not in {'invalid_input','failed','needs_context'}
        and explicit_subject(e.content) and len(e.content.strip())>=8]
    rank=lambda e:hashlib.sha256(('a2-pilot-strata-1:'+e.source_row_id).encode()).hexdigest()
    candidates.sort(key=rank)
    chosen=[]
    # Source lineage, not textual similarity, establishes previous user events.
    prior_row_ids={e.source_row_id for e in candidates if e.safe_session_ref and any(
        p.safe_session_ref==e.safe_session_ref and p.timestamp is not None and e.timestamp is not None and p.timestamp<e.timestamp for p in dataset.events)}
    buckets=[lambda e:e.source_row_id in prior_row_ids,
        lambda e:8<=len(e.content)<=35,lambda e:36<=len(e.content)<=80,
        lambda e:len(e.content)>80,lambda e:True]
    for accepts in buckets:
        match=next((e for e in candidates if e.source_row_id not in chosen and accepts(e)),None)
        if match: chosen.append(match.source_row_id)
    return chosen[:5]


async def run(args):
    logging.disable(logging.CRITICAL)
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.store import CoverageStore
    from knowledge_audit.privacy import private_json, private_write, AuditError
    from knowledge_audit.jobs import CoverageJobs, versions
    from knowledge_audit.runtime import confirm_staging
    from knowledge_audit.export import coverage_export
    from knowledge_audit.service import standalone_components, build_engine
    from utils.concurrency import BoundedBlockingRunner, AdmissionLimiter
    settings=load_coverage_settings()
    store=CoverageStore(settings.artifact_dir)
    if args.command=='import-a1':
        data,snapshot=store.import_a1(args.a1_directory,args.csv,args.owner_id)
        print(json.dumps({'dataset_id':data['dataset_id'],'snapshot_id':snapshot['snapshot_id'],
            'source_row_count':data['structure']['source_row_count'],'preparation_counts':data['preparation_counts'],
            'durable_root':str(store.root)},sort_keys=True))
        return 0
    if args.command=='review':
        from knowledge_audit.review import review_package
        print(json.dumps(review_package(store,args.run_ids,args.owner_id),sort_keys=True))
        return 0
    confirm_staging(confirmed=args.confirmed_staging,model=True,snapshot=True)
    dataset,redactor=store.dataset(args.dataset_id,args.owner_id)
    prepared=store.preparations(args.dataset_id,args.owner_id)
    selected=args.row_ids or selection(dataset,prepared)
    snap=store.snapshot(args.snapshot_id,args.owner_id)
    config={**settings.manifest(),'entry_budget':args.entry_budget,
            'documents':sorted({r['document_title'] for r in snap['records']}),
            'selection_method':'explicit_ids' if args.row_ids else 'a2-pilot-strata-1: stable hash, available-history and length bands; no outcome fields'}
    meta=store.create_run(args.owner_id,args.dataset_id,args.snapshot_id,selected,config,versions())
    runner=BoundedBlockingRunner(1); limiter=AdmissionLimiter(1,name='coverage-pilot')
    answering=None; close=None
    calls=Counter()
    completion_usage=[]
    try:
        answering,close=await standalone_components(runner)
        rag=answering.agent_service.rag_system
        async def observe(request):
            operation=request.url.path.rstrip('/').rsplit('/',1)[-1]
            if request.method=='POST' and operation in {'embed','rerank','completions'}:
                calls[operation]+=1
        # Dedicated operator process clients only. No hook or configuration on
        # the shared running app/service is modified.
        rag.search_engine._http.event_hooks['request'].append(observe)
        rag.client._client.event_hooks['request'].append(observe)
        completion=rag._completion
        async def measured_completion(**kwargs):
            import time
            started=time.perf_counter()
            value=await completion(**kwargs)
            measurement={'prompt_tokens':value.usage.prompt_tokens,'completion_tokens':value.usage.completion_tokens,
                         'duration_ms':round((time.perf_counter()-started)*1000,3)}
            completion_usage.append(measurement)
            from utils.read_only_audit import canonical_json
            fd=os.open(store._path('runs',meta['run_id'])/'completion-usage.jsonl',os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as stream: stream.write(canonical_json(measurement)+'\n')
            return value
        rag._completion=measured_completion
        async def factory(run_meta):
            return await build_engine(store,run_meta,settings,answering=answering,runner=runner,limiter=limiter)
        jobs=CoverageJobs(store,factory,runner)
        print(json.dumps({'run_id':meta['run_id'],'selected_row_ids':selected,'selected_count':len(selected),
                          'export_denominator':len(dataset.selected)},sort_keys=True),flush=True)
        jobs.start(meta['run_id'],args.owner_id)
        while jobs.tasks.active_job_ids:
            await asyncio.sleep(10)
            current=store.owned('runs',meta['run_id'],args.owner_id)
            print(json.dumps({'run_id':meta['run_id'],'state':current['state'],'stage':current.get('stage'),
                'completed_pilot_rows':current['completed_pilot_rows'],'live_calls':dict(calls)},sort_keys=True),flush=True)
        await jobs.aclose()
    finally:
        if close: await close()
        await runner.aclose()
    meta=store.owned('runs',meta['run_id'],args.owner_id)
    rows=store.rows(meta['run_id'],args.owner_id)
    data,manifest=store.export_revision(meta['run_id'],args.owner_id,True,create=True)
    directory=store._path('runs',meta['run_id'])
    private_write(directory/'coverage.csv',data)
    private_json(directory/'export-manifest.json',manifest)
    summary={'run_id':meta['run_id'],'state':meta['state'],'export_id':manifest['export_id'],
        'export_revision_id':manifest['export_revision_id'],'run_identity_id':meta.get('run_identity_id',''),
        'csv_sha256':manifest['csv_sha256'],'snapshot_id':meta['snapshot_id'],'configuration_id':meta['configuration_id'],
        'source_row_count':len(rows),'selected_ids':selected,'outcome_counts':dict(Counter(r['outcome'] for r in rows)),
        'live_calls':dict(calls),'all_completion_usage':{'prompt_tokens':sum(m['prompt_tokens'] for m in completion_usage),
            'completion_tokens':sum(m['completion_tokens'] for m in completion_usage),'observations':len(completion_usage)},
        'selected_rows':[{'source_row_id':r['source_row_id'],
            'outcome':r['outcome'],'processing_status':r['processing_status'],'coverage':r['coverage_status'],
            'evaluated_entry_count':r['evaluated_entry_count'],'verification_result':r.get('verification_result','not_run'),
            'supported_chunk_ids':r.get('supporting_chunk_ids',[]),
            'missing_aspect_ids':[a['aspect_id'] for a in r.get('unresolved_aspects',[])],
            'review_codes':r.get('review_codes',[]),
            'validation_categories':r.get('validation_diagnostics',[]),
            'failure_diagnostics':r.get('failure_diagnostics',[]),
            'verification_counts':dict(Counter(v['verdict'] for v in r.get('verifications',[]))),
            'model_calls':len(r.get('model_metrics',[])),
            'prompt_tokens':sum(m.get('prompt_tokens') or 0 for m in r.get('model_metrics',[])),
            'completion_tokens':sum(m.get('completion_tokens') or 0 for m in r.get('model_metrics',[])),
            'duration_ms':r.get('duration_ms'), 'error_code':r.get('error_code',''),
            'stopping_reason':r['stopping_reason']} for r in rows if r['source_row_id'] in selected]}
    private_json(directory/'pilot-summary.json',summary)
    print(json.dumps(summary,sort_keys=True))
    return 0 if meta['state']=='completed' else 2


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
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--owner-id',type=int,default=0,help='Operator namespace 0; web ownership requires an explicitly assigned real user ID.')
    commands=p.add_subparsers(dest='command',required=True)
    imp=commands.add_parser('import-a1'); imp.add_argument('--a1-directory',type=Path,required=True); imp.add_argument('--csv',type=Path,required=True)
    pilot=commands.add_parser('pilot'); pilot.add_argument('--dataset-id',required=True); pilot.add_argument('--snapshot-id',required=True)
    pilot.add_argument('--row-ids',nargs='*'); pilot.add_argument('--entry-budget',type=int,default=300); pilot.add_argument('--confirmed-staging',action='store_true')
    review=commands.add_parser('review');review.add_argument('--run-ids',nargs='+',required=True)
    args=p.parse_args()
    if args.owner_id<0: p.error('owner-id must be nonnegative')
    try: return asyncio.run(run(args))
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({'status':'failed','error_code':'a2_operator_failed'}),file=sys.stderr)
        return 2


if __name__=='__main__': raise SystemExit(main())
