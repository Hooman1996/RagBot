"""F1/F16a: a proof counts only after every conflict in its view has an explicit verdict."""
from __future__ import annotations
import re
from pathlib import Path

import pytest

from knowledge_audit import pipeline
from knowledge_audit.pipeline import BLOCKING_CODES, NOTE_CODES, RESIDUAL_CODES, SEARCH_CODES, CoverageEvaluator
from knowledge_audit.preparation import QueryPreparer
from knowledge_audit.privacy import Redactor
from knowledge_audit.schemas import SCHEMAS
from tests.test_answering_service import Processor, ImmediateRunner, Rewriter, Classifier
from tests.test_knowledge_coverage_pipeline import snapshot, LabeledModel, Retrieval, evaluate, input_dataset

ENTRIES = {'1': 'Unrelated.', '2': 'The fee is waived for standard accounts.',
           '3': 'Standard accounts pay the fee. It takes two days.', '4': 'Unrelated.'}
CONFLICT = 'Entry 2 says the fee is waived for the same account type.'


class ConflictModel(LabeledModel):
    """The reproduction: a partial batch reports a conflict, another batch has the proof."""
    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'batch' and any(e['chunk_id'] == '2' for e in data['entries']):
            value['conflicts'] = [CONFLICT]
            value['coverage'] = 'partial'
        return SCHEMAS[role].model_validate(value).model_dump()


def verification_calls(model):
    return [data for role, data in model.calls if role == 'verification']


def reproduction(model_class=ConflictModel, **kwargs):
    snap = snapshot(ENTRIES)
    model = model_class(snap, {'3': ['a1', 'a2']}, **kwargs)
    return evaluate(snap, model, Retrieval([], list(ENTRIES)))[0], model


def view_codes(row):
    assessments = [row.get('audit_assessment', {})] + list(row.get('phase_assessments', {}).values())
    return {c for a in assessments for key in ('review_codes', 'resolved_review_codes', 'residual_review_codes')
            for c in a.get(key, [])}


def test_contradicting_conflict_blocks_the_proof():
    row, model = reproduction(conflict_assessment='contradicts')
    assert row['outcome'] == 'needs_review' and row['coverage_status'] == 'uncertain'
    assert {'evidence_conflict', 'conflict_contradicts_proof'} <= set(row['review_codes'])
    last = verification_calls(model)[-1]
    assert [c['kind'] for c in last['observed_conflicts']] == ['batch_conflict']
    assert last['observed_conflicts'][0] == {'conflict_id': 'c1', 'kind': 'batch_conflict', 'text': CONFLICT,
                                             'source_entry_ids': ['1', '2']}
    assert '2' in {e['chunk_id'] for e in last['source_evidence']}
    assert any(v['verdict'] == 'rejected' for v in row['verifications'])


@pytest.mark.parametrize('assessment', ['not_applicable', 'compatible'])
def test_assessed_conflict_lets_the_proof_stand(assessment):
    row, model = reproduction(conflict_assessment=assessment)
    assert row['outcome'] == 'covered_not_reachable' and row['coverage_status'] == 'full'
    assert row['review_codes'] == []
    assert 'evidence_conflict' in row['audit_assessment']['resolved_review_codes']
    assert row['audit_assessment']['conflict_assessments'][0]['assessment'] == assessment
    assert len(verification_calls(model)) == 2


class NoAssessments(ConflictModel):
    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'verification':
            value['conflict_assessments'] = []
        return value


def test_unassessed_conflict_is_undetermined():
    row, model = reproduction(NoAssessments)
    assert row['coverage_status'] == 'uncertain' and row['outcome'] == 'needs_review'
    assert 'conflict_undetermined' in row['review_codes']
    assert verification_calls(model)[-1]['observed_conflicts']


def bad_identity(ids):
    class BadIdentity(ConflictModel):
        async def call(self, role, data):
            value = await super().call(role, data)
            if role == 'verification' and data['observed_conflicts']:
                value['conflict_assessments'] = [{'conflict_id': cid, 'assessment': 'not_applicable',
                                                  'explanation': 'Synthetic.'} for cid in ids]
            return value
    return BadIdentity


