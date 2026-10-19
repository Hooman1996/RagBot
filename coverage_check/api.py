"""Coverage-check page and routes. Errors carry fixed codes only."""
from __future__ import annotations

import base64
import binascii
import csv
import io
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from coverage_check import prompts
from coverage_check.checker import RESULTS, CoverageChecker
from coverage_check.jobs import CheckJobs
from coverage_check.settings import CoverageSettings, RunSettings, SettingsError, coverage_enabled, load_settings
from coverage_check.store import CheckStore, StoreError, parse_csv
from document_category import get_document_category
from frontend_paths import TEMPLATE_DIR
from new_architecture.knowledge_sources import build_datasource_listing
from versioned_assets import asset_integrity, vendor_integrity, versioned_asset
from web_auth import WebUser
from web_permissions import permissions_for_user

router = APIRouter(tags=["knowledge-coverage"])
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals.update(versioned_asset=versioned_asset, asset_integrity=asset_integrity,
                             vendor_integrity=vendor_integrity)

PAGE_PATH = "/knowledge-coverage"
API_PREFIX = "/api/knowledge-coverage/"
EXPORT_COLUMNS = ("row", "id", "question", "result", "answer_batch", "answer_phase", "answer_chunk_ids",
                  "answer_faq_titles", "batches_checked", "broader_used", "model_calls", "duration_ms",
                  "error_code", "note")
NO_STORE = {"Cache-Control": "no-store"}


def mount(app) -> bool:
    if not coverage_enabled():
        return False
    app.include_router(router)
    return True


def coverage_path(path: str) -> bool:
    return path == PAGE_PATH or path.startswith(API_PREFIX)


async def coverage_gate(request: Request, call_next):
    """With the flag off every coverage route is 404, before authentication."""
    if coverage_path(request.url.path):
        try:
            enabled = coverage_enabled()
        except SettingsError:
            enabled = False
        if not enabled:
            return JSONResponse({"detail": "not_found"}, status_code=404, headers=NO_STORE)
    return await call_next(request)


class CoverageRuntime:
    def __init__(self, app, settings: CoverageSettings):
        self.settings = settings
        self.store = CheckStore(settings.artifact_dir)

        def factory(meta):
            return CoverageChecker(app.state.answering_service, app.state.request_limiter,
                                   meta["documents"], meta["settings"])
        self.jobs = CheckJobs(self.store, factory)

    async def aclose(self) -> None:
        await self.jobs.aclose()


async def start(app, settings: CoverageSettings) -> CoverageRuntime:
    """Called from the app lifespan once the answering service exists."""
    runtime = CoverageRuntime(app, settings)
    await runtime.jobs.recover()
    app.state.coverage_check = runtime
    return runtime


def runtime_of(request: Request) -> CoverageRuntime:
    runtime = getattr(request.app.state, "coverage_check", None)
    if runtime is None:
        raise HTTPException(503, detail="coverage_unavailable")
    return runtime


def require(user, capability: str) -> None:
    if capability not in permissions_for_user(user.role, user.id):
        raise HTTPException(403, detail="permission_denied")


