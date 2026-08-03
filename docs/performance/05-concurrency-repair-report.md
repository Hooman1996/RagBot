# P2 concurrency and resource-lifecycle repair report

Date: 2026-07-28

Base revision: `fada571` on `main`

External request deadline: 50 seconds

## Executive summary

This change implements the verified P2 concurrency and resource-lifecycle
repairs from reports 02 and 04 without changing LangGraph structure, query
rewrite/classification order, cache semantics, prompts, retrieval ordering, or
vLLM/TEI container configuration.

The active application now creates its TEI, vLLM, Qdrant, PostgreSQL startup,
and MinIO resources inside FastAPI lifespan rather than constructing Qdrant at
module import. TEI uses one persistent async client and one persistent sync
client per process; the sync client replaces knowledge-base request-scoped
client construction. All owned clients are closed in reverse dependency order,
and closed services reject later use.

Blocking PostgreSQL, Qdrant, pandas, filesystem, OCR, Parsivar, BM25, prompt
formatting, graph construction, and Torch classification work on the audited
paths now crosses one bounded `asyncio.to_thread` adapter. Database operations
create and dispose their psycopg2 connection inside the worker thread.
Transactional writes finish commit/rollback and connection cleanup before
cancellation is re-raised. Read-only work may finish after its waiter is
cancelled, but retains its concurrency slot until the worker ends.

A synthetic, dependency-free 20-request benchmark of the verified blocking
metadata boundary reduced batch elapsed time from 0.4289 seconds to 0.0764
seconds, reduced maximum observed event-loop lag from 0.2384 seconds to 0.0008
seconds, and increased synthetic throughput from 46.63 to 261.71 requests per
second. This is evidence for the isolated mocked boundary only, not a staging
or production latency claim.

The full isolated suite passes 19 tests. No live staging or production request,
load test, database mutation, TEI/vLLM inference, Qdrant request, or MinIO
operation was performed.

## Audit contract

| Item | Recorded value |
|---|---|
| Audit question | Repair verified P2 concurrency, blocking-I/O, timeout, cancellation, error-boundary, and lifecycle defects |
| Primary workload | Mocked `AgentService.process_message` calls representing independent `/api/query` turns |
| Additional paths inspected/repaired | Mobile talk/history/feedback/satisfaction, session APIs, mass answer, OCR, analytics, KB TEI embedding |
| Source identity | Base revision `fada571`, branch `main`; worktree clean before this task |
| External deadline | 50 seconds |
| Staging hardware | One NVIDIA RTX 5880 Ada Generation GPU with 48 GB VRAM |
| Production hardware | Two NVIDIA L4 GPUs with 24 GB each; no result in this report is extrapolated to production |
| Model identifiers/service versions | Unknown in this checkout; no live service was contacted |
| Configuration fingerprint | Unknown for runtime; sensitive environment files were not printed |
| Synthetic dataset | 20 unique integer request IDs and content-free `"synthetic"` input |
| Arrival pattern | Closed-loop simultaneous burst of 20 tasks |
| Mocked blocking work | One 20 ms metadata read and one 20 ms async graph step per request |
| Warm-up | None |
| Runs | One retained comparable legacy/repaired run; earlier development repeats showed the same direction |
| Pass criteria | 20 results, request overlap, responsive heartbeat, bounded worker count, isolated failures, correct cancellation cleanup, one shared client, no post-close use |
| Cold/warm classification | In-process synthetic, neither a service cold start nor a warmed model-serving run |
| Background workload | Unknown; no staging workload was generated |
| GPU sharing/contention | Unknown and unmeasured |

## Scope boundaries honored

- No graph node, edge, or routing-table change.
- No rewrite/classification reordering.
- No new cache and no cache policy/invalidation change. The existing BM25 cache
  is only protected against concurrent mutation.
- No prompt, model output, retrieval candidate, Qdrant search-parameter, or
  answer-context behavior change.
- No vLLM or TEI container configuration change.
- No production infrastructure or endpoint access.

