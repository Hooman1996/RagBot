"""Separate immutable source, draft, review and combined-export revisions."""
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import os
import re
import secrets

from knowledge_audit.privacy import AuditError,private_directory,private_json,private_write,formula_safe
from knowledge_audit.store import now
from knowledge_audit.retention import protected_method
from knowledge_audit.export import encode_csv,ARRAY_FIELDS,MAP_FIELDS,STRUCTURED_DEFAULTS,_redact
from knowledge_audit.recommendations import eligibility,normalized,MetadataIndex,LOOKUP_VERSION
from knowledge_audit.recommendation_prompts import prompt_identity
from utils.read_only_audit import canonical_sha256


def decode_coverage(body,manifest):
    if not manifest['evidence_visible']:raise AuditError('recommendation_source_evidence_required')
    if hashlib.sha256(body).hexdigest()!=manifest['csv_sha256']:raise AuditError('export_identity_mismatch')
    result=[]
    for row in csv.DictReader(io.StringIO(body.decode('utf-8-sig'))):
        for key,value in row.items():
            escapes=manifest.get('csv_escaped_cells')
            if escapes is not None:
                if key in escapes.get(row['source_row_id'],[]):
                    if not value.startswith("'"):raise AuditError('export_identity_mismatch')
                    value=value[1:]
            elif value.startswith("'") and formula_safe(value[1:])==value:value=value[1:]
            if key in ARRAY_FIELDS or key in MAP_FIELDS or key in STRUCTURED_DEFAULTS:value=json.loads(value)
            if key in {'output_recovery_count','source_record_ordinal','evaluated_entry_count','batch_max_entries'} and value not in {'','None'} and isinstance(value,str):value=int(value)
            row[key]=value
        result.append(row)
    if [r['source_row_id'] for r in result]!=manifest['row_ids'] or any(r['export_id']!=manifest['export_id'] for r in result):raise AuditError('export_identity_mismatch')
    return result


