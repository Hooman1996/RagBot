"""F8d: a repeated question is evaluated once per run. Synthetic rows and mocked inference only."""
import asyncio
import copy
import csv
from collections import Counter
from datetime import datetime, timezone
import io
import json
import multiprocessing
import os
import secrets

import pytest
from fastapi.testclient import TestClient

import main
from knowledge_audit import dedupe, sizing
from knowledge_audit.history import AuditHistoryProvider
from knowledge_audit.inputs import ColumnMapping, ImportedDataset, InputEvent, TimestampPolicy
from knowledge_audit.jobs import CoverageJobs, versions
from knowledge_audit.pipeline import CoverageEvaluator
from knowledge_audit.preparation import QueryPreparer, prepare_dataset
from knowledge_audit.privacy import AuditError, Redactor
from knowledge_audit.recommendations import eligibility
from knowledge_audit.settings import CAPABILITIES, load_coverage_settings
from tests.test_answering_service import Classifier, ImmediateRunner, Processor, Rewriter
from tests.test_knowledge_coverage_access_jobs import coverage_staging, seed
from tests.test_knowledge_coverage_pipeline import LabeledModel, Retrieval
from tests.test_web_auth import csrf, login, setup

pytestmark = pytest.mark.usefixtures("coverage_staging")

KEY = b'synthetic-only-private-key-1234567890'
QUESTION = 'What is the synthetic approval duration and cutoff?'
OTHER = 'Which synthetic document is required for a transfer?'
PRIOR = 'Synthetic earlier user turn about cards.'
POLICY = {'entry_budget': 300, 'documents': ['Synthetic_FAQ'], 'dedupe_policy': dedupe.VERSION}
# Roles one evaluated covered_reachable row sends after preparation.
PER_ROW = {'scope': 1, 'aspects': 1, 'batch': 1, 'verification': 2}


def session(n):
    return 'session_' + f'{n:032x}' if n else ''


def event(n, text, session_number, minute, role='user'):
    return InputEvent('row_' + f'{n:032x}', n, session(session_number), '', text, role,
                      datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc), 'resolved', {}, ())


def dataset(events):
    return ImportedDataset('c' * 64, tuple(events), {'source_row_count': len(events),
                           'selected_row_count': sum(e.selected for e in events)}, ColumnMapping('query'), TimestampPolicy())


def history_free(texts):
    """Each row alone in its own session, or with no session at all."""
    return [event(n, text, n if n % 2 else 0, n) for n, text in enumerate(texts, 1)]


def build(tmp_path, events, settings=None):
    store, _, s, *_ = seed(tmp_path)
    redactor = Redactor(KEY)
    data = dataset(events)
    prep = QueryPreparer(Processor(), ImmediateRunner(), Rewriter(), Classifier())
    rows = asyncio.run(prepare_dataset(data, prep, redactor))
    d = store.save_dataset(data, redactor, KEY, 1, rows)
    meta = new_run(store, d, s, settings)
    return store, d, s, meta


def new_run(store, d, s, settings=None):
    return store.create_run(1, d['dataset_id'], s['snapshot_id'], [], settings or POLICY, versions(),
                            execution_mode='full_input', idempotency_key='synthetic_' + secrets.token_hex(16))


class Model(LabeledModel):
    """Records which question each scope call evaluated; optional per-call scope decisions."""
    def __init__(self, snap, scopes=()):
        super().__init__(snap, {'1': ['a1', 'a2']})
        self.scopes = list(scopes)
    async def call(self, role, data):
        if role == 'scope':
            self.scope = self.scopes.pop(0) if self.scopes else 'kb_question'
        return await super().call(role, data)


def engine_for(store, meta, model, *, dedupe_enabled=True):
    data, redactor = store.dataset(meta['dataset_id'], 1)
    prep = QueryPreparer(Processor(), ImmediateRunner(), Rewriter(), Classifier())
    return CoverageEvaluator(snapshot=model.snap, model=model, retrieval=Retrieval(['1'], ['1']), preparer=prep,
                             redactor=redactor, dataset=data, dedupe=dedupe_enabled)


