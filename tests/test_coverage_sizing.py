"""F8b: pre-start cost estimate from completed reference runs. Synthetic runs, rows and ledgers only."""
from dataclasses import asdict
import json
import secrets

import pytest
from fastapi.testclient import TestClient

import main
from knowledge_audit import sizing
from knowledge_audit.jobs import CoverageJobs, versions
from knowledge_audit.operations import Limits
from knowledge_audit.settings import load_coverage_settings
from tests.test_answering_service import ImmediateRunner
from tests.test_knowledge_coverage_access_jobs import coverage_staging, seed
from tests.test_web_auth import csrf, login, setup
from web_permissions import route_permission

MARKER = 'SYNTHETICMARKER7F3A'
QUERIES = tuple(f'{MARKER} synthetic question {n}?' for n in range(1, 8))
# (outcome, completions, tokens, duration_ms): 2 covered and 4 non-covered rows.
ROWS = (('covered_reachable', 4, 1000, 2000), ('covered_not_reachable', 6, 3000, 4000),
        ('possible_gap', 10, 10000, 10000), ('possible_partial_gap', 20, 20000, 20000),
        ('needs_review', 30, 30000, 30000), ('possible_gap', 40, 40000, 40000))
LOW = {**asdict(Limits()), 'completion_attempts': 50}


@pytest.fixture
def seeded(tmp_path, coverage_staging):
    store, d, s, _, data, *_ = seed(tmp_path, queries=QUERIES)
    return store, d, s, data


def config(selection='explicit_source_row_ids', limits=None, **changes):
    """The config create_run builds for documents Synthetic_FAQ and entry budget 300."""
    return {**load_coverage_settings({}).manifest(), 'entry_budget': 300, 'documents': ['Synthetic_FAQ'],
            'selection_method': selection, 'operational_limits': limits or asdict(Limits()), **changes}


