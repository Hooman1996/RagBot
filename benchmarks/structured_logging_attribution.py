"""Synthetic localhost Eval workload and content-free attribution helpers.

This module never starts services or changes application configuration. The
caller supplies a reviewed corpus of synthetic Eval payloads. Only outcomes,
timings, IDs, and hashes are retained; request/answer text is never persisted.
"""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


def content_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0}
    return {"count": len(values), "mean_ms": statistics.mean(values),
            "median_ms": statistics.median(values),
            "p95_ms": percentile(values, .95), "p99_ms": percentile(values, .99)}


def eval_category(http_status: int, data: dict) -> str:
    if http_status == 200 and data.get("status") == "COMPLETED":
        return "COMPLETED"
    if data.get("status") == "ERROR" and data.get("error_code") == "DEPENDENCY_UNAVAILABLE":
        return "DEPENDENCY_UNAVAILABLE"
    return "OTHER_FAILURE"


def _without_scores(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_scores(item) for key, item in value.items()
                if "score" not in key.lower()}
    if isinstance(value, list):
        return [_without_scores(item) for item in value]
    return value


def _scores(value: Any) -> list[float]:
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            if "score" in key.lower() and isinstance(item, (int, float)) and not isinstance(item, bool):
                if math.isfinite(item):
                    result.append(float(item))
            else:
                result.extend(_scores(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_scores(item))
    return result


def semantic_metadata(data: dict) -> dict:
    stages = {}
    for stage in data.get("stages", []):
        name = stage.get("stage_name")
        stages[name] = {key: stage.get(key) for key in
                        ("status", "input_hash", "output_hash", "error_code")}
        if name == "RERANK":
            output = stage.get("output_data")
            stages[name]["output_without_scores_hash"] = content_hash(_without_scores(output))
            stages[name]["scores"] = _scores(output)
    return {"answer_hash": content_hash(data.get("answer")),
            "intent_hash": content_hash(data.get("intent")), "stages": stages}


async def run_workload(base_url: str, corpus: list[dict], *, concurrency: int,
                       run_label: str, progress=None) -> dict:
    """Measure one fixed-concurrency run; no retries or secret-bearing headers."""
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Benchmark target must be an explicitly temporary localhost HTTP app")
    if not 1 <= concurrency <= len(corpus):
        raise ValueError("Invalid workload concurrency")
    gate = asyncio.Event()
    semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(connect=5, pool=10, write=10, read=70)
    async with httpx.AsyncClient(limits=limits, timeout=timeout, trust_env=False) as client:
        async def one(index: int, payload: dict) -> dict:
            digest = content_hash(payload)
            await gate.wait()
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post(
                        base_url + "/api/internal/evaluation/v1/turn", json=payload,
                        headers={"X-Request-Id": "synthetic-gateway-id"} if index == 0 else {},
                    )
                    elapsed = (time.perf_counter() - started) * 1000
                    try:
                        data = response.json()
                    except ValueError:
                        data = {}
                    if not isinstance(data, dict):
                        data = {}
                    timings = {}
                    for name, value in response.headers.items():
                        if name.lower().startswith("x-") and name.lower().endswith("-ms"):
                            try:
                                number = float(value)
                            except ValueError:
                                continue
                            if math.isfinite(number):
                                timings[name.lower()] = number
                    return {"run": run_label, "index": index, "payload_hash": digest,
                            "http_status": response.status_code,
                            "category": eval_category(response.status_code, data),
                            "latency_ms": elapsed,
                            "request_id": response.headers.get("X-Request-Id"),
                            "timing_headers": timings, "error_code": data.get("error_code"),
                            "client_error_type": None, "semantics": semantic_metadata(data)}
                except Exception as exc:
                    return {"run": run_label, "index": index, "payload_hash": digest,
                            "http_status": None, "category": "OTHER_FAILURE",
                            "latency_ms": (time.perf_counter() - started) * 1000,
                            "request_id": None, "timing_headers": {}, "error_code": None,
                            "client_error_type": type(exc).__name__, "semantics": {}}

        tasks = [asyncio.create_task(one(index, payload)) for index, payload in enumerate(corpus)]
        started = time.perf_counter()
        gate.set()
        rows = []
        for task in asyncio.as_completed(tasks):
            rows.append(await task)
            if progress is not None and len(rows) % 25 == 0:
                progress(len(rows))
        wall_seconds = time.perf_counter() - started
    rows.sort(key=lambda row: row["index"])
    result = {"label": run_label, "requests": len(corpus), "concurrency": concurrency,
              "corpus_hash": content_hash(corpus), "wall_seconds": wall_seconds,
              "rows": rows, "categories": dict(Counter(row["category"] for row in rows)),
              "http_statuses": dict(Counter(str(row["http_status"]) for row in rows))}
    for category in ("COMPLETED", "DEPENDENCY_UNAVAILABLE", "OTHER_FAILURE", "ALL"):
        selected = rows if category == "ALL" else [row for row in rows if row["category"] == category]
        result[category] = distribution([row["latency_ms"] for row in selected])
        result[category]["throughput_rps"] = len(selected) / wall_seconds
    return result


def common_success(baseline: dict, feature: dict) -> dict:
    """Compare matching successful inputs, rejecting mismatched corpora."""
    if baseline["corpus_hash"] != feature["corpus_hash"]:
        raise ValueError("Runs do not share the same ordered corpus")
    left = {row["index"]: row for row in baseline["rows"]}
    right = {row["index"]: row for row in feature["rows"]}
    indexes = sorted(index for index in left.keys() & right.keys()
                     if left[index]["category"] == right[index]["category"] == "COMPLETED")
    if any(left[index]["payload_hash"] != right[index]["payload_hash"] for index in indexes):
        raise ValueError("Matching indexes do not share the same payload")
    return {"count": len(indexes),
            "baseline": distribution([left[index]["latency_ms"] for index in indexes]),
            "feature": distribution([right[index]["latency_ms"] for index in indexes])}


async def _command() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text())
    if not isinstance(corpus, list) or not corpus or not all(isinstance(row, dict) for row in corpus):
        raise ValueError("Corpus must be a nonempty list of synthetic Eval payloads")
    if not 0 <= args.warmup <= len(corpus):
        raise ValueError("Invalid warmup count")
    if args.warmup:
        warmup = await run_workload(args.base_url, corpus[:args.warmup], concurrency=1,
                                    run_label=args.run_label + "_warmup")
        if warmup["categories"].get("COMPLETED", 0) != args.warmup:
            raise RuntimeError("Warmup was not fully successful; stop the experiment")
    await asyncio.sleep(2)
    result = await run_workload(args.base_url, corpus, concurrency=args.concurrency,
                                run_label=args.run_label)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    asyncio.run(_command())
