"""Validated permanent A2 configuration. Access is explicitly deny by default."""
from dataclasses import dataclass, field, asdict
import json
import os
from pathlib import Path

from knowledge_audit import referrals
from knowledge_audit.privacy import AuditError, normalize_public_contact
from knowledge_audit.operations import Limits

CAPABILITIES = frozenset({"coverage_run_start", "coverage_results_view",
                          "coverage_evidence_view", "coverage_export_download",
                          "coverage_recommendation_review"})


def coverage_enabled(environ=None) -> bool:
    env = os.environ if environ is None else environ
    enabled = env.get("KNOWLEDGE_COVERAGE_ENABLED", "").strip().lower() == "true"
    environment = env.get("ENVIRONMENT", "").strip().lower()
    if enabled and environment == "production":
        raise AuditError("coverage_enabled_in_production")
    return enabled and environment == "staging"


def require_coverage_enabled(environ=None) -> None:
    if not coverage_enabled(environ):
        raise AuditError("coverage_disabled")


@dataclass(frozen=True)
class CoverageSettings:
    artifact_dir: Path
    access_grants: dict[str, list[str]]
    upload_max_bytes: int
    model_max_tokens: int
    token_margin: int
    batch_max_entries: int = 2
    max_run_rows: int = 10000
    operational_limits: Limits = field(default_factory=Limits)
    recommendation_max_completions: int = 20
    retention_days: int = 30
    initial_depth: int = 150
    broader_depth: int = 300
    initial_entries: int = 50
    max_entry_budget: int = 300
    public_contacts: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.operational_limits,Limits):raise AuditError("invalid_operational_limits")
        if type(self.batch_max_entries) is not int or not 1 <= self.batch_max_entries <= 5:
            raise AuditError("invalid_coverage_batch_max_entries")

        if type(self.max_run_rows) is not int or not 5 <= self.max_run_rows <= 100000:
            raise AuditError("invalid_coverage_max_run_rows")

        if type(self.recommendation_max_completions) is not int or not 1<=self.recommendation_max_completions<=10000:
            raise AuditError('invalid_recommendation_completion_limit')
        if type(self.retention_days) is not int or not 1<=self.retention_days<=3650:
            raise AuditError('invalid_retention_days')
        if any(type(v) is not int for v in (self.initial_depth, self.broader_depth, self.initial_entries, self.max_entry_budget)):
            raise AuditError("invalid_coverage_integer")
        if not 1 <= self.initial_entries <= self.initial_depth < self.broader_depth or not 1 <= self.max_entry_budget:
            raise AuditError("invalid_coverage_depths")
        if type(self.public_contacts) is not tuple or any(type(c) is not str for c in self.public_contacts):
            raise AuditError("invalid_coverage_public_contacts")

    def manifest(self):
        from utils.read_only_audit import canonical_sha256
        return {"artifact_dir": str(self.artifact_dir), "access_grants_sha256": canonical_sha256(self.access_grants),
                "upload_max_bytes": self.upload_max_bytes, "model_max_tokens": self.model_max_tokens,
                "token_margin": self.token_margin, "schema": "coverage-settings-5", "operational_policy": "audit-operations-1", "operational_limits": asdict(self.operational_limits), "recommendation_max_completions": self.recommendation_max_completions, "retention_policy": {"version":"manual-dependency-retention-1","days":self.retention_days,"automatic_deletion":False}, "max_run_rows": self.max_run_rows, "execution_policy": "coverage-execution-1", "checkpoint_policy": "audit-boundaries-1",
                "structured_output_mode": "json_schema_strict_1", "proof_reuse_version": "question-ledger-2",
                "run_identity_version": "run-identity-1", "export_revision_version": "immutable-export-1",
                "json_syntax_recovery_attempts": 1, "recovery_policy": "json-invalid-stop-one-fresh-response-1",
                "failure_policy": "audit-failures-1", "model_deadline_policy": "production-client-inherited-1",
                "network_retries": 0, "unknown_server_completion_policy": "retain_error_no_automatic_retry",
                "initial_depths": [self.initial_depth] * 3, "expanded_depths": [self.broader_depth] * 3,
                "initial_entries": self.initial_entries, "maximum_distinct_entries": self.max_entry_budget, "batch_entries": self.batch_max_entries,
                "batch_max_entries": self.batch_max_entries, "batch_policy": "full-entries-configurable-1",
                "pilot_query_limit": 5, "model_concurrency": 1, "referral_guard_version": referrals.VERSION}


