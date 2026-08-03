#!/usr/bin/env python3
"""Synthetic bounded-scheduler benchmark; it sends no network traffic."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mass_answer_service import MassAnswerProcessor


class SyntheticAnsweringService:
    def __init__(self, delay_seconds: float):
        self.delay_seconds = delay_seconds

    async def answer(self, request):
        await asyncio.sleep(self.delay_seconds)
        return SimpleNamespace(
            answer="پاسخ مصنوعی",
            intent="general",
            rewritten_query=request.original_query,
            related_questions=[],
        )


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


async def run_case(rows: int, concurrency: int, delay: float) -> dict:
    processor = MassAnswerProcessor(
        answering_service=SyntheticAnsweringService(delay),
        row_concurrency=concurrency,
        row_timeout_seconds=max(1.0, delay * 10),
    )
    started = time.perf_counter()
    results = await processor.process(
        [f"synthetic-{index}" for index in range(rows)],
        selected_documents=["General_FAQ"],
        batch_id=f"synthetic-{rows}-{concurrency}",
    )
    duration = time.perf_counter() - started
    latencies = [row.processing_time_ms for row in results]
    return {
        "implementation": "bounded",
        "rows": rows,
        "concurrency": concurrency,
        "duration_seconds": duration,
        "rows_per_second": rows / duration,
        "p50_row_ms": percentile(latencies, 0.50),
        "p95_row_ms": percentile(latencies, 0.95),
        "p99_row_ms": percentile(latencies, 0.99),
        "max_row_ms": max(latencies),
        "errors": sum(row.status != "success" for row in results),
        "timeouts": sum(row.status == "timeout" for row in results),
    }


async def run_legacy_case(rows: int, delay: float) -> dict:
    service = SyntheticAnsweringService(delay)
    latencies = []
    started = time.perf_counter()
    for index in range(rows):
        row_started = time.perf_counter()
        await service.answer(SimpleNamespace(original_query=f"synthetic-{index}"))
        latencies.append((time.perf_counter() - row_started) * 1000)
    duration = time.perf_counter() - started
    return {
        "implementation": "legacy_sequential_baseline",
        "rows": rows,
        "concurrency": 1,
        "duration_seconds": duration,
        "rows_per_second": rows / duration,
        "p50_row_ms": percentile(latencies, 0.50),
        "p95_row_ms": percentile(latencies, 0.95),
        "p99_row_ms": percentile(latencies, 0.99),
        "max_row_ms": max(latencies),
        "errors": 0,
        "timeouts": 0,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", default="1,10,50,100,500")
    parser.add_argument("--concurrency", default="1,2,4,8")
    parser.add_argument("--synthetic-delay-ms", type=float, default=10.0)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    row_counts = [int(value) for value in args.rows.split(",")]
    concurrencies = [int(value) for value in args.concurrency.split(",")]
    if any(value < 1 for value in row_counts + concurrencies):
        parser.error("rows and concurrency values must be positive")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or Path("benchmarks/results/mass-answer/synthetic") / timestamp
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    for rows in row_counts:
        baseline = await run_legacy_case(
            rows, args.synthetic_delay_ms / 1000
        )
        cases.append(baseline)
        print(json.dumps(baseline, ensure_ascii=False))
        for concurrency in concurrencies:
            result = await run_case(
                rows, concurrency, args.synthetic_delay_ms / 1000
            )
            cases.append(result)
            print(json.dumps(result, ensure_ascii=False))
    (output / "summary.json").write_text(
        json.dumps(
            {
                "kind": "synthetic_scheduler_only",
                "timestamp_utc": timestamp,
                "delay_ms": args.synthetic_delay_ms,
                "cases": cases,
                "missing_live_metrics": [
                    "vLLM queue", "TEI latency", "Qdrant latency",
                    "PostgreSQL latency", "GPU utilization", "mobile impact",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    report = [
        "# Synthetic mass-answer scheduler benchmark",
        "",
        "This run compares the audited legacy sequential scheduler with bounded workers using one deterministic fake answer service. It is not evidence of vLLM, TEI, Qdrant, PostgreSQL, GPU, or end-to-end capacity.",
        "",
        f"Cases: {len(cases)}. Synthetic delay: {args.synthetic_delay_ms:g} ms.",
    ]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"artifacts={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
