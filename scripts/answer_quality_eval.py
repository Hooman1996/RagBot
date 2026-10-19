#!/usr/bin/env python3
"""Staging-only blind answer-quality evaluation of two app instances.

Subcommands: collect, blind, score. See
docs/performance/RELEASE_EVALUATION_RUNBOOK.md.

Questions and answers are written only to owner-only directories outside the
repository. The score report under docs/performance/ holds counts and rates
only. The terminal carries counts and fixed status lines only.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import importlib.util
import math
from pathlib import Path
import random
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from knowledge_audit.privacy import formula_safe  # noqa: E402
from scripts import _staging_guard as guard  # noqa: E402
from scripts.retrieval_eval import (  # noqa: E402
    cases_sha256, documents_arg, existing_private_dir, label_arg, load_cases, private_dir,
    read_csv, read_json, refuse, report_path, write_csv, write_json)

TALK_PATH = "/api/mobile/v1/talk"
LOAD_TEST = ROOT / "benchmarks" / "load" / "mobile_talk_load_test.py"
CORRECTNESS = ("correct", "partly", "incorrect")
SHEET_HEADER = ["item_id", "question", "answer_1", "answer_2", "correct_1", "correct_2",
                "grounded_1", "grounded_2", "preference"]
NO_ANSWER = "[no answer]"


# ---------- collect ----------

def load_identities(path: Path) -> list:
    """National codes from the operator-reserved staging fixture, via the load test's loader."""
    spec = importlib.util.spec_from_file_location("mobile_talk_load_test", LOAD_TEST)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        identities, _ = module.load_fixture(Path(path))
    except module.SetupError:
        refuse("collect", "identity_fixture_invalid")
    if not identities:
        refuse("collect", "identity_fixture_empty")
    return identities


async def httpx_post(url: str, body: dict, timeout: float):
    import httpx
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=body)
    answer = None
    if response.status_code == 200:
        try:
            answer = response.json().get("answer")
        except ValueError:
            answer = None
    return response.status_code, answer if isinstance(answer, str) else None


async def collect_answers(base_url, cases, documents, identities, *, timeout, post):
    url = base_url.rstrip("/") + TALK_PATH
    rows = []
    for index, case in enumerate(cases):
        body = {"session_id": str(uuid.uuid4()), "query": case["question"],
                "national_code": identities[index % len(identities)].national_code, "documents": documents}
        start = time.perf_counter()
        try:
            status, answer = await post(url, body, timeout)
        except Exception as exc:
            status, answer = type(exc).__name__, None
        rows.append({"question_id": case["question_id"], "answer": answer, "status": status,
                     "latency_ms": round((time.perf_counter() - start) * 1000, 3)})
    return rows


def collect(base_url, label, cases_dir, documents, identities, output, *, timeout=50.0, post=None) -> int:
    guard.load_env()
    guard.require_staging(guard.RETRIEVAL_KEYS)
    guard.require_loopback_url("--base-url", base_url)
    label = label_arg("collect", label)
    documents = documents_arg("collect", documents)
    cases_dir, cases = load_cases("collect", cases_dir)
    identities = load_identities(identities)
    output = private_dir("collect", output)
    if (output / label).exists():
        refuse("collect", "collection_exists")
    run_dir = private_dir("collect", output / label)
    rows = asyncio.run(collect_answers(base_url, cases["cases"], documents, identities,
                                       timeout=timeout, post=post or httpx_post))
    write_json(run_dir / "answers.json", rows)
    statuses = Counter(str(r["status"]) for r in rows)
    write_json(run_dir / "collect.json", {
        "label": label, "cases_file": str(cases_dir / "cases.json"), "cases_sha256": cases_sha256(cases_dir),
        "documents": documents, "timeout_seconds": timeout, "case_count": len(rows), "status_counts": dict(statuses)})
    answered = sum(1 for r in rows if r["status"] == 200 and r["answer"])
    print(f"collect: label={label} cases={len(rows)} answered={answered} failed={len(rows) - answered}")
    return 0


