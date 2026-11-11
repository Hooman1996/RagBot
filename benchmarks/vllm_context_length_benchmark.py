"""Direct vLLM benchmark for one variable (--max-model-len). Staging only.

build: write a fixed payload file: the NegahBoom answer prompt plus 10 random
       NegahBoom_FAQ chunks per request (FAQ text, no customer data). Only
       payloads that also fit a 4000-token limit are kept, so the same file is
       valid before and after the change. Keep the file out of git.
run:   replay the same payloads at concurrency 1, 16 and 50 (after a discarded
       warm-up) and write latency, TTFT and throughput as JSON.

See docs/performance/22-vllm-context-limit-repair.md.
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]

URL = "http://localhost:8000/v1/chat/completions"


def build(out):
    sys.path.insert(0, str(ROOT))
    from types import SimpleNamespace
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from new_architecture.app.config import NegahBoomPrompts as P
    from new_architecture.app.services.history.database import DatabaseManager
    from utils.RagSystem import RAGSystem

    rows = DatabaseManager().get_chunks_by_document_titles(["NegahBoom_FAQ"])
    rng = random.Random(20261111)
    payloads = []
    for _ in range(100):
        picked = rng.sample(rows, 10)
        ctx = RAGSystem.generate_context(None, [SimpleNamespace(content=r["text"]) for r in picked])
        question = rng.choice(picked)["text"].split("\n")[0][:200]
        messages = [{"role": "system", "content": P.GENERAL_RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": P.GENERAL_RAG_USER_PROMPT.format(
                        formatted_search_results=ctx, question=question)}]
        n = httpx.post("http://localhost:8000/tokenize", json={
            "model": "/app/model", "messages": messages, "add_generation_prompt": True}).json()["count"]
        if n + 500 <= 4000:  # must be valid under the baseline limit too
            payloads.append({"messages": messages, "prompt_tokens": n})
    json.dump(payloads, open(out, "w"), ensure_ascii=False)
    print(f"kept {len(payloads)} payloads; prompt tokens min/median/max",
          min(p["prompt_tokens"] for p in payloads),
          statistics.median(p["prompt_tokens"] for p in payloads),
          max(p["prompt_tokens"] for p in payloads))


async def one(client, payload):
    body = {"model": "/app/model", "messages": payload["messages"], "max_tokens": 500,
            "temperature": 0.0, "top_p": 1.0, "seed": 42, "stream": True,
            "stream_options": {"include_usage": True}}
    start = time.perf_counter()
    ttft = None
    out_tokens = None
    status = None
    async with client.stream("POST", URL, json=body) as r:
        status = r.status_code
        async for line in r.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            if ttft is None and chunk.get("choices") and chunk["choices"][0]["delta"].get("content"):
                ttft = time.perf_counter() - start
            if chunk.get("usage"):
                out_tokens = chunk["usage"]["completion_tokens"]
    return {"status": status, "latency": time.perf_counter() - start, "ttft": ttft, "out_tokens": out_tokens}


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


async def level(client, payloads, concurrency, total):
    sem = asyncio.Semaphore(concurrency)
    async def guarded(p):
        async with sem:
            return await one(client, p)
    start = time.perf_counter()
    results = await asyncio.gather(*(guarded(payloads[i % len(payloads)]) for i in range(total)))
    wall = time.perf_counter() - start
    ok = [r for r in results if r["status"] == 200]
    lat = [r["latency"] for r in ok]
    ttft = [r["ttft"] for r in ok if r["ttft"] is not None]
    toks = sum(r["out_tokens"] or 0 for r in ok)
    return {"concurrency": concurrency, "requests": total, "ok": len(ok),
            "errors": total - len(ok), "wall_s": round(wall, 2),
            "latency_p50_s": round(pct(lat, .5), 2), "latency_p95_s": round(pct(lat, .95), 2),
            "ttft_p50_s": round(pct(ttft, .5), 3), "ttft_p95_s": round(pct(ttft, .95), 3),
            "output_tokens": toks, "output_tok_per_s": round(toks / wall, 1)}


async def run(payload_file, out, label):
    payloads = json.load(open(payload_file))
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), limits=limits) as client:
        await level(client, payloads, 8, 16)  # warm-up (prefix cache, CUDA graphs), discarded
        results = {"label": label, "levels": []}
        for concurrency, total in ((1, 10), (16, 48), (50, 100)):
            r = await level(client, payloads, concurrency, total)
            print(json.dumps(r))
            results["levels"].append(r)
    json.dump(results, open(out, "w"), indent=2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "run"])
    ap.add_argument("--payloads", required=True)
    ap.add_argument("--out")
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.payloads)
    else:
        asyncio.run(run(a.payloads, a.out, a.label))
