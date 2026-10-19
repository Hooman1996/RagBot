"""F8c/F15: continuations, run chains, the chain export and required idempotency keys. Synthetic rows only."""
from dataclasses import replace
import csv
import hashlib
import io
import json
import os
import secrets

import pytest
from fastapi.testclient import TestClient

import main
from knowledge_audit import chain_export
from knowledge_audit.execution import continuation_counts, continuation_rows
from knowledge_audit.jobs import CoverageJobs, versions
from knowledge_audit.privacy import AuditError
from knowledge_audit.retention import plan_cleanup
from knowledge_audit.settings import load_coverage_settings
from tests.test_answering_service import ImmediateRunner
from tests.test_coverage_sizing import LOW, config, reference
from tests.test_knowledge_coverage_access_jobs import coverage_staging
from tests.test_knowledge_execution_recovery import create, synthetic_918
from tests.test_web_auth import csrf, login, setup
from utils.read_only_audit import canonical_sha256

pytestmark = pytest.mark.usefixtures("coverage_staging")


@pytest.fixture(autouse=True)
def no_fsync(monkeypatch):
    """These tests check selection and chains on 918-row runs, not crash durability; skip the disk flushes."""
    monkeypatch.setattr(os, 'fsync', lambda descriptor: None)
OUTCOMES = {'completed': 'covered_reachable', 'failed': 'error', 'needs_review': 'needs_review', 'needs_context': 'needs_context',
            'invalid_input': 'error', 'excluded': 'excluded'}
UNSIZED = 'No reference runs on this snapshot; run a pilot first or acknowledge an unsized run'
OVER = 'Estimated cost exceeds run limits; raise limits or accept a partial run'


def key():
    return 'synthetic_' + secrets.token_hex(16)


def mark(store, rid, statuses, **meta):
    """Set row statuses directly, rebuild the progress index, then update the run."""
    path = store._path('runs', rid) / 'rows'
    for row_id, status in statuses.items():
        status, extra = status if isinstance(status, tuple) else (status, {})
        row = store.read(path / (row_id + '.json'))
        row.update(processing_status=status, outcome=OUTCOMES.get(status, 'pending'), **extra)
        store.write(path / (row_id + '.json'), row)
    store.progress(rid, 1, reconcile=True)
    return store.update_run(rid, 1, meta) if meta else store.owned('runs', rid, 1)


def started(store, rid, *, model_limit, limits=None, serving=None):
    """What a started run records: serving and runtime_configuration in versions."""
    runtime = {'model_limit': model_limit, 'model_sample_rule': store.owned('runs', rid, 1)['settings'].get('selection_method', 'x'),
               'audit_concurrency': 1, 'audit_runtime_settings': {'batch_max_entries': 2, 'operational_limits': limits or {'completion_attempts': 200}}}
    return store.update_run(rid, 1, {'versions': {**versions(), 'serving': serving or {'vllm': {'model_id': 'synthetic'}},
                                                  'runtime_configuration': runtime}})


@pytest.fixture
def data918(tmp_path):
    store, d, snap, old, dataset = synthetic_918(tmp_path)
    return store, d, snap, old, dataset


# 1. Selection
def test_selection_rule_with_and_without_needs_review(data918):
    store, d, snap, old, dataset = data918
    ids = [e.source_row_id for e in dataset.selected][10:20]
    run = create(store, d, snap, old, 'subset', ids)
    statuses = dict(zip(ids, ['completed', 'pending', 'failed', 'interrupted', 'needs_review', 'needs_context',
                              'invalid_input', 'excluded', ('needs_review', {'unknown_completion_count': 1}),
                              ('completed', {'unknown_completion_count': 1})]))
    mark(store, run['run_id'], statuses, state='paused')
    default = [ids[1], ids[2], ids[3], ids[8]]
    assert continuation_rows(store, 1, run['run_id']) == default
    assert continuation_rows(store, 1, run['run_id'], include_needs_review=True) == [ids[1], ids[2], ids[3], ids[4], ids[8]]
    assert continuation_counts(store, 1, run['run_id']) == {'unfinished': 4, 'needs_review': 1, 'failed': 1, 'unknown': 1}
    with pytest.raises(AuditError, match='artifact_not_found'):
        continuation_rows(store, 2, run['run_id'])


