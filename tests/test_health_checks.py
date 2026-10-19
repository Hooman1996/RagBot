"""Offline monitoring contract and resource isolation; no live dependencies."""
import asyncio
import gc
import json
import io
import logging
import threading
import time
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import psycopg2
import pytest
from fastapi import FastAPI
from minio import Minio
from minio.error import S3Error
from openai import AsyncOpenAI, Omit

from utils import health_checks as health
from utils.client_lifecycle import SerializedClient
from utils.concurrency import AdmissionLimiter
from utils.http_logging_middleware import route_log_policy


SECRET = "synthetic-secret-never-published"


def runtime():
    app = FastAPI()
    remote = NS(rest_uri="https://qdrant.test/proxy/qdrant", _rest_headers={"api-key": SECRET}, _rest_args={})
    qdrant = SerializedClient(NS(_client=remote, close=MagicMock()))
    business_http = NS(headers={"Authorization": "Bearer " + SECRET}, auth=None, is_closed=False)
    search = NS(qdrant_client=qdrant, collection_name="private-collection", _expected_embedding_dimensions=1024,
                tei_embed_url="https://embedding.test/prefix", tei_rerank_url="https://reranker.test/prefix",
                _http=business_http, _sync_http=business_http, _closed=False)
    llm = NS(base_url="https://vllm.test/proxy/v1/", default_headers={"Authorization": "Bearer " + SECRET}, is_closed=False)
    rag = NS(client=llm, model_id="private-model", search_engine=search, _closed=False)
    classifier = NS(_checkpoint_loaded=True, required=False)
    agent = NS(rag_system=rag, graph=NS(ainvoke=AsyncMock(side_effect=AssertionError("graph must not execute"))),
               intent_classifier=classifier)
    answering = NS(agent_service=agent, intent_classifier=classifier)
    app.state.ready = True
    app.state.health_phase = "running"
    app.state.agent_service = agent
    app.state.answering_service = answering
    app.state.blocking_runner = NS(closed=False)
    app.state.request_limiter = AdmissionLimiter(3)
    app.state.db_manager = NS(conn_params={"host": "postgres.test", "password": SECRET, "options": "-c statement_timeout=10000"})
    app.state.health_ocr_service = None
    app.state.health_minio_bucket = "private-bucket"
    app.state.health_minio_client = Minio("minio.test:9000", access_key="test-key", secret_key=SECRET, secure=False)
    return app