## Implemented repairs

### Persistent client reuse and lifespan ownership

| Resource | Construction and reuse | Shutdown |
|---|---|---|
| TEI async HTTPX | One process-scoped lifespan client shared by embedding and reranking; limits 32 total/16 keep-alive | `aclose()` during lifespan teardown |
| TEI sync HTTPX | One process-scoped lifespan client shared by synchronous KB worker routes; HTTPX sync client supports cross-thread pooling | `close()` in the bounded worker runner |
| vLLM OpenAI client | One lifespan `AsyncOpenAI` with an injected persistent HTTPX transport; retries disabled | `AsyncOpenAI.close()` closes its transport |
| Qdrant | Created by startup connection initialization, then reused by RAG and KB routes; no import-time client remains | Serialized wrapper closes the underlying client exactly once |
| PostgreSQL request operations | No shared request cursor/connection; each `DatabaseManager` operation creates, uses, commits/rolls back, and closes a connection in one worker | Per-operation `finally`; startup probe connection closed at shutdown |
| MinIO | Created once during startup; not on the audited request critical path | Underlying urllib3 pool is cleared during shutdown |
| Bounded worker runner | One lifespan instance shared across application services | Stops admission and drains active workers |

The Qdrant client is wrapped in `SerializedClient`. Repository/runtime evidence
did not establish the installed client's cross-thread guarantees, so only one
method enters that shared client at a time. This is conservative correctness,
not a claimed Qdrant throughput optimization.

### Explicit timeout and pool policy

| Dependency | Connect | Read | Write | Pool acquire | Other |
|---|---:|---:|---:|---:|---|
| TEI HTTPX async/sync | 3 s | 15 s | 5 s | 3 s | 32 total connections, 16 keep-alive, 30 s idle expiry |
| vLLM HTTPX/OpenAI | 3 s | 45 s | 5 s | 3 s | 32 total connections, 16 keep-alive, 30 s idle expiry, SDK retries disabled |
| PostgreSQL | 5 s | Server statement timeout 10 s | Server statement timeout 10 s | Not applicable; active path still uses per-operation connections | Lock timeout 3 s |
| Qdrant sync SDK | SDK total timeout 10 s | SDK total timeout | SDK total timeout | Serialized admission | Phase-specific Qdrant timeouts are not exposed by the verified constructor contract |
| Outer AI request | — | — | — | Request admission 2 s | Total request deadline 50 s |

The HTTP phase budgets are deliberately below the external 50-second deadline.
No claim is made that the chosen values are optimal for staging; that requires
live percentile data and is a separate single-variable experiment.

### Bounded concurrency

- AI request admission: 32 concurrent web/mobile/mass-answer operations per
  process, configurable with `REQUEST_CONCURRENCY_LIMIT`.
- Admission wait: 2 seconds, configurable with
  `REQUEST_ADMISSION_TIMEOUT_SECONDS`; exhaustion maps to `SERVICE_BUSY`.
- Blocking worker admission: 16 operations per process, configurable with
  `BLOCKING_CONCURRENCY_LIMIT`.
- Qdrant: async semaphore plus a serialized sync-client wrapper.
- Parsivar tokenizer/stemmer and existing BM25 cache: explicit locks.
- Torch classifier: serialized read-only inference lock.
- OCR model: serialized inference lock.
- Same-session agent-state updates: existing per-session async lock retained.

### Cancellation semantics

Native async HTTP calls, semaphore acquisition, graph invocation, and model
calls propagate `CancelledError`; no request code catches it as an ordinary
failure.

Python cannot forcibly stop a callable already executing in a worker thread.
The bounded runner therefore uses these explicit policies:

1. A cancelled read-only waiter re-raises cancellation immediately. Its worker
   continues to completion, retains its slot, and has its result/exception
   consumed.
2. A cancelled transactional write waits for the worker's local transaction to
   commit or roll back and for its connection to close, then re-raises
   cancellation.
