#!/usr/bin/env python3
"""Read-only run-to-run stability report for the same rows on one snapshot.

It compares completed coverage runs that differ only in batch size, and writes
identifiers, labels and counts only: never query text, aspect descriptions,
sentence text or explanations. It never calls a model or a service.
"""
from __future__ import annotations
import argparse
from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VERSION = "coverage-stability-1"
BATCH_KEYS = frozenset({"batch_entries", "batch_max_entries"})
MIN_JACCARD = 0.9
PASS_RULE = ("A row passes when every run produced the same aspect checklist, every run has the same outcome, "
             "and the minimum pairwise Jaccard similarity of the support triples is at least 0.9.")


def jaccard(a, b):
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def load_runs(store, owner, run_ids):
    from knowledge_audit.privacy import AuditError
    runs = []
    for run_id in run_ids:
        try:
            meta = store.owned("runs", run_id, owner)
        except AuditError as error:
            if str(error) not in {"artifact_not_found", "invalid_artifact_id"}:
                raise
            raise AuditError("run_not_completed") from None
        if meta.get("state") != "completed":
            raise AuditError("run_not_completed")
        runs.append(meta)
    if len({(m["snapshot_id"], m["dataset_id"]) for m in runs}) != 1:
        raise AuditError("snapshot_mismatch")
    # Batch size must be the only variable between the compared runs.
    pinned = [{k: v for k, v in m["settings"].items() if k not in BATCH_KEYS} for m in runs]
    if any(m["versions"] != runs[0]["versions"] for m in runs) or any(p != pinned[0] for p in pinned):
        raise AuditError("code_version_mismatch")
    return runs


def load_row(store, owner, meta, row_id):
    from knowledge_audit.privacy import AuditError
    if row_id not in meta.get("selected_row_ids", []):
        raise AuditError("row_missing")
    try:
        row = store.row(meta["run_id"], row_id, owner)
    except AuditError as error:
        if str(error) not in {"artifact_not_found", "invalid_artifact_id"}:
            raise
        raise AuditError("row_missing") from None
    except OSError:
        raise AuditError("row_missing") from None
    if row.get("outcome", "pending") == "pending" or row.get("processing_status") in {"pending", "running"}:
        raise AuditError("row_missing")
    return row


def observation(meta, row):
    """Identifiers, labels and counts of one row in one run; no text fields."""
    triples = sorted({(s["entry_id"], s["aspect_id"], s["applicability"])
                      for batch in row.get("batch_results", []) for s in batch.get("supports", [])})
    completed = [m for m in row.get("model_metrics", []) if m.get("completion_tokens") is not None]
    return {"run_id": meta["run_id"], "batch_max_entries": meta["settings"].get("batch_max_entries"),
            "outcome": row["outcome"], "coverage_status": row.get("coverage_status", "not_evaluated"),
            "requested_aspect_count": len(row.get("requested_aspects", [])),
            "supported_aspect_ids": sorted(a["aspect_id"] for a in row.get("supported_aspects", [])),
            "support_triples": [list(t) for t in triples],
            "supporting_sentence_refs": sorted(f'{r["chunk_id"]}:{r["sentence_number"]}'
                                               for r in row.get("supporting_sentence_refs", [])),
            "verifications": [{"origin": v.get("origin", ""), "verdict": v.get("verdict", "")}
                              for v in row.get("verifications", [])],
            "completions": len(completed),
            "prompt_tokens": sum(m.get("prompt_tokens") or 0 for m in completed),
            "completion_tokens": sum(m["completion_tokens"] for m in completed)}