def healthy_http(request):
    assert request.method == "GET", "health must not invoke inference or writes"
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "private-model"}]})
    if "/collections/" in request.url.path:
        return httpx.Response(200, json={"status": "ok", "result": {"status": "green", "config": {
            "params": {"vectors": {"size": 1024, "distance": "Cosine"}}}}})
    return httpx.Response(200, content="all shards are ready" if request.url.path.endswith("readyz") else "")


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = runtime()
        self.requests = []
        def handler(request):
            self.requests.append(request)
            return healthy_http(request)
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.coordinator = health.HealthCoordinator(self.app, http_client=self.http)
        self.pg = MagicMock()
        self.pg.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        self.pg_connect = patch.object(health.psycopg2, "connect", return_value=self.pg)
        self.connect = self.pg_connect.start()
        self.minio_response = NS(status=200, release_conn=MagicMock())
        self.minio_patch = patch.object(Minio, "_url_open", return_value=self.minio_response)
        self.minio_head = self.minio_patch.start()

    async def asyncTearDown(self):
        await self.coordinator.aclose()
        self.pg_connect.stop()
        self.minio_patch.stop()

    async def report(self):
        return await self.coordinator.report(details=True)

    async def test_all_required_pass_optional_disabled_and_read_only_operations(self):
        original_params = dict(self.app.state.db_manager.conn_params)
        status, body = await self.report()
        self.assertEqual((status, body["status"], body["code"], body["ready"]), (200, "healthy", "HEALTH_OK", True))
        self.assertEqual(set(body["checks"]), set(health.COMPONENTS))
        self.assertEqual(body["failed_components"], [])
        self.assertEqual(body["warning_components"], [])
        self.assertLess(body["cache_age_ms"], 50)
        self.assertTrue(body["checked_at"].endswith("Z"))
        self.assertEqual(body["checks"]["ocr"], dict(status="disabled", required=False, code="CHECK_DISABLED", latency_ms=0))
        self.assertTrue(all(body["checks"][name]["status"] == "up" for name in health.REQUIRED))
        self.assertEqual(self.app.state.db_manager.conn_params, original_params)
        self.assertEqual(self.connect.call_args.kwargs["connect_timeout"], 2)
        self.assertEqual(self.connect.call_args.kwargs["tcp_user_timeout"], 1000)
        self.assertIn("statement_timeout=1000", self.connect.call_args.kwargs["options"])
        self.assertIn("default_transaction_read_only=on", self.connect.call_args.kwargs["options"])
        self.pg.cursor.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")
        self.pg.rollback.assert_called_once()
        self.pg.close.assert_called_once()
        self.pg.commit.assert_not_called()
        self.minio_head.assert_called_once_with("HEAD", "us-east-1", bucket_name="private-bucket")
        self.minio_response.release_conn.assert_called_once()
        self.assertEqual({str(r.url) for r in self.requests}, {
            "https://qdrant.test/proxy/qdrant/readyz", "https://qdrant.test/proxy/qdrant/collections/private-collection",
            "https://embedding.test/prefix/health", "https://reranker.test/prefix/health",
            "https://vllm.test/proxy/health", "https://vllm.test/proxy/v1/models"})
        self.assertTrue(all(SECRET in (r.headers.get("api-key") or r.headers.get("authorization", "")) for r in self.requests))
        for forbidden in (SECRET, ".test", "private-model", "private-bucket", "private-collection"):
            self.assertNotIn(forbidden, json.dumps(body))

    async def test_each_required_component_fails_and_multiple_failures_are_retained(self):
        for name in health.REQUIRED:
            with self.subTest(component=name):
                checks = {key: health.Check("up", key in health.REQUIRED, "CHECK_OK") for key in health.COMPONENTS}
                checks[name] = health.Check("down", True, "CHECK_AUTH_FAILED")
                code, body = health.snapshot(checks).response(details=True, now=time.monotonic())
                self.assertEqual((code, body["code"], body["ready"]), (503, "HEALTH_NOT_READY", False))
                self.assertEqual(body["failed_components"], [name])
                self.assertEqual(body["checks"][name]["code"], "CHECK_AUTH_FAILED")
        with patch.object(self.coordinator, "probe_tei_embedding", AsyncMock(side_effect=health.CheckFailure("CHECK_AUTH_FAILED"))), \
             patch.object(self.coordinator, "probe_vllm", AsyncMock(side_effect=health.CheckFailure("CHECK_RESOURCE_MISSING"))):
            status, body = await self.report()
        self.assertEqual(status, 503)
        self.assertEqual(set(body["failed_components"]), {"tei_embedding", "vllm"})

    async def test_minio_only_failure_is_degraded_and_ocr_initialized_is_up(self):
        self.app.state.health_ocr_service = object()
        self.minio_head.side_effect = S3Error(code="NoSuchBucket", message=SECRET, resource="private-bucket",
                                            request_id="private-id", host_id="private-host", response=None)
        status, body = await self.report()
        self.assertEqual((status, body["status"], body["code"], body["ready"]), (200, "degraded", "HEALTH_DEGRADED", True))
        self.assertEqual(body["warning_components"], ["minio"])
        self.assertEqual(body["checks"]["minio"]["code"], "CHECK_RESOURCE_MISSING")
        self.assertEqual(body["checks"]["ocr"]["status"], "up")

    async def test_classifier_unloaded_even_when_not_required_by_startup(self):
        self.app.state.agent_service.intent_classifier._checkpoint_loaded = False
        before = self.app.state.request_limiter.snapshot()
        status, body = await self.report()
        self.assertEqual(status, 503)
        self.assertEqual(body["failed_components"], ["intent_classifier"])
        self.assertEqual(body["checks"]["intent_classifier"]["code"], "CHECK_NOT_INITIALIZED")
        self.assertTrue(self.app.state.ready)
        self.assertEqual(self.app.state.request_limiter.snapshot(), before)

    async def test_local_clients_closed_and_graph_missing(self):
        await self.report()
        self.app.state.agent_service.graph = None
        status, body = await self.report()
        self.assertEqual(status, 503)
        self.assertEqual(body["checks"]["application"]["code"], "CHECK_NOT_INITIALIZED")
        self.app.state.agent_service.graph = NS(ainvoke=AsyncMock())
        self.app.state.agent_service.rag_system.search_engine._http.is_closed = True
        self.assertEqual((await self.report())[0], 503)
        self.app.state.agent_service.rag_system.search_engine._http.is_closed = False
        self.app.state.agent_service.rag_system.search_engine.qdrant_client._client._client._closed = True
        self.assertEqual((await self.report())[0], 503)

    async def test_starting_stopping_and_cache_cannot_override_lifecycle(self):
        self.app.state.health_phase = "starting"
        status, body = await self.report()
        self.assertEqual((status, body["code"]), (503, "HEALTH_STARTING"))
        self.assertFalse(self.requests)
        self.app.state.health_phase = "running"
        await self.report()
        self.app.state.ready = False
        status, body = await self.report()
        self.assertEqual(body["code"], "HEALTH_NOT_READY")
        self.app.state.ready = True
        self.app.state.health_phase = "stopping"
        status, body = await self.report()
        self.assertEqual((status, body["code"], body["ready"]), (503, "HEALTH_STOPPING", False))
        self.assertTrue(self.app.state.ready)  # reports never write the lifecycle flag

    async def test_shutdown_while_refreshing(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        async def slow():
            entered.set()
            await finish.wait()
        with patch.object(self.coordinator, "probe_vllm", slow):
            task = asyncio.create_task(self.report())
            await entered.wait()
            self.app.state.health_phase = "stopping"
            finish.set()
            status, body = await task
        self.assertEqual((status, body["code"]), (503, "HEALTH_STOPPING"))

    async def test_teardown_cancels_refresh_but_reachable_waiter_reports_stopping(self):
        entered = asyncio.Event()
        async def slow():
            entered.set()
            await asyncio.Event().wait()
        with patch.object(self.coordinator, "probe_vllm", slow):
            waiter = asyncio.create_task(self.report())
            await entered.wait()
            await self.coordinator.aclose()
            status, body = await waiter
        self.assertEqual((status, body["code"]), (503, "HEALTH_STOPPING"))

    async def test_health_sdk_logs_are_suppressed_in_async_and_thread_contexts(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        loggers = [logging.getLogger(name) for name in ("httpx", "httpcore.http11", "urllib3.connectionpool")]
        previous = [(logger, logger.level) for logger in loggers]
        for logger in loggers:
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        def emit():
            for logger in loggers:
                logger.debug("private health URL/credential: %s", SECRET)
        async def probe():
            emit()
            await self.coordinator.sync("postgres", emit)
        try:
            with patch.object(self.coordinator, "probe_postgres", probe):
                await self.report()
            self.assertEqual(stream.getvalue(), "")
            loggers[0].debug("ordinary-business-log")
            self.assertIn("ordinary-business-log", stream.getvalue())
        finally:
            for logger, level in previous:
                logger.removeHandler(handler)
                logger.setLevel(level)

    async def test_coalesce_cancellation_snapshot_detachment_and_expiry(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        count = 0
        async def slow():
            nonlocal count
            count += 1
            entered.set()
            await finish.wait()
        with patch.object(self.coordinator, "probe_vllm", slow):
            first = asyncio.create_task(self.report())
            await entered.wait()
            others = [asyncio.create_task(self.report()) for _ in range(30)]
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            finish.set()
            results = await asyncio.gather(*others)
            self.assertEqual(count, 1)
            self.assertTrue(all(status == 200 for status, _ in results))
            results[0][1]["checks"]["vllm"]["status"] = "down"
            results[0][1]["failed_components"].append("vllm")
            await asyncio.sleep(.02)
            _, cached = await self.report()
            self.assertEqual(cached["checks"]["vllm"]["status"], "up")
            self.assertGreaterEqual(cached["cache_age_ms"], 20)
            self.assertEqual(count, 1)
            with patch.object(health, "REUSE_SECONDS", 0):
                await self.report()
            self.assertEqual(count, 2)

    async def test_expired_success_not_reused_after_failed_refresh(self):
        await self.report()
        with patch.object(health, "REUSE_SECONDS", 0), patch.object(self.coordinator, "probe_vllm", AsyncMock(side_effect=TimeoutError(SECRET))):
            status, body = await self.report()
        self.assertEqual((status, body["checks"]["vllm"]["code"]), (503, "CHECK_TIMEOUT"))

    async def test_component_and_overall_deadlines(self):
        async def slow():
            await asyncio.sleep(10)
        for component_timeout, overall_timeout in ((.03, .2), (1, .03)):
            with patch.object(health, "PER_COMPONENT_SECONDS", component_timeout), patch.object(health, "REFRESH_SECONDS", overall_timeout), \
                 patch.object(health, "REUSE_SECONDS", 0), patch.object(self.coordinator, "probe_vllm", slow):
                # A full GC of the whole suite's heap takes about 0.5 s; keep it
                # out of the timed window so only the deadlines are measured.
                enabled = gc.isenabled()
                gc.collect()
                gc.disable()
                try:
                    started = time.monotonic()
                    status, body = await self.report()
                    elapsed = time.monotonic() - started
                finally:
                    if enabled:
                        gc.enable()
                self.assertLess(elapsed, .3)
                self.assertEqual((status, body["checks"]["vllm"]["code"]), (503, "CHECK_TIMEOUT"))
                self.assertEqual(set(body["checks"]), set(health.COMPONENTS))

    async def test_repeated_sync_timeouts_do_not_accumulate_threads_or_submissions(self):
        release = threading.Event()
        calls = []
        def stuck():
            calls.append(1)
            release.wait(2)
        try:
            for _ in range(20):
                with self.assertRaises((TimeoutError, health.CheckFailure)):
                    async with asyncio.timeout(.005):
                        await self.coordinator.sync("postgres", stuck)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(self.coordinator._sync_jobs), 1)
            self.assertEqual(self.coordinator.executor._work_queue.qsize(), 0)
        finally:
            release.set()
        await asyncio.sleep(.02)
        await self.coordinator.sync("postgres", lambda: 1)

    async def test_postgres_invalid_result_still_rolls_back_and_closes(self):
        self.pg.cursor.return_value.__enter__.return_value.fetchone.return_value = (2,)
        status, body = await self.report()
        self.assertEqual((status, body["checks"]["postgres"]["code"]), (503, "CHECK_INVALID_RESPONSE"))
        self.pg.rollback.assert_called_once()
        self.pg.close.assert_called_once()

    async def test_coordinator_error_is_content_free_500_and_does_not_reuse_success(self):
        await self.report()
        with patch.object(health, "REUSE_SECONDS", 0), patch.object(self.coordinator, "state_checks", side_effect=RuntimeError(SECRET)):
            status, body = await self.report()
        self.assertEqual((status, body["code"]), (500, "HEALTH_CHECK_ERROR"))
        self.assertNotIn(SECRET, json.dumps(body))
        self.assertIsNone(self.coordinator._snapshot)

    async def test_cleanup_owns_only_health_resources(self):
        business = self.app.state.agent_service.rag_system.search_engine.qdrant_client
        await self.report()
        with patch.object(self.coordinator.pool, "clear", wraps=self.coordinator.pool.clear) as clear:
            await self.coordinator.aclose()
        self.assertTrue(self.http.is_closed)
        self.assertTrue(self.coordinator.executor._shutdown)
        clear.assert_called_once()
        self.assertFalse(business.closed)
        business._client.close.assert_not_called()
        self.assertFalse(self.app.state.agent_service.rag_system.client.is_closed)
        self.assertTrue(self.app.state.ready)

    async def test_native_cleanup_still_runs_if_health_http_close_fails(self):
        with patch.object(self.http, "aclose", AsyncMock(side_effect=RuntimeError(SECRET))), \
             patch.object(self.coordinator.pool, "clear") as clear:
            with self.assertRaises(RuntimeError):
                await self.coordinator.aclose()
            clear.assert_called_once()
            self.assertTrue(self.coordinator.executor._shutdown)

    async def test_native_pool_cleanup_deferred_until_outstanding_minio_finishes(self):
        release = threading.Event()
        entered = threading.Event()
        def slow():
            entered.set()
            release.wait(2)
        waiter = asyncio.create_task(self.coordinator.sync("minio", slow))
        try:
            while not entered.is_set():
                await asyncio.sleep(.001)
            with patch.object(health, "REFRESH_SECONDS", .01), \
                 patch.object(self.coordinator.pool, "clear") as clear:
                await self.coordinator.aclose()
                clear.assert_not_called()
                release.set()
                # Keep the test loop active while the sandbox delivers thread
                # callbacks; its idle cross-thread wakeups are unreliable.
                async with asyncio.timeout(1):
                    while not waiter.done():
                        await asyncio.sleep(.001)
                await waiter
                clear.assert_called_once()
        finally:
            release.set()
            await asyncio.gather(waiter, return_exceptions=True)

    async def test_stable_state_change_logs_omit_raw_errors_and_success_poll_noise(self):
        with patch.object(health, "log_event") as event:
            await self.report()
            event.assert_not_called()
            with patch.object(health, "REUSE_SECONDS", 0), patch.object(self.coordinator, "probe_vllm", AsyncMock(side_effect=RuntimeError(SECRET))):
                await self.report()
                await self.report()
            self.assertEqual(event.call_count, 1)
            self.assertEqual(event.call_args.args[2], {"component": "vllm", "code": "CHECK_ERROR", "status": "down"})
            self.assertNotIn(SECRET, str(event.call_args))

    async def test_real_routes_legacy_auth_liveness_and_chatbot_remain_independent(self):
        import main
        import web_auth
        self.app.state.health_coordinator = self.coordinator
        db = NS(get_web_user_by_id=MagicMock(side_effect=AssertionError("lookup forbidden")))
        with patch.object(main.app, "state", self.app.state), patch.object(main, "db_manager", db), \
             patch.dict("os.environ", {"WEB_SESSION_SECRET": "test-secret-" + "x" * 48, "WEB_SESSION_SECONDS": "900"}), \
             patch.object(main, "rag_system", object()), patch.object(main, "available_documents", []), patch.object(main, "ocr_service", None):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                client.cookies.set(web_auth.SESSION_COOKIE, web_auth.create_session(1)[0])
                for name in ("live", "ready", "details"):
                    response = await client.get("/api/health/" + name)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["cache-control"], "no-store")
                db.get_web_user_by_id.assert_not_called()
                self.assertEqual((await client.get("/api/health")).json(), {
                    "status": "healthy", "system_initialized": True, "documents_available": 0, "ocr_available": False})
                client.cookies.clear()
                for path in ("/api/documents", "/api/health/unknown", "/api/health/live/"):
                    self.assertEqual((await client.get(path)).status_code, 401)
                self.assertEqual((await client.post("/api/health/live")).status_code, 401)
                self.app.state.agent_service.intent_classifier._checkpoint_loaded = False
                self.assertEqual((await client.get("/api/health/ready")).status_code, 503)
                original = self.app.state.request_limiter.snapshot()
                query = main.QueryRequest(query="synthetic", session_id=1, documents=[])
                with patch.object(main, "require_owned_session", AsyncMock()), patch.object(main, "_query_documents", AsyncMock(return_value={"answer": "mocked-success"})):
                    request = NS(app=main.app)
                    self.assertEqual(await main.query_documents(query, request, NS(user_id=1)), {"answer": "mocked-success"})
                self.assertTrue(self.app.state.ready)
                self.assertEqual(self.app.state.request_limiter.capacity, original.capacity)
                self.assertEqual(self.app.state.request_limiter.snapshot().acquired_total, original.acquired_total + 1)
                async def slow():
                    await asyncio.sleep(.08)
                with patch.object(health, "REUSE_SECONDS", 0), patch.object(self.coordinator, "probe_vllm", slow):
                    probe = asyncio.create_task(client.get("/api/health/details"))
                    await asyncio.sleep(.01)
                    start = time.monotonic()
                    live = await client.get("/api/health/live")
                    self.assertLess(time.monotonic() - start, .05)
                    self.assertEqual(live.json(), {"status": "alive", "code": "HEALTH_ALIVE"})
                    await probe

    async def test_reachable_routes_before_coordinator_creation_and_after_shutdown(self):
        import main
        app = FastAPI()
        for phase, expected in (("starting", "HEALTH_STARTING"), ("stopping", "HEALTH_STOPPING")):
            app.state.health_phase = phase
            with patch.object(main.app, "state", app.state):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                    for route in ("ready", "details"):
                        result = await client.get("/api/health/" + route)
                        self.assertEqual((result.status_code, result.json()["code"]), (503, expected))
                        self.assertEqual(result.headers["cache-control"], "no-store")
                    self.assertEqual((await client.get("/api/health/live")).status_code, 200)


@pytest.mark.parametrize("component", ["qdrant", "tei_embedding", "tei_reranker", "vllm"])
@pytest.mark.parametrize("scenario,expected", [
    ("timeout", "CHECK_TIMEOUT"), ("connect", "CHECK_UNREACHABLE"),
    ("auth", "CHECK_AUTH_FAILED"), ("unhealthy", "CHECK_UNHEALTHY"),
    ("structured_unhealthy", "CHECK_UNHEALTHY"),
    ("malformed_health", "CHECK_INVALID_RESPONSE"),
    ("invalid", "CHECK_INVALID_RESPONSE"), ("redirect", "CHECK_INVALID_RESPONSE"),
])
def test_external_failures_have_stable_codes(component, scenario, expected):
    async def run():
        app = runtime()
        host = {"qdrant": "qdrant.test", "tei_embedding": "embedding.test", "tei_reranker": "reranker.test", "vllm": "vllm.test"}[component]
        def handler(request):
            if request.url.host != host:
                return healthy_http(request)
            if scenario == "timeout":
                raise httpx.ReadTimeout(SECRET)
            if scenario == "connect":
                raise httpx.ConnectError(SECRET)
            if scenario == "structured_unhealthy":
                return httpx.Response(200, json={"error_type": "unhealthy", "error": SECRET})
            if scenario == "malformed_health":
                return httpx.Response(200, json={"status": [SECRET]})
            return httpx.Response({"auth": 401, "unhealthy": 500, "invalid": 200, "redirect": 302}[scenario], text="<html>" + SECRET)
        coordinator = health.HealthCoordinator(app, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        coordinator.probe_postgres = AsyncMock()
        coordinator.probe_minio = AsyncMock()
        try:
            status, body = await coordinator.report(details=True)
            assert status == 503
            assert body["checks"][component]["code"] == expected
            assert SECRET not in json.dumps(body)
        finally:
            await coordinator.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("scenario,expected", [
    ("collection_missing", "CHECK_RESOURCE_MISSING"), ("dimension", "CHECK_CONFIG_MISMATCH"),
    ("named", "CHECK_CONFIG_MISMATCH"), ("malformed", "CHECK_INVALID_RESPONSE"),
    ("unsupported_readyz", "CHECK_INVALID_RESPONSE"), ("model_missing", "CHECK_RESOURCE_MISSING"),
    ("malformed_models", "CHECK_INVALID_RESPONSE"), ("too_large", "CHECK_INVALID_RESPONSE"),
    ("red", "CHECK_UNHEALTHY"), ("unknown_status", "CHECK_INVALID_RESPONSE"),
])
def test_qdrant_and_model_metadata(scenario, expected):
    async def run():
        def handler(request):
            if request.url.path.endswith("readyz") and scenario == "unsupported_readyz":
                return httpx.Response(404)
            if request.url.path.endswith("models") and scenario in {"model_missing", "malformed_models"}:
                return httpx.Response(200, json={"data": []} if scenario == "model_missing" else {"data": [{}]})
            if "/collections/" in request.url.path:
                if scenario == "collection_missing":
                    return httpx.Response(404)
                if scenario == "malformed":
                    return httpx.Response(200, json={"status": "ok", "result": None})
                if scenario == "too_large":
                    return httpx.Response(200, content=b"x" * (health.MAX_RESPONSE_BYTES + 1))
                response = healthy_http(request)
                data = response.json()
                if scenario == "dimension":
                    data["result"]["config"]["params"]["vectors"]["size"] = 768
                if scenario == "named":
                    data["result"]["config"]["params"]["vectors"] = {"dense": {"size": 1024}}
                if scenario in {"red", "unknown_status"}:
                    data["result"]["status"] = "red" if scenario == "red" else "unknown"
                return httpx.Response(200, json=data)
            return healthy_http(request)
        coordinator = health.HealthCoordinator(runtime(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        coordinator.probe_postgres = AsyncMock()
        coordinator.probe_minio = AsyncMock()
        try:
            status, body = await coordinator.report(details=True)
            component = "vllm" if scenario in {"model_missing", "malformed_models"} else "qdrant"
            assert status == 503
            assert body["checks"][component]["code"] == expected
        finally:
            await coordinator.aclose()
    asyncio.run(run())


def test_auth_allowlist_and_logging_policy_are_exact():
    from web_auth import web_route
    for name in ("live", "ready", "details"):
        path = "/api/health/" + name
        assert not web_route(path, "GET")
        for method in ("POST", "PUT", "HEAD", "DELETE"):
            assert web_route(path, method)
        assert web_route(path + "/", "GET")
        policy = route_log_policy(path)
        assert not policy.request_body and not policy.response_body
    assert web_route("/api/health/unknown")


@pytest.mark.parametrize("component", sorted(health.REQUIRED))
def test_every_required_failure_through_coordinator(component):
    async def run():
        app = runtime()
        coordinator = health.HealthCoordinator(app, http_client=httpx.AsyncClient(transport=httpx.MockTransport(healthy_http)))
        coordinator.probe_postgres = AsyncMock()
        coordinator.probe_minio = AsyncMock()
        if component == "application":
            app.state.ready = False
        elif component == "intent_classifier":
            app.state.agent_service.intent_classifier._checkpoint_loaded = False
        else:
            setattr(coordinator, "probe_" + component,
                    AsyncMock(side_effect=health.CheckFailure("CHECK_AUTH_FAILED")))
        try:
            status, body = await coordinator.report(details=True)
            assert status == 503 and body["ready"] is False
            assert body["failed_components"] == [component]
            assert body["checks"][component]["code"] == (
                "CHECK_NOT_INITIALIZED" if component in {"application", "intent_classifier"} else "CHECK_AUTH_FAILED")
        finally:
            await coordinator.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("base,health_url,models", [
    ("https://example.test/proxy/v1/", "https://example.test/proxy/health", "https://example.test/proxy/v1/models"),
    ("https://example.test/proxy/", "https://example.test/proxy/health", "https://example.test/proxy/v1/models"),
])
def test_openai_url_prefixes(base, health_url, models):
    assert health.endpoint(base, "health", openai_root=True) == health_url
    suffix = "models" if base.rstrip("/").endswith("/v1") else "v1/models"
    assert health.endpoint(base, suffix) == models


def test_structured_exception_mapping_without_message_matching():
    auth = psycopg2.errors.InvalidPassword(SECRET)
    # Server-side SQLSTATE can be supplied through the diagnostic interface.
    class AuthFailure(psycopg2.OperationalError):
        pgcode = "28P01"
    assert health.failure_code(AuthFailure(SECRET)) == "CHECK_AUTH_FAILED"
    assert health.failure_code(auth) == "CHECK_AUTH_FAILED"
    assert health.failure_code(psycopg2.OperationalError(SECRET)) == "CHECK_UNREACHABLE"
    assert health.failure_code(health.CheckFailure("CHECK_CONFIG_MISMATCH")) == "CHECK_CONFIG_MISMATCH"
    assert health.failure_code(S3Error(code="AccessDenied", message=SECRET, resource=SECRET,
                                      request_id=SECRET, host_id=SECRET, response=None)) == "CHECK_AUTH_FAILED"


def test_health_pool_forces_no_redirects_or_retries():
    pool = health.HealthPool()
    with patch.object(health.urllib3.PoolManager, "urlopen", return_value=NS(status=200)) as call:
        pool.urlopen("HEAD", "http://example.test/bucket", retries=5, redirect=True)
    assert call.call_args.kwargs["retries"] is False
    assert call.call_args.kwargs["redirect"] is False
    pool.clear()


# Evidence: https://api.qdrant.tech/master/api-reference/service/readyz
@pytest.mark.parametrize("body,expected", [
    (b"all shards are ready", "CHECK_OK"),
    (b'"all shards are ready"', "CHECK_OK"),
    (b' \n"all shards are ready"\n', "CHECK_OK"),
    (b"", "CHECK_INVALID_RESPONSE"),
    (b"healthz check passed", "CHECK_INVALID_RESPONSE"),
    (b"some shards are not ready", "CHECK_INVALID_RESPONSE"),
    (b'"all shards are ready', "CHECK_INVALID_RESPONSE"),
    (b'{"status":"unhealthy"}', "CHECK_UNHEALTHY"),
    (b'{"unexpected":"all shards are ready"}', "CHECK_INVALID_RESPONSE"),
])
def test_qdrant_readiness_protocol(body, expected):
    async def run():
        def handler(request):
            if request.url.path.endswith("readyz"):
                return httpx.Response(200, content=body)
            return healthy_http(request)
        coordinator = health.HealthCoordinator(runtime(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            check = await coordinator._check("qdrant")
            assert check.code == expected
        finally:
            await coordinator.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("status", ["green", "yellow", "grey"])
def test_queryable_qdrant_collection_statuses(status):
    # https://qdrant.tech/documentation/faq/#why-is-my-collection-in-grey-status
    # Active search does not request indexed_only or prevent_unoptimized.
    async def run():
        def handler(request):
            response = healthy_http(request)
            if "/collections/" in request.url.path:
                data = response.json()
                data["result"]["status"] = status
                return httpx.Response(200, json=data)
            return response
        coordinator = health.HealthCoordinator(runtime(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            assert (await coordinator._check("qdrant")).code == "CHECK_OK"
        finally:
            await coordinator.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("status,code", [(403, "CHECK_AUTH_FAILED"),
    (503, "CHECK_UNHEALTHY"), (504, "CHECK_TIMEOUT"),
    (404, "CHECK_INVALID_RESPONSE"), (302, "CHECK_INVALID_RESPONSE")])
def test_qdrant_readiness_unsuccessful_http(status, code):
    async def run():
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(status, content=b"some shards are not ready")
        coordinator = health.HealthCoordinator(runtime(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            assert (await coordinator._check("qdrant")).code == code
            assert len(requests) == 1  # Never substitute healthz for readiness.
        finally:
            await coordinator.aclose()
    asyncio.run(run())


def test_installed_qdrant_sdk_target_and_auth_compatibility():
    from qdrant_client import QdrantClient
    async def run():
        app = runtime()
        client = QdrantClient(url="https://qdrant.test/proxy", api_key=SECRET,
                              check_compatibility=False)
        app.state.agent_service.rag_system.search_engine.qdrant_client = SerializedClient(client)
        requests = []
        def handler(request):
            requests.append(request)
            return healthy_http(request)
        coordinator = health.HealthCoordinator(app, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            assert (await coordinator._check("qdrant")).code == "CHECK_OK"
            assert [request.url.path for request in requests] == ["/proxy/readyz", "/proxy/collections/private-collection"]
            assert all(request.headers["api-key"] == SECRET for request in requests)
        finally:
            await coordinator.aclose()
            client.close()
    asyncio.run(run())


@pytest.fixture
def real_openai_health_runtime(monkeypatch):
    # SDK constructor defaults consult these variables even with a synthetic key.
    monkeypatch.delenv("OPENAI_ORG_ID", raising=False)
    monkeypatch.delenv("OPENAI_PROJECT_ID", raising=False)

    @asynccontextmanager
    async def create(handler=healthy_http, *, configured=False, invalid_header=False):
        def business_request_forbidden(_request):
            raise AssertionError("Health must use its isolated transport")

        business_http = httpx.AsyncClient(
            transport=httpx.MockTransport(business_request_forbidden),
            headers={"X-Business-Client": "synthetic-business"},
        )
        custom_headers = {"X-Synthetic-Custom": "synthetic-custom", "X-Synthetic-Omitted": Omit()}
        if invalid_header:
            custom_headers["X-Synthetic-Invalid"] = 42
        sdk = AsyncOpenAI(
            api_key="synthetic-vllm-key",
            base_url="https://vllm.test/proxy/v1/",
            organization="synthetic-org" if configured else None,
            project="synthetic-project" if configured else None,
            default_headers=custom_headers,
            http_client=business_http,
        )
        app = runtime()
        app.state.agent_service.rag_system.client = sdk
        requests = []

        def health_request(request):
            requests.append(request)
            assert request.method == "GET"
            return handler(request)

        coordinator = health.HealthCoordinator(
            app, http_client=httpx.AsyncClient(transport=httpx.MockTransport(health_request)),
        )
        business_headers = dict(business_http.headers)
        sdk_headers = sdk.default_headers
        try:
            yield coordinator, sdk, requests
        finally:
            try:
                await coordinator.aclose()
                assert coordinator.http.is_closed
                assert not sdk.is_closed()
                assert not business_http.is_closed
                assert dict(business_http.headers) == business_headers
                assert sdk.organization == ("synthetic-org" if configured else None)
                assert sdk.project == ("synthetic-project" if configured else None)
                # Omit instances are freshly constructed by the SDK property.
                for name, original in sdk_headers.items():
                    current = sdk.default_headers[name]
                    if isinstance(original, Omit):
                        assert isinstance(current, Omit)
                    else:
                        assert current == original
            finally:
                # Only fixture teardown owns closure of this business client.
                await sdk.close()
                assert business_http.is_closed

    return create


@pytest.mark.parametrize("configured", [False, True])
def test_vllm_real_sdk_headers(real_openai_health_runtime, configured):
    async def run():
        async with real_openai_health_runtime(configured=configured) as (coordinator, sdk, requests):
            for name in ("OpenAI-Organization", "OpenAI-Project"):
                assert isinstance(sdk.default_headers[name], str if configured else Omit)
            check = await coordinator._check("vllm")
            assert (check.status, check.code) == ("up", "CHECK_OK")
            assert [(request.method, str(request.url)) for request in requests] == [
                ("GET", "https://vllm.test/proxy/health"),
                ("GET", "https://vllm.test/proxy/v1/models"),
            ]
            for request in requests:
                assert request.headers["Authorization"] == "Bearer synthetic-vllm-key"
                assert request.headers["X-Synthetic-Custom"] == "synthetic-custom"
                assert "X-Synthetic-Omitted" not in request.headers
                if configured:
                    assert request.headers["OpenAI-Organization"] == "synthetic-org"
                    assert request.headers["OpenAI-Project"] == "synthetic-project"
                else:
                    assert "OpenAI-Organization" not in request.headers
                    assert "OpenAI-Project" not in request.headers
    asyncio.run(run())


@pytest.mark.parametrize("scenario,code", [
    ("missing_model", "CHECK_RESOURCE_MISSING"),
    ("health_auth", "CHECK_AUTH_FAILED"),
    ("health_unhealthy", "CHECK_UNHEALTHY"),
    ("health_timeout", "CHECK_TIMEOUT"),
    ("models_auth", "CHECK_AUTH_FAILED"),
    ("models_unhealthy", "CHECK_UNHEALTHY"),
    ("models_invalid", "CHECK_INVALID_RESPONSE"),
    ("models_timeout", "CHECK_TIMEOUT"),
])
def test_vllm_real_sdk_dependency_failure_codes(real_openai_health_runtime, scenario, code):
    async def run():
        def handler(request):
            health_request = request.url.path.endswith("/health")
            if health_request and scenario.startswith("health_"):
                return httpx.Response({"health_auth": 401, "health_unhealthy": 503,
                                       "health_timeout": 504}[scenario])
            if not health_request:
                if scenario == "missing_model":
                    return httpx.Response(200, json={"data": []})
                if scenario == "models_invalid":
                    return httpx.Response(200, json={"data": [{}]})
                if scenario == "models_timeout":
                    raise httpx.ReadTimeout("synthetic timeout")
                if scenario in {"models_auth", "models_unhealthy"}:
                    return httpx.Response(403 if scenario == "models_auth" else 500)
            return healthy_http(request)

        async with real_openai_health_runtime(handler) as (coordinator, _sdk, requests):
            check = await coordinator._check("vllm")
            assert (check.status, check.code) == ("down", code)
            paths = ["/proxy/health"]
            if not scenario.startswith("health_"):
                paths.append("/proxy/v1/models")
            assert [(request.method, request.url.path) for request in requests] == [
                ("GET", path) for path in paths
            ]
    asyncio.run(run())


def test_vllm_preserves_invalid_non_sentinel_header_failure(real_openai_health_runtime):
    async def run():
        async with real_openai_health_runtime(invalid_header=True) as (coordinator, _sdk, requests):
            check = await coordinator._check("vllm")
            assert (check.status, check.code) == ("down", "CHECK_ERROR")
            assert requests == []  # Invalid values are neither removed nor stringified.
    asyncio.run(run())