class RecommendationStore:
    def __init__(self,store):
        self.store=store;self.root=private_directory(store.root/'recommendations')

    def path(self,rid):
        if not re.fullmatch(r'rec_[0-9a-f]{32}',rid):raise AuditError('invalid_artifact_id')
        path=self.root/rid
        if not path.is_dir():raise AuditError('artifact_not_found')
        return private_directory(path)

    def owned(self,rid,owner):
        try:meta=self.store.read(self.path(rid)/'meta.json')
        except OSError:raise AuditError('artifact_not_found') from None
        if meta['owner_id']!=owner:raise AuditError('artifact_not_found')
        return meta

    @contextmanager
    def lock(self,rid):
        # Existing filesystem lease pattern, scoped to new artifacts only.
        import fcntl
        fd=os.open(self.path(rid)/'revision.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX);yield
        finally:os.close(fd)

    @protected_method
    def source(self,rid,owner):
        meta=self.owned(rid,owner);source=self.store.read(self.path(rid)/'source.json')
        if canonical_sha256(source)!=meta['source_sha256']:raise AuditError('recommendation_source_drift')
        return source

    def observations(self,source_meta,row,owner):
        """Comparable means same input row, snapshot and normalized resolved intent.

        Model/settings changes do not negate a known KB full proof on that source.
        No historical observation is overwritten or declared human ground truth.
        """
        if row.get('outcome') not in {'possible_gap','possible_partial_gap'}:return []
        found=[]
        for meta in self.store.list_owned('runs',owner):
            if meta['run_id']==source_meta['run_id'] or meta['input_id']!=source_meta['input_id'] or meta['snapshot_id']!=source_meta['snapshot_id'] or row['source_row_id'] not in meta['row_ids'] or meta['state']=='incompatible':continue
            other=self.store.row(meta['run_id'],row['source_row_id'],owner)
            if other.get('coverage_status')!='full' or other.get('verification_result')!='accepted' or other.get('outcome') not in {'covered_reachable','covered_not_reachable','needs_review'}:continue
            if not other.get('standalone_query_redacted') or normalized(other['standalone_query_redacted'])!=normalized(row.get('standalone_query_redacted')):continue
            from knowledge_audit.evidence import EvidenceIndex
            index=EvidenceIndex(self.store.snapshot(meta['snapshot_id'],owner))
            try:
                for ref in other.get('supporting_sentence_refs',[]):index.resolve(ref)
            except AuditError:continue
            if not other.get('supporting_sentence_refs'):continue
            found.append({'run_id':meta['run_id'],'source_row_id':row['source_row_id'],'snapshot_id':meta['snapshot_id'],
                'result_sha256':canonical_sha256(other),'coverage_status':'full','verification_result':'accepted',
                'comparison_rule':'same_input_row_snapshot_normalized_resolved_intent','human_ground_truth':False})
        return found

    @protected_method
    def create(self,run_id,owner,export_revision_id,row_ids):
        if not row_ids or len(row_ids)>5 or len(set(row_ids))!=len(row_ids):raise AuditError('invalid_pilot_selection')
        meta=self.store.owned('runs',run_id,owner)
        body,manifest=self.store.export_revision(run_id,owner,True,export_revision_id)
        rows=decode_coverage(body,manifest)
        if manifest['run_id']!=run_id or manifest['state']=='incompatible' or not set(row_ids)<=set(manifest['row_ids']):raise AuditError('recommendation_source_drift')
        _,redactor=self.store.dataset(meta['dataset_id'],owner)
        snapshot=self.store.snapshot(manifest['snapshot_id'],owner)
        index=MetadataIndex(snapshot)
        rid='rec_'+secrets.token_hex(16);path=private_directory(self.root/rid)
        source={'manifest':manifest,'rows':rows}
        private_json(path/'source.json',source)
        private_json(path/'metadata-index.json',{'version':'snapshot-metadata-index-1','snapshot_id':index.snapshot_id,
            'metadata_index_id':index.identity,'records':index.records,'taxonomy_paths':index.paths})
        results={}
        for row in rows:
            if row['source_row_id'] not in row_ids:continue
            selected=eligibility(row,manifest,self.observations(manifest,row,owner))
            results[row['source_row_id']]={'eligibility':selected,'recommendation_status':'pending' if selected['eligible'] else 'unavailable',
                'recommendations':[],'gap_specifications':[],'recommendation_review_status':'unreviewed','human_gap_review_status':'not_reviewed'}
        out={'version':'recommendation-revision-1','recommendation_revision_id':rid,'owner_id':owner,'created_at':now(),
            'source_run_id':run_id,'snapshot_id':manifest['snapshot_id'],'source_export_id':manifest['export_id'],
            'source_export_revision_id':manifest['export_revision_id'],'source_csv_sha256':manifest['csv_sha256'],
            'source_manifest_sha256':canonical_sha256(manifest),'source_sha256':canonical_sha256(source),
            'selected_row_ids':row_ids,'source_row_ids':manifest['row_ids'],'source_row_hashes':{r['source_row_id']:canonical_sha256(r) for r in rows},
            'metadata_index_id':index.identity,'state':'queued','phase':'queued','versions':recommendation_versions(),
            'human_gap_review_status':'not_reviewed','calibration_status':'real_query_calibration_pending','cancel_requested':False}
        from knowledge_audit.operations import Budget,Limits
        from knowledge_audit.settings import load_coverage_settings
        settings=load_coverage_settings().manifest()
        out['operational_settings']=settings
        out['operational_policy']='audit-operations-1'
        Budget(self.store,path,owner,Limits.from_settings(settings,recommendation=True))
        private_json(path/'results.json',_redact(results,redactor));private_json(path/'meta.json',out)
        return out

    @protected_method
    def results(self,rid,owner):
        self.owned(rid,owner)
        path=self.path(rid)
        value=self.store.read(path/'results.final.json') if (path/'results.final.json').exists() else self.store.read(path/'results.json')
        meta=self.owned(rid,owner)
        if meta.get('results_sha256') and canonical_sha256(value)!=meta['results_sha256']:raise AuditError('recommendation_result_drift')
        return value

    def effective_eligibility(self,rid,owner,row):
        meta=self.owned(rid,owner);source=self.source(rid,owner)
        live=self.store.owned('runs',meta['source_run_id'],owner)
        return self._eligibility_from_source(row,source['manifest'],live,owner)

    def _eligibility_from_source(self,row,manifest,live,owner):
        bound=dict(manifest)
        if live['state']=='incompatible':bound['state']='incompatible'
        return eligibility(row,bound,self.observations(bound,row,owner))

    def effective_results(self,rid,owner):
        results=self.results(rid,owner);source=self.source(rid,owner)
        meta=self.owned(rid,owner);live=self.store.owned('runs',meta['source_run_id'],owner)
        for row in source['rows']:
            if row['source_row_id'] not in results:continue
            value=results[row['source_row_id']]
            value['eligibility']=self._eligibility_from_source(row,source['manifest'],live,owner)
            if value['recommendation_status']=='drafted' and not value['eligibility']['eligible']:value['recommendation_status']='needs_review'
            value['approval_allowed']=value['eligibility']['eligible'] and meta['versions']['metadata_lookup']==LOOKUP_VERSION
            value['review_unavailable_reasons']=[] if meta['versions']['metadata_lookup']==LOOKUP_VERSION else ['recommendation_metadata_policy_changed']
            if value['recommendation_status']=='drafted' and not value['approval_allowed']:value['recommendation_status']='needs_review'
        return results

    @protected_method
    def save_progress(self,rid,owner,meta,results):
        self.owned(rid,owner)
        with self.lock(rid):
            self.store.write(self.path(rid)/'results.json',results)
            self.store.write(self.path(rid)/'meta.json',meta)

    @protected_method
    def finish(self,rid,owner,meta,results):
        self.owned(rid,owner)
        with self.lock(rid):
            private_json(self.path(rid)/'results.final.json',results)
            meta.update(results_sha256=canonical_sha256(results),finished_at=now())
            self.store.write(self.path(rid)/'meta.json',meta)

    def list_for_row(self,run_id,row_id,owner):
        self.store.row(run_id,row_id,owner)
        values=[]
        for p in self.root.glob('rec_*'):
            try:meta=self.owned(p.name,owner)
            except (AuditError,OSError):continue
            if meta['source_run_id']==run_id and row_id in meta['selected_row_ids']:values.append(meta)
        return sorted(values,key=lambda m:m['created_at'],reverse=True)

    def review(self,rid,owner,*,review_revision_id=None):
        self.owned(rid,owner);path=self.path(rid)
        if review_revision_id is None:
            if not (path/'latest-review.json').exists():return {'version':'recommendation-review-1','review_revision_id':'','decisions':{},'status':'unreviewed'}
            pointer=self.store.read(path/'latest-review.json');review_revision_id=pointer['review_revision_id']
        if not re.fullmatch(r'rvw_[0-9a-f]{32}',review_revision_id):raise AuditError('invalid_artifact_id')
        value=self.store.read(path/(review_revision_id+'.json'))
        if value['recommendation_revision_id']!=rid:raise AuditError('recommendation_review_mismatch')
        if canonical_sha256({k:v for k,v in value.items() if k!='review_sha256'})!=value['review_sha256']:raise AuditError('recommendation_review_mismatch')
        return value

    @protected_method
    def decide(self,rid,owner,row_id,question_id,decision,note):
        meta=self.owned(rid,owner)
        with self.lock(rid):
            results=self.results(rid,owner);result=results.get(row_id)
            if meta['state']!='completed' or not result or result['recommendation_status']!='drafted' or question_id not in {r['recommendation_id'] for r in result['recommendations']}:raise AuditError('recommendation_not_reviewable')
            if decision not in {'unreviewed','approved','rejected','needs_changes'}:raise AuditError('invalid_review_decision')
            if decision=='approved' and meta['versions']['metadata_lookup']!=LOOKUP_VERSION:raise AuditError('recommendation_metadata_policy_changed')
            source=self.source(rid,owner);row=next(r for r in source['rows'] if r['source_row_id']==row_id)
            if decision=='approved' and not self.effective_eligibility(rid,owner,row)['eligible']:raise AuditError('recommendation_source_requires_review')
            coverage=self.store.owned('runs',meta['source_run_id'],owner);_,redactor=self.store.dataset(coverage['dataset_id'],owner)
            old=self.review(rid,owner);review_id='rvw_'+secrets.token_hex(16)
            value={'version':'recommendation-review-1','review_revision_id':review_id,'recommendation_revision_id':rid,
                'recommendation_results_sha256':meta['results_sha256'],'previous_review_revision_id':old['review_revision_id'],
                'created_at':now(),'reviewer_user_id':owner,'approval_scope':'question_taxonomy_proposal_only_no_answer_or_kb_write',
                'decisions':{**old['decisions'],row_id+':'+question_id:{'source_row_id':row_id,'recommendation_id':question_id,
                    'status':decision,'note':redactor.text(note)}}}
            value['review_sha256']=canonical_sha256(value)
            private_json(self.path(rid)/(review_id+'.json'),value)
            self.store.write(self.path(rid)/'latest-review.json',{'review_revision_id':review_id})
            return value

    def metadata(self,rid,owner,faq_id):
        self.owned(rid,owner);index=self.store.read(self.path(rid)/'metadata-index.json')
        rows=[r for r in index['records'] if r['faq_entry_id']==faq_id]
        if not rows:raise AuditError('artifact_not_found')
        return {'snapshot_id':index['snapshot_id'],'faq_entry_id':faq_id,'metadata':rows,'coverage_claim':'not_established_by_title'}

    @protected_method
    def compose(self,rid,owner,visible,review_revision_id=None):
        meta=self.owned(rid,owner)
        with self.lock(rid):
            source=self.source(rid,owner);results=self.results(rid,owner);review=self.review(rid,owner,review_revision_id=review_revision_id)
            live=self.store.owned('runs',meta['source_run_id'],owner)
            rows=[]
            for original in source['rows']:
                row=dict(original);result=results.get(row['source_row_id'],{})
                selected=self._eligibility_from_source(original,source['manifest'],live,owner)
                status=result.get('recommendation_status','not_selected' if selected['eligible'] else 'unavailable')
                if selected['reason_codes'] and status=='drafted':status='needs_review'
                if status=='drafted' and meta['versions']['metadata_lookup']!=LOOKUP_VERSION:status='needs_review'
                row=recommendation_row(original,result,selected,meta,review,visible)
                rows.append(row)
            revision_id='rex_'+secrets.token_hex(16)
            for row in rows:row['export_revision_id']=revision_id
            fields=tuple(rows[0])
            body,export_id=encode_csv(rows,fields,source['manifest']['row_ids'])
            manifest={'schema_version':'coverage-recommendations-manifest-1','export_revision_id':revision_id,'export_id':export_id,
                'csv_sha256':hashlib.sha256(body).hexdigest(),'row_ids':source['manifest']['row_ids'],'row_count':len(rows),'captured_at':now(),
                'recommendation_revision_id':rid,'recommendation_state':meta['state'],'recommendation_results_sha256':canonical_sha256(results),
                'recommendation_versions':meta['versions'],'recommendation_serving_identity':meta.get('serving_identity',{}),
                'review_revision_id':review['review_revision_id'],'review_sha256':review.get('review_sha256',''),
                'coverage_source_manifest':source['manifest'],'source_sha256':meta['source_sha256'],
                'evidence_visible':visible,'human_gap_review_status':'not_reviewed','calibration_status':'real_query_calibration_pending'}
            if meta.get('operational_policy'):
                from knowledge_audit.operations import Budget,Limits
                manifest['recommendation_budget']=Budget(self.store,self.path(rid),owner,Limits.from_settings(meta['operational_settings'],recommendation=True)).summary()
            manifest['approval_scope']='question_taxonomy_proposal_only_no_answer_or_kb_write'
            directory=private_directory(private_directory(private_directory(self.path(rid)/'exports')/('evidence' if visible else 'restricted'))/revision_id)
            private_write(directory/'coverage.csv',body);private_json(directory/'manifest.json',manifest)
            return manifest

    @protected_method
    def download(self,rid,owner,visible,revision_id):
        self.owned(rid,owner)
        if not re.fullmatch(r'rex_[0-9a-f]{32}',revision_id):raise AuditError('invalid_artifact_id')
        path=self.path(rid)/'exports'/('evidence' if visible else 'restricted')/revision_id
        try:
            manifest=self.store.read(path/'manifest.json');file=path/'coverage.csv'
            if file.is_symlink() or file.stat().st_uid!=os.getuid() or file.stat().st_mode&0o077:raise AuditError('artifact_file_permissions')
            body=file.read_bytes()
        except OSError:raise AuditError('artifact_not_found') from None
        if hashlib.sha256(body).hexdigest()!=manifest['csv_sha256'] or manifest['evidence_visible']!=visible or manifest['recommendation_revision_id']!=rid:raise AuditError('export_identity_mismatch')
        return body,manifest


def recommendation_row(original,result,selected,meta,review,visible):
    """Shared projection; A4 callers retain their existing schema and meanings."""
    row=dict(original)
    rid=meta.get("recommendation_revision_id", "")
    status=result.get("recommendation_status", "not_selected" if selected["eligible"] else "unavailable")
    if selected["reason_codes"] and status=="drafted":status="needs_review"
    if status=="drafted" and meta.get("versions",{}).get("metadata_lookup")!=LOOKUP_VERSION:status="needs_review"
    drafts=result.get('recommendations',[]) if visible else []
    decisions=[review['decisions'].get(original['source_row_id']+':'+r['recommendation_id'],{'status':'unreviewed'}) for r in result.get('recommendations',[])]
    states={d['status'] for d in decisions}
    row.update(schema_version='coverage-recommendations-csv-1',export_id='',export_revision_id='',
        source_coverage_evidence_visibility=original.get('evidence_visibility',''),evidence_visibility='visible' if visible else 'restricted',
        source_coverage_export_id=original['export_id'],source_coverage_row_sha256=canonical_sha256(original),
        recommendation_revision_id=rid,review_revision_id=review['review_revision_id'],recommendation_status=status,
        recommendation_review_status=next(iter(states)) if len(states)==1 else 'mixed' if states else 'unreviewed',
        human_gap_review_status='not_reviewed',calibration_status='real_query_calibration_pending',
        recommendation_approval_scope='question_taxonomy_only_no_factual_answer_or_kb_write',
        recommendations=[{**r,'review':d} for r,d in zip(drafts,decisions)],
        gap_specifications=result.get('gap_specifications',[]) if visible else [],
        recommendation_eligibility=selected['eligible'],recommendation_unavailable_reasons=selected['reason_codes'],
        recommendation_error_code=result.get('error_code',''),recommendation_prompt_versions=meta['versions']['prompts'],
        recommendation_model_versions=meta.get('serving_identity',{}),
        recommendation_code_id=meta['versions']['code_id'],title_lookup_scope={k:v for k,v in result.get('title_lookup',{}).items() if k not in {'titles','taxonomy_paths'}},
        proposed_question=[r['recommended_question'] for r in drafts],category=[r['category'] for r in drafts],subcategory=[r['subcategory'] for r in drafts],
        proposed_new_category=[r['category'] for r in drafts if r['taxonomy_status']=='proposed_new_category'],
        proposed_new_subcategory=[r['subcategory'] for r in drafts if r['taxonomy_status']=='proposed_new_subcategory'],
        related_existing_faq_ids=list(dict.fromkeys(i for r in drafts for i in r['related_faq_ids'])),
        equivalent_existing_faq_ids=list(dict.fromkeys(i for r in drafts for i in r['equivalent_faq_ids'])))
    if not visible:
        from knowledge_audit.export import RESTRICTED_FIELDS
        for key in RESTRICTED_FIELDS:
            if key in row:row[key]=[]
        for key in ('explanation','verification_reason','error_reason'):row[key]=''
        row['evidence_phases']={}
    return row


def recommendation_versions():
    from knowledge_audit.runtime import code_identity
    code=code_identity()
    return {'prompts':prompt_identity(),'code':code,'code_id':canonical_sha256(code),'eligibility_policy':'recommendation-eligibility-1',
        'metadata_lookup':LOOKUP_VERSION,'approval_scope':'question_taxonomy_only','recovery_policy':'json-invalid-stop-one-fresh-response-1'}
