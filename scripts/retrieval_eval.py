#!/usr/bin/env python3
"""Staging-only retrieval evaluation of ranking configurations.

Subcommands: freeze, run, label-sheet, compare. See
docs/performance/RELEASE_EVALUATION_RUNBOOK.md.

Questions, chunk IDs, titles and per-question results are written only to
owner-only directories outside the repository. The compare report under
docs/performance/ holds counts, rates, intervals and latencies only. The
terminal carries counts and fixed status lines only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge_audit.privacy import AuditError, formula_safe, private_directory, private_write  # noqa: E402
from scripts import _staging_guard as guard  # noqa: E402

CHILD = ROOT / "scripts" / "_retrieval_child.py"
REPORT_ROOT = ROOT / "docs" / "performance"
BASELINE_COMMIT = "681cc95"
QUERY_RULE = "general_canonical"
RAG_CALL = re.compile(r"rag_system\s*=\s*await\s+blocking_runner\.run\(")
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RATE_METRICS = ("hit_context", "recall_context", "mrr_context")
RESAMPLES = 10_000
SEED = 1234


def refuse(command: str, code: str, status: int = 2) -> None:
    print(f"{command}: refused ({code})", file=sys.stderr)
    raise SystemExit(status)


def private_dir(command: str, path: Path) -> Path:
    try:
        return private_directory(Path(path))
    except AuditError as exc:
        refuse(command, str(exc))


def existing_private_dir(command: str, path: Path) -> Path:
    if not Path(path).is_dir():
        refuse(command, "input_directory_missing")
    return private_dir(command, path)


def write_json(path: Path, payload) -> None:
    private_write(path, (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8"))


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_csv(path: Path, header, rows) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    private_write(path, buffer.getvalue().encode("utf-8-sig"))


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def report_path(command: str, path) -> Path:
    path = Path(path).absolute()
    root = REPORT_ROOT.resolve()
    parent = path.parent.resolve()
    if path.suffix != ".md" or (parent != root and root not in parent.parents):
        refuse(command, "report_outside_docs_performance")
    return path


def cases_sha256(cases_dir: Path) -> str:
    return hashlib.sha256((Path(cases_dir) / "cases.json").read_bytes()).hexdigest()


def load_cases(command: str, cases_dir) -> tuple[Path, dict]:
    cases_dir = existing_private_dir(command, cases_dir)
    if not (cases_dir / "cases.json").is_file():
        refuse(command, "cases_missing")
    return cases_dir, read_json(cases_dir / "cases.json")


# ---------- freeze ----------

def production_query_preparer():
    """The general-intent retrieval query of a first turn, as answering_service builds it."""
    from utils.persian_hybrid_search import PersianTextProcessor
    from utils.persian_normalization import normalize_persian_text
    from utils.retrieval_query_canonicalizer import canonicalize_retrieval_query
    processor = PersianTextProcessor(use_stemming=False)
    return lambda question: canonicalize_retrieval_query(
        normalize_persian_text(str(processor.normalize(question)).strip()))


def checkout_head() -> str:
    return git(ROOT, "rev-parse", "HEAD")


def freeze(questions: Path, output: Path, *, prepare=None) -> int:
    existing_private_dir("freeze", Path(questions).absolute().parent)
    rows = read_csv(questions)
    if not rows or not {"question_id", "question"} <= set(rows[0]):
        refuse("freeze", "questions_columns")
    ids = [r["question_id"].strip() for r in rows]
    if any(not i for i in ids) or len(set(ids)) != len(ids) or any(not r["question"].strip() for r in rows):
        refuse("freeze", "questions_invalid")
    output = private_dir("freeze", output)
    if (output / "cases.json").exists():
        refuse("freeze", "cases_exist")
    guard.load_env()
    from utils.performance_config import PERFORMANCE_SETTINGS
    from utils.retrieval_query_canonicalizer import RETRIEVAL_QUERY_ALIASES_SHA256
    prepare = prepare or production_query_preparer()
    cases = [{"question_id": i, "question": r["question"], "retrieval_query": prepare(r["question"]),
              "query_rule": QUERY_RULE} for i, r in zip(ids, rows)]
    write_json(output / "cases.json", {
        "query_rule": QUERY_RULE, "alias_sha256": RETRIEVAL_QUERY_ALIASES_SHA256,
        "canonicalization_enabled": PERFORMANCE_SETTINGS.rag_query_canonicalization_enabled,
        "frozen_at_commit": checkout_head(), "cases": cases})
    print(f"freeze: {len(cases)} cases written")
    return 0


# ---------- run ----------

def git(worktree: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(worktree), *args], capture_output=True,
                          check=True, text=True).stdout.strip()


def call_span(text: str) -> range | None:
    """1-based line numbers of main.py's `rag_system = await blocking_runner.run(` call."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if RAG_CALL.search(line):
            depth = 0
            for end in range(start, len(lines)):
                depth += lines[end].count("(") - lines[end].count(")")
                if depth <= 0:
                    return range(start + 1, end + 2)
            return None
    return None


