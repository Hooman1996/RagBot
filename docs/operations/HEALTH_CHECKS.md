# RagBot monitoring health endpoints

These endpoints report health only. This change enables no automatic operational
response: no stop/restart, shutdown initiation, traffic removal/redirect, admission
change, repair, resource creation, scheduler, or deployment. Dependency failures
and health HTTP 503 responses do not change `app.state.ready`, limiters, or chatbot
route behavior. The production team owns polling, alerts, routing, and actions.

## Endpoints and JSON contracts

Only GET is public for each of the three exact new paths. Every new response is
JSON and has `Cache-Control: no-store`. No prefix-wide authentication exemption
exists; other paths, trailing-slash variants, and other methods keep their browser
authentication policy. Probes do not perform browser user lookup, login, role
checks, CSRF processing, or chatbot admission acquisition.

`GET /api/health` is the **legacy shallow health endpoint**. Its successful HTTP
200 and existing response are unchanged:

```json
{
  "status": "healthy",
  "system_initialized": true,
  "documents_available": 0,
  "ocr_available": false
}
```

`system_initialized` means the legacy RAG object exists; `documents_available` is
the existing cached document-list length; `ocr_available` means the existing OCR
object exists. This endpoint does not check dependencies or certify readiness.
Zero documents is not a new readiness failure.

`GET /api/health/live` always responds HTTP 200 when its handler can run:

```json
{"status": "alive", "code": "HEALTH_ALIVE"}
```

It performs no external calls, database lookup, model inference, checkpoint
hashing, resource allocation, or admission acquisition. It means HTTP is
responsive, not that dependencies are available. An unreachable/dead process or
failed startup can produce **no HTTP response**. No synthetic application response
is provided for that case; ordinary ASGI lifespan failure can prevent serving.

`GET /api/health/ready` returns this summary (example values):

```json
{
  "status": "healthy",
  "code": "HEALTH_OK",
  "ready": true,
  "checked_at": "2026-10-10T09:00:00.000000Z",
  "cache_age_ms": 0,
  "failed_components": [],
  "warning_components": []
}
```

`checked_at` is the UTC ISO-8601 completion timestamp of the dependency snapshot.
`cache_age_ms` is its nonnegative age in whole milliseconds, measured using
monotonic time. A fresh response will normally have age zero; scheduling can add a
few milliseconds. State-only checks are reevaluated at response time without
changing the timestamp of the external snapshot. `failed_components` lists
required components that are down/unestablished; `warning_components` lists down
auxiliary components. Intentionally disabled OCR appears in neither list.

| Condition | HTTP | status | code | ready |
| --- | --- | --- | --- | --- |
| All required pass; auxiliary pass or optional feature disabled | 200 | healthy | HEALTH_OK | true |
| Required pass; MinIO fails | 200 | degraded | HEALTH_DEGRADED | true |
| Any required fails or cannot be established | 503 | not_ready | HEALTH_NOT_READY | false |
| Initialization incomplete, handler reachable | 503 | starting | HEALTH_STARTING | false |
| Shutdown begun, handler reachable | 503 | stopping | HEALTH_STOPPING | false |
| Unexpected coordinator failure | 500 | error | HEALTH_CHECK_ERROR | false |

Dependency exceptions are ordinary component failures. Upstream statuses are not
forwarded: e.g. a required TEI HTTP 500 produces RagBot readiness HTTP 503. A
coordinator error discards cached success. Lifecycle bookkeeping distinguishes
starting from stopping, checks lifecycle before cache use and after a refresh,
and never returns cached success during shutdown.

`GET /api/health/details` has exactly the same summary, readiness decision and
HTTP status as `/ready` for the shared snapshot, plus a `checks` object. Every
component listed below always has a result with **only** these four fields:

```json
{
  "status": "up",
  "required": true,
  "code": "CHECK_OK",
  "latency_ms": 8
}
```

`status` is `up`, `down`, or `disabled`; `required` is boolean; `code` is one of the
codes below; `latency_ms` is a nonnegative integer duration in milliseconds.
State-only and unestablished lifecycle results have zero latency. `disabled` is
used only for absent optional OCR. Startup/shutdown/error snapshots mark
unestablished dependencies `down`, never `disabled`. Requiredness is fixed.

No dependency URLs/IPs, credentials, connection strings, bucket/collection names,
model paths/IDs, checkpoint hashes, raw errors, response bodies, stack traces,
documents, questions, answers, or customer identifiers are returned. Production
can restrict diagnostic access at its existing proxy/network boundary; this
change makes no proxy edits and opens no ports.

## Component checks and troubleshooting

