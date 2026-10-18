"""A6.2 single bounded staging experiment; synthetic, non-persisting generation.

Never initializes data stores or the answering graph. This is not a load/SLA test.
"""
import argparse
import asyncio
from dataclasses import asdict
import json
import logging
import math
import os
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import urlsplit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


async def run(args):
    from dotenv import dotenv_values
    root=Path(__file__).resolve().parents[1]
    logging.disable(logging.CRITICAL)
    import httpx
    from knowledge_audit.runtime import confirm_staging,code_identity
    from knowledge_audit.privacy import AuditError,Redactor,private_directory,private_json
    from knowledge_audit.model import AuditModel
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.telemetry import sample,gpu_sample
    from knowledge_audit.failures import category
    from knowledge_audit.operations import Budget,Limits,AuditAdmission
    from knowledge_audit.store import CoverageStore
    from utils.audit_dispatch import observe_audit
    from utils.RagSystem import RAGSystem
    from utils.concurrency import BoundedBlockingRunner,AdmissionLimiter,run_with_limit
    from utils.performance_config import PERFORMANCE_SETTINGS as perf
    from utils.read_only_audit import canonical_sha256
    from tests.test_knowledge_coverage_pipeline import snapshot
    from knowledge_audit.evidence import EvidenceIndex
    confirm_staging(confirmed=args.confirmed_staging,model=True)
    target=os.environ.get('TEI_RERANK_URL','')
    if target!=dotenv_values(root/'.env').get('TEI_RERANK_URL') or urlsplit(target).hostname not in {'127.0.0.1','localhost','::1'}:raise AuditError('unconfirmed_service_target')
    task_guard=private_directory(Path('/tmp/faq-a62-task-control'))/'task-budget-cd8989a2.json'
    if task_guard.exists():raise AuditError('resource_experiment_already_started')
    private_json(task_guard,{'version':'a62-task-guard-1','generation_limit':24,'tei_post_limit':80,'generation_posts':0,'tei_posts':0})
    directory=private_directory(args.output.absolute())
    store=CoverageStore(directory/'synthetic-store',ephemeral_test_store=True)
    campaign_path=directory/'campaign.json'
    if campaign_path.exists():raise AuditError('resource_experiment_already_started')
    state={'version':'a62-resources-1','generation_limit':24,'tei_post_limit':80,'generation_posts':0,'tei_posts':0,
        'metadata_requests':0,'started':True,'unknown_remote_completion':False,'observations':[],
        'scope':'synthetic_context_and_controlled_candidates_no_live_hybrid_retrieval','code':code_identity()}
    store.write(campaign_path,state)
    async def before(request):
        path=request.url.path
        if request.method=='POST' and path.endswith('/chat/completions'):
            if state['unknown_remote_completion'] or state['generation_posts']>=24:raise AuditError('diagnostic_budget_exhausted')
            state['generation_posts']+=1
        elif request.method=='POST' and (path.endswith('/embed') or path.endswith('/rerank')):
            if state['unknown_remote_completion'] or state['tei_posts']>=80:raise AuditError('diagnostic_budget_exhausted')
            state['tei_posts']+=1
        else:state['metadata_requests']+=1
        store.write(campaign_path,state)
        store.write(task_guard,{k:state[k] for k in ['generation_limit','tei_post_limit','generation_posts','tei_posts','unknown_remote_completion']})
    runner=BoundedBlockingRunner(2);rag=None
    async with httpx.AsyncClient(timeout=perf.vllm_http_read_timeout_seconds,event_hooks={'request':[before]}) as metadata:
        try:
            # All identity/limit checks precede any completion/TEI POST.
            for name,key in [('embedding','TEI_EMBED_URL'),('reranker','TEI_RERANK_URL')]:
                response=await metadata.get(os.environ[key].rstrip('/')+'/info');response.raise_for_status();body=response.json()
                state[name+'_identity']={k:body.get(k) for k in ['version','max_client_batch_size','max_input_length','auto_truncate']}
                state[name+'_identity']['model_id_sha256']=canonical_sha256(body.get('model_id','unknown'))
            rag=await runner.run(RAGSystem,qdrant_client=None,blocking_runner=runner)
            # Instrument only these newly owned clients; no shared client/settings mutation.
            rag.client._client.event_hooks.setdefault('request',[]).append(before)
            rag.search_engine._http.event_hooks.setdefault('request',[]).append(before)
            if rag.client.max_retries!=0:raise AuditError('network_retries_forbidden')
            redactor=Redactor(b'fictional-a62-resource-key-only-1234567890')
            shared=AdmissionLimiter(perf.request_concurrency_limit,name='a62-isolated-shared')
            settings=load_coverage_settings()
            model=AuditModel(rag,metadata,os.environ['VLLM_URL'],settings,redactor,
                limiter=AuditAdmission(shared,settings.operational_limits.pace_ms))
            await model.discover();state['serving']=dict(model.serving)
            state['client_policy']={'connect':rag.client.timeout.connect,'read':rag.client.timeout.read,'write':rag.client.timeout.write,'pool':rag.client.timeout.pool,'sdk_retries':rag.client.max_retries}
            state['performance_identity']=canonical_sha256(asdict(perf));state['shared_admission_capacity']=shared.capacity
            state['gpu_before']=await gpu_sample();origin=os.environ['VLLM_URL'].rstrip('/').removesuffix('/v1')
            state['telemetry_before']=await sample(metadata,origin)
            metrics=[];original=rag._completion
            async def measured(**kwargs):
                started=time.perf_counter();row={'status':'error','error_category':'none','known_usage':False}
                try:
                    response=await original(**kwargs)
                    row.update(status='returned',known_usage=True,prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,finish_reason=response.choices[0].finish_reason)
                    return response
                except BaseException as error:
                    row['error_category']=category(error)
                    if state['generation_posts'] and row['error_category'] not in {'dispatch_budget_exhausted'}:state['unknown_remote_completion']=True
                    raise
                finally:
                    row['duration_ms']=round((time.perf_counter()-started)*1000,3);metrics.append(row)
            rag._completion=measured
            snap=snapshot({'1':'In fictional FableBank only, paper-card approval takes two days.',
                           '2':'In fictional FableBank only, submit a paper-card request before 18:00.'})
            index=EvidenceIndex(snap)
            question='What are the approval duration and submission cutoff for the fictional FableBank paper card?'
            data={'question':question,'aspects':[{'aspect_id':'a1','description':'approval duration','conditions':[]},
                {'aspect_id':'a2','description':'submission cutoff','conditions':[]}], 'entries':[index.entry('1'),index.entry('2')]}
            state['synthetic_payload_sha256']=canonical_sha256(data)
            context=rag.generate_context([type('Candidate',(),{'content':r['content']})() for r in snap['records']])
            budget_dir=private_directory(directory/'audit-allowance')
            budget=Budget(store,budget_dir,0,Limits(completion_attempts=24,pace_ms=settings.operational_limits.pace_ms),
                token_counter=model.count_completion_tokens)
            budget.start()
            async def reference():
                return await run_with_limit(shared,lambda:rag.answer(question,context,[], '', 'formal','short',
                    enable_history=False,category='FAQ'),acquire_timeout=perf.request_admission_timeout_seconds)
            async def audit():
                with observe_audit(budget):return await model.call('batch',data)
            async def observation(label,operation):
                before_count=len(metrics);started=time.perf_counter();out={'case_id':label,'status':'error'}
                try:
                    async with asyncio.timeout(perf.application_request_timeout_seconds):await operation()
                    out['status']='returned'
                except BaseException as error:
                    out['error_category']=category(error)
                out['duration_ms']=round((time.perf_counter()-started)*1000,3)
                out['completions']=metrics[before_count:] # pair slices are summarized separately below
                state['observations'].append(out);store.write(campaign_path,state)
            for i in range(2):
                if state['unknown_remote_completion']:break
                await observation('reference_alone_'+str(i+1),reference)
            for i in range(2):
                if state['unknown_remote_completion']:break
                await observation('audit_alone_'+str(i+1),audit)
            for i in range(2):
                if state['unknown_remote_completion']:break
                begin=len(metrics)
                await asyncio.gather(observation('reference_with_audit_'+str(i+1),reference),observation('audit_with_reference_'+str(i+1),audit))
                state.setdefault('interference_pairs',[]).append({'pair':i+1,'completions':metrics[begin:]})
            # Controlled candidates exercise unchanged title/taxonomy scoring and
            # global reranking, never PG/Qdrant/hybrid-search recall.
            if not state['unknown_remote_completion']:
                from utils.persian_hybrid_search import SearchResult
                for depth in (settings.initial_depth,settings.broader_depth):
                    planned=math.ceil(depth/min(perf.tei_rerank_max_client_batch_size,state['reranker_identity']['max_client_batch_size']))
                    if state['tei_posts']+planned+1>80:
                        state.setdefault('unexecuted',[]).append({'case_id':'controlled_'+str(depth),'reason':'tei_task_budget'});continue
                    started=time.perf_counter()
                    try:
                        await rag.search_engine._encode_query(question)
                        candidates=[SearchResult(doc_id=str(i),content='question: Fictional paper card approval '+str(i)+'\nanswer: Synthetic only.\nquestion category: Fictional. sub_category: Paper',score=1/(i+1),bm25_score=0,semantic_score=0) for i in range(depth)]
                        selected=await rag.search_engine.rerank_search_results(question,candidates,top_k=depth)
                        state.setdefault('controlled_candidates',[]).append({'depth':depth,'candidate_count':len(candidates),'selected_count':len(selected),'duration_ms':round((time.perf_counter()-started)*1000,3),'status':'returned'})
                    except Exception as error:
                        state.setdefault('controlled_candidates',[]).append({'depth':depth,'status':'error','error_category':category(error)});break
            budget.stop();state['audit_budget']=budget.summary()
            state['audit_model_metrics']=[{k:v for k,v in m.items() if k in {'role','attempt','status','prompt_tokens','completion_tokens','failure_category','phase_timings_ms','duration_ms','finish_reason'}} for m in model.metrics]
            await model.discover()
            state['serving_identity_unchanged']=model.serving==state['serving']
            state['telemetry_after']=await sample(metadata,origin);state['gpu_after']=await gpu_sample()
            state['completion_metrics']=metrics
            for group in ['reference_alone','audit_alone','reference_with_audit','audit_with_reference']:
                samples=[o['duration_ms'] for o in state['observations'] if o['case_id'].startswith(group) and o['status']=='returned']
                state.setdefault('summary',{})[group]={'returned':len(samples),'median_ms':statistics.median(samples) if samples else None,'range_ms':[min(samples),max(samples)] if samples else []}
            state['state']='paused_unknown' if state['unknown_remote_completion'] else 'finished'
        except BaseException as error:
            state.update(state='blocked_or_failed',error_category=category(error))
        finally:
            if rag is not None:await rag.aclose()
            await runner.aclose()
            store.write(campaign_path,state)
    print(json.dumps({k:state.get(k) for k in ['state','generation_posts','tei_posts','metadata_requests','unknown_remote_completion','error_category','summary']}))


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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--confirmed-staging',action='store_true')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:
        asyncio.run(run(args))
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