@pytest.mark.parametrize('ids', [['c9'], ['c1', 'c1']])
def test_unknown_or_duplicate_conflict_id_is_an_error(ids):
    row, _ = reproduction(bad_identity(ids))
    assert row['outcome'] == 'error' and row['processing_status'] == 'failed'
    assert row['error_code'] == 'invalid_conflict_identity'


UNCERTAIN = 'Entry 1 may apply only to premium accounts.'


class UncertainSupport(LabeledModel):
    """Entry 1 gives an uncertain support for a1, which the witness in entry 3 relies on."""
    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'batch' and any(e['chunk_id'] == '1' for e in data['entries']):
            entry = next(e for e in data['entries'] if e['chunk_id'] == '1')
            value['supports'].append({'aspect_id': 'a1', 'entry_id': '1', 'citations': [{'snapshot_id': self.snap['snapshot_id'],
                'faq_entry_id': entry['faq_entry_id'], 'chunk_id': '1', 'sentence_number': 1}],
                'applicability': 'uncertain', 'conditions': [], 'dependencies': [], 'explanation': UNCERTAIN})
            value['coverage'] = 'uncertain'
        return SCHEMAS[role].model_validate(value).model_dump()


def test_uncertain_support_on_a_witness_aspect_needs_a_verdict():
    row, model = reproduction(UncertainSupport, conflict_assessment='cannot_determine')
    assert row['coverage_status'] == 'uncertain' and row['outcome'] == 'needs_review'
    assert 'conflict_undetermined' in row['review_codes']
    assert verification_calls(model)[-1]['observed_conflicts'] == [{'conflict_id': 'c1', 'kind': 'uncertain_support',
        'text': UNCERTAIN, 'source_entry_ids': ['1'], 'aspect_id': 'a1'}]
    row, _ = reproduction(UncertainSupport)
    assert row['coverage_status'] == 'full' and row['review_codes'] == []


def engine(snap, model):
    prep = QueryPreparer(Processor(), ImmediateRunner(), Rewriter(result='Synthetic?'), Classifier())
    return CoverageEvaluator(snapshot=snap, model=model, retrieval=Retrieval([], []), preparer=prep,
        redactor=Redactor(b'synthetic-only-private-key-1234567890'), dataset=input_dataset())


def test_uncertain_support_outside_the_witness_is_not_a_conflict():
    # An accepted proof covers every required aspect, so an off-witness aspect
    # only arises for the helper itself; check the aspect and entry rules there.
    snap = snapshot(ENTRIES)
    evaluator = engine(snap, LabeledModel(snap, {}))
    support = {'aspect_id': 'a2', 'entry_id': '1', 'applicability': 'uncertain', 'explanation': UNCERTAIN}
    batches = [{'entry_ids': ['1', '2'], 'result': {'conflicts': []}}]
    assert evaluator.view_conflicts(batches, [support], {'1', '2', '3'}, {'a1'}, {'3'}) == []
    assert evaluator.view_conflicts(batches, [support], {'1', '2', '3'}, {'a1', 'a2'}, {'1'}) == []
    assert len(evaluator.view_conflicts(batches, [support], {'1', '2', '3'}, {'a1', 'a2'}, {'3'})) == 1


class UncertainOtherBatch(LabeledModel):
    """An uncertain batch that gives no support the witness relies on."""
    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'batch' and not value['supports']:
            value['coverage'] = 'uncertain'
        return SCHEMAS[role].model_validate(value).model_dump()


def test_uncertain_batch_elsewhere_is_residual_not_resolved():
    row, model = reproduction(UncertainOtherBatch)
    assert row['outcome'] == 'covered_not_reachable' and row['review_codes'] == []
    assert row['residual_review_codes'] == ['batch_uncertain']
    assert 'batch_uncertain' not in row['audit_assessment']['resolved_review_codes']
    assert all(not data['observed_conflicts'] for data in verification_calls(model))


def test_residual_codes_do_not_block_a_verified_proof():
    snap = snapshot({'1': 'Oversized synthetic entry.', '3': 'Two days, cutoff 18:00.'})
    model = LabeledModel(snap, {'3': ['a1', 'a2']}, overflow_ids=['1'])
    row = evaluate(snap, model, Retrieval([], ['1', '3']))[0]
    assert row['outcome'] == 'covered_not_reachable' and row['coverage_status'] == 'full'
    assert row['review_codes'] == [] and row['residual_review_codes'] == ['entry_too_long']
    assert row['audit_assessment']['resolved_review_codes'] == []


