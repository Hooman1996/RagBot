# Request admission audit

Audit date: 2026-08-05  
Repository: `/root/projects/faq` at `c57b67e8770374cfd8a1f4db4ce97d639914b51d`  
Primary endpoint: `POST /api/mobile/v1/talk`  
External deadline: 50 seconds

This document freezes the read-only audit completed before implementation
changes. No service was restarted, no container was changed, no live load was
sent, and the active `.env` was not modified or printed.

The subsequent implementation and verification are documented in
[`20-request-admission-repair-report.md`](20-request-admission-repair-report.md).

## Executive conclusion

The checked-in semaphore implementation does release permits correctly. A
deterministic isolated run using the current `run_with_limit` implementation
submitted 100 tasks together to a capacity-50 semaphore. The first 50 held
permits for 2 through 10 seconds. All 50 waiters acquired released permits,
all 100 completed, peak active work was exactly 50, and the semaphore returned
to capacity 50. Waiters began acquiring after about 2.0 seconds.

Consequently, the claim that an asyncio semaphore in this revision fails to
wake waiters is disproved. If a request in the *same* 100-request server wave
really returns a complete response before 12 seconds, its outer permit has
already been released and a live waiter can acquire it.

The exact cause of the reported live observation cannot be reproduced from the
repository evidence currently available:

- no 100-request result artifact exists under `benchmarks/results`;
- the checked-in load fixture has only 50 identities and the checked-in runner
  refuses concurrency 100;
- the application emits no admission or permit-hold timings;
- the load runner's existing stage fields remain null unless an external
  gateway happens to add timing headers;
- the phrase “under 8 seconds” is not tied to a named metric. The internal
  `AnsweringService.timings_ms["total"]` ends before assistant persistence,
  response construction, and outer permit release.

The most defensible diagnosis is therefore a **measurement/reproduction gap**,
not a semaphore handoff defect. Two plausible explanations remain to be tested
with instrumentation: (1) the first 50 requests in the 100-request run did not
actually release permits before 12 seconds even though a separate 50-request
run had faster completions, or (2) the compared “under 8 seconds” number ended
before the full permit-hold interval. Client/proxy queueing or a different load
tool could also make submission time differ from server admission-wait time.

One independent correctness defect is confirmed: the web route starts its
50-second application deadline only *after* admission, while mobile includes
admission inside the 50-second total. The web route can therefore consume about
12 + 50 seconds. This does not explain the mobile observation but should be
made consistent.

## Admission lifecycle

### Mobile endpoint

| Question | Verified answer | Evidence |
|---|---|---|
| Waiting starts | Immediately inside `run_with_limit`, after FastAPI has parsed and validated the request | `mobile_api.py:81-95`; `utils/concurrency.py:99-108` |
| Acquire call | `await asyncio.wait_for(semaphore.acquire(), timeout=acquire_timeout)` | `utils/concurrency.py:107-108` |
| Release call | `semaphore.release()` | `utils/concurrency.py:114-117` |
| Release in `finally` | Yes | `utils/concurrency.py:114-117` |
| Release after failed acquire | No. The acquire exception exits before the release-owning `try` begins | `utils/concurrency.py:107-114` |
| Cancellation leak | No leak found. Cancellation while waiting does not enter the release block; cancellation after acquisition executes `finally` | `utils/concurrency.py:107-117` |
| Admission error | HTTP 503, `SERVICE_BUSY` via `ServiceOverloadedError` | `utils/concurrency.py:109-112`; `utils/service_errors.py:28-30`; `main.py:490-507` |
| Total deadline | Mobile wraps admission plus operation in the 50-second `asyncio.wait_for` | `mobile_api.py:86-101` |

There is a narrow cancellation semantic worth preserving in tests: the
acquired flag is implicit in control flow rather than explicit state. It is
correct in the current implementation, but a reusable limiter object should
make ownership explicit and expose counters.

### Web endpoint

The web route uses the same limiter instance but nests its timeout differently:

