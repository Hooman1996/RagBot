"""A5 run-level, explicitly selected, immutable export. No model/service calls."""
from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
import io
import os
import re
import secrets

from knowledge_audit.export import csv_display_escapes, encode_csv
from knowledge_audit.retention import protected_method
from knowledge_audit.privacy import AuditError, private_directory, private_json, private_write
from knowledge_audit.recommendation_store import RecommendationStore, decode_coverage, recommendation_row
from knowledge_audit.recommendations import LOOKUP_VERSION
from utils.read_only_audit import canonical_sha256
from knowledge_audit.store import now


EMPTY_REVIEW = {'review_revision_id': '', 'decisions': {}}
EMPTY_VERSIONS = {'prompts': {}, 'code_id': ''}


def accounting(rows):
    outcomes = Counter(r.get('outcome', 'pending') for r in rows)
    return {
        'total_source_rows': len(rows), 'outcome_counts': dict(outcomes),
        'coverage_evaluated': sum(r.get('coverage_status') in {'full', 'partial', 'unsupported', 'uncertain'}
                                  and r.get('outcome') not in {'pending','error','excluded','needs_context'}
                                  and int(r.get('evaluated_entry_count') or 0) > 0 for r in rows),
        'pending': outcomes['pending'], 'excluded': outcomes['excluded'],
        'review_needed': outcomes['needs_review'] + outcomes['needs_context'], 'errors': outcomes['error'],
        'preparation_counts': dict(Counter(r.get('preparation_status', '') for r in rows)),
        'independent_human_gap_confirmation': 'not_reviewed',
    }