def run(store, meta, model, **options):
    async def execute():
        async def factory(_):
            return engine_for(store, meta, model, **options)
        jobs = CoverageJobs(store, factory, ImmediateRunner())
        jobs.start(meta['run_id'], 1)
        await asyncio.gather(*list(jobs.tasks._tasks.values()))
        await jobs.aclose()
    asyncio.run(execute())
    assert store.owned('runs', meta['run_id'], 1)['state'] == 'completed'
    return {r['source_row_id']: r for r in store.rows(meta['run_id'], 1)}


def roles(model):
    return Counter(role for role, _ in model.calls)


def evaluated_questions(model):
    return [data['original_question'] for role, data in model.calls if role == 'scope']


def times(counts, n):
    return Counter({role: count * n for role, count in counts.items()})


def snap_of(store, meta):
    return store.snapshot(meta['snapshot_id'], 1)


def prepared_row(**changes):
    """An eligible prepared row as QueryPreparer.prepare returns it."""
    base = {'input_query_redacted': QUESTION, 'normalized_query_redacted': QUESTION, 'standalone_query_redacted': QUESTION,
            'canonical_retrieval_query_redacted': 'synthetic approval duration cutoff', 'existing_intent': 'general',
            'scope_status': 'unknown', 'preparation_status': 'prepared', 'rewrite_status': 'no_prior_history',
            'uncertainty_codes': [], 'history_status': 'unavailable',
            'history_provenance': {'history_status': 'unavailable', 'prior_order_ambiguous': False, 'unresolved_peer_times': False,
                                   'equal_timestamp_event_count': 0, 'history_digest': 'a' * 64, 'cutoff_row_id': 'row_' + '1' * 32}}
    return {**base, **changes}


def provenance(events, index):
    data = dataset(events)
    return AuditHistoryProvider(data, Redactor(KEY)).before(data.events[index]).provenance


def test_eligibility_and_key_inputs():
    identity = 'i' * 64
    assert dedupe.key(identity, prepared_row()) is not None
    incomplete = provenance([event(1, PRIOR, 1, 1, 'assistant'), event(2, QUESTION, 1, 2)], 1)
    ambiguous = provenance([event(1, PRIOR, 1, 2), event(2, QUESTION, 1, 2)], 1)
    assert incomplete['history_status'] == 'incomplete' and ambiguous['history_status'] == 'ambiguous'
    for changes in ({'preparation_status': 'uncertain_preparation'}, {'preparation_status': 'needs_context'},
                    {'uncertainty_codes': ['context_guard_reviewed']},
                    {'history_provenance': incomplete, 'history_status': 'incomplete'},
                    {'history_provenance': ambiguous, 'history_status': 'ambiguous'},
                    {'rewrite_status': 'fallback'}, {'existing_intent': ''}):
        assert not dedupe.eligible(prepared_row(**changes)) and dedupe.key(identity, prepared_row(**changes)) is None
    user_only = provenance([event(1, PRIOR, 1, 1), event(2, QUESTION, 1, 2)], 1)
    assert user_only['history_status'] == 'user_only'
    assert dedupe.key(identity, prepared_row(history_provenance=user_only, history_status='user_only', rewrite_status='rewritten'))
    assert dedupe.key(identity, prepared_row()) == dedupe.key(identity, prepared_row())
    # Row identity and cutoff are not part of the key; every evaluated text is.
    moved = copy.deepcopy(prepared_row()); moved['history_provenance']['cutoff_row_id'] = 'row_' + '2' * 32
    assert dedupe.key(identity, moved) == dedupe.key(identity, prepared_row())
    base = dedupe.key(identity, prepared_row())
    for name in ('input_query_redacted', 'normalized_query_redacted', 'standalone_query_redacted',
                 'canonical_retrieval_query_redacted', 'existing_intent'):
        assert dedupe.key(identity, prepared_row(**{name: 'changed synthetic value'})) != base
    digest = copy.deepcopy(prepared_row()); digest['history_provenance']['history_digest'] = 'b' * 64
    assert dedupe.key(identity, digest) != base
    assert dedupe.key('j' * 64, prepared_row()) != base


