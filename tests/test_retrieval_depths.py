import asyncio
from dataclasses import replace
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from pipeline_observer import PipelineStage, bind_pipeline_observer
from tests.retrieval_depth_fixtures import depth_search, expanded_case
from tests.rrf_fixtures import case_from_ids
from utils.performance_config import PERFORMANCE_SETTINGS, load_performance_settings
from utils.persian_hybrid_search import PersianHybridSearch
from utils.revision_cache import RevisionAwareCache


class MetadataObserver:
    def __init__(self): self.rows = []
    def record(self, result):
        if result.stage == PipelineStage.RETRIEVAL:
            self.rows.append(dict(result.metrics))


class RetrievalDepthTests(unittest.IsolatedAsyncioTestCase):
    async def run_depths(self, search, lexical=None, dense=None, final=None):
        observer = MetadataObserver()
        with bind_pipeline_observer(observer):
            result = await search.search('synthetic', allowed_docs=['permitted-FAQ'],
                top_k=final, bm25_candidate_limit=lexical, semantic_candidate_limit=dense)
        return result, observer.rows[-1]

    async def test_default_depth_is_50_and_content_is_preserved(self):
        case = expanded_case()
        rows, metrics = await self.run_depths(depth_search(case))
        self.assertEqual(metrics['bm25_candidate_limit'], 50)
        self.assertEqual(metrics['bm25_candidate_count'], 50)
        self.assertEqual(metrics['semantic_candidate_count'], 50)
        self.assertEqual(len(rows), PERFORMANCE_SETTINGS.rag_retrieval_top_k)
        for row in rows: self.assertEqual(row.content, case['chunks'][row.doc_id]['text'])

    async def test_required_combined_configurations_have_actual_distinct_counts(self):
        case = expanded_case()
        for lexical, dense, final, returned in [(50,50,50,50),(150,50,150,150),
                (100,100,150,150),(150,150,150,150),(300,300,300,300)]:
            with self.subTest(depths=(lexical,dense,final)):
                rows, metrics = await self.run_depths(depth_search(case),lexical,dense,final)
                self.assertEqual(len(rows), returned)
                self.assertEqual(len({r.doc_id for r in rows}), returned)
                self.assertEqual(metrics['bm25_candidate_count'], lexical)
                self.assertEqual(metrics['semantic_candidate_count'], dense)
                self.assertEqual(metrics['returned_candidate_count'], returned)
                self.assertEqual([r.original_rrf_rank for r in rows],list(range(1,returned+1)))
                self.assertEqual(metrics['bm25_candidate_limit'],lexical)
                self.assertEqual(metrics['semantic_candidate_limit'],dense)
                self.assertEqual(metrics['retrieval_top_k'],final)

    async def test_one_branch_depth_changes_relevant_information(self):
        search = depth_search(expanded_case())
        default, _ = await self.run_depths(search,50,50,50)
        lexical, _ = await self.run_depths(search,150,50,50)
        dense, _ = await self.run_depths(search,50,150,50)
        self.assertFalse({'lex-relevant','dense-relevant'} & {r.doc_id for r in default})
        self.assertIn('lex-relevant',{r.doc_id for r in lexical})
        self.assertIn('dense-relevant',{r.doc_id for r in dense})

    async def test_small_lexical_limit_does_not_limit_dense_branch(self):
        search = depth_search(expanded_case())
        rows, m = await self.run_depths(search,5,100,150)
        self.assertEqual((m['bm25_candidate_count'],m['semantic_candidate_count'],len(rows)),(5,100,105))
        self.assertEqual(search.requested_dense_depths,[100])
        self.assertEqual(search.allowed_scopes,[['permitted-FAQ']])

    async def test_overlap_and_small_corpus_are_not_padded(self):
        rows,m = await self.run_depths(depth_search(case_from_ids(['a','b'],['b','c'])),150,150,300)
        self.assertEqual({r.doc_id for r in rows},{'a','b','c'})
        self.assertEqual(m['candidate_union_count'],3)
        self.assertEqual(len(rows),3)

    async def test_nonpositive_lexical_candidates_stay_excluded(self):
        case=case_from_ids(['positive','zero','negative'],[])
        for r,score in zip(case['sparse'],[1,0,-1]): r['score']=score
        rows,m=await self.run_depths(depth_search(case),150,150,150)
        self.assertEqual([r.doc_id for r in rows],['positive'])
        self.assertEqual(m['bm25_candidate_count'],1)

    async def test_empty_branch_and_corpus_diagnostics_show_effective_depths(self):
        for case in [case_from_ids([],[]),case_from_ids([],['a'])]:
            rows,m=await self.run_depths(depth_search(case),150,100,300)
            self.assertEqual(m['bm25_candidate_limit'],150)
            self.assertEqual(m['semantic_candidate_limit'],100)
            self.assertEqual(m['returned_candidate_count'],len(rows))

    async def test_invalid_request_depths_reject_without_coercion(self):
        for value in (0,-1,1.5,'50',True,False):
            for name in ('bm25_candidate_limit','semantic_candidate_limit','top_k'):
                with self.subTest(value=value,name=name):
                    with self.assertRaises(ValueError):
                        await depth_search(expanded_case()).search('synthetic',allowed_docs=['permitted'],**{name:value})

    async def test_override_then_default_preserves_shared_settings_and_environment(self):
        search=depth_search(expanded_case())
        environment=dict(os.environ)
        _,m=await self.run_depths(search,150,150,150)
        _,n=await self.run_depths(search)
        self.assertEqual(m['bm25_candidate_count'],150)
        self.assertEqual(n['bm25_candidate_count'],50)
        self.assertEqual(n['semantic_candidate_limit'],PERFORMANCE_SETTINGS.rag_semantic_candidate_limit)
        self.assertEqual(dict(os.environ),environment)
        self.assertEqual(PERFORMANCE_SETTINGS.rag_bm25_candidate_limit,50)

    async def test_concurrent_requests_on_one_engine_are_isolated(self):
        search=depth_search(expanded_case())
        a,b=await asyncio.gather(self.run_depths(search,150,50,150),self.run_depths(search,5,100,150))
        self.assertEqual((a[1]['bm25_candidate_count'],a[1]['semantic_candidate_count'],len(a[0])),(150,50,150))
        self.assertEqual((b[1]['bm25_candidate_count'],b[1]['semantic_candidate_count'],len(b[0])),(5,100,105))

    async def test_corpus_cache_is_reused_across_request_depths(self):
        search=depth_search(expanded_case())
        corpus=search._get_or_build_bm25(['permitted'])
        search._bm25_cache=RevisionAwareCache()
        search._processor_lock=threading.Lock()
        search.chunk_revision_fetcher=lambda docs:'frozen-1'
        builds=[]
        search._fetch_chunks=lambda docs:corpus[2]
        def build(chunks):
            builds.append(1)
            return corpus[0],corpus[1],[]
        search._build_temporary_bm25=build
        search._get_or_build_bm25=PersianHybridSearch._get_or_build_bm25.__get__(search)
        await self.run_depths(search,150,50,150)
        _,m=await self.run_depths(search)
        self.assertEqual(builds,[1])
        self.assertEqual(m['bm25_candidate_count'],50)

    async def test_configured_branch_depths_apply_without_request_overrides(self):
        settings=replace(PERFORMANCE_SETTINGS,rag_bm25_candidate_limit=100,
            rag_semantic_candidate_limit=100,rag_retrieval_top_k=150)
        with patch('utils.persian_hybrid_search.PERFORMANCE_SETTINGS',settings):
            rows,m=await self.run_depths(depth_search(expanded_case()))
        self.assertEqual((m['bm25_candidate_count'],m['semantic_candidate_count'],len(rows)),(100,100,150))

    async def test_rag_retrieve_forwards_overrides_and_does_not_hide_zero(self):
        from utils.RagSystem import RAGSystem
        rag=RAGSystem.__new__(RAGSystem)
        rag._closed=False
        rag.search_engine=depth_search(expanded_case())
        rows=await rag.retrieve('synthetic',top_k=150,allowed_docs=['permitted'],
            bm25_candidate_limit=150,semantic_candidate_limit=50)
        self.assertEqual(len(rows),150)
        with self.assertRaises(ValueError):await rag.retrieve('synthetic',top_k=0,allowed_docs=['permitted'])

    async def test_trace_records_effective_request_depths_and_counts(self):
        diagnostics = {}
        trace = SimpleNamespace(set_diagnostic=lambda key, value: diagnostics.update({key: value}))
        with patch('utils.persian_hybrid_search.current_trace', return_value=trace):
            rows, metrics = await self.run_depths(depth_search(expanded_case()), 150, 50, 150)
        self.assertEqual(diagnostics['retrieval_depths'], {
            key: metrics[key] for key in ('bm25_candidate_limit', 'semantic_candidate_limit',
                'retrieval_top_k', 'bm25_candidate_count', 'semantic_candidate_count',
                'candidate_union_count', 'returned_candidate_count')})
        self.assertEqual(diagnostics['retrieval_depths']['returned_candidate_count'], len(rows))

    async def test_document_scope_is_required_and_dense_filter_keeps_requested_limit(self):
        search = depth_search(expanded_case())
        with self.assertRaises(ValueError):
            await search.search('synthetic', bm25_candidate_limit=150)
        calls = []
        async def encode(query): return [0.1, 0.2]
        def query_points(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(points=[SimpleNamespace(payload={'chunk_id': 'permitted'}, score=0.9)])
        search._encode_query = encode
        class KeywordRunner:
            async def run(self, function, *args, **kwargs):
                return function(*args, **kwargs)
        search._blocking_runner = KeywordRunner()
        search.qdrant_client = SimpleNamespace(query_points=query_points)
        search.collection_name = 'synthetic'
        search._qdrant_semaphore = asyncio.Semaphore(1)
        for name in ('_qdrant_waiting', '_qdrant_active', '_qdrant_acquired_total', '_qdrant_released_total'):
            setattr(search, name, 0)
        rows = await PersianHybridSearch._semantic_search(search, 'synthetic', ['permitted-FAQ'], 150)
        self.assertEqual(rows, {'permitted': 0.9})
        self.assertEqual(calls[0]['limit'], 150)
        self.assertEqual(calls[0]['query_filter'].must[0].key, 'document')
        self.assertEqual(calls[0]['query_filter'].must[0].match.any, ['permitted-FAQ'])
        self.assertFalse(calls[0]['with_vectors'])


class DepthConfigurationTests(unittest.TestCase):
    def test_positive_integer_env_defaults_and_combined_pool_validation(self):
        for lexical,dense,final in [(50,50,50),(150,50,150),(100,100,150),(150,150,150),(300,300,300),(5,5,1000)]:
            with self.subTest(depths=(lexical,dense,final)),patch.dict(os.environ,{
                'RAG_BM25_CANDIDATE_LIMIT':str(lexical),'RAG_SEMANTIC_CANDIDATE_LIMIT':str(dense),
                'RAG_RETRIEVAL_TOP_K':str(final)},clear=True):
                s=load_performance_settings()
                self.assertEqual((s.rag_bm25_candidate_limit,s.rag_semantic_candidate_limit,s.rag_retrieval_top_k),(lexical,dense,final))

    def test_invalid_env_depths_and_context_relationship_remain_rejected(self):
        for key in ('RAG_BM25_CANDIDATE_LIMIT','RAG_SEMANTIC_CANDIDATE_LIMIT','RAG_RETRIEVAL_TOP_K'):
            for value in ('0','-1','1.5','true','abc'):
                with self.subTest(key=key,value=value),patch.dict(os.environ,{key:value},clear=True):
                    with self.assertRaises(ValueError):load_performance_settings()
        with patch.dict(os.environ,{'RAG_RETRIEVAL_TOP_K':'9','RAG_CONTEXT_RERANK_TOP_K':'10'},clear=True):
            with self.assertRaises(ValueError):load_performance_settings()

    def test_tracked_templates_and_validator_manifest_match_loader(self):
        from scripts.validate_environment import _specs
        # Source-authored generated template has no automatic generator; the
        # manifest and this guard prevent silently dropping the new setting.
        spec=_specs()['RAG_BM25_CANDIDATE_LIMIT']
        self.assertEqual((spec.kind,spec.default,spec.minimum),('int','50',1))
        for name in ('env.example','Production_ENV.example','.env.example.generated'):
            content=(Path(__file__).resolve().parents[1]/name).read_text()
            self.assertEqual(content.count('RAG_BM25_CANDIDATE_LIMIT=50'),1)