# 2-3, 7. The API
@pytest.fixture
def client_runtime(data918, setup, monkeypatch):
    store, d, snap, old, dataset = data918
    jobs = CoverageJobs(store, lambda run: None, ImmediateRunner())
    monkeypatch.setattr(jobs, 'start', lambda *a: None)
    settings = load_coverage_settings({})
    monkeypatch.setattr(main.app.state, 'coverage_runtime', (settings, store, jobs), raising=False)
    setup.users[1]['role'] = 'admin'
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        yield client, store, d, snap, dataset, jobs


def paused_full(store, d, snap, dataset, settings=None, done=40):
    run = store.create_run(1, d['dataset_id'], snap['snapshot_id'], [], settings or config('server_all_user_query_rows'),
                           versions(), execution_mode='full_input')
    return mark(store, run['run_id'], {r: 'completed' for r in run['selected_row_ids'][:done]}, state='paused', pause_reason='budget_completions')


def post(client, rid, **body):
    return client.post(f'/api/knowledge-coverage/runs/{rid}/continuations', json=body, headers=csrf(client))


def test_continuation_creates_a_linked_subset_run(client_runtime):
    client, store, d, snap, dataset, _ = client_runtime
    source = paused_full(store, d, snap, dataset)
    rid = source['run_id']
    preview = client.get(f'/api/knowledge-coverage/runs/{rid}/continuation-preview')
    assert preview.json() == {'unfinished': 878, 'needs_review': 0, 'failed': 0, 'unknown': 0}
    estimate = client.post(f'/api/knowledge-coverage/runs/{rid}/continuation-estimate', json={}, headers=csrf(client)).json()
    assert estimate['row_count'] == 878 and estimate['estimate'] is None and estimate['truncated'] is False
    refused = post(client, rid, idempotency_key=key())
    assert refused.status_code == 422 and refused.json()['detail'] == UNSIZED
    same = key()
    created = post(client, rid, idempotency_key=same, sizing_acknowledged=True)
    assert created.status_code == 202, created.text
    body = created.json()
    assert body['truncated'] is False and body['remaining_rows'] == 0
    meta = store.owned('runs', body['run_id'], 1)
    assert meta['execution_mode'] == 'subset' and meta['selected_row_ids'] == source['selected_row_ids'][40:]
    assert meta['continues_run_id'] == rid and meta['chain_root_run_id'] == rid
    assert 'continues_run_id' not in meta['settings'] and 'chain_root_run_id' not in meta['settings']
    assert meta['settings']['entry_budget'] == source['settings']['entry_budget'] and meta['settings']['documents'] == ['Synthetic_FAQ']
    assert meta['sizing']['sizing_acknowledged'] is True and meta['sizing']['estimate'] is None
    assert post(client, rid, idempotency_key=same, sizing_acknowledged=True).json()['run_id'] == body['run_id']
    # A second continuation of the same source would branch the chain.
    again = post(client, rid, idempotency_key=key(), sizing_acknowledged=True)
    assert again.status_code == 409 and again.json()['detail'] == 'run_already_continued'
    # The continuation of the continuation keeps the root.
    mark(store, body['run_id'], {}, state='paused')
    second = post(client, body['run_id'], idempotency_key=key(), sizing_acknowledged=True).json()
    assert store.owned('runs', second['run_id'], 1)['chain_root_run_id'] == rid


def test_continuation_sizing_rules_apply(client_runtime):
    client, store, d, snap, dataset, _ = client_runtime
    reference(store, d, snap, dataset)
    source = paused_full(store, d, snap, dataset)
    over = post(client, source['run_id'], idempotency_key=key(), operational_limits=LOW)
    assert over.status_code == 422 and over.json()['detail'] == OVER
    created = post(client, source['run_id'], idempotency_key=key(), operational_limits=LOW, accept_partial_run=True)
    assert created.status_code == 202, created.text
    sizing = store.owned('runs', created.json()['run_id'], 1)['sizing']
    assert sizing['accept_partial_run'] is True and sizing['comparison']['fits'] is False and sizing['estimate']['row_count'] == 878


