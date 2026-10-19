#!/usr/bin/env python3
"""P1-only frozen fusion comparison. No chat/KB writes or runtime feature code.

Private inputs/answers stay in a user-owned 0700 directory outside the repo;
stdout is an allowlisted summary. Live calls require explicit staging confirmation.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
from dataclasses import asdict
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
from types import MethodType
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

# Match the confirmed project loader even if invoked from another worktree/CWD.
load_dotenv(Path('/root/projects/faq/.env'), override=False)
logging.disable(logging.CRITICAL)

import httpx
from tests.rrf_fixtures import controlled_cases, replay_search
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.persian_normalization import normalize_persian_text
from utils.rag_utils import parse_faq_relevance_fields
from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)


def config_identity():
    return {
        'performance': asdict(PERFORMANCE_SETTINGS),
        'artifacts': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            for name in ('new_architecture/app/config.py', 'config/retrieval_query_aliases.json',
                         'utils/performance_config.py', 'utils/rag_utils.py', 'utils/RagSystem.py')},
    }


async def capabilities(client):
    result = {}
    for key, suffix in [('TEI_EMBED_URL', '/info'), ('TEI_RERANK_URL', '/info'), ('VLLM_URL', '/models')]:
        response = await client.get(os.environ[key].rstrip('/')+suffix)
        response.raise_for_status()
        body = response.json()
        if key == 'VLLM_URL':
            result[key] = [{k: row.get(k) for k in ('id', 'max_model_len')} for row in body['data']]
        else:
            result[key] = {k: body.get(k) for k in ('version', 'model_id', 'max_client_batch_size',
                'max_input_length', 'auto_truncate', 'max_batch_tokens', 'max_batch_requests')}
    return result


async def freeze(directory, live):
    inputs = {'schema': 1, 'config': config_identity(), 'cases': controlled_cases(), 'live': live}
    if live:
        import psycopg2.extras
        from scripts.kb_signature import create_signature, POSTGRES_CHUNK_QUERY
        from new_architecture.app.services.history.database import DatabaseManager
        from utils.concurrency import BoundedBlockingRunner
        from utils.persian_hybrid_search import PersianHybridSearch, PersianTextProcessor
        from qdrant_client import QdrantClient
        signature = create_signature('p1-before-freeze')
        if not signature['cross_store']['consistent']:
            raise RuntimeError('inconsistent_kb')
        write_private(directory/'signature-before.json', signature)
        inputs['kb_fingerprint'] = {k: signature['postgres'][k] for k in ('aggregate_sha256', 'record_count')}
        database = DatabaseManager()
        conn = database.get_connection()
        try:
            conn.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(POSTGRES_CHUNK_QUERY)
                rows = cursor.fetchall()
        finally:
            conn.rollback()
            conn.close()
        chunks = {str(r['chunk_id']): {'text': r['content'], 'document_name': r['document_title']} for r in rows}
        docs = sorted({c['document_name'] for c in chunks.values()})
        # Selection is by stable ID/length, not user feedback or query outcomes.
        eligible = []
        for row in rows:
            fields = parse_faq_relevance_fields(row['content'])
            if fields['question'] and 'FAQ' in row['document_title'] and len(row['content']) < 600:
                eligible.append((str(row['chunk_id']), fields['question']))
        if len(eligible) < 2:
            raise RuntimeError('insufficient_short_faqs')
        blocking = BoundedBlockingRunner(1)
        qdrant = QdrantClient(host=os.getenv('QDRANT_HOST'), port=int(os.getenv('QDRANT_PORT', '6333')),
            api_key=os.getenv('QDRANT_API_KEY'), https=os.getenv('QDRANT_HTTPS', 'false').lower()=='true', timeout=10)
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as http:
            inputs['capabilities'] = await capabilities(http)
            search = PersianHybridSearch(qdrant_client=qdrant, chunk_fetcher=lambda titles: {
                cid: c for cid, c in chunks.items() if c['document_name'] in titles},
                http_client=http, blocking_runner=blocking)
            processor = PersianTextProcessor(use_stemming=False)
            original_score = search._score_bm25
            original_dense = search._semantic_search
            try:
                for ordinal, (expected_id, question) in enumerate(eligible[:2], 1):
                    capture = {}

                    def sparse_capture(*args):
                        scores, candidates = original_score(*args)
                        capture['sparse'] = [{'id': cid, 'score': float(score)} for cid, score in candidates]
                        return scores, candidates

                    async def dense_capture(*args, **kwargs):
                        scores = await original_dense(*args, **kwargs)
                        capture['dense'] = [{'id': cid, 'score': float(score)} for cid, score in scores.items()]
                        return scores

                    search._score_bm25 = sparse_capture
                    search._semantic_search = dense_capture
                    query = canonicalize_retrieval_query(normalize_persian_text(processor.normalize(question)))
                    started = time.perf_counter()
                    await search.search(query, top_k=PERFORMANCE_SETTINGS.rag_retrieval_top_k, allowed_docs=docs)
                    capture['capture_ms'] = (time.perf_counter()-started)*1000
                    ids = {r['id'] for r in capture['sparse']+capture['dense']}
                    inputs['cases'].append(dict(capture, id=f'kb-{ordinal}', query=query, top_k=50,
                        chunks={cid: chunks[cid] for cid in ids}, relevant_ids=[expected_id],
                        provenance='short-existing-FAQ-title-query', required_facts=[]))
                # Ensure source content matches both signature observations.
                second = create_signature('p1-after-freeze')
                from scripts.kb_signature import compare_signatures
                if not compare_signatures(signature, second)['status']['FULL_MATCH']:
                    raise RuntimeError('kb_changed_during_freeze')
                write_private(directory/'signature-after-freeze.json', second)
            finally:
                await search.aclose()
                await blocking.aclose()
                qdrant.close()
    inputs['identity'] = digest(inputs)
    write_private(directory/'inputs.json', inputs)
    print(json.dumps({'phase': 'freeze', 'input_identity': inputs['identity'], 'case_count': len(inputs['cases']),
        'config_identity': digest(inputs['config']), 'capabilities': inputs.get('capabilities'),
        'kb': inputs.get('kb_fingerprint'), 'directory_mode': oct(directory.stat().st_mode & 0o777)}, sort_keys=True))


def percentiles(values):
    ordered = sorted(values)
    return {'n': len(values), 'median_ms': statistics.median(values), 'p95_ms': ordered[int(.95*(len(ordered)-1))]}


async def run(directory, phase, live):
    inputs = json.loads((directory/'inputs.json').read_text())
    identity = inputs.pop('identity')
    if digest(inputs) != identity or config_identity() != inputs['config']:
        raise RuntimeError('frozen_input_or_configuration_mismatch')
    inputs['identity'] = identity
    summaries = []
    private_answers = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http:
        if live and await capabilities(http) != inputs['capabilities']:
            raise RuntimeError('serving_configuration_changed')
        rag = None
        if live:
            from utils.RagSystem import RAGSystem
            from openai import AsyncOpenAI
            rag = RAGSystem.__new__(RAGSystem)
            rag._closed = False
            rag.model_id = '/app/model'
            rag._vllm_active = rag._vllm_timeout_total = 0
            rag.client = AsyncOpenAI(base_url=os.environ['VLLM_URL'], api_key='vllm-token-not-needed',
                max_retries=0, timeout=50)
        try:
            for case in inputs['cases']:
                search = replay_search(case)
                times = []
                rows = None
                for _ in range(200):
                    started = time.perf_counter()
                    current = await search.search(case['query'], top_k=case['top_k'], allowed_docs=['frozen-scope'])
                    times.append((time.perf_counter()-started)*1000)
                    if rows is not None and rows != current:
                        raise RuntimeError('unstable_frozen_fusion')
                    rows = current
                ids = [r.doc_id for r in rows]
                reference = case['relevant_ids']
                out = {'case_id': case['id'], 'retrieved_ids': ids,
                    'fused_scores': [r.score for r in rows], 'rrf_ranks': [r.original_rrf_rank for r in rows],
                    'relevant_retrieved': len(set(ids)&set(reference)), 'relevant_expected': len(reference),
                    'fusion_replay': percentiles(times), 'stable_repeats': 200, 'reranker': []}
                if live:
                    search._http = http
                    search.tei_rerank_url = os.environ['TEI_RERANK_URL'].rstrip('/')
                    selected = None
                    for repeat in range(2):
                        started = time.perf_counter()
                        selected_rows = await search.rerank_search_results(case['query'], rows,
                            top_k=PERFORMANCE_SETTINGS.rag_context_rerank_top_k)
                        out['reranker'].append({'elapsed_ms': (time.perf_counter()-started)*1000,
                            'request_sizes': [len(rows)], 'selected_ids': [r.doc_id for r in selected_rows],
                            'scores': [r.reranker_score for r in selected_rows]})
                        if repeat == 0: selected = selected_rows
                    selected_ids = {r.doc_id for r in selected}
                    out['relevant_selected'] = len(selected_ids & set(reference))
                    out['context_required_fact_count'] = sum(f['entry'] in selected_ids for f in case['required_facts'])
                    if case['required_facts']:
                        # Actual model call with unchanged production FAQ prompts/settings.
                        started = time.perf_counter()
                        answer = await rag.answer(user_question=case['query'], context=rag.generate_context(selected),
                            recent_history='', current_summary='', tone='friendly', response_type='normal',
                            enable_history=False, category='FAQ')
                        out['generation_ms'] = (time.perf_counter()-started)*1000
                        out['answer_fact_checks'] = {f['id']: bool(re.search(f['pattern'], answer, re.DOTALL))
                            for f in case['required_facts']}
                        out['answer_forbidden_claim_detected'] = any(re.search(p, answer) for p in case['forbidden_patterns'])
                        private_answers.append({'case_id': case['id'], 'answer': answer})
                summaries.append(out)
        finally:
            if rag is not None: await rag.client.close()
    summary = {'phase': phase, 'input_identity': identity, 'config_identity': digest(inputs['config']),
        'search_source_sha256': hashlib.sha256((ROOT/'utils/persian_hybrid_search.py').read_bytes()).hexdigest(),
        'cases': summaries, 'live': live}
    write_private(directory/f'{phase}.json', summary)
    if private_answers: write_private(directory/f'{phase}-answers.json', private_answers)
    print(json.dumps({'phase': phase, 'input_identity': identity, 'case_count': len(summaries),
        'relevant_retrieved': sum(c['relevant_retrieved'] for c in summaries),
        'relevant_expected': sum(c['relevant_expected'] for c in summaries),
        'reranker_calls': sum(len(c['reranker']) for c in summaries),
        'generation_calls': len(private_answers), 'result_sha256': digest(summary)}, sort_keys=True))


async def paired_timing(directory):
    """Alternate checkpoint/current search; no network or production mutation."""
    import utils.persian_hybrid_search as module
    inputs = json.loads((directory/'inputs.json').read_text())
    identity = inputs.pop('identity')
    if digest(inputs) != identity or config_identity() != inputs['config']:
        raise RuntimeError('frozen_input_or_configuration_mismatch')
    checkpoint = subprocess.run(['git', 'show',
        '0663fa07acaf2ba9433789e8655643b9e7d6b163:utils/persian_hybrid_search.py'],
        cwd=ROOT, check=True, capture_output=True, text=True).stdout
    tree = ast.parse(checkpoint)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=='PersianHybridSearch')
    method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name=='search')
    namespace = dict(module.__dict__)
    fragment = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), method], type_ignores=[])
    exec(compile(ast.fix_missing_locations(fragment), '<checkpoint-search>', 'exec'), namespace)
    result = []
    for case in inputs['cases']:
        old = replay_search(case)
        old.search = MethodType(namespace['search'], old)
        new = replay_search(case)
        measured = {'before': [], 'after': []}
        for iteration in range(1050):
            order = [('before', old), ('after', new)]
            if iteration % 2: order.reverse()
            for label, search in order:
                started = time.perf_counter()
                await search.search(case['query'], top_k=case['top_k'], allowed_docs=['frozen-scope'])
                if iteration >= 50: measured[label].append((time.perf_counter()-started)*1000)
        result.append({'case_id': case['id'], **{label: percentiles(values) for label, values in measured.items()}})
    summary = {'phase': 'paired-timing', 'input_identity': identity,
        'warmup_per_case_per_version': 50, 'cases': result, 'network_calls': 0}
    write_private(directory/'paired-timing.json', summary)
    print(json.dumps(summary, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['freeze', 'before', 'after', 'timing'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--confirmed-staging', action='store_true')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(ROOT): raise RuntimeError('private_artifacts_must_be_outside_repository')
    if not directory.exists(): directory.mkdir(mode=0o700)
    if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise RuntimeError('private_directory_permissions')
    if args.phase == 'timing':
        operation = paired_timing(directory)
    elif args.phase == 'freeze':
        operation = freeze(directory, args.confirmed_staging)
    else:
        operation = run(directory, args.phase, args.confirmed_staging)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        asyncio.run(operation)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error_type': type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
