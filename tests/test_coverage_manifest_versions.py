"""The settings manifest pins every policy this branch added, under schema coverage-settings-6."""
from knowledge_audit import dedupe, failures, operations, recovery, referrals
from knowledge_audit.settings import load_coverage_settings

POLICY_KEYS = {
    "proof_reuse_version": "question-ledger-2",
    "referral_guard_version": "referral-guard-1",
    "reachability_policy_version": "redaction-reachability-1",
    "verification_policy": "order-permuted-2",
    "failure_policy": "audit-failures-2",
    "operational_policy": "audit-operations-2",
    "checkpoint_policy": "audit-boundaries-2",
    "dedupe_policy": "repeated-question-1",
    "recommendation_review_policy": "second-reviewer-1",
}


def test_manifest_schema_and_policy_keys():
    manifest = load_coverage_settings({}).manifest()
    assert manifest["schema"] == "coverage-settings-6"
    assert {key: manifest[key] for key in POLICY_KEYS} == POLICY_KEYS
    # Hard-coded manifest strings must follow the modules that own them.
    assert manifest["failure_policy"] == failures.VERSION
    assert manifest["operational_policy"] == operations.VERSION
    assert manifest["checkpoint_policy"] == recovery.VERSION
    assert manifest["referral_guard_version"] == referrals.VERSION
    assert manifest["dedupe_policy"] == dedupe.VERSION
