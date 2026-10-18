"""F7: a question changed by redaction gets no certain production-reachability claim."""
from __future__ import annotations

import asyncio
import csv
import io
import json

import pytest

import tests.test_knowledge_coverage_pipeline as pipeline_tests
from knowledge_audit.export import coverage_export
from knowledge_audit.pipeline import BLOCKING_CODES, NOTE_CODES, RESIDUAL_CODES, SEARCH_CODES
from knowledge_audit.preparation import QueryPreparer, prepare_dataset
from knowledge_audit.recommendations import eligibility
from knowledge_audit.settings import load_coverage_settings
from tests.test_answering_service import Classifier, ImmediateRunner, Processor, Rewriter
from tests.test_knowledge_audit_a1 import dataset, redactor, t  # noqa: F401  (redactor is a fixture)
from tests.test_knowledge_coverage_pipeline import LabeledModel, Retrieval, evaluate, input_dataset, snapshot

QUESTION = 'What is the approval duration and cutoff?'
# Synthetic card-like digits; the audit redactor scrubs any such run.
CARD_QUESTION = 'What is the approval duration and cutoff for card 1234567890123456?'
NEW_CODES = ('production_reachability_unresolved', 'redaction_changed_production_query')
META = lambda snap: {'state': 'completed', 'snapshot_id': snap['snapshot_id']}


@pytest.fixture
def marked(monkeypatch):
    """Make every prepared row carry one redaction code, as the real preparer would."""
    def mark(code):
        class Marked(QueryPreparer):
            async def prepare(self, *args, **kwargs):
                result = await super().prepare(*args, **kwargs)
                if result['preparation_status'] in {'prepared', 'uncertain_preparation'}:
                    result['uncertainty_codes'].append(code)
                    result['preparation_status'] = 'uncertain_preparation'
                return result
        monkeypatch.setattr(pipeline_tests, 'QueryPreparer', Marked)
    return mark


def reachable(question=QUESTION):
    snap = snapshot({'1': 'Approval takes two working days. Deadline is 18:00.'})
    row = evaluate(snap, LabeledModel(snap, {'1': ['a1', 'a2']}), Retrieval(['1'], ['1']),
                   dataset=input_dataset((question,)))[0]
    return row, snap


def not_reachable(question=QUESTION):
    # Production sees only the duration entry; the audit also finds the full one.
    snap = snapshot({'1': 'Approval takes two working days. Deadline is 18:00.', '2': 'Approval takes two working days.'})
    row = evaluate(snap, LabeledModel(snap, {'1': ['a1', 'a2'], '2': ['a1']}), Retrieval(['2'], ['1', '2']),
                   dataset=input_dataset((question,)))[0]
    return row, snap


def gap(question='What is the fee?'):
    snap = snapshot({'1': 'Unrelated synthetic policy.'})
    row = evaluate(snap, LabeledModel(snap, {}, aspects=1), Retrieval(['1'], ['1']),
                   dataset=input_dataset((question,)))[0]
    return row, snap


def assert_covered_but_uncertain(row):
    assert row['outcome'] == 'needs_review' and row['processing_status'] == 'needs_review'
    assert row['production_reachability'] == 'uncertain'
    assert row['coverage_status'] == 'full' and row['verification_result'] == 'accepted'
    assert row['supporting_faq_ids'] and row['stopping_reason'] == 'verified_full'
    assert all(row['review_codes'].count(code) == 1 for code in NEW_CODES)


def test_covered_reachable_with_redacted_query_goes_to_review():
    row, _ = reachable(CARD_QUESTION)
    assert 'redaction_changed_query' in row['uncertainty_codes']
    assert row['production_context_sufficiency'] == 'full'
    assert_covered_but_uncertain(row)
    assert row['supporting_faq_ids'] == ['1']


def test_covered_not_reachable_with_redacted_rewrite_goes_to_review(marked):
    marked('redaction_changed_rewrite')
    row, _ = not_reachable()
    assert row['production_context_sufficiency'] == 'partial'
    assert_covered_but_uncertain(row)


def test_gap_with_redacted_history_goes_to_review_and_is_ineligible(marked):
    marked('redaction_changed_history')
    row, snap = gap()
    assert row['outcome'] == 'needs_review' and row['processing_status'] == 'needs_review'
    assert row['production_reachability'] == 'uncertain'
    assert row['review_codes'].count('redaction_changed_production_query') == 1
    assert 'production_reachability_unresolved' not in row['review_codes']
    result = eligibility(row, META(snap))
    assert result['eligible'] is False
    assert {'context_or_redaction_unresolved', 'unresolved_evaluation_issue'} <= set(result['reason_codes'])


