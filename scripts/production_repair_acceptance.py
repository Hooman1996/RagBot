#!/usr/bin/env python3
"""Bounded P1–P4 validation, not audit runtime code. Never writes KB/chat data.

Private snapshots and model answers stay outside Git (directory 0700/files 0600).
Stdout contains only identifiers, counts, timing and generic errors.
Exit 0 means checks executed, not release approval. Quality labels, human review,
live transactional writes, visuals and load readiness require separate evidence.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MethodType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.rrf_p1_compare import capabilities, config_identity, digest, percentiles, write_private
from scripts.reranker_p3_compare import RecordingHttp
from tests.retrieval_depth_fixtures import depth_search
from utils.performance_config import PERFORMANCE_SETTINGS as SETTINGS

logging.disable(logging.CRITICAL)
P0 = '0663fa07acaf2ba9433789e8655643b9e7d6b163'
P1 = 'c8338050aa548cfc3f48f0927d4bcd270c2e608f'
P2 = 'd45ddf6684a15b8a376fb8277ce68e0df04f7d7e'
P3_DIR = Path('/tmp/ragbot-p3-batching-20261013')


class SafeRecordingHttp(RecordingHttp):
    async def post(self, url, *, json):
        response = await super().post(url, json=json)
        self.calls[-1]['service_metrics'] = {}
        for name in ('x-compute-tokens', 'x-total-time', 'x-queue-time', 'x-inference-time', 'x-tokenization-time'):
            value = response.headers.get(name)
            if value is not None:
                try:
                    self.calls[-1]['service_metrics'][name] = float(value)
                except ValueError:
                    pass  # Optional telemetry must not change the protocol verdict.
        return response


def checkpoint(commit, names=('search', '_score_bm25', 'rerank_search_results')):
    import utils.persian_hybrid_search as module
    source = subprocess.run(['git', 'show', f'{commit}:utils/persian_hybrid_search.py'],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'PersianHybridSearch')
    methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    if len(methods) != len(names):
        raise RuntimeError('checkpoint_contract_changed')
    for method in methods:
        method.decorator_list = []
    namespace = dict(module.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), '<checkpoint-methods>', 'exec'), namespace)
    return namespace


def frozen_inputs():
    inputs = json.loads((P3_DIR / 'inputs.json').read_text())
    copy = dict(inputs)
    identity = copy.pop('identity')
    if digest(copy) != identity or config_identity() != json.loads((P3_DIR / 'after.json').read_text())['config']:
        raise RuntimeError('frozen_input_or_configuration_changed')
    return inputs


def engine(case, methods=None):
    search = depth_search(case)
    if methods:
        search.search = MethodType(methods['search'], search)
        search._score_bm25 = methods['_score_bm25']
        search.rerank_search_results = MethodType(methods['rerank_search_results'], search)
    return search


async def offline(directory):
    inputs = frozen_inputs()
    versions = {name: checkpoint(commit) for name, commit in [('p0', P0), ('p1', P1), ('p2', P2)]}
    outputs = []
    for case in inputs['cases']:
        searches = {name: engine(case, methods) for name, methods in versions.items()}
        searches['p4'] = engine(case)
        samples = {name: [] for name in searches}
        prior = {}
        for repeat in range(110):
            order = list(searches.items())
            if repeat % 2:
                order.reverse()
            for name, search in order:
                start = time.perf_counter()
                rows = await search.search(case['query'], top_k=50, allowed_docs=['frozen-scope'])
                if repeat >= 10:
                    samples[name].append((time.perf_counter() - start) * 1000)
                if name in prior and rows != prior[name]:
                    raise RuntimeError('unstable_frozen_ordering')
                prior[name] = rows
        if not (prior['p1'] == prior['p2'] == prior['p4']):
            raise RuntimeError('default_parity_failure')
        outputs.append(dict(case_id=case['id'], default_parity=True,
            relevant_expected=len(case['relevant_ids']), versions={name:dict(
                ids=[r.doc_id for r in rows], scores=[r.score for r in rows],
                relevant_retrieved=len({r.doc_id for r in rows} & set(case['relevant_ids'])),
                timing=percentiles(samples[name])) for name, rows in prior.items()}))
    from scripts.kb_taxonomy_p4_compare import update_case, checkpoint_code
    old = checkpoint_code()
    taxonomy = []
    for name in ('answer_edit', 'taxonomy_only', 'clean_noop', 'legacy_noop'):
        pairs = {'before': [], 'after': []}
        for index in range(100):
            order = ('before', 'after') if index % 2 == 0 else ('after', 'before')
            for phase in order:
                pairs[phase].append(update_case(name, old if phase == 'before' else None))
        taxonomy.append(dict(case=name, **{phase:dict(timing=percentiles([r['elapsed_ms'] for r in rows]),
            observations={k:v for k,v in rows[0].items() if k != 'elapsed_ms'}) for phase, rows in pairs.items()}))
    def blob(commit, path):
        return subprocess.run(['git', 'show', f'{commit}:{path}'], cwd=ROOT, capture_output=True, check=True).stdout
    p0_p3_kb_unchanged = all(blob(P0, path) == blob('e15761f5eb8d173ad6ebbe0ac9f02aba70503dcf', path)
        for path in ('kb_manager.py', 'new_architecture/knowledge_update.py'))
    summary = dict(input_identity=inputs['identity'], config_identity=digest(config_identity()),
        cases=outputs, taxonomy=taxonomy, p0_p3_kb_unchanged=p0_p3_kb_unchanged,
        timing_scope='synthetic providers and in-memory stores; no service latency')
    write_private(directory / 'offline.json', summary)
    print(json.dumps(dict(phase='offline', input_identity=inputs['identity'], cases=len(outputs),
        default_parity=True, relevant_before=sum(c['versions']['p0']['relevant_retrieved'] for c in outputs),
        relevant_after=sum(c['versions']['p4']['relevant_retrieved'] for c in outputs),
        p0_p3_kb_unchanged=p0_p3_kb_unchanged)), flush=True)


async def model_answer(rag, client, query, rows, limit, required_facts=None, forbidden=None):
    """Tokenize actual unchanged messages before generation; retain no copied prompt."""
    original = rag._completion
    measurements = {}
    async def measured(**kwargs):
        response = await client.post(os.environ['VLLM_URL'].rstrip('/').removesuffix('/v1') + '/tokenize',
            json={'model':kwargs['model'], 'messages':kwargs['messages'], 'add_generation_prompt':True})
        response.raise_for_status()
        count = response.json()['count']
        measurements.update(prompt_tokens=count, reserved_output_tokens=kwargs['max_tokens'])
        if not isinstance(count, int) or count + kwargs['max_tokens'] > limit:
            raise ValueError('diagnostic_context_budget_exceeded')
        result = await original(**kwargs)
        measurements.update(output_tokens=result.usage.completion_tokens,
            server_prompt_tokens=result.usage.prompt_tokens, finish_reason=result.choices[0].finish_reason)
        return result
    rag._completion = measured
    start = time.perf_counter()
    try:
        answer = await asyncio.wait_for(rag.answer(user_question=query, context=rag.generate_context(rows),
            recent_history='', current_summary='', tone='friendly', response_type='normal', enable_history=False,
            category='FAQ'), timeout=SETTINGS.application_request_timeout_seconds)
    except ValueError as exc:
        if str(exc) != 'diagnostic_context_budget_exceeded':
            raise
        return dict(measurements, status='blocked_context_budget'), None
    finally:
        rag._completion = original
    result = dict(measurements, status='generated', elapsed_ms=(time.perf_counter()-start)*1000,
        checks={f['id']:bool(re.search(f['pattern'], answer, re.DOTALL)) for f in (required_facts or [])},
        forbidden_claim=(any(re.search(p, answer) for p in forbidden) if forbidden is not None else None),
        human_fact_review='unavailable' if not required_facts else 'synthetic_lexical_checks_only')
    return result, answer


async def live(directory):
    import httpx
    import psycopg2.extras
    from openai import AsyncOpenAI
    from qdrant_client import QdrantClient
    from scripts.kb_signature import create_signature, compare_signatures, POSTGRES_CHUNK_QUERY
    from new_architecture.app.services.history.database import DatabaseManager
    from utils.concurrency import BoundedBlockingRunner
    from utils.persian_hybrid_search import PersianHybridSearch
    from utils.RagSystem import RAGSystem
    from utils.persian_normalization import normalize_persian_text
    from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query
    from utils.service_errors import ServiceUnavailableError
    from parsivar import Normalizer

    inputs = frozen_inputs()
    signature = create_signature('acceptance-before')
    write_private(directory / 'signature-before.json', signature)
    if not signature['cross_store']['consistent']:
        raise RuntimeError('inconsistent_kb')
    prior_signature = json.loads((P3_DIR / 'signature-before.json').read_text())
    if not compare_signatures(prior_signature, signature)['status']['FULL_MATCH']:
        raise RuntimeError('kb_changed_since_frozen_p3')
    connection = DatabaseManager().get_connection()
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(POSTGRES_CHUNK_QUERY)
            records = cursor.fetchall()
    finally:
        connection.rollback()
        connection.close()
    chunks = {str(r['chunk_id']):dict(text=r['content'], document_name=r['document_title']) for r in records}
    p3_snapshot = json.loads((P3_DIR / 'expanded-inputs.json').read_text())
    copy = dict(p3_snapshot)
    if digest({k:v for k,v in copy.items() if k != 'identity'}) != copy['identity'] or chunks != p3_snapshot['chunks']:
        raise RuntimeError('snapshot_content_changed')
    snapshot = dict(chunks=chunks, source='repeatable-read PostgreSQL capture, checked against P3 frozen content',
        p3_identity=p3_snapshot['identity'], config_identity=digest(config_identity()))
    snapshot['identity'] = digest(snapshot)
    write_private(directory / 'snapshot.json', snapshot)
    point_to_chunk = {r['qdrant_point_id']:r['logical_chunk_id'] for r in signature['qdrant']['records']}
    fixture_path = ROOT / 'benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json'
    fixture = json.loads(fixture_path.read_text())
    csv_source = ROOT / 'General_FAQ.csv'
    with csv_source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream)
        source_info = dict(columns=next(reader), rows=sum(1 for _ in reader), sha256=hashlib.sha256(csv_source.read_bytes()).hexdigest())
    qdrant = QdrantClient(host=os.getenv('QDRANT_HOST'), port=int(os.getenv('QDRANT_PORT', '6333')),
        api_key=os.getenv('QDRANT_API_KEY'), https=os.getenv('QDRANT_HTTPS','false').lower() == 'true', timeout=10)
    blocking = BoundedBlockingRunner(1)
    timeout = httpx.Timeout(connect=SETTINGS.tei_http_connect_timeout_seconds,
        read=SETTINGS.tei_http_read_timeout_seconds, write=SETTINGS.tei_http_write_timeout_seconds,
        pool=SETTINGS.tei_http_pool_timeout_seconds)
    outputs, private_answers, representative = [], [], []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        serving = await capabilities(client)
        if serving != inputs['capabilities']:
            raise RuntimeError('serving_identity_changed')
        write_private(directory / 'serving.json', serving)
        rag = RAGSystem.__new__(RAGSystem)
        rag._closed=False; rag.model_id=serving['VLLM_URL'][0]['id']; rag._vllm_active=rag._vllm_timeout_total=0
        rag.client=AsyncOpenAI(base_url=os.environ['VLLM_URL'], api_key='vllm-token-not-needed', max_retries=0,
            timeout=SETTINGS.vllm_http_read_timeout_seconds)
        search = PersianHybridSearch(qdrant_client=qdrant, chunk_fetcher=lambda titles:{cid:c for cid,c in chunks.items()
            if c['document_name'] in titles}, http_client=client, blocking_runner=blocking)
        runtime_client = None
        try:
            old = checkpoint(P0)
            # Same frozen ranks/content, original/current methods, one request per side/case.
            for case in inputs['cases']:
                comparison = dict(case_id=case['id'], versions={})
                for phase, methods in [('p0',old), ('p4',None)]:
                    replay = engine(case, methods)
                    rows = await replay.search(case['query'], top_k=50, allowed_docs=['frozen-scope'])
                    recorder=RecordingHttp(client); replay._http=recorder
                    replay.tei_rerank_url=os.environ['TEI_RERANK_URL'].rstrip('/')
                    start=time.perf_counter()
                    selected=await asyncio.wait_for(replay.rerank_search_results(case['query'], rows, top_k=10),
                        timeout=SETTINGS.application_request_timeout_seconds)
                    observation=dict(selected_ids=[r.doc_id for r in selected],
                        selected_scores=[r.reranker_score for r in selected], rerank_ms=(time.perf_counter()-start)*1000,
                        calls=recorder.calls, info_calls=recorder.capability_calls,
                        relevant_selected=len({r.doc_id for r in selected} & set(case['relevant_ids'])),
                        context_facts=sum(f['entry'] in {r.doc_id for r in selected} for f in case['required_facts']))
                    if any(r.content != case['chunks'][r.doc_id]['text'] for r in selected):
                        raise RuntimeError('selected_content_changed')
                    if case['required_facts']:
                        observation['generation'], answer=await model_answer(rag, client, case['query'], selected,
                            serving['VLLM_URL'][0]['max_model_len'], case['required_facts'], case['forbidden_patterns'])
                        private_answers.append(dict(case_id=case['id'], phase=phase, answer=answer))
                    comparison['versions'][phase]=observation
                outputs.append(comparison)
            print(json.dumps(dict(phase='live-frozen', cases=len(outputs), snapshot_identity=snapshot['identity'])), flush=True)

            # New connection pool and fresh embedding client: client-cold, not model/GPU-cold.
            runtime_client=httpx.AsyncClient(timeout=timeout,follow_redirects=False)
            from utils.tei_embedding_client import TeiEmbeddingClient
            search.embedding_client=TeiEmbeddingClient(os.environ['TEI_EMBED_URL'],runtime_client)
            recorder=SafeRecordingHttp(runtime_client); search._http=recorder
            query=p3_snapshot['cases'][0]['query']; docs=p3_snapshot['allowed_docs']
            runtime=[]
            for depth, label in [(50,'cold-client'), (50,'warm-client'), (150,'expanded-150'), (300,'expanded-300')]:
                start=time.perf_counter(); call_start=len(recorder.calls); info_start=recorder.capability_calls
                async def operation():
                    rows=await search.search(query, top_k=depth, allowed_docs=docs,
                        bm25_candidate_limit=depth, semantic_candidate_limit=depth)
                    retrieval_ms=(time.perf_counter()-start)*1000
                    rerank_start=time.perf_counter()
                    selected=await search.rerank_search_results(query, rows, top_k=10)
                    return rows, selected, retrieval_ms, (time.perf_counter()-rerank_start)*1000
                rows,selected,retrieval_ms,rerank_ms=await asyncio.wait_for(operation(), SETTINGS.application_request_timeout_seconds)
                calls=recorder.calls[call_start:]
                if sum(c['size'] for c in calls)!=len(rows) or any(c['size']>50 for c in calls):
                    raise RuntimeError('candidate_accounting_failure')
                if any(r.content != chunks[r.doc_id]['text'] for r in [*rows,*selected]):
                    raise RuntimeError('source_content_changed')
                runtime.append(dict(label=label, depth=depth, returned=len(rows), content_preserved=True,
                    retrieval_ms=retrieval_ms, rerank_ms=rerank_ms, total_ms=(time.perf_counter()-start)*1000,
                    calls=calls, info_calls=recorder.capability_calls-info_start, selected_ids=[r.doc_id for r in selected],
                    retained_content_identity=digest([r.content for r in rows])))
            search.embedding_client=TeiEmbeddingClient(os.environ['TEI_EMBED_URL'],client)
            await runtime_client.aclose()
            # Simulate discovery outage only in this diagnostic proxy; never alter the server.
            class InfoUnavailable(RecordingHttp):
                async def get(self, *args, **kwargs):
                    self.capability_calls += 1
                    return httpx.Response(503, request=httpx.Request('GET','https://synthetic.invalid/info'))
            proxy=InfoUnavailable(client); search._http=proxy
            await search.rerank_search_results(query, rows[:1], top_k=1)
            if proxy.capability_calls:raise RuntimeError('cached_limit_not_reused')
            cold=engine(inputs['cases'][0]); cold._http=proxy
            cold.tei_rerank_url=search.tei_rerank_url
            posts=len(proxy.calls)
            try:
                await cold.rerank_search_results(query, rows[:1], top_k=1)
            except ServiceUnavailableError:
                pass
            else:raise RuntimeError('capability_failure_not_translated')
            if len(proxy.calls)!=posts or cold._tei_reranker_active!=0 or cold._rerank_server_limits:
                raise RuntimeError('failed_discovery_resource_leak')
            search._http=client
            normalizer=Normalizer()
            for case in fixture['queries']:
                normalized=canonicalize_retrieval_query(normalize_persian_text(normalizer.normalize(case['query'])))
                relevant=[point_to_chunk[str(cid)] for cid in case['relevant_ids']]
                if any(cid not in chunks for cid in relevant):raise RuntimeError('relevance_id_unmapped')
                branches={}
                original_score,original_dense=search._score_bm25,search._semantic_search
                def score(*args):
                    values,candidates=original_score(*args)
                    branches['sparse']=[dict(id=cid, score=float(value)) for cid,value in candidates]
                    return values,candidates
                async def dense(*args, **kwargs):
                    values=await original_dense(*args, **kwargs)
                    branches['dense']=[dict(id=cid,score=float(value)) for cid,value in values.items()]
                    return values
                search._score_bm25,search._semantic_search=score,dense
                try:
                    start=time.perf_counter()
                    result=await asyncio.wait_for(search.search(normalized, allowed_docs=['General_FAQ']),
                        timeout=SETTINGS.application_request_timeout_seconds)
                    retrieval_ms=(time.perf_counter()-start)*1000
                finally:search._score_bm25,search._semantic_search=original_score,original_dense
                recorder=RecordingHttp(client); search._http=recorder
                selected=await search.rerank_search_results(normalized,result,top_k=10)
                generation,answer=await model_answer(rag,client,normalized,selected,serving['VLLM_URL'][0]['max_model_len'])
                entry=dict(case_id=case['id'], source_query=case['query'], retrieval_query=normalized, relevant_ids=relevant,
                    **branches, retrieved_ids=[r.doc_id for r in result], selected_ids=[r.doc_id for r in selected],
                    relevant_retrieved=len({r.doc_id for r in result}&set(relevant)),
                    relevant_selected=len({r.doc_id for r in selected}&set(relevant)),
                    retrieval_ms=retrieval_ms,calls=recorder.calls,generation=generation)
                representative.append(entry); private_answers.append(dict(case_id=case['id'],phase='banking-fixture',answer=answer))
                search._http=client
            summary=dict(input_identity=inputs['identity'], snapshot_identity=snapshot['identity'],
                config_identity=digest(config_identity()), serving=serving, source_csv=source_info,
                relevance_fixture_identity=digest(fixture), comparisons=outputs, runtime=runtime,
                discovery=dict(cold_info_calls=runtime[0]['info_calls'],warm_info_calls=runtime[1]['info_calls'],
                    cached_outage_info_calls=0,cold_outage='ServiceUnavailableError',cold_outage_posts=0,
                    balanced_resources=True,simulation=True), representative=representative,
                model_quality_limit='fixture has relevance labels only; no independent fact labels or human review',
                release_status='BLOCKED')
            write_private(directory/'live.json',summary)
            write_private(directory/'answers.json',private_answers)
        finally:
            if runtime_client is not None:
                await runtime_client.aclose()
            await rag.client.close(); await search.aclose(); await blocking.aclose(); qdrant.close()
    after=create_signature('acceptance-after')
    write_private(directory/'signature-after.json',after)
    match=compare_signatures(signature,after)['status']['FULL_MATCH']
    if not match:raise RuntimeError('kb_changed_during_acceptance')
    print(json.dumps(dict(phase='live-complete', snapshot_identity=snapshot['identity'],signature_full_match=match,
        chunks=signature['postgres']['record_count'],points=signature['qdrant']['point_count'],
        runtime=[dict(label=r['label'],returned=r['returned'],requests=[c['size'] for c in r['calls']],
            info_calls=r['info_calls'],total_ms=r['total_ms']) for r in runtime],
        banking_fixture_cases=len(representative), relevant_expected=sum(len(c['relevant_ids']) for c in representative),
        relevant_retrieved=sum(c['relevant_retrieved'] for c in representative),
        relevant_selected=sum(c['relevant_selected'] for c in representative))),flush=True)


async def followup(directory):
    """Investigate fixture misses; compare partitions and source-derived referrals."""
    import httpx
    from openai import AsyncOpenAI
    from qdrant_client import QdrantClient
    from scripts.kb_signature import create_signature,compare_signatures
    from scripts.reranker_p3_compare import comparability
    from utils.faq_content import parse_faq_content
    from utils.persian_hybrid_search import PersianHybridSearch
    from utils.concurrency import BoundedBlockingRunner
    from utils.RagSystem import RAGSystem
    from utils.persian_normalization import normalize_persian_text
    from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query
    from parsivar import Normalizer
    inputs=frozen_inputs(); old=checkpoint(P0)
    prior=json.loads((directory/'live.json').read_text())
    snapshot=json.loads((directory/'snapshot.json').read_text())
    copy=dict(snapshot); identity=copy.pop('identity')
    if digest(copy)!=identity or prior['config_identity']!=digest(config_identity()):
        raise RuntimeError('evaluation_identity_changed')
    chunks=snapshot['chunks']; label_investigation=[]
    for case in prior['representative']:
        fixture=dict(id=case['case_id'],query=case['retrieval_query'],sparse=case['sparse'],dense=case['dense'],
            chunks=chunks,relevant_ids=case['relevant_ids'])
        rows_before=await engine(fixture,old).search(fixture['query'],top_k=50,allowed_docs=['General_FAQ'])
        rows_after=await engine(fixture).search(fixture['query'],top_k=50,allowed_docs=['General_FAQ'])
        if [r.doc_id for r in rows_after]!=case['retrieved_ids']:
            raise RuntimeError('banking_fixture_replay_changed')
        words=set(re.findall(r'\w+',case['retrieval_query']))
        label_investigation.append(dict(case_id=case['case_id'],expected_ids=case['relevant_ids'],
            before_inclusion=len({r.doc_id for r in rows_before}&set(case['relevant_ids'])),
            after_inclusion=case['relevant_retrieved'],
            expected_title_token_overlap={cid:len(words & set(re.findall(r'\w+',parse_faq_content(chunks[cid]['text']).question)))
                for cid in case['relevant_ids']},
            status='human_review_current_snapshot_labels_required'))
    before=create_signature('acceptance-followup-before')
    if not compare_signatures(json.loads((directory/'signature-after.json').read_text()),before)['status']['FULL_MATCH']:
        raise RuntimeError('kb_changed_before_followup')
    write_private(directory/'followup-signature-before.json',before)
    blocking=BoundedBlockingRunner(1)
    qdrant=QdrantClient(host=os.getenv('QDRANT_HOST'),port=int(os.getenv('QDRANT_PORT','6333')),
        api_key=os.getenv('QDRANT_API_KEY'),https=os.getenv('QDRANT_HTTPS','false').lower()=='true',timeout=10)
    answers=[]; referrals=[]
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
        serving=await capabilities(client)
        if serving!=prior['serving']:raise RuntimeError('serving_identity_changed')
        partitions=await comparability(inputs,client)
        rag=RAGSystem.__new__(RAGSystem)
        rag._closed=False;rag.model_id=serving['VLLM_URL'][0]['id'];rag._vllm_active=rag._vllm_timeout_total=0
        rag.client=AsyncOpenAI(base_url=os.environ['VLLM_URL'],api_key='vllm-token-not-needed',max_retries=0,
            timeout=SETTINGS.vllm_http_read_timeout_seconds)
        search=PersianHybridSearch(qdrant_client=qdrant,chunk_fetcher=lambda titles:{cid:c for cid,c in chunks.items()
            if c['document_name'] in titles},http_client=client,blocking_runner=blocking)
        try:
            for cid in ('3','57'):
                source=parse_faq_content(chunks[cid]['text'])
                if not source.is_qa or not re.search(r'پشتیبانی|تماس|مراجعه',source.answer):
                    raise RuntimeError('source_referral_contract_changed')
                equivalent=[i for i,row in chunks.items() if parse_faq_content(row['text']).answer==source.answer]
                # This suffix asks for existing source conditions; it adds no facts.
                query=canonicalize_retrieval_query(normalize_persian_text(Normalizer().normalize(
                    source.question+' لطفاً شرایط و مسیر پیگیری را توضیح بده.')))
                rows=await search.search(query,allowed_docs=['General_FAQ'])
                selected=await search.rerank_search_results(query,rows,top_k=10)
                result,answer=await model_answer(rag,client,query,selected,serving['VLLM_URL'][0]['max_model_len'])
                referrals.append(dict(source_id=cid,source_answer_identity=digest(source.answer),
                    expected='source-derived referral instruction; preserve all source conditions',
                    source_has_conditions=bool(re.search(r'اگر|در صورت',source.answer)),equivalent_ids=equivalent,
                    selected_equivalent_ids=list(set(equivalent)&{r.doc_id for r in selected}),
                    generation=result,referral_word_present=bool(answer and re.search(r'پشتیبانی|تماس|مراجعه',answer)),
                    condition_semantics='unassessed_requires_human_review'))
                answers.append(dict(source_id=cid,answer=answer))
        finally:
            await rag.client.close();await search.aclose();await blocking.aclose();qdrant.close()
    after=create_signature('acceptance-followup-after')
    write_private(directory/'followup-signature-after.json',after)
    match=compare_signatures(before,after)['status']['FULL_MATCH']
    if not match:raise RuntimeError('kb_changed_during_followup')
    summary=dict(snapshot_identity=identity,label_investigation=label_investigation,
        partitions=partitions,referrals=referrals,signature_full_match=match,
        earlier_unlabeled_forbidden_flags='unassessed: an empty forbidden-pattern list is not evidence of absent unsupported claims',
        release_status='BLOCKED')
    write_private(directory/'followup.json',summary);write_private(directory/'referral-answers.json',answers)
    print(json.dumps(dict(phase='followup',signature_full_match=match,
        baseline_fixture_inclusion=sum(c['before_inclusion'] for c in label_investigation),
        final_fixture_inclusion=sum(c['after_inclusion'] for c in label_investigation),
        partitions=[dict(case_id=c['case_id'],path=c['path'],max_drift=max(o['max_score_drift'] for o in c['observations']),
            selected_set_changes=sum(o['selected_set_changed'] for o in c['observations'])) for c in partitions],
        referrals=[dict(source_id=c['source_id'],selected_equivalent_ids=c['selected_equivalent_ids'],
            referral_word_present=c['referral_word_present']) for c in referrals])),flush=True)


async def budgets(directory):
    """Tokenize actual expanded selected contexts without another generation call."""
    import httpx
    from scripts.kb_signature import create_signature,compare_signatures
    from utils.persian_hybrid_search import SearchResult
    from utils.RagSystem import RAGSystem
    frozen_inputs()
    previous=json.loads((directory/'live.json').read_text())
    snapshot=json.loads((directory/'snapshot.json').read_text())
    check=dict(snapshot);identity=check.pop('identity')
    if digest(check)!=identity:raise RuntimeError('snapshot_identity_changed')
    before=create_signature('acceptance-budgets-before')
    if not compare_signatures(json.loads((directory/'signature-after.json').read_text()),before)['status']['FULL_MATCH']:
        raise RuntimeError('kb_changed_before_budget_check')
    write_private(directory/'budget-signature-before.json',before)
    p3_snapshot=json.loads((P3_DIR/'expanded-inputs.json').read_text())
    query=p3_snapshot['cases'][0]['query']
    class TokenizationOnly(Exception):pass
    observations=[]
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
        serving=await capabilities(client)
        if serving!=previous['serving']:raise RuntimeError('serving_identity_changed')
        rag=RAGSystem.__new__(RAGSystem);rag._closed=False;rag.model_id=serving['VLLM_URL'][0]['id']
        async def tokenize(**kwargs):
            response=await client.post(os.environ['VLLM_URL'].rstrip('/').removesuffix('/v1')+'/tokenize',
                json={'model':kwargs['model'],'messages':kwargs['messages'],'add_generation_prompt':True})
            response.raise_for_status();count=response.json()['count']
            if not isinstance(count,int) or count+kwargs['max_tokens']>serving['VLLM_URL'][0]['max_model_len']:
                raise RuntimeError('expanded_selected_context_budget_exceeded')
            observations.append(dict(depth=case['depth'],selected_count=len(rows),prompt_tokens=count,
                reserved_output_tokens=kwargs['max_tokens'],generation_calls=0,source_content_preserved=True))
            raise TokenizationOnly()
        rag._completion=tokenize
        for case in previous['runtime'][2:]:
            rows=[SearchResult(cid,snapshot['chunks'][cid]['text'],.1,1,.5) for cid in case['selected_ids']]
            try:
                await rag.answer(user_question=query,context=rag.generate_context(rows),recent_history='',current_summary='',
                    tone='friendly',response_type='normal',enable_history=False,category='FAQ')
            except TokenizationOnly:
                pass
    after=create_signature('acceptance-budgets-after');write_private(directory/'budget-signature-after.json',after)
    match=compare_signatures(before,after)['status']['FULL_MATCH']
    if not match:raise RuntimeError('kb_changed_during_budget_check')
    summary=dict(snapshot_identity=identity,observations=observations,signature_full_match=match,
        quality='expanded contexts tokenized only; no additional generated-answer quality claim')
    write_private(directory/'budgets.json',summary);print(json.dumps(summary),flush=True)


async def finalize(directory):
    """Record serving/configuration identities after all bounded live checks."""
    import httpx
    from scripts.kb_signature import create_signature,compare_signatures
    frozen_inputs()
    previous=json.loads((directory/'live.json').read_text())
    async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
        serving=await capabilities(client)
    signature=create_signature('acceptance-final')
    match=compare_signatures(json.loads((directory/'signature-before.json').read_text()),signature)['status']['FULL_MATCH']
    if serving!=previous['serving'] or digest(config_identity())!=previous['config_identity'] or not match:
        raise RuntimeError('final_evaluation_identity_changed')
    summary=dict(serving=serving,config_identity=previous['config_identity'],signature_full_match=match,
        snapshot_identity=previous['snapshot_identity'],postgres_signature=signature['postgres']['aggregate_sha256'],
        chunks=signature['postgres']['record_count'],points=signature['qdrant']['point_count'],release_status='BLOCKED')
    write_private(directory/'final-identity.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='serving'}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('offline','live','followup','budgets','finalize'))
    parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--confirmed-staging',action='store_true')
    args=parser.parse_args(); directory=args.directory.resolve()
    if directory.is_relative_to(ROOT):raise RuntimeError('private_directory_inside_repository')
    if not directory.exists():directory.mkdir(mode=0o700)
    if directory.stat().st_uid!=os.getuid() or directory.stat().st_mode&0o077:
        raise RuntimeError('private_directory_permissions')
    if args.phase!='offline' and not args.confirmed_staging:raise RuntimeError('staging_confirmation_required')
    asyncio.run({'offline':offline,'live':live,'followup':followup,'budgets':budgets,'finalize':finalize}[args.phase](directory))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps(dict(error_type=type(exc).__name__)),file=sys.stderr)
        sys.exit(2)