def ragsystem_call_touched(diff: str, old: str, new: str) -> bool:
    old_span, new_span = call_span(old), call_span(new)
    if old_span is None or new_span is None:
        return True
    for line in diff.splitlines():
        match = HUNK.match(line)
        if match:
            a, b, c, d = (int(g) if g is not None else 1 for g in match.groups())
            if any(n in old_span for n in range(a, a + b)) or any(n in new_span for n in range(c, c + d)):
                return True
        elif line[:1] in "+-" and not line.startswith(("+++", "---")) and "RAGSystem" in line:
            return True
    return False


def check_worktree(worktree: Path) -> str:
    """Exit 2 unless the worktree is clean and main.py builds RAGSystem as at the baseline."""
    try:
        if git(worktree, "status", "--porcelain", "--untracked-files=no"):
            refuse("run", "worktree_not_clean")
        diff = git(worktree, "diff", "-U0", BASELINE_COMMIT, "HEAD", "--", "main.py")
        old = git(worktree, "show", f"{BASELINE_COMMIT}:main.py")
        new = git(worktree, "show", "HEAD:main.py")
        head = git(worktree, "rev-parse", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        refuse("run", "worktree_git_failed")
    if ragsystem_call_touched(diff, old, new):
        refuse("run", "main_py_ragsystem_call_changed")
    return head


def documents_arg(command: str, value: str) -> list[str]:
    documents = [d.strip() for d in value.split(",") if d.strip()]
    if not documents:
        refuse(command, "documents_missing")
    return documents


def label_arg(command: str, value: str) -> str:
    if not LABEL.match(value):
        refuse(command, "invalid_label")
    return value


def run(worktree: Path, cases_dir: Path, label: str, documents: str, output: Path, *, child=CHILD) -> int:
    guard.load_env()
    guard.require_staging(guard.RETRIEVAL_KEYS)
    label = label_arg("run", label)
    documents = documents_arg("run", documents)
    cases_dir, cases = load_cases("run", cases_dir)
    worktree = Path(worktree).resolve()
    head = check_worktree(worktree)
    output = private_dir("run", output)
    if (output / label).exists():
        refuse("run", "run_exists")
    run_dir = private_dir("run", output / label)
    write_json(run_dir / "request.json", {"cases_file": str(cases_dir / "cases.json"), "documents": documents})
    env = dict(os.environ, PYTHONPATH=str(worktree))
    # Child output may hold service text, so it is discarded; results are files.
    process = subprocess.run([sys.executable, "-P", str(child), "--run-dir", str(run_dir)], cwd=worktree, env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status_file = run_dir / "child.json"
    child_status = read_json(status_file) if status_file.is_file() else {"fatal": "no_child_status"}
    fatal = child_status.get("fatal") or (None if process.returncode == 0 else f"child_exit_{process.returncode}")
    write_json(run_dir / "run.json", {
        "label": label, "git_head": head, "documents": documents,
        "settings": child_status.get("settings"), "case_count": child_status.get("case_count", 0),
        "error_count": child_status.get("error_count", 0), "fatal": fatal,
        "cases_sha256": cases_sha256(cases_dir), "query_rule": cases.get("query_rule")})
    print(f"run: label={label} cases={child_status.get('case_count', 0)} "
          f"errors={child_status.get('error_count', 0)} status={'failed' if fatal else 'complete'}")
    return 1 if fatal else 0


# ---------- label-sheet ----------

def load_run(command: str, run_dir) -> dict:
    run_dir = existing_private_dir(command, run_dir)
    meta = read_json(run_dir / "run.json")
    if meta.get("fatal"):
        refuse(command, "run_failed")
    meta["per_question"] = {r["question_id"]: r for r in read_json(run_dir / "per_question.json")}
    meta["titles"] = read_json(run_dir / "titles.json")
    return meta


def label_sheet(cases_dir, run_dirs, output) -> int:
    _, cases = load_cases("label-sheet", cases_dir)
    runs = [load_run("label-sheet", d) for d in run_dirs]
    output = private_dir("label-sheet", output)
    titles = {}
    for r in runs:
        titles.update({k: v for k, v in r["titles"].items() if k not in titles})
    rows, questions = [], 0
    for case in cases["cases"]:
        chunk_ids = []
        for r in runs:
            result = r["per_question"].get(case["question_id"]) or {}
            for cid in (*(result.get("retrieved_ids") or ()), *(result.get("context_ids") or ())):
                if cid not in chunk_ids:
                    chunk_ids.append(cid)
        if not chunk_ids:
            continue
        if rows:
            rows.append(["", "", "", "", ""])
        questions += 1
        rows.extend([case["question_id"], formula_safe(case["question"]), cid,
                     formula_safe(titles.get(cid, "")), ""] for cid in chunk_ids)
    write_csv(output / "label-sheet.csv", ["question_id", "question", "chunk_id", "faq_title", "relevant"], rows)
    print(f"label-sheet: {questions} questions, {sum(1 for r in rows if r[0])} rows")
    return 0


# ---------- compare ----------

def question_metrics(relevant: set, retrieved: list, context: list) -> dict:
    first = next((rank for rank, cid in enumerate(context, start=1) if cid in relevant), None)
    return {"hit_context": 1.0 if first else 0.0,
            "recall_context": len(relevant & set(context)) / len(relevant),
            "mrr_context": 1.0 / first if first else 0.0,
            "recall_retrieved": len(relevant & set(retrieved)) / len(relevant),
            "empty": 0.0 if context else 1.0}


def quantile(values, q: float):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def paired_bootstrap(diffs: dict[str, list[float]], *, resamples=RESAMPLES, seed=SEED) -> dict:
    """Mean paired difference and 95% percentile interval; one index draw per resample for all metrics."""
    n = len(next(iter(diffs.values())))
    if n == 0:
        return {m: {"mean": None, "low": None, "high": None} for m in diffs}
    rng = random.Random(seed)
    population = range(n)
    means = {m: [] for m in diffs}
    for _ in range(resamples):
        index = rng.choices(population, k=n)
        for metric, values in diffs.items():
            means[metric].append(sum(map(values.__getitem__, index)) / n)
    return {m: {"mean": statistics.fmean(diffs[m]), "low": quantile(means[m], 0.025),
                "high": quantile(means[m], 0.975)} for m in diffs}


def read_labels(command: str, sheet) -> dict[str, set]:
    labels: dict[str, set] = {}
    for row in read_csv(sheet):
        qid, cid, value = (row.get(k, "") or "" for k in ("question_id", "chunk_id", "relevant"))
        if not qid.strip():
            continue
        value = value.strip()
        if value not in {"", "1"}:
            refuse(command, "invalid_relevant_label")
        labels.setdefault(qid.strip(), set())
        if value == "1":
            labels[qid.strip()].add(cid.strip())
    return labels


def evaluate_runs(cases: dict, labels: dict, runs: list[dict]) -> dict:
    question_ids = [c["question_id"] for c in cases["cases"]]
    labeled = [q for q in question_ids if labels.get(q)]
    per_run = {}
    for r in runs:
        rows = {}
        for qid in labeled:
            result = r["per_question"].get(qid) or {"error": "missing"}
            # A failed case counts as an empty context, never as skipped.
            rows[qid] = question_metrics(labels[qid], result.get("retrieved_ids") or [],
                                         result.get("context_ids") or [])
        latencies = [r["per_question"][q]["latency_ms"] for q in question_ids
                     if not (r["per_question"].get(q) or {"error": "missing"}).get("error")]
        errors = sum(1 for q in question_ids if (r["per_question"].get(q) or {"error": "missing"}).get("error"))
        per_run[r["label"]] = {
            "rows": rows, "errors": errors,
            "means": {m: statistics.fmean(v[m] for v in rows.values()) if rows else None
                      for m in (*RATE_METRICS, "recall_retrieved", "empty")},
            "p50": quantile(latencies, 0.5), "p95": quantile(latencies, 0.95)}
    return {"question_count": len(question_ids), "labeled": labeled,
            "no_relevant": len(question_ids) - len(labeled), "runs": per_run}


def comparison_pairs(labels: list[str], baseline: str) -> list[tuple[str, str]]:
    pairs = [(label, baseline) for label in labels if label != baseline]
    for previous, label in zip(labels, labels[1:]):
        if (label, previous) not in pairs:
            pairs.append((label, previous))
    return pairs


def compare_runs(evaluation: dict, labels: list[str], baseline: str, thresholds: dict) -> dict:
    runs = evaluation["runs"]
    comparisons = []
    for label, reference in comparison_pairs(labels, baseline):
        diffs = {m: [runs[label]["rows"][q][m] - runs[reference]["rows"][q][m] for q in evaluation["labeled"]]
                 for m in RATE_METRICS}
        delta = lambda k: None if runs[label][k] is None or runs[reference][k] is None else runs[label][k] - runs[reference][k]
        comparisons.append({"label": label, "reference": reference, "metrics": paired_bootstrap(diffs),
                            "p50_delta": delta("p50"), "p95_delta": delta("p95")})
    verdicts = {}
    for c in comparisons:
        if c["reference"] != baseline:
            continue
        p95, base_p95 = runs[c["label"]]["p95"], runs[baseline]["p95"]
        checks = {
            "hit_context_lower": c["metrics"]["hit_context"]["low"] is not None
                and c["metrics"]["hit_context"]["low"] >= thresholds["min_hit_diff"],
            "recall_context_lower": c["metrics"]["recall_context"]["low"] is not None
                and c["metrics"]["recall_context"]["low"] >= thresholds["min_recall_diff"],
            "p95_absolute": p95 is not None and p95 <= thresholds["max_p95_ms"],
            "p95_ratio": p95 is not None and base_p95 is not None and p95 <= thresholds["max_p95_ratio"] * base_p95,
        }
        verdicts[c["label"]] = {"checks": checks, "pass": all(checks.values())}
    return {"comparisons": comparisons, "verdicts": verdicts}


def fmt(value) -> str:
    return "n/a" if value is None else f"{value:+.4f}"


def rate(value) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def ms(value) -> str:
    return "n/a" if value is None else f"{value:,.1f}"


def render_report(cases: dict, runs: list[dict], evaluation: dict, result: dict, baseline: str, thresholds: dict) -> str:
    labels = [r["label"] for r in runs]
    ev = evaluation["runs"]
    out = ["# Release retrieval evaluation", "",
           "Generated by `scripts/retrieval_eval.py compare` (runbook: `docs/performance/RELEASE_EVALUATION_RUNBOOK.md`). "
           "Aggregates only: counts, rates, intervals and latencies.", "",
           "## Inputs", "",
           f"- Frozen cases: {evaluation['question_count']}; query rule `{cases.get('query_rule')}`, "
           f"canonicalization enabled: {cases.get('canonicalization_enabled')}, alias SHA-256 `{cases.get('alias_sha256')}`.",
           f"- Questions with at least one relevant chunk (used for rates): {len(evaluation['labeled'])}.",
           f"- Questions with no relevant chunk (counted, excluded from rates): {evaluation['no_relevant']}.",
           "- Relevance is pooled: a person labeled the union of the retrieved and context chunks of every run once.",
           "- A case that raised counts as an empty context in the rates and is left out of the latencies.",
           f"- Paired 95% percentile bootstrap: {RESAMPLES:,} resamples, `random.Random({SEED})`.",
           f"- Baseline: `{baseline}`.", "",
           "## Configurations", "",
           "| Label | Commit | Cases | Errors | Datasources |", "|---|---|---:|---:|---:|"]
    for r in runs:
        out.append(f"| `{r['label']}` | `{r['git_head'][:12]}` | {r['case_count']} | {ev[r['label']]['errors']} | {len(r['documents'])} |")
    keys = sorted({k for r in runs for k in (r.get("settings") or {})})
    if keys:
        out += ["", "| Setting | " + " | ".join(f"`{l}`" for l in labels) + " |", "|---|" + "---|" * len(labels)]
        for key in keys:
            out.append(f"| `{key}` | " + " | ".join(f"`{(r.get('settings') or {}).get(key)}`" for r in runs) + " |")
    out += ["", "## Rates and latency", "",
            "| Label | hit_context | recall_context | mrr_context | recall_retrieved | empty | p50 ms | p95 ms |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for label in labels:
        m = ev[label]["means"]
        out.append(f"| `{label}` | {rate(m['hit_context'])} | {rate(m['recall_context'])} | {rate(m['mrr_context'])} | "
                   f"{rate(m['recall_retrieved'])} | {rate(m['empty'])} | {ms(ev[label]['p50'])} | {ms(ev[label]['p95'])} |")
    out += ["", "## Paired differences", "",
            "| Comparison | metric | mean difference | 95% interval |", "|---|---|---:|---|"]
    for c in result["comparisons"]:
        for metric in RATE_METRICS:
            s = c["metrics"][metric]
            out.append(f"| `{c['label']}` − `{c['reference']}` | {metric} | {fmt(s['mean'])} | [{fmt(s['low'])}, {fmt(s['high'])}] |")
    out += ["", "| Comparison | p50 delta ms | p95 delta ms |", "|---|---:|---:|"]
    for c in result["comparisons"]:
        delta = lambda v: "n/a" if v is None else f"{v:+,.1f}"
        out.append(f"| `{c['label']}` − `{c['reference']}` | {delta(c['p50_delta'])} | {delta(c['p95_delta'])} |")
    out += ["", "## Verdict against the baseline", "",
            f"Thresholds: lower bound of the hit_context difference ≥ {thresholds['min_hit_diff']}; lower bound of the "
            f"recall_context difference ≥ {thresholds['min_recall_diff']}; p95 ≤ {thresholds['max_p95_ms']:,.0f} ms; "
            f"p95 ≤ {thresholds['max_p95_ratio']} × the baseline's p95.", "",
            "| Label | hit lower bound | recall lower bound | p95 absolute | p95 ratio | verdict |", "|---|---|---|---|---|---|"]
    for label, v in result["verdicts"].items():
        check = lambda k: "pass" if v["checks"][k] else "FAIL"
        out.append(f"| `{label}` | {check('hit_context_lower')} | {check('recall_context_lower')} | "
                   f"{check('p95_absolute')} | {check('p95_ratio')} | **{'PASS' if v['pass'] else 'FAIL'}** |")
    overall = bool(result["verdicts"]) and all(v["pass"] for v in result["verdicts"].values())
    out += ["", f"Overall: **{'PASS' if overall else 'FAIL'}**.", ""]
    return "\n".join(out)


def compare(cases_dir, sheet, run_dirs, baseline, report, thresholds) -> int:
    report = report_path("compare", report)
    cases_dir, cases = load_cases("compare", cases_dir)
    runs = [load_run("compare", d) for d in run_dirs]
    labels = [r["label"] for r in runs]
    if len(set(labels)) != len(labels) or baseline not in labels:
        refuse("compare", "invalid_run_labels")
    digest = cases_sha256(cases_dir)
    if any(r.get("cases_sha256") != digest for r in runs):
        refuse("compare", "run_cases_mismatch")
    evaluation = evaluate_runs(cases, read_labels("compare", sheet), runs)
    result = compare_runs(evaluation, labels, baseline, thresholds)
    report.write_text(render_report(cases, runs, evaluation, result, baseline, thresholds), encoding="utf-8")
    passed = bool(result["verdicts"]) and all(v["pass"] for v in result["verdicts"].values())
    print(f"compare: {len(evaluation['labeled'])} labeled questions, {evaluation['no_relevant']} without a relevant chunk, "
          f"{len(runs)} runs, verdict {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--questions", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("run")
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--label", required=True)
    p.add_argument("--documents", required=True)
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("label-sheet")
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--runs", required=True, nargs="+", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("compare")
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--sheet", required=True, type=Path)
    p.add_argument("--runs", required=True, nargs="+", type=Path)
    p.add_argument("--baseline", required=True)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--min-hit-diff", type=float, default=-0.02)
    p.add_argument("--min-recall-diff", type=float, default=-0.02)
    p.add_argument("--max-p95-ms", type=float, default=45_000.0)
    p.add_argument("--max-p95-ratio", type=float, default=1.2)
    args = parser.parse_args(argv)
    if args.command == "freeze":
        return freeze(args.questions, args.output)
    if args.command == "run":
        return run(args.repo, args.cases, args.label, args.documents, args.output)
    if args.command == "label-sheet":
        return label_sheet(args.cases, args.runs, args.output)
    return compare(args.cases, args.sheet, args.runs, args.baseline, args.report, {
        "min_hit_diff": args.min_hit_diff, "min_recall_diff": args.min_recall_diff,
        "max_p95_ms": args.max_p95_ms, "max_p95_ratio": args.max_p95_ratio})


if __name__ == "__main__":
    raise SystemExit(main())
