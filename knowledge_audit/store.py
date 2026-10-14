"""Protected atomic file checkpoints, following existing in-process job patterns.

No new database schema/infrastructure. An OS file lease prevents two workers from
processing the same run; recovery is explicit and completed rows are immutable.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

from knowledge_audit.inputs import ImportedDataset, InputEvent, ColumnMapping, TimestampPolicy, CsvInputAdapter
from knowledge_audit.privacy import AuditError, Redactor, private_directory, private_json, private_write
from knowledge_audit.export import FIELDS, STRUCTURED_DEFAULTS
from knowledge_audit.snapshot import load_snapshot
from utils.read_only_audit import canonical_json, canonical_sha256


def now():
    return datetime.now(timezone.utc).isoformat()


class BytesInput:
    def __init__(self, data: bytes):
        self.data = data
    def read_bytes(self):
        return self.data


class CoverageStore:
    def __init__(self, root: Path, *, ephemeral_test_store=False):
        # Validate configuration before creating directories, even in CLI mode.
        from knowledge_audit.settings import load_coverage_settings
        if not ephemeral_test_store:
            load_coverage_settings({"KNOWLEDGE_COVERAGE_ARTIFACT_DIR": str(root)})
        if not root.exists():
            root.mkdir(parents=True, mode=0o700)
        self.root = private_directory(root)
        for name in ("datasets", "snapshots", "runs", "archive"):
            private_directory(self.root / name)

    def _path(self, kind, identity):
        patterns = {"datasets": r"d_[0-9a-f]{32}", "runs": r"r_[0-9a-f]{32}", "snapshots": r"[0-9a-f]{64}"}
        if not re.fullmatch(patterns[kind], identity):
            raise AuditError("invalid_artifact_id")
        return self.root / kind / identity

    def read(self, path):
        private_directory(path.parent)
        if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
            raise AuditError("artifact_file_permissions")
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, path, payload):
        temporary = path.with_name(".checkpoint-" + secrets.token_hex(16))
        private_json(temporary, payload)
        os.replace(temporary, path)

    def list_owned(self, kind, owner):
        rows = []
        for p in sorted((self.root / kind).iterdir(), reverse=True):
            if not p.is_dir() or p.is_symlink():
                continue
            try:
                meta = self.read(p / "meta.json")
                if meta.get("owner_id") == owner or (kind == "snapshots" and owner in meta.get("authorized_owners", [])):
                    rows.append(meta)
            except (OSError, ValueError):
                continue
        return sorted(rows, key=lambda m: m.get("created_at", ""), reverse=True)

    def owned(self, kind, identity, owner):
        try:
            meta = self.read(self._path(kind, identity) / "meta.json")
        except (OSError, ValueError):
            raise AuditError("artifact_not_found") from None
        if meta.get("owner_id") != owner and not (kind == "snapshots" and owner in meta.get("authorized_owners", [])):
            raise AuditError("artifact_not_found")
        return meta

    def save_dataset(self, dataset, redactor, key, owner, preparations=None):
        did = "d_" + secrets.token_hex(16)
        path = private_directory(self._path("datasets", did))
        events = []
        for event in dataset.events:
            row = asdict(event)
            row["content"] = redactor.text(event.content)
            row["timestamp"] = event.timestamp.isoformat() if event.timestamp else None
            row["issues"] = list(event.issues)
            if row["content"] != event.content:
                row["issues"].append("redaction_changed_query" if event.selected else "source_text_redacted")
            events.append(row)
        payload = {"schema_version": "coverage-input-1", "input_id": dataset.input_id,
                   "events": events, "structure": dataset.structure, "mapping": asdict(dataset.mapping),
                   "timestamp_policy": asdict(dataset.timestamp_policy)}
        payload["redacted_input_id"] = canonical_sha256(payload)
        private_json(path / "dataset.json", payload)
        private_write(path / "privacy.key", key)
        if preparations is not None:
            private_json(path / "preparations.json", preparations)
        meta = {"dataset_id": did, "owner_id": owner, "created_at": now(),
                "input_id": dataset.input_id, "redacted_input_id": payload["redacted_input_id"],
                "structure": dataset.structure, "mapping": asdict(dataset.mapping),
                "timestamp_policy": asdict(dataset.timestamp_policy),
                "preparation_status": "ready" if preparations is not None else "pending",
                "preparation_counts": dict(Counter(r["preparation_status"] for r in preparations)) if preparations else {"pending_model": len(dataset.selected)}}
        private_json(path / "meta.json", meta)
        return meta

    def dataset(self, did, owner):
        self.owned("datasets", did, owner)
        path = self._path("datasets", did)
        payload = self.read(path / "dataset.json")
        identity = payload.pop("redacted_input_id")
        if canonical_sha256(payload) != identity:
            raise AuditError("input_artifact_drift")
        events = tuple(InputEvent(**{**r, "timestamp": datetime.fromisoformat(r["timestamp"]) if r["timestamp"] else None,
                                     "issues": tuple(r["issues"])}) for r in payload["events"])
        keypath = path / "privacy.key"
        if keypath.is_symlink() or keypath.stat().st_mode & 0o077:
            raise AuditError("artifact_file_permissions")
        dataset = ImportedDataset(payload["input_id"], events, payload["structure"],
                                  ColumnMapping(**payload["mapping"]), TimestampPolicy(**payload["timestamp_policy"]))
        return dataset, Redactor(keypath.read_bytes())

    def preparations(self, did, owner):
        self.owned("datasets", did, owner)
        return self.read(self._path("datasets", did) / "preparations.json")

    def set_preparations(self, did, owner, rows):
        meta = self.owned("datasets", did, owner)
        dataset, _ = self.dataset(did, owner)
        if [r["source_row_id"] for r in rows] != [e.source_row_id for e in dataset.selected]:
            raise AuditError("input_row_accounting_mismatch")
        path = self._path("datasets", did)
        self.write(path / "preparations.json", rows)
        meta.update(preparation_status="ready", preparation_counts=dict(Counter(r["preparation_status"] for r in rows)))
        self.write(path / "meta.json", meta)

    def register_snapshot(self, snapshot_path, manifest_path, owner):
        snapshot = load_snapshot(snapshot_path)
        manifest = self.read(manifest_path)
        if snapshot["snapshot_id"] != manifest["snapshot_id"] or hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != manifest["content_file_sha256"]:
            raise AuditError("snapshot_identity_mismatch")
        sid = snapshot["snapshot_id"]
        path = self._path("snapshots", sid)
        if path.exists():
            # This method is trusted operator/capture code, never a browser's
            # arbitrary-ID grant endpoint. Re-registering identical validated
            # bytes can explicitly assign snapshot access to the requested owner.
            existing = self.read(path / "meta.json")
            if hashlib.sha256((path / "kb-snapshot.json").read_bytes()).hexdigest() != manifest["content_file_sha256"]:
                raise AuditError("snapshot_identity_mismatch")
            owners = set(existing.get("authorized_owners", [existing["owner_id"]]))
            owners.add(owner)
            existing["authorized_owners"] = sorted(owners)
            self.write(path / "meta.json", existing)
            return existing
        private_directory(path)
        private_write(path / "kb-snapshot.json", snapshot_path.read_bytes())
        private_write(path / "kb-snapshot-manifest.json", manifest_path.read_bytes())
        meta = {"snapshot_id": sid, "owner_id": owner, "authorized_owners": [owner], "created_at": now(),
                "record_count": len(snapshot["records"]), "manifest": manifest,
                "documents": sorted({r["document_title"] for r in snapshot["records"]})}
        private_json(path / "meta.json", meta)
        return meta

    def snapshot(self, sid, owner):
        meta = self.owned("snapshots", sid, owner)
        path = self._path("snapshots", sid)
        snapshot = load_snapshot(path / "kb-snapshot.json")
        if hashlib.sha256((path / "kb-snapshot.json").read_bytes()).hexdigest() != meta["manifest"]["content_file_sha256"]:
            raise AuditError("snapshot_identity_mismatch")
        return snapshot

    def import_a1(self, source: Path, raw_csv: Path, owner=0):
        """Trusted operator CLI only; never exposed as a server-path endpoint."""
        private_directory(source)
        manifest = self.read(source / "preparation-manifest.json")
        if not re.fullmatch(r"a1_[0-9a-f]{32}", manifest.get("run_id", "")):
            raise AuditError("a1_export_identity_mismatch")
        if hashlib.sha256((source / "preparation.csv").read_bytes()).hexdigest() != manifest["csv_sha256"]:
            raise AuditError("a1_export_hash_mismatch")
        keypath = source / "privacy.key"
        if keypath.is_symlink() or keypath.stat().st_mode & 0o077:
            raise AuditError("artifact_file_permissions")
        key = keypath.read_bytes()
        redactor = Redactor(key)
        dataset = CsvInputAdapter(raw_csv, ColumnMapping(**manifest["mapping"]),
            policy=TimestampPolicy(**manifest["timestamp_policy"])).load(redactor)
        if dataset.input_id != manifest["input_id"] or [e.source_row_id for e in dataset.selected] != manifest["row_ids"]:
            raise AuditError("a1_input_identity_mismatch")
        import csv
        from knowledge_audit.privacy import formula_safe
        with (source / "preparation.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            for key in list(row):
                value = row[key]
                if value.startswith("'") and formula_safe(value[1:]) == value:
                    value = value[1:]
                if key in STRUCTURED_DEFAULTS:
                    value = json.loads(value)
                elif key in ("model_selected", "model_prepared"):
                    value = value == "true"
                elif key in ("source_record_ordinal", "processing_ordinal", "selected_input_row_count", "source_input_row_count"):
                    value = int(value)
                row[key] = value
            if set(row) != set(FIELDS):
                raise AuditError("a1_export_schema_mismatch")
        if [r["source_row_id"] for r in rows] != manifest["row_ids"] or any(r["export_id"] != manifest["export_id"] for r in rows):
            raise AuditError("a1_export_identity_mismatch")
        archive = private_directory(self.root / "archive" / manifest["run_id"])
        if not any(archive.iterdir()):
            hashes = {}
            for name in ("preparation.csv", "preparation-manifest.json", "kb-snapshot.json", "kb-snapshot-manifest.json", "privacy.key"):
                data = (source / name).read_bytes()
                private_write(archive / name, data)
                hashes[name] = hashlib.sha256(data).hexdigest()
                if hashlib.sha256((archive / name).read_bytes()).hexdigest() != hashes[name]:
                    raise AuditError("a1_archive_hash_mismatch")
            private_json(archive / "archive-manifest.json", {"a1_run_id": manifest["run_id"], "hashes": hashes})
        snapshot = self.register_snapshot(source / "kb-snapshot.json", source / "kb-snapshot-manifest.json", owner)
        meta = self.save_dataset(dataset, redactor, keypath.read_bytes(), owner, rows)
        return meta, snapshot

    def create_run(self, owner, did, sid, selected_ids, settings, versions):
        data, _ = self.dataset(did, owner)
        self.snapshot(sid, owner)
        rows = self.preparations(did, owner)
        if not selected_ids or len(selected_ids) > 5 or len(set(selected_ids)) != len(selected_ids) or not set(selected_ids) <= {e.source_row_id for e in data.selected}:
            raise AuditError("invalid_pilot_selection")
        rid = "r_" + secrets.token_hex(16)
        path = private_directory(self._path("runs", rid))
        private_directory(path / "rows")
        meta = {"run_id": rid, "owner_id": owner, "dataset_id": did, "snapshot_id": sid,
                "input_id": data.input_id, "selected_row_ids": selected_ids,
                "row_ids": [e.source_row_id for e in data.selected], "input_row_count": len(data.selected),
                "source_input_row_count": len(data.events),
                "state": "queued", "created_at": now(), "updated_at": now(),
                "settings": settings, "configuration_id": canonical_sha256(settings), "versions": versions,
                "completed_pilot_rows": 0, "attempt": 0, "error_code": ""}
        for row in rows:
            initial = {**row, "processing_status": "pending", "coverage_status": "not_evaluated",
                       "model_selected": row["source_row_id"] in selected_ids,
                       "outcome": "needs_context" if row["preparation_status"] == "needs_context" else "pending",
                       "recommendation_status": "unassessed", "recommendations": [], "attempt_count": 0,
                       "stopping_reason": "pending", "evaluated_entry_count": 0}
            if row["preparation_status"] in {"invalid_input", "failed"}:
                initial.update(processing_status="invalid_input" if row["preparation_status"] == "invalid_input" else "failed",
                               outcome="error", stopping_reason="invalid_input")
            private_json(path / "rows" / (row["source_row_id"] + ".json"), initial)
        private_json(path / "meta.json", meta)
        return meta

    def row(self, rid, row_id, owner):
        meta = self.owned("runs", rid, owner)
        if row_id not in meta["row_ids"]:
            raise AuditError("artifact_not_found")
        return self.read(self._path("runs", rid) / "rows" / (row_id + ".json"))

    def save_row(self, rid, row, owner):
        meta = self.owned("runs", rid, owner)
        if row["source_row_id"] not in meta["selected_row_ids"]:
            raise AuditError("invalid_result_identity")
        self.write(self._path("runs", rid) / "rows" / (row["source_row_id"] + ".json"), row)

    def rows(self, rid, owner):
        meta = self.owned("runs", rid, owner)
        return [self.row(rid, row_id, owner) for row_id in meta["row_ids"]]

    def lease(self, rid):
        path = self._path("runs", rid) / "worker.lock"
        return self._lease_path(path)

    def global_lease(self):
        return self._lease_path(self.root / "audit-worker.lock")

    def _lease_path(self, path):
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            raise AuditError("run_already_owned") from None
        return descriptor

    def update_run(self, rid, owner, updates, preserve_cancel=True):
        path = self._path("runs", rid)
        fd = os.open(path / "metadata.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            meta = self.owned("runs", rid, owner)
            cancelled = meta.get("cancel_requested", False)
            meta.update(updates)
            if preserve_cancel and cancelled:
                meta["cancel_requested"] = True
            self.write(path / "meta.json", meta)
            return meta
        finally:
            os.close(fd)
