# Request admission repair report

Date: 2026-08-05  
Repository: `/root/projects/faq`  
Primary endpoint: `POST /api/mobile/v1/talk`

## Outcome

The outer semaphore did not contain a permit-handoff defect. The observed
claim—complete responses before 12 seconds in the same 100-request wave while
no waiter acquires—is incompatible with the audited one-worker limiter. No raw
100-request artifact exists to resolve that contradiction. The actionable root
cause is an observability/reproduction gap: the earlier timing was not tied to
server receive, admission wait, or complete permit hold, and the checked-in
fixture cannot run 100 users.

The deterministic reproduction is decisive for the implementation itself:
100 tasks started together, capacity was 50, admission timeout was 12 seconds,
and the first 50 held permits for 2–10 seconds. All 100 acquired, none timed
out, peak active work was exactly 50, and acquired/released totals returned to
100/100. The first waiter acquired at 2.0007 seconds and the last at 2.0630
seconds in the final mock run.

One separate correctness defect was fixed. `/api/query` previously began its
50-second application timeout after admission; it could consume roughly
12 + 50 seconds. It now applies the same total deadline semantics as mobile:
admission and pipeline work are both inside the 50-second deadline.

No retrieval-quality or generation setting changed. The active `.env` was not
edited; its pre/post SHA-256 is
`5a47a654bc62ff0624a26bd5ead9a5dd0917597f0c60c302e2c1580dad1951d8`.

## Admission lifecycle after repair

`AdmissionLimiter` in `utils/concurrency.py` now owns the lifecycle explicitly:

1. increment the worker-local waiting count;
2. wait for the semaphore with `asyncio.wait_for`;
3. mark ownership only after successful acquisition;
4. run the operation;
5. release exactly once in `finally` only when ownership exists;
6. preserve `CancelledError` while recording whether cancellation happened
   before or after acquisition.

Relevant implementation points:

- limiter definition and counters: `utils/concurrency.py:35-217`;
- shared worker-local construction: `main.py:227-231`;
- mobile acquisition boundary: `mobile_api.py:89-103`;
- web acquisition boundary and total deadline: `main.py:642-658`;
- content-free request tracing middleware: `main.py:474-519`;
- content-free worker metrics: `main.py:1798-1836`.

The web and mobile answer endpoints share the same `app.state.request_limiter`
inside a worker. There is one instance per FastAPI worker, not one global host
instance. Multiple workers therefore multiply admission capacity, blocking
capacity, Qdrant capacity, and HTTP pools.

## Placement and permit lifetime

No database, TEI, Qdrant, vLLM, MinIO, filesystem, or CPU-heavy application
operation runs before admission. Work before admission is limited to ASGI/FastAPI
parsing, Pydantic validation, dependency resolution, and a small closure.

The mobile permit covers:

- user/session resolution and user-message persistence;
- normalization, intent classification, history, and optional rewrite;
- per-session locking and agent-state reads;
- embedding, retrieval, related-question reranking, and answer generation;
- agent-state and assistant-message persistence;
- related-question selection and response-model construction.

The permit is released before FastAPI response serialization and socket write.
The old answering-service `total` ended before assistant persistence, response
construction, and release. It was not permit-hold time. The live first true
release time for the reported 100-request run remains unknown because that run
has no correlatable artifact.

## Nested queues

```text
outer admission: 50 per worker
  -> blocking runner: 16 per worker
  -> per-session lock: 1 per internal session
  -> Qdrant semaphore: 8 per worker
     -> blocking runner for synchronous SDK work
  -> TEI HTTP pool: 64 -> TEI scheduler
  -> vLLM HTTP pool: 64 -> vLLM scheduler/shared GPU
  -> PostgreSQL connection/query work and required persistence
```

Fifty outer permits can be occupied while requests wait on an inner resource.
That permit hoarding is the main performance hypothesis to measure. The audit
did not prove Qdrant, blocking threads, HTTP pools, TEI, vLLM, PostgreSQL, or
the event loop caused the reported blanket timeouts.

## Instrumentation added

All times use a monotonic clock. Logs and artifacts exclude prompts, answers,
credentials, national codes, and raw session IDs.

- response correlation and admission headers: request ID, server receive time,
  acquire outcome, admission wait, permit hold, pipeline, and bounded stages;
- structured admission events: process ID, stable limiter ID, capacity,
  active/waiting counts, outcome, wait, hold, and release reason;
- `/api/metrics/admission`: worker-local admission, blocking, Qdrant, TEI-client,
  and vLLM-client counters;
- spans for history, intent, rewrite, embedding, Qdrant wait/work, reranking,
  vLLM, persistence, response build, and post-generation work;
- sanitized load-test records with client/server request IDs, submission index,
  timeout category, admission timing, hold timing, stage timing, hashes, and
  lengths—never full question or answer text.

TEI scheduler queueing, vLLM queue/TTFT/KV/preemption, database pool wait, and
transport-internal HTTP pool wait still require server metrics or deeper client
hooks. The new counters do not invent values for unobservable stages.

## Runtime verification

