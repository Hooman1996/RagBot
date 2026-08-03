"""Synthetic 20-request benchmark for the AgentService blocking boundary.

This does not contact FastAPI, PostgreSQL, TEI, vLLM, Qdrant, or MinIO.
``legacy`` executes the metadata read on the loop to reproduce the verified P2
boundary. ``repaired`` supplies real worker threads at ``asyncio.to_thread``.
"""

import argparse
import asyncio
import concurrent.futures
import functools
import importlib
import json
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


fake_graph_module = types.ModuleType("agent_graph")


class FakeGraph:
    async def ainvoke(self, state):
        await asyncio.sleep(0.02)
        state["messages"] = [{"role": "assistant", "content": "ok"}]
        return state


fake_graph_module.AgentState = dict
fake_graph_module.build_graph = lambda **kwargs: FakeGraph()
sys.modules["agent_graph"] = fake_graph_module

database_module = types.ModuleType(
    "new_architecture.app.services.history.database"
)
database_module.DatabaseManager = object
database_module.ChatManager = object
sys.modules[
    "new_architecture.app.services.history.database"
] = database_module

agent_service_module = importlib.import_module("agent_service")


class BlockingDatabase:
    def get_session_by_id(self, session_id):
        return {"user_id": session_id}

    def get_session_metadata(self, session_id):
        time.sleep(0.02)
        return {}

    def update_session_metadata(self, session_id, metadata):
        return None


async def benchmark(mode: str):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=24)
    original_to_thread = asyncio.to_thread

    async def legacy_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    async def repaired_to_thread(func, /, *args, **kwargs):
        future = executor.submit(functools.partial(func, *args, **kwargs))
        while not future.done():
            await asyncio.sleep(0.001)
        return future.result()

    asyncio.to_thread = (
        legacy_to_thread if mode == "legacy" else repaired_to_thread
    )
    try:
        service = agent_service_module.AgentService(
            rag_system=object(),
            intent_classifier=object(),
            scenarios_db={},
            db_manager=BlockingDatabase(),
            chat_manager=object(),
        )
        latencies = []

        async def request(index):
            started = time.perf_counter()
            result = await service.process_message(
                str(index), "synthetic", selected_docs=[]
            )
            latencies.append(time.perf_counter() - started)
            return result

        batch_started = time.perf_counter()
        tasks = [
            asyncio.create_task(request(index)) for index in range(20)
        ]
        heartbeat_lag = []
        previous = time.perf_counter()
        while any(not task.done() for task in tasks):
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            heartbeat_lag.append(max(0.0, now - previous - 0.005))
            previous = now
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - batch_started
        ordered = sorted(latencies)

        def percentile(fraction):
            index = min(
                len(ordered) - 1, int(len(ordered) * fraction)
            )
            return ordered[index]

        await service.blocking_runner.aclose()
        return {
            "mode": mode,
            "requests": len(tasks),
            "elapsed_seconds": round(elapsed, 4),
            "event_loop_lag_max_seconds": round(max(heartbeat_lag), 4),
            "p50_seconds": round(percentile(0.50), 4),
            "p95_seconds": round(percentile(0.95), 4),
            "p99_seconds": round(percentile(0.99), 4),
            "throughput_rps": round(len(tasks) / elapsed, 2),
        }
    finally:
        asyncio.to_thread = original_to_thread
        executor.shutdown(wait=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("legacy", "repaired"), required=True
    )
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(benchmark(arguments.mode)), sort_keys=True))