def load_coverage_settings(environ=None) -> CoverageSettings:
    env = os.environ if environ is None else environ
    root = Path(__file__).resolve().parents[1]
    path = Path(env.get("KNOWLEDGE_COVERAGE_ARTIFACT_DIR", "/root/projects/faq-private/knowledge-coverage"))
    if not path.is_absolute() or path == root or root in path.parents or Path("/tmp") == path or Path("/tmp") in path.parents:
        raise AuditError("invalid_durable_artifact_directory")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise AuditError("artifact_symlink_forbidden")
    try:
        grants = json.loads(env.get("KNOWLEDGE_COVERAGE_ACCESS_GRANTS", "{}"))
        if not isinstance(grants, dict) or any(not isinstance(uid, str) or not uid.isascii() or
                not uid.isdecimal() or int(uid) <= 0 or str(int(uid)) != uid or
                not isinstance(caps, list) or any(not isinstance(c, str) or c not in CAPABILITIES for c in caps)
                for uid, caps in grants.items()):
            raise ValueError()
    except (ValueError, TypeError):
        raise AuditError("invalid_coverage_access_grants") from None
    def integer(key, default, low, high):
        try:
            raw = env.get(key, str(default))
            if type(raw) not in {str, int}:
                raise ValueError()
            value = int(raw)
        except (ValueError, TypeError):
            raise AuditError("invalid_coverage_integer") from None
        if not low <= value <= high:
            raise AuditError("invalid_coverage_integer")
        return value
    raw_contacts = env.get("KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS", "")
    if not isinstance(raw_contacts, str):
        raise AuditError("invalid_coverage_public_contacts")
    contacts = tuple(dict.fromkeys(normalize_public_contact(entry)
                                   for entry in raw_contacts.split(","))) if raw_contacts.strip() else ()
    return CoverageSettings(path, grants,
        integer("KNOWLEDGE_COVERAGE_UPLOAD_MAX_BYTES", 5242880, 1024, 20971520),
        integer("KNOWLEDGE_COVERAGE_MODEL_MAX_TOKENS", 1200, 256, 4096),
        integer("KNOWLEDGE_COVERAGE_TOKEN_MARGIN", 128, 32, 1024),
        integer("KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES", 2, 1, 5),
        integer("KNOWLEDGE_COVERAGE_MAX_RUN_ROWS", 10000, 5, 100000),
        Limits(integer("KNOWLEDGE_COVERAGE_MAX_COMPLETIONS",200,1,100000),
            integer("KNOWLEDGE_COVERAGE_MAX_TOKENS",1000000,1,1000000000),
            integer("KNOWLEDGE_COVERAGE_MAX_EXECUTION_SECONDS",3600,1,604800),
            integer("KNOWLEDGE_COVERAGE_MAX_CONSECUTIVE_FAILURES",3,1,100),
            integer("KNOWLEDGE_COVERAGE_MIN_FREE_BYTES",1073741824,0,1099511627776),
            integer("KNOWLEDGE_COVERAGE_PACE_MS",500,0,60000)),
        integer("KNOWLEDGE_RECOMMENDATION_MAX_COMPLETIONS",20,1,10000),
        integer("KNOWLEDGE_COVERAGE_RETENTION_DAYS",30,1,3650),
        integer("KNOWLEDGE_COVERAGE_INITIAL_DEPTH",150,1,1000),
        integer("KNOWLEDGE_COVERAGE_BROADER_DEPTH",300,2,1000),
        integer("KNOWLEDGE_COVERAGE_INITIAL_ENTRIES",50,1,1000),
        integer("KNOWLEDGE_COVERAGE_MAX_ENTRY_BUDGET",300,1,1000),
        contacts)


def grants_for(user_id: int) -> frozenset[str]:
    return frozenset(load_coverage_settings().access_grants.get(str(user_id), []))
