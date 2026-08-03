import asyncio
import concurrent.futures
import functools
import threading
import time
import unittest
from pathlib import Path

from utils.client_lifecycle import SerializedClient
from utils.concurrency import BoundedBlockingRunner
from utils.service_errors import (
    ServiceOverloadedError,
    ServiceProtocolError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)


ROOT = Path(__file__).resolve().parents[1]


class ThreadedAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=24)
        self.original_to_thread = asyncio.to_thread

        async def working_to_thread(func, /, *args, **kwargs):
            call = functools.partial(func, *args, **kwargs)
            future = self.executor.submit(call)
            while not future.done():
                await asyncio.sleep(0.001)
            return future.result()

        # Python 3.14's default asyncio executor is unavailable in this audit
        # interpreter. Tests retain real worker-thread behavior by supplying a
        # dedicated executor at the asyncio.to_thread boundary.
        asyncio.to_thread = working_to_thread

    async def asyncTearDown(self):
        asyncio.to_thread = self.original_to_thread
        self.executor.shutdown(wait=True)


class ConcurrentRequestTests(ThreadedAsyncTestCase):
    async def test_twenty_mocked_requests_overlap_and_loop_stays_responsive(self):
        runner = BoundedBlockingRunner(max_concurrency=20)
        active = 0
        peak_active = 0
        lock = threading.Lock()

        def blocking_request(request_id):
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            try:
                time.sleep(0.05)
                return request_id
            finally:
                with lock:
                    active -= 1

        started = time.perf_counter()
        requests = [
            asyncio.create_task(runner.run(blocking_request, request_id))
            for request_id in range(20)
        ]
        heartbeat_lag = []
        previous = time.perf_counter()
        while any(not request.done() for request in requests):
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            heartbeat_lag.append(max(0.0, now - previous - 0.005))
            previous = now

        results = await asyncio.gather(*requests)
        elapsed = time.perf_counter() - started
        await runner.aclose()

        self.assertEqual(results, list(range(20)))
        self.assertGreaterEqual(peak_active, 10)
        self.assertLess(elapsed, 0.25)
        self.assertLess(max(heartbeat_lag), 0.05)

    async def test_twenty_requests_obey_bound(self):
        runner = BoundedBlockingRunner(max_concurrency=4)
        active = 0
        peak_active = 0
        lock = threading.Lock()

        def blocking_request(request_id):
            nonlocal active, peak_active
            with lock:
                active += 1
                peak_active = max(peak_active, active)
            try:
                time.sleep(0.01)
                return request_id
            finally:
                with lock:
                    active -= 1

        results = await asyncio.gather(
            *(runner.run(blocking_request, index) for index in range(20))
        )
        await runner.aclose()

        self.assertEqual(results, list(range(20)))
        self.assertEqual(peak_active, 4)

    async def test_one_failure_does_not_cancel_nineteen_requests(self):
        runner = BoundedBlockingRunner(max_concurrency=20)

        def blocking_request(request_id):
            time.sleep(0.01)
            if request_id == 7:
                raise RuntimeError("synthetic failure")
            return request_id

        results = await asyncio.gather(
            *(runner.run(blocking_request, index) for index in range(20)),
            return_exceptions=True,
        )
        await runner.aclose()

        self.assertIsInstance(results[7], RuntimeError)
        self.assertEqual(
            [value for value in results if not isinstance(value, Exception)],
            [index for index in range(20) if index != 7],
        )

    async def test_cancelled_write_finishes_transaction_cleanup(self):
        runner = BoundedBlockingRunner(max_concurrency=2)
        started = threading.Event()
        state = {"active": False, "committed": False}

        def database_write():
            state["active"] = True
            started.set()
            try:
                time.sleep(0.05)
                state["committed"] = True
            finally:
                state["active"] = False

        cancelled = asyncio.create_task(
            runner.run(
                database_write,
                wait_for_completion_on_cancel=True,
            )
        )
        while not started.is_set():
            await asyncio.sleep(0.001)
        unrelated = asyncio.create_task(runner.run(lambda: "unrelated"))
        cancelled.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await cancelled
        self.assertEqual(await unrelated, "unrelated")
        self.assertFalse(state["active"])
        self.assertTrue(state["committed"])
        self.assertEqual(runner.active_count, 0)
        await runner.aclose()


