"""Configurable audit retrieval depths and entry budget; synthetic fixtures only."""
from __future__ import annotations
import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from knowledge_audit.privacy import AuditError
from knowledge_audit.settings import CAPABILITIES, load_coverage_settings
from tests.test_answering_service import ImmediateRunner
from tests.test_knowledge_coverage_access_jobs import audit_runtime, coverage_staging, enabled_coverage  # noqa: F401
from tests.test_knowledge_coverage_pipeline import LabeledModel, Retrieval, input_dataset, snapshot
from tests.test_web_auth import csrf, login, setup  # noqa: F401

DEPTH_KEYS = {'KNOWLEDGE_COVERAGE_INITIAL_DEPTH': '100', 'KNOWLEDGE_COVERAGE_BROADER_DEPTH': '200',
              'KNOWLEDGE_COVERAGE_INITIAL_ENTRIES': '30', 'KNOWLEDGE_COVERAGE_MAX_ENTRY_BUDGET': '120'}


def test_defaults_keep_the_settings_manifest_unchanged():
    settings = load_coverage_settings({})
    assert (settings.initial_depth, settings.broader_depth, settings.initial_entries, settings.max_entry_budget) == (150, 300, 50, 300)
    manifest = settings.manifest()
    assert manifest['initial_depths'] == [150] * 3 and manifest['expanded_depths'] == [300] * 3
    assert manifest['initial_entries'] == 50 and manifest['maximum_distinct_entries'] == 300
    assert manifest['schema'] == 'coverage-settings-5'


def test_overrides_are_reflected_and_orderings_validated():
    settings = load_coverage_settings(DEPTH_KEYS)
    assert (settings.initial_depth, settings.broader_depth, settings.initial_entries, settings.max_entry_budget) == (100, 200, 30, 120)
    manifest = settings.manifest()
    assert manifest['initial_depths'] == [100] * 3 and manifest['expanded_depths'] == [200] * 3
    assert manifest['initial_entries'] == 30 and manifest['maximum_distinct_entries'] == 120
    assert set(manifest) == set(load_coverage_settings({}).manifest())
    for bad in ({'KNOWLEDGE_COVERAGE_INITIAL_DEPTH': '40', 'KNOWLEDGE_COVERAGE_INITIAL_ENTRIES': '41'},
                {'KNOWLEDGE_COVERAGE_INITIAL_DEPTH': '200', 'KNOWLEDGE_COVERAGE_BROADER_DEPTH': '200'},
                {'KNOWLEDGE_COVERAGE_INITIAL_DEPTH': '250', 'KNOWLEDGE_COVERAGE_BROADER_DEPTH': '200'}):
        with pytest.raises(AuditError, match='^invalid_coverage_depths$'):
            load_coverage_settings(bad)
    with pytest.raises(AuditError, match='^invalid_coverage_integer$'):
        load_coverage_settings({'KNOWLEDGE_COVERAGE_BROADER_DEPTH': '1001'})