3. Shutdown stops new admission and drains active workers before clients close.
4. Database statement/lock timeouts bound how long a cancelled DB write can
   remain inside PostgreSQL.

This prevents connection or transaction objects from escaping in an
indeterminate state. It does not pretend that Python thread cancellation can
abort an in-flight network syscall.

### API-boundary error translation

The application-wide `ServiceError` handler emits the existing banking-shaped
fields (`errorCode`, `errorDesc`, and `errorDetails`) without dependency
payloads, prompts, credentials, customer data, or raw exception text.

| Internal failure | HTTP status | Stable code |
|---|---:|---|
| TEI/vLLM/Qdrant/dependency timeout | 504 | `DEPENDENCY_TIMEOUT` |
| PostgreSQL, TEI, vLLM, or Qdrant unavailable | 503 | `DEPENDENCY_UNAVAILABLE` |
| Malformed embedding/reranking response | 502 | `DEPENDENCY_INVALID_RESPONSE` |
| Request admission exhausted | 503 | `SERVICE_BUSY` |

Mobile's broad fallback now re-raises `HTTPException` and `ServiceError`
unchanged and explicitly propagates cancellation. Unknown internal errors
remain generic 500 responses without raw exception content.

Embedding responses are additionally validated as one non-empty batch
containing exactly 1024 finite numeric values. Reranker results must be a list
of unique, in-range integer indexes with finite numeric scores.

## `asyncio.to_thread` operation audit

All active-path calls below go through `BoundedBlockingRunner.run`, whose only
execution boundary is `asyncio.to_thread`.

| Operation/group | Why blocking | Object thread-safety | Connection created inside worker? | Exceptions and cancellation |
|---|---|---|---|---|
| Startup `DatabaseConnections.connect_all` | psycopg2, MinIO, and Qdrant synchronous network calls; bucket/collection checks | Startup is single-threaded; created clients are not concurrently entered during initialization | Yes, PostgreSQL and SDK transports are created in the startup worker | Startup exception aborts readiness; cancellation waits for cleanup |
| `DatabaseManager.init_db` and all CRUD/session/history/feedback/ticket calls | psycopg2 connect, SQL execution, commit/rollback | Manager stores immutable connection parameters; no cursor or connection is shared | Yes, every `_execute` opens its connection in the worker and closes it in `finally` | psycopg2 becomes `ServiceUnavailableError`; writes finish cleanup before cancellation propagates |
| Authentication | psycopg2 plus bcrypt CPU work | Authentication service stores the manager only; cursor/connection are local | Yes | DB exceptions translate to 503; transaction rolls back and closes; cancellation waits |
| Analytics | Multiple synchronous cursor calls and result materialization | Entire request owns one local connection/cursor in one worker | Yes | Generic output is 500 without SQL/raw error; connection closes in `finally`; cancellation is read-only policy |
| Qdrant `query_points` | Synchronous SDK network call | Installed-version guarantee unknown; shared client is serialized | No; persistent client was created at startup | Timeout/unavailable translation; cancellation propagates while worker retains its slot |
| Parsivar normalize/tokenize/stem and BM25 build/score | CPU-heavy Python/native NLP and corpus scoring | Normalizer, tokenizer/stemmer, and cache mutations are lock-protected | Database chunk fetches within cache build create their own worker-local connections | Exceptions propagate; cancellation does not corrupt shared cache because locks and slot remain until worker finishes |
| Context/related-question/history formatting | Regex, sorting, XML/string construction | Input state is request-local and the shared RAG object is read-only for these calls | No | Exceptions propagate; read-only cancellation policy |
| Torch classifier construction and inference | Filesystem checkpoint load, tensor transfer, CPU/GPU forward pass | Model is shared read-only; all forward passes are serialized by a lock | No | Exceptions propagate; async TEI cancellation remains native; thread inference retains its slot |
| RAG system, graph, text processor, OCR construction | Filesystem/model initialization and CPU object construction | Construction occurs before app readiness; published only after success | No request connection; injected clients already exist | Failure aborts startup and teardown closes every resource created so far |
| OCR file write/inference/cleanup | Filesystem I/O and CPU/GPU OCR | Shared OCR model protected by one inference lock | No | Temporary directory always removed; generic safe 500; cancelled work retains its slot |
| pandas CSV/Excel parse and output | CPU parsing/serialization and synchronous filesystem I/O | DataFrame is request-local | No | Parse maps to safe 400; output write finishes before cancellation propagates |
| Persistent sync TEI client close, DB/MinIO/Qdrant close | Synchronous socket/pool teardown | Shutdown occurs after request drain; runner prevents new work | No | Cleanup attempts continue across individual close failures; normal shutdown reports aggregate failure |

