"""F6: a proof is accepted only when verification agrees in both evidence orders."""
from __future__ import annotations
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from knowledge_audit.pipeline import BLOCKING_CODES, NOTE_CODES, RESIDUAL_CODES, SEARCH_CODES, CoverageEvaluator
from knowledge_audit.preparation import QueryPreparer
from knowledge_audit.privacy import AuditError, Redactor
from knowledge_audit.schemas import SCHEMAS
from knowledge_audit.settings import CoverageSettings, load_coverage_settings
from tests.test_answering_service import Processor, ImmediateRunner, Rewriter, Classifier
from tests.test_coverage_conflict_verdicts import ENTRIES, ConflictModel
from tests.test_knowledge_coverage_pipeline import snapshot, LabeledModel, Retrieval, input_dataset

TWO_ENTRIES = {'1': 'Approval takes two working days.', '2': 'The deadline is 18:00.'}
OTHER_CONFLICT = 'Entry 1 says a different deadline applies.'


def evaluator(snap, model, retrieval, passes=2):
    prep = QueryPreparer(Processor(), ImmediateRunner(), Rewriter(result='Approval duration and cutoff?'), Classifier())
    return CoverageEvaluator(snapshot=snap, model=model, retrieval=retrieval, preparer=prep,
        redactor=Redactor(b'synthetic-only-private-key-1234567890'), dataset=input_dataset(), verification_passes=passes)


def run(engine):
    event = engine.dataset.selected[0]
    return asyncio.run(engine.evaluate(event, {'source_row_id': event.source_row_id, 'source_record_ordinal': event.ordinal}))


def verification_calls(model):
    return [data for role, data in model.calls if role == 'verification']


def canonical(data):
    return [s['support_id'] for s in data['supports']] == sorted(s['support_id'] for s in data['supports'])


class OrderSensitive(LabeledModel):
    """Accepts the canonical evidence order and rejects any other order."""
    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'verification' and not canonical(data):
            required = [f'a{i}' for i in range(1, self.aspects + 1)]
            value = {**value, 'verdict': 'rejected', 'supported_aspect_ids': [], 'unresolved_aspect_ids': required}
        return SCHEMAS[role].model_validate(value).model_dump()


def two_entry_row(model_class=LabeledModel, passes=2, production=(), **kwargs):
    snap = snapshot(TWO_ENTRIES)
    model = model_class(snap, {'1': ['a1'], '2': ['a2']}, **kwargs)
    engine = evaluator(snap, model, Retrieval(list(production), list(TWO_ENTRIES)), passes)
    return run(engine), model, engine


def test_acceptance_that_depends_on_order_goes_to_review():
    row, model, _ = two_entry_row(OrderSensitive)
    assert row['outcome'] == 'needs_review' and row['coverage_status'] == 'uncertain'
    assert {'verification_order_unstable', 'verification_unresolved'} <= set(row['review_codes'])
    first, second = verification_calls(model)
    for key in ('supports', 'source_evidence', 'observed_conflicts'):
        assert second[key] == first[key][::-1]
    assert len(first['supports']) == 2 and len(first['source_evidence']) == 2
    assert {k: v for k, v in second.items() if k not in {'supports', 'source_evidence', 'observed_conflicts'}} == \
           {k: v for k, v in first.items() if k not in {'supports', 'source_evidence', 'observed_conflicts'}}
    assert [v['origin'] for v in row['verifications']] == ['initial:1', 'initial:1:reversed']
    assert [v['verdict'] for v in row['verifications']] == ['accepted', 'rejected']
    assert len({v['bundle_id'] for v in row['verifications']}) == 1


def test_acceptance_in_both_orders_keeps_the_covered_outcome():
    row, model, _ = two_entry_row(production=TWO_ENTRIES)
    assert row['outcome'] == 'covered_reachable' and row['coverage_status'] == 'full'
    assert row['verification_result'] == 'accepted' and row['review_codes'] == []
    assert len(verification_calls(model)) == 2
    assert [v['origin'] for v in row['verifications']] == ['production:1', 'production:1:reversed']
    row, model, _ = two_entry_row()
    assert row['outcome'] == 'covered_not_reachable' and len(verification_calls(model)) == 2


