"""Read-only staging metadata: allowlisted numeric metrics, no logs or labels."""
import asyncio
import math
import re
import time

METRICS = frozenset({"num_requests_running", "num_requests_waiting", "kv_cache_usage_perc",
    "gpu_cache_usage_perc", "request_queue_time_seconds_sum", "request_queue_time_seconds_count",
    "time_to_first_token_seconds_sum", "time_to_first_token_seconds_count", "request_success_total",
    "generation_tokens_total", "prompt_tokens_total", "request_prefill_time_seconds_sum",
    "request_prefill_time_seconds_count", "request_decode_time_seconds_sum", "request_decode_time_seconds_count"})


def numeric_metrics(body):
    result = {}
    for line in body.splitlines():
        match = re.fullmatch(r'vllm:([a-z_]+)(?:\{[^\n]*\})?\s+([0-9.eE+\-]+)', line)
        if match and match[1] in METRICS:
            value = float(match[2])
            if math.isfinite(value):
                result[match[1]] = result.get(match[1], 0) + value
    return result


async def sample(http, origin):
    item = {"monotonic_seconds": round(time.monotonic(), 3)}
    try:
        response = await http.get(origin + "/metrics", timeout=2)
        response.raise_for_status()
        item["vllm"] = numeric_metrics(response.text)
        item["metrics_status"] = "observed" if item["vllm"] else "no_allowlisted_metrics"
    except Exception:
        item["metrics_status"] = "unavailable"
    return item


async def gpu_sample():
    try:
        proc = await asyncio.create_subprocess_exec("nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), 3)
        except BaseException:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        rows = [[float(v.strip()) for v in line.split(",")] for line in stdout.decode().splitlines()]
        if proc.returncode != 0 or not rows or any(len(r) != 5 or not all(math.isfinite(v) for v in r) for r in rows):
            return {"status": "unavailable"}
        return {"status": "observed", "gpu_numeric_rows": rows}
    except (OSError, ValueError, TimeoutError):
        return {"status": "unavailable"}