Operations deliberately not offloaded include small dictionary/list updates,
Pydantic/FastAPI serialization, category selection, and semaphore bookkeeping.
They are not established CPU bottlenecks.

## Concurrency test coverage

`tests/test_p2_concurrency.py` issues at least 20 simultaneous mocked requests
in each relevant concurrency scenario and verifies:

- a heartbeat continues while 20 blocking calls execute in worker threads;
- at least ten independent operations overlap in the 20-worker case;
- the configured bound is exactly four in the bounded test;
- one synthetic failure leaves the other 19 results intact;
- one process-scoped client services all 20 calls and closes exactly once;
- both client and runner reject use after close;
- cancellation of a database-like write waits for transaction cleanup;
- an unrelated request completes when its peer fails or is cancelled;
- lifecycle source owns and closes every relevant client;
- phase-specific HTTP and PostgreSQL timeouts are present;
- stable error codes are registered at the FastAPI boundary.

The test interpreter is Python 3.14.6. Its default asyncio executor accepts
work but does not deliver completion callbacks, so `asyncio.to_thread` itself
hangs in this environment. The tests replace only that boundary with a
dedicated real `ThreadPoolExecutor` plus async polling. Blocking work still runs
on real worker threads, while production code continues to call
`asyncio.to_thread`.

## Controlled benchmark

Commands:

```bash
python3 benchmarks/p2_mock_concurrency.py --mode legacy
python3 benchmarks/p2_mock_concurrency.py --mode repaired
```

The legacy mode reproduces the verified event-loop metadata read. Repaired mode
uses the bounded worker boundary. Both use the same synthetic inputs, 20-task
burst, 20 ms metadata delay, 20 ms async graph delay, process, interpreter, and
measurement code. Durations use `time.perf_counter()`.

| Metric | Legacy | Repaired | Change |
|---|---:|---:|---:|
| Requests | 20 | 20 | Same |
| Batch elapsed | 0.4289 s | 0.0764 s | -82.2% |
| p50 request latency | 0.4086 s | 0.0496 s | -87.9% |
| p95 request latency | 0.4272 s | 0.0707 s | -83.5% |
| p99 request latency | 0.4272 s | 0.0707 s | -83.5%; unstable at n=20 |
| Maximum event-loop lag | 0.2384 s | 0.0008 s | -99.7% |
| Throughput | 46.63 req/s | 261.71 req/s | +461.3% |
| Success/timeout/error | 20/0/0 | 20/0/0 | Same |

| Experiment | Major variable | Baseline | After | p50 | p95 | p99 | Throughput | Timeout rate | Quality | Decision |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| P2-1 | Metadata read executes on loop vs bounded worker | 0.4289 s batch | 0.0764 s batch | 0.4086 → 0.0496 s | 0.4272 → 0.0707 s | 0.4272 → 0.0707 s, unstable | 46.63 → 261.71 req/s | 0% → 0% | Not model-affecting | Keep |
| P2-2 | Process-scoped client reuse/lifecycle | Per-call sync TEI construction and unclosed async clients found statically | One shared client per mode; 20/20 reuse test; close-once and post-close rejection pass | Not measured | Not measured | Not measured | Not claimed | Not applicable | Not model-affecting | Keep as correctness repair |
| P2-3 | Bounded worker/request admission | No common bound | 20-call test peaks at configured 4/4 | Not measured | Not measured | Not measured | Not claimed | Admission behavior tested | Not model-affecting | Keep as safety repair |