def build_report(store, owner, run_ids, row_ids):
    runs = load_runs(store, owner, run_ids)
    rows = []
    for row_id in row_ids:
        loaded = [(meta, load_row(store, owner, meta, row_id)) for meta in runs]
        # Compared in memory only; descriptions never reach the output.
        checklists = [[(a.get("aspect_id"), a.get("description")) for a in row.get("requested_aspects", [])]
                      for _, row in loaded]
        observed = [observation(meta, row) for meta, row in loaded]
        sets = [{tuple(t) for t in o["support_triples"]} for o in observed]
        scores = [jaccard(a, b) for a, b in combinations(sets, 2)]
        summary = {"aspect_checklist_agreement": all(c == checklists[0] for c in checklists),
                   "verdict_agreement": len({o["outcome"] for o in observed}) == 1,
                   "support_jaccard_min": round(min(scores), 6), "support_jaccard_mean": round(sum(scores) / len(scores), 6)}
        summary["support_agreement_pass"] = summary["support_jaccard_min"] >= MIN_JACCARD
        summary["passed"] = summary["aspect_checklist_agreement"] and summary["verdict_agreement"] and summary["support_agreement_pass"]
        rows.append({"row_id": row_id, "runs": observed, **summary})
    return {"version": VERSION, "snapshot_id": runs[0]["snapshot_id"], "dataset_id": runs[0]["dataset_id"],
            "run_ids": [m["run_id"] for m in runs], "pass_rule": PASS_RULE, "minimum_jaccard": MIN_JACCARD,
            "rows": rows, "rows_passed": sum(r["passed"] for r in rows), "all_passed": all(r["passed"] for r in rows)}


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(report):
    lines = ["# Coverage stability report", "",
             f'Snapshot `{report["snapshot_id"]}`, dataset `{report["dataset_id"]}`, {len(report["run_ids"])} runs.', "",
             "| Row | Run | Batch max | Outcome | Coverage | Aspects supported / requested | Support triples | "
             "Sentence refs | Verifications | Completions | Prompt tokens | Completion tokens |",
             "|---|---|---:|---|---|---|---:|---|---|---:|---:|---:|"]
    for row in report["rows"]:
        for o in row["runs"]:
            verdicts = ", ".join(f'{v["origin"]}={v["verdict"]}' for v in o["verifications"]) or "none"
            lines.append("| " + " | ".join(cell(v) for v in (
                row["row_id"], o["run_id"], o["batch_max_entries"], o["outcome"], o["coverage_status"],
                f'{len(o["supported_aspect_ids"])} / {o["requested_aspect_count"]}', len(o["support_triples"]),
                ", ".join(o["supporting_sentence_refs"]) or "none", verdicts, o["completions"],
                o["prompt_tokens"], o["completion_tokens"])) + " |")
    lines += ["", "## Agreement", "",
              "| Row | Aspect checklist | Outcome | Jaccard min | Jaccard mean | Support | Row |",
              "|---|---|---|---:|---:|---|---|"]
    word = {True: "pass", False: "fail"}
    for row in report["rows"]:
        lines.append("| " + " | ".join(cell(v) for v in (
            row["row_id"], word[row["aspect_checklist_agreement"]], word[row["verdict_agreement"]],
            f'{row["support_jaccard_min"]:.3f}', f'{row["support_jaccard_mean"]:.3f}',
            word[row["support_agreement_pass"]], word[row["passed"]])) + " |")
    lines += ["", f'{report["rows_passed"]} of {len(report["rows"])} rows pass.', "", "## Pass rule", "", PASS_RULE, ""]
    return "\n".join(lines)


def write_report(report, output):
    from knowledge_audit.privacy import private_directory, private_json, private_write
    directory = private_directory(output)
    private_json(directory / "stability-report.json", report)
    private_write(directory / "stability-report.md", markdown(report).encode("utf-8"))
    return directory


def main(argv=None, *, store=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", type=int, default=0, help="Operator namespace 0, as in knowledge_coverage_pilot.py.")
    parser.add_argument("--run-id", action="append", required=True, dest="run_ids", help="Completed run; repeat, at least 2.")
    parser.add_argument("--row-id", action="append", required=True, dest="row_ids", help="Source row ID; repeat, at least 1.")
    parser.add_argument("--output", type=Path, required=True, help="New owner-only directory outside the repository.")
    args = parser.parse_args(argv)
    if args.owner_id < 0:
        parser.error("owner-id must be nonnegative")
    run_ids, row_ids = list(dict.fromkeys(args.run_ids)), list(dict.fromkeys(args.row_ids))
    if len(run_ids) < 2:
        parser.error("at least two distinct --run-id values are required")
    from knowledge_audit.privacy import AuditError
    try:
        if store is None:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env", override=False)
            from knowledge_audit.settings import load_coverage_settings, require_coverage_enabled
            require_coverage_enabled()
            from knowledge_audit.store import CoverageStore
            store = CoverageStore(load_coverage_settings().artifact_dir)
        report = build_report(store, args.owner_id, run_ids, row_ids)
        directory = write_report(report, args.output)
    except AuditError as error:
        print(str(error), file=sys.stderr)
        return 2
    except FileExistsError:
        print("stability_report_exists", file=sys.stderr)
        return 2
    except Exception:
        print("stability_report_failed", file=sys.stderr)
        return 2
    print(json.dumps({"version": VERSION, "rows": len(report["rows"]), "rows_passed": report["rows_passed"],
                      "all_passed": report["all_passed"], "output": str(directory)}, sort_keys=True))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