```text
run_with_limit(acquire timeout 12 s,
  operation(asyncio.wait_for(pipeline, timeout 50 s)))
```

Evidence: `main.py:589-606`. Admission is outside its application timeout, so
the route's worst-case application-controlled duration is approximately 62
seconds. Mobile instead has:

```text
asyncio.wait_for(
  run_with_limit(acquire timeout 12 s, pipeline),
  timeout 50 s)
```

This discrepancy is a confirmed endpoint-consistency defect.

## Limiter instances and worker scope

- `lifespan()` constructs one request semaphore at `main.py:215-216` and stores
  it at `app.state.request_limiter` at `main.py:368-378`.
- Both `/api/query` and `/api/mobile/v1/talk` access that same app-state object.
- No request-path construction of an outer request semaphore was found.
- `PersianHybridSearch` has a separate nested Qdrant semaphore; it is not a
  duplicate outer limiter (`utils/persian_hybrid_search.py:278-282`).
- `AgentService` has per-session locks. Requests sharing an internal session
  serialize inside the outer permit (`agent_service.py:43,64-82`).
- Every OS worker runs its own lifespan and therefore owns a distinct limiter,
  blocking runner, Qdrant semaphore, and HTTP pools. Host-wide theoretical
  admission is `worker_count × REQUEST_CONCURRENCY_LIMIT`.

## Running staging process

Read-only inspection at audit time found:

| Fact | Observed value |
|---|---|
| Reload supervisor PID | 2589346 |
| Application worker PID | 2589348 |
| Command | `uvicorn main:app --reload --host 0.0.0.0 --port 7000` |
| Working directory | `/root/projects/faq` |
| Python | `/root/miniconda3/envs/faq/bin/python3.12` |
| Worker count | One application worker plus one reload supervisor |
| Health | HTTP 200 at `/api/health`, status `healthy` |
| Application metrics | `/metrics` returns HTTP 404 |
| Source relationship | Process started 2026-08-05; audited Python files predate process start, so the worker loaded this revision unless an unobserved in-place mutation occurred |

The `--reload` flag is operationally important: editing a watched Python file
can automatically replace PID 2589348. Python implementation or test changes
must therefore be treated as a FastAPI restart and require explicit approval.

The process environment does not contain the selected settings because
`main.py:13-16` loads `.env` during import. Since `load_dotenv()` defaults to
`override=False`, a shell-exported value would win. None of the allowlisted
concurrency variables was exported in the worker environment, so the current
`.env` supplies them. Effective non-secret values were verified as:

```text
APPLICATION_REQUEST_TIMEOUT_SECONDS=50
REQUEST_CONCURRENCY_LIMIT=50
REQUEST_ADMISSION_TIMEOUT_SECONDS=12
BLOCKING_CONCURRENCY_LIMIT=16
TEI_HTTP_MAX_CONNECTIONS=64
TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS=16
VLLM_HTTP_MAX_CONNECTIONS=64
VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS=16
QDRANT_CONCURRENCY=8
```

## Work before admission

Application-controlled work before the outer acquire is limited to:

1. ASGI server receipt and HTTP parsing.
2. FastAPI routing.
3. JSON body parsing and Pydantic `TalkRequest` validation.
4. Dependency resolution (the mobile route has no authentication dependency).
5. Allocation of a small closure around `_gateway_talk`.

No PostgreSQL, MinIO, TEI, Qdrant, vLLM, history, intent, or persistence call is
made in the route before `run_with_limit`. This placement is correct. Basic
schema validation before admission is cheap and prevents invalid requests from
occupying expensive slots. The mobile endpoint is documented as unauthenticated
at the FastAPI layer; any gateway authentication is outside this repository.

## Work while holding the permit

The mobile permit covers the complete `_gateway_talk` operation:

1. PostgreSQL user lookup or creation (`mobile_api.py:112-118`).
2. PostgreSQL external-session resolution/creation (`mobile_api.py:120-128`).
3. User-message persistence (`mobile_api.py:130-140`).
4. Normalization on the bounded blocking runner (`answering_service.py:62-78`).
5. Intent TEI embedding and CPU classification (`answering_service.py:80-85`;
   `intent_classifier.py:202-231`).
6. History PostgreSQL read and optional vLLM rewrite
   (`answering_service.py:87-107`).
7. Per-session lock, session and metadata reads (`agent_service.py:64-115`).
8. LangGraph routing and one of the answer paths (`agent_service.py:169-175`).
9. FAQ BM25 work, TEI embedding, Qdrant wait/query, related-question TEI
   reranking, and vLLM answer generation (`agent_graph.py:143-190`;
   `utils/persian_hybrid_search.py:492-575`).
10. Agent-state PostgreSQL persistence (`agent_service.py:194-205`).
11. Assistant-message PostgreSQL persistence (`mobile_api.py:158-166`).
12. Related-question selection and `TalkResponse` construction
   (`mobile_api.py:168-191`).

Required persistence therefore extends permit lifetime beyond final LLM output.
It is unsafe to move those writes after release without choosing and documenting
new failure semantics.

## Work after release

After `_gateway_talk` returns its `TalkResponse`, `run_with_limit` releases the
permit before the route returns to FastAPI. Response-model validation,
serialization, middleware completion, socket writes, proxy work, and client
receive time occur after release. These costs should be measured separately but
do not explain a missing server-side semaphore handoff.

## Timing gaps

- Client elapsed time in `mobile_talk_load_test.py:695-822` includes client-side
  connection-pool wait, network/proxy time, server admission, pipeline work,
  response serialization, and response transfer.
- It does not identify server receive time or true server admission start.
- `AnsweringService.timings_ms["total"]` starts after mobile user/session/message
  setup and ends immediately after the graph (`answering_service.py:62-152`).
  It excludes assistant persistence, response construction, permit release,
  response serialization, and network return.
- Existing load-runner fields such as `limiter_wait_ms` are populated only from
  response headers (`mobile_talk_load_test.py:802-818`). The application emits
  none of those headers.

Therefore “under 8 seconds” is not interpretable until its source field is
identified. If it is the answering-service total or LLM generation duration, it
does **not** prove a permit was released under 8 seconds. If it is complete
client latency from the same 100-request wave, it does prove release occurred
before that response, and the live result needs raw per-request correlation to
explain the contradiction.

## Nested queue hierarchy

```text
socket / proxy / client pool
  -> FastAPI request parsing
    -> outer admission: 50 per worker
      -> shared blocking runner: 16
         -> PostgreSQL: a new connection per operation
         -> BM25 / normalization / CPU classification
         -> synchronous Qdrant SDK call
      -> per-session lock: 1 per internal session
      -> TEI HTTP client pool: 64, keep-alive 16
         -> embedding TEI scheduler
         -> reranker TEI scheduler
      -> Qdrant semaphore: 8
         -> blocking runner: 16
      -> vLLM HTTP client pool: 64, keep-alive 16
         -> vLLM scheduler / shared GPU
      -> required PostgreSQL persistence
    -> release outer permit
  -> response validation / serialization / network return
```

This architecture can hoard outer permits: up to 50 admitted requests may wait
on an eight-slot Qdrant gate, the 16-slot blocking runner, per-session locks,
database connection creation, TEI, or vLLM while all outer permits remain
occupied. This is a performance risk, not proof of the reported event. It must
be measured before increasing an inner limit.

At idle, local service metric endpoints were available for vLLM and both TEI
servers. FastAPI had no metrics endpoint. The shared RTX 5880 reported about
41,038 MiB used and 7,474 MiB free; vLLM accounted for about 37,610 MiB and the
two TEI processes about 1.5 GiB each. These are idle observations, not load
capacity results.

## Load-generator audit