class RecordingRetrieval(Retrieval):
    def __init__(self, *args, initial_depth, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_depth, self.depths = initial_depth, []

    async def fetch(self, query, *, production=False, depth=None, documents=None):
        await self.check()
        if not production:
            self.depths.append(depth)
        ids = self.production if production else self.initial if depth == self.initial_depth else self.expanded
        metric = {'candidate_ids': ids, 'candidate_count': len(ids), 'selected_ids': ids,
                  'purpose': 'production_baseline' if production else 'initial_audit' if depth == self.initial_depth else 'broader_audit',
                  'depths': [50] * 3 if production else [depth] * 3}
        self.metrics.append(metric)
        return metric


def configured_evaluator(snap, model, retrieval, budget):
    from knowledge_audit.pipeline import CoverageEvaluator
    from knowledge_audit.preparation import QueryPreparer
    from knowledge_audit.privacy import Redactor
    from tests.test_answering_service import Classifier, Processor, Rewriter
    prep = QueryPreparer(Processor(), ImmediateRunner(), Rewriter(result='Approval duration and cutoff?'), Classifier())
    return CoverageEvaluator(snapshot=snap, model=model, retrieval=retrieval, preparer=prep,
        redactor=Redactor(b'synthetic-only-private-key-1234567890'), dataset=input_dataset(), entry_budget=budget,
        initial_depth=100, broader_depth=200, max_entry_budget=120)


def test_pipeline_uses_configured_depths_and_budget_ceiling():
    snap = snapshot({'1': 'Duration is two days.', '2': 'Unrelated.', '3': 'Still unrelated.'})
    retrieval = RecordingRetrieval([], ['1', '2'], ['2', '1', '3'], initial_depth=100)
    engine = configured_evaluator(snap, LabeledModel(snap, {'1': ['a1']}), retrieval, 120)
    event = engine.dataset.selected[0]
    row = asyncio.run(engine.evaluate(event, {'source_row_id': event.source_row_id, 'source_record_ordinal': event.ordinal}))
    assert row['outcome'] == 'possible_partial_gap'
    assert retrieval.depths == [100, 200]
    assert row['evaluation_scope']['initial_depths'] == [100] * 3
    assert row['evaluation_scope']['broader_depths'] == [200] * 3
    assert row['evaluation_scope']['distinct_entry_budget'] == 120
    assert configured_evaluator(snap, LabeledModel(snap, {}), retrieval, None).entry_budget == 120
    with pytest.raises(AuditError, match='^invalid_entry_budget$'):
        configured_evaluator(snap, LabeledModel(snap, {}), retrieval, 121)


def test_retrieval_keeps_configured_initial_entries_and_rejects_other_depths(monkeypatch):
    from knowledge_audit.retrieval import AuditRetrieval
    snap = snapshot({str(i): f'Full synthetic answer {i}.' for i in range(1, 61)})
    candidates = [SimpleNamespace(doc_id=r['chunk_id'], content=r['content']) for r in snap['records']]
    calls = []
    async def retrieve(query, **kwargs):
        calls.append(kwargs); return candidates
    async def rerank(query, records, top_k):
        return list(reversed(records))[:top_k]
    rag = SimpleNamespace(retrieve=retrieve, search_engine=SimpleNamespace(rerank_search_results=rerank))
    reader = AuditRetrieval(rag, snap, ImmediateRunner(), None, initial_depth=100, broader_depth=200, initial_entries=30)
    async def check():
        pass
    reader.check = check
    async def run():
        initial = await reader.fetch('synthetic query')
        broader = await reader.fetch('synthetic query', depth=200)
        assert len(initial['selected_ids']) == 30 and initial['purpose'] == 'initial_audit' and initial['depths'] == [100] * 3
        assert len(broader['selected_ids']) == 60 and broader['purpose'] == 'broader_audit'
        for depth in (150, 300, 99):
            with pytest.raises(AuditError, match='^invalid_audit_depth$'):
                await reader.fetch('synthetic query', depth=depth)
    asyncio.run(run())
    assert [c['top_k'] for c in calls] == [100, 200]
    assert calls[0]['bm25_candidate_limit'] == 100 and calls[1]['semantic_candidate_limit'] == 200


def test_run_started_under_other_depths_is_identity_drift(monkeypatch):
    from knowledge_audit.service import build_engine
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED', 'true'); monkeypatch.setenv('ENVIRONMENT', 'staging')
    settings = load_coverage_settings({})
    meta = {'settings': {**settings.manifest(), 'initial_depths': [100] * 3}}
    with pytest.raises(AuditError, match='^audit_runtime_identity_drift$'):
        asyncio.run(build_engine(None, meta, settings, answering=None, runner=None, limiter=None))


def test_api_entry_budget_defaults_to_and_is_bounded_by_configured_maximum(audit_runtime, setup, monkeypatch):
    store, d, s, meta, jobs = audit_runtime
    settings = replace(load_coverage_settings({}), max_entry_budget=120)
    monkeypatch.setattr(main.app.state, 'coverage_runtime', (settings, store, jobs), raising=False)
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_MAX_ENTRY_BUDGET', '120')
    setup.users[1]['role'] = 'admin'
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS', json.dumps({'1': sorted(CAPABILITIES)}))
    body = {'dataset_id': d['dataset_id'], 'snapshot_id': s['snapshot_id'], 'row_ids': list(meta['row_ids'][:1]),
            'documents': ['Synthetic_FAQ']}
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        page = client.get('/knowledge-coverage'); assert page.status_code == 200
        assert 'id="coverageBudget" type="number" min="1" max="120" value="120"' in page.text
        rejected = client.post('/api/knowledge-coverage/runs', json={**body, 'entry_budget': 121, 'idempotency_key': 'synthetic_depth_rejected'}, headers=csrf(client))
        assert rejected.status_code == 409 and rejected.json()['detail'] == 'invalid_entry_budget'
        started = client.post('/api/knowledge-coverage/runs', json={**body, 'idempotency_key': 'synthetic_depth_started'}, headers=csrf(client))
        assert started.status_code == 202, started.text
        assert started.json()['settings']['entry_budget'] == 120
