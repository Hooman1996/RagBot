"""Reusable A1 CSV/manifest export with exact identity and row conservation."""
from collections import Counter
import csv
from dataclasses import asdict
import hashlib
import io
import re
from pathlib import Path

from knowledge_audit.privacy import AuditError, Redactor, formula_safe, private_json, private_write
from utils.read_only_audit import canonical_json, canonical_sha256


FIELDS = (
    "schema_version", "run_id", "export_id", "source_row_id", "source_query_id",
    "source_record_ordinal", "processing_ordinal", "safe_session_ref", "timestamp", "timestamp_status",
    "input_query_redacted", "normalized_query_redacted", "standalone_query_redacted",
    "canonical_retrieval_query_redacted", "existing_intent", "scope_status", "processing_status",
    "coverage_status", "preparation_status", "model_selected", "model_prepared", "rewrite_status", "history_status",
    "timestamp_provenance", "history_provenance", "preparation_errors", "uncertainty_codes",
    "kb_snapshot_id", "configuration_id", "preparation_code_id", "input_id", "input_scope",
    "selected_input_row_count", "source_input_row_count",
)
STRUCTURED_DEFAULTS = {"timestamp_provenance": {}, "history_provenance": {},
                       "preparation_errors": [], "uncertainty_codes": []}


def _redact(value, redactor, key=""):
    if isinstance(value, str):
        # Generated typed identities are opaque already. Applying PII patterns
        # to hash digits would corrupt row conservation and snapshot references.
        reference_keys = {"source_row_id", "source_query_id", "safe_session_ref", "cutoff_row_id",
                          "history_row_ids", "excluded_equal_timestamp_ids", "history_digest",
                          "input_id", "kb_snapshot_id", "configuration_id", "preparation_code_id",
                          "snapshot_id", "bundle_id", "content_sha256", "source_content_sha256",
                          "run_identity_id", "export_revision_id", "run_id"}
        if (key in reference_keys or key.endswith("_sha256")) and re.fullmatch(r"(?:row|query|session|r|rev)_[0-9a-f]{32}|[0-9a-f]{64}", value):
            return value
        if key in {"chunk_id", "faq_entry_id", "support_id", "entry_id", "supporting_chunk_ids", "supporting_faq_ids", "production_candidate_ids", "production_context_ids", "evaluated_entry_ids", "related_faq_ids", "equivalent_faq_ids"} and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
            return value
        return redactor.text(value)
    if isinstance(value, list):
        return [_redact(v, redactor, key) for v in value]
    if isinstance(value, dict):
        return {k: _redact(v, redactor, k) for k, v in value.items()}
    return value


def encode_csv(rows, fields, expected_ids):
    """Shared A1/A2 byte exporter. Exact source order/IDs and formula-safe views."""
    if [r["source_row_id"] for r in rows] != expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise AuditError("export_row_accounting_mismatch")
    export_id = canonical_sha256(rows)
    rows = [{**row, "export_id": export_id} for row in rows]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: formula_safe(canonical_json(v) if isinstance(v, (dict, list)) else
            "true" if v is True else "false" if v is False else str(v)) for k, v in row.items()})
    data = buffer.getvalue().encode("utf-8-sig")
    parsed = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))
    if [r["source_row_id"] for r in parsed] != expected_ids or any(r["export_id"] != export_id for r in parsed):
        raise AuditError("export_serialization_mismatch")
    return data, export_id


def export_preparation(directory: Path, dataset, results: list[dict], *, run_id: str,
                       configuration: dict, code_identity: dict, redactor: Redactor,
                       snapshot_id: str = "", serving_identity: dict | None = None) -> dict:
    expected_ids = [e.source_row_id for e in dataset.selected]
    actual_ids = [r.get("source_row_id") for r in results]
    if Counter(expected_ids) != Counter(actual_ids) or len(set(actual_ids)) != len(actual_ids):
        raise AuditError("export_row_accounting_mismatch")
    config_id, code_id = canonical_sha256(configuration), canonical_sha256(code_identity)
    rows = []
    for result in sorted(results, key=lambda r: r["source_record_ordinal"]):
        row = {key: result.get(key, STRUCTURED_DEFAULTS.get(key, "")) for key in FIELDS}
        row.update(schema_version="a1-preparation-csv-1", run_id=run_id,
            processing_status="preparation_only", coverage_status="", kb_snapshot_id=snapshot_id,
            configuration_id=config_id, preparation_code_id=code_id, input_id=dataset.input_id,
            input_scope="full_input_preparation_bounded_model_sample",
            selected_input_row_count=len(expected_ids), source_input_row_count=len(dataset.events))
        rows.append(_redact(row, redactor))
    data, export_id = encode_csv(rows, FIELDS, expected_ids)
    private_write(directory / "preparation.csv", data)
    manifest = {"schema_version": "a1-preparation-manifest-1", "run_id": run_id, "export_id": export_id,
                "csv_file": "preparation.csv", "csv_sha256": hashlib.sha256(data).hexdigest(),
                "row_ids": expected_ids, "input_id": dataset.input_id, "input_structure": dataset.structure,
                "mapping": asdict(dataset.mapping),
                "timestamp_policy": asdict(dataset.timestamp_policy),
                "selected_row_count": len(rows), "source_row_count": len(dataset.events),
                "preparation_status_counts": dict(Counter(r["preparation_status"] for r in rows)),
                "model_prepared_count": sum(r["model_prepared"] is True for r in rows),
                "model_sample_row_ids": [r["source_row_id"] for r in rows if r.get("model_selected") is True],
                "configuration": configuration, "configuration_id": config_id,
                "code_identity": code_identity, "preparation_code_id": code_id,
                "kb_snapshot_id": snapshot_id, "snapshot_state": "captured" if snapshot_id else "not_captured",
                "serving_identity": serving_identity or {"status": "not_contacted"},
                "redaction_version": redactor.version, "coverage_evaluation": "not_run",
                "input_scope": "full_input_preparation_bounded_model_sample"}
    private_json(directory / "preparation-manifest.json", manifest)
    return manifest