class SharedClientLifecycleTests(ThreadedAsyncTestCase):
    async def test_twenty_requests_reuse_one_client_and_close_once(self):
        class Client:
            constructions = 0

            def __init__(self):
                type(self).constructions += 1
                self.calls = []
                self.close_calls = 0

            def request(self, request_id):
                self.calls.append(request_id)
                return request_id

            def close(self):
                self.close_calls += 1

        raw_client = Client()
        client = SerializedClient(raw_client)
        runner = BoundedBlockingRunner(max_concurrency=20)
        results = await asyncio.gather(
            *(runner.run(client.request, index) for index in range(20))
        )
        await runner.run(client.close)

        self.assertEqual(results, list(range(20)))
        self.assertEqual(Client.constructions, 1)
        self.assertEqual(raw_client.close_calls, 1)
        self.assertEqual(sorted(raw_client.calls), list(range(20)))
        with self.assertRaises(RuntimeError):
            await runner.run(client.request, 21)
        await runner.aclose()
        with self.assertRaises(RuntimeError):
            await runner.run(lambda: None)


class StaticLifecycleAndBoundaryTests(unittest.TestCase):
    def test_lifespan_owns_clients_and_explicit_phase_timeouts(self):
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        search_source = (
            ROOT / "utils/persian_hybrid_search.py"
        ).read_text(encoding="utf-8")
        rag_source = (ROOT / "utils/RagSystem.py").read_text(encoding="utf-8")
        config_source = (
            ROOT / "utils/performance_config.py"
        ).read_text(encoding="utf-8")

        import_time_prefix = main_source.split(
            "@asynccontextmanager", maxsplit=1
        )[0]
        self.assertNotIn("qdrant_client = QdrantClient(", import_time_prefix)
        for setting in (
            "tei_http_connect_timeout_seconds",
            "tei_http_read_timeout_seconds",
            "tei_http_write_timeout_seconds",
            "tei_http_pool_timeout_seconds",
        ):
            self.assertIn(setting, main_source)
            self.assertIn(setting, search_source)
        self.assertIn("vllm_http_read_timeout_seconds", main_source)
        self.assertIn("vllm_http_read_timeout_seconds", rag_source)
        self.assertIn('"TEI_HTTP_READ_TIMEOUT_SECONDS", 15.0', config_source)
        self.assertIn('"VLLM_HTTP_READ_TIMEOUT_SECONDS", 45.0', config_source)
        self.assertIn("await cleanup(rag_system.aclose)", main_source)
        self.assertIn("await cleanup(llm_client.close)", main_source)
        self.assertIn("await cleanup(tei_http_client.aclose)", main_source)
        self.assertIn("db_connections.close_all", main_source)

    def test_database_connections_are_created_inside_worker_operations(self):
        database_source = (
            ROOT / "new_architecture/app/services/history/database.py"
        ).read_text(encoding="utf-8")
        agent_source = (ROOT / "agent_service.py").read_text(encoding="utf-8")
        auth_source = (
            ROOT
            / "new_architecture/app/services/authentication/authentication.py"
        ).read_text(encoding="utf-8")
        classifier_source = (
            ROOT / "intent_classifier.py"
        ).read_text(encoding="utf-8")

        self.assertIn("conn = self.get_connection()", database_source)
        self.assertIn('"connect_timeout": connect_timeout', database_source)
        self.assertIn("statement_timeout=", database_source)
        self.assertIn(
            "await self.blocking_runner.run(\n"
            "            self.db_manager.get_session_metadata",
            agent_source,
        )
        self.assertIn(
            "conn = self.db_manager.get_connection()", auth_source
        )
        self.assertIn(
            "await self.blocking_runner.run(\n"
            "                    self._classify_embedding",
            classifier_source,
        )

    def test_service_errors_have_stable_boundary_codes(self):
        self.assertEqual(ServiceTimeoutError.status_code, 504)
        self.assertEqual(ServiceUnavailableError.status_code, 503)
        self.assertEqual(ServiceProtocolError.status_code, 502)
        self.assertEqual(ServiceOverloadedError.status_code, 503)
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        mobile_source = (ROOT / "mobile_api.py").read_text(encoding="utf-8")
        self.assertIn("@app.exception_handler(ServiceError)", main_source)
        self.assertIn("except asyncio.CancelledError:", mobile_source)
        self.assertIn("except (HTTPException, ServiceError):", mobile_source)


if __name__ == "__main__":
    unittest.main()
