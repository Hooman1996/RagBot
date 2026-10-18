"""Versioned redacted KB content capture and strict live-source/index drift gate.

Read-only REPEATABLE READ freezes PostgreSQL during capture. Qdrant remains live;
matching bracketing signatures detect observed drift, not concurrent ABA writes.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from knowledge_audit.privacy import AuditError, Redactor, private_json
from utils.faq_content import parse_faq_content
from utils.read_only_audit import canonical_sha256, text_sha256


# Version 1 snapshots ran KB text through the customer-query redactor. They stay
# readable and exportable but cannot start new runs.
SNAPSHOT_VERSION = "a1-kb-snapshot-2"
READABLE_SNAPSHOT_VERSIONS = frozenset({"a1-kb-snapshot-1", SNAPSHOT_VERSION})


def assert_compatible(reference: dict, current: dict) -> None:
    from scripts.kb_signature import compare_signatures
    if not compare_signatures(reference, current)["status"]["FULL_MATCH"]:
        raise AuditError("source_or_index_drift")


def read_postgres_snapshot(connection_factory) -> dict:
    """Use the repository's authoritative chunk SQL and existing revision table."""
    import psycopg2.extras
    from scripts.kb_signature import POSTGRES_CHUNK_QUERY
    connection = connection_factory()
    try:
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(POSTGRES_CHUNK_QUERY)
            rows = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT document_id, revision FROM knowledge_document_revisions ORDER BY document_id")
            revisions = {str(row["document_id"]): int(row["revision"]) for row in cursor.fetchall()}
            cursor.execute("SELECT to_regclass('chunk_versions') AS relation")
            version_ids = {}
            if cursor.fetchone()["relation"]:
                cursor.execute("SELECT chunk_id, MAX(id) AS version_id FROM chunk_versions GROUP BY chunk_id ORDER BY chunk_id")
                version_ids = {str(row["chunk_id"]): int(row["version_id"]) for row in cursor.fetchall()}
        return {"rows": rows, "document_revisions": revisions, "latest_stored_version_ids": version_ids}
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def _source_records(rows: list[dict]) -> list[dict]:
    from scripts.kb_signature import _mapping_metadata
    records = []
    for row in rows:
        if row.get("chunk_id") is None or not isinstance(row.get("content"), str):
            raise AuditError("snapshot_invalid_source_record")
        mapping = _mapping_metadata(row.get("document_id"), row.get("chunk_index"), row.get("document_title"))
        records.append({"chunk_id": str(row["chunk_id"]), **mapping,
                        "content_sha256": text_sha256(row["content"]),
                        "metadata_sha256": canonical_sha256({**mapping, "chunk_type": row.get("chunk_type"),
                            "page_number": row.get("page_number"), "chunk_meta_data": row.get("chunk_meta_data")}),
                        "cross_store_metadata_sha256": canonical_sha256(mapping)})
    return sorted(records, key=lambda r: (r["chunk_id"], r["document_id"] or "", r["chunk_index"], r["content_sha256"]))


