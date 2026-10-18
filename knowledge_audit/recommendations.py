"""Question-only analysis of immutable, eligible coverage findings."""
import copy
import re
from pydantic import ValidationError
from knowledge_audit.evidence import EvidenceIndex
from knowledge_audit.privacy import AuditError
from knowledge_audit.schemas import Aspect
from knowledge_audit.recommendation_schemas import SCHEMAS
from utils.persian_normalization import normalize_persian_text
from utils.read_only_audit import canonical_sha256

LOOKUP_VERSION='snapshot-titles-taxonomy-2'
TITLE_LIMIT=20

SAFE_CODES=frozenset({'invalid_source_aspects','invalid_gap_identity','invented_missing_aspect','invented_gap_condition',
    'missing_gap_review_requirements','invalid_partial_support_reference','invented_numeric_premise','missing_gap_aspects',
    'invalid_recommendation_identity','question_only_required','invalid_recommendation_faq_id','invalid_equivalence_basis',
    'title_cannot_prove_incomplete_answer','existing_faq_reference_required','exact_title_requires_review',
    'equivalent_title_requires_review','invalid_taxonomy_path','taxonomy_collision_requires_review',
    'invalid_proposed_taxonomy','invalid_new_subcategory','invalid_new_category','unaddressed_missing_aspects',
    'invalid_citation','diagnostic_budget_exhausted','redaction_text_limit','missing_partial_support_reference'})


def safe_error(error):
    from knowledge_audit.failures import TRANSPORT_CODES,VALIDATION_CODES,category
    code=str(error) if isinstance(error,AuditError) else ''
    return code if code in SAFE_CODES|TRANSPORT_CODES|VALIDATION_CODES else category(error)


def normalized(value):
    return ' '.join(normalize_persian_text(value or '').replace('\u200c',' ').casefold().split())


def title_key(value):
    # Production preparation changes punctuation spacing; compare lexical words,
    # without treating title equivalence as answer coverage or incompleteness.
    return tuple(re.findall(r'\w+',normalized(value)))


def eligibility(row,meta,observations=()):
    reasons=[]
    outcome=row.get('outcome')
    if outcome=='covered_not_reachable':reasons.append('retrieval_improvement_not_kb_gap')
    elif outcome=='covered_reachable':reasons.append('knowledge_already_covered')
    elif outcome not in {'possible_gap','possible_partial_gap'}:reasons.append('coverage_'+(outcome if outcome in {'error','pending','excluded','needs_context','needs_review'} else 'not_eligible'))
    if row.get('processing_status')!='completed':reasons.append('coverage_not_completed')
    if row.get('scope_status')!='kb_question':reasons.append('scope_not_confirmed')
    if row.get('preparation_status')!='prepared':reasons.append('preparation_not_resolved')
    missing=row.get('unresolved_aspects',[]);aspects=row.get('requested_aspects',[])
    ids=[a.get('aspect_id') for a in aspects if isinstance(a,dict)]
    mids=[a.get('aspect_id') for a in missing if isinstance(a,dict)]
    if not mids or len(set(mids))!=len(mids) or not set(mids)<=set(ids):reasons.append('missing_aspects_not_identified')
    if outcome=='possible_gap' and row.get('coverage_status')!='unsupported' or outcome=='possible_partial_gap' and row.get('coverage_status')!='partial':reasons.append('coverage_dimensions_inconsistent')
    if row.get('error_code') or row.get('review_codes') or any(row.get('review_codes_by_phase',{}).values()):reasons.append('unresolved_evaluation_issue')
    if row.get('verification_result') in {'rejected','uncertain'}:reasons.append('verification_unresolved')
    if any('kb_redaction_affected' in (codes or []) for codes in (row.get('review_codes'),row.get('residual_review_codes'),*row.get('review_codes_by_phase',{}).values())):reasons.append('kb_redaction_unresolved')
    for name in ('audit_assessment','production_assessment'):
        if row.get(name,{}).get('conflicts') or row.get(name,{}).get('review_codes'):reasons.append('compatibility_or_evaluation_unresolved')
    if any(row.get(k) for k in ('conflicts','ambiguities')) or row.get('aspect_checklist',{}).get('ambiguities'):reasons.append('context_or_compatibility_unresolved')
    if any(c in {'unresolved_context','redaction_changed_query','redaction_changed_rewrite','redaction_changed_history'} for c in row.get('uncertainty_codes',[])):reasons.append('context_or_redaction_unresolved')
    if row.get('validation_diagnostics') and not row.get('output_recovery_count'):reasons.append('unresolved_validation_issue')
    if any(d.get('failure_category') not in {'none','schema_validation'} for d in row.get('failure_diagnostics',[])):reasons.append('unresolved_model_failure')
    scope=row.get('evaluation_scope',{})
    if not scope or scope.get('whole_kb_absence_proven') is not False or row.get('stopping_reason') not in {'candidate_exhausted','evaluation_limit'}:reasons.append('evaluation_scope_not_established')
    if meta.get('state')=='incompatible' or row.get('kb_snapshot_id')!=meta.get('snapshot_id'):reasons.append('incompatible_snapshot_or_run')
    if observations:reasons.append('conflicting_full_coverage_observation')
    return {'version':'recommendation-eligibility-1','eligible':not reasons,'reason_codes':list(dict.fromkeys(reasons)),
        'independent_human_gap_confirmation':'not_reviewed','calibration_status':'real_query_calibration_pending',
        'contradictory_observations':list(observations)}


