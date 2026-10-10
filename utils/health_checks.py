"""Read-only, worker-local monitoring. Never controls chatbot admission or routing."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
import psycopg2
import urllib3
from minio import Minio
from minio.error import InvalidResponseError, S3Error, ServerError
from openai import Omit

from .structured_logging import log_event

COMPONENTS = (
    "application", "postgres", "qdrant", "tei_embedding", "tei_reranker",
    "vllm", "intent_classifier", "minio", "ocr",
)
REQUIRED = frozenset(COMPONENTS[:-2])
PER_COMPONENT_SECONDS = 2.0
REFRESH_SECONDS = 3.0
REUSE_SECONDS = 5.0
MAX_RESPONSE_BYTES = 64 * 1024
LOGGER = logging.getLogger("health_checks")
_HEALTH_IO = ContextVar("health_io", default=False)


class _HealthLogFilter(logging.Filter):
    def filter(self, record):
        # SDK debug logs can include URLs/headers. Suppress only health I/O,
        # leaving business-client logging policy untouched.
        return not _HEALTH_IO.get()


_IO_LOG_FILTER = _HealthLogFilter()


class CheckFailure(Exception):
    """Only a stable code crosses the probe boundary."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def failure_code(exc):
    if isinstance(exc, CheckFailure):
        return exc.code
    if isinstance(exc, urllib3.exceptions.MaxRetryError):
        return failure_code(exc.reason)
    if isinstance(exc, (httpx.ConnectError, ConnectionError, urllib3.exceptions.NewConnectionError)):
        return "CHECK_UNREACHABLE"
    if isinstance(exc, (TimeoutError, httpx.TimeoutException, urllib3.exceptions.TimeoutError)):
        return "CHECK_TIMEOUT"
    if isinstance(exc, psycopg2.Error):
        if isinstance(exc, (psycopg2.errors.InvalidPassword, psycopg2.errors.InvalidAuthorizationSpecification)):
            return "CHECK_AUTH_FAILED"
        if isinstance(exc, psycopg2.errors.QueryCanceled):
            return "CHECK_TIMEOUT"
        sqlstate = exc.pgcode or getattr(exc.diag, "sqlstate", None)
        if sqlstate and sqlstate.startswith("28"):
            return "CHECK_AUTH_FAILED"
        if sqlstate == "57014":
            return "CHECK_TIMEOUT"
        if isinstance(exc, psycopg2.OperationalError):
            # libpq connection failures often supply no SQLSTATE. Do not parse
            # localized messages or claim an authentication diagnosis without it.
            return "CHECK_UNREACHABLE"
    if isinstance(exc, S3Error):
        if exc.code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken", "InvalidToken"}:
            return "CHECK_AUTH_FAILED"
        if exc.code == "NoSuchBucket":
            return "CHECK_RESOURCE_MISSING"
        if exc.code in {"RequestTimeout", "RequestTimeoutException"}:
            return "CHECK_TIMEOUT"
        if exc.code in {"RetryHead", "PermanentRedirect", "AuthorizationHeaderMalformed"}:
            return "CHECK_CONFIG_MISMATCH"
        if exc.code in {"InternalError", "ServiceUnavailable", "SlowDown"}:
            return "CHECK_UNHEALTHY"
        if exc.code == "MethodNotAllowed":
            return "CHECK_INVALID_RESPONSE"
        if exc.response is not None:
            status = exc.response.status
            if status in {401, 403, 408, 504} or status >= 500:
                return http_status_code(status)
    if isinstance(exc, ServerError):
        return http_status_code(exc.status_code)
    if isinstance(exc, InvalidResponseError):
        return http_status_code(exc._code)
    if isinstance(exc, (httpx.DecodingError, httpx.RemoteProtocolError)):
        return "CHECK_INVALID_RESPONSE"
    return "CHECK_ERROR"


def http_status_code(status, *, resource=False):
    if status in {401, 403}:
        return "CHECK_AUTH_FAILED"
    if status in {408, 504}:
        return "CHECK_TIMEOUT"
    if status == 404 and resource:
        return "CHECK_RESOURCE_MISSING"
    if status >= 500 or status == 429:
        return "CHECK_UNHEALTHY"
    return "CHECK_INVALID_RESPONSE"