# ---------- blind ----------

def load_collection(command: str, path) -> tuple[dict, dict]:
    path = existing_private_dir(command, path)
    meta = read_json(path / "collect.json")
    return meta, {r["question_id"]: r for r in read_json(path / "answers.json")}


def blind(a_dir, b_dir, seed: int, output) -> int:
    (meta_a, answers_a), (meta_b, answers_b) = load_collection("blind", a_dir), load_collection("blind", b_dir)
    if meta_a["label"] == meta_b["label"]:
        refuse("blind", "same_label")
    if meta_a["cases_sha256"] != meta_b["cases_sha256"]:
        refuse("blind", "collection_cases_mismatch")
    cases_dir, cases = load_cases("blind", Path(meta_a["cases_file"]).parent)
    if cases_sha256(cases_dir) != meta_a["cases_sha256"]:
        refuse("blind", "collection_cases_mismatch")
    output = private_dir("blind", output)
    rng = random.Random(seed)
    rows, items = [], {}
    for case in cases["cases"]:
        qid = case["question_id"]
        if qid not in answers_a or qid not in answers_b:
            continue
        item_id = f"item-{len(items) + 1:04d}"
        order = ("b", "a") if rng.random() < 0.5 else ("a", "b")
        answers = {"a": answers_a[qid]["answer"] or NO_ANSWER, "b": answers_b[qid]["answer"] or NO_ANSWER}
        items[item_id] = {"question_id": qid, "answer_1": order[0], "answer_2": order[1]}
        rows.append([item_id, formula_safe(case["question"]), formula_safe(answers[order[0]]),
                     formula_safe(answers[order[1]]), "", "", "", "", ""])
    write_csv(output / "grading-sheet.csv", SHEET_HEADER, rows)
    write_json(output / "grading-key.json", {"seed": seed, "baseline": meta_a["label"],
                                             "candidate": meta_b["label"], "items": items})
    print(f"blind: {len(items)} items written")
    return 0


# ---------- score ----------

def sign_test(wins_a: int, wins_b: int) -> float:
    """Two-sided exact sign test p-value under p = 0.5; ties are excluded by the caller."""
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins_a, wins_b) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def tally(sheet_rows: list[dict], key: dict) -> dict:
    items = key["items"]
    if sorted(r["item_id"] for r in sheet_rows) != sorted(items):
        refuse("score", "sheet_key_mismatch")
    invalid = 0
    stats = {role: {"correct": Counter(), "grounded": 0} for role in ("a", "b")}
    preference = Counter()
    for row in sheet_rows:
        item = items[row["item_id"]]
        values = {k: (row.get(k) or "").strip().lower() for k in SHEET_HEADER[4:]}
        if (any(values[f"correct_{s}"] not in CORRECTNESS or values[f"grounded_{s}"] not in {"yes", "no"} for s in "12")
                or values["preference"] not in {"1", "2", "same"}):
            invalid += 1
            continue
        for slot in "12":
            role = item[f"answer_{slot}"]
            stats[role]["correct"][values[f"correct_{slot}"]] += 1
            stats[role]["grounded"] += values[f"grounded_{slot}"] == "yes"
        preference[item[f"answer_{values['preference']}"] if values["preference"] != "same" else "same"] += 1
    if invalid:
        print(f"score: {invalid} items have missing or invalid grades", file=sys.stderr)
        raise SystemExit(2)
    return {"graded": len(sheet_rows), "stats": stats, "preference": preference,
            "p_value": sign_test(preference["a"], preference["b"])}


def score_verdict(result: dict, *, alpha: float, max_extra_incorrect: int) -> dict:
    prefer_baseline = result["preference"]["a"] > result["preference"]["b"] and result["p_value"] < alpha
    extra = result["stats"]["b"]["correct"]["incorrect"] - result["stats"]["a"]["correct"]["incorrect"]
    return {"sign_test_favors_baseline": prefer_baseline, "extra_incorrect": extra,
            "too_many_incorrect": extra > max_extra_incorrect,
            "pass": not prefer_baseline and extra <= max_extra_incorrect}


