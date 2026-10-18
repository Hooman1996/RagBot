"""Main-dashboard audit routes. No arbitrary path reads, raw input downloads or KB writes."""
from __future__ import annotations
import asyncio
import base64
from collections import Counter
import json
from pathlib import Path
import secrets
from typing import Annotated, Literal
from dataclasses import asdict
from knowledge_audit.operations import Budget,Limits

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from frontend_paths import TEMPLATE_DIR
from fastapi.templating import Jinja2Templates
from versioned_assets import versioned_asset, asset_integrity, vendor_integrity
from web_auth import WebUser
from web_permissions import permissions_for_user
from knowledge_audit.schemas import StrictModel
from knowledge_audit.settings import load_coverage_settings, coverage_enabled, require_coverage_enabled
from knowledge_audit.store import CoverageStore, BytesInput
from knowledge_audit.privacy import AuditError, Redactor, private_directory
from knowledge_audit.inputs import ColumnMapping, TimestampPolicy, CsvInputAdapter
from knowledge_audit.preparation import QueryPreparer, prepare_dataset
from knowledge_audit.export import coverage_export
from knowledge_audit.jobs import CoverageJobs, versions
from knowledge_audit.service import build_engine
from utils.read_only_audit import canonical_sha256

router = APIRouter(tags=["knowledge-coverage"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals.update(versioned_asset=versioned_asset, asset_integrity=asset_integrity, vendor_integrity=vendor_integrity)


def mount(app, environ=None) -> bool:
    if not coverage_enabled(environ):
        return False
    app.include_router(router)
    return True


class ImportPayload(StrictModel):
    csv_base64: str
    mapping: dict[str, str | None]
    calendar: str = "gregorian"
    source_timezone: str | None = None
    authoritative_source_order: bool = False
    encoding: str = "utf-8-sig"
    delimiter: str = ","


class BudgetPayload(StrictModel):
    completion_attempts: int = Field(strict=True,ge=1,le=100000)
    token_allowance: int = Field(strict=True,ge=1,le=1000000000)
    execution_seconds: int = Field(strict=True,ge=1,le=604800)
    consecutive_failures: int = Field(strict=True,ge=1,le=100)
    min_free_bytes: int = Field(strict=True,ge=0,le=1099511627776)
    pace_ms: int = Field(strict=True,ge=0,le=60000)


class RunPayload(StrictModel):
    dataset_id: str = Field(pattern=r"^d_[0-9a-f]{32}$")
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_ids: list[str] = Field(default_factory=list, max_length=100000)
    execution_mode: Literal["pilot", "subset", "full_input"] = "pilot"
    idempotency_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{16,128}$")
    entry_budget: int | None = Field(default=None, ge=1)
    documents: list[str] = Field(min_length=1, max_length=50)
    operational_limits: BudgetPayload | None = None
    budget_acknowledged: bool = False


class RecoveryPayload(StrictModel):
    unknown_policy: Literal["stop", "skip_unknown", "retry_unknown"] = "stop"


def require(user, *capabilities):
    permissions = permissions_for_user(user.role, user.id)
    if not set(capabilities) <= permissions:
        raise HTTPException(403, detail="Permission denied")


def safe_meta(meta):
    keys = ("run_id", "dataset_id", "snapshot_id", "created_at", "state", "stage", "completed_pilot_rows",
            "input_row_count", "selected_row_ids", "active_row_id", "error_code", "attempt", "cancel_requested",
            "processed_rows", "execution_mode", "execution_version", "selected_row_count", "completion_quality", "recovery_choice",
            "ordering_provenance", "settings", "pause_reason", "operational_policy")
    return {k: meta[k] for k in keys if k in meta}


def runtime(request):
    require_coverage_enabled()
    if hasattr(request.app.state, "coverage_runtime"):
        return request.app.state.coverage_runtime
    settings = load_coverage_settings()
    store = CoverageStore(settings.artifact_dir)
    runner = request.app.state.blocking_runner
    async def factory(meta):
        return await build_engine(store, meta, settings, answering=request.app.state.answering_service,
            runner=runner, limiter=request.app.state.request_limiter)
    async def access_guard(owner):
        import main
        account = await runner.run(main.db_manager.get_web_user_by_id, owner)
        return bool(account and account.get("is_active") and
            {"coverage_run_start", "kb_read"} <= permissions_for_user(account.get("role"), owner))
    jobs = CoverageJobs(store, factory, runner, access_guard=access_guard)
    request.app.state.coverage_runtime = (settings, store, jobs)
    return settings, store, jobs


async def safe_call(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except AuditError as exc:
        code = str(exc)
        if code == "artifact_not_found" or code == "invalid_artifact_id":
            raise HTTPException(404, detail="Audit resource not found") from None
        raise HTTPException(409, detail=code if code in SAFE_API_CODES else "Audit operation could not complete") from None
    except (OSError, ValueError):
        raise HTTPException(409, detail="Audit operation could not complete") from None


@router.get("/knowledge-coverage")
async def page(request: Request, user: WebUser):
    require(user, "coverage_results_view")
    settings = load_coverage_settings()
    return templates.TemplateResponse(request=request, name="knowledge_coverage.html", context={
        "permissions": permissions_for_user(user.role, user.id), "upload_max_bytes": settings.upload_max_bytes,
        "contract_version": "coverage-page-3", "max_run_rows": settings.max_run_rows, "batch_max_entries": settings.batch_max_entries, "max_entry_budget": settings.max_entry_budget, "operational_limits":asdict(settings.operational_limits), "retention_days":settings.retention_days}, headers={"Cache-Control": "no-store"})


def calibration_summary(meta):
    # Controlled results stay separate; no private review notes or run checkpoints.
    return {key:meta[key] for key in ("calibration_id","scope","state","created_at","finished_at",
        "configuration","configuration_id","run_identity_id","selection","summary","human_labels",
        "dispatches","returned_completions","reported_usage") if key in meta}


@router.get("/api/knowledge-coverage/calibrations")
async def calibrations(request: Request, user: WebUser):
    require(user,"coverage_results_view")
    from knowledge_audit.calibration import CalibrationArtifacts
    _,store,_ = runtime(request)
    rows = await safe_call(CalibrationArtifacts(store).list_owned,user.id)
    return [calibration_summary(meta) for meta in rows]


@router.get("/api/knowledge-coverage/calibrations/{calibration_id}")
async def calibration_detail(calibration_id: str, request: Request, user: WebUser):
    require(user,"coverage_results_view")
    from knowledge_audit.calibration import CalibrationArtifacts
    _,store,_ = runtime(request)
    return calibration_summary(await safe_call(CalibrationArtifacts(store).owned,calibration_id,user.id))


async def calibration_download(calibration_id,request,user):
    require(user,"coverage_export_download","coverage_results_view")
    from knowledge_audit.calibration import CalibrationArtifacts
    _,store,_ = runtime(request)
    visible = {"coverage_evidence_view","kb_read"} <= permissions_for_user(user.role,user.id)
    return await safe_call(CalibrationArtifacts(store).download,calibration_id,user.id,visible)


@router.get("/api/knowledge-coverage/calibrations/{calibration_id}/export")
async def calibration_csv(calibration_id: str, request: Request, user: WebUser):
    body,manifest = await calibration_download(calibration_id,request,user)
    return Response(body,media_type="text/csv; charset=utf-8",headers={"Cache-Control":"no-store",
        "Content-Disposition":'attachment; filename="calibration-'+manifest["export_id"]+'.csv"'})


@router.get("/api/knowledge-coverage/calibrations/{calibration_id}/export-manifest")
async def calibration_manifest(calibration_id: str, request: Request, user: WebUser):
    _,manifest = await calibration_download(calibration_id,request,user)
    return Response(json.dumps(manifest),media_type="application/json",headers={"Cache-Control":"no-store"})


@router.post("/api/knowledge-coverage/datasets", status_code=201)
async def import_dataset(request: Request, user: WebUser):
    require(user, "coverage_run_start")
    settings, store, jobs = runtime(request)
    # Bounded streaming BEFORE JSON/base64 decoding. No multipart disk spool,
    # raw server filename or filesystem path can be selected by a browser.
    bound = settings.upload_max_bytes * 4 // 3 + 16384
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > bound:
            raise HTTPException(413, detail="CSV exceeds the upload limit")
        body.extend(part)
    try:
        payload = ImportPayload.model_validate_json(bytes(body))
        raw = base64.b64decode(payload.csv_base64, validate=True)
        if len(raw) > settings.upload_max_bytes:
            raise HTTPException(413, detail="CSV exceeds the upload limit")
        mapping = ColumnMapping(**payload.mapping)
        policy = TimestampPolicy(payload.calendar, payload.source_timezone, payload.authoritative_source_order)
        key = secrets.token_bytes(32)
        redactor = Redactor(key)
        data = await safe_call(CsvInputAdapter(BytesInput(raw), mapping, policy=policy,
            encoding=payload.encoding, delimiter=payload.delimiter).load, redactor)
        meta = await safe_call(store.save_dataset, data, redactor, key, user.id)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(422, detail="Invalid CSV format or column mapping") from None
    async def normalize():
        try:
            rows = await prepare_dataset(data, QueryPreparer.from_answering_service(request.app.state.answering_service), redactor)
            await safe_call(store.set_preparations, meta["dataset_id"], user.id, rows)
        except BaseException:
            meta["preparation_status"] = "interrupted"
            await run_in_threadpool(store.write, store._path("datasets", meta["dataset_id"]) / "meta.json", meta)
            raise
    jobs.tasks.start(meta["dataset_id"], normalize, operation_type="knowledge_coverage_import")
    return {k: meta[k] for k in ("dataset_id", "structure", "preparation_status", "preparation_counts", "timestamp_policy")}


@router.get("/api/knowledge-coverage/datasets")
async def datasets(request: Request, user: WebUser):
    require(user, "coverage_results_view")
    _, store, _ = runtime(request)
    data = await safe_call(store.list_owned, "datasets", user.id)
    return [{k: d[k] for k in ("dataset_id", "created_at", "structure", "preparation_counts", "preparation_status", "timestamp_policy")} for d in data]


@router.get("/api/knowledge-coverage/datasets/{dataset_id}/rows")
async def input_rows(dataset_id: str, request: Request, user: WebUser,
                     offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 25):
    require(user, "coverage_results_view")
    _, store, _ = runtime(request)
    meta = await safe_call(store.owned, "datasets", dataset_id, user.id)
    if meta["preparation_status"] != "ready":
        return {"state": meta["preparation_status"], "rows": [], "total": meta["structure"]["selected_row_count"]}
    rows = await safe_call(store.preparations, dataset_id, user.id)
    return {"state": "ready", "total": len(rows), "rows": [summary(r) for r in rows[offset:offset + limit]]}


@router.get("/api/knowledge-coverage/snapshots")
async def snapshots(request: Request, user: WebUser):
    require(user, "coverage_run_start", "kb_read")
    _, store, _ = runtime(request)
    rows = await safe_call(store.list_owned, "snapshots", user.id)
    return [{k: r[k] for k in ("snapshot_id", "created_at", "record_count", "documents")} for r in rows]


@router.post("/api/knowledge-coverage/snapshots", status_code=201)
async def snapshot_capture(request: Request, user: WebUser):
    require(user, "coverage_run_start", "kb_read")
    settings, store, _ = runtime(request)
    from knowledge_audit.runtime import confirm_staging
    from knowledge_audit.snapshot import capture_snapshot, read_postgres_snapshot
    from scripts.kb_signature import create_signature
    from new_architecture.app.services.history.database import DatabaseManager
    confirm_staging(confirmed=True, snapshot=True)
    path = await safe_call(private_directory, store.root / "archive" / ("capture_" + secrets.token_hex(16)))
    await safe_call(capture_snapshot, path, Redactor(secrets.token_bytes(32)), signature_provider=create_signature,
        content_provider=lambda: read_postgres_snapshot(DatabaseManager().get_connection),
        public_contacts=settings.public_contacts)
    meta = await safe_call(store.register_snapshot, path / "kb-snapshot.json", path / "kb-snapshot-manifest.json", user.id)
    return {k: meta[k] for k in ("snapshot_id", "record_count", "documents", "created_at")}


def resolve_entry_budget(requested, maximum):
    budget = maximum if requested is None else requested
    if type(budget) is not int or not 1 <= budget <= maximum:
        raise AuditError("invalid_entry_budget")
    return budget


@router.post("/api/knowledge-coverage/runs", status_code=202)
async def create_run(payload: RunPayload, request: Request, user: WebUser):
    require(user, "coverage_run_start", "kb_read")
    settings, store, jobs = runtime(request)
    source = await safe_call(store.owned, "datasets", payload.dataset_id, user.id)
    if source["preparation_status"] != "ready":
        raise HTTPException(409, detail="Input preparation is not ready")
    snapshot = await safe_call(store.owned, "snapshots", payload.snapshot_id, user.id)
    if not set(payload.documents) <= set(snapshot["documents"]):
        raise HTTPException(422, detail="Choose a datasource from this snapshot")
    if payload.execution_mode=='full_input' and not payload.budget_acknowledged:
        raise HTTPException(422,detail='Confirm finite full-input limits; the run may pause before all rows are evaluated')
    effective=payload.operational_limits.model_dump() if payload.operational_limits else asdict(settings.operational_limits)
    ceiling=asdict(settings.operational_limits)
    if any((v>ceiling[k] if k not in {'min_free_bytes','pace_ms'} else v<ceiling[k]) for k,v in effective.items()):
        raise HTTPException(422,detail='Run limits exceed configured allowance or reduce storage/pacing protection')
    entry_budget = await safe_call(resolve_entry_budget, payload.entry_budget, settings.max_entry_budget)
    config = {**settings.manifest(), "entry_budget": entry_budget, "documents": payload.documents,
              "selection_method": "server_all_user_query_rows" if payload.execution_mode == "full_input" else "explicit_source_row_ids", "operational_limits":effective}
    meta = await safe_call(store.create_run, user.id, payload.dataset_id, payload.snapshot_id,
                           payload.row_ids, config, versions(), execution_mode=payload.execution_mode, idempotency_key=payload.idempotency_key or canonical_sha256(payload.model_dump()))
    jobs.start(meta["run_id"], user.id)
    return safe_meta(meta)


@router.get("/api/knowledge-coverage/runs")
async def runs(request: Request, user: WebUser):
    require(user, "coverage_results_view")
    _, store, _ = runtime(request)
    return [safe_meta(m) for m in await safe_call(store.list_owned, "runs", user.id)]


@router.get("/api/knowledge-coverage/runs/{run_id}")
async def run_detail(run_id: str, request: Request, user: WebUser):
    require(user, "coverage_results_view")
    _, store, jobs = runtime(request)
    meta = await safe_call(store.owned, "runs", run_id, user.id)
    meta = await jobs.inspect_state(run_id, user.id)
    counts = await safe_call(store.progress, run_id, user.id)
    resource={}
    if meta.get('operational_policy'):
        budget=await safe_call(Budget,store,store._path('runs',run_id),user.id,Limits.from_settings(meta['settings']))
        resource=await safe_call(budget.summary)
    return {**safe_meta(meta), 'operational_budget':resource, 'retention_policy':meta['settings'].get('retention_policy',{'automatic_deletion':False,'status':'historical_unrecorded'}), **counts, **({"completed_pilot_rows": counts["processed_rows"]} if meta.get("execution_mode", "pilot")=="pilot" else {})}


def summary(row):
    keys = ("source_row_id", "source_record_ordinal", "input_query_redacted", "preparation_status", "history_status",
            "processing_status", "coverage_status", "outcome", "evaluated_entry_count", "production_context_sufficiency")
    return {k: row[k] for k in keys if k in row}


@router.get("/api/knowledge-coverage/runs/{run_id}/results")
async def results(run_id: str, request: Request, user: WebUser,
                  offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                  outcome: str = "", search: Annotated[str, Query(max_length=200)] = ""):
    require(user, "coverage_results_view")
    _, store, _ = runtime(request)
    return await safe_call(store.result_page, run_id, user.id, offset, limit, outcome, search)


@router.get("/api/knowledge-coverage/runs/{run_id}/rows/{row_id}")
async def evidence(run_id: str, row_id: str, request: Request, user: WebUser):
    require(user, "coverage_evidence_view", "coverage_results_view", "kb_read")
    _, store, _ = runtime(request)
    meta = await safe_call(store.owned, "runs", run_id, user.id)
    row = await safe_call(store.row, run_id, row_id, user.id)
    if meta["state"] == "incompatible":
        return {**summary(row), "evidence_visibility": "snapshot_mismatch"}
    snapshot = await safe_call(store.snapshot, meta["snapshot_id"], user.id)
    from knowledge_audit.evidence import EvidenceIndex
    index = EvidenceIndex(snapshot)
    ids = list(dict.fromkeys(r["chunk_id"] for r in row.get("supporting_sentence_refs", [])))
    if not ids:
        ids = list(dict.fromkeys(s["entry_id"] for s in row.get("audit_assessment", {}).get("supports", [])))
    return {"result": row, "evidence": [index.entry(cid) for cid in ids]}


async def exported(run_id, request, user, revision_id=None, *, create=False):
    require(user, "coverage_export_download", "coverage_results_view")
    _, store, _ = runtime(request)
    await safe_call(store.owned, "runs", run_id, user.id)
    visible = {"coverage_evidence_view", "kb_read"} <= permissions_for_user(user.role, user.id)
    return await safe_call(store.export_revision, run_id, user.id, visible, revision_id, create=create)


@router.post("/api/knowledge-coverage/runs/{run_id}/export-revisions", status_code=201)
async def create_export_revision(run_id: str, request: Request, user: WebUser):
    _, manifest = await exported(run_id, request, user, create=True)
    return {k: manifest[k] for k in ("export_revision_id", "export_id", "csv_sha256", "export_captured_at", "state", "row_count")}


@router.get("/api/knowledge-coverage/runs/{run_id}/export")
async def download(run_id: str, request: Request, user: WebUser, revision_id: str | None = None):
    data, manifest = await exported(run_id, request, user, revision_id)
    return Response(data, media_type="text/csv; charset=utf-8", headers={"Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="coverage-{run_id}.csv"', "X-Coverage-Export-ID": manifest["export_id"],
        "X-Coverage-Revision-ID": manifest["export_revision_id"]})


@router.get("/api/knowledge-coverage/runs/{run_id}/export-manifest")
async def export_manifest(run_id: str, request: Request, user: WebUser, revision_id: str | None = None):
    _, manifest = await exported(run_id, request, user, revision_id)
    return manifest


@router.post("/api/knowledge-coverage/runs/{run_id}/cancel")
async def cancel(run_id: str, request: Request, user: WebUser):
    require(user, "coverage_run_start")
    _, store, jobs = runtime(request)
    await safe_call(store.owned, "runs", run_id, user.id)
    try:
        await jobs.cancel(run_id, user.id)
    except AuditError:
        raise HTTPException(409, detail="Run cannot be cancelled") from None
    return {"state": "cancellation_requested"}


@router.post("/api/knowledge-coverage/runs/{run_id}/retry", status_code=202)
async def retry(run_id: str, request: Request, user: WebUser, payload: RecoveryPayload | None = None):
    require(user, "coverage_run_start")
    _, store, jobs = runtime(request)
    await safe_call(store.owned, "runs", run_id, user.id)
    try:
        await jobs.recover(run_id, user.id, unknown_policy=payload.unknown_policy if payload else "stop")
    except AuditError as error:
        code = str(error)
        raise HTTPException(409, detail=code if code in SAFE_API_CODES else "Active or incompatible run cannot be resumed") from None
    return {"state": "queued"}


SAFE_API_CODES = {"coverage_disabled", "coverage_enabled_in_production", "budget_ledger_missing","budget_completions","budget_tokens","budget_elapsed","budget_failures","budget_disk","budget_new_run_required","unknown_remote_completion","budget_identity_mismatch","invalid_run_selection", "invalid_execution_mode", "run_selection_exceeds_maximum",
    "full_input_selection_is_server_resolved", "idempotency_request_conflict", "invalid_idempotency_key",
    "unknown_remote_completion_requires_choice", "audit_version_drift", "audit_runtime_identity_drift",
    "invalid_pilot_selection", "invalid_entry_budget", "invalid_column_mapping", "invalid_timestamp_mapping", "ambiguous_csv_header",
    "csv_syntax_or_encoding_error", "invalid_source_timezone", "invalid_calendar", "invalid_csv_format",
    "snapshot_capture_mismatch", "snapshot_cross_store_inconsistent", "source_or_index_drift", "incompatible_run",
    "snapshot_policy_superseded"}

# A4 responsibilities and revisions remain separate from coverage run versions.
from knowledge_audit.recommendation_api import router as recommendation_router
router.include_router(recommendation_router)

from knowledge_audit.run_export_api import router as run_export_router
router.include_router(run_export_router)
