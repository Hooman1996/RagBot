#!/usr/bin/env python3
"""Synthetic P4 write-path measurements plus frozen P3 retrieval replay.

All repositories/vectors are in memory. No KB writes or persisted conversations.
Live default scoring checks require established staging confirmation.
"""
from __future__ import annotations
import argparse
import ast
import asyncio
import json
import logging
from pathlib import Path
import sys
import time
import subprocess
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.rrf_p1_compare import config_identity,digest,percentiles,write_private
from tests.test_kb_manager_chunk_create import ChunkCreateTests
from tests.test_knowledge_update_consistency import (SharedPostgresState,FakeRepository,FakeVectorStore,
    CacheInvalidator,fake_vector)
from new_architecture.knowledge_update import KnowledgeUpdateCoordinator,VectorPoint
from tests.retrieval_depth_fixtures import depth_search
from utils.rag_utils import parse_faq_relevance_fields
import kb_manager

logging.disable(logging.CRITICAL)
QUESTION='Synthetic review duration and cutoff?'
ANSWER='Fictional review takes two working days. Requests after 14:00 begin next working day.'
FOOTER='question category: synthetic. sub_category: review'
CONTENT=f'question: {QUESTION}\nanswer: {ANSWER}\n{FOOTER}'


def update_case(name, checkpoint=None):
    state=SharedPostgresState()
    state.content=CONTENT
    state.vector=fake_vector(kb_manager.normalizer.normalize(CONTENT))
    state.versions=[CONTENT]
    vectors=FakeVectorStore()
    vectors.point=VectorPoint(1,state.vector,dict(content=CONTENT,text=CONTENT,
        chunk_id=1,chunk_index=0,document_id=7,document='General_FAQ'))
    cache=CacheInvalidator()
    embedded=[]
    def embed(text):embedded.append(text);return fake_vector(text)
    coordinator_class=checkpoint['coordinator'] if checkpoint else KnowledgeUpdateCoordinator
    coordinator=coordinator_class(repository_factory=lambda:FakeRepository(state),
        vector_store=vectors,embed_content=embed,invalidate_local_cache=cache)
    values=dict(chunk_id=1,is_qa=True,question=QUESTION,answer=ANSWER,changed_by='synthetic-test')
    if name=='answer_edit':values['answer']=ANSWER+' Preserve the synthetic condition.'
    if name=='taxonomy_only':values.update(main_category='synthetic new',sub_category='new review')
    if name=='legacy_noop':values['answer']+=f'\n{FOOTER}'
    case=ChunkCreateTests()
    case.setUp()
    try:
        with patch.object(kb_manager,'_knowledge_update_coordinator',return_value=coordinator):
            start=time.perf_counter()
            api=checkpoint['api'] if checkpoint else kb_manager.api_sync_chunk
            result=api(kb_manager.ChunkSyncPayload(**values))
            elapsed=(time.perf_counter()-start)*1000
        fields=parse_faq_relevance_fields(state.content)
        return dict(elapsed_ms=elapsed,category=bool(fields['main_category']),subcategory=bool(fields['sub_category']),
            facts_preserved=ANSWER in state.content,embedding_calls=len(embedded),vector_writes=vectors.upsert_count,
            versions_added=len(state.versions)-1,cache_invalidations=cache.calls,
            postgres_vector_equal=state.vector==vectors.point.vector,
            content_equal=state.content==vectors.point.payload['content'],no_op=result.get('no_op',False))
    finally:case.doCleanups()


