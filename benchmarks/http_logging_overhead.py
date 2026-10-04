"""Offline ASGI benchmark: python benchmarks/http_logging_overhead.py."""

from __future__ import annotations

import asyncio
import io
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.http_logging_middleware import HttpLoggingMiddleware
from utils.structured_logging import LoggingSettings, start_logging

PAYLOAD = json.dumps({
    "session_id": "benchmark-session", "query": "How do I check my account balance?",
    "national_code": "1234567891",
}).encode()
RESPONSE = json.dumps({
    "query_id": "benchmark-query", "answer": "Please use the mobile banking app.",
    "related_questions": [],
}).encode()


async def endpoint(scope, receive, send):
    while True:
        message = await receive()
        if not message.get("more_body", False):
            break
    await asyncio.sleep(0)  # Let concurrent request contexts interleave.
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": RESPONSE, "more_body": False})


async def one_request(app):
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "path": "/api/mobile/v1/talk", "query_string": b"",
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(PAYLOAD)).encode())],
    }
    received = False
    response_id = None

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": PAYLOAD, "more_body": False}

    async def send(message):
        nonlocal response_id
        if message["type"] == "http.response.start":
            response_id = dict(message.get("headers", [])).get(b"x-request-id")

    await app(scope, receive, send)
    return response_id


def stats(samples):
    samples.sort()
    return statistics.median(samples), samples[int(len(samples) * 0.95)]


async def measure(app, count=1000):
    samples = []
    for _ in range(100):
        await one_request(app)
    for _ in range(count):
        started = time.perf_counter_ns()
        await one_request(app)
        samples.append((time.perf_counter_ns() - started) / 1_000)
    return stats(samples)


async def main():
    bare_median, bare_p95 = await measure(endpoint)
    stream = io.StringIO()
    settings = LoggingSettings(environment="benchmark", pii_hmac_secret="benchmark-only-key")
    runtime = start_logging(settings, stream)
    app = HttpLoggingMiddleware(endpoint, settings)
    try:
        logged_median, logged_p95 = await measure(app)
        ids = await asyncio.gather(*(one_request(app) for _ in range(50)))
        overflow = runtime.handler.overflow_count
    finally:
        runtime.close()
    assert len(ids) == len(set(ids)) == 50
    print(f"requests=1000 disabled_median_us={bare_median:.1f} disabled_p95_us={bare_p95:.1f}")
    print(f"requests=1000 enabled_median_us={logged_median:.1f} enabled_p95_us={logged_p95:.1f}")
    print(f"median_overhead_us={logged_median - bare_median:.1f} p95_overhead_us={logged_p95 - bare_p95:.1f}")
    print(f"concurrent_requests=50 unique_request_ids=50 queue_overflow_count={overflow}")


if __name__ == "__main__":
    asyncio.run(main())
