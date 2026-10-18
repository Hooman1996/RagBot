"""F5: a ticket referral is evidence only for a contact question."""
from __future__ import annotations

import pytest

from knowledge_audit.pipeline import BLOCKING_CODES, NOTE_CODES, RESIDUAL_CODES, SEARCH_CODES
from knowledge_audit.recommendations import eligibility
from knowledge_audit.referrals import classify_aspect, is_referral_only
from knowledge_audit.settings import load_coverage_settings
from tests.test_knowledge_coverage_pipeline import snapshot, LabeledModel, Retrieval, evaluate, input_dataset
from utils.faq_fallback import FAQ_FALLBACK_FRAGMENT

REFERRAL = 'For more information please submit a ticket in the app.'
MIXED = 'کارمزد صدور کارت ۵۰۰۰۰ ریال است و برای اعتراض تیکت ثبت کنید.'
META = lambda snap: {'state': 'completed', 'snapshot_id': snap['snapshot_id']}


class DescribedModel(LabeledModel):
    """One aspect whose description decides its class."""
    def __init__(self, snap, labels, description, **kwargs):
        super().__init__(snap, labels, aspects=1, **kwargs)
        self.description = description

    async def call(self, role, data):
        value = await super().call(role, data)
        if role == 'aspects':
            value['aspects'][0]['description'] = self.description
        return value


def run(entries, labels, description, question, production=('1',), initial=('1',)):
    snap = snapshot(entries)
    model = DescribedModel(snap, labels, description)
    row = evaluate(snap, model, Retrieval(list(production), list(initial)), dataset=input_dataset((question,)))[0]
    return row, model, snap


def fee_referral():
    return run({'1': REFERRAL}, {'1': ['a1']}, 'Card issuance fee', 'What is the card issuance fee?')


def unclassified_referral():
    return run({'1': REFERRAL}, {'1': ['a1']}, 'Which branches offer this service', 'Which branches offer this service?')


def fee_referral_beside_fact():
    return run({'1': REFERRAL, '2': 'The card issuance fee is 50000 rials.'}, {'1': ['a1'], '2': ['a1']},
               'Card issuance fee', 'What is the card issuance fee?', production=('1', '2'), initial=('1', '2'))


def verification_calls(model):
    return [data for role, data in model.calls if role == 'verification']


@pytest.mark.parametrize('sentence', [FAQ_FALLBACK_FRAGMENT, 'برای اطلاعات بیشتر لطفا تیکت ثبت کنید.', REFERRAL,
                                      'لطفا با پشتیبانی تماس بگیرید.'])
def test_referral_sentences_are_referral_only(sentence):
    assert is_referral_only(sentence)


@pytest.mark.parametrize('sentence', [MIXED, 'Approval takes 2 days; contact support if it is late.',
                                      'شرایط دریافت وام در بخش تسهیلات آمده است؛ در صورت نیاز تیکت ثبت کنید.',
                                      'The fee is shown in the app.'])
def test_sentences_with_a_fact_or_without_a_referral_are_not(sentence):
    assert not is_referral_only(sentence)


@pytest.mark.parametrize('description,expected', [
    ('How to submit a support ticket', 'contact_procedure'), ('راه ارتباط با پشتیبانی', 'contact_procedure'),
    ('Card issuance fee', 'substantive_fact'), ('مدت زمان بررسی تیکت', 'substantive_fact'),
    ('Fee for submitting a complaint', 'substantive_fact'), ('Which branches offer this service', 'unclassified')])
def test_aspect_classes(description, expected):
    assert classify_aspect({'aspect_id': 'a1', 'description': description, 'conditions': []}) == expected


def test_referral_does_not_answer_a_fee_question():
    row, model, snap = fee_referral()
    assert row['coverage_status'] == 'unsupported' and row['outcome'] == 'possible_gap'
    assert 'referral_only_support' in row['residual_review_codes']
    assert 'referral_only_support' not in row['review_codes']
    assert verification_calls(model) == []
    batch = row['batch_results'][0]
    # The stored model output is kept; the support only moves out of the usable list.
    assert batch['result']['coverage'] == 'full' and batch['result']['supports']
    assert batch['supports'] == [] and batch['excluded_referral_supports'][0]['aspect_id'] == 'a1'
    # The note leaves a real gap exactly as eligible as it would be without it.
    plain = {**row, 'residual_review_codes': [c for c in row['residual_review_codes'] if c not in NOTE_CODES]}
    assert eligibility(row, META(snap)) == eligibility(plain, META(snap))


def test_note_is_kept_beside_a_verified_witness():
    row, model, _ = fee_referral_beside_fact()
    assert row['outcome'] == 'covered_reachable' and row['supporting_chunk_ids'] == ['2']
    assert 'referral_only_support' in row['residual_review_codes'] and row['review_codes'] == []
    assert all(s['entry_id'] == '2' for data in verification_calls(model) for s in data['supports'])


def test_referral_still_answers_a_contact_question():
    row, model, _ = run({'1': REFERRAL}, {'1': ['a1']}, 'How do I submit a complaint ticket?',
                        'How do I submit a complaint ticket?')
    assert row['coverage_status'] == 'full' and row['outcome'] == 'covered_reachable'
    assert row['verification_result'] == 'accepted' and verification_calls(model)
    assert 'referral_only_support' not in row['residual_review_codes']


def test_referral_for_an_unclassified_aspect_goes_to_review():
    row, _, snap = unclassified_referral()
    assert row['coverage_status'] == 'full' and row['outcome'] == 'needs_review'
    assert row['processing_status'] == 'needs_review'
    assert 'referral_support_unclassified' in row['review_codes']
    assert eligibility(row, META(snap))['eligible'] is False


def test_mixed_sentence_counts_as_evidence():
    row, model, _ = run({'1': MIXED}, {'1': ['a1']}, 'Card issuance fee', 'What is the card issuance fee?')
    assert row['coverage_status'] == 'full' and row['outcome'] == 'covered_reachable'
    assert 'referral_only_support' not in row['residual_review_codes'] and verification_calls(model)


def test_fallback_constant_is_shared_with_the_chatbot():
    from agent_graph import FAQ_FALLBACK_FRAGMENT as chatbot
    assert chatbot == FAQ_FALLBACK_FRAGMENT


def test_guard_version_is_in_the_manifest():
    assert load_coverage_settings({}).manifest()['referral_guard_version'] == 'referral-guard-1'


def test_every_code_in_this_file_belongs_to_exactly_one_set():
    rows = [fee_referral()[0], fee_referral_beside_fact()[0], unclassified_referral()[0]]
    assessments = [a for row in rows for a in [row['audit_assessment'], *row['phase_assessments'].values()]]
    emitted = {c for row in rows for key in ('review_codes', 'residual_review_codes') for c in row[key]}
    emitted |= {c for a in assessments for key in ('review_codes', 'resolved_review_codes', 'residual_review_codes')
                for c in a[key]}
    assert {'referral_only_support', 'referral_support_unclassified'} <= emitted
    sets = (BLOCKING_CODES, RESIDUAL_CODES, SEARCH_CODES, NOTE_CODES)
    assert all(sum(code in s for s in sets) == 1 for code in emitted), sorted(emitted)