def endpoint(base, suffix, *, openai_root=False):
    """Append to the configured prefix; remove only a final OpenAI /v1."""
    parts = urlsplit(str(base))
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment:
        raise CheckFailure("CHECK_CONFIG_MISMATCH")
    path = parts.path.rstrip("/")
    if openai_root and path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parts.scheme, parts.netloc, path + "/" + suffix, "", ""))


@dataclass(frozen=True)
class Check:
    status: str
    required: bool
    code: str
    latency_ms: int = 0

    def payload(self):
        return dict(status=self.status, required=self.required, code=self.code,
                    latency_ms=self.latency_ms)


@dataclass(frozen=True)
class Snapshot:
    checked_at: str
    completed: float
    checks: tuple[tuple[str, Check], ...]
    special: str | None = None

    def response(self, *, details, now):
        checks = dict(self.checks)
        failed = [name for name, check in self.checks if check.required and check.status != "up"]
        warnings = [name for name, check in self.checks if not check.required and check.status == "down"]
        if self.special:
            status, code, http_status, ready = {
                "starting": ("starting", "HEALTH_STARTING", 503, False),
                "stopping": ("stopping", "HEALTH_STOPPING", 503, False),
                "error": ("error", "HEALTH_CHECK_ERROR", 500, False),
            }[self.special]
        elif failed:
            status, code, http_status, ready = "not_ready", "HEALTH_NOT_READY", 503, False
        elif warnings:
            status, code, http_status, ready = "degraded", "HEALTH_DEGRADED", 200, True
        else:
            status, code, http_status, ready = "healthy", "HEALTH_OK", 200, True
        body = dict(status=status, code=code, ready=ready, checked_at=self.checked_at,
                    cache_age_ms=max(0, int((now - self.completed) * 1000)),
                    failed_components=failed, warning_components=warnings)
        if details:
            body["checks"] = {name: checks[name].payload() for name in COMPONENTS}
        return http_status, body


def snapshot(checks, special=None):
    return Snapshot(datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    time.monotonic(), tuple((name, checks[name]) for name in COMPONENTS), special)


def known_closed(obj):
    # SDK wrappers (OpenAI, SerializedClient, QdrantClient) expose their
    # transport state on an inner client. Inspect flags without method calls.
    for _ in range(4):
        if obj is None:
            break
        for name in ("_closed", "closed", "is_closed"):
            value = getattr(obj, name, False)
            if value is True or (type(value) is int and value != 0):
                return True
        obj = getattr(obj, "_client", None)
    return False


class HealthPool(urllib3.PoolManager):
    """Prevent the SDK from enabling HTTP retries or following redirects."""
    def urlopen(self, method, url, **kwargs):
        kwargs.update(retries=False, redirect=False)
        return super().urlopen(method, url, **kwargs)