class MetadataIndex:
    """Only metadata enters the recommender; answers cannot influence lookup."""
    def __init__(self,snapshot):
        self.snapshot_id=snapshot['snapshot_id'];self.records=[];paths={}
        for source in snapshot['records']:
            category=source.get('main_category');subcategory=source.get('sub_category') or None
            if category is not None and not str(category).strip():category=None
            title=source.get('question')
            if not isinstance(title,str) or not source.get('faq_entry_id'):continue
            record={'faq_entry_id':source['faq_entry_id'],'chunk_id':source['chunk_id'],'question_title':title,
                'category':category,'subcategory':subcategory}
            self.records.append(record)
            if category is not None:
                key=(category,subcategory)
                paths[key]={'taxonomy_path_id':'path_'+canonical_sha256(key)[:24],'category':category,'subcategory':subcategory}
        self.paths=list(paths.values())
        groups={};categories={}
        for p in self.paths:
            groups.setdefault((normalized(p['category']),normalized(p['subcategory'])),[]).append(p)
            categories.setdefault(normalized(p['category']),set()).add(p['category'])
        for group in groups.values():
            for p in group:
                p['normalization_collision']=len(group)>1
                p['category_normalization_collision']=len(categories[normalized(p['category'])])>1
        self.identity=canonical_sha256({'version':LOOKUP_VERSION,'snapshot_id':self.snapshot_id,'records':self.records,'paths':self.paths})

    def lookup(self,question,missing,supported):
        query=normalized(question);query_key=title_key(question);tokens=set(re.findall(r'\w+',query+' '+' '.join(normalized(a['description']) for a in missing)))
        scored=[]
        for r in self.records:
            title=normalized(r['question_title']);words=set(re.findall(r'\w+',title));overlap=len(words&tokens)
            exact=title_key(r['question_title'])==query_key
            if overlap or r['chunk_id'] in supported or exact:
                score=1000*exact+100*(r['chunk_id'] in supported)+overlap/max(1,len(words|tokens))
                scored.append((score,r))
        ordered=sorted(scored,key=lambda pair:(-pair[0],str(pair[1]['faq_entry_id']),str(pair[1]['chunk_id'])))
        selected=[]
        for _,r in ordered[:TITLE_LIMIT]:
            selected.append({**r,'exact_title_match':title_key(r['question_title'])==query_key,
                'evaluated_partial_support':r['chunk_id'] in supported})
        return {'version':LOOKUP_VERSION,'snapshot_id':self.snapshot_id,'metadata_index_id':self.identity,
            'method':'persian_normalized_words_overlap_support_first_exact_tokens','metadata_records_examined':len(self.records),
            'candidate_count':len(scored),'selected_count':len(selected),'title_limit':TITLE_LIMIT,
            'scope':'bounded_title_candidates_not_coverage_or_equivalence_proof',
            'taxonomy_paths':copy.deepcopy(self.paths),'titles':selected,
            'missing_category_count':sum(r['category'] is None for r in self.records)}


def analyst_input(row,meta):
    try:
        for a in row['requested_aspects']:Aspect.model_validate(a)
        for a in row['unresolved_aspects']:Aspect.model_validate(a)
    except (ValidationError,KeyError):raise AuditError('invalid_source_aspects') from None
    supports=[]
    for aspect in row.get('supported_aspects',[]):
        for s in aspect.get('supports',[]):
            supports.append({k:s[k] for k in ('aspect_id','entry_id','citations','applicability','conditions','dependencies','explanation') if k in s})
    return {'resolved_question':row['standalone_query_redacted'],'requested_aspects':row['requested_aspects'],
        'missing_aspects':row['unresolved_aspects'],'partial_support':supports,
        'evaluation_scope':row['evaluation_scope'],'stopping_reason':row['stopping_reason'],
        'uncertainty':row.get('review_codes',[]),'human_gap_confirmation':'not_reviewed',
        'source':{'run_id':meta['run_id'],'snapshot_id':meta['snapshot_id'],'source_row_id':row['source_row_id'],
            'source_result_sha256':canonical_sha256(row),'coverage_export_id':meta['export_id']}}


