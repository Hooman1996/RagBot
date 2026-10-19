"""F6: read-only run-to-run stability report; synthetic runs and rows only."""
from __future__ import annotations
import copy
import json
import stat

import pytest

from knowledge_audit.privacy import private_directory
from knowledge_audit.settings import load_coverage_settings
from knowledge_audit.store import CoverageStore
from scripts import knowledge_coverage_stability_report as report

MARKER = 'UNIQUE-PRIVATE-MARKER-7f3a'
SNAPSHOT = 'a' * 64
ROW = 'row_' + '1' * 32


def row(outcome='covered_not_reachable', supports=(('3', 'a1', 'applicable'), ('3', 'a2', 'applicable')),
        descriptions=('duration', 'deadline')):
    aspects = [{'aspect_id': f'a{n}', 'description': f'{MARKER} {d}', 'conditions': []} for n, d in enumerate(descriptions, 1)]
    witness = [{'entry_id': e, 'aspect_id': a, 'applicability': p, 'explanation': MARKER + ' support',
                'citations': [{'chunk_id': e, 'sentence_number': n, 'text': MARKER + ' sentence'}]}
               for n, (e, a, p) in enumerate(supports, 1)]
    return {'source_row_id': ROW, 'input_query_redacted': MARKER + ' query', 'standalone_query_redacted': MARKER + ' query',
            'outcome': outcome, 'processing_status': 'completed', 'coverage_status': 'full', 'explanation': MARKER + ' explanation',
            'requested_aspects': aspects, 'supported_aspects': [{**a, 'supports': []} for a in aspects],
            'batch_results': [{'batch_id': 'initial:1', 'entry_ids': ['3'], 'supports': witness,
                               'result': {'explanation': MARKER + ' batch', 'conflicts': [MARKER + ' conflict']}}],
            'supporting_sentence_refs': [r for s in witness for r in s['citations']],
            'verifications': [{'origin': 'initial:1', 'verdict': 'accepted', 'explanation': MARKER + ' verifier'},
                              {'origin': 'initial:1:reversed', 'verdict': 'accepted', 'explanation': MARKER + ' verifier'}],
            'model_metrics': [{'role': 'batch', 'prompt_tokens': 1000, 'completion_tokens': 100},
                              {'role': 'verification', 'prompt_tokens': 2000, 'completion_tokens': 130},
                              {'role': 'verification', 'prompt_tokens': 2000, 'completion_tokens': None}]}


@pytest.fixture
def store(tmp_path):
    return CoverageStore(tmp_path / 'coverage', ephemeral_test_store=True)


def save_run(store, number, saved_row, *, batch=2, snapshot=SNAPSHOT, settings=None, state='completed', versions=None):
    rid = 'r_' + f'{number:032x}'
    base = {**load_coverage_settings({}).manifest(), 'entry_budget': 300, 'documents': ['Synthetic_FAQ']}
    pinned = {**base, 'batch_entries': batch, 'batch_max_entries': batch, **(settings or {})}
    path = private_directory(store._path('runs', rid))
    private_directory(path / 'rows')
    store.write(path / 'meta.json', {'run_id': rid, 'owner_id': 0, 'dataset_id': 'd_' + '2' * 32, 'snapshot_id': snapshot,
        'state': state, 'settings': pinned, 'versions': versions or {'code': 'synthetic'}, 'row_ids': [ROW], 'selected_row_ids': [ROW]})
    store.write(path / 'rows' / (ROW + '.json'), saved_row)
    return rid


def invoke(store, run_ids, output):
    args = [a for rid in run_ids for a in ('--run-id', rid)] + ['--row-id', ROW, '--output', str(output)]
    return report.main(args, store=store)


def test_identical_supports_pass(store, tmp_path, capsys):
    runs = [save_run(store, 1, row(), batch=1), save_run(store, 2, row(), batch=5)]
    assert invoke(store, runs, tmp_path / 'out') == 0
    data = json.loads((tmp_path / 'out' / 'stability-report.json').read_text())
    summary = data['rows'][0]
    assert summary['support_jaccard_min'] == summary['support_jaccard_mean'] == 1.0
    assert summary['passed'] and data['all_passed']
    first = summary['runs'][0]
    assert first['batch_max_entries'] == 1 and summary['runs'][1]['batch_max_entries'] == 5
    assert first['supporting_sentence_refs'] == ['3:1', '3:2'] and first['supported_aspect_ids'] == ['a1', 'a2']
    assert first['support_triples'] == [['3', 'a1', 'applicable'], ['3', 'a2', 'applicable']]
    assert first['verifications'] == [{'origin': 'initial:1', 'verdict': 'accepted'},
                                      {'origin': 'initial:1:reversed', 'verdict': 'accepted'}]
    assert (first['completions'], first['prompt_tokens'], first['completion_tokens']) == (2, 3000, 230)
    assert json.loads(capsys.readouterr().out)['all_passed'] is True


