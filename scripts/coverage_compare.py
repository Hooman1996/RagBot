#!/usr/bin/env python3
"""Compare two coverage checks, and optionally a labelled CSV, from their private run folders.

    conda run --no-capture-output -n faq python scripts/coverage_compare.py \
        --before RUN_A --after RUN_B [--expected PATH.csv]

Prints JSON lines with counts, codes, timings and row numbers only; never questions, notes,
titles or chunk text. Contacts no service. Exit code 2 on a row-count mismatch, an unknown
expected value or an unreadable run or CSV.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coverage_check.settings import SettingsError, load_settings  # noqa: E402
from coverage_check.store import CheckStore, StoreError, parse_csv  # noqa: E402

EXPECTED = {"answered": {"answered", "answered_combined"}, "partial": {"partial"},
            "not_answered": {"not_answered"}, "chitchat": {"chitchat"}}


class CompareError(Exception):
    """A fixed code for exit 2."""

    def __init__(self, code: str, **facts):
        super().__init__(code)
        self.code = code
        self.facts = facts


def p95(values: list[int]) -> int | None:
    """Nearest-rank 95th percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def mean(values) -> float | None:
    values = list(values)
    return round(sum(values) / len(values), 2) if values else None


def load_run(store: CheckStore, run_id: str) -> dict:
    """Row number -> stored result (None while waiting), plus the run's meta."""
    try:
        meta = store.meta(run_id)
        codes = store.result_codes(run_id)
        results = {row: store.result(run_id, row) for row in range(1, meta["row_count"] + 1)
                   if row in codes}
    except StoreError as exc:
        raise CompareError(exc.code, run_id=run_id) from None
    return {"meta": meta, "results": results}


def outcome(run: dict, row: int) -> str:
    found = run["results"].get(row)
    return found["result"] if found else "waiting"


def run_summary(side: str, run: dict) -> dict:
    meta, found = run["meta"], list(run["results"].values())
    rows = range(1, meta["row_count"] + 1)
    calls = [r["model_calls"] for r in found if isinstance(r.get("model_calls"), int)]
    durations = [r["duration_ms"] for r in found if isinstance(r.get("duration_ms"), int)]
    return {
        "kind": "run", "side": side, "run_id": meta["run_id"],
        "prompt_version": meta.get("prompt_version"), "state": meta["state"], "row_count": meta["row_count"],
        "results": dict(sorted(Counter(outcome(run, row) for row in rows).items())),
        "error_codes": dict(sorted(Counter(r.get("error_code") for r in found
                                           if r.get("result") == "error").items(), key=lambda kv: str(kv[0]))),
        "model_calls_total": sum(calls), "model_calls_mean": mean(calls),
        "duration_ms_mean": mean(durations), "duration_ms_p95": p95(durations),
    }


def read_expected(path: Path, row_count: int, max_rows: int) -> dict[int, str]:
    try:
        raw = path.read_bytes()
    except OSError:
        raise CompareError("expected_unreadable") from None
    try:
        rows = parse_csv(raw, max_rows, extra="expected")
    except StoreError as exc:
        raise CompareError(exc.code) from None
    if len(rows) != row_count:
        raise CompareError("expected_row_count_mismatch", expected_rows=len(rows), row_count=row_count)
    labels = {}
    for item in rows:
        value = item["expected"].strip().lower()
        if value not in EXPECTED:
            raise CompareError("unknown_expected_value", row=item["row"])
        labels[item["row"]] = value
    return labels


def compare(store: CheckStore, before_id: str, after_id: str, expected: Path | None, max_rows: int) -> list[dict]:
    before, after = load_run(store, before_id), load_run(store, after_id)
    row_count = before["meta"]["row_count"]
    if row_count != after["meta"]["row_count"]:
        raise CompareError("row_count_mismatch", before=row_count, after=after["meta"]["row_count"])
    labels = read_expected(expected, row_count, max_rows) if expected is not None else None

    lines = [run_summary("before", before), run_summary("after", after)]
    pairs: dict[tuple[str, str], list[int]] = {}
    for row in range(1, row_count + 1):
        pairs.setdefault((outcome(before, row), outcome(after, row)), []).append(row)
    lines.append({"kind": "change_table", "pairs": [
        {"before": b, "after": a, "count": len(rows)} for (b, a), rows in sorted(pairs.items())]})
    lines.append({"kind": "changed_rows", "pairs": [
        {"before": b, "after": a, "rows": rows} for (b, a), rows in sorted(pairs.items()) if b != a]})
    if labels is not None:
        for side, run in (("before", before), ("after", after)):
            wrong = [row for row, label in labels.items() if outcome(run, row) not in EXPECTED[label]]
            agree = row_count - len(wrong)
            lines.append({"kind": "agreement", "side": side, "run_id": run["meta"]["run_id"],
                          "agree": agree, "total": row_count, "rate": round(agree / row_count, 4),
                          "wrong_rows": wrong})
    return lines


def main(argv=None, artifact_dir: Path | None = None, out=None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", required=True, help="run id of the earlier check")
    parser.add_argument("--after", required=True, help="run id of the later check")
    parser.add_argument("--expected", type=Path, help="the test CSV with an expected column")
    args = parser.parse_args(argv)
    max_rows = 100000
    if artifact_dir is None:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        try:
            settings = load_settings()
        except SettingsError as exc:
            print(json.dumps({"error": "invalid_setting", "variable": str(exc)}), file=out)
            return 2
        artifact_dir, max_rows = settings.artifact_dir, settings.max_rows
    try:
        lines = compare(CheckStore(artifact_dir), args.before, args.after, args.expected, max_rows)
    except CompareError as exc:
        print(json.dumps({"error": exc.code, **exc.facts}), file=out)
        return 2
    for line in lines:
        print(json.dumps(line, ensure_ascii=False), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