def checkpoint_code():
    import new_architecture.knowledge_update as update_module
    def source(path):
        return ast.parse(subprocess.run(['git','show',f'e15761f5eb8d173ad6ebbe0ac9f02aba70503dcf:{path}'],
            cwd=ROOT,capture_output=True,text=True,check=True).stdout)
    cls=next(n for n in source('new_architecture/knowledge_update.py').body
        if isinstance(n,ast.ClassDef) and n.name=='KnowledgeUpdateCoordinator')
    namespace=dict(update_module.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'<P3-coordinator>','exec'),namespace)
    api=next(n for n in source('kb_manager.py').body if isinstance(n,ast.FunctionDef) and n.name=='api_sync_chunk')
    api.decorator_list=[]
    api_namespace=dict(kb_manager.__dict__)
    api_namespace['_knowledge_update_coordinator']=lambda main:kb_manager._knowledge_update_coordinator(main)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[api],type_ignores=[])),'<P3-update-api>','exec'),api_namespace)
    return {'coordinator':namespace['KnowledgeUpdateCoordinator'],'api':api_namespace['api_sync_chunk']}


def create_case(legacy):
    case=ChunkCreateTests();case.setUp()
    try:
        payload=kb_manager.ChunkCreatePayload(document_id=case.document_id,question=QUESTION,
            answer=ANSWER+(f'\n{FOOTER}' if legacy else ''),is_qa=True,
            main_category='synthetic',sub_category='review')
        kb_manager.api_create_chunk(payload)
        _,row=case.query('INSERT INTO chunks')
        fields=parse_faq_relevance_fields(row[1])
        return dict(category=bool(fields['main_category']),subcategory=bool(fields['sub_category']),facts_preserved=ANSWER in row[1])
    finally:case.doCleanups()