def test_continuation_refusals(client_runtime, monkeypatch):
    client, store, d, snap, dataset, jobs = client_runtime
    source = paused_full(store, d, snap, dataset)
    rid = source['run_id']
    lease = store.lease(rid)
    try:
        held = post(client, rid, idempotency_key=key(), sizing_acknowledged=True)
    finally:
        os.close(lease)
    assert held.status_code == 409 and held.json()['detail'] == 'run_active'
    store.update_run(rid, 1, {'state': 'queued', 'stage': 'waiting'})
    queued = post(client, rid, idempotency_key=key(), sizing_acknowledged=True)
    assert queued.status_code == 409 and queued.json()['detail'] == 'run_active'
    store.update_run(rid, 1, {'state': 'paused'})
    # A changed setting is a different setup.
    drifted = paused_full(store, d, snap, dataset, config('server_all_user_query_rows', batch_max_entries=1))
    refused = post(client, drifted['run_id'], idempotency_key=key(), sizing_acknowledged=True)
    assert refused.status_code == 409 and refused.json()['detail'] == 'continuation_identity_drift'
    with pytest.raises(AuditError, match='continuation_identity_drift'):
        chain_export.same_setup(drifted, config(), versions())
    # Nothing left to run.
    ids = [e.source_row_id for e in dataset.selected][:5]
    done = store.create_run(1, d['dataset_id'], snap['snapshot_id'], ids, config(), versions(), execution_mode='subset')
    mark(store, done['run_id'], {r: 'completed' for r in ids}, state='completed')
    empty = post(client, done['run_id'], idempotency_key=key(), sizing_acknowledged=True)
    assert empty.status_code == 422 and empty.json()['detail'] == 'No unfinished rows'
    # A started source has serving and runtime_configuration; that alone is not drift.
    started(store, rid, model_limit=918)
    created = post(client, rid, idempotency_key=key(), sizing_acknowledged=True)
    assert created.status_code == 202, created.text
    assert client.post('/api/knowledge-coverage/runs/r_' + 'f' * 32 + '/continuations',
                       json={'idempotency_key': key()}, headers=csrf(client)).status_code == 404


def test_continuation_over_the_row_maximum_is_truncated(client_runtime, monkeypatch):
    client, store, d, snap, dataset, jobs = client_runtime
    source = paused_full(store, d, snap, dataset)
    # The maximum only caps the selection; the run settings stay those of the source.
    settings = load_coverage_settings({})
    class Capped:
        max_run_rows = 300
        def __getattr__(self, name):
            return getattr(settings, name)
    monkeypatch.setattr(main.app.state, 'coverage_runtime', (Capped(), store, jobs), raising=False)
    estimate = client.post(f"/api/knowledge-coverage/runs/{source['run_id']}/continuation-estimate", json={}, headers=csrf(client)).json()
    assert estimate['row_count'] == 300 and estimate['truncated'] is True and estimate['remaining_rows'] == 578
    created = post(client, source['run_id'], idempotency_key=key(), sizing_acknowledged=True)
    assert created.status_code == 202, created.text
    assert created.json()['truncated'] is True and created.json()['remaining_rows'] == 578
    assert store.owned('runs', created.json()['run_id'], 1)['selected_row_ids'] == source['selected_row_ids'][40:340]


def test_every_run_creating_request_needs_an_idempotency_key(client_runtime):
    client, store, d, snap, dataset, _ = client_runtime
    body = {'dataset_id': d['dataset_id'], 'snapshot_id': snap['snapshot_id'], 'row_ids': [dataset.selected[0].source_row_id],
            'execution_mode': 'pilot', 'entry_budget': 300, 'documents': ['Synthetic_FAQ']}
    assert client.post('/api/knowledge-coverage/runs', json=body, headers=csrf(client)).status_code == 422
    first = client.post('/api/knowledge-coverage/runs', json={**body, 'idempotency_key': key()}, headers=csrf(client))
    second = client.post('/api/knowledge-coverage/runs', json={**body, 'idempotency_key': key()}, headers=csrf(client))
    assert first.status_code == second.status_code == 202 and first.json()['run_id'] != second.json()['run_id']
    source = paused_full(store, d, snap, dataset)
    missing = client.post(f"/api/knowledge-coverage/runs/{source['run_id']}/continuations", json={'sizing_acknowledged': True}, headers=csrf(client))
    assert missing.status_code == 422
    assert not any(m.get('continues_run_id') for m in store.list_owned('runs', 1))


