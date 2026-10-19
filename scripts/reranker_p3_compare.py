#!/usr/bin/env python3
"""Bounded, read-only P3 staging checks. Private evidence stays outside Git."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
import time
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.rrf_p1_compare import capabilities, config_identity, digest, write_private
from tests.retrieval_depth_fixtures import depth_search
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.rag_utils import build_faq_rerank_text
from utils.rag_utils import parse_faq_relevance_fields
from utils.persian_normalization import normalize_persian_text


class RecordingHttp:
    def __init__(self, client):
        self.client = client
        self.calls = []
        self.capability_calls = 0

    async def get(self, *args, **kwargs):
        self.capability_calls += 1
        return await self.client.get(*args, **kwargs)

    async def post(self, url, *, json):
        start = time.perf_counter()
        response = await self.client.post(url, json=json)
        self.calls.append(dict(size=len(json['texts']), elapsed_ms=(time.perf_counter()-start)*1000,
            scoring_identity=digest(json), raw_scores=json.get('raw_scores', 'omitted'),
            scores=response.json() if response.status_code == 200 else None))
        return response


async def normal(inputs, client):
    from openai import AsyncOpenAI
    from utils.RagSystem import RAGSystem
    rag = RAGSystem.__new__(RAGSystem)
    rag._closed = False
    rag.model_id = '/app/model'
    rag._vllm_active = rag._vllm_timeout_total = 0
    rag.client = AsyncOpenAI(base_url=os.environ['VLLM_URL'], api_key='vllm-token-not-needed', max_retries=0, timeout=50)
    outputs, answers = [], []
    try:
        for case in inputs['cases']:
            search = depth_search(case)
            rows = await search.search(case['query'], top_k=50, allowed_docs=['frozen-scope'])
            search.tei_rerank_url = os.environ['TEI_RERANK_URL'].rstrip('/')
            recorder = RecordingHttp(client)
            search._http = recorder
            repetitions = []
            for repeat in range(2):
                start = time.perf_counter()
                selected = await search.rerank_search_results(case['query'], rows, top_k=10)
                repetitions.append(dict(elapsed_ms=(time.perf_counter()-start)*1000,
                    selected_ids=[r.doc_id for r in selected], scores=[r.reranker_score for r in selected]))
                if repeat == 0:
                    context = selected
            related = [dict(question=build_faq_rerank_text(r.content), answer='', _trace_id=r.doc_id) for r in rows]
            start = time.perf_counter()
            related_selected = await search.rerank(case['query'], related, threshold=PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold)
            out = dict(case_id=case['id'], retrieved_ids=[r.doc_id for r in rows],
                scoring_text_identity=digest([build_faq_rerank_text(r.content) for r in rows]),
                repetitions=repetitions, calls=recorder.calls, capability_calls=recorder.capability_calls,
                related_ms=(time.perf_counter()-start)*1000,
                related_selected_ids=[r['_trace_id'] for r in related_selected],
                relevant_selected=len({r.doc_id for r in context} & set(case['relevant_ids'])),
                context_fact_count=sum(f['entry'] in {r.doc_id for r in context} for f in case['required_facts']))
            if case['required_facts']:
                start = time.perf_counter()
                answer = await rag.answer(user_question=case['query'], context=rag.generate_context(context),
                    recent_history='', current_summary='', tone='friendly', response_type='normal', enable_history=False, category='FAQ')
                out['generation_ms'] = (time.perf_counter()-start)*1000
                out['answer_checks'] = {f['id']: bool(re.search(f['pattern'], answer, re.DOTALL)) for f in case['required_facts']}
                out['forbidden_claim'] = any(re.search(p, answer) for p in case['forbidden_patterns'])
                answers.append(dict(case_id=case['id'], answer=answer))
            outputs.append(out)
    finally:
        await rag.client.close()
    return outputs, answers


async def freeze_expanded(inputs, client, directory):
    import psycopg2.extras
    from scripts.kb_signature import POSTGRES_CHUNK_QUERY, create_signature, compare_signatures
    from new_architecture.app.services.history.database import DatabaseManager
    from qdrant_client import QdrantClient
    from utils.concurrency import BoundedBlockingRunner
    from utils.persian_hybrid_search import PersianHybridSearch
    signature = create_signature('p3-before')
    if not signature['cross_store']['consistent'] or signature['postgres']['aggregate_sha256'] != inputs['kb_fingerprint']['aggregate_sha256']:
        raise RuntimeError('kb_changed_since_frozen_reference')
    write_private(directory/'signature-before.json', signature)
    conn = DatabaseManager().get_connection()
    try:
        conn.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(POSTGRES_CHUNK_QUERY)
            rows = cursor.fetchall()
    finally:
        conn.rollback()
        conn.close()
    chunks = {str(r['chunk_id']): dict(text=r['content'], document_name=r['document_title']) for r in rows}
    docs = sorted({c['document_name'] for c in chunks.values() if 'FAQ' in c['document_name']})
    blocking = BoundedBlockingRunner(1)
    qdrant = QdrantClient(host=os.getenv('QDRANT_HOST'), port=int(os.getenv('QDRANT_PORT','6333')),
        api_key=os.getenv('QDRANT_API_KEY'), https=os.getenv('QDRANT_HTTPS','false').lower()=='true', timeout=10)
    search = PersianHybridSearch(qdrant_client=qdrant, chunk_fetcher=lambda titles: {
        cid:c for cid,c in chunks.items() if c['document_name'] in titles}, http_client=client, blocking_runner=blocking)
    cases = []
    try:
        for case in inputs['cases']:
            if not case['id'].startswith('kb-'):
                continue
            for depth in (150,300):
                capture = {}
                original_score, original_dense = search._score_bm25, search._semantic_search
                def sparse(*args):
                    scores, candidates = original_score(*args)
                    capture['sparse'] = [{'id':cid,'score':float(score)} for cid,score in candidates]
                    return scores,candidates
                async def dense(*args, **kwargs):
                    scores = await original_dense(*args, **kwargs)
                    capture['dense'] = [{'id':cid,'score':float(score)} for cid,score in scores.items()]
                    return scores
                search._score_bm25,search._semantic_search = sparse,dense
                start = time.perf_counter()
                result = await search.search(case['query'], top_k=depth, allowed_docs=docs,
                    bm25_candidate_limit=depth, semantic_candidate_limit=depth)
                search._score_bm25,search._semantic_search = original_score,original_dense
                cases.append(dict(case_id=case['id'],query=case['query'],depth=depth,
                    retrieved_ids=[r.doc_id for r in result],relevant_ids=case['relevant_ids'],
                    capture_ms=(time.perf_counter()-start)*1000,**capture))
        second = create_signature('p3-after-freeze')
        if not compare_signatures(signature,second)['status']['FULL_MATCH']:
            raise RuntimeError('kb_changed_during_freeze')
    finally:
        await search.aclose()
        await blocking.aclose()
        qdrant.close()
    frozen = dict(chunks=chunks, allowed_docs=docs, cases=cases)
    frozen['identity'] = digest(frozen)
    write_private(directory/'expanded-inputs.json',frozen)
    return dict(identity=frozen['identity'],cases=[dict(case=c['case_id'],depth=c['depth'],
        returned=len(c['retrieved_ids']),lexical=sum(r['score']>0 for r in c['sparse']),dense=len(c['dense'])) for c in cases])


async def run(directory, phase):
    import httpx
    from scripts.kb_signature import create_signature, compare_signatures
    if phase == 'before':
        inputs = json.loads(Path('/tmp/ragbot-p2-default-20261013/inputs.json').read_text())
        p2 = json.loads(Path('/tmp/ragbot-p2-default-20261013/after.json').read_text())
        if config_identity() != p2['config']:
            raise RuntimeError('p2_configuration_changed')
        write_private(directory/'inputs.json', inputs)
    else:
        inputs = json.loads((directory/'inputs.json').read_text())
        previous = json.loads((directory/'before.json').read_text())['config']
        current = config_identity()
        settings = dict(current['performance'])
        if settings.pop('tei_rerank_max_client_batch_size') != 50 or settings != previous['performance']:
            raise RuntimeError('non_batch_performance_settings_changed')
        for name, value in previous['artifacts'].items():
            if name != 'utils/performance_config.py' and current['artifacts'][name] != value:
                raise RuntimeError('non_batch_artifact_changed')
    copy = dict(inputs)
    identity = copy.pop('identity')
    if digest(copy) != identity:
        raise RuntimeError('frozen_input_changed')
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        serving = await capabilities(client)
        if serving != inputs['capabilities']:
            raise RuntimeError('serving_configuration_changed')
        if phase in ('before', 'after'):
            cases,answers = await normal(inputs,client)
            expanded = await freeze_expanded(inputs,client,directory) if phase == 'before' else None
        elif phase == 'expanded':
            cases, answers, expanded = await expanded_after(inputs, client, directory), [], None
        elif phase == 'comparability':
            cases, answers, expanded = await comparability(inputs, client), [], None
        elif phase == 'retrieval-timing':
            cases, answers, expanded = await retrieval_timing(client, directory), [], None
        elif phase == 'related-normal':
            cases, answers, expanded = await related_normal(inputs, client, directory), [], None
        else:
            cases, answers = await synthetic_expanded(client, serving['VLLM_URL'][0]['max_model_len'])
            expanded = None
        if phase == 'expanded':
            signature = create_signature('p3-after-expanded')
            before_signature = json.loads((directory/'signature-before.json').read_text())
            if not compare_signatures(before_signature, signature)['status']['FULL_MATCH']:
                raise RuntimeError('kb_changed_during_expanded_checks')
            write_private(directory/'signature-after.json',signature)
    summary = dict(phase=phase,input_identity=identity,config=config_identity(),
        capabilities=serving,cases=cases,expanded_freeze=expanded)
    write_private(directory/f'{phase}.json',summary)
    if answers:
        write_private(directory/f'{phase}-answers.json',answers)
    safe = dict(phase=phase,input_identity=identity,config_identity=digest(summary['config']),
        capabilities=serving,case_count=len(cases),requests=[r['size'] for c in cases for r in c.get('calls',[])],
        relevant_selected=sum(c.get('relevant_selected',0) for c in cases),
        context_facts=sum(c.get('context_fact_count',0) for c in cases),
        answer_checks=sum(sum(c.get('answer_checks',{}).values()) for c in cases), expanded=expanded)
    if phase == 'comparability':
        safe = dict(phase=phase,input_identity=identity,config_identity=digest(summary['config']),
            cases=[dict(case_id=c['case_id'],path=c['path'],
                maximum_score_drift=max(o['max_score_drift'] for o in c['observations']),
                order_changes=sum(o['order_changed'] for o in c['observations']),
                selected_set_changes=sum(o['selected_set_changed'] for o in c['observations']),
                requests=[r['size'] for o in c['observations'] for r in o['calls']]) for c in cases])
    if phase == 'retrieval-timing':safe = dict(phase=phase,cases=cases)
    if phase == 'related-normal':
        safe = dict(phase=phase,cases=[dict(case_id=c['case_id'],payload_parity=c['payload_parity'],
            selected_parity=c['selected_parity'],requests=[r['size'] for r in c['calls']]) for c in cases])
    print(json.dumps(safe))


async def retrieval_timing(client, directory):
    """Investigate service latency variation without changing retrieval behavior."""
    import ast
    import subprocess
    from qdrant_client import QdrantClient
    from utils.concurrency import BoundedBlockingRunner
    from utils.persian_hybrid_search import PersianHybridSearch
    from utils.request_instrumentation import RequestTrace, set_current_trace, reset_current_trace
    frozen=json.loads((directory/'expanded-inputs.json').read_text())
    identity=frozen.pop('identity')
    if digest(frozen)!=identity:raise RuntimeError('expanded_frozen_input_changed')
    current=ast.parse((ROOT/'utils/persian_hybrid_search.py').read_text())
    old_source=subprocess.run(['git','show','d45ddf6684a15b8a376fb8277ce68e0df04f7d7e:utils/persian_hybrid_search.py'],
        cwd=ROOT,capture_output=True,text=True,check=True).stdout
    old=ast.parse(old_source)
    def methods(tree):
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PersianHybridSearch')
        return {n.name:ast.dump(n,include_attributes=False) for n in cls.body
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    current_methods,old_methods=methods(current),methods(old)
    names=['search','_score_bm25','_semantic_search','_encode_query','_get_or_build_bm25','_process_query','_normalise_query','_build_temporary_bm25']
    if any(current_methods[name]!=old_methods[name] for name in names):
        raise RuntimeError('retrieval_code_changed')
    chunks,docs=frozen['chunks'],frozen['allowed_docs']
    blocking=BoundedBlockingRunner(1)
    qdrant=QdrantClient(host=os.getenv('QDRANT_HOST'),port=int(os.getenv('QDRANT_PORT','6333')),
        api_key=os.getenv('QDRANT_API_KEY'),https=os.getenv('QDRANT_HTTPS','false').lower()=='true',timeout=10)
    search=PersianHybridSearch(qdrant_client=qdrant,chunk_fetcher=lambda titles:{cid:c for cid,c in chunks.items()
        if c['document_name'] in titles},http_client=client,blocking_runner=blocking)
    observations=[]
    try:
        for index,case in enumerate(frozen['cases'][:2]):
            trace=RequestTrace(request_id=f'p3-retrieval-{index}',process_id=os.getpid())
            token=set_current_trace(trace)
            start=time.perf_counter()
            try:
                rows=await search.search(case['query'],top_k=case['depth'],allowed_docs=docs,
                    bm25_candidate_limit=case['depth'],semantic_candidate_limit=case['depth'])
            finally:reset_current_trace(token)
            total=(time.perf_counter()-start)*1000
            if [r.doc_id for r in rows]!=case['retrieved_ids']:raise RuntimeError('retrieval_order_changed')
            observations.append(dict(case_id=case['case_id'],depth=case['depth'],
                unchanged_checkpoint_methods=names,total_ms=total,spans_ms=trace.durations_ms,
                outside_service_spans_ms=total-sum(trace.durations_ms.values()),returned=len(rows)))
    finally:
        await search.aclose()
        await blocking.aclose()
        qdrant.close()
    return observations


async def related_normal(inputs, client, directory):
    """Pair P2/current on the graph's normal three question-only candidates."""
    import ast
    import subprocess
    from types import MethodType
    import utils.persian_hybrid_search as module
    checkpoint=subprocess.run(['git','show','d45ddf6684a15b8a376fb8277ce68e0df04f7d7e:utils/persian_hybrid_search.py'],
        cwd=ROOT,check=True,capture_output=True,text=True).stdout
    cls=next(n for n in ast.parse(checkpoint).body if isinstance(n,ast.ClassDef) and n.name=='PersianHybridSearch')
    method=next(n for n in cls.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='rerank')
    namespace=dict(module.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'<P2-related-rerank>','exec'),namespace)
    baseline=json.loads((directory/'before.json').read_text())
    outputs=[]
    for case,prior in zip(inputs['cases'],baseline['cases'],strict=True):
        if case['id'] not in ('synthetic-info-1','kb-1','kb-2'):continue
        selected_ids=prior['repetitions'][0]['selected_ids'][:3]
        candidates=[dict(question=parse_faq_relevance_fields(case['chunks'][cid]['text'])['question'],_trace_id=cid) for cid in selected_ids]
        engines={}
        for phase in ('before','after'):
            search=depth_search(case)
            search.tei_rerank_url=os.environ['TEI_RERANK_URL'].rstrip('/')
            search._http=RecordingHttp(client)
            if phase=='before':search.rerank=MethodType(namespace['rerank'],search)
            engines[phase]=search
        observations=[]
        for repeat in range(3):
            phases=('before','after') if repeat%2==0 else ('after','before')
            for phase in phases:
                search=engines[phase]
                start=time.perf_counter()
                result=await search.rerank(case['query'],candidates,threshold=PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold)
                observations.append(dict(phase=phase,repeat=repeat,elapsed_ms=(time.perf_counter()-start)*1000,
                    selected_ids=[r['_trace_id'] for r in result]))
        before_calls,after_calls=engines['before']._http.calls,engines['after']._http.calls
        if [c['scoring_identity'] for c in before_calls]!=[c['scoring_identity'] for c in after_calls]:
            raise RuntimeError('normal_related_payload_changed')
        outputs.append(dict(case_id=case['id'],observations=observations,
            calls=before_calls+after_calls,payload_parity=True,
            capability_calls=engines['after']._http.capability_calls,
            selected_parity=all(o['selected_ids']==observations[0]['selected_ids'] for o in observations)))
    return outputs