async def run(args):
    directory=args.directory.resolve()
    if directory.is_relative_to(ROOT):raise RuntimeError('private_directory_inside_repository')
    if not directory.exists():directory.mkdir(mode=0o700)
    if directory.stat().st_uid!=__import__('os').getuid() or directory.stat().st_mode&0o077:
        raise RuntimeError('private_directory_permissions')
    inputs=json.loads(Path('/tmp/ragbot-p3-batching-20261013/inputs.json').read_text())
    prior=json.loads(Path('/tmp/ragbot-p3-batching-20261013/after.json').read_text())
    if config_identity()!=prior['config']:raise RuntimeError('retrieval_or_model_configuration_changed')
    copy=dict(inputs);identity=copy.pop('identity')
    if digest(copy)!=identity:raise RuntimeError('frozen_input_changed')
    if args.phase=='inventory':
        if not args.confirmed_staging:raise RuntimeError('staging_confirmation_required')
        from scripts.kb_signature import create_signature
        from utils.faq_content import parse_faq_content
        from new_architecture.app.services.history.database import DatabaseManager
        signature=create_signature('p4-read-only')
        write_private(directory/'signature-current.json',signature)
        connection=DatabaseManager().get_connection()
        findings={'current':[],'history':[]}
        counts={}
        try:
            connection.set_session(readonly=True,isolation_level='REPEATABLE READ',autocommit=False)
            with connection.cursor() as cursor:
                for name,query in [('current','SELECT id, content FROM chunks ORDER BY id'),
                    ('history','SELECT id, content FROM chunk_versions ORDER BY id')]:
                    cursor.execute(query)
                    rows=cursor.fetchall()
                    count=dict(rows=len(rows),faq=0,uncategorized=0,missing_subcategory=0,orphan=0,ambiguous=0)
                    for identifier,content in rows:
                        parsed=parse_faq_content(content or '')
                        if not parsed.is_qa:continue
                        count['faq']+=1
                        for reason,condition in [('uncategorized',not parsed.main_category),
                            ('missing_subcategory',not parsed.sub_category),('orphan',bool(parsed.sub_category and not parsed.main_category)),
                            ('ambiguous',bool(parsed.taxonomy_error))]:
                            if condition:count[reason]+=1;findings[name].append(dict(id=str(identifier),reason=reason))
                    counts[name]=count
        finally:connection.rollback();connection.close()
        summary=dict(phase='inventory',counts=counts,findings=findings,
            postgres_count=signature['postgres']['record_count'],postgres_signature=signature['postgres']['aggregate_sha256'],
            qdrant_count=signature['qdrant']['point_count'],consistent=signature['cross_store']['consistent'])
        write_private(directory/'inventory.json',summary)
        print(json.dumps(summary));return
    if args.phase=='composed':
        if not args.confirmed_staging:raise RuntimeError('staging_confirmation_required')
        import httpx
        from scripts.rrf_p1_compare import capabilities
        async with httpx.AsyncClient(timeout=30) as client:
            serving=await capabilities(client)
            if serving!=inputs['capabilities']:raise RuntimeError('serving_configuration_changed')
            summary,answers=await composed_checks(client,serving['VLLM_URL'][0]['max_model_len'])
        summary.update(input_identity=identity,config_identity=digest(config_identity()))
        write_private(directory/'composed.json',summary)
        write_private(directory/'composed-answers.json',answers)
        print(json.dumps(summary));return
    retrieval=[]
    for case,expected in zip(inputs['cases'],prior['cases'],strict=True):
        rows=await depth_search(case).search(case['query'],top_k=50,allowed_docs=['frozen-scope'])
        ids=[r.doc_id for r in rows]
        if ids!=expected['retrieved_ids'] or any(r.content!=case['chunks'][r.doc_id]['text'] for r in rows):
            raise RuntimeError('frozen_retrieval_changed')
        retrieval.append(dict(case_id=case['id'],returned=len(ids),ids_identity=digest(ids)))
    if args.phase=='paired':
        old=checkpoint_code()
        measurements=[]
        for name in ('answer_edit','taxonomy_only','clean_noop','legacy_noop'):
            pairs={'before':[],'after':[]}
            for index in range(100):
                order=('before','after') if index%2==0 else ('after','before')
                for phase in order:pairs[phase].append(update_case(name,old if phase=='before' else None))
            measurements.append(dict(case=name,**{phase:dict(timing=percentiles([r['elapsed_ms'] for r in rows]),
                observations={k:v for k,v in rows[0].items() if k!='elapsed_ms'}) for phase,rows in pairs.items()}))
        summary=dict(phase='paired',fixture_identity=digest({'content':CONTENT,'scope':[1,0,7,'General_FAQ']}),
            input_identity=identity,config_identity=digest(config_identity()),measurements=measurements,
            scope='alternating P3/current synthetic complete-store fixtures; zero live writes or service calls')
        write_private(directory/'paired.json',summary)
        print(json.dumps(summary));return
    measurements=[]
    for name in ('answer_edit','taxonomy_only','clean_noop','legacy_noop'):
        rows=[update_case(name) for _ in range(100)]
        measurements.append(dict(case=name,timing=percentiles([r['elapsed_ms'] for r in rows]),
            observations={k:v for k,v in rows[0].items() if k!='elapsed_ms'}))
    summary=dict(phase=args.phase,input_identity=identity,config_identity=digest(config_identity()),
        fixture_identity=digest(CONTENT),retrieval=retrieval,measurements=measurements,
        create_clean=create_case(False),create_legacy=create_case(True),live=False)
    if args.confirmed_staging:
        import httpx
        from scripts.reranker_p3_compare import normal
        from scripts.rrf_p1_compare import capabilities
        async with httpx.AsyncClient(timeout=30) as client:
            if await capabilities(client)!=inputs['capabilities']:raise RuntimeError('serving_configuration_changed')
            cases,answers=await normal(inputs,client)
        write_private(directory/f'{args.phase}-answers.json',answers)
        summary.update(live=True,cases=cases)
    write_private(directory/f'{args.phase}.json',summary)
    safe={k:v for k,v in summary.items() if k!='cases'}
    if 'cases' in summary:
        safe['live_checks']=dict(relevant_selected=sum(c['relevant_selected'] for c in summary['cases']),
            context_facts=sum(c['context_fact_count'] for c in summary['cases']),
            answer_checks=sum(sum(c.get('answer_checks',{}).values()) for c in summary['cases']))
    print(json.dumps(safe))


