"""Run chains: continuation setup checks and one immutable export of the whole input.

A continuation is a subset run over a source run's unfinished rows. Runs linked
by continues_run_id form a chain; the chain export takes each row from the
latest run that finished it. No model or service calls.
"""
from contextlib import ExitStack
import copy
import hashlib
import os
import re

from knowledge_audit import sizing
from knowledge_audit.execution import TERMINAL
from knowledge_audit.privacy import AuditError, private_directory, private_json, private_write
from knowledge_audit.retention import artifact_access
from utils.read_only_audit import canonical_sha256

VERSION = "coverage-chain-export-1"
# The row count and the limits legitimately differ between the runs of a chain;
# the sample rule is the selection method, which sizing.comparable also ignores.
UNMERGED_RUNTIME = frozenset({"model_limit", "model_sample_rule"})


def same_setup(source, config, versions):
    """A continuation runs on the setup its source ran on."""
    if sizing.comparable(source) != sizing.comparable({"settings": config, "versions": versions}):
        raise AuditError("continuation_identity_drift")


def merge_identity(meta):
    """What every run of a chain shares; runs that never started have no serving identity."""
    versions = meta["versions"]
    runtime = versions.get("runtime_configuration")
    if runtime is not None:
        runtime = {k: copy.deepcopy(v) for k, v in runtime.items() if k not in UNMERGED_RUNTIME}
        if isinstance(runtime.get("audit_runtime_settings"), dict):
            runtime["audit_runtime_settings"].pop("operational_limits", None)
    return {**sizing.comparable(meta), "serving": versions.get("serving"), "runtime_configuration": runtime}


def chain(store, owner, run_id):
    """Every run of run_id's chain, root first, in creation order."""
    meta = store.owned("runs", run_id, owner)
    root = meta.get("chain_root_run_id") or meta["run_id"]
    seen = {meta["run_id"]}
    while meta.get("continues_run_id"):
        meta = store.owned("runs", meta["continues_run_id"], owner)
        if meta["run_id"] in seen:
            raise AuditError("ambiguous_run_chain")
        seen.add(meta["run_id"])
    if meta["run_id"] != root:
        raise AuditError("ambiguous_run_chain")
    runs = [m for m in store.list_owned("runs", owner) if m["run_id"] == root or m.get("chain_root_run_id") == root]
    runs.sort(key=lambda m: (m["run_id"] != root, m["created_at"], m["run_id"]))
    sources = [m["continues_run_id"] for m in runs[1:]]
    if len(set(sources)) != len(sources) or not set(sources) <= {m["run_id"] for m in runs}:
        raise AuditError("ambiguous_run_chain")
    identity = merge_identity(runs[0])
    for other in runs[1:]:
        if (merge_identity(other) != identity or other["dataset_id"] != runs[0]["dataset_id"]
                or other["snapshot_id"] != runs[0]["snapshot_id"] or other["row_ids"] != runs[0]["row_ids"]):
            raise AuditError("chain_identity_drift")
    return runs


def merged_rows(store, owner, runs, copies=None):
    """Each root row from the latest run that finished it, else its latest copy, plus provenance."""
    copies = copies or {m["run_id"]: store.rows(m["run_id"], owner) for m in runs}
    by_run = [(m, {r["source_row_id"]: r for r in copies[m["run_id"]]}) for m in runs]
    rows, provenance = [], {}
    for row_id in runs[0]["row_ids"]:
        # Prefer runs that selected the row; an unselected copy only repeats the input.
        ran = [(m, rows_) for m, rows_ in by_run if row_id in m["selected_row_ids"]] or by_run
        chosen = next(((m, rows_) for m, rows_ in reversed(ran)
                       if rows_[row_id]["processing_status"] in TERMINAL - {"failed"}), ran[-1])
        rows.append(chosen[1][row_id])
        provenance[row_id] = chosen[0]["run_id"]
    return rows, provenance


def _frozen(store, owner, meta):
    frozen = dict(meta)
    if meta.get("operational_policy"):
        from knowledge_audit.operations import Budget, Limits
        frozen["operational_budget"] = Budget(store, store._path("runs", meta["run_id"]), owner,
                                              Limits.from_settings(meta["settings"])).summary()
    return frozen


def capture(store, owner, runs):
    """Each run's rows, its meta with its budget summary, and its results hash."""
    copies = {m["run_id"]: store.rows(m["run_id"], owner) for m in runs}
    frozen = {m["run_id"]: _frozen(store, owner, m) for m in runs}
    return copies, frozen, {rid: canonical_sha256(rows) for rid, rows in copies.items()}