# 4-6. Chains, the chain export and retention
def chain_of_three(store, d, snap, old, dataset):
    root = create(store, d, snap, old, 'full_input', key=key())
    ids = root['selected_row_ids']
    started(store, root['run_id'], model_limit=918, limits={'completion_attempts': 50})
    # Row 7 has an empty question and stays invalid_input.
    mark(store, root['run_id'], {**{r: 'completed' for r in ids[:40] if r != ids[7]}, ids[40]: 'failed'}, state='paused')
    first_rows = continuation_rows(store, 1, root['run_id'])
    assert first_rows == ids[40:41] + ids[41:]
    chain = {'continues_run_id': root['run_id'], 'chain_root_run_id': root['run_id']}
    c1 = store.create_run(1, d['dataset_id'], snap['snapshot_id'], first_rows, old['settings'], versions(),
                          execution_mode='subset', idempotency_key=key(), chain=chain)
    started(store, c1['run_id'], model_limit=878, limits={'completion_attempts': 120})
    mark(store, c1['run_id'], {**{r: 'completed' for r in ids[40:100]}, ids[50]: 'failed'}, state='paused')
    second_rows = continuation_rows(store, 1, c1['run_id'])
    assert second_rows == [ids[50]] + ids[100:]
    c2 = store.create_run(1, d['dataset_id'], snap['snapshot_id'], second_rows, old['settings'], versions(), execution_mode='subset',
                          idempotency_key=key(), chain={'continues_run_id': c1['run_id'], 'chain_root_run_id': root['run_id']})
    started(store, c2['run_id'], model_limit=819, limits={'completion_attempts': 900})
    mark(store, c2['run_id'], {r: 'completed' for r in second_rows}, state='completed')
    return root, c1, c2


def test_chain_of_three_runs_exports_each_row_from_the_run_that_finished_it(data918):
    store, d, snap, old, dataset = data918
    root, c1, c2 = chain_of_three(store, d, snap, old, dataset)
    ids = root['row_ids']
    runs = chain_export.chain(store, 1, c1['run_id'])
    assert [m['run_id'] for m in runs] == [root['run_id'], c1['run_id'], c2['run_id']]
    body, manifest = chain_export.export_revision(store, 1, c2['run_id'], True, create=True)
    rows = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'), newline='')))
    assert len(rows) == len(root['row_ids']) == 918 and [r['source_row_id'] for r in rows] == ids
    expected = {**{r: root['run_id'] for r in ids[:40]}, **{r: c1['run_id'] for r in ids[40:100]},
                ids[50]: c2['run_id'], **{r: c2['run_id'] for r in ids[100:]}, ids[7]: root['run_id']}
    assert {r['source_row_id']: r['source_run_id'] for r in rows} == expected
    assert rows[7]['processing_status'] == 'invalid_input' and rows[50]['processing_status'] == 'completed'
    assert all(r['run_id'] == root['run_id'] and r['export_revision_id'] == manifest['export_revision_id'] for r in rows)
    assert manifest['chain_export_version'] == 'coverage-chain-export-1'
    assert manifest['chain_run_ids'] == [root['run_id'], c1['run_id'], c2['run_id']]
    assert manifest['chain_results_sha256'] == {m['run_id']: canonical_sha256(store.rows(m['run_id'], 1)) for m in (root, c1, c2)}
    assert hashlib.sha256(body).hexdigest() == manifest['csv_sha256'] and body[:3] == b'\xef\xbb\xbf'
    assert manifest['row_count'] == 918 and manifest['source_run_row_counts'] == {root['run_id']: 40, c1['run_id']: 59, c2['run_id']: 819}
    # The same chain state gives the same immutable revision and the same bytes.
    again, same = chain_export.export_revision(store, 1, root['run_id'], True, create=True)
    assert again == body and same == manifest
    assert chain_export.export_revision(store, 1, c1['run_id'], True, manifest['export_revision_id']) == (body, manifest)
    runs = chain_export.chain(store, 1, root['run_id'])
    _, redactor = store.dataset(d['dataset_id'], 1)
    captured = chain_export.capture(store, 1, runs)
    assert chain_export.revision_name(runs, *captured[1:], True) == manifest['export_revision_id']
    rebuilt, _ = chain_export.build(store, 1, runs, chain_export.capture(store, 1, runs), redactor, True,
                                    manifest['export_revision_id'], 'another capture time')
    assert rebuilt == body  # a fresh build from the same state gives the stored bytes
    # Restricted projection keeps the run export's restricted fields.
    restricted, limited = chain_export.export_revision(store, 1, root['run_id'], False, create=True)
    assert limited['evidence_visible'] is False and limited['export_revision_id'] != manifest['export_revision_id']
    assert all(r['evidence_visibility'] == 'restricted' and r['explanation'] == ''
               for r in csv.DictReader(io.StringIO(restricted.decode('utf-8-sig'), newline='')))
    # Model limits and operational limits differed across the three runs.
    assert len({json.dumps(m['versions']['runtime_configuration'], sort_keys=True) for m in runs}) == 3


