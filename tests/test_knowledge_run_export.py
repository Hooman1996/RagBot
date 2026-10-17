"""A5 export fixtures are fictional checkpoints, never model/live customer runs."""
import asyncio
import copy
import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from knowledge_audit.inputs import CsvInputAdapter, ColumnMapping
from knowledge_audit.privacy import AuditError
from knowledge_audit.preparation import prepare_dataset
from knowledge_audit.recommendation_store import RecommendationStore, decode_coverage
from knowledge_audit.run_export import RunExportStore
from knowledge_audit.store import BytesInput
from tests.test_knowledge_coverage_access_jobs import seed, audit_runtime
from tests.test_knowledge_recommendations import DraftModel, seed_gap_store
from tests.test_web_auth import setup, login, csrf


def finish_draft(recs, meta, row_ids, *, multiple=False):
    """Prescribed question-only fixture; no model or evaluator is invoked."""
    source = recs.source(meta['recommendation_revision_id'], 1)
    results = recs.results(meta['recommendation_revision_id'], 1)
    for row in source['rows']:
        if row['source_row_id'] not in row_ids:
            continue
        path = recs.store.read(recs.path(meta['recommendation_revision_id']) / 'metadata-index.json')['taxonomy_paths'][0]
        questions = []
        for n in range(1, 3 if multiple else 2):
            questions.append({'recommendation_id': 'q' + str(n), 'gap_ids': ['g1'],
                'recommended_question': 'پرسش آزمایشی، با نیم‌فاصله و "نقل قول"\nمهلت چیست؟',
                'missing_aspect_ids': ['a2'], 'category': path['category'], 'subcategory': path['subcategory'],
                'taxonomy_path_id': path['taxonomy_path_id'], 'taxonomy_status': 'existing_path',
                'related_faq_ids': ['1'], 'equivalent_faq_ids': [], 'equivalence_basis': 'none',
                'action': 'new_question', 'justification': 'Synthetic missing aspect.', 'uncertainty': ['Human review pending.']})
        results[row['source_row_id']].update(recommendation_status='drafted', recommendations=questions,
            gap_specifications=[{'gap_id': 'g1', 'missing_aspect_ids': ['a2'], 'missing_information': 'Synthetic cutoff not supplied.',
                'conditions': [], 'partial_support_references': [], 'search_scope_limitations': ['bounded_search_not_exhaustive'],
                'review_requirements': ['knowledge_team_confirmation']}])
    meta.update(state='completed')
    recs.finish(meta['recommendation_revision_id'], 1, meta, results)
    return meta


def selection(meta, row_id, review=''):
    return {'source_row_id': row_id, 'recommendation_revision_id': meta['recommendation_revision_id'], 'review_revision_id': review}


