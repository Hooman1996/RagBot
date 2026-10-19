"""Every audit error code is allow-listed or deliberately internal; every review code has a label.

A code is surfaced when its own string is stored on a row, run or recommendation
record, written to an export or sent as an API detail. Surfaced codes must be in
one of the four allow-lists. Every other code is internal-only: each boundary
masks it (the generic 409/500 text, ``audit_failed``, ``failures.category``) or
translates it into a fixed sentence, so the code itself never leaves the process.
"""
import ast
import re
from pathlib import Path

from knowledge_audit.api import SAFE_API_CODES
from knowledge_audit.operations import SAFE_ERRORS
from knowledge_audit.pipeline import BLOCKING_CODES, ERROR_CODES, NOTE_CODES, RESIDUAL_CODES, SEARCH_CODES
from knowledge_audit.recommendations import SAFE_CODES

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "knowledge_audit"
ALLOWED = set(SAFE_API_CODES) | set(ERROR_CODES) | set(SAFE_ERRORS) | set(SAFE_CODES)

CLI = "raised only on an offline CLI path, which prints the code to the operator"
CALIBRATE = "raised only by scripts/knowledge_coverage_calibrate.py or the pilot's human-label packages; printed to the operator"
CLEANUP = "raised only by scripts/knowledge_coverage_cleanup.py; printed to the operator"
FIXTURE = "raised only by the A4 fixture pilot and revalidation scripts; printed to the operator"
INTEGRITY = "stored artifact, snapshot or checkpoint integrity check; masked to the generic 409 or audit_failed"
PATH = "private artifact path or file-mode refusal; masked to the generic 409 or audit_failed"
NOT_FOUND = "safe_call answers 404 'Audit resource not found'; masked to the generic 409 elsewhere"
SETTINGS = "settings validation outside safe_call: fails startup, a CLI or the request with a generic 500"
INVARIANT = "argument or accounting invariant; masked to the generic 409 or audit_failed"
LEDGER = "budget ledger invariant; operations records audit_failed and the API masks it"
EXPORT_MESSAGE = "run_export_api.MESSAGES translates it into a fixed sentence; masked elsewhere"
TIMESTAMP = "caught as ValueError by TimestampPolicy.parse; the row records timestamp_invalid"
CANCEL = "the cancel routes answer with a fixed 'cannot be cancelled' sentence"
MODEL = "model client check; failures.category maps it to a generic category and the row records audit_failed"
LIVE_RUN = "live-run confirmation refusal; raised only on a CLI path without --confirmed, which prints it"
LOCK = "retention lock refusal; masked to the generic 409 or audit_failed, printed by the cleanup CLI"