def test_chain_export_api_is_hash_bound(client_runtime):
    client, store, d, snap, dataset, _ = client_runtime
    old = {'settings': {'entry_budget': 300, 'documents': ['Synthetic_FAQ']}}
    root, c1, c2 = chain_of_three(store, d, snap, old, dataset)
    base = f"/api/knowledge-coverage/runs/{c1['run_id']}"
    revision = client.post(base + '/chain-export-revisions', headers=csrf(client))
    assert revision.status_code == 201, revision.text
    value = revision.json()
    assert value['chain_run_ids'] == [root['run_id'], c1['run_id'], c2['run_id']] and value['row_count'] == 918
    body = client.get(base + '/chain-export?revision_id=' + value['export_revision_id'])
    manifest = client.get(f"/api/knowledge-coverage/runs/{root['run_id']}/chain-export-manifest?revision_id=" + value['export_revision_id']).json()
    assert body.status_code == 200 and hashlib.sha256(body.content).hexdigest() == manifest['csv_sha256'] == value['csv_sha256']
    assert body.headers['X-Coverage-Revision-ID'] == value['export_revision_id']
    assert client.get(base + '/chain-export?revision_id=rev_' + '0' * 32).status_code == 404


def test_bad_chains_are_refused(data918):
    store, d, snap, old, dataset = data918
    root, c1, c2 = chain_of_three(store, d, snap, old, dataset)
    with pytest.raises(AuditError, match='run_already_continued'):
        store.create_run(1, d['dataset_id'], snap['snapshot_id'], continuation_rows(store, 1, root['run_id']), old['settings'], versions(),
                         execution_mode='subset', idempotency_key=key(), chain={'continues_run_id': root['run_id'], 'chain_root_run_id': root['run_id']})
    branch = create(store, d, snap, old, 'subset', root['row_ids'][100:110], key=key())
    store.update_run(branch['run_id'], 1, {'continues_run_id': root['run_id'], 'chain_root_run_id': root['run_id']})
    with pytest.raises(AuditError, match='ambiguous_run_chain'):
        chain_export.chain(store, 1, c2['run_id'])
    store.update_run(branch['run_id'], 1, {'continues_run_id': '', 'chain_root_run_id': ''})
    assert len(chain_export.chain(store, 1, c2['run_id'])) == 3
    store.update_run(c1['run_id'], 1, {'snapshot_id': 'b' * 64})
    with pytest.raises(AuditError, match='chain_identity_drift'):
        chain_export.chain(store, 1, root['run_id'])
    store.update_run(c1['run_id'], 1, {'snapshot_id': snap['snapshot_id']})
    started(store, c2['run_id'], model_limit=819, serving={'vllm': {'model_id': 'another-synthetic'}})
    with pytest.raises(AuditError, match='chain_identity_drift'):
        chain_export.export_revision(store, 1, root['run_id'], True, create=True)


def test_retention_keeps_every_run_of_a_retained_chain_export(data918):
    store, d, snap, old, dataset = data918
    root, c1, c2 = chain_of_three(store, d, snap, old, dataset)
    for m in store.list_owned('runs', 1):  # no active work, so retention decides by references
        store.update_run(m['run_id'], 1, {'state': 'completed'})
    chain_export.export_revision(store, 1, c2['run_id'], True, create=True)
    (store._path('runs', root['run_id']) / '.hold').write_text('')
    (store._path('runs', root['run_id']) / '.hold').chmod(0o600)
    plan = plan_cleanup(store.root, 1, 1, as_of=4102444800)
    assert plan['unresolved_inventory'] is False
    node = plan['nodes'][root['run_id']]
    assert node['reasons'] == ['explicit_hold']  # the chain-exports layout is known
    assert {c1['run_id'], c2['run_id']} <= set(node['references'])
    assert not {root['run_id'], c1['run_id'], c2['run_id']} & set(plan['candidates'])
