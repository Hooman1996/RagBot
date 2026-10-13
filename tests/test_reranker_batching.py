"""Synthetic protocol, global-ranking and resource tests; no model-quality claims."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import httpx
from pipeline_observer import bind_pipeline_observer
from utils.performance_config import PERFORMANCE_SETTINGS, load_performance_settings
from utils.persian_hybrid_search import PersianHybridSearch, SearchResult
from utils.rag_utils import build_faq_rerank_text
from utils.service_errors import ServiceProtocolError, ServiceTimeoutError, ServiceUnavailableError


def candidates(count):
    return [SearchResult(doc_id=str(i), content=f'question: entry-{i:03}\nanswer: full answer {i}\nsecond sentence\nquestion category: synthetic. sub_category: test',
        score=.1, bm25_score=1, semantic_score=.5, original_rrf_rank=i+1,
        metadata={'document_name':'synthetic-FAQ','nested':{'source':i}}) for i in range(count)]


class Observer:
    def __init__(self): self.records=[]
    def record(self, result): self.records.append(result)


class Server:
    def __init__(self, limit=64, factory=None, info=None):
        self.limit,self.factory,self.info=limit,factory,info
        self.posts=[]
        self.gets=0

    async def handle(self, request):
        if request.method=='GET':
            self.gets+=1
            await asyncio.sleep(0)
            return httpx.Response(200,json=self.info if self.info is not None else {'max_client_batch_size':self.limit})
        payload=json.loads(request.content)
        self.posts.append(payload)
        if len(payload['texts'])>self.limit:
            return httpx.Response(413,json={'error':'synthetic batch limit'})
        if self.factory is not None:
            result=self.factory(len(self.posts),payload,request)
            if asyncio.iscoroutine(result):result=await result
            return result
        return httpx.Response(200,json=[{'index':i,'score':int(re.search(r'entry-(\d+)',text)[1])/1000}
            for i,text in reversed(list(enumerate(payload['texts'])))])


class RerankerBatchingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.clients=[]
    async def asyncTearDown(self):
        for client in self.clients:await client.aclose()

    def search(self, server=None, limit=50):
        server=server or Server()
        client=httpx.AsyncClient(transport=httpx.MockTransport(server.handle))
        self.clients.append(client)
        search=PersianHybridSearch.__new__(PersianHybridSearch)
        search._closed=False
        search._http=client
        search.tei_rerank_url='http://synthetic.test'
        search.rerank_max_client_batch_size=limit
        search._tei_reranker_active=search._tei_pool_timeout_total=0
        return search,server

    async def test_sizes_mapping_all_scores_global_top_k_and_full_content(self):
        for limit in (50,64):
            for count in (0,1,49,50,51,64,65,150,300):
                with self.subTest(limit=limit,count=count):
                    search,server=self.search(limit=limit)
                    original=candidates(count)
                    observer=Observer()
                    with bind_pipeline_observer(observer):
                        result=await search.rerank_search_results('synthetic',original,top_k=10)
                    expected_sizes=[min(limit,count-offset) for offset in range(0,count,limit)]
                    self.assertEqual([len(p['texts']) for p in server.posts],expected_sizes)
                    self.assertEqual([r.doc_id for r in result],[str(i) for i in range(count-1,max(-1,count-11),-1)])
                    self.assertEqual(len(observer.records),1)
                    record=observer.records[0]
                    self.assertEqual(record.metrics['batch_count'],len(expected_sizes))
                    self.assertEqual(record.metrics['completed_batch_count'],len(expected_sizes))
                    self.assertEqual(record.metrics['request_sizes'],expected_sizes)
                    self.assertEqual(len(record.output_data['rankings']),count)
                    for ranked in record.output_data['rankings']:
                        source=original[int(ranked['chunk_id'])]
                        self.assertEqual(ranked['content'],source.content)
                        self.assertEqual(ranked['metadata'],source.metadata)
                        self.assertEqual(ranked['reranker_score'],int(source.doc_id)/1000)
                    self.assertEqual(server.gets,1 if count else 0)
                    self.assertEqual(search._tei_reranker_active,0)
                    for r in result:
                        source=original[int(r.doc_id)]
                        self.assertEqual(r.content,source.content)
                        self.assertEqual(r.metadata,source.metadata)
                        self.assertEqual(r.original_rrf_rank,source.original_rrf_rank)
                        self.assertEqual(r.reranker_score,int(r.doc_id)/1000)
                    for p in server.posts:self.assertIs(p['raw_scores'],False)
                    self.assertEqual([t for p in server.posts for t in p['texts']],
                        [build_faq_rerank_text(c.content) for c in original])

    async def test_related_global_threshold_top_five_and_unchanged_texts(self):
        search,server=self.search()
        original=[{'question':f'entry-{i:03}','answer':f'private synthetic answer {i}','_trace_id':i} for i in range(150)]
        observer=Observer()
        with bind_pipeline_observer(observer):
            selected=await search.rerank('synthetic',original,threshold=.145)
        self.assertEqual([r['_trace_id'] for r in selected],[149,148,147,146,145])
        self.assertTrue(all(r is original[r['_trace_id']] for r in selected))
        self.assertEqual([len(p['texts']) for p in server.posts],[50,50,50])
        self.assertTrue(all('raw_scores' not in p for p in server.posts))
        self.assertEqual([t for p in server.posts for t in p['texts']],[r['question'] for r in original])
        self.assertEqual(len(observer.records),1)
        self.assertEqual(observer.records[0].metrics['auxiliary_related_questions']['batch_count'],3)
        self.assertEqual(len(observer.records[0].output_data['auxiliary_related_questions']['rankings']),150)
        self.assertEqual(await search.rerank('synthetic',original,threshold=.2),[])

    async def test_duplicate_scoring_texts_keep_distinct_global_positions(self):
        def factory(number,payload,request):
            return httpx.Response(200,json=[{'index':i,'score':((number-1)*50+i)/1000}
                for i in reversed(range(len(payload['texts'])))])
        search,_=self.search(Server(factory=factory))
        original=candidates(51)
        original[50]=replace(original[50],content=original[0].content)
        result=await search.rerank_search_results('synthetic',original,top_k=51)
        self.assertEqual([r.doc_id for r in result],[str(i) for i in range(50,-1,-1)])
        self.assertEqual(result[0].metadata,original[50].metadata)
        self.assertEqual(result[-1].metadata,original[0].metadata)

    async def test_related_zero_candidates_has_no_http_and_one_observer_result(self):
        search,server=self.search()
        observer=Observer()
        with bind_pipeline_observer(observer):self.assertEqual(await search.rerank('synthetic',[],threshold=.1),[])
        self.assertEqual((server.gets,len(server.posts),search._tei_reranker_active),(0,0,0))
        self.assertEqual(len(observer.records),1)

    async def test_exact_ties_keep_context_rrf_id_policy_and_related_encounter_policy(self):
        def ties(number,payload,request):
            return httpx.Response(200,json=[{'index':i,'score':.5} for i in reversed(range(len(payload['texts'])))])
        search,_=self.search(Server(factory=ties),limit=2)
        original=candidates(5)
        original[0]=replace(original[0],doc_id='b',original_rrf_rank=1)
        original[1]=replace(original[1],doc_id='a',original_rrf_rank=1)
        result=await search.rerank_search_results('synthetic',original,top_k=5)
        self.assertEqual([r.doc_id for r in result],['a','b','2','3','4'])
        related=[{'question':f'entry-{i:03}','id':i} for i in range(5)]
        selected=await search.rerank('synthetic',related,threshold=.5)
        self.assertEqual([r['id'] for r in selected],[1,0,3,2,4])

    async def test_invalid_responses_fail_whole_operation_on_both_paths(self):
        valid=[{'index':0,'score':.2},{'index':1,'score':.3}]
        invalid=[None,{},'bad',[],valid[:1],valid+[{'index':2,'score':.4}],['bad','bad'],
            [{'index':0,'score':.2},{'index':0,'score':.3}]]
        for index in (True,False,-1,2,1.0,'1',None):
            invalid.append([valid[0],{'index':index,'score':.3}])
        for score in (None,True,False,'0.5',float('nan'),float('inf'),-float('inf'),10**400):
            invalid.append([valid[0],{'index':1,'score':score}])
        invalid.extend([[valid[0],{'score':.3}],[valid[0],{'index':1}]])
        for body in invalid:
            for path in ('context','related'):
                with self.subTest(body_type=type(body).__name__,path=path):
                    search,_=self.search(Server(factory=lambda n,p,r,b=body:httpx.Response(200,content=json.dumps(b))))
                    observer=Observer()
                    with bind_pipeline_observer(observer),self.assertRaises(ServiceProtocolError):
                        await self.invoke(search,path,2)
                    self.assertEqual(search._tei_reranker_active,0)
                    self.assertEqual(len(observer.records),1)
                    self.assertEqual(observer.records[0].status,'ERROR')
                    self.assertIsNone(observer.records[0].output_data)

    async def invoke(self,search,path,count):
        if path=='context':return await search.rerank_search_results('synthetic',candidates(count),top_k=10)
        return await search.rerank('synthetic',[{'question':f'entry-{i:03}'} for i in range(count)],threshold=.1)

    async def test_malformed_json_is_translated(self):
        for path in ('context','related'):
            search,_=self.search(Server(factory=lambda n,p,r:httpx.Response(200,text='{invalid')))
            with self.assertRaises(ServiceProtocolError):await self.invoke(search,path,1)
            self.assertEqual(search._tei_reranker_active,0)

    async def test_failed_middle_batch_no_partial_success_or_further_requests(self):
        for path in ('context','related'):
            for failure in ('incomplete','http','read_timeout','pool_timeout'):
                def factory(number,payload,request):
                    if number==2:
                        if failure=='http':return httpx.Response(503)
                        if failure=='read_timeout':raise httpx.ReadTimeout('synthetic',request=request)
                        if failure=='pool_timeout':raise httpx.PoolTimeout('synthetic',request=request)
                        return httpx.Response(200,json=[])
                    return httpx.Response(200,json=[{'index':i,'score':.5} for i in range(len(payload['texts']))])
                with self.subTest(path=path,failure=failure):
                    search,server=self.search(Server(factory=factory))
                    observer=Observer()
                    error=ServiceProtocolError if failure=='incomplete' else ServiceUnavailableError if failure=='http' else ServiceTimeoutError
                    with bind_pipeline_observer(observer),self.assertRaises(error):await self.invoke(search,path,150)
                    self.assertEqual(len(server.posts),2)
                    self.assertEqual(search._tei_reranker_active,0)
                    self.assertEqual(search._tei_pool_timeout_total,int(failure=='pool_timeout'))
                    self.assertEqual(len(observer.records),1)
                    m=observer.records[0].metrics
                    if path=='related':m=m['auxiliary_related_questions']
                    self.assertEqual((m['batch_count'],m['completed_batch_count']),(2,1))
                    self.assertEqual(len(m['batch_duration_ms']),2)

    async def test_cancellation_in_middle_batch_propagates_and_balances_counters(self):
        for path in ('context','related'):
            reached=asyncio.Event()
            async def factory(number,payload,request):
                if number==2:
                    reached.set()
                    await asyncio.Event().wait()
                return httpx.Response(200,json=[{'index':i,'score':.5} for i in range(len(payload['texts']))])
            search,server=self.search(Server(factory=factory))
            observer=Observer()
            with bind_pipeline_observer(observer):
                task=asyncio.create_task(self.invoke(search,path,150))
                await asyncio.wait_for(reached.wait(),1)
                self.assertEqual(search._tei_reranker_active,1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            self.assertEqual(search._tei_reranker_active,0)
            self.assertEqual(len(server.posts),2)
            self.assertEqual(len(observer.records),1)
            self.assertEqual(observer.records[0].status,'CANCELLED')

    async def test_external_timeout_cancels_remaining_batches(self):
        for path in ('context','related'):
            async def factory(number,payload,request):
                if number==2:await asyncio.Event().wait()
                return httpx.Response(200,json=[{'index':i,'score':.5} for i in range(len(payload['texts']))])
            search,server=self.search(Server(factory=factory))
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(.02):await self.invoke(search,path,150)
            self.assertEqual(len(server.posts),2)
            self.assertEqual(search._tei_reranker_active,0)

    async def test_concurrent_operations_are_independent_and_capability_lookup_is_coalesced(self):
        active={}
        async def factory(number,payload,request):
            query=payload['query']
            active[query]=active.get(query,0)+1
            self.assertEqual(active[query],1)
            await asyncio.sleep(0)
            active[query]-=1
            return httpx.Response(200,json=[{'index':i,'score':int(re.search(r'entry-(\d+)',t)[1])/1000}
                for i,t in enumerate(payload['texts'])])
        search,server=self.search(Server(factory=factory))
        observer=Observer()
        with bind_pipeline_observer(observer):
            a,b=await asyncio.gather(search.rerank_search_results('first',candidates(150),top_k=10),
                search.rerank_search_results('second',candidates(65),top_k=10))
        self.assertEqual(([r.doc_id for r in a],[r.doc_id for r in b]),
            ([str(i) for i in range(149,139,-1)],[str(i) for i in range(64,54,-1)]))
        self.assertEqual(server.gets,1)
        self.assertEqual(search._tei_reranker_active,0)
        self.assertEqual(len(observer.records),2)
        self.assertEqual(sorted(r.metrics['request_sizes'] for r in observer.records),[[50,15],[50,50,50]])

    async def test_server_limit_guard_is_target_specific_and_separate_from_embedding(self):
        for server_limit,client_limit,allowed in ((20,50,False),(64,65,False),(20,10,True),(200,150,True)):
            with self.subTest(server=server_limit,client=client_limit):
                search,server=self.search(Server(limit=server_limit),limit=client_limit)
                if allowed:await self.invoke(search,'context',1)
                else:
                    with self.assertRaises(ServiceProtocolError):await self.invoke(search,'context',1)
                    self.assertEqual(server.posts,[])
                self.assertEqual(search._tei_reranker_active,0)

    async def test_invalid_capabilities_fail_closed_and_are_not_cached(self):
        for info in ({},{'max_client_batch_size':0},{'max_client_batch_size':True},{'max_client_batch_size':'64'},[]):
            search,server=self.search(Server(info=info))
            with self.assertRaises(ServiceProtocolError):await self.invoke(search,'context',1)
            self.assertEqual(server.posts,[])
            self.assertEqual(search._rerank_server_limits,{})
            self.assertEqual(search._tei_reranker_active,0)

    async def test_capability_failures_and_cancellation_balance_resources(self):
        for failure in ('json','http','pool','cancel'):
            reached=asyncio.Event()
            async def handler(request):
                self.assertEqual(request.method,'GET')
                if failure=='json':return httpx.Response(200,text='{invalid')
                if failure=='http':return httpx.Response(503)
                if failure=='pool':raise httpx.PoolTimeout('synthetic',request=request)
                reached.set()
                await asyncio.Event().wait()
            search,_=self.search()
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
            self.clients.append(client)
            search._http=client
            if failure=='cancel':
                task=asyncio.create_task(self.invoke(search,'context',1))
                await asyncio.wait_for(reached.wait(),1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            else:
                error={'json':ServiceProtocolError,'http':ServiceUnavailableError,'pool':ServiceTimeoutError}[failure]
                with self.assertRaises(error):await self.invoke(search,'context',1)
            self.assertEqual(search._tei_reranker_active,0)
            self.assertEqual(search._tei_pool_timeout_total,int(failure=='pool'))
            self.assertEqual(search._rerank_server_limits,{})

    async def test_closed_client_sends_no_request(self):
        search,server=self.search()
        search._closed=True
        with self.assertRaises(RuntimeError):await self.invoke(search,'context',1)
        self.assertEqual((server.gets,len(server.posts),search._tei_reranker_active),(0,0,0))


class RerankBatchConfigurationTests(unittest.TestCase):
    def test_default_loader_validator_and_templates(self):
        from scripts.validate_environment import _specs
        with patch.dict(os.environ,{},clear=True):
            settings=load_performance_settings()
        self.assertEqual(settings.tei_rerank_max_client_batch_size,50)
        spec=_specs()['TEI_RERANK_MAX_CLIENT_BATCH_SIZE']
        self.assertEqual((spec.kind,spec.default,spec.minimum),('int','50',1))
        for name in ('env.example','Production_ENV','.env.example.generated'):
            text=(Path(__file__).resolve().parents[1]/name).read_text()
            self.assertEqual(text.count('TEI_RERANK_MAX_CLIENT_BATCH_SIZE=50'),1)

    def test_invalid_values_and_embedding_independence(self):
        for value in ('0','-1','1.5','true','bad'):
            with self.subTest(value=value),patch.dict(os.environ,{'TEI_RERANK_MAX_CLIENT_BATCH_SIZE':value},clear=True):
                with self.assertRaises(ValueError):load_performance_settings()
        with patch.dict(os.environ,{'TEI_RERANK_MAX_CLIENT_BATCH_SIZE':'64','TEI_EMBED_MAX_CLIENT_BATCH_SIZE':'50'},clear=True):
            settings=load_performance_settings()
            self.assertEqual((settings.tei_rerank_max_client_batch_size,settings.tei_embed_max_client_batch_size),(64,50))