def test_identical_history_free_rows_are_evaluated_once(tmp_path):
    store, d, s, meta = build(tmp_path, history_free([QUESTION, QUESTION, QUESTION, OTHER]))
    model = Model(snap_of(store, meta))
    rows = run(store, meta, model)
    first, second, third, other = (rows[i] for i in meta['processing_row_ids'])
    assert roles(model) == times(PER_ROW, 2)
    assert sorted(evaluated_questions(model)) == sorted([QUESTION, OTHER])
    for copy_row in (second, third):
        assert copy_row['deduplicated_from_row_id'] == first['source_row_id']
        assert copy_row['model_evaluated'] is False and copy_row['entry_model_dispatched'] is False
        assert copy_row['dedupe_key_sha256'] == first['dedupe_key_sha256']
    assert first['deduplicated_from_row_id'] == '' and first['model_evaluated'] is True
    assert other['deduplicated_from_row_id'] == '' and other['dedupe_key_sha256'] != first['dedupe_key_sha256']
    set_keys = {'deduplicated_from_row_id', 'model_evaluated', 'entry_model_dispatched'}
    for name in set(first) | set(second):
        if name not in set(dedupe.OWN_KEYS) | set_keys:
            assert second.get(name) == first.get(name), name
    assert first['outcome'] == second['outcome'] == 'covered_reachable' and second['processing_status'] == 'completed'
    assert second['stopping_reason'] == first['stopping_reason'] and second['evaluated_entry_ids'] == first['evaluated_entry_ids']
    for name in ('source_row_id', 'source_record_ordinal', 'processing_ordinal', 'timestamp', 'safe_session_ref'):
        assert len({first[name], second[name], third[name]}) == 3, name
    assert second['model_metrics'] == [] and second['retrieval_metrics'] == []
    assert store.progress(meta['run_id'], 1)['model_evaluated_rows'] == 2


def test_prior_turns_decide_whether_a_row_copies(tmp_path):
    events = [event(1, PRIOR, 1, 1), event(2, QUESTION, 1, 2), event(3, PRIOR, 2, 3), event(4, QUESTION, 2, 4),
              event(5, 'A different synthetic earlier turn.', 3, 5), event(6, QUESTION, 3, 6)]
    store, d, s, meta = build(tmp_path, events)
    model = Model(snap_of(store, meta))
    rows = run(store, meta, model)
    ids = [e.source_row_id for e in events]
    assert rows[ids[1]]['history_status'] == 'user_only' and rows[ids[1]]['rewrite_status'] == 'rewritten'
    assert rows[ids[3]]['deduplicated_from_row_id'] == ids[1]  # same text, identical user-only prior turns
    assert rows[ids[5]]['deduplicated_from_row_id'] == ''      # different prior turns: evaluated again
    assert rows[ids[2]]['deduplicated_from_row_id'] == ids[0]  # the history-free prior turns repeat too
    assert rows[ids[4]]['deduplicated_from_row_id'] == ''
    assert roles(model) == times(PER_ROW, 4)


def test_a_source_sent_to_review_is_not_copied(tmp_path):
    store, d, s, meta = build(tmp_path, history_free([QUESTION, QUESTION, QUESTION]))
    model = Model(snap_of(store, meta), scopes=['uncertain'])
    rows = run(store, meta, model)
    first, second, third = (rows[i] for i in meta['processing_row_ids'])
    assert first['processing_status'] == 'needs_review' and first['deduplicated_from_row_id'] == ''
    assert second['deduplicated_from_row_id'] == '' and second['processing_status'] == 'completed'
    assert third['deduplicated_from_row_id'] == second['source_row_id']
    assert evaluated_questions(model) == [QUESTION, QUESTION]