def full_fixture(tmp_path):
    store, _, snap, old, _, redactor, preparer = seed(tmp_path)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['query'])
    values = ['پرسش آزمایشی، "نیم‌فاصله"\nخط بعد؟'] * 918
    values[7] = ''
    for text in values:
        writer.writerow([text])
    dataset = CsvInputAdapter(BytesInput(stream.getvalue().encode('utf-8-sig')), ColumnMapping('query')).load(redactor)
    prepared = asyncio.run(prepare_dataset(dataset, preparer, redactor))
    imported = store.save_dataset(dataset, redactor, b'synthetic-only-private-key-1234567890', 1, prepared)
    meta = store.create_run(1, imported['dataset_id'], snap['snapshot_id'], [e.source_row_id for e in dataset.selected[:5]], old['settings'], old['versions'])
    rows = store.rows(meta['run_id'], 1)
    statuses = ['possible_partial_gap', 'possible_gap', 'covered_reachable', 'covered_not_reachable', 'excluded', 'needs_review', 'needs_context', 'error']
    from tests.test_knowledge_recommendations import gap_case
    _, template, _ = gap_case()
    for n, status in enumerate(statuses):
        row = rows[n]
        if n < 2:
            preserved = {k: row[k] for k in ('source_row_id', 'source_record_ordinal', 'safe_session_ref', 'input_query_redacted')}
            row.update(copy.deepcopy(template), **preserved, kb_snapshot_id=snap['snapshot_id'])
        row.update(outcome=status, processing_status='completed' if n < 5 else 'failed' if n == 7 else 'needs_context',
                   coverage_status=['partial','unsupported','full','full','not_evaluated','uncertain','not_evaluated','not_evaluated'][n],
                   preparation_status='invalid_input' if n == 7 else 'needs_context' if n == 6 else 'prepared',
                   evaluated_entry_count=2 if n < 4 else 0,
                   production_context_sufficiency='full' if n == 2 else 'partial' if n == 0 else 'unsupported' if n == 3 else 'not_evaluated',
                   stopping_reason='candidate_exhausted' if n < 2 else 'verified_full' if n in (2,3) else status)
        if n in (2,3):
            row.update(verification_result='accepted',production_reachability='sufficient' if n==2 else 'insufficient')
        # Non-pilot statuses here are prescribed import/checkpoint fixtures.
        if n < 5:store.save_row(meta['run_id'], row, 1)
        else:store.write(store._path('runs',meta['run_id'])/'rows'/(row['source_row_id']+'.json'),row)
    store.update_run(meta['run_id'], 1, {'state': 'completed', 'completed_pilot_rows': 5})
    _, source = store.export_revision(meta['run_id'], 1, True, create=True)
    recs = RecommendationStore(store)
    first = finish_draft(recs, recs.create(meta['run_id'],1,source['export_revision_id'],[rows[0]['source_row_id']]), [rows[0]['source_row_id']], multiple=True)
    second = finish_draft(recs, recs.create(meta['run_id'],1,source['export_revision_id'],[rows[1]['source_row_id']]), [rows[1]['source_row_id']])
    return store, RunExportStore(store), recs, meta, source, rows, first, second


def parsed(body):
    return list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'), newline='')))


def test_full_918_path_multiple_rows_proposals_reviews_and_immutable_pairs(tmp_path):
    store, exports, recs, run, source, rows, first, second = full_fixture(tmp_path)
    row1, row2 = rows[0]['source_row_id'], rows[1]['source_row_id']
    approved = recs.decide(first['recommendation_revision_id'], 1, row1, 'q1', 'approved', 'Synthetic private review note.')
    rejected = recs.decide(second['recommendation_revision_id'], 1, row2, 'q1', 'rejected', 'Synthetic rejection.')
    selected = [selection(first,row1,approved['review_revision_id']), selection(second,row2,rejected['review_revision_id'])]
    preview = exports.preview(run['run_id'],1,source['export_revision_id'],selected,True)
    assert preview['summary']['total_source_rows'] == 918
    assert preview['summary']['pending'] == 910
    assert preview['summary']['coverage_evaluated'] == 4
    assert preview['summary']['review_needed'] == 2 and preview['summary']['excluded'] == 1 and preview['summary']['errors'] == 1
    assert preview['summary']['recommendation_review_states'] == {'approved':1,'unreviewed':1,'rejected':1}
    frozen = exports.create(run['run_id'],1,source['export_revision_id'],selected,True)
    body, manifest = exports.download(run['run_id'],1,True,frozen['export_revision_id'])
    output = parsed(body)
    assert len(output) == 918 and [r['source_row_id'] for r in output] == source['row_ids']
    assert len(set(r['source_row_id'] for r in output)) == 918
    assert output[8]['input_query_redacted'] == output[9]['input_query_redacted']
    assert len(json.loads(output[0]['recommendations'])) == 2
    assert '\n' in json.loads(output[0]['recommendations'])[0]['recommended_question']
    assert [r['outcome'] for r in output[:8]] == [r['outcome'] for r in rows[:8]]
    assert output[2]['production_context_sufficiency'] == 'full' and output[3]['production_context_sufficiency'] == 'unsupported'
    assert output[2]['production_reachability']=='sufficient' and output[3]['production_reachability']=='insufficient'
    assert all(r['human_gap_review_status'] == 'not_reviewed' for r in output)
    assert all(r['recommendation_status'] == 'unavailable' for r in output[2:])
    assert all(json.loads(r['recommendation_unavailable_reasons']) for r in output[2:])
    assert set(manifest['revision_selection_map']) == {row1,row2}
    assert manifest['revision_selection_map'][row1]['review_revision_id'] == approved['review_revision_id']
    assert hashlib.sha256(body).hexdigest() == manifest['csv_sha256'] and body.startswith(b'\xef\xbb\xbf')
    recs.decide(first['recommendation_revision_id'],1,row1,'q1','needs_changes','Later decision.')
    store.save_row(run['run_id'],{**rows[0],'outcome':'needs_review'},1)
    assert exports.download(run['run_id'],1,True,frozen['export_revision_id']) == (body,manifest)
    assert all(r['export_id'] == manifest['export_id'] for r in output)
    original = exports.source(run['run_id'],1,source['export_revision_id'])[0]
    for i, r in enumerate(output):
        for field in ('coverage_status','production_context_sufficiency','production_reachability','stopping_reason','kb_snapshot_id',
                      'configuration_id','rubric_version','run_identity_id','batch_max_entries'):
            assert r[field] == str(original[i][field])
        for field in ('requested_aspects','supported_aspects','unresolved_aspects','supporting_sentence_refs',
                      'evaluation_scope','model_versions','prompt_versions'):
            assert json.loads(r[field]) == original[i][field]
    # Both independent pandas and Python parsers must preserve the exact denominator.
    import pandas as pd
    independent = pd.read_csv(io.BytesIO(body), encoding='utf-8-sig', dtype=str, keep_default_na=False)
    assert independent['source_row_id'].tolist() == manifest['row_ids']