def reference(store, d, s, data, rows=ROWS, *, settings=None, state='completed', meta_changes=None):
    ids = [e.source_row_id for e in data.selected][:len(rows)]
    meta = store.create_run(1, d['dataset_id'], s['snapshot_id'], ids, settings or config(), versions(), execution_mode='subset')
    path = store._path('runs', meta['run_id'])
    ledger = store.read(path / 'budget.json')
    for number, (row_id, (outcome, completions, tokens, ms)) in enumerate(zip(ids, rows)):
        for n in range(completions):
            ledger['requests'][f'allowance_{number:04d}{n:028d}'] = {'state': 'returned', 'charged_tokens': tokens // completions,
                'known_tokens': tokens // completions, 'responsibility': 'batch', 'source_row_id': row_id}
        # A refused connection is never counted.
        ledger['requests'][f'allowance_{number:04d}{"f" * 28}'] = {'state': 'not_sent', 'charged_tokens': 0,
            'known_tokens': 0, 'responsibility': 'batch', 'source_row_id': row_id}
        row = store.read(path / 'rows' / (row_id + '.json'))
        row.update(outcome=outcome, processing_status='completed', duration_ms=ms, explanation=MARKER + ' explanation')
        store.write(path / 'rows' / (row_id + '.json'), row)
    store.write(path / 'budget.json', ledger)
    return store.update_run(meta['run_id'], 1, {'state': state, **(meta_changes or {})})


def stats_for(store, d, s, settings=None):
    return sizing.reference_stats(store, 1, s['snapshot_id'], d['dataset_id'], settings or config(), versions())


def test_reference_runs_match_on_setup_but_not_on_limits(seeded):
    store, d, s, data = seeded
    kept = [reference(store, d, s, data)['run_id'],
            reference(store, d, s, data, settings=config('server_all_user_query_rows', LOW))['run_id'],
            reference(store, d, s, data, meta_changes={'versions': {**versions(), 'serving': {'fixture': 'synthetic'},
                'runtime_configuration': {'audit_runtime_settings': {'batch_max_entries': 2}}}})['run_id']]
    for ignored in ({'state': 'running'}, {'meta_changes': {'snapshot_id': 'b' * 64}},
                    {'meta_changes': {'dataset_id': 'd_' + 'e' * 32}},
                    {'meta_changes': {'versions': {**versions(), 'code_id': 'f' * 64}}},
                    {'settings': config(batch_max_entries=1)}):
        reference(store, d, s, data, **ignored)
    stats = stats_for(store, d, s)
    assert sorted(stats['reference_run_ids']) == sorted(kept) and stats['reference_row_count'] == 18


def test_reference_stats_are_exact_and_skip_not_sent_and_pending_rows(seeded):
    store, d, s, data = seeded
    run = reference(store, d, s, data, rows=ROWS + (('pending', 3, 300, 100),))
    stats = stats_for(store, d, s)
    assert stats['reference_run_ids'] == [run['run_id']] and stats['reference_row_count'] == 6
    covered, non_covered, other = (stats['classes'][c] for c in sizing.CLASSES)
    assert (covered['rows'], non_covered['rows'], other['rows']) == (2, 4, 0)
    assert covered['share'] == pytest.approx(1 / 3) and non_covered['share'] == pytest.approx(2 / 3)
    assert covered['completions'] == {'total': 10, 'mean': 5, 'p90': 6}
    assert covered['tokens'] == {'total': 4000, 'mean': 2000, 'p90': 3000}
    assert covered['seconds'] == {'total': 6, 'mean': 3, 'p90': 4}
    # Nearest rank: position ceil(0.9 * 4) = 4 of the sorted list.
    assert non_covered['completions'] == {'total': 100, 'mean': 25, 'p90': 40}
    assert non_covered['tokens'] == {'total': 100000, 'mean': 25000, 'p90': 40000}
    assert non_covered['seconds'] == {'total': 100, 'mean': 25, 'p90': 40}
    assert other['completions'] == {'total': 0, 'mean': 0, 'p90': 0}


def test_fewer_than_five_rows_give_no_stats(seeded):
    store, d, s, data = seeded
    reference(store, d, s, data, rows=ROWS[:4])
    assert stats_for(store, d, s) is None


def test_estimate_and_compare_are_exact(seeded):
    store, d, s, data = seeded
    reference(store, d, s, data)
    stats = stats_for(store, d, s)
    # 10 rows: 10 * (1/3 * 5 + 2/3 * 25) = 183.3 -> 184; 10 * (1/3 * 6 + 2/3 * 40) = 286.7 -> 287.
    result = sizing.estimate(10, stats)
    assert result['version'] == sizing.VERSION and result['row_count'] == 10
    assert result['completions'] == {'expected': 184, 'high': 287}
    assert result['tokens'] == {'expected': 173334, 'high': 276667}
    assert result['seconds'] == {'expected': 177, 'high': 280}
    fits = sizing.compare(result, asdict(Limits()))
    assert fits['completions'] == {'limit': 200, 'expected': 184, 'high': 287, 'fits_expected': True, 'fits_high': False}
    assert fits['tokens']['fits_high'] and fits['seconds']['fits_high'] and fits['fits'] is True
    over = sizing.compare(sizing.estimate(918, stats), asdict(Limits()))
    assert over['completions']['expected'] == 16830 and over['seconds']['expected'] == 16218 and over['fits'] is False
    # Override: non-covered 0.5, and the covered class takes the rest.
    half = sizing.estimate(918, stats, non_covered_share=0.5)
    assert half['shares'] == {'covered': 0.5, 'non_covered': 0.5, 'other': 0}
    assert half['completions'] == {'expected': 13770, 'high': 21114}
    assert half['seconds'] == {'expected': 12852, 'high': 20196}


@pytest.fixture
def client_runtime(seeded, setup, monkeypatch):
    store, d, s, data = seeded
    jobs = CoverageJobs(store, lambda run: None, ImmediateRunner())
    monkeypatch.setattr(jobs, 'start', lambda *a: None)
    monkeypatch.setattr(main.app.state, 'coverage_runtime', (load_coverage_settings({}), store, jobs), raising=False)
    setup.users[1]['role'] = 'admin'
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        yield client, store, d, s, data


def body(d, s, data, mode='full_input', **extra):
    rows = [] if mode == 'full_input' else [e.source_row_id for e in data.selected][:6]
    return {'dataset_id': d['dataset_id'], 'snapshot_id': s['snapshot_id'], 'row_ids': rows, 'execution_mode': mode,
            'entry_budget': 300, 'documents': ['Synthetic_FAQ'], 'budget_acknowledged': mode == 'full_input',
            'idempotency_key': 'synthetic_' + secrets.token_hex(16), **extra}


def estimate_body(d, s, data, mode='full_input', **extra):
    return {k: v for k, v in body(d, s, data, mode, **extra).items() if k not in {'budget_acknowledged', 'idempotency_key'}}


def test_estimate_endpoint_shape_and_permissions(client_runtime, setup, monkeypatch):
    client, store, d, s, data = client_runtime
    assert route_permission('POST', '/api/knowledge-coverage/runs/estimate') == 'coverage_run_start'
    empty = client.post('/api/knowledge-coverage/runs/estimate', json=estimate_body(d, s, data), headers=csrf(client))
    assert empty.status_code == 200, empty.text
    assert empty.json() == {'row_count': len(data.selected), 'estimate': None, 'comparison': None,
                            'reference': {'run_ids': [], 'row_count': 0}, 'sizing_version': sizing.VERSION,
                            # Seven distinct questions in one session: nothing to copy.
                            'dedupe': {'policy': 'repeated-question-1', 'candidate_rows': 7, 'distinct_questions': 7,
                                       'possible_copies': 0}}
    run = reference(store, d, s, data)
    sized = client.post('/api/knowledge-coverage/runs/estimate', json=estimate_body(d, s, data, operational_limits=LOW),
                        headers=csrf(client)).json()
    assert sized['row_count'] == 7 and sized['reference'] == {'run_ids': [run['run_id']], 'row_count': 6}
    # 7 * 55/3 = 128.3 -> 129 expected completions against a limit of 50.
    assert sized['estimate']['completions'] == {'expected': 129, 'high': 201}
    assert sized['comparison']['completions'] == {'limit': 50, 'expected': 129, 'high': 201,
                                                  'fits_expected': False, 'fits_high': False}
    assert sized['comparison']['fits'] is False
    subset = client.post('/api/knowledge-coverage/runs/estimate', json=estimate_body(d, s, data, 'subset', non_covered_share=1),
                         headers=csrf(client)).json()
    assert subset['row_count'] == 6 and subset['estimate']['completions'] == {'expected': 150, 'high': 240}
    assert MARKER not in json.dumps(sized) and MARKER not in json.dumps(subset)
    setup.users[1]['role'] = 'dashboard_viewer'
    for path, payload in (('runs/estimate', estimate_body(d, s, data)), ('runs', body(d, s, data, sizing_acknowledged=True))):
        assert client.post('/api/knowledge-coverage/' + path, json=payload, headers=csrf(client)).status_code == 403


@pytest.mark.parametrize('mode', ['full_input', 'subset'])
def test_unsized_run_needs_acknowledgement(client_runtime, mode):
    client, store, d, s, data = client_runtime
    refused = client.post('/api/knowledge-coverage/runs', json=body(d, s, data, mode), headers=csrf(client))
    assert refused.status_code == 422
    assert refused.json()['detail'] == 'No reference runs on this snapshot; run a pilot first or acknowledge an unsized run'
    started = client.post('/api/knowledge-coverage/runs', json=body(d, s, data, mode, sizing_acknowledged=True), headers=csrf(client))
    assert started.status_code == 202, started.text
    meta = store.owned('runs', started.json()['run_id'], 1)
    assert meta['sizing'] == {'version': sizing.VERSION, 'estimate': None, 'comparison': None,
                              'reference': {'run_ids': [], 'row_count': 0}, 'sizing_acknowledged': True,
                              'accept_partial_run': False}
    assert 'sizing' not in meta['settings']


@pytest.mark.parametrize('mode', ['full_input', 'subset'])
def test_run_over_the_limits_needs_partial_acceptance(client_runtime, mode):
    client, store, d, s, data = client_runtime
    run = reference(store, d, s, data)
    refused = client.post('/api/knowledge-coverage/runs', json=body(d, s, data, mode, operational_limits=LOW), headers=csrf(client))
    assert refused.status_code == 422
    assert refused.json()['detail'] == 'Estimated cost exceeds run limits; raise limits or accept a partial run'
    # A sized run within the limits needs no checkbox.
    fits = client.post('/api/knowledge-coverage/runs', json=body(d, s, data, mode), headers=csrf(client))
    assert fits.status_code == 202, fits.text
    assert store.owned('runs', fits.json()['run_id'], 1)['sizing']['comparison']['fits'] is True
    started = client.post('/api/knowledge-coverage/runs', json=body(d, s, data, mode, operational_limits=LOW, accept_partial_run=True),
                          headers=csrf(client))
    assert started.status_code == 202, started.text
    meta = store.owned('runs', started.json()['run_id'], 1)
    assert meta['sizing']['accept_partial_run'] is True and meta['sizing']['comparison']['fits'] is False
    assert meta['sizing']['reference'] == {'run_ids': [run['run_id']], 'row_count': 6}
    assert meta['sizing']['estimate']['row_count'] == (7 if mode == 'full_input' else 6)
    assert 'sizing' not in meta['settings'] and MARKER not in json.dumps(meta['sizing'])


def test_pilot_runs_skip_sizing(client_runtime):
    client, store, d, s, data = client_runtime
    for n in range(2):
        pilot = client.post('/api/knowledge-coverage/runs', json={**body(d, s, data, 'pilot'), 'row_ids': [data.selected[n].source_row_id],
                            'operational_limits': LOW}, headers=csrf(client))
        assert pilot.status_code == 202, pilot.text
        assert 'sizing' not in store.owned('runs', pilot.json()['run_id'], 1)
        reference(store, d, s, data)


def test_version_keys_match_a_new_run():
    assert set(versions()) == sizing.VERSION_KEYS