class RunExportStore:
    def __init__(self, store):
        self.store = store
        self.recommendations = RecommendationStore(store)

    def source(self, run_id, owner, revision_id):
        """Read an owned frozen source internally; caller entitlement controls projection.

        A restricted owner can select existing draft/source IDs without receiving the
        privileged CSV, notes, titles or evidence. Direct old download routes retain
        their existing stricter projection matching.
        """
        self.store.owned('runs', run_id, owner)
        if not re.fullmatch(r'rev_[0-9a-f]{32}', revision_id):
            raise AuditError('invalid_artifact_id')
        base = self.store._path('runs', run_id) / 'exports'
        visible = (base / 'evidence' / revision_id).is_dir()
        body, manifest = self.store.export_revision(run_id, owner, visible, revision_id)
        # decode_coverage requires evidence visibility; use the same strict decoder
        # for already-restricted sources without changing their original manifest.
        rows = decode_coverage(body, {**manifest, 'evidence_visible': True})
        if manifest['run_id'] != run_id or any(r['kb_snapshot_id'] != manifest['snapshot_id'] for r in rows):
            raise AuditError('export_identity_mismatch')
        return rows, manifest

    def _revisions(self, run_id, owner):
        values = []
        self.store.owned('runs', run_id, owner)
        for path in self.recommendations.root.glob('rec_*'):
            if path.is_symlink():
                continue
            meta = self.recommendations.owned(path.name, owner) if self.store.read(path / 'meta.json').get('owner_id') == owner else None
            if meta and meta['source_run_id'] == run_id:
                values.append(meta)
        return sorted(values, key=lambda m: (m['created_at'], m['recommendation_revision_id']), reverse=True)

    @protected_method
    def options(self, run_id, owner, source_revision_id=''):
        self.store.owned('runs', run_id, owner)
        sources = []
        base = self.store._path('runs', run_id) / 'exports'
        for path in base.glob('*/rev_*/manifest.json'):
            m = self.store.read(path)
            sources.append({k: m[k] for k in ('export_revision_id', 'export_id', 'row_count', 'state', 'evidence_visible','export_captured_at')})
        sources.sort(key=lambda s: s['export_captured_at'],reverse=True)
        drafts = []
        for meta in self._revisions(run_id, owner):
            rid = meta['recommendation_revision_id']
            results = self.recommendations.results(rid, owner)
            current = self.recommendations.review(rid, owner)
            reviews = []
            for path in self.recommendations.path(rid).glob('rvw_*.json'):
                value = self.recommendations.review(rid, owner, review_revision_id=path.stem)
                reviews.append({'review_revision_id': path.stem, 'created_at': value['created_at'],
                                'states': {k: v['status'] for k, v in value['decisions'].items()}})
            drafts.append({k: meta[k] for k in ('recommendation_revision_id', 'selected_row_ids', 'source_export_revision_id', 'state', 'created_at')})
            drafts[-1].update(compatible=meta['source_export_revision_id'] == source_revision_id,
                              incompatibility_reason='' if meta['source_export_revision_id'] == source_revision_id else 'different_frozen_coverage_source',
                              row_statuses={k: r['recommendation_status'] for k, r in results.items()},
                              review_revisions=sorted(reviews, key=lambda r: r['created_at'], reverse=True),
                              latest_review_revision_id=current['review_revision_id'])
        rows=self.source(run_id,owner,source_revision_id)[0] if source_revision_id else []
        return {'coverage_sources': sources, 'draft_revisions': drafts,
                'source_row_ordinals':{r['source_row_id']:r['source_record_ordinal'] for r in rows},
                'source_summary': accounting(rows) if source_revision_id else None}

    def _capture(self, run_id, owner, source_revision_id, selections, visible):
        rows, manifest = self.source(run_id, owner, source_revision_id)
        live = self.store.owned('runs', run_id, owner)
        by_id = {row['source_row_id']: row for row in rows}
        if len({s['source_row_id'] for s in selections}) != len(selections):
            raise AuditError('export_duplicate_row_selection')
        if not {s['source_row_id'] for s in selections} <= set(by_id):
            raise AuditError('export_unknown_source_row')
        pinned, captured, projection = {}, {}, []
        # Keep all selected draft/review captures consistent; explicit reviews are
        # immutable and an empty review ID deliberately means no decisions.
        with ExitStack() as stack:
            for rid in sorted({s['recommendation_revision_id'] for s in selections}):
                self.recommendations.owned(rid, owner)
                stack.enter_context(self.recommendations.lock(rid))
            for selected in selections:
                row_id, rid = selected['source_row_id'], selected['recommendation_revision_id']
                meta = self.recommendations.owned(rid, owner)
                if (meta['source_run_id'] != run_id or meta['source_export_revision_id'] != source_revision_id
                    or meta['source_export_id'] != manifest['export_id'] or meta['source_csv_sha256'] != manifest['csv_sha256']
                    or meta['source_manifest_sha256'] != canonical_sha256(manifest)
                    or meta['snapshot_id'] != manifest['snapshot_id']
                    or meta['source_row_hashes'].get(row_id) != canonical_sha256(by_id[row_id])):
                    raise AuditError('export_incompatible_coverage_source')
                self.recommendations.source(rid, owner)
                if not meta.get('results_sha256') or meta['state'] in {'queued', 'running'}:
                    raise AuditError('export_draft_not_finished')
                result = self.recommendations.results(rid, owner).get(row_id)
                if result is None or row_id not in meta['selected_row_ids']:
                    raise AuditError('export_unknown_draft_row')
                review_id = selected['review_revision_id']
                review = self.recommendations.review(rid, owner, review_revision_id=review_id) if review_id else EMPTY_REVIEW
                if review_id and review['recommendation_results_sha256'] != meta['results_sha256']:
                    raise AuditError('recommendation_review_mismatch')
                captured[row_id] = (meta, result, review)
                pinned[row_id] = {**selected, 'source_row_sha256': canonical_sha256(by_id[row_id]),
                                  'recommendation_results_sha256': meta['results_sha256'],
                                  'review_sha256': review.get('review_sha256', ''), 'versions': meta['versions'],
                                  'serving_identity': meta.get('serving_identity', {})}
                if meta.get('operational_policy'):
                    from knowledge_audit.operations import Budget,Limits
                    pinned[row_id]['operational_budget']=Budget(self.store,self.recommendations.path(rid),owner,Limits.from_settings(meta['operational_settings'],recommendation=True)).summary()
            states = Counter()
            for original in rows:
                row_id = original['source_row_id']
                meta, result, review = captured.get(row_id, ({'versions': EMPTY_VERSIONS}, {}, EMPTY_REVIEW))
                eligibility = self.recommendations._eligibility_from_source(original, manifest, live, owner)
                row = recommendation_row(original, result, eligibility, meta, review, visible)
                if row_id not in captured:
                    row['recommendation_status'] = 'not_selected' if eligibility['eligible'] else 'unavailable'
                for question in result.get('recommendations', []):
                    states[review['decisions'].get(row_id + ':' + question['recommendation_id'], {}).get('status', 'unreviewed')] += 1
                projection_reasons=list(eligibility['reason_codes'])
                if row_id in captured and result['recommendation_status']!='drafted':projection_reasons.append('recommendation_error_or_incomplete')
                if row_id in captured and meta['versions'].get('metadata_lookup')!=LOOKUP_VERSION:projection_reasons.append('recommendation_metadata_policy_changed')
                row.update(recommendation_projection_reasons=projection_reasons, recommendation_approval_allowed=row_id in captured and not projection_reasons,
                           schema_version='coverage-run-csv-1', source_coverage_export_revision_id=source_revision_id,
                           recommendation_selection='selected' if row_id in captured else 'not_selected')
                if visible and not manifest['evidence_visible']:row['evidence_visibility']='source_restricted'
                projection.append(row)
        available = self._revisions(run_id, owner)
        selected_pairs = {(s['source_row_id'], s['recommendation_revision_id']) for s in selections}
        unselected = [{'source_row_id': row_id, 'recommendation_revision_id': m['recommendation_revision_id'],
                       'compatible': m['source_export_revision_id'] == source_revision_id,
                       'reason': 'not_selected' if m['source_export_revision_id'] == source_revision_id else 'different_frozen_coverage_source'}
                      for m in available for row_id in m['selected_row_ids'] if (row_id, m['recommendation_revision_id']) not in selected_pairs]
        summary = {**accounting(rows), 'rows_with_selected_recommendations': len(selections),
                   'recommendation_review_states': dict(states), 'unselected_drafts': unselected,
                   'incompatible_draft_count': sum(not d['compatible'] for d in unselected),
                   'selected_draft_states': dict(Counter(v[1]['recommendation_status'] for v in captured.values()))}
        return projection, manifest, pinned, summary

    def preview(self, run_id, owner, source_revision_id, selections, visible):
        _, manifest, pinned, summary = self._capture(run_id, owner, source_revision_id, selections, visible)
        return {'source_export_revision_id': source_revision_id, 'source_export_id': manifest['export_id'],
                'selection_map': {k: {f: v[f] for f in ('recommendation_revision_id', 'review_revision_id')} for k, v in pinned.items()},
                'summary': summary, 'evidence_visible': visible}

    @protected_method
    def create(self, run_id, owner, source_revision_id, selections, visible):
        rows, source, pinned, summary = self._capture(run_id, owner, source_revision_id, selections, visible)
        revision_id = 'runex_' + secrets.token_hex(16)
        for row in rows:
            row['export_revision_id'] = revision_id
        body, export_id = encode_csv(rows, tuple(rows[0]), source['row_ids'])
        manifest = {'schema_version': 'coverage-run-manifest-1', 'run_id': run_id, 'owner_id': owner,
                    'export_revision_id': revision_id, 'export_id': export_id, 'csv_sha256': hashlib.sha256(body).hexdigest(),
                    'row_ids': source['row_ids'], 'row_count': len(rows), 'snapshot_id': source['snapshot_id'],
                    'source_coverage_export_revision_id': source_revision_id, 'source_coverage_export_id': source['export_id'],
                    'source_coverage_csv_sha256': source['csv_sha256'], 'source_coverage_manifest_sha256': canonical_sha256(source),
                    'coverage_source_manifest': source, 'revision_selection_map': pinned, 'summary': summary,
                    'captured_at': now(), 'evidence_visible': visible, 'coverage_state': source['state'],
                    'input_scope': source.get('input_scope', 'pilot_subset_full_input_export'), 'human_gap_review_status': 'not_reviewed',
                    'approval_scope': 'question_taxonomy_only_no_factual_answer_or_confirmed_kb_absence',
                    'csv_display_policy': 'formula-prefix-map-1', 'csv_escaped_cells': csv_display_escapes(rows)}
        directory = self._directory(run_id, visible) / revision_id
        private_directory(directory)
        private_write(directory / 'coverage.csv', body)
        private_json(directory / 'manifest.json', manifest)
        return manifest

    def _directory(self, run_id, visible):
        root = private_directory(self.store._path('runs', run_id) / 'combined-exports')
        return private_directory(root / ('evidence' if visible else 'restricted'))

    @protected_method
    def download(self, run_id, owner, visible, revision_id):
        self.store.owned('runs', run_id, owner)
        if not re.fullmatch(r'runex_[0-9a-f]{32}', revision_id):
            raise AuditError('invalid_artifact_id')
        path = self._directory(run_id, visible) / revision_id
        try:
            manifest = self.store.read(path / 'manifest.json')
            file = path / 'coverage.csv'
            if file.is_symlink() or file.stat().st_uid != os.getuid() or file.stat().st_mode & 0o077:
                raise AuditError('artifact_file_permissions')
            body = file.read_bytes()
        except OSError:
            raise AuditError('artifact_not_found') from None
        if (manifest['owner_id'] != owner or manifest['run_id'] != run_id or manifest['export_revision_id'] != revision_id
            or manifest['evidence_visible'] != visible or hashlib.sha256(body).hexdigest() != manifest['csv_sha256']):
            raise AuditError('export_identity_mismatch')
        rows = list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'), newline='')))
        if [r['source_row_id'] for r in rows] != manifest['row_ids'] or any(r['export_id'] != manifest['export_id'] for r in rows):
            raise AuditError('export_identity_mismatch')
        return body, manifest
