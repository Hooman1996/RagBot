"""Explicitly synthetic FAQ content, payload and locked-write preservation tests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
import logging
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError
import kb_manager
from new_architecture.knowledge_update import (KnowledgeUpdateCoordinator,KnowledgeUpdateFailure,
    PsycopgKnowledgeRepository,VectorPoint)
from tests.test_knowledge_update_consistency import (SharedPostgresState,FakeRepository,FakeVectorStore,
    CacheInvalidator,fake_vector)
from tests import test_kb_manager_chunk_create as create_fixtures
from utils.faq_content import FaqContentError,compose_faq,parse_faq_content
from utils.rag_utils import parse_faq_relevance_fields,build_faq_rerank_text,parse_content


QUESTION='Synthetic request?'
ANSWER='First synthetic fact.\nAfter 14:00, begin next working day.'
CONTENT=f'question: {QUESTION}\nanswer: {ANSWER}\nquestion category: synthetic. sub_category: review'


class FaqTaxonomyParsingTests(unittest.TestCase):
    def test_clean_fields_preserve_all_answer_lines_and_taxonomy(self):
        p=kb_manager.extract_qa_components(CONTENT)
        self.assertEqual((p['question'],p['answer'],p['main_category'],p['sub_category']),
            (QUESTION,ANSWER,'synthetic','review'))
        self.assertEqual(compose_faq(QUESTION,ANSWER,{},current_content=CONTENT),CONTENT)

    def test_creation_with_both_parent_only_and_uncategorized(self):
        for fields,expected in [({'main_category':'synthetic','sub_category':'review'},('synthetic','review')),
            ({'main_category':'synthetic'},('synthetic',None)),({},(None,None))]:
            with self.subTest(fields=fields):
                content=compose_faq(QUESTION,ANSWER,fields)
                parsed=parse_faq_content(content)
                self.assertEqual((parsed.main_category,parsed.sub_category),expected)
                self.assertEqual(parsed.answer,ANSWER)
                self.assertEqual(content.count('question category:'),int(expected[0] is not None))

    def test_legacy_footer_precedence_duplicates_and_clearing(self):
        legacy=ANSWER+'\nquestion category: synthetic. sub_category: review'
        self.assertEqual(compose_faq(QUESTION,legacy,{}),CONTENT)
        self.assertEqual(parse_faq_content(compose_faq(QUESTION,legacy,{'sub_category':'new'})).sub_category,'new')
        parent=compose_faq(QUESTION,legacy,{'main_category':'new'})
        self.assertEqual((parse_faq_content(parent).main_category,parse_faq_content(parent).sub_category),('new',None))
        cleared=compose_faq(QUESTION,legacy,{'main_category':None})
        self.assertNotIn('category:',cleared)
        repeated=legacy+'\nquestion category: synthetic. sub_category: review'
        self.assertEqual(compose_faq(QUESTION,repeated,{}),CONTENT)

    def test_conflicting_footer_rejected_without_losing_read_content(self):
        ambiguous=CONTENT+'\nquestion category: other'
        parsed=parse_faq_content(ambiguous)
        self.assertIsNotNone(parsed.taxonomy_error)
        self.assertIn('question category: other',parsed.answer)
        with self.assertRaises(FaqContentError):compose_faq(QUESTION,ANSWER,{},current_content=ambiguous)
        with self.assertRaises(FaqContentError):compose_faq(QUESTION,ANSWER+'\nquestion category: one\nquestion category: two',{})
        with self.assertRaises(FaqContentError):compose_faq(QUESTION,ANSWER+'\nquestion category: stale. sub_category: old',{},current_content=CONTENT)

    def test_omitted_null_empty_parent_change_and_child_change(self):
        cases=[({},('synthetic','review')),({'main_category':None},(None,None)),
            ({'main_category':''},(None,None)),({'sub_category':None},('synthetic',None)),
            ({'sub_category':''},('synthetic',None)),({'main_category':'other'},('other',None)),
            ({'main_category':'other','sub_category':'assigned'},('other','assigned'))]
        for fields,expected in cases:
            with self.subTest(fields=fields):
                p=parse_faq_content(compose_faq(QUESTION,ANSWER,fields,current_content=CONTENT))
                self.assertEqual((p.main_category,p.sub_category),expected)
        with self.assertRaises(FaqContentError):compose_faq(QUESTION,ANSWER,{'main_category':None,'sub_category':'invalid'},current_content=CONTENT)
        with self.assertRaises(FaqContentError):compose_faq(QUESTION,ANSWER,{'sub_category':'orphan'})

    def test_inline_quoted_and_fenced_prose_is_not_taxonomy(self):
        for text in ['Explain question category: examples in prose.',
            'Use the words sub_category: example in the sentence.',
            'A quoted line:\n> question category: example',
            'A code example:\n```\nquestion category: example\n```']:
            with self.subTest(text=text):
                p=parse_faq_content(compose_faq(QUESTION,text,{}))
                self.assertEqual(p.answer,text)
                self.assertIsNone(p.main_category)

    def test_numbered_answers_are_kept_inside_generation_compatible_outer_answer(self):
        numbered='answer 1: First synthetic fact.\nanswer 2: After 14:00, begin next working day.'
        old=f'question: {QUESTION}\n{numbered}\nquestion category: synthetic. sub_category: review'
        self.assertEqual(parse_faq_content(old).answer,numbered)
        content=compose_faq(QUESTION,numbered,{'main_category':'synthetic','sub_category':'review'})
        self.assertIn('answer: answer 1:',content)
        self.assertIn('First synthetic fact.',content)
        self.assertIn('After 14:00, begin next working day.',content)
        from utils.RagSystem import RAGSystem
        from utils.persian_hybrid_search import SearchResult
        result=SearchResult('1',content,.1,1,.5)
        context=RAGSystem.__new__(RAGSystem).generate_context([result])
        self.assertIn(numbered,context)
        self.assertIn('<main_category>synthetic</main_category>',context)
        self.assertIn('<sub_category>review</sub_category>',context)
        self.assertEqual(parse_faq_relevance_fields(content)['main_category'],'synthetic')
        self.assertNotIn('First synthetic fact.',build_faq_rerank_text(content))
        self.assertTrue(any('First synthetic fact.' in a for a in parse_content(content)['answers']))

    def test_raw_content_and_singleton_legacy_wrapper(self):
        raw='Raw document\nquestion category: words\nsub_category: more words'
        self.assertFalse(parse_faq_content(raw).is_qa)
        self.assertEqual(parse_faq_content(raw).answer,raw)
        wrapped='['+CONTENT+']'
        self.assertEqual(parse_faq_content(wrapped).answer,ANSWER)
        self.assertEqual(compose_faq(QUESTION,ANSWER,{},current_content=wrapped),wrapped)

    def test_legacy_single_line_question_answer_is_preserved(self):
        old=f'question: {QUESTION} answer: {ANSWER}\nquestion category: synthetic. sub_category: review'
        parsed=parse_faq_content(old)
        self.assertEqual((parsed.question,parsed.answer),(QUESTION,ANSWER))
        self.assertEqual(compose_faq(QUESTION,ANSWER,{},current_content=old),old)

    def test_legacy_orphan_is_not_given_an_invented_parent(self):
        old=f'question: {QUESTION}\nanswer: {ANSWER}\nsub_category: historical'
        content=compose_faq(QUESTION,ANSWER+' Changed.',{},current_content=old)
        self.assertIsNone(parse_faq_content(content).main_category)
        self.assertEqual(parse_faq_content(content).sub_category,'historical')
        cleared=compose_faq(QUESTION,ANSWER,{'main_category':None},current_content=old)
        self.assertIsNone(parse_faq_content(cleared).sub_category)


class FaqPayloadTests(unittest.TestCase):
    def payload(self,**metadata):
        return kb_manager.ChunkSyncPayload(chunk_id=1,is_qa=True,question=QUESTION,answer=ANSWER,**metadata)

    def test_omission_is_distinct_from_null_and_empty_and_aliases_are_explicit(self):
        self.assertEqual(self.payload().explicit_taxonomy(),{})
        self.assertEqual(self.payload(main_category=None).explicit_taxonomy(),{'main_category':None})
        self.assertEqual(self.payload(sub_category='').explicit_taxonomy(),{'sub_category':None})
        self.assertEqual(self.payload(category='synthetic',subcategory='review').explicit_taxonomy(),
            {'main_category':'synthetic','sub_category':'review'})
        with self.assertRaises(ValidationError):self.payload(category='one',main_category='two')
        self.assertEqual(self.payload(category='synthetic',main_category='synthetic').main_category,'synthetic')

    def test_label_types_and_structural_injection_are_rejected(self):
        for value in (42,True,['a'],'one\ntwo','question category: one','sub_category: hidden'):
            with self.subTest(value=value),self.assertRaises(ValidationError):self.payload(main_category=value)


class FaqCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.state=SharedPostgresState()
        self.state.content=CONTENT;self.state.vector=fake_vector(CONTENT);self.state.versions=[CONTENT]
        self.vectors=FakeVectorStore()
        self.vectors.point=VectorPoint(1,self.state.vector,{'content':CONTENT,'text':CONTENT,'knowledge_revision':'initial',
            'chunk_id':1,'chunk_index':0,'document_id':7,'document':'General_FAQ'})
        self.cache=CacheInvalidator();self.embedded=[]

    def coordinator(self,repository=None,embed=None):
        def embedding(text):self.embedded.append(text);return fake_vector(text)
        return KnowledgeUpdateCoordinator(repository_factory=repository or (lambda:FakeRepository(self.state)),
            vector_store=self.vectors,embed_content=embed or embedding,invalidate_local_cache=self.cache,
            logger=logging.getLogger('synthetic-taxonomy-test'))

    def prepare(self,answer=ANSWER,**metadata):
        def prepare(current):
            content=compose_faq(QUESTION,answer,metadata,current_content=current)
            return content,content
        return prepare

    def test_answer_edit_and_taxonomy_only_use_complete_searchable_content(self):
        for prepare in (self.prepare(ANSWER+' Updated.'),self.prepare(main_category='other',sub_category='assigned')):
            result=self.coordinator().update(chunk_id=1,prepare_content=prepare,changed_by='synthetic')
            self.assertFalse(result.no_op)
            self.assertEqual(self.state.content,self.vectors.point.payload['text'])
            self.assertEqual(self.state.content,self.vectors.point.payload['content'])
            self.assertEqual(self.state.vector,self.vectors.point.vector)
            self.assertEqual(self.state.vector,fake_vector(self.embedded[-1]))
            self.assertEqual(self.state.versions[-1],self.state.content)
            self.assertIn(ANSWER,self.state.content)
        self.assertEqual(self.cache.calls,2)
        self.assertEqual(parse_faq_content(self.state.content).main_category,'other')

    def test_noop_retains_content_revision_and_no_writes(self):
        result=self.coordinator().update(chunk_id=1,prepare_content=self.prepare(),changed_by='synthetic')
        self.assertTrue(result.no_op)
        self.assertEqual(result.revision,'initial')
        self.assertEqual(result.updated_stores,())
        self.assertEqual(self.embedded,[])
        self.assertEqual((self.vectors.upsert_count,self.cache.calls,len(self.state.versions)),(0,0,1))
        self.assertNotIn('updated_content',result.as_dict())

    def test_unchanged_source_with_stale_vector_is_repaired(self):
        self.vectors.point=replace(self.vectors.point,vector=[0,0])
        result=self.coordinator().update(chunk_id=1,prepare_content=self.prepare(),changed_by='synthetic')
        self.assertFalse(result.no_op)
        self.assertEqual(self.vectors.point.vector,self.state.vector)
        self.assertEqual((self.cache.calls,self.vectors.upsert_count),(1,1))

    def test_unchanged_source_with_missing_scope_metadata_is_repaired(self):
        self.vectors.point.payload.pop('document')
        result=self.coordinator().update(chunk_id=1,prepare_content=self.prepare(),changed_by='synthetic')
        self.assertFalse(result.no_op)
        self.assertEqual(self.vectors.point.payload['document'],'General_FAQ')

    def test_rollback_failure_is_repair_required_without_blind_vector_restore(self):
        class RollbackFails(FakeRepository):
            def rollback(self):raise RuntimeError('synthetic rollback failure')
        self.vectors.fail_confirmation=True
        with self.assertRaises(KnowledgeUpdateFailure) as raised:self.coordinator(repository=lambda:RollbackFails(self.state)).update(
            chunk_id=1,prepare_content=self.prepare(main_category='new'),changed_by='synthetic')
        self.assertTrue(raised.exception.repair_required)
        self.assertEqual(self.vectors.restore_count,0)
        self.assertEqual(self.state.content,CONTENT)

    def test_concurrent_taxonomy_change_cannot_be_restored_from_preflight(self):
        entered=threading.Event();continue_first=threading.Event();first_embeddings=[]
        def embed(text):
            first_embeddings.append(text)
            if len(first_embeddings)==1:
                entered.set()
                if not continue_first.wait(2):raise RuntimeError('synthetic synchronization timeout')
            return fake_vector(text)
        first=self.coordinator(embed=embed)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future=executor.submit(first.update,chunk_id=1,prepare_content=self.prepare(ANSWER+' Answer edit.'),changed_by='answer-editor')
            self.assertTrue(entered.wait(2))
            self.coordinator().update(chunk_id=1,prepare_content=self.prepare(main_category='concurrent',sub_category='new child'),changed_by='taxonomy-editor')
            continue_first.set();future.result(timeout=2)
        parsed=parse_faq_content(self.state.content)
        self.assertEqual((parsed.main_category,parsed.sub_category),('concurrent','new child'))
        self.assertIn('Answer edit.',parsed.answer)
        self.assertEqual(len(first_embeddings),2)
        self.assertIn('concurrent',first_embeddings[-1])
        self.assertEqual(self.state.vector,self.vectors.point.vector)
        self.assertEqual(len(self.state.versions),3)

    def test_stale_legacy_footer_is_rejected_under_lock_after_concurrent_clear(self):
        entered=threading.Event();resume=threading.Event()
        def embed(text):
            entered.set()
            if not resume.wait(2):raise RuntimeError('synthetic timeout')
            return fake_vector(text)
        legacy=ANSWER+' Changed.\nquestion category: synthetic. sub_category: review'
        with ThreadPoolExecutor(max_workers=2) as executor:
            future=executor.submit(self.coordinator(embed=embed).update,chunk_id=1,
                prepare_content=self.prepare(legacy),changed_by='legacy-editor')
            self.assertTrue(entered.wait(2))
            self.coordinator().update(chunk_id=1,prepare_content=self.prepare(main_category=None),changed_by='taxonomy-editor')
            resume.set()
            with self.assertRaises(FaqContentError):future.result(timeout=2)
        self.assertIsNone(parse_faq_content(self.state.content).main_category)
        self.assertIsNone(parse_faq_content(self.state.content).sub_category)
        self.assertEqual(len(self.state.versions),2)
        self.assertEqual(self.state.content,self.vectors.point.payload['content'])

    def test_revert_restores_categorized_and_uncategorized_content_exactly(self):
        for target in (f'question: {QUESTION}\nanswer: historical fact',CONTENT):
            result=self.coordinator().update(chunk_id=1,content=target,normalized_content=target,changed_by='Reverted by synthetic')
            self.assertTrue(result.success)
            self.assertEqual(self.state.content,target)
            self.assertEqual(self.state.versions[-1],target)
            self.assertEqual(self.vectors.point.payload['content'],target)
            self.assertEqual(self.state.vector,fake_vector(target))
        self.assertEqual(self.cache.calls,2)

    def test_conflict_rejection_and_embedding_failure_leave_stores_unchanged(self):
        with self.assertRaises(FaqContentError):self.coordinator().update(chunk_id=1,
            prepare_content=self.prepare(main_category=None,sub_category='invalid'),changed_by='synthetic')
        with self.assertRaises(KnowledgeUpdateFailure):self.coordinator(embed=lambda text:(_ for _ in ()).throw(RuntimeError('synthetic'))).update(
            chunk_id=1,prepare_content=self.prepare(main_category='new'),changed_by='synthetic')
        self.assertEqual(self.state.content,CONTENT)
        self.assertEqual(self.vectors.upsert_count,0)

    def test_qdrant_compensation_and_post_commit_failures_keep_taxonomy_consistency(self):
        self.vectors.fail_confirmation=True
        with self.assertRaises(KnowledgeUpdateFailure):self.coordinator().update(chunk_id=1,
            prepare_content=self.prepare(main_category='new'),changed_by='synthetic')
        self.assertEqual(self.state.content,CONTENT)
        self.assertEqual(self.vectors.point.payload['content'],CONTENT)
        self.vectors.fail_restore=True
        with self.assertRaises(KnowledgeUpdateFailure) as raised:self.coordinator().update(chunk_id=1,
            prepare_content=self.prepare(main_category='new'),changed_by='synthetic')
        self.assertTrue(raised.exception.repair_required)

    def test_sql_stage_versions_revision_and_embedding_lineage(self):
        repository=PsycopgKnowledgeRepository(lambda:None)
        repository._cursor=Mock(rowcount=1);repository._document_id=7
        repository.stage(chunk_id=1,content=CONTENT,vector=[1,2],changed_by='synthetic',changed_at='synthetic-time')
        calls=repository._cursor.execute.call_args_list
        self.assertEqual(len(calls),4)
        self.assertEqual(calls[0].args[1][0],CONTENT)
        self.assertIn('UPDATE embeddings',calls[1].args[0])
        self.assertNotIn('model_name =',calls[1].args[0])
        self.assertEqual(calls[2].args[1][1],CONTENT)
        self.assertIn('revision + 1',calls[3].args[0])

    def test_revision_change_refreshes_another_workers_corpus_cache(self):
        from utils.revision_cache import RevisionAwareCache
        other_worker=RevisionAwareCache()
        def corpus():return other_worker.get_or_build(('synthetic-FAQ',),len(self.state.versions),lambda:self.state.content)
        self.assertEqual(corpus(),CONTENT)
        self.coordinator().update(chunk_id=1,prepare_content=self.prepare(main_category='UniqueTaxon'),changed_by='synthetic')
        self.assertIn('UniqueTaxon',corpus())
        self.assertEqual(self.cache.calls,1)


class TaxonomyLexicalTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_category_is_searchable_in_actual_bm25_without_changing_depths(self):
        from utils.persian_hybrid_search import PersianHybridSearch,PersianTextProcessor
        from utils.revision_cache import RevisionAwareCache
        from tests.rrf_fixtures import InlineRunner
        search=PersianHybridSearch.__new__(PersianHybridSearch)
        search._closed=False;search._blocking_runner=InlineRunner()
        search.processor=PersianTextProcessor(use_stemming=False)
        search._processor_lock=threading.Lock();search._bm25_cache=RevisionAwareCache()
        content=compose_faq(QUESTION,ANSWER,{'main_category':'UniqueTaxon','sub_category':'review'})
        corpus={'1':{'text':content,'document_name':'synthetic-FAQ'},
            '2':{'text':'question: Other topic\nanswer: unrelated fact','document_name':'synthetic-FAQ'},
            '3':{'text':'question: Different topic\nanswer: separate fact','document_name':'synthetic-FAQ'}}
        search.chunk_fetcher=lambda docs:corpus
        search.chunk_revision_fetcher=lambda docs:'synthetic-revision-2'
        async def dense(query,docs,top_k):return {}
        search._semantic_search=dense
        rows=await search.search('UniqueTaxon',allowed_docs=['synthetic-FAQ'])
        self.assertEqual([r.doc_id for r in rows],['1'])
        self.assertGreater(rows[0].bm25_score,0)
        self.assertEqual(rows[0].content,content)


class FaqApiCreateTests(unittest.TestCase):
    setUp=create_fixtures.ChunkCreateTests.setUp
    execute=create_fixtures.ChunkCreateTests.execute
    fetchone=create_fixtures.ChunkCreateTests.fetchone
    query=create_fixtures.ChunkCreateTests.query
    def test_taxonomy_reaches_every_create_representation(self):
        for fields in ({'main_category':'synthetic','sub_category':'review'},{'main_category':'synthetic'},{}):
            self.queries.clear()
            result=kb_manager.api_create_chunk(kb_manager.ChunkCreatePayload(document_id=self.document_id,
                question=QUESTION,answer=ANSWER,is_qa=True,**fields))
            content=self.query('INSERT INTO chunks')[1][1]
            self.assertEqual(parse_faq_content(content).main_category,fields.get('main_category'))
            self.assertEqual(self.query('INSERT INTO chunk_versions')[1][1],content)
            self.assertEqual(self.main.qdrant_client.upsert.call_args.kwargs['points'][0].payload['content'],content)
            encoded=self.search.embed_documents_sync.call_args.args[0][0]
            self.assertIn('First synthetic fact',encoded)
            self.assertRegex(encoded,r'14\s*:\s*00')
            if fields.get('main_category'):self.assertRegex(encoded,r'question\s+category\s*:\s*synthetic')

    def test_legacy_creation_and_raw_submission_compatibility(self):
        kb_manager.api_create_chunk(kb_manager.ChunkCreatePayload(document_id=self.document_id,question=QUESTION,
            answer=ANSWER+'\nquestion category: synthetic. sub_category: review',is_qa=True))
        self.assertEqual(parse_faq_content(self.query('INSERT INTO chunks')[1][1]).sub_category,'review')
        self.queries.clear()
        raw='Raw\nquestion category: literal'
        kb_manager.api_create_chunk(kb_manager.ChunkCreatePayload(document_id=self.document_id,answer=raw,is_qa=False,
            main_category='ignored',sub_category='ignored'))
        self.assertEqual(self.query('INSERT INTO chunks')[1][1],raw)

    def test_conflicting_legacy_create_is_422_before_embedding_or_writes(self):
        with self.assertRaises(HTTPException) as raised:kb_manager.api_create_chunk(kb_manager.ChunkCreatePayload(
            document_id=self.document_id,question=QUESTION,answer=ANSWER+'\nquestion category: one\nquestion category: two',is_qa=True))
        self.assertEqual(raised.exception.status_code,422)
        self.search.embed_documents_sync.assert_not_called()
        self.main.qdrant_client.upsert.assert_not_called()
