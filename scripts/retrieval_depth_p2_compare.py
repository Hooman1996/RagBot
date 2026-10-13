#!/usr/bin/env python3
"""Read-only P2 comparison on frozen inputs. No expanded live reranking.

Private inputs/answers require an external 0700 directory. Only content-safe
measurements are printed. Live default checks require staging confirmation.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import MethodType
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.rrf_p1_compare import (capabilities, config_identity, digest,
    percentiles, write_private)
from tests.retrieval_depth_fixtures import depth_search, expanded_case
from utils.performance_config import PERFORMANCE_SETTINGS

CHECKPOINT = 'c8338050aa548cfc3f48f0927d4bcd270c2e608f'


def checked_inputs(directory):
    inputs = json.loads((directory / 'inputs.json').read_text())
    identity = inputs.pop('identity')
    if digest(inputs) != identity:
        raise RuntimeError('frozen_input_mismatch')
    current = config_identity()
    performance = dict(current['performance'])
    if performance.pop('rag_bm25_candidate_limit') != 50 or performance != inputs['config']['performance']:
        raise RuntimeError('default_settings_changed')
    # P2 intentionally edits the performance loader and retrieval forwarding.
    # Prompt/model config, aliases and reranker text parser must stay frozen.
    for name in ('new_architecture/app/config.py', 'config/retrieval_query_aliases.json', 'utils/rag_utils.py'):
        if current['artifacts'][name] != inputs['config']['artifacts'][name]:
            raise RuntimeError('non_retrieval_configuration_changed')
    inputs['identity'] = identity
    return inputs, current


async def default_after(directory, live):
    import httpx
    inputs, current_config = checked_inputs(directory)
    before = json.loads((directory / 'before.json').read_text())
    outputs, answers = [], []
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http:
        if live and await capabilities(http) != inputs['capabilities']:
            raise RuntimeError('serving_configuration_changed')
        rag = None
        if live:
            from openai import AsyncOpenAI
            from utils.RagSystem import RAGSystem
            rag = RAGSystem.__new__(RAGSystem)
            rag._closed = False
            rag.model_id = '/app/model'
            rag._vllm_active = rag._vllm_timeout_total = 0
            rag.client = AsyncOpenAI(base_url=os.environ['VLLM_URL'], api_key='vllm-token-not-needed', max_retries=0, timeout=50)
        try:
            for case, old in zip(inputs['cases'], before['cases'], strict=True):
                search = depth_search(case)
                rows = await search.search(case['query'], top_k=case['top_k'], allowed_docs=['frozen-scope'])
                ids = [r.doc_id for r in rows]
                scores = [r.score for r in rows]
                ranks = [r.original_rrf_rank for r in rows]
                parity = (ids == old['retrieved_ids'] and scores == old['fused_scores'] and ranks == old['rrf_ranks']
                    and all(r.content == case['chunks'][r.doc_id]['text'] for r in rows))
                if not parity:
                    raise RuntimeError('default_first_stage_regression')
                out = dict(case_id=case['id'], retrieved_ids=ids, fused_scores=scores, rrf_ranks=ranks,
                    default_parity=parity, lexical_count=min(50, sum(r['score'] > 0 for r in case['sparse'])),
                    dense_count=min(50, len(case['dense'])), returned_count=len(rows),
                    relevant_retrieved=len(set(ids) & set(case['relevant_ids'])), reranker=[])
                if live:
                    limit = inputs['capabilities']['TEI_RERANK_URL']['max_client_batch_size']
                    if len(rows) > limit:
                        raise RuntimeError('unsafe_reranker_request_size')
                    search._http = http
                    search.tei_rerank_url = os.environ['TEI_RERANK_URL'].rstrip('/')
                    for repeat in range(2):
                        start = time.perf_counter()
                        selected = await search.rerank_search_results(case['query'], rows,
                            top_k=PERFORMANCE_SETTINGS.rag_context_rerank_top_k)
                        out['reranker'].append(dict(elapsed_ms=(time.perf_counter()-start)*1000,
                            request_sizes=[len(rows)], selected_ids=[r.doc_id for r in selected],
                            scores=[r.reranker_score for r in selected]))
                        if repeat == 0:
                            context = selected
                    selected_ids = {r.doc_id for r in context}
                    out['relevant_selected'] = len(selected_ids & set(case['relevant_ids']))
                    out['context_required_fact_count'] = sum(f['entry'] in selected_ids for f in case['required_facts'])
                    if case['required_facts']:
                        start = time.perf_counter()
                        answer = await rag.answer(user_question=case['query'], context=rag.generate_context(context),
                            recent_history='', current_summary='', tone='friendly', response_type='normal',
                            enable_history=False, category='FAQ')
                        out['generation_ms'] = (time.perf_counter()-start)*1000
                        out['answer_fact_checks'] = {f['id']: bool(re.search(f['pattern'], answer, re.DOTALL))
                            for f in case['required_facts']}
                        out['answer_forbidden_claim_detected'] = any(re.search(p, answer) for p in case['forbidden_patterns'])
                        answers.append(dict(case_id=case['id'], answer=answer))
                outputs.append(out)
        finally:
            if rag is not None:
                await rag.client.close()
    summary = dict(phase='after', input_identity=inputs['identity'], config_identity=digest(current_config),
        config=current_config, live=live, cases=outputs)
    write_private(directory / 'after.json', summary)
    if answers:
        write_private(directory / 'after-answers.json', answers)
    print(json.dumps(dict(phase='after', input_identity=inputs['identity'], config_identity=digest(current_config),
        case_count=len(outputs), default_parity=all(c['default_parity'] for c in outputs),
        relevant_retrieved=sum(c['relevant_retrieved'] for c in outputs),
        reranker_calls=sum(len(c['reranker']) for c in outputs), generation_calls=len(answers))))


def checkpoint_methods():
    import utils.persian_hybrid_search as module
    source = subprocess.run(['git', 'show', f'{CHECKPOINT}:utils/persian_hybrid_search.py'],
        cwd=ROOT, check=True, capture_output=True, text=True).stdout
    cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'PersianHybridSearch')
    # Extract only methods: do not import checkpoint side effects or alter globals.
    methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in ('search', '_score_bm25')]
    for method in methods:
        method.decorator_list = []
    namespace = dict(module.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), '<P1-methods>', 'exec'), namespace)
    return namespace


async def timing(directory):
    inputs, config = checked_inputs(directory)
    old = checkpoint_methods()
    pairs = []
    for case in inputs['cases']:
        baseline, current = depth_search(case), depth_search(case)
        baseline.search = MethodType(old['search'], baseline)
        baseline._score_bm25 = old['_score_bm25']
        samples = {'before': [], 'after': []}
        for iteration in range(210):
            ordered = [('before', baseline), ('after', current)]
            if iteration % 2:
                ordered.reverse()
            rows = {}
            for label, search in ordered:
                start = time.perf_counter()
                rows[label] = await search.search(case['query'], top_k=50, allowed_docs=['frozen-scope'])
                elapsed = (time.perf_counter()-start)*1000
                if iteration >= 10:
                    samples[label].append(elapsed)
            if rows['before'] != rows['after']:
                raise RuntimeError('paired_default_regression')
        pairs.append(dict(case_id=case['id'], **{key: percentiles(value) for key, value in samples.items()}))
    summary = dict(phase='timing', input_identity=inputs['identity'], config_identity=digest(config),
        checkpoint=CHECKPOINT, scope='offline score-selection/fusion; frozen dense provider; no service calls', cases=pairs)
    write_private(directory / 'timing.json', summary)
    print(json.dumps(summary))


async def depths(directory):
    case = expanded_case()
    frozen = dict(case=case, identity=digest(case), config_identity=digest(config_identity()))
    write_private(directory / 'depth-inputs.json', frozen)
    outputs = []
    # First four experiments change only one depth from the baseline. Remaining
    # configurations establish joint correctness, not causal performance effects.
    for lexical, dense, final in [(50,50,50), (150,50,50), (50,150,50), (50,50,150),
        (150,50,150), (100,100,150), (150,150,150), (300,300,300)]:
        search = depth_search(case)
        samples, lexical_times, dense_times = [], [], []
        original_score, original_dense = search._score_bm25, search._semantic_search

        def score(*args):
            start = time.perf_counter()
            result = original_score(*args)
            lexical_times.append((time.perf_counter()-start)*1000)
            return result

        async def dense_provider(*args, **kwargs):
            start = time.perf_counter()
            result = await original_dense(*args, **kwargs)
            dense_times.append((time.perf_counter()-start)*1000)
            return result

        search._score_bm25, search._semantic_search = score, dense_provider
        prior = None
        for iteration in range(210):
            start = time.perf_counter()
            rows = await search.search(case['query'], top_k=final, allowed_docs=['synthetic-FAQ'],
                bm25_candidate_limit=lexical, semantic_candidate_limit=dense)
            if iteration >= 10:
                samples.append((time.perf_counter()-start)*1000)
            if prior is not None and rows != prior:
                raise RuntimeError('unstable_depth_ordering')
            prior = rows
        sparse_ids = {r['id'] for r in case['sparse'][:lexical]}
        dense_ids = {r['id'] for r in case['dense'][:dense]}
        ids = [r.doc_id for r in rows]
        if len(ids) != min(final, len(sparse_ids | dense_ids)) or len(ids) != len(set(ids)):
            raise RuntimeError('depth_count_or_deduplication_failure')
        outputs.append(dict(depths=[lexical,dense,final], lexical_count=len(sparse_ids), dense_count=len(dense_ids),
            union_count=len(sparse_ids | dense_ids), returned_count=len(ids), returned_ids=ids,
            reference_entries_retrieved=sorted(set(ids) & set(case['relevant_ids'])),
            reference_fact_count=len(set(ids) & set(case['relevant_ids'])),
            retrieval=percentiles(samples), lexical_selection=percentiles(lexical_times[10:]),
            frozen_dense_provider=percentiles(dense_times[10:]),
            fusion_and_overhead=percentiles([a-b-c for a,b,c in zip(samples,lexical_times[10:],dense_times[10:])]),
            reranker_calls=0, generation_calls=0))
    summary = dict(phase='depths', input_identity=frozen['identity'], config_identity=frozen['config_identity'],
        scope='synthetic frozen score providers; no live services or answer-quality measurement', cases=outputs)
    write_private(directory / 'depths.json', summary)
    print(json.dumps(dict(phase='depths', input_identity=frozen['identity'],
        cases=[{k:v for k,v in row.items() if k != 'returned_ids'} for row in outputs])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('after', 'timing', 'depths'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--confirmed-staging', action='store_true')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(ROOT) or not directory.is_dir() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise RuntimeError('private_directory_permissions')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        asyncio.run({'after': lambda: default_after(directory, args.confirmed_staging),
            'timing': lambda: timing(directory), 'depths': lambda: depths(directory)}[args.phase]())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error_type': type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