def test_incompatible_duplicate_unknown_unfinished_sources_rejected(tmp_path):
    store,recs,first,row,_,_=seed_gap_store(tmp_path)
    source=first['source_export_revision_id'];exports=RunExportStore(store);run=first['source_run_id']
    with pytest.raises(AuditError,match='duplicate_row_selection'):
        exports.preview(run,1,source,[selection(first,row['source_row_id'])]*2,True)
    with pytest.raises(AuditError,match='draft_not_finished'):
        exports.preview(run,1,source,[selection(first,row['source_row_id'])],True)
    finish_draft(recs,first,[row['source_row_id']])
    _,other=store.export_revision(run,1,True,create=True)
    with pytest.raises(AuditError,match='incompatible_coverage_source'):
        exports.create(run,1,other['export_revision_id'],[selection(first,row['source_row_id'])],True)
    with pytest.raises(AuditError,match='unknown_draft_row'):
        exports.create(run,1,source,[selection(first,store.rows(run,1)[1]['source_row_id'])],True)
    with pytest.raises(AuditError,match='unknown_source_row'):
        exports.create(run,1,source,[selection(first,'row_'+'f'*32)],True)
    with pytest.raises(AuditError,match='artifact_not_found'):
        exports.options(run,2)
    summary=exports.preview(run,1,other['export_revision_id'],[],True)['summary']
    assert summary['incompatible_draft_count'] == 1 and len(summary['unselected_drafts']) == 1


@pytest.mark.parametrize('text',["=1+1",'  +SUM(1,2)','\t@SUM(1,2)','\r\n-1+2','\u202e\u200f=1+1','\x00 =1+1',"'=original apostrophe","'ordinary apostrophe",'نیم‌فاصله، "نقل قول"\nخط دوم'])
def test_formula_display_prefix_map_exact_original_roundtrip(tmp_path,text):
    store,recs,meta,row,_,_=seed_gap_store(tmp_path)
    live=store.row(meta['source_run_id'],row['source_row_id'],1)
    live['input_query_redacted']=text;store.save_row(meta['source_run_id'],live,1)
    body,manifest=store.export_revision(meta['source_run_id'],1,True,create=True)
    assert manifest['csv_display_policy']=='formula-prefix-map-1'
    assert decode_coverage(body,manifest)[0]['input_query_redacted']==text
    exports=RunExportStore(store)
    frozen=exports.create(meta['source_run_id'],1,manifest['export_revision_id'],[],True)
    out,m=exports.download(meta['source_run_id'],1,True,frozen['export_revision_id'])
    value=parsed(out)[0]['input_query_redacted']
    if 'input_query_redacted' in m['csv_escaped_cells'].get(row['source_row_id'],[]):value=value[1:]
    assert value==text