def capture_snapshot(directory: Path, redactor: Redactor, *, signature_provider,
                     content_provider, public_contacts=()) -> dict:
    before = signature_provider("a1-snapshot-before")
    if before["cross_store"].get("consistent") is not True:
        raise AuditError("snapshot_cross_store_inconsistent")
    capture = content_provider()
    after = signature_provider("a1-snapshot-after")
    assert_compatible(before, after)
    raw_rows = capture["rows"]
    records = _source_records(raw_rows)
    # Verify the actual transactional content against both signatures; merely
    # obtaining unchanged bracketing signatures does not prove capture equality.
    if records != before["postgres"]["records"] or len({r["chunk_id"] for r in records}) != len(records):
        raise AuditError("snapshot_capture_mismatch")
    chunks = []
    for row in raw_rows:
        # KB content policy, not the customer-query policy: public bank facts stay.
        content = redactor.kb_text(row["content"], public_contacts)
        parts = parse_faq_content(content)
        chunk_id = str(row["chunk_id"])
        chunks.append({"chunk_id": chunk_id, "faq_entry_id": chunk_id if parts.is_qa else None,
            "document_id": str(row["document_id"]), "chunk_index": row["chunk_index"],
            "document_title": redactor.kb_text(row["document_title"], public_contacts),
            "content": content, "question": parts.question, "answer": parts.answer,
            "main_category": parts.main_category, "sub_category": parts.sub_category,
            "taxonomy_status": "ambiguous" if parts.taxonomy_error else "parsed" if parts.is_qa else "not_faq",
            "source_content_sha256": text_sha256(row["content"]), "content_sha256": text_sha256(content),
            "redaction_changed": content != row["content"],
            "document_revision": capture["document_revisions"].get(str(row["document_id"]), 0),
            "latest_stored_version_id": capture["latest_stored_version_ids"].get(chunk_id)})
    chunks.sort(key=lambda c: c["chunk_id"])
    snapshot = {"schema_version": SNAPSHOT_VERSION, "records": chunks,
                "source_signature": before, "bracketing_signature": after,
                "document_revisions": capture["document_revisions"], "redaction_version": redactor.version,
                "kb_redaction_policy": {"version": redactor.kb_version,
                                        "public_contacts_sha256": canonical_sha256(sorted(public_contacts))},
                "consistency": "repeatable_read_verified_against_bracketing_signatures",
                "retrieval_frozen": False, "faq_identity_policy": "one_recognized_faq_chunk; no inferred grouping",
                "capture_code_sha256": {str(path.relative_to(Path(__file__).resolve().parents[1])):
                    hashlib.sha256(path.read_bytes()).hexdigest() for path in
                    (Path(__file__), Path(__file__).with_name("privacy.py"),
                     Path(__file__).resolve().parents[1] / "scripts/kb_signature.py")}}
    snapshot["snapshot_id"] = canonical_sha256(snapshot)
    private_json(directory / "kb-snapshot.json", snapshot)
    manifest = {"schema_version": "a1-kb-manifest-2", "snapshot_id": snapshot["snapshot_id"],
                "content_file": "kb-snapshot.json", "content_file_sha256": hashlib.sha256(
                    (directory / "kb-snapshot.json").read_bytes()).hexdigest(),
                "record_count": len(chunks), "redacted_record_count": sum(c["redaction_changed"] for c in chunks),
                "source_signature_identity": canonical_sha256(before),
                "source_pg_identity": before["postgres"]["aggregate_sha256"],
                "consistency": snapshot["consistency"], "retrieval_frozen": False}
    private_json(directory / "kb-snapshot-manifest.json", manifest)
    return manifest


def load_snapshot(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise AuditError("snapshot_permissions")
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        identity = snapshot.pop("snapshot_id")
        if snapshot.get("schema_version") not in READABLE_SNAPSHOT_VERSIONS or canonical_sha256(snapshot) != identity:
            raise AuditError("snapshot_identity_mismatch")
        if any(text_sha256(row["content"]) != row["content_sha256"] for row in snapshot["records"]):
            raise AuditError("snapshot_content_mismatch")
        snapshot["snapshot_id"] = identity
        return snapshot
    except (ValueError, KeyError, TypeError):
        raise AuditError("invalid_snapshot") from None


def enforce_run_compatibility(snapshot: dict, current_signature: dict,
                              expected_configuration_id: str, current_configuration_id: str) -> None:
    """Later runner must call before and after each live retrieval/evidence unit.

    Reject and invalidate results on mismatch; never substitute today's KB text.
    For stronger guarantees A2 needs an immutable matching index/checkpoint.
    """
    if expected_configuration_id != current_configuration_id:
        raise AuditError("configuration_drift")
    assert_compatible(snapshot["source_signature"], current_signature)