def test_needs_review_row_keeps_its_codes_and_gains_the_redaction_code():
    entries = {str(i): ('VIP only.' if i == 1 else 'Standard only.' if i == 6 else 'Unrelated.') for i in range(1, 7)}
    snap = snapshot(entries)
    model = LabeledModel(snap, {'1': ['a1'], '6': ['a2']}, conflicts=True)
    row = evaluate(snap, model, Retrieval([], list(entries)), dataset=input_dataset((CARD_QUESTION,)))[0]
    assert row['outcome'] == 'needs_review' and row['coverage_status'] == 'uncertain'
    assert 'incompatible_conditions' in row['review_codes']
    assert row['review_codes'].count('redaction_changed_production_query') == 1
    assert row['production_reachability'] == 'uncertain'


@pytest.mark.parametrize('setup,outcome,reachability', [
    (reachable, 'covered_reachable', 'sufficient'),
    (not_reachable, 'covered_not_reachable', 'insufficient'),
    (gap, 'possible_gap', 'unknown')])
def test_rows_without_redaction_are_unchanged(setup, outcome, reachability):
    row, _ = setup()
    assert not any(c.startswith('redaction_changed') for c in row['uncertainty_codes'])
    assert row['outcome'] == outcome and row['production_reachability'] == reachability
    assert not set(NEW_CODES) & set(row['review_codes'])


def prepared(tmp_path, redactor, rows):  # noqa: F811
    data = dataset(tmp_path, redactor, rows)
    preparer = QueryPreparer(Processor(), ImmediateRunner(), Rewriter(result='What is the card shipping duration?'), Classifier())
    return asyncio.run(prepare_dataset(data, preparer, redactor, model_limit=len(rows)))[-1]


CURRENT = ['What is the card shipping duration?', 'a', t(2), 'user']


def test_redacted_prior_turn_marks_the_rewrite(tmp_path, redactor):  # noqa: F811
    result = prepared(tmp_path, redactor, [['Card shipping, my mobile is 09121234567', 'a', t(1), 'user'], CURRENT])
    assert result['rewrite_status'] == 'rewritten'
    assert 'redaction_changed_history' in result['uncertainty_codes']
    assert result['preparation_status'] == 'uncertain_preparation'


def test_plain_prior_turn_does_not_mark_the_rewrite(tmp_path, redactor):  # noqa: F811
    result = prepared(tmp_path, redactor, [['Card shipping question', 'a', t(1), 'user'], CURRENT])
    assert result['rewrite_status'] == 'rewritten'
    assert 'redaction_changed_history' not in result['uncertainty_codes']
    assert result['preparation_status'] == 'prepared'


def test_no_prior_history_does_not_mark_the_rewrite(tmp_path, redactor):  # noqa: F811
    result = prepared(tmp_path, redactor, [CURRENT])
    assert result['rewrite_status'] == 'no_prior_history'
    assert 'redaction_changed_history' not in result['uncertainty_codes']


def test_export_shows_uncertain_reachability_and_both_codes(tmp_path):
    from tests.test_knowledge_coverage_access_jobs import seed
    row, _ = reachable(CARD_QUESTION)
    store, _, _, meta, _, exporter, _ = seed(tmp_path)
    rows = store.rows(meta['run_id'], 1)
    rows[0].update({k: row[k] for k in ('outcome', 'processing_status', 'coverage_status', 'production_reachability',
                                        'verification_result', 'review_codes')})
    body, _ = coverage_export(meta, rows, exporter, evidence_visible=True)
    parsed = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'), newline='')))
    assert parsed[0]['production_reachability'] == 'uncertain' and parsed[0]['outcome'] == 'needs_review'
    assert set(NEW_CODES) <= set(json.loads(parsed[0]['review_codes']))


def test_new_review_codes_are_not_view_codes():
    for code in NEW_CODES:
        assert not any(code in codes for codes in (BLOCKING_CODES, RESIDUAL_CODES, SEARCH_CODES, NOTE_CODES))


def test_manifest_records_the_reachability_policy():
    assert load_coverage_settings({}).manifest()['reachability_policy_version'] == 'redaction-reachability-1'
