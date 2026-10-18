"""Evaluate a repeated question once per run.

A later row copies an earlier completed row of the same run only when every
row-specific input the evaluation reads is identical. Rows with uncertain
preparation or history never copy and are never copied. Keys and previews
hold digests and counts only, never text.
"""
import copy

from utils.read_only_audit import canonical_sha256

VERSION = "repeated-question-1"
# QueryPreparer.prepare keys that belong to the copy itself. processing_status,
# coverage_status and scope_status are also returned there, but evaluation
# overwrites them, so a copy carries the source's values.
PREPARED_KEYS = ("source_row_id", "source_record_ordinal", "source_query_id", "safe_session_ref",
                 "timestamp", "timestamp_status", "timestamp_provenance", "input_query_redacted",
                 "normalized_query_redacted", "standalone_query_redacted", "canonical_retrieval_query_redacted",
                 "existing_intent", "preparation_status", "model_prepared", "rewrite_status",
                 "preparation_errors", "uncertainty_codes", "history_provenance", "history_status")
# Row lineage the job loop seeds, plus this attempt's own accounting.
ROW_KEYS = ("processing_ordinal", "model_selected")
ATTEMPT_KEYS = ("attempt_count", "run_identity_id", "duration_ms", "model_metrics", "retrieval_metrics",
                "validation_diagnostics", "output_recovery_count", "failure_diagnostics", "request_journal",
                "validated_checkpoint_count", "checkpoint_reuse_count", "unknown_completion_count")
OWN_KEYS = PREPARED_KEYS + ROW_KEYS + ATTEMPT_KEYS


def enabled(settings):
    """Only runs whose pinned settings name this policy copy rows."""
    return settings.get("dedupe_policy") == VERSION


def _history_known(provenance):
    return (isinstance(provenance, dict) and provenance.get("history_status") in {"unavailable", "user_only"}
            and provenance.get("prior_order_ambiguous") is False and provenance.get("unresolved_peer_times") is False
            and provenance.get("equal_timestamp_event_count") == 0)


def eligible(prepared):
    return (prepared.get("preparation_status") == "prepared" and prepared.get("uncertainty_codes") == []
            and prepared.get("rewrite_status") in {"no_prior_history", "rewritten"}
            and bool(prepared.get("existing_intent")) and _history_known(prepared.get("history_provenance")))


def key(identity, prepared):
    if not eligible(prepared):
        return None
    return canonical_sha256({"version": VERSION, "identity": identity,
        **{k: prepared[k] for k in ("input_query_redacted", "normalized_query_redacted", "standalone_query_redacted",
                                    "canonical_retrieval_query_redacted", "existing_intent", "scope_status",
                                    "rewrite_status", "history_status")},
        "history_digest": prepared["history_provenance"]["history_digest"]})


def run_identity(meta):
    """Constant within a run; part of every key, so keys never match across runs.

    Two runs on the same setup share every other field here, so run_id is what
    keeps their keys apart.
    """
    settings = meta["settings"]
    return canonical_sha256({"run_id": meta["run_id"], "dataset_id": meta["dataset_id"], "snapshot_id": meta["snapshot_id"],
                             "run_identity_id": meta["run_identity_id"], "configuration_id": meta["configuration_id"],
                             "documents": settings["documents"], "entry_budget": settings["entry_budget"],
                             "versions": meta["versions"]})


def candidate_key(preparation_row):
    """Pre-run key over stored preparation rows, for the preview only."""
    if (preparation_row.get("preparation_status") not in {"pending_model", "prepared"}
            or preparation_row.get("uncertainty_codes") or not _history_known(preparation_row.get("history_provenance"))):
        return None
    return canonical_sha256({"input_query_redacted": preparation_row["input_query_redacted"],
                             "normalized_query_redacted": preparation_row["normalized_query_redacted"],
                             "history_status": preparation_row["history_provenance"]["history_status"],
                             "history_digest": preparation_row["history_provenance"]["history_digest"]})


def preview(preparation_rows, row_ids):
    """Counts only: rows that may copy an earlier row; never text or keys."""
    wanted = set(row_ids)
    keys = [k for k in (candidate_key(r) for r in preparation_rows if r.get("source_row_id") in wanted) if k is not None]
    return {"policy": VERSION, "candidate_rows": len(keys), "distinct_questions": len(set(keys)),
            "possible_copies": len(keys) - len(set(keys))}


def is_source(row):
    return (row.get("processing_status") == "completed" and bool(row.get("dedupe_key_sha256"))
            and not row.get("deduplicated_from_row_id"))


def register(sources, row):
    """Keep the first completed, model-evaluated row per key; row IDs only."""
    if is_source(row):
        sources.setdefault(row["dedupe_key_sha256"], row["source_row_id"])


def source_map(store, meta):
    """Rebuilt from the stored rows of this run, in processing order."""
    sources = {}
    rows = store._path("runs", meta["run_id"]) / "rows"
    for row_id in meta.get("processing_row_ids", meta["selected_row_ids"]):
        register(sources, store.read(rows / (row_id + ".json")))
    return sources


def copy_result(source, own):
    result = copy.deepcopy(source)
    for name in OWN_KEYS:
        if name in own:
            result[name] = copy.deepcopy(own[name])
        else:
            # Never present the source's accounting as this row's own.
            result.pop(name, None)
    result.update(deduplicated_from_row_id=source["source_row_id"], dedupe_key_sha256=own["dedupe_key_sha256"],
                  model_evaluated=False, entry_model_dispatched=False)
    # stopping_reason stays the source's: the copy's evaluation scope is the source's.
    return result