def revision_name(runs, frozen, results, evidence_visible):
    """Named by its inputs, so an unchanged chain maps to the same revision."""
    return "rev_" + canonical_sha256({"version": VERSION, "evidence_visible": evidence_visible,
                                      "runs": [[frozen[m["run_id"]], results[m["run_id"]]] for m in runs]})[:32]


def build(store, owner, runs, captured, redactor, evidence_visible, revision_id, captured_at):
    """The chain CSV and manifest; equal inputs give equal bytes."""
    from knowledge_audit.export import coverage_export
    copies, frozen, results = captured
    rows, provenance = merged_rows(store, owner, runs, copies)
    root, latest = runs[0], frozen[runs[-1]["run_id"]]
    selected = {row_id for m in runs for row_id in m["selected_row_ids"]}
    processing = list(dict.fromkeys(row_id for m in runs for row_id in m["processing_row_ids"]))
    meta = {**latest, "run_id": root["run_id"], "execution_mode": root["execution_mode"], "row_ids": root["row_ids"],
            "selected_row_ids": [row_id for row_id in root["row_ids"] if row_id in selected],
            "processing_row_ids": processing, "operational_budget": {},
            "export_revision_id": revision_id, "export_captured_at": captured_at}
    body, manifest = coverage_export(meta, rows, redactor, evidence_visible=evidence_visible,
                                     sources={row_id: frozen[rid] for row_id, rid in provenance.items()})
    manifest.pop("operational_budget", None)
    manifest.update(chain_export_version=VERSION, chain_root_run_id=root["run_id"],
                    chain_run_ids=[m["run_id"] for m in runs],
                    chain_results_sha256={m["run_id"]: results[m["run_id"]] for m in runs},
                    chain_runs=[{"run_id": m["run_id"], "continues_run_id": m.get("continues_run_id", ""),
                                 "state": m["state"], "execution_mode": m["execution_mode"],
                                 "selected_row_count": len(m["selected_row_ids"]),
                                 "run_identity_id": m.get("run_identity_id", ""), "configuration_id": m["configuration_id"],
                                 "operational_budget": frozen[m["run_id"]].get("operational_budget", {}),
                                 "pause_reason": m.get("pause_reason", "")} for m in runs],
                    merge_identity_sha256=canonical_sha256(merge_identity(root)),
                    source_run_row_counts={m["run_id"]: sum(v == m["run_id"] for v in provenance.values()) for m in runs})
    return body, manifest


def export_revision(store, owner, run_id, evidence_visible, revision_id=None, *, create=False):
    """Frozen, permission-specific chain CSV/manifest pair, stored with the root run.

    A revision is named by its inputs: exporting an unchanged chain again
    returns the same revision. Retention reads the run IDs in the manifest, so a
    retained export keeps every run of its chain.
    """
    from knowledge_audit.store import now
    with artifact_access(store.root):
        runs = chain(store, owner, run_id)
        root = runs[0]["run_id"]
        projection = private_directory(private_directory(store._path("runs", root) / "chain-exports")
                                       / ("evidence" if evidence_visible else "restricted"))
        pointer = projection / "latest.json"
        if revision_id is not None and not re.fullmatch(r"rev_[0-9a-f]{32}", revision_id):
            raise AuditError("invalid_artifact_id")
        if create:
            locked = sorted(m["run_id"] for m in runs)
            with ExitStack() as stack:
                for rid in locked:
                    stack.enter_context(store.run_lock(rid))
                runs = chain(store, owner, run_id)
                if sorted(m["run_id"] for m in runs) != locked:
                    raise AuditError("run_chain_changed")  # a run joined the chain; export again
                captured = capture(store, owner, runs)
                revision_id = revision_name(runs, *captured[1:], evidence_visible)
                revision = projection / revision_id
                if not (revision / "manifest.json").exists():
                    _, redactor = store.dataset(runs[0]["dataset_id"], owner)
                    body, manifest = build(store, owner, runs, captured, redactor, evidence_visible, revision_id, now())
                    private_directory(revision)
                    private_write(revision / "coverage.csv", body)
                    private_json(revision / "manifest.json", manifest)
                store.write(pointer, {"export_revision_id": revision_id})
        elif revision_id is None:
            if not pointer.exists():
                raise AuditError("artifact_not_found")
            revision_id = store.read(pointer)["export_revision_id"]
        revision = projection / revision_id
        try:
            manifest = store.read(revision / "manifest.json")
            path = revision / "coverage.csv"
            if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
                raise AuditError("artifact_file_permissions")
            body = path.read_bytes()
        except OSError:
            raise AuditError("artifact_not_found") from None
        if (hashlib.sha256(body).hexdigest() != manifest["csv_sha256"] or manifest["evidence_visible"] != evidence_visible
                or manifest.get("chain_export_version") != VERSION or manifest["export_revision_id"] != revision_id):
            raise AuditError("export_identity_mismatch")
        return body, manifest