| Component | Required? | Check | What to investigate on failure |
| --- | --- | --- | --- |
| application | Yes | State only: existing ready flag; answering service; active agent and compiled graph; RAG/search/client/runner objects not known closed | Lifecycle completion and existing application startup logs; missing graph/client or closed runner |
| postgres | Yes | Dedicated short-lived connection to active `DatabaseManager.conn_params`; execute and validate `SELECT 1`; rollback and close | Target accessibility, configured credentials, connection/statement deadline, connection exhaustion |
| qdrant | Yes | Isolated GET readiness and configured collection metadata; verify unnamed dense vector and active search engine's expected dimension | Readiness support/proxy path, authentication, absent collection, red collection status, named-vector layout or dimension mismatch |
| tei_embedding | Yes | Active search engine embedding URL: GET `/health` | Service accessibility, authorization, model-service health, malformed/proxy HTML responses |
| tei_reranker | Yes | Active search engine reranking URL: GET `/health` | Same checks as embedding; related-question reranking still uses this dependency even if answer-context reranking is disabled |
| vllm | Yes | Active OpenAI client target: GET `/health`, then `/v1/models`; verify active `RAGSystem.model_id` exists | Service health, configured base prefix/authentication, served model IDs versus active model |
| intent_classifier | Yes | State only: active classifier's load-time `_checkpoint_loaded` validation flag | Existing checkpoint construction/metadata/hash validation and loaded classifier; no reload/hash in probes |
| minio | No, auxiliary after startup | Isolated signed HEAD bucket-existence request using startup client's actual target, credential provider and cached region | Accessibility/authentication, missing bucket, region/configuration mismatch, permissions |
| ocr | No, optional | State only: whether optional OCR initialized | Absent OCR yields `disabled`/`CHECK_DISABLED`; use existing OCR diagnostics if OCR is needed |

PostgreSQL uses the actual history database target, not the unused SQLAlchemy
pool or long-lived startup connection. Its connection parameters are copied;
health does not mutate business parameters. It overrides `connect_timeout=2`,
`statement_timeout=1000`, `lock_timeout=1000`, and requests read-only transactions.
The isolated connection also enables TCP keepalives with one-second idle/interval,
one failed probe, and a 1000 ms TCP user timeout to bound stalled socket detection
on the supported Linux/libpq runtime. OS DNS and native cleanup can still outlast
the async deadline; submission remains bounded as described below.
No commit, schema setup, migration, or application write executes. This tests
connectivity and simple query execution, **not all application write permissions**.

A checkpoint is required for the production-readiness *report*, even if startup
configuration permits an unloaded classifier. Object existence alone does not
pass. This does not change `INTENT_CLASSIFIER_REQUIRED`, startup validation, or
classification behavior.

MinIO remains an existing startup prerequisite: startup may currently create a
bucket or fail before HTTP is served. Health does not refactor that policy. Once
running, MinIO failures only degrade the report, retaining `ready: true` when
required components pass. Health sends one signed HEAD with no SDK region
discovery, retries, or redirects, and never creates a bucket/object. The installed
SDK's low-level signed request method is used to avoid its automatic retry logic;
SDK upgrades need the offline regression tests. Reviewed clients: qdrant-client
1.16.2, MinIO 7.2.20, httpx 0.28.1, psycopg2-binary 2.9.11. The SDK target/auth
attributes are covered using installed Qdrant and MinIO objects. Service-server
versions were not observed live; the supported readiness protocol is the
documented Qdrant `/readyz` contract, not a claimed production-version validation.

## Stable component codes

| Code | Meaning |
| --- | --- |
| CHECK_OK | Check passed |
| CHECK_TIMEOUT | Async deadline exceeded or structured native/upstream timeout |
| CHECK_UNREACHABLE | Connection could not be established |
| CHECK_AUTH_FAILED | Structured authentication rejection (HTTP 401/403, PostgreSQL SQLSTATE class 28/type, or S3 auth code) |
| CHECK_UNHEALTHY | Explicit unhealthy/server-failure status |
| CHECK_RESOURCE_MISSING | Configured collection/bucket missing, or configured vLLM model absent |
| CHECK_CONFIG_MISMATCH | Observed layout/dimension/region or URL configuration conflicts with application requirements |
| CHECK_NOT_INITIALIZED | Required local component/checkpoint absent, lifecycle incomplete, or dependency target unavailable locally |
| CHECK_INVALID_RESPONSE | Malformed, oversized, unsupported, redirected, or unverifiable response |
| CHECK_DISABLED | Optional OCR absent by installation/initialization |
| CHECK_ERROR | Other component failure |

Mapping uses exception types, SQLSTATE, S3 codes, and HTTP statuses, never raw
message matching. libpq can omit SQLSTATE for connection-time errors (including
some password rejections or timeouts); such undifferentiated OperationalErrors
are `CHECK_UNREACHABLE`, rather than a guessed diagnosis. Use existing protected
service logs for precise diagnosis. Required results are all retained even when
several components fail. Unsupported health APIs do not count as successful.

