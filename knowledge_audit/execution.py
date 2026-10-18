"""File-backed execution selection and rebuildable progress index (no inference)."""
from collections import Counter
from contextlib import contextmanager, nullcontext
import fcntl
import os
import re
import secrets

from knowledge_audit.operations import VERSION as OPERATIONS_VERSION
from knowledge_audit.privacy import AuditError, private_directory
from utils.read_only_audit import canonical_sha256

VERSION = "coverage-execution-1"
TERMINAL = {"completed", "excluded", "needs_context", "needs_review", "invalid_input", "failed"}
SUMMARY = ("source_row_id", "source_record_ordinal", "input_query_redacted", "preparation_status", "history_status",
           "processing_status", "coverage_status", "outcome", "evaluated_entry_count", "production_context_sufficiency",
           "attempt_count", "unknown_completion_count", "model_prepared", "validated_checkpoint_count", "model_evaluated", "entry_model_dispatched")


@contextmanager
def creation_lock(store, owner):
    fd = os.open(store.root / ("creation-" + str(int(owner)) + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def create_run(store, owner, did, sid, selected_ids, settings, versions, *, execution_mode, idempotency_key):
    from knowledge_audit.store import now
    from knowledge_audit.snapshot import SNAPSHOT_VERSION
    data, _ = store.dataset(did, owner)
    if store.snapshot(sid, owner).get("schema_version") != SNAPSHOT_VERSION:
        raise AuditError("snapshot_policy_superseded")
    rows = store.preparations(did, owner)
    available = [e.source_row_id for e in data.selected]
    maximum = settings.get("max_run_rows", 10000)
    if type(maximum) is not int or not 5 <= maximum <= 100000:
        raise AuditError("invalid_run_size_limit")
    if execution_mode == "full_input":
        if selected_ids:
            raise AuditError("full_input_selection_is_server_resolved")
        selected_ids = available.copy()
    elif execution_mode not in {"pilot", "subset"}:
        raise AuditError("invalid_execution_mode")
    if (not selected_ids or len(set(selected_ids)) != len(selected_ids) or not set(selected_ids) <= set(available)
            or execution_mode == "pilot" and len(selected_ids) > 5):
        raise AuditError("invalid_pilot_selection" if execution_mode == "pilot" else "invalid_run_selection")
    if len(selected_ids) > maximum:
        raise AuditError("run_selection_exceeds_maximum")
    # Source order is exported; a separate replay order uses A1's chronological policy.
    chosen = set(selected_ids)
    selected_ids = [rid for rid in available if rid in chosen]
    chronological = [e.source_row_id for e in data.processing_order() if e.selected and e.source_row_id in chosen]
    request_id = canonical_sha256({"dataset": did, "snapshot": sid, "rows": selected_ids, "mode": execution_mode,
                                   "settings": settings, "versions": versions})
    if idempotency_key is not None and not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", idempotency_key):
        raise AuditError("invalid_idempotency_key")
    # A deterministic owner/key address also survives a crash before the response/pointer write.
    rid = "r_" + (canonical_sha256([owner, idempotency_key])[:32] if idempotency_key else secrets.token_hex(16))
    with creation_lock(store, owner):
        path = store._path("runs", rid)
        if path.exists() and (path / "meta.json").exists():
            prior = store.owned("runs", rid, owner)
            if prior.get("creation_request_id") != request_id:
                raise AuditError("idempotency_request_conflict")
            return prior
        private_directory(path)
        intent = path / "creation.json"
        if intent.exists() and store.read(intent)["request_id"] != request_id:
            raise AuditError("idempotency_request_conflict")
        store.write(intent, {"request_id": request_id})
        private_directory(path / "rows")
        meta = {"run_id": rid, "owner_id": owner, "dataset_id": did, "snapshot_id": sid, "input_id": data.input_id,
                "execution_version": VERSION, "operational_policy": OPERATIONS_VERSION, "execution_mode": execution_mode, "creation_request_id": request_id,
                "selected_row_ids": selected_ids, "processing_row_ids": chronological, "row_ids": available,
                "selected_row_count": len(selected_ids), "input_row_count": len(available), "source_input_row_count": len(data.events),
                "ordering_provenance": "a1_timestamp_then_stable_source_ordinal_unverified_ties",
                "state": "queued", "stage": "waiting", "created_at": now(), "updated_at": now(),
                "settings": settings, "configuration_id": canonical_sha256(settings), "versions": versions,
                "processed_rows": 0, "attempt": 0, "error_code": "", "cancel_requested": False}
        if execution_mode == "pilot":
            meta["completed_pilot_rows"] = 0
        if [r["source_row_id"] for r in rows] != available:
            raise AuditError("input_row_accounting_mismatch")
        initial_rows = []
        for row in rows:
            initial = {**row, "processing_status": "pending", "coverage_status": "not_evaluated",
                       "model_selected": row["source_row_id"] in chosen,
                       "outcome": "needs_context" if row["preparation_status"] == "needs_context" else "pending",
                       "recommendation_status": "unassessed", "recommendations": [], "attempt_count": 0,
                       "unknown_completion_count": 0, "model_evaluated": False, "entry_model_dispatched": False, "stopping_reason": "pending", "evaluated_entry_count": 0}
            if row["preparation_status"] in {"invalid_input", "failed"}:
                initial.update(processing_status="invalid_input" if row["preparation_status"] == "invalid_input" else "failed",
                               outcome="error", stopping_reason="invalid_input")
            store.write(path / "rows" / (row["source_row_id"] + ".json"), initial)
            initial_rows.append(initial)
        store.write(path / "progress.json", build_index(meta, initial_rows))
        from knowledge_audit.operations import Budget, Limits
        Budget(store,path,owner,Limits.from_settings(settings))
        store.write(path / "meta.json", meta)  # publish only after all source rows exist
        return meta


def summary(row):
    return {k: row[k] for k in SUMMARY if k in row}


def build_index(meta, rows):
    return {"version": VERSION, "selection_id": canonical_sha256(meta["selected_row_ids"]),
            "rows": {r["source_row_id"]: summary(r) for r in rows}}


def _index(store, rid, owner, meta, reconcile=False):
    path = store._path("runs", rid)
    if not meta.get('execution_version'):
        return build_index(meta, store.rows(rid, owner))  # legacy reads never add artifacts
    index = None
    if not reconcile and (path / "progress.json").exists() and not (path / "progress-dirty.json").exists():
        index = store.read(path / "progress.json")
    if index is None or index.get("selection_id") != canonical_sha256(meta["selected_row_ids"]):
        index = build_index(meta, store.rows(rid, owner))
        store.write(path / "progress.json", index)
        (path / "progress-dirty.json").unlink(missing_ok=True)
    return index


def save_row(store, rid, row, owner):
    with store.run_lock(rid):
        meta = store.owned("runs", rid, owner)
        if row["source_row_id"] not in meta["selected_row_ids"]:
            raise AuditError("invalid_result_identity")
        path = store._path("runs", rid)
        index = _index(store, rid, owner, meta)
        # Dirty marker precedes the authoritative write. Any interrupted pair is rebuilt.
        store.write(path / "progress-dirty.json", {"row_id": row["source_row_id"]})
        store.write(path / "rows" / (row["source_row_id"] + ".json"), row)
        index["rows"][row["source_row_id"]] = summary(row)
        store.write(path / "progress.json", index)
        (path / "progress-dirty.json").unlink(missing_ok=True)


def progress(store, rid, owner, *, reconcile=False):
    original = store.owned("runs", rid, owner)
    with store.run_lock(rid) if original.get("execution_version") else nullcontext():
        meta = store.owned("runs", rid, owner)
        index = _index(store, rid, owner, meta, reconcile)
        rows = list(index["rows"].values())
        selected = [index["rows"][row_id] for row_id in meta["selected_row_ids"]]
        processed = sum(r["processing_status"] in TERMINAL for r in selected)
        return {"imported_rows": len(rows), "selected_rows": len(selected), "processed_rows": processed,
                "model_evaluated_rows": sum(r.get("model_evaluated", False) for r in selected) if meta.get("execution_version") else None,
                "model_dispatched_rows": sum(r.get("entry_model_dispatched", False) for r in selected) if meta.get("execution_version") else None,
                "entry_evaluation_attempted_rows": sum(r.get("evaluated_entry_count", 0) > 0 for r in selected),
                "pending_rows": sum(r["processing_status"] not in TERMINAL for r in selected),
                "interrupted_rows": sum(r["processing_status"] in {"interrupted", "cancelled"} for r in selected),
                "unknown_completion_count": sum(r.get("unknown_completion_count", 0) for r in selected),
                "validated_checkpoint_count": sum(r.get("validated_checkpoint_count", 0) for r in selected),
                "retryable_rows": sum(r["processing_status"] in {"failed", "interrupted", "cancelled"} for r in selected),
                "outcome_counts": dict(Counter(r["outcome"] for r in rows)),
                "selected_outcome_counts": dict(Counter(r["outcome"] for r in selected)),
                "preparation_counts": dict(Counter(r["preparation_status"] for r in rows))}


def result_page(store, rid, owner, offset, limit, outcome, search):
    original = store.owned("runs", rid, owner)
    with store.run_lock(rid) if original.get("execution_version") else nullcontext():
        meta = store.owned("runs", rid, owner)
        rows = _index(store, rid, owner, meta)["rows"]
        filtered = [rows[key] for key in meta["row_ids"] if (not outcome or rows[key]["outcome"] == outcome)
                    and (not search or search.casefold() in rows[key].get("input_query_redacted", "").casefold())]
        return {"total": len(filtered), "source_total": len(rows), "rows": filtered[offset:offset + limit]}


def attempt_seed(row):
    """New effective work keeps lineage/preparation; previous verdicts live in attempts."""
    from knowledge_audit.export import FIELDS
    keep = set(FIELDS) | {'attempt_count', 'unknown_completion_count', 'validated_checkpoint_count', 'request_journal',
                          'evaluated_entry_count', 'evaluated_entry_ids', 'model_evaluated', 'entry_model_dispatched'}
    return {k: v for k, v in row.items() if k in keep}