class ReversedContradiction(ConflictModel):
    """Two conflicts; the verifier accepts both orders but contradicts in reversed order."""
    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'batch' and value['conflicts']:
            value['conflicts'] = [value['conflicts'][0], OTHER_CONFLICT]
        if role == 'verification' and data['observed_conflicts']:
            ids = [c['conflict_id'] for c in data['observed_conflicts']]
            flipped = ids != sorted(ids)
            value['conflict_assessments'] = [{'conflict_id': cid, 'assessment': 'contradicts' if flipped and n == 0 else 'not_applicable',
                                              'explanation': 'Synthetic conflict assessment.'} for n, cid in enumerate(ids)]
        return SCHEMAS[role].model_validate(value).model_dump()


def test_reversed_pass_checks_every_conflict_verdict():
    snap = snapshot(ENTRIES)
    model = ReversedContradiction(snap, {'3': ['a1', 'a2']})
    row = run(evaluator(snap, model, Retrieval([], list(ENTRIES))))
    assert row['coverage_status'] != 'full' and row['outcome'] == 'needs_review'
    assert {'conflict_contradicts_proof', 'verification_order_unstable', 'verification_unresolved'} <= set(row['review_codes'])
    calls = [d for d in verification_calls(model) if d['observed_conflicts']]
    first, second = calls[0], calls[1]
    assert [c['conflict_id'] for c in first['observed_conflicts']] == ['c1', 'c2']
    assert second['observed_conflicts'] == first['observed_conflicts'][::-1]
    assert second['source_evidence'] == first['source_evidence'][::-1] and len(first['source_evidence']) == 3
    reversed_record = next(v for v in row['verifications'] if v['origin'] == 'conflict_reverification:reversed')
    assert reversed_record['verdict'] == 'rejected'


def test_single_pass_matches_the_previous_behaviour():
    single, model, _ = two_entry_row(passes=1)
    assert len(verification_calls(model)) == 1
    double, _, _ = two_entry_row(passes=2)
    volatile = {'duration_ms', 'verifications', 'model_metrics'}
    assert {k: v for k, v in single.items() if k not in volatile} == {k: v for k, v in double.items() if k not in volatile}
    assert single['verifications'] == [v for v in double['verifications'] if not v['origin'].endswith(':reversed')]
    row, model, _ = two_entry_row(OrderSensitive, passes=1)
    assert row['outcome'] == 'covered_not_reachable' and len(verification_calls(model)) == 1


def test_primary_rejection_makes_no_second_call():
    row, model, _ = two_entry_row(verification='rejected')
    assert row['outcome'] == 'needs_review' and row['verification_result'] == 'rejected'
    assert len(verification_calls(model)) == 1
    assert not any(v['origin'].endswith(':reversed') for v in row['verifications'])
    assert 'verification_order_unstable' not in row['review_codes']


def test_cached_proof_makes_no_model_call():
    row, model, engine = two_entry_row(production=TWO_ENTRIES)
    calls, records = len(model.calls), len(engine.verifications)
    witness = row['audit_assessment']['witness']
    question = row['standalone_query_redacted']
    verdict = asyncio.run(engine.verify(question, row['requested_aspects'], witness, [], 'repeat'))
    assert verdict['verdict'] == 'accepted'
    assert len(model.calls) == calls and len(engine.verifications) == records


@pytest.mark.parametrize('raw', ['3', '0', 'two'])
def test_invalid_pass_count_is_refused(raw):
    with pytest.raises(AuditError, match='^invalid_verification_passes$'):
        load_coverage_settings({'KNOWLEDGE_COVERAGE_VERIFICATION_PASSES': raw})
    settings = load_coverage_settings({})
    for bad in (3, 0, True, '2'):
        with pytest.raises(AuditError, match='^invalid_verification_passes$'):
            replace(settings, verification_passes=bad)
    snap = snapshot(TWO_ENTRIES)
    with pytest.raises(AuditError, match='^invalid_verification_passes$'):
        evaluator(snap, LabeledModel(snap, {}), Retrieval([], []), 3)