def test_restricted_projection_does_not_leak_drafts_notes_or_evidence(tmp_path):
    store,recs,first,row,_,_=seed_gap_store(tmp_path)
    finish_draft(recs,first,[row['source_row_id']]);rid=first['recommendation_revision_id']
    review=recs.decide(rid,1,row['source_row_id'],'q1','rejected','PRIVATE_NOTE_SENTINEL')
    exports=RunExportStore(store);selected=[selection(first,row['source_row_id'],review['review_revision_id'])]
    frozen=exports.create(first['source_run_id'],1,first['source_export_revision_id'],selected,False)
    body,manifest=exports.download(first['source_run_id'],1,False,frozen['export_revision_id'])
    assert b'PRIVATE_NOTE_SENTINEL' not in body+json.dumps(manifest).encode()
    assert 'پرسش آزمایشی' not in body.decode('utf-8-sig')
    for r in parsed(body):
        assert json.loads(r['recommendations'])==[] and json.loads(r['requested_aspects'])==[]
        assert json.loads(r['gap_specifications'])==[] and json.loads(r['evidence_phases'])=={}
        assert r['evidence_visibility']=='restricted'
    with pytest.raises(AuditError,match='artifact_not_found'):
        exports.download(first['source_run_id'],1,True,frozen['export_revision_id'])


def test_selected_failed_draft_stays_error_without_proposals_or_approval(tmp_path):
    store,recs,meta,row,_,_=seed_gap_store(tmp_path)
    results=recs.results(meta['recommendation_revision_id'],1)
    results[row['source_row_id']].update(recommendation_status='error',error_code='model_read_timeout')
    meta.update(state='completed');recs.finish(meta['recommendation_revision_id'],1,meta,results)
    exports=RunExportStore(store)
    m=exports.create(meta['source_run_id'],1,meta['source_export_revision_id'],[selection(meta,row['source_row_id'])],True)
    body,_=exports.download(meta['source_run_id'],1,True,m['export_revision_id'])
    output=parsed(body)[0]
    assert output['recommendation_status']=='error' and output['recommendation_error_code']=='model_read_timeout'
    assert output['recommendation_approval_allowed']=='false' and json.loads(output['recommendations'])==[]
    assert 'recommendation_error_or_incomplete' in json.loads(output['recommendation_projection_reasons'])
    assert output['outcome']==row['outcome']


@pytest.mark.parametrize('kind',['proposed_new_category','proposed_new_subcategory'])
def test_run_export_preserves_proposed_taxonomy_flags_as_review_proposals(tmp_path,kind):
    store,recs,meta,row,_,_=seed_gap_store(tmp_path)
    source=recs.source(meta['recommendation_revision_id'],1)
    results=recs.results(meta['recommendation_revision_id'],1)
    # Prescribed proposal fixture: these are taxonomy suggestions, not KB edits.
    from knowledge_audit.recommendation_store import recommendation_row
    finish_draft(recs,meta,[row['source_row_id']],multiple=True)
    # Create a separate immutable revision rather than modify its saved result.
    new=recs.create(meta['source_run_id'],1,meta['source_export_revision_id'],[row['source_row_id']])
    results=copy.deepcopy(recs.results(meta['recommendation_revision_id'],1))
    proposal=results[row['source_row_id']]['recommendations'][1]
    proposal.update(taxonomy_status=kind,taxonomy_path_id=None,subcategory='Fictional proposed child')
    if kind=='proposed_new_category':proposal['category']='Fictional proposed parent'
    new.update(state='completed');recs.finish(new['recommendation_revision_id'],1,new,results)
    exports=RunExportStore(store)
    m=exports.create(meta['source_run_id'],1,meta['source_export_revision_id'],[selection(new,row['source_row_id'])],True)
    body,_=exports.download(meta['source_run_id'],1,True,m['export_revision_id']);first=parsed(body)[0]
    assert len(parsed(body))==3 and len(json.loads(first['recommendations']))==2
    assert json.loads(first[kind])==[proposal['category'] if kind=='proposed_new_category' else proposal['subcategory']]
    assert json.loads(first['recommendations'])[1]['taxonomy_status']==kind
    assert first['human_gap_review_status']=='not_reviewed'