def _no_new_numbers(value,provided):
    value=re.sub(r'(?<!\w)[agq][1-9][0-9]?(?!\w)','',value)
    numbers=set(re.findall(r'\d+(?:[.:/]\d+)*',value))
    if not numbers<=set(re.findall(r'\d+(?:[.:/]\d+)*',provided)):raise AuditError('invented_numeric_premise')


def validate_gaps(value,payload,index):
    value=SCHEMAS['gap_analysis'].model_validate(value).model_dump()
    missing={a['aspect_id'] for a in payload['missing_aspects']};covered=set()
    allowed_refs={canonical_sha256(c) for s in payload['partial_support'] for c in s['citations']}
    allowed_conditions={c for a in payload['requested_aspects'] for c in a['conditions']}|{c for s in payload['partial_support'] for c in s.get('conditions',[])}
    if [g['gap_id'] for g in value['gaps']]!=['g'+str(i) for i in range(1,len(value['gaps'])+1)]:raise AuditError('invalid_gap_identity')
    for g in value['gaps']:
        ids=set(g['missing_aspect_ids'])
        if len(ids)!=len(g['missing_aspect_ids']) or not ids<=missing or covered&ids:raise AuditError('invented_missing_aspect')
        covered.update(ids)
        if not set(g['conditions'])<=allowed_conditions:raise AuditError('invented_gap_condition')
        if set(g['search_scope_limitations'])!={'bounded_search_not_exhaustive','human_labels_pending'} or not {'independent_gap_review','knowledge_team_confirmation'}<=set(g['review_requirements']):raise AuditError('missing_gap_review_requirements')
        for ref in g['partial_support_references']:
            if canonical_sha256(ref) not in allowed_refs:raise AuditError('invalid_partial_support_reference')
            index.resolve(ref)
        _no_new_numbers(g['missing_information'],payload['resolved_question']+' '.join(a['description']+' '.join(a['conditions']) for a in payload['requested_aspects']))
    if covered!=missing:raise AuditError('missing_gap_aspects')
    if allowed_refs and not any(g['partial_support_references'] for g in value['gaps']):raise AuditError('missing_partial_support_reference')
    return value


def validate_questions(value,gaps,lookup,row):
    value=SCHEMAS['question_recommendation'].model_validate(value).model_dump()
    allowed={g['gap_id']:set(g['missing_aspect_ids']) for g in gaps['gaps']};covered=set()
    titles={r['faq_entry_id']:r for r in lookup['titles']};paths={p['taxonomy_path_id']:p for p in lookup['taxonomy_paths']}
    cats={p['category'] for p in paths.values()}
    exact=[r for r in titles.values() if r['exact_title_match']]
    if [r['recommendation_id'] for r in value['recommendations']]!=['q'+str(i) for i in range(1,len(value['recommendations'])+1)]:raise AuditError('invalid_recommendation_identity')
    for r in value['recommendations']:
        if len(set(r['gap_ids']))!=len(r['gap_ids']) or not set(r['gap_ids'])<=set(allowed):raise AuditError('invalid_gap_identity')
        ids=set().union(*(allowed[g] for g in r['gap_ids']))
        if len(set(r['missing_aspect_ids']))!=len(r['missing_aspect_ids']) or not set(r['missing_aspect_ids'])<=ids or not r['missing_aspect_ids']:raise AuditError('invented_missing_aspect')
        covered.update(r['missing_aspect_ids'])
        if not r['recommended_question'].rstrip().endswith(('?','؟')):raise AuditError('question_only_required')
        _no_new_numbers(r['recommended_question'],row['standalone_query_redacted']+' '.join(a['description']+' '.join(a['conditions']) for a in row['requested_aspects']))
        refs=set(r['related_faq_ids']+r['equivalent_faq_ids'])
        if not refs<=set(titles):raise AuditError('invalid_recommendation_faq_id')
        if bool(r['equivalent_faq_ids'])!=(r['equivalence_basis']!='none'):raise AuditError('invalid_equivalence_basis')
        if r['equivalence_basis']=='evaluated_partial_support' and any(not titles[i]['evaluated_partial_support'] for i in r['equivalent_faq_ids']):raise AuditError('title_cannot_prove_incomplete_answer')
        if r['action']=='review_existing_faq' and not refs:raise AuditError('existing_faq_reference_required')
        if exact and r['action']=='new_question':raise AuditError('exact_title_requires_review')
        if r['equivalent_faq_ids'] and r['action']=='new_question':raise AuditError('equivalent_title_requires_review')
        category,sub=r['category'],r['subcategory']
        if any(p['category_normalization_collision'] and normalized(p['category'])==normalized(category) for p in paths.values()) and r['action']!='taxonomy_review':raise AuditError('taxonomy_collision_requires_review')
        path=paths.get(r['taxonomy_path_id'])
        existing=any((p['category'],p['subcategory'])==(category,sub) for p in paths.values())
        norm_existing=any((normalized(p['category']),normalized(p['subcategory']))==(normalized(category),normalized(sub)) for p in paths.values())
        if r['taxonomy_status']=='existing_path':
            if not path or (path['category'],path['subcategory'])!=(category,sub):raise AuditError('invalid_taxonomy_path')
            if path['normalization_collision'] and r['action']!='taxonomy_review':raise AuditError('taxonomy_collision_requires_review')
        else:
            if r['taxonomy_path_id'] is not None or existing or norm_existing:raise AuditError('invalid_proposed_taxonomy')
            if r['taxonomy_status']=='proposed_new_subcategory' and category not in cats:raise AuditError('invalid_new_subcategory')
            if r['taxonomy_status']=='proposed_new_category' and any(normalized(category)==normalized(c) for c in cats):raise AuditError('invalid_new_category')
    if covered!=set().union(*allowed.values()):raise AuditError('unaddressed_missing_aspects')
    return value