The staging service is healthy at HTTP 200. It has one reload supervisor
(PID 2589346 at verification) and one application worker (PID 2601115). The
content-free metrics endpoint reported:

- admission capacity 50, active 0, waiting 0;
- blocking capacity 16, active 0, waiting 0;
- Qdrant capacity 8, active 0, waiting 0;
- all admission totals zero immediately after the final reload.

Because `--reload` is active, source edits replaced the worker as approved by
the operator. vLLM, TEI, Qdrant, PostgreSQL, MinIO, Docker, and the active
`.env` were not restarted or changed. A separate host-scope start attempt saw
the existing service and did not create a second supervisor or worker.

## Tests

Added `tests/test_request_admission.py` for:

- success, exception, and cancellation release;
- no release following failed acquisition;
- waiter handoff and capacity 50 / task count 100 reproduction;
- maximum-active and acquired-minus-released invariants;
- idle no-leak state;
- endpoint sharing and explicit worker-local isolation;
- distinct admission/server timeout and client timeout classifications;
- documented non-guarantee of FIFO fairness;
- content-free tracing headers.

Added `benchmarks/admission/mock_admission_benchmark.py` for a repeatable,
dependency-free proof. Updated load-runner tests cover sanitized output and the
new timing schema.

Executed results:

- 89 admission/load/config/service/TEI unit tests: passed;
- 46 database/mass-answer/environment-validator unit tests: passed;
- total non-overlapping `unittest` tests: 135 passed;
- deterministic mock: 100 completed, 0 timed out, max active 50, 100 acquired,
  100 released, idle active/waiting 0;
- Python compilation and `git diff --check`: passed.

`python -m pytest -q` was not run because pytest is not installed in the active
FAQ environment. This is recorded as tooling unavailable, not as a passing or
failing pytest suite.

## Environment recommendation

No numerical change is supported without a live before/after benchmark. The
recommended tested-control file therefore preserves the effective baseline:

```dotenv
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

This is a control, not a claim of optimal performance. Do not yet recommend:

- admission timeout 15/18: creates no throughput and risks the 20-second goal;
- request capacity 60: may increase nested queueing and GPU preemption;
- Qdrant 12/16: requires material measured Qdrant wait and healthy service
  latency/CPU/memory;
- blocking 20/24: requires material blocking wait without CPU, event-loop, or
  database regression;
- keep-alive 32/64: requires measured connection churn or pool pressure.

## Manual experiment commands

Review the full matrix without traffic:

```bash
cd /root/projects/faq
scripts/run_admission_live_benchmark.sh .env.test.admission-baseline
```

After separate explicit approval for state-changing live load, an operator
provides at least 100 reserved staging identities:

```bash
cd /root/projects/faq
export RAGBOT_ADMISSION_IDENTITY_FIXTURE=/secure/path/staging-identities-100.json
export RAGBOT_ADMISSION_SCENARIO_FILE=/root/projects/faq/benchmarks/load/fixtures/persian_banking_scenarios.json
scripts/run_admission_live_benchmark.sh .env.test.admission-baseline --execute
```

Exact individual scenarios:

```bash
scripts/test_admission_configuration.sh .env.test.admission-baseline 50 burst
scripts/test_admission_configuration.sh .env.test.admission-baseline 75 burst
scripts/test_admission_configuration.sh .env.test.admission-baseline 100 burst
scripts/test_admission_configuration.sh .env.test.admission-baseline 100 arrival-rate 10
```

Replace the candidate filename with one experimental file at a time. Each
script starts a temporary one-worker service on port 7100, requires typed
confirmation, refuses production, records health/PIDs, and restores the exact
original `.env` if anything external changes it.

## Restart and rollback

The preferred test path does not replace port 7000. If an operator deliberately
tests the active service instead, capture its exact command/PIDs and health,
stop only the owning Uvicorn process, start the same reviewed one-worker
command, and recheck health and `/api/metrics/admission`. Do not restart model
or data services.

To end a temporary candidate run, use `Ctrl-C`; the trap stops only its recorded
temporary PID. The test trap restores its private backup automatically if the
active file changes. For a separately retained operator backup, recovery is:

```bash
cd /root/projects/faq
scripts/restore_admission_configuration.sh /absolute/path/to/env.backup
```

The active `.env` was never an edit target. To undo code changes, first save and
inspect a scoped patch, verify a reverse application, reverse only that patch,
then restart FastAPI under explicit operator control:

```bash
cd /root/projects/faq
git diff --binary -- main.py mobile_api.py answering_service.py agent_service.py \
  utils/concurrency.py utils/request_instrumentation.py utils/RagSystem.py \
  utils/persian_hybrid_search.py benchmarks/load tests \
  >/tmp/faq-admission-code.patch
git apply --check --reverse /tmp/faq-admission-code.patch
git apply --reverse /tmp/faq-admission-code.patch
```

## Remaining approval gates

Explicit approval is still required before state-changing live benchmark
traffic, applying any candidate configuration, modifying `.env`, restarting an
external dependency, committing/pushing, or changing production/staging
service definitions. FastAPI source reload/restart permission was granted for
this repair and used only for the application worker.
