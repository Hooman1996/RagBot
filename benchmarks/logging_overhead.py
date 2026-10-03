"""Run with: python benchmarks/logging_overhead.py (no external services)."""

import io
import json
import logging
import statistics
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.log_sanitizer import sanitize
from utils.structured_logging import LoggingSettings, log_event, start_logging


def main() -> None:
    payload = {
        "method": "POST", "path": "/api/mobile/v1/talk", "status_code": 200,
        "query": "موجودی حساب من چقدر است؟", "answer": "لطفا از برنامه بانک استفاده کنید.",
        "durations_ms": {"embedding": 12.5, "reranker": 8.3, "vllm": 730.4},
    }
    count = 5000
    baseline = []
    for _ in range(count):
        started = time.perf_counter_ns()
        json.dumps(payload, ensure_ascii=False)
        baseline.append((time.perf_counter_ns() - started) / 1_000)
    samples = []
    runtime = start_logging(LoggingSettings(queue_size=8192), stream=io.StringIO())
    logger = logging.getLogger("logging_benchmark")
    try:
        for _ in range(count):
            started = time.perf_counter_ns()
            safe = sanitize(payload)
            log_event(logger, "response_completed", safe)
            samples.append((time.perf_counter_ns() - started) / 1_000)
    finally:
        runtime.close()
    baseline.sort()
    samples.sort()
    print(f"samples={count} old_json_prepare_median_us={statistics.median(baseline):.1f} old_json_prepare_p95_us={baseline[int(count * 0.95)]:.1f}")
    print(f"samples={count} sanitized_enqueue_median_us={statistics.median(samples):.1f} sanitized_enqueue_p95_us={samples[int(count * 0.95)]:.1f}")


if __name__ == "__main__":
    main()
