"""Validated permanent A2 configuration. Access is explicitly deny by default."""
from dataclasses import dataclass
import json
import os
from pathlib import Path

from knowledge_audit.privacy import AuditError

CAPABILITIES = frozenset({"coverage_run_start", "coverage_results_view",
                          "coverage_evidence_view", "coverage_export_download"})


@dataclass(frozen=True)
class CoverageSettings:
    artifact_dir: Path
    access_grants: dict[str, list[str]]
    upload_max_bytes: int
    model_max_tokens: int
    token_margin: int

    def manifest(self):
        from utils.read_only_audit import canonical_sha256
        return {"artifact_dir": str(self.artifact_dir), "access_grants_sha256": canonical_sha256(self.access_grants),
                "upload_max_bytes": self.upload_max_bytes, "model_max_tokens": self.model_max_tokens,
                "token_margin": self.token_margin, "schema": "coverage-settings-1",
                "initial_depths": [150, 150, 150], "expanded_depths": [300, 300, 300],
                "initial_entries": 50, "maximum_distinct_entries": 300, "batch_entries": 5,
                "pilot_query_limit": 5, "model_concurrency": 1}


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
            value = int(env.get(key, str(default)))
        except (ValueError, TypeError):
            raise AuditError("invalid_coverage_integer") from None
        if not low <= value <= high:
            raise AuditError("invalid_coverage_integer")
        return value
    return CoverageSettings(path, grants,
        integer("KNOWLEDGE_COVERAGE_UPLOAD_MAX_BYTES", 5242880, 1024, 20971520),
        integer("KNOWLEDGE_COVERAGE_MODEL_MAX_TOKENS", 1200, 256, 4096),
        integer("KNOWLEDGE_COVERAGE_TOKEN_MARGIN", 128, 32, 1024))


def grants_for(user_id: int) -> frozenset[str]:
    return frozenset(load_coverage_settings().access_grants.get(str(user_id), []))