def test_map_is_rebuilt_from_the_store_after_a_crash(tmp_path):
    store, d, s, meta = build(tmp_path, history_free([QUESTION, QUESTION]))
    first_id, second_id = meta['processing_row_ids']
    def worker():
        real = store.write
        def die_after_first_row(path, value):
            real(path, value)
            if path.name == first_id + '.json' and value.get('processing_status') == 'completed':
                os._exit(23)
        store.write = die_after_first_row
        async def execute():
            async def factory(_):
                return engine_for(store, meta, Model(snap_of(store, meta)))
            jobs = CoverageJobs(store, factory, ImmediateRunner()); jobs.start(meta['run_id'], 1)
            await asyncio.gather(*jobs.tasks._tasks.values())
        asyncio.run(execute())
    process = multiprocessing.Process(target=worker); process.start(); process.join(30)
    if process.is_alive():
        process.kill(); process.join(); pytest.fail('synthetic child did not terminate')
    assert process.exitcode == 23
    assert store.row(meta['run_id'], first_id, 1)['processing_status'] == 'completed'
    assert store.row(meta['run_id'], second_id, 1)['processing_status'] == 'pending'
    model = Model(snap_of(store, meta))
    async def recover():
        async def factory(_):
            return engine_for(store, meta, model)
        jobs = CoverageJobs(store, factory, ImmediateRunner())
        assert (await jobs.inspect_state(meta['run_id'], 1))['state'] == 'interrupted'
        await jobs.recover(meta['run_id'], 1)
        await asyncio.gather(*jobs.tasks._tasks.values()); await jobs.aclose()
    asyncio.run(recover())
    assert store.row(meta['run_id'], second_id, 1)['deduplicated_from_row_id'] == first_id
    assert model.calls == []  # the new worker found the source on disk, not in memory


def test_runs_never_share_sources(tmp_path):
    store, d, s, meta = build(tmp_path, history_free([QUESTION, QUESTION]))
    first = run(store, meta, Model(snap_of(store, meta)))
    later = new_run(store, d, s)
    model = Model(snap_of(store, later))
    second = run(store, later, model)
    assert evaluated_questions(model) == [QUESTION]
    first_id, repeat_id = later['processing_row_ids']
    assert second[first_id]['deduplicated_from_row_id'] == '' and second[repeat_id]['deduplicated_from_row_id'] == first_id
    assert first[first_id]['dedupe_key_sha256'] != second[first_id]['dedupe_key_sha256']  # run identity differs


def test_setting_off_and_runs_without_the_policy_evaluate_every_row(tmp_path):
    off = load_coverage_settings({'KNOWLEDGE_COVERAGE_DEDUPE': 'false'})
    assert off.dedupe is False and off.manifest()['dedupe_policy'] == 'disabled'
    assert load_coverage_settings({}).manifest()['dedupe_policy'] == dedupe.VERSION
    assert load_coverage_settings({'KNOWLEDGE_COVERAGE_DEDUPE': ' TRUE '}).dedupe is True
    for value in ('yes', '1', ''):
        with pytest.raises(AuditError, match='invalid_coverage_dedupe'):
            load_coverage_settings({'KNOWLEDGE_COVERAGE_DEDUPE': value})
    disabled = {**off.manifest(), 'entry_budget': 300, 'documents': ['Synthetic_FAQ']}
    store, d, s, meta = build(tmp_path, history_free([QUESTION, QUESTION]), settings=disabled)
    model = Model(snap_of(store, meta))
    # The factory follows the pinned policy, as service.build_engine does.
    rows = run(store, meta, model, dedupe_enabled=dedupe.enabled(meta['settings']))
    assert evaluated_questions(model) == [QUESTION, QUESTION]
    assert all(r['deduplicated_from_row_id'] == '' and 'dedupe_key_sha256' not in r for r in rows.values())
    legacy = new_run(store, d, s, {'entry_budget': 300, 'documents': ['Synthetic_FAQ']})
    model = Model(snap_of(store, legacy))
    rows = run(store, legacy, model, dedupe_enabled=True)  # an engine that has dedupe still needs the pinned policy
    assert evaluated_questions(model) == [QUESTION, QUESTION]
    assert all(r['deduplicated_from_row_id'] == '' for r in rows.values())