| Property | Checked-in behavior | Evidence |
|---|---|---|
| Burst synchronization | All tasks wait on an `asyncio.Event`; release occurs only after all report ready | `mobile_talk_load_test.py:825-856` |
| Client lifetime | One shared `httpx.AsyncClient` for the run | `mobile_talk_load_test.py:1691-1724` |
| Client pool | Defaults: max 100, keep-alive 50; validation requires max connections at least concurrency | `mobile_talk_load_test.py:147-174,498-501` |
| Timeouts | Explicit connect/read/write/pool; read must exceed 50 seconds | `mobile_talk_load_test.py:448-506,1691-1700` |
| Retries | None | direct `client.post` at `mobile_talk_load_test.py:735-740` |
| Client semaphore | None beyond HTTPX's connection pool |
| Percentiles | Success-only and all-completed are separate; failures are counted and disclosed | `mobile_talk_load_test.py:1042-1125` |
| Admission classification | Only HTTP 503 plus `SERVICE_BUSY` is classified as admission timeout | `mobile_talk_load_test.py:590-628` |
| Deadline classification | HTTP 504 plus `DEPENDENCY_TIMEOUT` | same |
| Request order | Records sort by client start; code does not claim this is server admission order | `mobile_talk_load_test.py:972-973` |
| 50 vs 100 reproducibility | Stock fixture supports 50 users only, so a stock 100-concurrent run fails setup | `mobile_talk_load_test.py:511-515`; fixture count verified without printing identities |

The current artifact schema also stores full synthetic query text, complete
answers, session IDs, and full national-code-like identifiers. That conflicts
with this audit's stricter data-minimization requirement and must be repaired
before another live run.

## Isolated correctness evidence

Executed command: an in-memory Python harness importing the current
`utils.concurrency.run_with_limit`. It contacted no service.

```text
submitted=100
completed=100
timed_out=0
acquired=100
released=100
active_at_idle=0
max_active=50
second_wave_acquired=50
second_wave_wait_min_ms=2002.7
second_wave_wait_max_ms=2335.8
semaphore_value_at_idle=50
```

This proves waiter handoff, capacity enforcement, balanced release, and no idle
leak for the success path. Deterministic exception, cancellation, failed
acquisition, HTTP mapping, and shared-endpoint coverage still need permanent
tests.

## Confirmed findings

### P1 — live observation is not reproducible from retained evidence

There is no raw 100-request artifact, the stock runner cannot run 100 users,
and the server emits no admission lifecycle data. Exact first release time in
the observed live run is **unknown**.

### P1 — permit-hold timing is absent and an internal metric can mislead

The answer-service timer is shorter than outer permit lifetime. Comparing it to
the 12-second admission timeout can create precisely the apparent contradiction
in the incident description.

### P1 — web and mobile deadline scope differs

Mobile includes admission in 50 seconds; web can spend admission plus 50
seconds. Both endpoints should use one documented admission utility and the
same total-deadline semantics.

### P2 — nested queues are invisible

Outer 50, blocking 16, and Qdrant 8 can create permit hoarding. No current
measurement attributes those waits.

### P2 — the runner records more content than necessary

Full questions, answers, session identifiers, and identity-like values should
be replaced with bounded lengths, hashes, aliases, and sanitized categories.

### P3 — asyncio fairness must not be promised

CPython's present semaphore implementation normally wakes waiters in queue
order, and the isolated test observed handoff. The public contract does not
guarantee strict fairness. Correctness must depend on eventual release and
bounded waiting, not FIFO order.

## Implementation boundary

The next safe code change is a reusable, worker-local admission limiter that
owns acquire/release, explicit acquired state, monotonic timings, counters, and
sanitized request correlation. The two answering routes should share it and
use a consistent total deadline. Request tracing should expose response headers
and structured content-free logs, while nested stages use context-bound spans.

Because the running Uvicorn command uses `--reload`, editing any watched Python
file may restart the valuable staging worker. Implementation must wait for the
operator's explicit restart approval or be performed after the running process
is moved out of reload mode.
