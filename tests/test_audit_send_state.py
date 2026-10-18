"""F8a, F16b: requests that never reached the server do not pause the run. Synthetic data only."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from knowledge_audit.failures import send_state
from knowledge_audit.operations import Budget, Limits, OperationalPause
from knowledge_audit.privacy import AuditError
from knowledge_audit.recovery import UNKNOWN, CheckpointModel, RowJournal, unknown_records
from knowledge_audit.store import CoverageStore
from tests.test_answering_service import ImmediateRunner
from tests.test_knowledge_coverage_access_jobs import coverage_staging, seed
from utils.audit_dispatch import audit_dispatch, completion_metadata, observe_audit
from utils.service_errors import ServiceUnavailableError

REQUEST = httpx.Request('POST', 'http://fixture/v1/chat/completions')
ROW = 'row_' + '5' * 32


def caused(outer, inner):
    outer.__cause__ = inner
    return outer


def status_error():
    return httpx.HTTPStatusError('synthetic', request=REQUEST, response=httpx.Response(500, request=REQUEST))


def api_status_error():
    return openai.APIStatusError('synthetic', response=httpx.Response(500, request=REQUEST), body=None)


def connection_error(cause):
    return caused(openai.APIConnectionError(request=REQUEST), cause)


@pytest.mark.parametrize('error', [
    httpx.ConnectError('synthetic', request=REQUEST),
    httpx.ConnectTimeout('synthetic', request=REQUEST),
    httpx.PoolTimeout('synthetic', request=REQUEST),
    connection_error(httpx.ConnectError('synthetic', request=REQUEST)),
    caused(ServiceUnavailableError('synthetic'), connection_error(httpx.ConnectError('synthetic', request=REQUEST))),
], ids=['connect', 'connect_timeout', 'pool_timeout', 'sdk_connection', 'service_unavailable'])
def test_connection_never_made_is_not_sent(error):
    assert send_state(error) == 'not_sent'


@pytest.mark.parametrize('error', [status_error(), api_status_error()], ids=['httpx_status', 'sdk_status'])
def test_error_status_is_server_rejected(error):
    assert send_state(error) == 'server_rejected'


@pytest.mark.parametrize('error', [
    httpx.ReadTimeout('synthetic', request=REQUEST),
    httpx.RemoteProtocolError('synthetic', request=REQUEST),
    connection_error(httpx.ReadError('synthetic', request=REQUEST)),
    caused(openai.APITimeoutError(request=REQUEST), httpx.ReadTimeout('synthetic', request=REQUEST)),
    asyncio.CancelledError(),
    caused(OperationalPause('budget_elapsed'), httpx.ConnectError('synthetic', request=REQUEST)),
], ids=['read_timeout', 'remote_protocol', 'sdk_read_error', 'sdk_read_timeout', 'cancelled', 'pause'])
def test_ambiguous_failure_is_unknown(error):
    assert send_state(error) == 'unknown'


def budget(tmp_path):
    root = tmp_path / 'store'
    store = CoverageStore(root, ephemeral_test_store=True)
    run = root / 'runs' / ('r_' + '0' * 32)
    run.mkdir(mode=0o700, parents=True)
    return Budget(store, run, 1, Limits(min_free_bytes=0, pace_ms=0))


def raising(error):
    async def operation():
        raise error
    return operation


async def answered():
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10))


async def dispatch(b, operation):
    with observe_audit(b), completion_metadata('batch', 100):
        return await audit_dispatch('completion', operation, output_tokens=50)


def only_request(b):
    requests = list(b.read()['requests'].values())
    assert len(requests) == 1
    return requests[0]


def test_refused_connection_is_refunded_and_does_not_pause(tmp_path):
    b = budget(tmp_path)
    b.row_id = ROW
    async def run():
        with pytest.raises(httpx.ConnectError):
            await dispatch(b, raising(httpx.ConnectError('synthetic', request=REQUEST)))
        summary = b.summary()
        assert summary['pause_reason'] == '' and summary['unknown_reservations'] == 0
        assert summary['tokens_charged'] == 0 and summary['completion_attempts'] == 0
        assert summary['not_sent_completions'] == 1 and summary['dispatched_completions'] == 0
        assert summary['failure_streaks'] == {'model': 1} and summary['consecutive_failures'] == 1
        item = only_request(b)
        assert item['state'] == 'not_sent' and item['charged_tokens'] == item['known_tokens'] == 0
        assert item['error_category'] == 'model_connection_failure'
        # Readers of unknown work exclude it by construction.
        assert b.unknown_row_ids() == []
        b.acknowledge_unknown()
        assert 'acknowledged' not in only_request(b)
        # Not blocked: the second refusal is a new dispatch, not a pause.
        for _ in range(2):
            with pytest.raises(httpx.ConnectError):
                await dispatch(b, raising(httpx.ConnectError('synthetic', request=REQUEST)))
        summary = b.summary()
        assert summary['consecutive_failures'] == 3 and summary['not_sent_completions'] == 3
        assert summary['tokens_charged'] == 0 and summary['completion_attempts'] == 0
        with pytest.raises(OperationalPause, match='budget_failures'):
            await dispatch(b, answered)
        assert len(b.read()['requests']) == 3
    asyncio.run(run())


def test_server_rejection_keeps_charge_and_does_not_pause(tmp_path):
    b = budget(tmp_path)
    async def run():
        with pytest.raises(httpx.HTTPStatusError):
            await dispatch(b, raising(status_error()))
        summary = b.summary()
        item = only_request(b)
        assert item['state'] == 'failed_known' and item['known_tokens'] is None
        assert item['charged_tokens'] == 150 and item['error_category'] == 'model_http_rejection'
        assert summary['tokens_charged'] == 150 and summary['completion_attempts'] == 1
        assert summary['pause_reason'] == '' and summary['unknown_reservations'] == 0
        assert summary['server_rejected_completions'] == 1 and summary['dispatched_completions'] == 1
        assert summary['failure_streaks'] == {'model': 1}
        response = await dispatch(b, answered)
        assert response.usage.completion_tokens == 10
        summary = b.summary()
        assert summary['tokens_charged'] == 260 and summary['known_tokens'] == 110
        assert summary['completion_attempts'] == 2 and summary['server_rejected_completions'] == 1
    asyncio.run(run())


def test_server_rejection_over_allowance_pauses_for_tokens_only(tmp_path):
    root = tmp_path / 'store'
    store = CoverageStore(root, ephemeral_test_store=True)
    run = root / 'runs' / ('r_' + '0' * 32)
    run.mkdir(mode=0o700, parents=True)
    b = Budget(store, run, 1, Limits(min_free_bytes=0, pace_ms=0, token_allowance=150))
    identity = b.reserve('completion', 150, 'batch')
    b.dispatched(identity)
    value = b.read()
    value['tokens_charged'] = 151
    b.write(value)
    b.server_rejected(identity, 'model_http_rejection')
    assert b.summary()['pause_reason'] == 'budget_tokens'


def test_read_timeout_still_pauses_as_unknown(tmp_path):
    b = budget(tmp_path)
    async def run():
        with pytest.raises(httpx.ReadTimeout):
            await dispatch(b, raising(httpx.ReadTimeout('synthetic', request=REQUEST)))
        summary = b.summary()
        assert only_request(b)['state'] == 'unknown'
        assert summary['pause_reason'] == 'unknown_remote_completion' and summary['unknown_reservations'] == 1
        assert summary['tokens_charged'] == 150 and summary['not_sent_completions'] == 0
        with pytest.raises(OperationalPause, match='unknown_remote_completion'):
            await dispatch(b, answered)
    asyncio.run(run())


@pytest.fixture
def journal_run(tmp_path, coverage_staging):
    from tests.test_knowledge_execution_recovery import pinned
    store, _, _, meta, *_ = seed(tmp_path)
    meta = pinned(store, meta)
    row = store.row(meta['run_id'], meta['selected_row_ids'][0], 1)
    row['attempt_count'] = 1
    return store, meta, row


def model_call(journal_run, transport):
    from tests.test_knowledge_coverage_reliability import model_fixture
    store, meta, row = journal_run
    b = Budget(store, store._path('runs', meta['run_id']), 1, Limits())
    b.start()
    journal = RowJournal(store, meta, row, ImmediateRunner())
    async def run():
        model, rag, http = model_fixture(transport)
        try:
            with observe_audit(b), pytest.raises(AuditError):
                await CheckpointModel(model, journal).call('scope', {'question': 'Synthetic procedure?'})
            return model.metrics[-1]
        finally:
            await rag.client.close()
            await http.aclose()
    return asyncio.run(run()), journal, b


def test_model_refused_connection_is_not_dispatched(journal_run):
    def refuse(request):
        raise httpx.ConnectError('synthetic', request=request)
    metric, journal, b = model_call(journal_run, refuse)
    assert metric['dispatched'] is False and metric['server_completion_state'] == 'not_dispatched'
    assert metric['failure_category'] == 'model_connection_failure'
    records = journal.records()
    assert len(records) == 1 and records[0]['state'] == 'failed_before_dispatch'
    assert records[0]['state'] not in UNKNOWN and journal.unknowns() == []
    summary = b.summary()
    assert summary['pause_reason'] == '' and summary['not_sent_completions'] == 1
    assert summary['failure_streaks']['model'] == 1


def test_model_http_500_is_rejected_and_counted_once(journal_run):
    def reject(request):
        return httpx.Response(500, json={'error': {'message': 'synthetic'}})
    metric, journal, b = model_call(journal_run, reject)
    assert metric['dispatched'] is True and metric['server_completion_state'] == 'rejected_by_server'
    assert metric['failure_category'] == 'model_http_rejection' and metric['http_status'] == 500
    records = journal.records()
    assert len(records) == 1 and records[0]['state'] == 'response_received'
    assert records[0]['state'] not in UNKNOWN and journal.unknowns() == []
    summary = b.summary()
    assert summary['pause_reason'] == '' and summary['server_rejected_completions'] == 1
    # The ledger counts the failure; the model result does not count it again.
    assert summary['failure_streaks']['model'] == 1 and summary['consecutive_failures'] == 1


def test_rewrite_fallback_is_a_reusable_checkpoint(journal_run):
    store, meta, row = journal_run
    journal = RowJournal(store, meta, row, ImmediateRunner())
    calls = []
    async def fallback():
        calls.append(True)
        return {'preparation_status': 'uncertain_preparation', 'rewrite_status': 'fallback'}
    async def failed():
        return {'preparation_status': 'failed', 'rewrite_status': 'not_run'}
    async def run():
        first = await journal.invoke('preparation', {'event': 'synthetic-1'}, fallback)
        records = journal.records()
        assert len(records) == 1 and records[0]['state'] == 'validated' and records[0]['result_sha256']
        assert records[0]['result']['rewrite_status'] == 'fallback'
        assert journal.unknowns() == [] and unknown_records(store, meta, row['source_row_id']) == []
        again = await journal.invoke('preparation', {'event': 'synthetic-1'}, fallback)
        assert again == first and again['preparation_status'] == 'uncertain_preparation'
        assert journal.hits == 1 and len(calls) == 1
        await journal.invoke('preparation', {'event': 'synthetic-2'}, failed)
        assert [r['state'] for r in journal.unknowns()] == ['preparation_unobserved']
    asyncio.run(run())