class HealthCoordinator:
    def __init__(self, app, *, http_client=None):
        self.app = app
        for name in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2",
                     "httpcore.proxy", "httpcore.socks", "urllib3.connectionpool", "urllib3.util.retry"):
            logger = logging.getLogger(name)
            if _IO_LOG_FILTER not in logger.filters:
                logger.addFilter(_IO_LOG_FILTER)
        self.http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(PER_COMPONENT_SECONDS),
            limits=httpx.Limits(max_connections=6, max_keepalive_connections=6),
            transport=httpx.AsyncHTTPTransport(retries=0, limits=httpx.Limits(
                max_connections=6, max_keepalive_connections=6)),
            follow_redirects=False,
        )
        self.pool = HealthPool(num_pools=1, maxsize=1, block=True, retries=False,
                               timeout=urllib3.Timeout(total=2, connect=1, read=1))
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ragbot-health")
        self._sync_jobs = {}
        self._refresh_task = None
        self._snapshot = None
        self._previous = {}
        self._closed = False

    def lifecycle(self):
        phase = getattr(self.app.state, "health_phase", "starting")
        if self._closed or phase == "stopping":
            return "stopping"
        if phase != "running":
            return "starting"
        return None

    def local(self):
        state = self.app.state
        answering = getattr(state, "answering_service", None)
        agent = getattr(state, "agent_service", None)
        rag = getattr(agent, "rag_system", None)
        search = getattr(rag, "search_engine", None)
        return answering, agent, rag, search

    def state_checks(self):
        answering, agent, rag, search = self.local()
        resources = (answering, agent, rag, search,
                     getattr(rag, "client", None), getattr(search, "qdrant_client", None),
                     getattr(search, "_http", None), getattr(search, "_sync_http", None),
                     getattr(self.app.state, "blocking_runner", None))
        initialized = (getattr(self.app.state, "ready", False) is True
                       and all(obj is not None for obj in resources)
                       and callable(getattr(getattr(agent, "graph", None), "ainvoke", None))
                       and getattr(answering, "agent_service", None) is agent)
        runners = (getattr(agent, "blocking_runner", None), getattr(rag, "blocking_runner", None),
                   getattr(search, "_blocking_runner", None))
        available = initialized and not any(map(known_closed, resources + runners))
        checks = {"application": Check("up" if available else "down", True,
                                      "CHECK_OK" if available else "CHECK_NOT_INITIALIZED")}
        classifier = getattr(agent, "intent_classifier", None)
        loaded = classifier is not None and getattr(classifier, "_checkpoint_loaded", False) is True
        checks["intent_classifier"] = Check("up" if loaded else "down", True,
                                            "CHECK_OK" if loaded else "CHECK_NOT_INITIALIZED")
        ocr = getattr(self.app.state, "health_ocr_service", None)
        checks["ocr"] = Check("up" if ocr is not None else "disabled", False,
                              "CHECK_OK" if ocr is not None else "CHECK_DISABLED")
        return checks

    def unavailable(self, special):
        checks = {name: Check("down", name in REQUIRED,
                             "CHECK_ERROR" if special == "error" else "CHECK_NOT_INITIALIZED")
                  for name in COMPONENTS}
        # OCR alone can be intentionally disabled; unchecked services cannot.
        ocr = getattr(self.app.state, "health_ocr_service", None)
        checks["ocr"] = Check("up" if ocr is not None else "disabled", False,
                              "CHECK_OK" if ocr is not None else "CHECK_DISABLED")
        return snapshot(checks, special)

    async def report(self, *, details=False):
        try:
            return await self._report(details=details)
        except asyncio.CancelledError:
            # Teardown cancels the shared refresh. An uncancelled HTTP waiter
            # can still receive the stopping report; actual request cancellation
            # must propagate normally.
            if self.lifecycle() == "stopping" and not asyncio.current_task().cancelling():
                return self.unavailable("stopping").response(details=details, now=time.monotonic())
            raise
        except Exception:
            self._snapshot = None
            return self.unavailable("error").response(details=details, now=time.monotonic())

    async def _report(self, *, details):
        phase = self.lifecycle()
        if phase:
            return self.unavailable(phase).response(details=details, now=time.monotonic())
        cached = self._snapshot
        if cached is None or time.monotonic() - cached.completed >= REUSE_SECONDS:
            if self._refresh_task is None or self._refresh_task.done():
                self._refresh_task = asyncio.create_task(self._refresh())
            cached = await asyncio.shield(self._refresh_task)
        # Shutdown may begin while the refresh is awaited. Recheck before serving.
        phase = self.lifecycle()
        if phase:
            cached = self.unavailable(phase)
        else:
            # Local state is cheap and must not serve a cached local success
            # after a readiness flag/client has changed.
            checks = dict(cached.checks)
            checks.update(self.state_checks())
            cached = Snapshot(cached.checked_at, cached.completed,
                              tuple((name, checks[name]) for name in COMPONENTS), cached.special)
        return cached.response(details=details, now=time.monotonic())

    async def _refresh(self):
        tasks = {}
        try:
            checks = self.state_checks()
            for name in COMPONENTS:
                if name not in checks:
                    tasks[name] = asyncio.create_task(self._check(name))
            done, pending = await asyncio.wait(tasks.values(), timeout=REFRESH_SECONDS)
            for name, task in tasks.items():
                if task in done:
                    checks[name] = task.result()
                else:
                    task.cancel()
                    checks[name] = Check("down", name in REQUIRED, "CHECK_TIMEOUT", int(REFRESH_SECONDS * 1000))
            await asyncio.gather(*pending, return_exceptions=True)
            result = snapshot(checks)
            for name, check in result.checks:
                transition = (check.status, check.code)
                previous = self._previous.get(name)
                if previous != transition and (previous is not None or check.status == "down"):
                    log_event(LOGGER, "health_component_changed", {
                        "component": name, "code": check.code, "status": check.status,
                    })
                self._previous[name] = transition
            self._snapshot = result
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            # Coordinator errors never reuse old success or expose exception text.
            result = self.unavailable("error")
            self._snapshot = None
            return result
        finally:
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks.values(), return_exceptions=True)

    async def _check(self, name):
        started = time.monotonic()
        token = _HEALTH_IO.set(True)
        try:
            try:
                async with asyncio.timeout(PER_COMPONENT_SECONDS):
                    await getattr(self, "probe_" + name)()
                status, code = "up", "CHECK_OK"
            except Exception as exc:
                status, code = "down", failure_code(exc)
        finally:
            _HEALTH_IO.reset(token)
        return Check(status, name in REQUIRED, code, int((time.monotonic() - started) * 1000))

    async def get(self, url, *, headers=None, auth=None, resource=False):
        # Stream into a bounded buffer. Never log upstream bodies, headers or URLs.
        async with self.http.stream("GET", url, headers=headers, auth=auth,
                                    follow_redirects=False) as response:
            if response.status_code != 200:
                raise CheckFailure(http_status_code(response.status_code, resource=resource))
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise CheckFailure("CHECK_INVALID_RESPONSE")
                chunks.extend(chunk)
            return bytes(chunks)

    @staticmethod
    def parse_json(body):
        try:
            return json.loads(body)
        except (ValueError, UnicodeError):
            raise CheckFailure("CHECK_INVALID_RESPONSE") from None

    async def service_health(self, url, *, qdrant_readiness=False, **kwargs):
        body = await self.get(url, **kwargs)
        # TEI/vLLM use an empty successful response. Qdrant's readiness
        # contract is distinct from its healthz/liveness contract.
        accepted = {b"all shards are ready"} if qdrant_readiness else {b""}
        if body.strip() not in accepted:
            # Structured explicit unhealthy results still fail if a proxy has
            # rewritten the HTTP status. Do not match raw exception messages.
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError):
                data = None
            if qdrant_readiness and data == "all shards are ready":
                return
            if isinstance(data, dict) and (data.get("error_type") == "unhealthy"
                                          or data.get("status") in ("down", "unhealthy")):
                raise CheckFailure("CHECK_UNHEALTHY")
            raise CheckFailure("CHECK_INVALID_RESPONSE")

    def search(self):
        search = self.local()[3]
        if search is None:
            raise CheckFailure("CHECK_NOT_INITIALIZED")
        return search

    async def probe_tei_embedding(self):
        search = self.search()
        await self.service_health(endpoint(search.tei_embed_url, "health"),
                                  headers=search._http.headers, auth=search._http.auth)

    async def probe_tei_reranker(self):
        search = self.search()
        await self.service_health(endpoint(search.tei_rerank_url, "health"),
                                  headers=search._http.headers, auth=search._http.auth)

    async def probe_vllm(self):
        rag = self.local()[2]
        if rag is None:
            raise CheckFailure("CHECK_NOT_INITIALIZED")
        client = rag.client
        headers = {
            name: value
            for name, value in client.default_headers.items()
            if not isinstance(value, Omit)
        }
        await self.service_health(endpoint(client.base_url, "health", openai_root=True), headers=headers)
        base = str(client.base_url).rstrip("/")
        models_url = endpoint(base, "models" if urlsplit(base).path.endswith("/v1") else "v1/models")
        data = self.parse_json(await self.get(models_url, headers=headers))
        if (not isinstance(data, dict) or not isinstance(data.get("data"), list)
                or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in data["data"])):
            raise CheckFailure("CHECK_INVALID_RESPONSE")
        if rag.model_id not in {item["id"] for item in data["data"]}:
            raise CheckFailure("CHECK_RESOURCE_MISSING")

    async def probe_qdrant(self):
        search = self.search()
        client = search.qdrant_client
        # Inspect attributes only; never enter the shared SerializedClient lock.
        from .client_lifecycle import SerializedClient
        if isinstance(client, SerializedClient):
            client = client._client
        remote = client._client
        base = getattr(remote, "rest_uri", None)
        if base is None:
            raise CheckFailure("CHECK_CONFIG_MISMATCH")
        args = getattr(remote, "_rest_args", {})
        kwargs = dict(headers=getattr(remote, "_rest_headers", {}), auth=args.get("auth"))
        # A 404 on /readyz is explicitly unverifiable, never treated as healthy.
        await self.service_health(endpoint(base, "readyz"), qdrant_readiness=True, **kwargs)
        if not search.collection_name:
            raise CheckFailure("CHECK_CONFIG_MISMATCH")
        data = self.parse_json(await self.get(endpoint(base, "collections/" + quote(search.collection_name, safe="")),
                                               resource=True, **kwargs))
        try:
            if data["status"] != "ok":
                raise CheckFailure("CHECK_UNHEALTHY")
            info = data["result"]
            if info["status"] == "red":
                raise CheckFailure("CHECK_UNHEALTHY")
            # Active query_points does not request indexed_only or
            # prevent_unoptimized: grey permits full scans of unindexed data.
            if info["status"] not in {"green", "yellow", "grey"}:
                raise CheckFailure("CHECK_INVALID_RESPONSE")
            vectors = info["config"]["params"]["vectors"]
        except (KeyError, TypeError):
            raise CheckFailure("CHECK_INVALID_RESPONSE") from None
        if not isinstance(vectors, dict):
            raise CheckFailure("CHECK_INVALID_RESPONSE")
        # query_points passes no `using`: only the unnamed dense vector works.
        if "size" not in vectors:
            raise CheckFailure("CHECK_CONFIG_MISMATCH")
        if type(vectors["size"]) is not int or vectors["size"] <= 0:
            raise CheckFailure("CHECK_INVALID_RESPONSE")
        if vectors["size"] != search._expected_embedding_dimensions:
            raise CheckFailure("CHECK_CONFIG_MISMATCH")

    async def sync(self, name, operation):
        previous = self._sync_jobs.get(name)
        if previous is not None and not previous.done():
            raise CheckFailure("CHECK_TIMEOUT")
        if self._closed:
            raise CheckFailure("CHECK_NOT_INITIALIZED")
        # Exactly two possible jobs, one per component; no executor queue growth.
        def work():
            token = _HEALTH_IO.set(True)
            try:
                return operation()
            finally:
                _HEALTH_IO.reset(token)
        future = self.executor.submit(work)
        self._sync_jobs[name] = future
        # Consume errors from native work completing after its async deadline.
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        return await asyncio.shield(wrapped)

    async def probe_postgres(self):
        manager = getattr(self.app.state, "db_manager", None)
        if manager is None:
            raise CheckFailure("CHECK_NOT_INITIALIZED")
        params = dict(manager.conn_params)
        params["connect_timeout"] = 2
        params.update(keepalives=1, keepalives_idle=1, keepalives_interval=1,
                      keepalives_count=1, tcp_user_timeout=1000)
        params["options"] = (params.get("options", "") +
                             " -c statement_timeout=1000 -c lock_timeout=1000 -c default_transaction_read_only=on")

        def query():
            conn = psycopg2.connect(**params)
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    if cursor.fetchone() != (1,):
                        raise CheckFailure("CHECK_INVALID_RESPONSE")
            finally:
                try:
                    conn.rollback()
                finally:
                    conn.close()
        await self.sync("postgres", query)

    async def probe_minio(self):
        active = getattr(self.app.state, "health_minio_client", None)
        bucket = getattr(self.app.state, "health_minio_bucket", None)
        if active is None or not bucket:
            raise CheckFailure("CHECK_NOT_INITIALIZED")
        # Clone the startup client's actual target/credential provider. Do not
        # reuse its network pool or trigger SDK location discovery/retry/repair.
        base = active._base_url
        region = active._region_map.get(bucket) or base.region or "us-east-1"
        client = Minio(base.host, secure=base.is_https, region=region,
                       credentials=active._provider, http_client=self.pool)

        def exists():
            response = client._url_open("HEAD", region, bucket_name=bucket)
            try:
                if response.status != 200:
                    raise CheckFailure("CHECK_INVALID_RESPONSE")
            finally:
                response.release_conn()
        await self.sync("minio", exists)

    async def aclose(self):
        self._closed = True
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
            await asyncio.gather(self._refresh_task, return_exceptions=True)
        try:
            await self.http.aclose()
        finally:
            await self._close_native_resources()

    async def _close_native_resources(self):
        # Cancellation cannot kill threads. Finish native cleanup in the thread;
        # defer pool disposal if a job exceeds the bounded teardown wait.
        jobs = tuple(self._sync_jobs.values())
        if jobs:
            wrapped = [asyncio.wrap_future(job) for job in jobs]
            await asyncio.wait(wrapped, timeout=REFRESH_SECONDS)
            for future in wrapped:
                future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        self.executor.shutdown(wait=False, cancel_futures=True)
        minio_job = self._sync_jobs.get("minio")
        if minio_job is not None and not minio_job.done():
            minio_job.add_done_callback(lambda _: self.pool.clear())
        else:
            self.pool.clear()
