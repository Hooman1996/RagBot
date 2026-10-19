"""Protected human-review packages; no labels, recommendations or new answers."""
import hashlib
import html
import json
import secrets

from knowledge_audit.evidence import EvidenceIndex
from knowledge_audit.privacy import AuditError, private_directory, private_json, private_write
from knowledge_audit.store import now

REVIEW_FIELDS = ("reviewer", "reviewed_at", "aspects_agree_or_correct", "applicability_agree_or_correct",
    "conditions_or_conflicts", "coverage_agree_or_correct", "missing_facts", "production_context_sufficiency",
    "reviewer_notes")


def review_package(store, run_ids, owner):
    if not run_ids or len(run_ids) > 3 or len(set(run_ids)) != len(run_ids):
        raise AuditError("invalid_review_runs")
    metas = [store.owned("runs", rid, owner) for rid in run_ids]
    reference = metas[0]
    if len(reference["selected_row_ids"]) != 5 or any(m["selected_row_ids"] != reference["selected_row_ids"] or
            m["input_id"] != reference["input_id"] for m in metas):
        raise AuditError("review_input_mismatch")
    directory = private_directory(private_directory(store.root / "reviews") / ("review_" + secrets.token_hex(16)))
    indexes = {m["snapshot_id"]: EvidenceIndex(store.snapshot(m["snapshot_id"], owner)) for m in metas}
    _, redactor = store.dataset(reference["dataset_id"], owner)
    manifest = {"version":"human-review-package-1", "created_at":now(), "run_ids":run_ids,
        "input_id":reference["input_id"], "snapshot_ids":list(indexes), "row_ids":reference["selected_row_ids"],
        "human_labels_provided":False, "files":{}}
    pieces = ["<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width'>",
        "<meta http-equiv=Content-Security-Policy content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<title>Private pilot evidence review</title><style>body{font:16px sans-serif;max-width:1100px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;text-align:start}section{border-top:1px solid #aaa;margin-top:2rem}h1,h2,h3{line-height:1.5}</style>",
        "<h1>Private pilot evidence review</h1><p>Untrusted redacted source text. No independent human labels have been provided. Review conditions and evidence; automated verdicts are not ground truth. Edit each row JSON's blank reviewer fields, or record notes separately. No network submission or factual-answer drafting.</p>"]
    for row_id in reference["selected_row_ids"]:
        observations = []
        for meta in metas:
            # Capture one consistent checkpoint. New runs must not modify an old
            # run's result; every observation keeps its original run identities.
            with store.run_lock(meta["run_id"]):
                row = store.row(meta["run_id"], row_id, owner)
            index = indexes[meta["snapshot_id"]]
            cited = {s["chunk_id"] for s in row.get("supporting_sentence_refs", [])}
            for aspect in row.get("supported_aspects", []):
                cited.update(s["entry_id"] for s in aspect.get("supports", []))
            for reference_citation in row.get("supporting_sentence_refs", []):
                index.resolve(reference_citation)
            keys = ("source_record_ordinal", "source_row_id", "input_query_redacted", "standalone_query_redacted",
                "requested_aspects", "supported_aspects", "unresolved_aspects", "scope_status", "history_status",
                "history_provenance", "outcome", "coverage_status", "processing_status", "production_context_sufficiency",
                "production_reachability", "production_assessment", "verifications", "verification_reason",
                "review_codes", "stopping_reason", "error_code", "failure_diagnostics", "evaluation_scope")
            value = {k:row.get(k) for k in keys}
            value.update(run_id=meta["run_id"], snapshot_id=meta["snapshot_id"], run_identity_id=meta.get("run_identity_id"),
                cited_evidence=[index.entry(cid) for cid in sorted(cited)],
                production_selected_evidence=[index.entry(cid) for cid in row.get("production_context_ids", [])],
                review_priority="special_attention" if row.get("source_record_ordinal") in {518,121} else "standard")
            observations.append(value)
        from knowledge_audit.export import _redact
        package = _redact({"version":"human-review-row-1", "source_row_id":row_id,
            "observations":observations, "reviewer_fields":{k:"" for k in REVIEW_FIELDS},
            "independent_human_review_status":"not_reviewed"},redactor)
        name = row_id + ".json"
        private_json(directory / name, package)
        manifest["files"][name] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        pieces.append("<section><h2>Source row " + str(observations[0]["source_record_ordinal"]) + "</h2><p>" + row_id +
            "</p><h3>Blank reviewer fields</h3><pre>" + html.escape(json.dumps(package["reviewer_fields"],ensure_ascii=False,indent=2)) + "</pre>")
        for value in package["observations"]:
            pieces.append("<h3>Run " + html.escape(value["run_id"]) + "</h3><pre dir=auto>" +
                html.escape(json.dumps(value,ensure_ascii=False,indent=2)) + "</pre>")
        pieces.append("</section>")
    private_write(directory / "index.html", "\n".join(pieces).encode("utf-8"))
    manifest["files"]["index.html"] = hashlib.sha256((directory / "index.html").read_bytes()).hexdigest()
    private_json(directory / "manifest.json", manifest)
    return {"directory":str(directory), "row_count":5, "run_ids":run_ids,
        "manifest_sha256":hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()}