def test_export_recommendations_and_sizing_treat_copies_as_copies(tmp_path):
    store, d, s, meta = build(tmp_path, history_free([QUESTION, QUESTION, OTHER]))
    rows = run(store, meta, Model(snap_of(store, meta)))
    first_id, copy_id, other_id = meta['processing_row_ids']
    for visible in (True, False):
        body, _ = store.export_revision(meta['run_id'], 1, visible, create=True)
        parsed = {r['source_row_id']: r for r in csv.DictReader(io.StringIO(body.decode('utf-8-sig')))}
        assert parsed[copy_id]['deduplicated_from_row_id'] == first_id
        assert parsed[first_id]['deduplicated_from_row_id'] == parsed[other_id]['deduplicated_from_row_id'] == ''
        assert 'dedupe_key_sha256' not in next(iter(parsed.values()))
    live = store.owned('runs', meta['run_id'], 1)
    assert 'deduplicated_row_uses_source' in eligibility(rows[copy_id], live)['reason_codes']
    assert 'deduplicated_row_uses_source' not in eligibility(rows[first_id], live)['reason_codes']
    observed = {name: [] for name in sizing.CLASSES}
    sizing._observe(store, live, observed)
    assert sum(len(v) for v in observed.values()) == 2


@pytest.fixture
def client_store(tmp_path, setup, monkeypatch):
    # Three repeats, one other question, and two rows with ambiguous (equal-time) history.
    events = history_free([QUESTION, QUESTION, QUESTION, OTHER]) + [event(5, OTHER, 9, 30), event(6, PRIOR, 9, 30)]
    store, d, s, _ = build(tmp_path, events)
    jobs = CoverageJobs(store, lambda run: None, ImmediateRunner())
    monkeypatch.setattr(jobs, 'start', lambda *a: None)
    monkeypatch.setattr(main.app.state, 'coverage_runtime', (load_coverage_settings({}), store, jobs), raising=False)
    setup.users[1]['role'] = 'admin'
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS', json.dumps({'1': sorted(CAPABILITIES)}))
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, 'alice')
        yield client, store, d, s


def test_estimate_previews_possible_copies_without_text_or_keys(client_store, monkeypatch):
    client, store, d, s = client_store
    payload = {'dataset_id': d['dataset_id'], 'snapshot_id': s['snapshot_id'], 'row_ids': [], 'execution_mode': 'full_input',
               'entry_budget': 300, 'documents': ['Synthetic_FAQ']}
    response = client.post('/api/knowledge-coverage/runs/estimate', json=payload, headers=csrf(client))
    assert response.status_code == 200, response.text
    view = response.json()
    assert view['dedupe'] == {'policy': dedupe.VERSION, 'candidate_rows': 4, 'distinct_questions': 2, 'possible_copies': 2}
    assert view['row_count'] == 6 and view['estimate'] is None  # the estimate still counts every row
    text = json.dumps(view)
    assert QUESTION not in text and OTHER not in text and PRIOR not in text
    subset = client.post('/api/knowledge-coverage/runs/estimate', headers=csrf(client),
                         json={**payload, 'execution_mode': 'subset', 'row_ids': ['row_' + f'{n:032x}' for n in (1, 2, 4)]}).json()
    assert subset['dedupe']['possible_copies'] == 1
    off = load_coverage_settings({'KNOWLEDGE_COVERAGE_DEDUPE': 'false'})
    monkeypatch.setattr(main.app.state, 'coverage_runtime', (off, *main.app.state.coverage_runtime[1:]), raising=False)
    assert client.post('/api/knowledge-coverage/runs/estimate', json=payload, headers=csrf(client)).json()['dedupe'] is None