async def store_call(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except StoreError as exc:
        raise HTTPException(404 if exc.code == "not_found" else 422, detail=exc.code) from None
    except (OSError, ValueError, KeyError):
        raise HTTPException(500, detail="storage_failed") from None


class StartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    csv_base64: str
    file_name: str = Field(max_length=1024)
    documents: list[str] = Field(min_length=1, max_length=500)
    depth: int
    keep: int
    batch_size: int
    broader_enabled: bool
    broader_depth: int
    broader_keep: int


def counts_for(meta: dict, codes: dict[int, str]) -> dict:
    counts = Counter(codes.values())
    view = {result: counts.get(result, 0) for result in RESULTS}
    view["waiting"] = max(0, meta["row_count"] - len(codes))
    return view


def run_view(meta: dict, codes: dict[int, str], active_row: int | None = None) -> dict:
    keys = ("run_id", "created_at", "owner_id", "file_name", "documents", "settings", "state", "row_count")
    # Runs created before step 23 have no recorded version.
    return {**{key: meta[key] for key in keys}, "prompt_version": meta.get("prompt_version"),
            "done": len(codes), "active_row": active_row}


def chunk_view(chunk_ids, titles) -> list[dict]:
    return [{"chunk_id": chunk_id, "title": titles.get(chunk_id)} for chunk_id in chunk_ids]


def row_view(item: dict, result: dict | None) -> dict:
    result = result or {}
    titles = result.get("titles") or {}
    return {
        "row": item["row"], "id": item["id"], "question": item["question"],
        "result": result.get("result"), "answer_batch": result.get("answer_batch"),
        "answer_phase": result.get("answer_phase"),
        "answer_chunks": chunk_view(result.get("answer_chunk_ids") or [], titles),
        "batches": [{"number": b["number"], "phase": b["phase"], "verdict": b["verdict"],
                     "chunks": chunk_view(b["chunk_ids"], titles)} for b in result.get("batches") or []],
        "combines": [{"phase": c["phase"], "verdict": c["verdict"],
                      "chunks": chunk_view(c["chunk_ids"], titles)} for c in result.get("combines") or []],
        "broader_used": result.get("broader_used"), "model_calls": result.get("model_calls"),
        "duration_ms": result.get("duration_ms"), "error_code": result.get("error_code"),
        "note": result.get("note"),
    }


def detail_chunks(chunk_ids, relied_ids, titles, texts) -> list[dict]:
    relied = set(relied_ids or [])
    return [{"number": number, "chunk_id": chunk_id, "title": titles.get(chunk_id),
             "text": texts.get(chunk_id), "relied": chunk_id in relied}
            for number, chunk_id in enumerate(chunk_ids, 1)]


def row_detail(store: CheckStore, run_id: str, item: dict, result: dict | None) -> dict:
    """row_view plus, per batch and combine call, its note and the numbered chunk text the model saw."""
    view = row_view(item, result)
    if not result:
        return view
    titles = result.get("titles") or {}
    keys = result.get("text_keys") or {}
    texts = {}
    for chunk_id, key in keys.items():
        texts[chunk_id] = store.chunk_text(run_id, key)
    view["batches"] = [{"number": b["number"], "phase": b["phase"], "verdict": b["verdict"], "note": b.get("note"),
                        "chunks": detail_chunks(b["chunk_ids"], b.get("relied_chunk_ids"), titles, texts)}
                       for b in result.get("batches") or []]
    view["combines"] = [{"phase": c["phase"], "verdict": c["verdict"], "note": c.get("note"),
                         "chunks": detail_chunks(c["chunk_ids"], c.get("relied_chunk_ids"), titles, texts)}
                        for c in result.get("combines") or []]
    return view


def formula_safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def export_line(item: dict, result: dict | None) -> list[str]:
    view = row_view(item, result)
    result = result or {}
    values = {
        **{key: view[key] for key in ("row", "id", "question", "answer_batch", "answer_phase",
                                      "model_calls", "duration_ms", "error_code", "note")},
        "result": view["result"] or "waiting",
        "answer_chunk_ids": ";".join(c["chunk_id"] for c in view["answer_chunks"]),
        "answer_faq_titles": " | ".join(c["title"] or "" for c in view["answer_chunks"]),
        "batches_checked": len(result.get("batches") or []) if result else "",
        "broader_used": ("true" if view["broader_used"] else "false") if result else "",
    }
    return [formula_safe(values[column]) for column in EXPORT_COLUMNS]


@router.get(PAGE_PATH)
async def page(request: Request, user: WebUser):
    require(user, "coverage_results_view")
    settings = runtime_of(request).settings
    return templates.TemplateResponse(request=request, name="knowledge_coverage.html", context={
        "permissions": permissions_for_user(user.role, user.id), "defaults": settings.run.as_dict(),
        "upload_max_bytes": settings.upload_max_bytes, "max_rows": settings.max_rows}, headers=NO_STORE)


@router.get("/api/knowledge-coverage/documents")
async def documents(request: Request, user: WebUser):
    require(user, "coverage_run_start")
    runtime_of(request)
    state = request.app.state
    rows = await state.blocking_runner.run(state.db_manager.get_available_documents)
    payload = build_datasource_listing([row["title"] for row in rows], get_document_category)
    return JSONResponse(payload, headers=NO_STORE)


@router.post("/api/knowledge-coverage/checks", status_code=201)
async def start_check(request: Request, user: WebUser):
    require(user, "coverage_run_start")
    runtime = runtime_of(request)
    settings = runtime.settings
    # Bounded stream before any JSON or base64 decoding.
    bound = settings.upload_max_bytes * 4 // 3 + 65536
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > bound:
            raise HTTPException(413, detail="upload_too_large")
        body.extend(part)
    try:
        payload = StartPayload.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(422, detail="invalid_request") from None
    try:
        run = RunSettings(**payload.model_dump(include=set(RunSettings.__dataclass_fields__)))
    except SettingsError as exc:
        raise HTTPException(422, detail="invalid_" + str(exc)) from None
    try:
        raw = base64.b64decode(payload.csv_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, detail="invalid_csv") from None
    if len(raw) > settings.upload_max_bytes:
        raise HTTPException(413, detail="upload_too_large")
    rows = await store_call(parse_csv, raw, settings.max_rows)
    # The chosen datasources pass through the chat's own validator.
    validator = request.app.state.answering_service.selection_validator
    if validator is not None:
        chosen = await request.app.state.blocking_runner.run(validator, list(payload.documents))
    else:
        chosen = list(dict.fromkeys(d.strip() for d in payload.documents if d.strip()))
    if not chosen:
        raise HTTPException(422, detail="no_documents")
    meta = await store_call(runtime.store.create, owner_id=user.id, file_name=payload.file_name,
                            documents=list(chosen), settings=settings.run_values(run), rows=rows,
                            prompt_version=prompts.PROMPT_VERSION)
    runtime.jobs.enqueue(meta["run_id"])
    return {"run_id": meta["run_id"]}


@router.get("/api/knowledge-coverage/checks")
async def list_checks(request: Request, user: WebUser):
    require(user, "coverage_results_view")
    runtime = runtime_of(request)
    store = runtime.store
    metas = await store_call(store.list)
    views = []
    for meta in metas:
        codes = await store_call(store.result_codes, meta["run_id"])
        views.append(run_view(meta, codes, runtime.jobs.active_row(meta["run_id"])))
    return JSONResponse(views, headers=NO_STORE)


@router.get("/api/knowledge-coverage/checks/{run_id}")
async def get_check(run_id: str, request: Request, user: WebUser):
    require(user, "coverage_results_view")
    runtime = runtime_of(request)
    store = runtime.store
    meta = await store_call(store.meta, run_id)
    codes = await store_call(store.result_codes, run_id)
    active_row = runtime.jobs.active_row(run_id)
    return JSONResponse({"meta": run_view(meta, codes, active_row), "counts": counts_for(meta, codes),
                         "done": len(codes), "active_row": active_row}, headers=NO_STORE)


@router.get("/api/knowledge-coverage/checks/{run_id}/rows")
async def check_rows(run_id: str, request: Request, user: WebUser,
                     offset: Annotated[int, Query(ge=0)] = 0,
                     limit: Annotated[int, Query(ge=1, le=100)] = 50,
                     result: Annotated[str | None, Query(max_length=32)] = None):
    require(user, "coverage_results_view")
    if result is not None and result not in (*RESULTS, "waiting"):
        raise HTTPException(422, detail="invalid_result_filter")
    runtime = runtime_of(request)
    store = runtime.store
    items = await store_call(store.inputs, run_id)
    codes = await store_call(store.result_codes, run_id)
    active_row = runtime.jobs.active_row(run_id)
    if result == "waiting":
        items = [item for item in items if item["row"] not in codes]
    elif result is not None:
        items = [item for item in items if codes.get(item["row"]) == result]
    page_items = items[offset:offset + limit]
    rows = []
    for item in page_items:
        found = await store_call(store.result, run_id, item["row"]) if item["row"] in codes else None
        rows.append({**row_view(item, found), "active": item["row"] == active_row})
    return JSONResponse({"total": len(items), "offset": offset, "rows": rows}, headers=NO_STORE)


@router.get("/api/knowledge-coverage/checks/{run_id}/rows/{row}")
async def check_row(run_id: str, row: int, request: Request, user: WebUser):
    require(user, "coverage_results_view")
    store = runtime_of(request).store
    items = await store_call(store.inputs, run_id)
    item = next((item for item in items if item["row"] == row), None)
    if item is None:
        raise HTTPException(404, detail="not_found")
    found = await store_call(store.result, run_id, row)
    return JSONResponse(await store_call(row_detail, store, run_id, item, found), headers=NO_STORE)


@router.post("/api/knowledge-coverage/checks/{run_id}/cancel")
async def cancel_check(run_id: str, request: Request, user: WebUser):
    require(user, "coverage_run_start")
    runtime = runtime_of(request)
    meta = await store_call(runtime.store.meta, run_id)
    if meta["state"] not in {"queued", "running"}:
        raise HTTPException(409, detail="invalid_state")
    await runtime.jobs.cancel(run_id)
    return {"run_id": run_id, "state": (await store_call(runtime.store.meta, run_id))["state"]}


@router.post("/api/knowledge-coverage/checks/{run_id}/resume")
async def resume_check(run_id: str, request: Request, user: WebUser):
    require(user, "coverage_run_start")
    runtime = runtime_of(request)
    meta = await store_call(runtime.store.meta, run_id)
    if meta["state"] not in {"cancelled", "interrupted"}:
        raise HTTPException(409, detail="invalid_state")
    # A run keeps the prompts it was created with; results from two prompt versions never mix.
    if meta.get("prompt_version") != prompts.PROMPT_VERSION:
        raise HTTPException(409, detail="prompt_changed")
    await store_call(runtime.store.set_state, run_id, "queued")
    runtime.jobs.enqueue(run_id)
    return {"run_id": run_id, "state": "queued"}


@router.get("/api/knowledge-coverage/checks/{run_id}/export")
async def export_check(run_id: str, request: Request, user: WebUser):
    require(user, "coverage_results_view")
    store = runtime_of(request).store
    items = await store_call(store.inputs, run_id)
    codes = await store_call(store.result_codes, run_id)

    async def lines():
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(EXPORT_COLUMNS)
        yield "﻿" + buffer.getvalue()
        for item in items:
            buffer.seek(0)
            buffer.truncate()
            found = await run_in_threadpool(store.result, run_id, item["row"]) if item["row"] in codes else None
            writer.writerow(export_line(item, found))
            yield buffer.getvalue()

    return StreamingResponse(lines(), media_type="text/csv; charset=utf-8", headers={
        **NO_STORE, "Content-Disposition": f'attachment; filename="coverage-{run_id}.csv"'})