INTERNAL_ONLY = {
    "a1_archive_hash_mismatch": CLI, "a1_export_hash_mismatch": CLI, "a1_export_identity_mismatch": CLI,
    "a1_export_schema_mismatch": CLI, "a1_input_identity_mismatch": CLI,
    "artifact_directory_permissions": PATH, "artifact_file_permissions": PATH, "artifact_parent_missing": PATH,
    "artifact_repository_forbidden": PATH, "artifact_symlink_forbidden": PATH,
    "artifact_not_found": NOT_FOUND, "invalid_artifact_id": NOT_FOUND,
    "attempt_already_saved": INTEGRITY, "checkpoint_candidate_mismatch": INTEGRITY,
    "checkpoint_schema_mismatch": INTEGRITY, "configuration_drift": INTEGRITY, "export_identity_mismatch": INTEGRITY,
    "export_row_accounting_mismatch": INTEGRITY, "export_serialization_mismatch": INTEGRITY,
    "invalid_privacy_key": INTEGRITY, "invalid_snapshot": INTEGRITY, "snapshot_content_mismatch": INTEGRITY,
    "snapshot_invalid_source_record": INTEGRITY, "snapshot_permissions": INTEGRITY,
    "recommendation_result_drift": INTEGRITY, "recommendation_source_evidence_required": INTEGRITY,
    "calibration_fixture_drift": CALIBRATE, "calibration_label_drift": CALIBRATE,
    "candidate_outside_fixture_snapshot": CALIBRATE, "invalid_calibration_budget": CALIBRATE,
    "invalid_calibration_selection": CALIBRATE, "invalid_seeded_removal": CALIBRATE,
    "duplicate_review_observation": CALIBRATE, "human_label_observation_mismatch": CALIBRATE,
    "human_label_package_mismatch": CALIBRATE, "human_label_snapshot_mismatch": CALIBRATE,
    "human_reviewer_required": CALIBRATE, "invalid_human_labels": CALIBRATE, "invalid_review_package": CALIBRATE,
    "review_package_drift": CALIBRATE, "invalid_review_runs": CALIBRATE, "review_input_mismatch": CALIBRATE,
    "cleanup_new_reference": CLEANUP, "cleanup_path_changed": CLEANUP, "cleanup_plan_identity_mismatch": CLEANUP,
    "cleanup_plan_stale": CLEANUP, "cleanup_safe_delete_unavailable": CLEANUP, "invalid_cleanup_policy": CLEANUP,
    "cleanup_artifacts_busy": LOCK, "cleanup_nested_access": LOCK,
    "invalid_a4_budget": FIXTURE, "recommendation_fixture_drift": FIXTURE,
    "invalid_coverage_batch_max_entries": SETTINGS,
    "invalid_coverage_depths": SETTINGS, "invalid_coverage_integer": SETTINGS,
    "invalid_coverage_max_run_rows": SETTINGS, "invalid_coverage_public_contacts": SETTINGS,
    "invalid_durable_artifact_directory": SETTINGS, "invalid_operational_limits": SETTINGS,
    "invalid_recommendation_completion_limit": SETTINGS, "invalid_retention_days": SETTINGS,
    "duplicate_candidate_identity": INVARIANT, "duplicate_snapshot_ids": INVARIANT, "invalid_audit_depth": INVARIANT,
    "invalid_snapshot_scope": INVARIANT, "input_row_accounting_mismatch": INVARIANT,
    "invalid_order_policy": INVARIANT, "invalid_model_sample_limit": INVARIANT,
    "invalid_preparation_timeout": INVARIANT, "invalid_recovery_choice": INVARIANT,
    "invalid_result_identity": INVARIANT, "invalid_run_size_limit": INVARIANT,
    "invalid_budget_boundary": LEDGER, "invalid_token_reservation": LEDGER, "invalid_service_counter": LEDGER,
    "invalid_operational_limit": LEDGER,
    "export_draft_not_finished": EXPORT_MESSAGE, "export_duplicate_row_selection": EXPORT_MESSAGE,
    "export_incompatible_coverage_source": EXPORT_MESSAGE, "export_unknown_draft_row": EXPORT_MESSAGE,
    "export_unknown_source_row": EXPORT_MESSAGE, "recommendation_review_mismatch": EXPORT_MESSAGE,
    "invalid_jalali_date": TIMESTAMP, "jalali_year_out_of_range": TIMESTAMP, "invalid_timestamp": TIMESTAMP,
    "recommendation_not_active": CANCEL, "run_not_active": CANCEL,
    "invalid_token_count": MODEL, "model_not_discovered": MODEL,
    "live_run_confirmation_required": LIVE_RUN,
}

# The only places an internal-only code may appear other than as a raised code:
# boundaries that translate it into a fixed answer.
TRANSLATIONS = {("api.py", "artifact_not_found"), ("api.py", "invalid_artifact_id")} | {
    ("run_export_api.py", code) for code, reason in INTERNAL_ONLY.items() if reason == EXPORT_MESSAGE}


def _trees():
    return {path.name: ast.parse(path.read_text(encoding="utf-8")) for path in sorted(AUDIT.glob("*.py"))}


def _raised(trees):
    """AuditError("...") literals, including both branches of a conditional code."""
    codes, nodes = {}, set()
    for name, tree in trees.items():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args and
                    getattr(node.func, "id", getattr(node.func, "attr", None)) == "AuditError"):
                continue
            arg = node.args[0]
            for value in [arg] if isinstance(arg, ast.Constant) else [arg.body, arg.orelse] if isinstance(arg, ast.IfExp) else []:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    codes.setdefault(value.value, set()).add(f"{name}:{node.lineno}")
                    nodes.add(id(value))
    return codes, nodes


def test_every_raised_code_is_allow_listed_or_internal_only():
    codes, _ = _raised(_trees())
    assert len(codes) > 150
    unplaced = {code: sorted(where) for code, where in codes.items() if code not in ALLOWED and code not in INTERNAL_ONLY}
    assert not unplaced


def test_internal_only_set_is_exact():
    codes, _ = _raised(_trees())
    assert not set(INTERNAL_ONLY) & ALLOWED
    assert set(INTERNAL_ONLY) <= set(codes), sorted(set(INTERNAL_ONLY) - set(codes))
    assert all(reason and "\n" not in reason for reason in INTERNAL_ONLY.values())


def test_internal_only_codes_are_never_stored_or_sent():
    # Stored or passed-through codes appear as string constants outside AuditError(...),
    # for example in jobs' interrupt sets or a review-reason list.
    trees = _trees()
    _, raised_nodes = _raised(trees)
    found = {(name, node.value) for name, tree in trees.items() for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and node.value in INTERNAL_ONLY and id(node) not in raised_nodes}
    assert found <= TRANSLATIONS, sorted(found - TRANSLATIONS)


def _label_maps():
    source = (ROOT / "static/js/knowledge_coverage.js").read_text(encoding="utf-8")
    maps = {}
    for match in re.finditer(r"const (LABELS\w*) = \{", source):
        body = source[match.end():source.index("\n    };", match.end())]
        maps[match.group(1)] = set(re.findall(r"([A-Za-z_]\w*)\s*:\s*['\"]", body))
    return maps