Only P2-1 is presented as a measured performance improvement. P2-2 and P2-3
are correctness/resource-safety changes and carry no unmeasured latency claim.

## Validation results

Run from `/root/projects/faq`.

| Command | Result |
|---|---|
| `python3 -m compileall -q .` | Passed |
| `python3 -m unittest discover -s tests -v` | Passed, 19 tests |
| `python3 -m unittest discover -s tests -q` | Passed, 19 tests |
| `git diff --check` | Passed |
| `python3 benchmarks/p2_mock_concurrency.py --mode legacy` | Passed; metrics recorded above |
| `python3 benchmarks/p2_mock_concurrency.py --mode repaired` | Passed; metrics recorded above |
| `python3 -c 'import main; assert main.app is not None'` | Blocked: `ModuleNotFoundError: pandas` |

The suite emits one pre-existing `datetime.utcnow()` deprecation warning.

## Tests deliberately not run

- Live TEI, vLLM, Qdrant, PostgreSQL, or MinIO calls.
- `python3 test_qdrant.py`, because its target is not proven isolated staging.
- State-changing knowledge-base or API requests.
- Staging/production load, stress, soak, or fault tests.
- Retrieval and answer-quality suites, because no repository command or dataset
  exists. This patch does not intentionally change model behavior.
- Full application lifespan integration, because the audit interpreter lacks
  pandas and other application dependencies and the repository has no canonical
  Python dependency manifest.

## Remaining limitations and follow-up experiments

1. The synthetic benchmark isolates Python scheduling and does not include real
   downstream queueing, GPU work, network latency, database locks, or payload
   sizes.
2. P99 is statistically unstable at 20 samples.
3. PostgreSQL still creates one connection per operation. Replacing it with a
   bounded pool is a separate major variable requiring its own baseline.
4. Qdrant is deliberately serialized until the deployed client version and
   transport thread-safety are verified. An async Qdrant client or persistent
   client pool is a separate experiment.
5. Request and HTTP pool limits are defaults based on the external deadline,
   not staging capacity measurements. Tune only with controlled staging load.
6. `asyncio.to_thread` completion is broken in this audit interpreter. The
   deployment interpreter and executor must be validated before rollout.
7. The existing per-session lock remains process-local; multi-worker safety
   still requires database-backed versioning or locking.
8. MinIO is startup-only for the audited query path and was not optimized as a
   latency component.
9. The existing BM25 cache still lacks mutation invalidation; its behavior was
   intentionally not changed in this batch.

## Files changed

- `agent_graph.py`
- `agent_service.py`
- `benchmarks/p2_mock_concurrency.py`
- `env.example`
- `intent_classifier.py`
- `main.py`
- `mobile_api.py`
- `new_architecture/app/services/authentication/authentication.py`
- `new_architecture/app/services/db_connection/connection.py`
- `new_architecture/app/services/history/database.py`
- `tests/test_p0_p1_repairs.py`
- `tests/test_p2_concurrency.py`
- `utils/RagSystem.py`
- `utils/__init__.py`
- `utils/client_lifecycle.py`
- `utils/concurrency.py`
- `utils/persian_hybrid_search.py`
- `utils/service_errors.py`
- `docs/performance/05-concurrency-repair-report.md`

## Rollback

After committing, revert the P2 repair commit with:

```bash
git revert <p2-concurrency-repair-commit>
```

Before committing, preserve and reverse only this reviewed patch:

```bash
git diff --binary > /tmp/faq-p2-concurrency-repair.patch
git apply --check -R /tmp/faq-p2-concurrency-repair.patch
git apply -R /tmp/faq-p2-concurrency-repair.patch
```

Review `git status --short` before rollback so unrelated work is not included.