async def composed_checks(client,context_limit):
    """New synthetic Q/A composition; real embedding/scoring/generation, no stores."""
    import os
    import re
    from openai import AsyncOpenAI
    from tests.rrf_fixtures import controlled_cases
    from utils.faq_content import compose_faq,parse_faq_content
    from utils.rag_utils import build_faq_rerank_text
    from utils.tei_embedding_client import TeiEmbeddingClient
    from utils.persian_hybrid_search import SearchResult
    from utils.RagSystem import RAGSystem
    from scripts.reranker_p3_compare import RecordingHttp
    cases=controlled_cases()
    rows=[]
    for cid in cases[0]['relevant_ids']:
        parsed=parse_faq_content(cases[0]['chunks'][cid]['text'])
        content=compose_faq(parsed.question,parsed.answer,dict(main_category=parsed.main_category,sub_category=parsed.sub_category))
        if content!=cases[0]['chunks'][cid]['text']:raise RuntimeError('synthetic_facts_changed')
        rows.append(SearchResult(cid,content,.1,1,.5))
    start=time.perf_counter()
    vectors=await TeiEmbeddingClient(os.environ['TEI_EMBED_URL'],client).embed_documents(
        [kb_manager.normalizer.normalize(row.content) for row in rows])
    embedding_ms=(time.perf_counter()-start)*1000
    rag=RAGSystem.__new__(RAGSystem)
    rag._closed=False;rag.model_id='/app/model';rag._vllm_active=rag._vllm_timeout_total=0
    rag.client=AsyncOpenAI(base_url=os.environ['VLLM_URL'],api_key='vllm-token-not-needed',max_retries=0,timeout=50)
    original=rag._completion
    budgets=[]
    async def budgeted(**kwargs):
        response=await client.post(os.environ['VLLM_URL'].rstrip('/').removesuffix('/v1')+'/tokenize',
            json={'model':kwargs['model'],'messages':kwargs['messages'],'add_generation_prompt':True})
        response.raise_for_status()
        count=response.json()['count']
        if not isinstance(count,int) or count+kwargs['max_tokens']>context_limit:raise RuntimeError('context_budget_exceeded')
        budgets.append(dict(prompt_tokens=count,reserved_output_tokens=kwargs['max_tokens']))
        return await original(**kwargs)
    rag._completion=budgeted
    outputs=[];answers=[]
    try:
        for case in cases:
            search=depth_search(case);recorder=RecordingHttp(client)
            search._http=recorder;search.tei_rerank_url=os.environ['TEI_RERANK_URL'].rstrip('/')
            start=time.perf_counter()
            selected=await search.rerank_search_results(case['query'],rows,top_k=10)
            rerank_ms=(time.perf_counter()-start)*1000
            context=rag.generate_context(selected)
            if any(parse_faq_content(row.content).answer not in context for row in rows):raise RuntimeError('generation_context_lost_facts')
            start=time.perf_counter()
            answer=await rag.answer(user_question=case['query'],context=context,recent_history='',current_summary='',
                tone='friendly',response_type='normal',enable_history=False,category='FAQ')
            outputs.append(dict(case_id=case['id'],selected_ids=[row.doc_id for row in selected],
                request_sizes=[c['size'] for c in recorder.calls],rerank_ms=rerank_ms,
                generation_ms=(time.perf_counter()-start)*1000,**budgets[-1],
                checks={f['id']:bool(re.search(f['pattern'],answer,re.DOTALL)) for f in case['required_facts']},
                forbidden_claim=any(re.search(p,answer) for p in case['forbidden_patterns'])))
            answers.append(dict(case_id=case['id'],answer=answer))
    finally:await rag.client.close()
    return dict(phase='composed',fixture_identity=digest([r.content for r in rows]),
        scoring_identity=digest([build_faq_rerank_text(r.content) for r in rows]),
        embedding_count=len(vectors),embedding_dimension=len(vectors[0]),embedding_ms=embedding_ms,
        source_content_preserved=True,cases=outputs,scope='synthetic facts; no KB writes or persisted conversations'),answers


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('before','after','paired','composed','inventory'))
    parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--confirmed-staging',action='store_true')
    asyncio.run(run(parser.parse_args()))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__}),file=sys.stderr)
        sys.exit(2)
