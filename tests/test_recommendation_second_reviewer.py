"""Synthetic second-reviewer approval policy for question recommendations."""
import asyncio
import functools
import json

import pytest

import tests.test_knowledge_coverage_access_jobs as access_jobs
import tests.test_knowledge_recommendations as fixtures
from knowledge_audit.privacy import AuditError
from knowledge_audit.recommendations import RecommendationEngine
from knowledge_audit.settings import load_coverage_settings
from tests.test_knowledge_coverage_access_jobs import coverage_staging
from tests.test_knowledge_recommendations import DraftModel, REVIEWER, seed_gap_store

pytestmark = pytest.mark.usefixtures("coverage_staging")

QUERY_MARKER = 'SYNTHQUERYMARKER'
EVIDENCE_MARKER = 'SYNTHEVIDENCEMARKER'


def drafted(tmp_path):
    """A completed revision owned by user 1 with one drafted row."""
    store, recs, meta, row, snap, redactor = seed_gap_store(tmp_path)
    rid = meta['recommendation_revision_id']
    source = recs.source(rid, 1)
    result = asyncio.run(RecommendationEngine(DraftModel(), snap, redactor).draft(source['rows'][0], source['manifest']))
    meta['state'] = 'completed'
    recs.finish(rid, 1, meta, {row['source_row_id']: result})
    return recs, rid, row['source_row_id']


def test_owner_cannot_approve_own_run_but_can_reject_or_request_changes(tmp_path, monkeypatch):
    recs, rid, row_id = drafted(tmp_path)
    with pytest.raises(AuditError, match='second_reviewer_required'):
        recs.decide(rid, 1, REVIEWER, row_id, 'q1', 'approved', '')
    assert recs.decide(rid, 1, REVIEWER, row_id, 'q1', 'rejected', '')['decisions'][row_id + ':q1']['status'] == 'rejected'
    assert recs.decide(rid, 1, REVIEWER, row_id, 'q1', 'needs_changes', '')['decisions'][row_id + ':q1']['status'] == 'needs_changes'
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_REQUIRE_SECOND_REVIEWER', 'false')
    assert recs.decide(rid, 1, REVIEWER, row_id, 'q1', 'approved', '')['reviewer_user_id'] == 1
    assert load_coverage_settings().manifest()['recommendation_review_policy'] == 'owner-review-1'


def test_second_reviewer_with_capability_approves_and_is_recorded(tmp_path):
    recs, rid, row_id = drafted(tmp_path)
    assert rid in [m['recommendation_revision_id'] for m in recs.list_reviewable(2, REVIEWER)]
    assert recs.list_reviewable(1, REVIEWER) == []
    review = recs.decide(rid, 2, REVIEWER, row_id, 'q1', 'approved', '')
    assert (review['reviewer_user_id'], review['run_owner_id']) == (2, 1)
    decision = review['decisions'][row_id + ':q1']
    assert (decision['status'], decision['reviewer_user_id'], decision['run_owner_id']) == ('approved', 2, 1)
    manifest = recs.compose(rid, 1, True)
    assert (manifest['reviewer_user_id'], manifest['run_owner_id']) == (2, 1)


def test_second_user_without_capability_sees_nothing(tmp_path):
    recs, rid, row_id = drafted(tmp_path)
    assert recs.list_reviewable(2, frozenset()) == []
    for call in (lambda: recs.reviewable(rid, 2, frozenset()), lambda: recs.reviewer_view(rid, 2, frozenset()),
                 lambda: recs.decide(rid, 2, frozenset(), row_id, 'q1', 'approved', '')):
        with pytest.raises(AuditError, match='artifact_not_found'):
            call()


def test_reviewer_projection_never_carries_queries_or_evidence(tmp_path, monkeypatch):
    original = access_jobs.snapshot
    monkeypatch.setattr(access_jobs, 'snapshot', lambda texts: original({k: v + ' ' + EVIDENCE_MARKER for k, v in texts.items()}))
    monkeypatch.setattr(fixtures, 'seed', functools.partial(access_jobs.seed,
        queries=(QUERY_MARKER + ' What is the duration and cutoff?', 'Duplicate?', 'Duplicate?')))
    recs, rid, row_id = drafted(tmp_path)
    view = recs.reviewer_view(rid, 2, REVIEWER)
    assert QUERY_MARKER in json.dumps(recs.source(rid, 1), ensure_ascii=False)
    assert EVIDENCE_MARKER in json.dumps(recs.store.snapshot(view['revision']['snapshot_id'], 1), ensure_ascii=False)
    assert view['rows'][row_id]['recommendations'] and view['rows'][row_id]['gap_specifications']
    for value in (view, recs.list_reviewable(2, REVIEWER)):
        text = json.dumps(value, ensure_ascii=False)
        assert QUERY_MARKER not in text and EVIDENCE_MARKER not in text