def test_verification_overflow_reason_is_kept(monkeypatch):
    snap = snapshot({'1': 'Two days, cutoff 18:00.'})
    model = LabeledModel(snap, {'1': ['a1', 'a2']})
    fits = model.fits
    async def no_verification(role, data):
        return role != 'verification' and await fits(role, data)
    monkeypatch.setattr(model, 'fits', no_verification)
    row = evaluate(snap, model, Retrieval([], ['1']))[0]
    assert row['coverage_status'] == 'uncertain' and 'verification_token_overflow' in row['review_codes']
    assert not verification_calls(model)


class ManyConflicts(LabeledModel):
    """Six batches report 8+8+8+8+8+1 = 41 distinct conflicts."""
    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'batch':
            first = data['entries'][0]['chunk_id']
            value['conflicts'] = [f'Synthetic conflict {first}-{k}.' for k in range(1 if first == '11' else 8)]
        return SCHEMAS[role].model_validate(value).model_dump()


def test_conflict_cap_skips_verification():
    entries = {str(i): 'Duration is two days.' if i == 1 else 'Deadline is 18:00.' if i == 12 else 'Unrelated.'
               for i in range(1, 13)}
    snap = snapshot(entries)
    model = ManyConflicts(snap, {'1': ['a1'], '12': ['a2']})
    row = evaluate(snap, model, Retrieval([], list(entries)))[0]
    reconciliation = [data for role, data in model.calls if role == 'reconciliation']
    assert reconciliation and len(reconciliation[0]['observed_conflicts']) == 41
    assert [c['conflict_id'] for c in reconciliation[0]['observed_conflicts']] == [f'c{i}' for i in range(1, 42)]
    assert 'conflict_limit_exceeded' in row['review_codes'] and row['coverage_status'] == 'uncertain'
    assert verification_calls(model) == []


def test_duplicate_conflicts_are_removed_before_numbering():
    snap = snapshot(ENTRIES)
    evaluator = engine(snap, LabeledModel(snap, {}))
    batches = [{'entry_ids': ['1', '2'], 'result': {'conflicts': ['B.', 'A.', 'A.']}},
               {'entry_ids': ['2', '9'], 'result': {'conflicts': ['A.']}}]
    records = evaluator.view_conflicts(batches, [], {'1', '2'}, {'a1'}, set())
    assert [(r['conflict_id'], r['text'], r['source_entry_ids']) for r in records] == [
        ('c1', 'A.', ['1', '2']), ('c2', 'A.', ['2']), ('c3', 'B.', ['1', '2'])]


def test_every_view_code_belongs_to_exactly_one_set(monkeypatch):
    sets = (BLOCKING_CODES, RESIDUAL_CODES, SEARCH_CODES, NOTE_CODES)
    assert all(not (a & b) for i, a in enumerate(sets) for b in sets[i + 1:])
    source = Path(pipeline.__file__).read_text()
    body = source[source.index('    async def view('):source.index('    def apply_result(')]
    emitted = set(re.findall(r'(?:codes|residual)\.append\("([a-z_]+)"\)', body))
    emitted |= {c for group in re.findall(r'review_codes\.extend\(\[([^\]]*)\]\)', body) for c in re.findall(r'"([a-z_]+)"', group)}
    rows = [reproduction(conflict_assessment=a)[0] for a in ('contradicts', 'not_applicable', 'cannot_determine')]
    rows += [reproduction(NoAssessments)[0], reproduction(UncertainSupport, conflict_assessment='cannot_determine')[0],
             reproduction(UncertainOtherBatch)[0]]
    snap = snapshot({'1': 'Oversized synthetic entry.', '3': 'Two days, cutoff 18:00.'})
    rows.append(evaluate(snap, LabeledModel(snap, {'3': ['a1', 'a2']}, overflow_ids=['1']), Retrieval([], ['1', '3']))[0])
    emitted |= {c for row in rows for c in view_codes(row)}
    assert {'evidence_conflict', 'conflict_contradicts_proof', 'conflict_undetermined', 'conflict_limit_exceeded',
            'verification_token_overflow', 'entry_too_long', 'batch_uncertain'} <= emitted
    assert all(sum(code in s for s in sets) == 1 for code in emitted), sorted(emitted)