async def expanded_after(inputs, client, directory):
    from qdrant_client import QdrantClient
    from utils.concurrency import BoundedBlockingRunner
    from utils.persian_hybrid_search import PersianHybridSearch
    frozen=json.loads((directory/'expanded-inputs.json').read_text())
    identity=frozen.pop('identity')
    if digest(frozen)!=identity:
        raise RuntimeError('expanded_frozen_input_changed')
    chunks,docs=frozen['chunks'],frozen['allowed_docs']
    blocking=BoundedBlockingRunner(1)
    qdrant=QdrantClient(host=os.getenv('QDRANT_HOST'),port=int(os.getenv('QDRANT_PORT','6333')),
        api_key=os.getenv('QDRANT_API_KEY'),https=os.getenv('QDRANT_HTTPS','false').lower()=='true',timeout=10)
    search=PersianHybridSearch(qdrant_client=qdrant,chunk_fetcher=lambda titles:{
        cid:c for cid,c in chunks.items() if c['document_name'] in titles},http_client=client,blocking_runner=blocking)
    outputs=[]
    try:
        for case in frozen['cases']:
            depth=case['depth']
            start=time.perf_counter()
            rows=await search.search(case['query'],top_k=depth,allowed_docs=docs,
                bm25_candidate_limit=depth,semantic_candidate_limit=depth)
            retrieval_ms=(time.perf_counter()-start)*1000
            if [r.doc_id for r in rows]!=case['retrieved_ids']:
                raise RuntimeError('expanded_first_stage_order_changed')
            recorder=RecordingHttp(client)
            search._http=recorder
            repetitions=[]
            for repeat in range(2):
                start=time.perf_counter()
                selected=await search.rerank_search_results(case['query'],rows,top_k=10)
                repetitions.append(dict(elapsed_ms=(time.perf_counter()-start)*1000,
                    selected_ids=[r.doc_id for r in selected],scores=[r.reranker_score for r in selected],
                    relevant_selected=len({r.doc_id for r in selected}&set(case['relevant_ids']))))
                if not all(r.content==chunks[r.doc_id]['text'] and r.metadata['document_name']==chunks[r.doc_id]['document_name'] for r in selected):
                    raise RuntimeError('source_content_or_metadata_changed')
            context_calls=list(recorder.calls)
            if len(context_calls)!=2*((depth+49)//50) or any(r['size']>50 for r in context_calls):
                raise RuntimeError('batch_accounting_failure')
            for offset in range(0,len(context_calls),len(context_calls)//2):
                if sum(r['size'] for r in context_calls[offset:offset+len(context_calls)//2])!=len(rows):
                    raise RuntimeError('lost_candidates')
            related=[dict(question=parse_faq_relevance_fields(r.content)['question'],_trace_id=r.doc_id) for r in rows]
            start=time.perf_counter()
            selected_related=await search.rerank(case['query'],related,threshold=PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold)
            outputs.append(dict(case_id=case['case_id'],depth=depth,input_identity=identity,
                retrieval_ms=retrieval_ms,before_retrieval_ms=case['capture_ms'],retrieved_ids=[r.doc_id for r in rows],
                content_preserved=True,first_stage_parity=True,repetitions=repetitions,calls=recorder.calls,
                capability_calls=recorder.capability_calls,relevant_selected=repetitions[0]['relevant_selected'],
                related_ms=(time.perf_counter()-start)*1000,related_selected_ids=[r['_trace_id'] for r in selected_related]))
            search._http=client
    finally:
        await search.aclose()
        await blocking.aclose()
        qdrant.close()
    return outputs


async def comparability(inputs, client):
    outputs=[]
    for case in (inputs['cases'][0],inputs['cases'][3]):
        rows=await depth_search(case).search(case['query'],top_k=50,allowed_docs=['frozen-scope'])
        for path in ('answer_context','related_questions'):
            texts=([build_faq_rerank_text(r.content) for r in rows] if path=='answer_context' else
                [normalize_persian_text(parse_faq_relevance_fields(r.content)['question']) for r in rows])
            observations=[]
            for limit,order_name in ((50,'original'),(25,'original'),(17,'original'),(25,'rotate-13'),(50,'reverse')):
                permutation=list(range(len(rows)))
                if order_name=='rotate-13':permutation=permutation[13:]+permutation[:13]
                if order_name=='reverse':permutation.reverse()
                for repeat in range(2):
                    search=depth_search(case)
                    search.rerank_max_client_batch_size=limit
                    search.tei_rerank_url=os.environ['TEI_RERANK_URL'].rstrip('/')
                    recorder=RecordingHttp(client)
                    search._http=recorder
                    metrics={}
                    start=time.perf_counter()
                    result=await search._rerank_scores_batched(normalize_persian_text(case['query']),
                        [texts[i] for i in permutation],raw_scores=False if path=='answer_context' else None,metrics=metrics)
                    elapsed=(time.perf_counter()-start)*1000
                    mapped=[(permutation[index],score) for index,score in result]
                    score_map={i:score for i,score in mapped}
                    if len(score_map)!=len(rows):raise RuntimeError('comparability_mapping_failure')
                    ordered=sorted(mapped,key=(lambda item:(-item[1],rows[item[0]].original_rrf_rank,str(rows[item[0]].doc_id)))
                        if path=='answer_context' else (lambda item:-item[1]))
                    selected=ordered[:10] if path=='answer_context' else [r for r in ordered if r[1]>=PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold][:5]
                    selected_ids=[rows[i].doc_id for i,score in selected]
                    baseline=observations[0] if observations else None
                    cutoff=score_map[ordered[min(9,len(ordered)-1)][0]] if path=='answer_context' else PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold
                    observations.append(dict(limit=limit,order=order_name,repeat=repeat,elapsed_ms=elapsed,
                        calls=recorder.calls,scores=[score_map[i] for i in range(len(rows))],
                        ordered_ids=[rows[i].doc_id for i,score in ordered],selected_ids=selected_ids,
                        max_score_drift=max(abs(score_map[i]-baseline['scores'][i]) for i in range(len(rows))) if baseline else 0,
                        order_changed=bool(baseline and [rows[i].doc_id for i,s in ordered]!=baseline['ordered_ids']),
                        selected_set_changed=bool(baseline and set(selected_ids)!=set(baseline['selected_ids'])),
                        cutoff_score=cutoff,relevant_selected=len(set(selected_ids)&set(case['relevant_ids'])),
                        context_fact_count=sum(f['entry'] in selected_ids for f in case['required_facts'])))
            outputs.append(dict(case_id=case['id'],path=path,scoring_text_identity=digest(texts),observations=observations))
    return outputs


async def synthetic_expanded(client, context_limit):
    from tests.rrf_fixtures import case_from_ids, controlled_cases
    from openai import AsyncOpenAI
    from utils.RagSystem import RAGSystem
    reference=controlled_cases()[0]
    ids=[f'distractor-{i:03}' for i in range(300)]
    ids[79],ids[129]='fact-time','fact-cutoff'
    case=case_from_ids(ids,[])
    case['query']=reference['query']
    for cid in ids:
        case['chunks'][cid]=reference['chunks'].get(cid,reference['chunks']['sparse-01'])
    rag=RAGSystem.__new__(RAGSystem)
    rag._closed=False
    rag.model_id='/app/model'
    rag._vllm_active=rag._vllm_timeout_total=0
    rag.client=AsyncOpenAI(base_url=os.environ['VLLM_URL'],api_key='vllm-token-not-needed',max_retries=0,timeout=50)
    original_completion=rag._completion
    token_measurements=[]
    async def checked_completion(**kwargs):
        # Tokenize the actual production messages/chat template; no copied prompt
        # is printed or written, and no source is truncated to fit the budget.
        url=os.environ['VLLM_URL'].rstrip('/').removesuffix('/v1')+'/tokenize'
        response=await client.post(url,json={'model':kwargs['model'],'messages':kwargs['messages'],'add_generation_prompt':True})
        response.raise_for_status()
        count=response.json()['count']
        if not isinstance(count,int) or count+kwargs['max_tokens']>context_limit:
            raise RuntimeError('synthetic_prompt_exceeds_served_context')
        token_measurements.append(dict(prompt_tokens=count,reserved_output_tokens=kwargs['max_tokens']))
        return await original_completion(**kwargs)
    rag._completion=checked_completion
    outputs,answers=[],[]
    try:
        for depth in (150,300):
            for limit in (50,25):
                search=depth_search(case)
                rows=await search.search(case['query'],top_k=depth,allowed_docs=['synthetic-FAQ'],
                    bm25_candidate_limit=depth,semantic_candidate_limit=depth)
                search.rerank_max_client_batch_size=limit
                search.tei_rerank_url=os.environ['TEI_RERANK_URL'].rstrip('/')
                recorder=RecordingHttp(client)
                search._http=recorder
                start=time.perf_counter()
                selected=await search.rerank_search_results(case['query'],rows,top_k=10)
                rerank_ms=(time.perf_counter()-start)*1000
                selected_ids=[r.doc_id for r in selected]
                start=time.perf_counter()
                answer=await rag.answer(user_question=case['query'],context=rag.generate_context(selected),
                    recent_history='',current_summary='',tone='friendly',response_type='normal',enable_history=False,category='FAQ')
                outputs.append(dict(case_id=f'synthetic-{depth}-{limit}',depth=depth,limit=limit,
                    fixture_identity=digest(case),calls=recorder.calls,rerank_ms=rerank_ms,selected_ids=selected_ids,
                    relevant_selected=len(set(selected_ids)&set(reference['relevant_ids'])),
                    context_fact_count=sum(f['entry'] in selected_ids for f in reference['required_facts']),
                    answer_checks={f['id']:bool(re.search(f['pattern'],answer,re.DOTALL)) for f in reference['required_facts']},
                    forbidden_claim=any(re.search(p,answer) for p in reference['forbidden_patterns']),
                    generation_ms=(time.perf_counter()-start)*1000,**token_measurements[-1]))
                answers.append(dict(case_id=outputs[-1]['case_id'],answer=answer))
    finally:
        await rag.client.close()
    return outputs,answers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('before','after','expanded','comparability','synthetic','retrieval-timing','related-normal'))
    parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--confirmed-staging',action='store_true',required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(ROOT):
        raise RuntimeError('private_directory_inside_repository')
    if not directory.exists():
        directory.mkdir(mode=0o700)
    if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise RuntimeError('private_directory_permissions')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        asyncio.run(run(directory,args.phase))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__}),file=sys.stderr)
        sys.exit(2)
