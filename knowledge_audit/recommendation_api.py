"""Owned A4 review routes in the existing main-dashboard router."""
from fastapi import APIRouter,Request,HTTPException
from fastapi.responses import Response
from pydantic import Field
from web_auth import WebUser
from web_permissions import permissions_for_user
from knowledge_audit.schemas import StrictModel
from knowledge_audit.recommendation_store import RecommendationStore
from knowledge_audit.recommendation_jobs import RecommendationJobs,build_recommendation_engine
from knowledge_audit.recommendations import eligibility

router=APIRouter(tags=['knowledge-coverage'])


def require(*args):
    from knowledge_audit.api import require as implementation
    return implementation(*args)


def runtime(request):
    from knowledge_audit.api import runtime as implementation
    return implementation(request)


async def safe_call(*args,**kwargs):
    from knowledge_audit.api import safe_call as implementation
    return await implementation(*args,**kwargs)



class DraftPayload(StrictModel):
    coverage_export_revision_id: str = Field(pattern=r'^rev_[0-9a-f]{32}$')
    row_ids: list[str] = Field(min_length=1,max_length=5)


class DecisionPayload(StrictModel):
    source_row_id: str = Field(pattern=r'^row_[0-9a-f]{32}$')
    recommendation_id: str = Field(pattern=r'^q[1-3]$')
    decision: str = Field(pattern=r'^(unreviewed|approved|rejected|needs_changes)$')
    note: str = Field(default='',max_length=600)


class ExportPayload(StrictModel):
    review_revision_id: str | None = Field(default=None,pattern=r'^rvw_[0-9a-f]{32}$')


def services(request):
    if hasattr(request.app.state,'recommendation_runtime'):return request.app.state.recommendation_runtime
    _,store,coverage_jobs=runtime(request)
    recommendations=RecommendationStore(store)
    async def factory(meta):return await build_recommendation_engine(request,recommendations,meta)
    jobs=RecommendationJobs(recommendations,coverage_jobs,request.app.state.blocking_runner,factory)
    request.app.state.recommendation_runtime=(recommendations,jobs)
    return recommendations,jobs


def public_meta(meta):
    return {k:meta[k] for k in ('recommendation_revision_id','source_run_id','source_export_id','source_export_revision_id',
        'snapshot_id','created_at','finished_at','state','phase','error_code','selected_row_ids','versions','serving_identity',
        'human_gap_review_status','calibration_status','operational_settings','pause_reason') if k in meta}


def evidence_access(user,*extra):
    require(user,'coverage_results_view','coverage_evidence_view','kb_read',*extra)


@router.get('/api/knowledge-coverage/runs/{run_id}/rows/{row_id}/recommendations')
async def availability(run_id: str,row_id: str,request: Request,user: WebUser):
    evidence_access(user)
    store,jobs=services(request)
    meta=await safe_call(store.store.owned,'runs',run_id,user.id)
    row=await safe_call(store.store.row,run_id,row_id,user.id)
    observations=await safe_call(store.observations,meta,row,user.id)
    revisions=await safe_call(store.list_for_row,run_id,row_id,user.id)
    from dataclasses import asdict
    from knowledge_audit.settings import load_coverage_settings
    from knowledge_audit.operations import Limits
    limits=Limits.from_settings(load_coverage_settings().manifest(),recommendation=True)
    return {'eligibility':eligibility(row,meta,observations),'revisions':[public_meta(r) for r in revisions],
        'operational_limits':asdict(limits),'allowance_scope':'separate_per_recommendation_revision_no_usage_reset'}


@router.post('/api/knowledge-coverage/runs/{run_id}/recommendations',status_code=202)
async def create(run_id: str,payload: DraftPayload,request: Request,user: WebUser):
    evidence_access(user,'coverage_run_start','coverage_export_download')
    store,jobs=services(request)
    meta=await safe_call(store.create,run_id,user.id,payload.coverage_export_revision_id,payload.row_ids)
    jobs.start(meta['recommendation_revision_id'],user.id)
    return public_meta(meta)


@router.get('/api/knowledge-coverage/recommendations/{revision_id}')
async def detail(revision_id: str,request: Request,user: WebUser):
    evidence_access(user)
    store,jobs=services(request)
    meta=await safe_call(store.owned,revision_id,user.id)
    result=await safe_call(store.effective_results,revision_id,user.id)
    review=await safe_call(store.review,revision_id,user.id)
    budget={}
    if meta.get('operational_policy'):
        from knowledge_audit.operations import Budget,Limits
        resource=await safe_call(Budget,store.store,store.path(revision_id),user.id,Limits.from_settings(meta['operational_settings'],recommendation=True))
        budget=await safe_call(resource.summary)
    return {'revision':public_meta(meta),'results':result,'review':review,'operational_budget':budget}


@router.post('/api/knowledge-coverage/recommendations/{revision_id}/cancel')
async def cancel(revision_id: str,request: Request,user: WebUser):
    evidence_access(user,'coverage_run_start')
    store,jobs=services(request)
    from knowledge_audit.privacy import AuditError
    await safe_call(store.owned,revision_id,user.id)
    try:await jobs.cancel(revision_id,user.id)
    except AuditError:raise HTTPException(409,detail='Recommendation cannot be cancelled') from None
    return {'state':'cancellation_requested'}


@router.post('/api/knowledge-coverage/recommendations/{revision_id}/reviews',status_code=201)
async def decide(revision_id: str,payload: DecisionPayload,request: Request,user: WebUser):
    evidence_access(user,'coverage_recommendation_review')
    store,_=services(request)
    return await safe_call(store.decide,revision_id,user.id,payload.source_row_id,payload.recommendation_id,payload.decision,payload.note)


@router.get('/api/knowledge-coverage/recommendations/{revision_id}/metadata/{faq_id}')
async def metadata(revision_id: str,faq_id: str,request: Request,user: WebUser):
    evidence_access(user)
    store,_=services(request)
    return await safe_call(store.metadata,revision_id,user.id,faq_id)


@router.post('/api/knowledge-coverage/recommendations/{revision_id}/export-revisions',status_code=201)
async def compose(revision_id: str,payload: ExportPayload,request: Request,user: WebUser):
    require(user,'coverage_export_download','coverage_results_view')
    store,_=services(request)
    visible={'coverage_evidence_view','kb_read'}<=permissions_for_user(user.role,user.id)
    manifest=await safe_call(store.compose,revision_id,user.id,visible,payload.review_revision_id)
    return {k:manifest[k] for k in ('export_id','export_revision_id','review_revision_id','captured_at','row_count','recommendation_state')}


async def exported(revision_id,export_revision_id,request,user):
    require(user,'coverage_export_download','coverage_results_view')
    store,_=services(request)
    visible={'coverage_evidence_view','kb_read'}<=permissions_for_user(user.role,user.id)
    return await safe_call(store.download,revision_id,user.id,visible,export_revision_id)


@router.get('/api/knowledge-coverage/recommendations/{revision_id}/export')
async def download(revision_id: str,export_revision_id: str,request: Request,user: WebUser):
    body,manifest=await exported(revision_id,export_revision_id,request,user)
    return Response(body,media_type='text/csv; charset=utf-8',headers={'Cache-Control':'no-store',
        'Content-Disposition':'attachment; filename="coverage-recommendations-'+manifest['export_id']+'.csv"'})


@router.get('/api/knowledge-coverage/recommendations/{revision_id}/export-manifest')
async def manifest(revision_id: str,export_revision_id: str,request: Request,user: WebUser):
    _,value=await exported(revision_id,export_revision_id,request,user)
    return value