COVERAGE_FIELDS = FIELDS + ("outcome", "support_arrangement", "production_context_sufficiency", "production_reachability",
    "requested_aspects", "supported_aspects", "unresolved_aspects", "supporting_faq_ids", "supporting_chunk_ids",
    "supporting_sentence_refs", "explanation", "verification_result", "verification_reason", "verifications",
    "production_candidate_ids", "production_context_ids", "production_baseline_version", "evaluated_entry_ids",
    "evaluated_entry_count", "retrieved_candidate_count", "stopping_reason", "evaluation_scope", "evidence_visibility",
    "error_code", "error_reason", "attempt_count", "recommendations", "recommendation_status", "proposed_question",
    "category", "subcategory", "proposed_new_category", "proposed_new_subcategory", "related_existing_faq_ids",
    "equivalent_existing_faq_ids", "rubric_version", "model_versions", "prompt_versions", "tokenizer_versions",
    "normalization_version", "alias_version", "classifier_version", "run_settings_version", "review_codes",
    "run_identity_id", "export_revision_id", "review_codes_by_phase", "evidence_phases", "validation_diagnostics",
    "output_recovery_count", "recovery_policy", "failure_diagnostics", "batch_max_entries")
ARRAY_FIELDS = {"requested_aspects", "supported_aspects", "unresolved_aspects", "supporting_faq_ids", "supporting_chunk_ids",
    "supporting_sentence_refs", "verifications", "production_candidate_ids", "production_context_ids", "evaluated_entry_ids",
    "recommendations", "proposed_question", "category", "subcategory", "proposed_new_category", "proposed_new_subcategory", "failure_diagnostics",
    "related_existing_faq_ids", "equivalent_existing_faq_ids", "review_codes", "preparation_errors", "uncertainty_codes", "validation_diagnostics"}
MAP_FIELDS = {"timestamp_provenance", "history_provenance", "evaluation_scope", "model_versions", "prompt_versions", "tokenizer_versions", "review_codes_by_phase", "evidence_phases"}
RESTRICTED_FIELDS = ARRAY_FIELDS - {"preparation_errors", "uncertainty_codes", "review_codes", "failure_diagnostics"}


def coverage_export(meta, results, redactor, *, evidence_visible):
    rows = []
    for source in results:
        row = {k: source.get(k, [] if k in ARRAY_FIELDS else {} if k in MAP_FIELDS else "") for k in COVERAGE_FIELDS}
        row.update(schema_version="coverage-csv-4", run_id=meta["run_id"], export_id="",
            batch_max_entries=meta["settings"].get("batch_max_entries",meta["settings"].get("batch_entries",2)),
            run_identity_id=meta.get("run_identity_id", ""), export_revision_id=meta.get("export_revision_id", ""),
            kb_snapshot_id=meta["snapshot_id"], configuration_id=meta["configuration_id"], input_id=meta["input_id"],
            input_scope="pilot_subset_full_input_export", selected_input_row_count=len(meta["row_ids"]),
            source_input_row_count=meta.get("source_input_row_count", len(meta["row_ids"])), rubric_version=meta["versions"]["prompts"]["rubric_version"],
            model_versions=meta["versions"].get("serving", {}), prompt_versions=meta["versions"]["prompts"],
            tokenizer_versions={"method": "served_tokenize", "immutable_revision": "unverified"},
            recommendations=[], recommendation_status="unassessed", run_settings_version=meta["configuration_id"],
            preparation_code_id=meta["versions"].get("code_id", ""), production_baseline_version="production-selection-1")
        row["retrieved_candidate_count"] = sum(m["candidate_count"] for m in source.get("retrieval_metrics", []) if m["purpose"] != "production_baseline")
        row["review_codes_by_phase"] = {phase: a.get("review_codes", []) for phase, a in source.get("phase_assessments", {}).items()}
        row["evidence_phases"] = source.get("question_evidence", {}).get("entry_phases", {}) if evidence_visible else {}
        row["evidence_visibility"] = "snapshot_mismatch" if meta["state"] == "incompatible" else "visible" if evidence_visible else "restricted"
        if not evidence_visible:
            for key in RESTRICTED_FIELDS:
                row[key] = []
            for key in ("explanation", "verification_reason", "error_reason"):
                row[key] = ""
        rows.append(_redact(row, redactor))
    data, export_id = encode_csv(rows, COVERAGE_FIELDS, meta["row_ids"])
    manifest = {"schema_version": "coverage-export-manifest-4", "run_id": meta["run_id"], "export_id": export_id,
                "export_revision_id": meta.get("export_revision_id", ""), "export_captured_at": meta.get("export_captured_at", ""),
                "run_identity_id": meta.get("run_identity_id", ""), "run_identities": meta.get("run_identities", {}),
                "run_identity_captured_at": meta.get("run_identity_captured_at", ""),
                "identity_status": "pinned_before_evaluation" if meta.get("run_identities") else "not_pinned",
                "csv_sha256": hashlib.sha256(data).hexdigest(), "row_ids": meta["row_ids"],
                "row_count": len(rows), "pilot_selected_row_ids": meta["selected_row_ids"],
                "input_id": meta["input_id"], "snapshot_id": meta["snapshot_id"],
                "configuration_id": meta["configuration_id"], "settings": meta["settings"], "versions": meta["versions"],
                "state": meta["state"], "evidence_visible": evidence_visible,
                "outcome_counts": dict(Counter(r["outcome"] for r in rows))}
    return data, manifest
