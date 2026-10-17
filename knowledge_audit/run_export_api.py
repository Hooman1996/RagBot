"""Owner/capability/CSRF protected run-level export, with no model dispatch."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import Field
from web_auth import WebUser
from web_permissions import permissions_for_user
from knowledge_audit.schemas import StrictModel
from knowledge_audit.privacy import AuditError
from knowledge_audit.run_export import RunExportStore

router = APIRouter(tags=['knowledge-coverage'])
MESSAGES = {
    'export_duplicate_row_selection': 'Choose at most one draft revision per source row.',
    'export_unknown_source_row': 'A selected row is absent from this frozen coverage source.',
    'export_unknown_draft_row': 'The draft revision does not contain the selected row.',
    'export_incompatible_coverage_source': 'These drafts use different frozen coverage sources. Select revisions from the same coverage export.',
    'export_draft_not_finished': 'Wait for drafting to finish or choose a finished revision.',
    'recommendation_review_mismatch': 'The selected review does not belong to this frozen draft result.',
}


class RowSelection(StrictModel):
    source_row_id: str = Field(pattern=r'^row_[0-9a-f]{32}$')
    recommendation_revision_id: str = Field(pattern=r'^rec_[0-9a-f]{32}$')
    # Required, including empty: never silently select a mutable latest review.
    review_revision_id: str = Field(pattern=r'^(?:rvw_[0-9a-f]{32})?$')


class RunExportSelection(StrictModel):
    coverage_export_revision_id: str = Field(pattern=r'^rev_[0-9a-f]{32}$')
    selections: list[RowSelection]


def service(request, user):
    from knowledge_audit.api import require, runtime
    require(user, 'coverage_results_view', 'coverage_export_download')
    _, store, _ = runtime(request)
    visible = {'coverage_evidence_view', 'kb_read'} <= permissions_for_user(user.role, user.id)
    return RunExportStore(store), visible


async def call(fn, *args):
    from knowledge_audit.api import safe_call
    try:
        # Local codes below are allowlisted; no exception messages are exposed.
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(fn, *args)
    except AuditError as error:
        code = str(error)
        if code in MESSAGES:
            raise HTTPException(409, detail=MESSAGES[code]) from None
        def rejected():
            raise AuditError(code)
        return await safe_call(rejected)
    except (OSError, ValueError):
        raise HTTPException(409, detail='Export source is unavailable or invalid. Select an existing frozen source.') from None


@router.get('/api/knowledge-coverage/runs/{run_id}/export-options')
async def options(run_id: str, request: Request, user: WebUser, coverage_export_revision_id: str = ''):
    store, _ = service(request, user)
    return await call(store.options, run_id, user.id, coverage_export_revision_id)


@router.post('/api/knowledge-coverage/runs/{run_id}/combined-export-preview')
async def preview(run_id: str, payload: RunExportSelection, request: Request, user: WebUser):
    store, visible = service(request, user)
    return await call(store.preview, run_id, user.id, payload.coverage_export_revision_id,
                      [s.model_dump() for s in payload.selections], visible)


@router.post('/api/knowledge-coverage/runs/{run_id}/combined-export-revisions', status_code=201)
async def create(run_id: str, payload: RunExportSelection, request: Request, user: WebUser):
    store, visible = service(request, user)
    manifest = await call(store.create, run_id, user.id, payload.coverage_export_revision_id,
                          [s.model_dump() for s in payload.selections], visible)
    return {k: manifest[k] for k in ('export_id', 'export_revision_id', 'row_count', 'summary', 'captured_at', 'evidence_visible')}


async def download_pair(run_id, revision_id, request, user):
    store, visible = service(request, user)
    return await call(store.download, run_id, user.id, visible, revision_id)


@router.get('/api/knowledge-coverage/runs/{run_id}/combined-export')
async def download(run_id: str, revision_id: str, request: Request, user: WebUser):
    body, manifest = await download_pair(run_id, revision_id, request, user)
    return Response(body, media_type='text/csv; charset=utf-8', headers={
        'Cache-Control': 'no-store', 'Content-Disposition': 'attachment; filename="coverage-run-' + manifest['export_id'] + '.csv"',
        'X-Coverage-Export-ID': manifest['export_id'], 'X-Coverage-Revision-ID': revision_id})


@router.get('/api/knowledge-coverage/runs/{run_id}/combined-export-manifest')
async def manifest(run_id: str, revision_id: str, request: Request, user: WebUser):
    _, value = await download_pair(run_id, revision_id, request, user)
    return value