def test_different_outcome_fails(store, tmp_path):
    runs = [save_run(store, 1, row()), save_run(store, 2, row(outcome='possible_partial_gap'), batch=3)]
    assert invoke(store, runs, tmp_path / 'out') == 1
    summary = json.loads((tmp_path / 'out' / 'stability-report.json').read_text())['rows'][0]
    assert summary['verdict_agreement'] is False and summary['support_agreement_pass'] is True and not summary['passed']


def test_different_aspects_fail(store, tmp_path):
    runs = [save_run(store, 1, row()), save_run(store, 2, row(descriptions=('deadline', 'duration')), batch=3)]
    assert invoke(store, runs, tmp_path / 'out') == 1
    summary = json.loads((tmp_path / 'out' / 'stability-report.json').read_text())['rows'][0]
    assert summary['aspect_checklist_agreement'] is False and summary['verdict_agreement'] is True and not summary['passed']


def test_low_support_agreement_fails(store, tmp_path):
    runs = [save_run(store, 1, row()), save_run(store, 2, row(supports=(('3', 'a1', 'applicable'), ('4', 'a2', 'applicable'))))]
    assert invoke(store, runs, tmp_path / 'out') == 1
    summary = json.loads((tmp_path / 'out' / 'stability-report.json').read_text())['rows'][0]
    assert summary['support_jaccard_min'] == pytest.approx(1 / 3) and summary['support_agreement_pass'] is False


@pytest.mark.parametrize('second,code', [
    ({'snapshot': 'b' * 64}, 'snapshot_mismatch'),
    ({'settings': {'entry_budget': 120}}, 'code_version_mismatch'),
    ({'settings': {'verification_passes': 1}}, 'code_version_mismatch'),
    ({'state': 'running'}, 'run_not_completed'),
])
def test_refusals_print_only_the_code(store, tmp_path, capsys, second, code):
    runs = [save_run(store, 1, row()), save_run(store, 2, row(), batch=3, **second)]
    assert invoke(store, runs, tmp_path / 'out') == 2
    captured = capsys.readouterr()
    assert captured.err.strip() == code and captured.out == ''
    assert not (tmp_path / 'out').exists()


def test_missing_row_and_run_are_refused(store, tmp_path, capsys):
    pending = {**row(), 'outcome': 'pending', 'processing_status': 'pending'}
    runs = [save_run(store, 1, row()), save_run(store, 2, pending)]
    assert invoke(store, runs, tmp_path / 'out') == 2
    assert capsys.readouterr().err.strip() == 'row_missing'
    assert invoke(store, [runs[0], 'r_' + 'f' * 32], tmp_path / 'out') == 2
    assert capsys.readouterr().err.strip() == 'run_not_completed'


def test_outputs_are_private_and_contain_no_text(store, tmp_path, capsys):
    other = row(outcome='needs_review')
    other['verifications'][1] = {**other['verifications'][1], 'verdict': 'rejected'}
    runs = [save_run(store, 1, row(), batch=1), save_run(store, 2, copy.deepcopy(other), batch=2)]
    assert invoke(store, runs, tmp_path / 'out') == 1
    captured = capsys.readouterr()
    for name in ('stability-report.json', 'stability-report.md'):
        path = tmp_path / 'out' / name
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert MARKER not in path.read_text()
    assert MARKER not in captured.out and MARKER not in captured.err
    text = (tmp_path / 'out' / 'stability-report.md').read_text()
    assert 'initial:1:reversed=rejected' in text and '## Pass rule' in text and text.count(ROW) == 3


def started_versions(batch, **runtime):
    # A started run records settings.manifest(), batch keys included, in its versions.
    manifest = {**load_coverage_settings({}).manifest(), 'batch_entries': batch, 'batch_max_entries': batch, **runtime}
    return {'code': 'synthetic', 'runtime_configuration': {'status': 'observed', 'audit_runtime_settings': manifest}}


def test_runs_differing_only_in_batch_size_in_runtime_versions_are_compared(store, tmp_path):
    runs = [save_run(store, 1, row(), batch=1, versions=started_versions(1)),
            save_run(store, 2, row(), batch=5, versions=started_versions(5))]
    stored = [copy.deepcopy(store.owned('runs', rid, 0)) for rid in runs]
    assert invoke(store, runs, tmp_path / 'out') == 0
    assert json.loads((tmp_path / 'out' / 'stability-report.json').read_text())['all_passed'] is True
    # The comparison works on a copy; the stored meta keeps its batch keys.
    assert [store.owned('runs', rid, 0) for rid in runs] == stored
    assert stored[1]['versions']['runtime_configuration']['audit_runtime_settings']['batch_max_entries'] == 5


def test_runtime_versions_differing_beyond_batch_size_are_refused(store, tmp_path, capsys):
    runs = [save_run(store, 1, row(), batch=1, versions=started_versions(1)),
            save_run(store, 2, row(), batch=5, versions=started_versions(5, initial_entries=7))]
    assert invoke(store, runs, tmp_path / 'out') == 2
    assert capsys.readouterr().err.strip() == 'code_version_mismatch'
    assert not (tmp_path / 'out').exists()