class RecommendationEngine:
    def __init__(self,model,snapshot,redactor):
        self.model=model;self.index=EvidenceIndex(snapshot);self.metadata=MetadataIndex(snapshot);self.redactor=redactor
        self.eligibility_provider=None

    async def draft(self,row,meta,observations=()):
        selected=eligibility(row,meta,observations)
        result={'eligibility':selected,'recommendation_status':'unavailable','recommendations':[],
            'gap_specifications':[],'human_gap_review_status':'not_reviewed','recommendation_review_status':'unreviewed'}
        if not selected['eligible']:return result
        start=len(self.model.metrics)
        try:
            if self.eligibility_provider:
                result['eligibility']=await self.eligibility_provider(row,meta)
                if not result['eligibility']['eligible']:return result
            payload=analyst_input(row,meta)
            for s in payload['partial_support']:
                for ref in s['citations']:self.index.resolve(ref)
            if not await self.model.fits('gap_analysis',payload):raise AuditError('model_input_token_overflow')
            from knowledge_audit.export import _redact
            gaps=validate_gaps(_redact(await self.model.call('gap_analysis',payload),self.redactor),payload,self.index)
            result['gap_specifications']=gaps['gaps']
            if self.eligibility_provider:
                result['eligibility']=await self.eligibility_provider(row,meta)
                if not result['eligibility']['eligible']:return result
            supported={s['entry_id'] for s in payload['partial_support']}
            lookup=self.metadata.lookup(payload['resolved_question'],payload['missing_aspects'],supported)
            result['title_lookup']=lookup
            prompt={'gap_specifications':gaps['gaps'],'resolved_question':payload['resolved_question'],
                'partial_support_relationships':payload['partial_support'],'title_lookup':lookup,'source':payload['source']}
            if not await self.model.fits('question_recommendation',prompt):raise AuditError('model_input_token_overflow')
            questions=validate_questions(await self.model.call('question_recommendation',prompt),gaps,lookup,row)
            safe=_redact(questions,self.redactor)
            questions=validate_questions(safe,gaps,lookup,row)
            result.update(recommendation_status='drafted',recommendations=questions['recommendations'])
            if self.eligibility_provider:
                result['eligibility']=await self.eligibility_provider(row,meta)
                if not result['eligibility']['eligible']:result['recommendation_status']='needs_review'
        except ValidationError:
            result.update(recommendation_status='error',error_code='invalid_model_schema')
        except AuditError as error:
            # AuditError is fixed internal code, never an external exception message.
            result.update(recommendation_status='error',error_code=safe_error(error))
        except Exception as error:
            from knowledge_audit.failures import category
            result.update(recommendation_status='error',error_code=category(error))
        finally:
            result['model_metrics']=self.model.metrics[start:]
        return result