## URL handling, upstream protocol, and authentication

Health reads active runtime targets, not an independent set of environment
values. Qdrant's resolved REST URI, prefix, headers, and configured HTTP auth are
read without calling its serialized shared client. The active search collection
and dimension are used. TEI paths append `/health` to the active search-engine
base prefix and reuse its configured HTTP headers/auth.

For vLLM, only a terminal `/v1` is removed to derive health. For example,
`https://example.invalid/proxy/v1/` produces `/proxy/health` and
`/proxy/v1/models`, preserving HTTPS, authority and proxy prefix. The active
OpenAI client's default headers (including applicable credentials) are used.
A base without `/v1` gets health at its prefix and model listing at
`<prefix>/v1/models`. Redirects are disabled. These example hosts are illustrative
and never appear in actual health responses.

The expected TEI/vLLM health response is an empty HTTP 200. Qdrant `/readyz`
requires `all shards are ready`, as plain text or a JSON string. Other bodies,
including Qdrant liveness text, empty responses, HTML, malformed JSON, and unknown
objects, are unverifiable. Structured explicit unhealthy results fail even if
an intermediary changes their status to 200. HTTP 401/403, 408/504, and 5xx map
to authentication failure, timeout, and unhealthy respectively.

Qdrant collection `green`, `yellow`, and `grey` pass when readiness and vector
metadata pass. Grey means optimizations are pending/paused, and can increase
latency; it does not establish inability to serve queries. The active search
uses unnamed vectors and does not enable `indexed_only`/`prevent_unoptimized`:
unindexed segments can be scanned. Red represents an engine error and fails.
Unknown statuses fail verification. This monitoring does not certify query
latency, indexing completeness, or answer quality, and never triggers optimization.
If search restrictions change, review this policy before relying on grey results.
See the official [collection statuses](https://qdrant.tech/documentation/manage-data/collections/)
and [grey-status query behavior](https://qdrant.tech/documentation/faq/#why-is-my-collection-in-grey-status).

Qdrant `/readyz` support on the deployed server was **not established by a live
probe** during this offline implementation. A 404 is reported as
`CHECK_INVALID_RESPONSE`, indicating an unsupported readiness route or incorrect
proxy prefix; it is never silently accepted. Operators should verify the server
version and route support. For older servers exposing `/healthz`, that documented
read-only liveness check plus collection metadata is a useful diagnostic
alternative, but does not establish the same readiness semantics. This code does
not silently fall back to it. Adopting a weaker alternative requires a reviewed
monitoring change. No collection creation, point counting, payload inspection,
vector search, embeddings, reranking, completions, rewriting, or graph execution
is performed by probes.

Upstream references: [Qdrant monitoring](https://qdrant.tech/documentation/ops-monitoring/monitoring/),
[Qdrant readiness API](https://api.qdrant.tech/master/api-reference/service/readyz),
[TEI health implementation](https://github.com/huggingface/text-embeddings-inference/blob/main/router/src/http/server.rs),
[vLLM serving endpoints](https://docs.vllm.ai/en/latest/serving/online_serving/).

## Deadlines, cache, and resource bounds

Dependency work runs concurrently on demand. Fixed initial defaults are:

- Two seconds for each entire component, including its multiple HTTP requests.
- Three seconds for the overall dependency refresh.
- Five seconds of snapshot reuse, shared between `/ready` and `/details`.
- One in-flight refresh per application worker. Caller cancellation is shielded
  from the shared refresh; cancelling one request does not cancel others' work.
- A separate reusable HTTP client with at most six connections and six keepalive
  connections, explicit two-second I/O timeouts, zero retries, no redirects, and
  a 64 KiB response-body limit.
- A separate executor with two health threads, at most one PostgreSQL job and one
  MinIO job outstanding. No health work uses business blocking capacity/admission.
- A separate MinIO pool with one pooled connection, no retries/redirects, and
  total two-second, connect one-second, and read one-second network timeouts.

Snapshots are complete immutable values; HTTP response dictionaries are detached.
Expiration and age use monotonic time. Expired success is never served while a
refresh runs or after it fails. Missing or timed-out required results fail the
report. Local/lifecycle checks are reevaluated before serving cached results.
There is no periodic task, monitoring loop, or scheduler.

Cancellation cannot terminate a Python thread or necessarily interrupt OS DNS.
Native connection/statement/network timeouts complement the async deadlines.
If a thread outlasts its async deadline, that component fails and another job for
it is not submitted while the thread remains outstanding. Threads keep ownership
of rollback/connection cleanup. Thus repeated timeouts cannot accumulate threads
or queued probe submissions. Normal lifespan teardown cancels health refreshes,
closes only health HTTP resources, waits up to three seconds for native jobs,
and defers MinIO pool disposal to its completing worker if necessary. It does
not initiate shutdown or close any chatbot-owned client.

Caches are worker-local. Multiple ASGI workers can report different snapshots;
load-balanced polling is not a guarantee of observing every worker. Liveness
remains independent of slow dependency checks.

Health-route request/response bodies are omitted by the existing HTTP logging
policy. Health SDK I/O logs are suppressed in health-only execution contexts so
URLs/headers/errors do not escape through debug logging. Component state-change
logs contain fixed `component`, `status`, and `code` fields. Initial successful
checks and repeated unchanged polling do not emit component-success logs. Normal
HTTP request/response metadata logging remains in place.

## Read-only monitoring integration

Use the service's configured `API_PORT`; **7000 is only the documented default**.
Do not source private `.env` files into diagnostic output. If API_PORT is already
available in the operator's shell, these examples use it:

```bash
curl --silent --show-error --max-time 5 --include "http://127.0.0.1:${API_PORT:-7000}/api/health/live"
curl --silent --show-error --max-time 5 --include "http://127.0.0.1:${API_PORT:-7000}/api/health/ready"
curl --silent --show-error --max-time 5 --include "http://127.0.0.1:${API_PORT:-7000}/api/health/details"
```

These are examples for the production team; no server was started/restarted and
these curl commands were not executed during local verification. Curl without
`--fail` can exit successfully after receiving HTTP 503; monitoring must inspect
the HTTP status, overall code, and component lists, and distinguish transport
failure from an application report.

Example policy to configure in the team's **existing monitoring system**:

- Poll every ten seconds.
- Alert after three consecutive failures.
- Consider recovery after two consecutive successes.
- Initially enable monitoring/alerts only; track MinIO degradation separately.
- Configure no restart, shutdown, admission action, or traffic removal.

Readiness failure is a report. Connecting it later to automatic traffic removal
is a separate operational decision. This change contains no deployment manifest,
cron job, systemd unit, restart script, or active polling configuration.

Health is not an answer-quality test, retrieval evaluation, comprehensive
write-permission audit, GPU capacity benchmark, or end-to-end banking transaction
test. Local verification uses mocked dependencies; deployed API compatibility,
network access, credentials, and production capacity still require the team's
read-only operational validation.

## Reproducible offline verification

Activate the existing environment; no environment installation is required:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python -m pytest -p tests.offline_guard tests/test_health_checks.py -q
python -m pytest -p tests.offline_guard tests/test_web_auth.py tests/test_web_permissions.py -q
python -m pytest -p tests.offline_guard tests/test_http_logging_middleware.py tests/test_background_logging.py tests/test_structured_logging.py -q
python -m pytest -p tests.offline_guard tests/test_answering_service.py tests/test_request_admission.py tests/test_p2_concurrency.py tests/test_vllm_error_translation.py tests/test_tei_embedding_policy.py tests/test_answer_context_reranking.py -q
python -m pytest -p tests.offline_guard tests -m 'not integration and not artifact' -q -o faulthandler_timeout=60
python -m compileall -q main.py web_auth.py utils/health_checks.py utils/http_logging_middleware.py tests
git diff --check
```

Use the existing installation's conda initialization path if it differs. The
tracked guard blocks real socket connections, DNS resolution, and psycopg2
connections; realistic mocks override individual dependency boundaries. It does
not skip tests. No hidden temporary plugins, private environment files, or live
services are required for offline verification. The managed sandbox prevented
cross-thread asyncio wakeups even in a minimal dependency-free program; running
these guarded tests outside that sandbox resolves TestClient/executor hangs.
No workaround, scheduler, or thread monkeypatch was added to application code.

`integration` identifies the seven analytics SQL cases and the served analytics
SQL/API/frontend case: these require a separately authorized development PostgreSQL
instance, use synthetic read-only CTEs, and are not offline unit tests. `artifact`
identifies private training-dataset integrity and historical/production weight
audits. These files are unavailable in a clean checkout and are not fabricated.
The original artifact audits remain runnable explicitly. Synthetic temporary
checkpoints independently exercise strict loading, metadata/hash/threshold
validation, deterministic routing, and public preprocessing offline. The FAQ
reader has standalone coverage without a dataset prerequisite. Authentication,
permissions, logging, and chatbot regression suites are fully included.

The original report contained **14 failures and 14 setup errors**, not 17
failures. An isolated unchanged baseline reproduced all 28 IDs. The sanitized
[28-case failure matrix](HEALTH_VERIFICATION.md) records causes, baseline/health
comparisons, fixture repairs, and unavailable artifact checks. No prompt,
retrieval, authentication, or production classifier policy was changed to fix
these tests. No live inference, load test, deployment, integration-service check,
or production validation is claimed.

Final command results and merged-tree verification are recorded in
[HEALTH_VERIFICATION.md](HEALTH_VERIFICATION.md).