def test_run_export_api_owner_csrf_explicit_review_and_permission_revocation(tmp_path,audit_runtime,setup,monkeypatch):
    from fastapi.testclient import TestClient
    from knowledge_audit.settings import CAPABILITIES
    import main
    isolated=tmp_path/'export-test';isolated.mkdir(mode=0o700)
    store,recs,rec,row,_,_=seed_gap_store(isolated)
    finish_draft(recs,rec,[row['source_row_id']])
    _,_,_,_,jobs=audit_runtime
    monkeypatch.setattr(main.app.state,'coverage_runtime',(None,store,jobs))
    setup.users[1]['role']='admin';setup.users[2]['role']='admin'
    monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS',json.dumps({'1':sorted(CAPABILITIES),'2':sorted(CAPABILITIES)}))
    base='/api/knowledge-coverage/runs/'+rec['source_run_id']
    payload={'coverage_export_revision_id':rec['source_export_revision_id'],
             'selections':[selection(rec,row['source_row_id'])]}
    with TestClient(main.app,raise_server_exceptions=False) as client:
        assert client.get(base+'/export-options').status_code==401
        login(client,'alice')
        opts=client.get(base+'/export-options?coverage_export_revision_id='+rec['source_export_revision_id'])
        assert opts.status_code==200 and opts.json()['draft_revisions'][0]['compatible']
        assert client.post(base+'/combined-export-preview',json=payload).status_code==403
        assert client.post(base+'/combined-export-preview',json=payload,headers=csrf(client)).status_code==200
        missing_review=copy.deepcopy(payload);missing_review['selections'][0].pop('review_revision_id')
        assert client.post(base+'/combined-export-preview',json=missing_review,headers=csrf(client)).status_code==422
        created=client.post(base+'/combined-export-revisions',json=payload,headers=csrf(client))
        assert created.status_code==201,created.text
        revision=created.json()['export_revision_id']
        csv_url=base+'/combined-export?revision_id='+revision
        manifest_url=base+'/combined-export-manifest?revision_id='+revision
        old=client.get(csv_url);assert old.status_code==200
        assert hashlib.sha256(old.content).hexdigest()==client.get(manifest_url).json()['csv_sha256']
        _,other=store.export_revision(rec['source_run_id'],1,True,create=True)
        incompatible={**payload,'coverage_export_revision_id':other['export_revision_id']}
        failure=client.post(base+'/combined-export-preview',json=incompatible,headers=csrf(client))
        assert failure.status_code==409 and 'different frozen coverage sources' in failure.json()['detail']
        restricted=sorted(CAPABILITIES-{'coverage_evidence_view'})
        monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS',json.dumps({'1':restricted,'2':sorted(CAPABILITIES)}))
        assert client.get(csv_url).status_code==404 and client.get(manifest_url).status_code==404
        new=client.post(base+'/combined-export-revisions',json=payload,headers=csrf(client));assert new.status_code==201
        restricted_body=client.get(base+'/combined-export?revision_id='+new.json()['export_revision_id'])
        assert restricted_body.status_code==200 and json.loads(parsed(restricted_body.content)[0]['recommendations'])==[]
        monkeypatch.setenv('KNOWLEDGE_COVERAGE_ACCESS_GRANTS',json.dumps({'1':['coverage_results_view'],'2':sorted(CAPABILITIES)}))
        assert client.get(base+'/combined-export?revision_id='+new.json()['export_revision_id']).status_code==403
        assert client.get(base+'/export-options').status_code==403
        login(client,'bob')
        for path in (csv_url,manifest_url,base+'/export-options'):
            assert client.get(path).status_code==404