def render_score(key: dict, result: dict, verdict: dict, *, alpha: float, max_extra_incorrect: int) -> str:
    n = result["graded"]
    share = lambda v: "n/a" if not n else f"{v / n:.4f}"
    labels = {"a": key["baseline"], "b": key["candidate"]}
    out = ["# Release answer-quality evaluation", "",
           "Generated by `scripts/answer_quality_eval.py score` (runbook: `docs/performance/RELEASE_EVALUATION_RUNBOOK.md`). "
           "Graded blind: the grader saw a per-item random order and no configuration names. Aggregates only.", "",
           f"- Graded items: {n}.", f"- Baseline: `{labels['a']}`; release candidate: `{labels['b']}`.", "",
           "| Configuration | correct | partly | incorrect | correct rate | partly rate | incorrect rate | grounded rate |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for role in ("a", "b"):
        c, g = result["stats"][role]["correct"], result["stats"][role]["grounded"]
        out.append(f"| `{labels[role]}` | {c['correct']} | {c['partly']} | {c['incorrect']} | {share(c['correct'])} | "
                   f"{share(c['partly'])} | {share(c['incorrect'])} | {share(g)} |")
    p = result["preference"]
    out += ["", "| Preference | count |", "|---|---:|",
            f"| `{labels['a']}` | {p['a']} |", f"| `{labels['b']}` | {p['b']} |", f"| same | {p['same']} |", "",
            f"Two-sided exact sign test on preferences, excluding `same`: n = {p['a'] + p['b']}, p = {result['p_value']:.4f}.", "",
            "## Verdict", "",
            f"The release candidate fails if the sign test favors the baseline at p < {alpha}, or if its `incorrect` "
            f"count exceeds the baseline's by more than {max_extra_incorrect}.", "",
            f"- Sign test favors the baseline: {'yes' if verdict['sign_test_favors_baseline'] else 'no'}.",
            f"- Extra `incorrect` answers: {verdict['extra_incorrect']:+d}.",
            f"- Verdict: **{'PASS' if verdict['pass'] else 'FAIL'}**.", ""]
    return "\n".join(out)


def score(sheet, key_file, report, *, alpha=0.05, max_extra_incorrect=2) -> int:
    report = report_path("score", report)
    existing_private_dir("score", Path(sheet).absolute().parent)
    existing_private_dir("score", Path(key_file).absolute().parent)
    key = read_json(key_file)
    result = tally(read_csv(sheet), key)
    verdict = score_verdict(result, alpha=alpha, max_extra_incorrect=max_extra_incorrect)
    report.write_text(render_score(key, result, verdict, alpha=alpha, max_extra_incorrect=max_extra_incorrect),
                      encoding="utf-8")
    print(f"score: {result['graded']} items, verdict {'PASS' if verdict['pass'] else 'FAIL'}")
    return 0 if verdict["pass"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect")
    p.add_argument("--base-url", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--cases", required=True, type=Path)
    p.add_argument("--documents", required=True)
    p.add_argument("--identities", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("blind")
    p.add_argument("--a", required=True, type=Path, help="baseline collection directory")
    p.add_argument("--b", required=True, type=Path, help="release-candidate collection directory")
    p.add_argument("--seed", required=True, type=int)
    p.add_argument("--output", required=True, type=Path)
    p = sub.add_parser("score")
    p.add_argument("--sheet", required=True, type=Path)
    p.add_argument("--key", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--max-extra-incorrect", type=int, default=2)
    args = parser.parse_args(argv)
    if args.command == "collect":
        return collect(args.base_url, args.label, args.cases, args.documents, args.identities, args.output)
    if args.command == "blind":
        return blind(args.a, args.b, args.seed, args.output)
    return score(args.sheet, args.key, args.report, alpha=args.alpha, max_extra_incorrect=args.max_extra_incorrect)


if __name__ == "__main__":
    raise SystemExit(main())
