"""Frozen synthetic score providers; use production BM25 selection and fusion."""
import asyncio
from types import SimpleNamespace
from tests.rrf_fixtures import InlineRunner, case_from_ids


def expanded_case():
    sparse = [f'lex-{i:03}' for i in range(1, 301)]
    dense = [f'dense-{i:03}' for i in range(1, 301)]
    sparse[119] = dense[49] = 'lex-relevant'
    sparse[49] = dense[119] = 'dense-relevant'
    case = case_from_ids(sparse, dense)
    case['id'] = 'synthetic-depth-reference'
    case['query'] = 'How long does fictional review take, and when does processing begin for requests after 14:00?'
    case['relevant_ids'] = ['lex-relevant', 'dense-relevant']
    # Independently labeled complementary source facts, not scores-as-labels.
    case['chunks']['lex-relevant']['text'] = 'question: synthetic review duration\nanswer: Fictional review takes two working days.\nquestion category: synthetic. sub_category: review'
    case['chunks']['dense-relevant']['text'] = 'question: synthetic review cutoff\nanswer: Fictional requests after 14:00 start the next working day.\nquestion category: synthetic. sub_category: review'
    return case


def depth_search(case):
    from utils.persian_hybrid_search import PersianHybridSearch
    search = PersianHybridSearch.__new__(PersianHybridSearch)
    search._closed = False
    search._blocking_runner = InlineRunner()
    ids = [r['id'] for r in case['sparse']]
    scores = [r['score'] for r in case['sparse']]
    model = SimpleNamespace(get_scores=lambda tokens: scores)
    search._get_or_build_bm25 = lambda docs: (model, ids, case['chunks'])
    search._process_query = lambda query: [query]
    search._normalise_query = lambda query: query
    search.requested_dense_depths = []
    search.allowed_scopes = []

    async def dense(query, docs, top_k):
        search.requested_dense_depths.append(top_k)
        search.allowed_scopes.append(list(docs))
        await asyncio.sleep(0)
        return {r['id']: r['score'] for r in case['dense'][:top_k]}

    search._semantic_search = dense
    return search
