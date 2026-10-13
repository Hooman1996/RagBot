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
                          "input_id", "kb_snapshot_id", "configuration_id", "preparation_code_id"}
        if key in reference_keys and re.fullmatch(r"(?:row|query|session)_[0-9a-f]{32}|[0-9a-f]{64}", value):
            return value
        return redactor.text(value)
    if isinstance(value, list):
        return [_redact(v, redactor, key) for v in value]
    if isinstance(value, dict):
        return {k: _redact(v, redactor, k) for k, v in value.items()}
    return value


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
    export_id = canonical_sha256(rows)
    for row in rows:
        row["export_id"] = export_id
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: formula_safe(canonical_json(v) if isinstance(v, (dict, list)) else
                                       "true" if v is True else "false" if v is False else str(v)) for k, v in row.items()})
    data = buffer.getvalue().encode("utf-8-sig")
    # An independent parse validates identity/count/order after serialization.
    parsed = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))
    if [r["source_row_id"] for r in parsed] != expected_ids or any(r["export_id"] != export_id for r in parsed):
        raise AuditError("export_serialization_mismatch")
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