def test_manifest_pins_passes_and_policy():
    two = load_coverage_settings({}).manifest()
    one = load_coverage_settings({'KNOWLEDGE_COVERAGE_VERIFICATION_PASSES': '1'}).manifest()
    assert (two['verification_passes'], two['verification_policy']) == (2, 'order-permuted-2')
    assert (one['verification_passes'], one['verification_policy']) == (1, 'single-pass-1')
    assert {k for k in two if two[k] != one[k]} == {'verification_passes', 'verification_policy'}
    assert CoverageSettings.__dataclass_fields__['verification_passes'].default == 2


class Captured(Exception):
    pass


def patched_engine_inputs(monkeypatch):
    from knowledge_audit import service
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED', 'true'); monkeypatch.setenv('ENVIRONMENT', 'staging')
    monkeypatch.setenv('TEI_RERANK_URL', 'http://localhost:7998'); monkeypatch.setenv('VLLM_URL', 'http://localhost:8000/v1')
    monkeypatch.setattr(service, 'confirm_staging', lambda **kwargs: None)
    monkeypatch.setattr('dotenv.dotenv_values', lambda path: {'TEI_RERANK_URL': 'http://localhost:7998'})
    async def capable(search):
        return None
    monkeypatch.setattr(service, '_require_reranker_capability', capable)
    class Model:
        def __init__(self, *args, **kwargs):
            self.serving = {'fixture': 'synthetic'}
        async def discover(self):
            pass
    class Reader:
        def __init__(self, *args, **kwargs):
            pass
        async def check(self):
            pass
    monkeypatch.setattr(service, 'AuditModel', Model)
    monkeypatch.setattr(service, 'AuditRetrieval', Reader)
    monkeypatch.setattr(service, 'QueryPreparer', SimpleNamespace(from_answering_service=lambda answering: object()))
    captured = {}
    def engine(**kwargs):
        captured.update(kwargs)
        raise Captured()
    monkeypatch.setattr(service, 'CoverageEvaluator', engine)
    store = SimpleNamespace(dataset=lambda did, owner: (SimpleNamespace(), object()),
                            snapshot=lambda sid, owner: {}, _path=lambda kind, rid: __import__('pathlib').Path('/nonexistent'))
    answering = SimpleNamespace(agent_service=SimpleNamespace(rag_system=SimpleNamespace(search_engine=None)))
    return service, captured, store, answering


@pytest.mark.parametrize('passes', [1, 2])
def test_build_engine_uses_the_pinned_pass_count(monkeypatch, passes):
    service, captured, store, answering = patched_engine_inputs(monkeypatch)
    settings = replace(load_coverage_settings({}), verification_passes=passes)
    meta = {'settings': {**settings.manifest(), 'entry_budget': 5, 'documents': ['Synthetic_FAQ']},
            'dataset_id': 'd_' + '0' * 32, 'snapshot_id': '0' * 64, 'owner_id': 0, 'run_id': 'r_' + '0' * 32,
            'execution_version': 'synthetic'}
    with pytest.raises(Captured):
        asyncio.run(service.build_engine(store, meta, settings, answering=answering, runner=ImmediateRunner(), limiter=None))
    assert captured['verification_passes'] == passes


def test_run_pinned_at_two_passes_cannot_resume_under_one(monkeypatch):
    from knowledge_audit.service import build_engine
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ENABLED', 'true'); monkeypatch.setenv('ENVIRONMENT', 'staging')
    meta = {'settings': load_coverage_settings({}).manifest()}
    settings = load_coverage_settings({'KNOWLEDGE_COVERAGE_VERIFICATION_PASSES': '1'})
    with pytest.raises(AuditError, match='^audit_runtime_identity_drift$'):
        asyncio.run(build_engine(None, meta, settings, answering=None, runner=None, limiter=None))
    # A run created before this step has no pinned pass count and cannot resume either.
    legacy = {'settings': {k: v for k, v in meta['settings'].items() if k not in {'verification_passes', 'verification_policy'}}}
    with pytest.raises(AuditError, match='^audit_runtime_identity_drift$'):
        asyncio.run(build_engine(None, legacy, load_coverage_settings({}), answering=None, runner=None, limiter=None))


def test_order_code_is_blocking_only():
    sets = (BLOCKING_CODES, RESIDUAL_CODES, SEARCH_CODES, NOTE_CODES)
    assert [('verification_order_unstable' in s) for s in sets] == [True, False, False, False]
