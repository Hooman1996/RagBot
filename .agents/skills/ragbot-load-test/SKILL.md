---
name: ragbot-load-test
description: Design, implement, validate, run, and analyze reproducible staging-only load tests for the RagBot mobile talk API. Use when Codex needs to audit mobile talk request prerequisites, build an async httpx load generator, smoke-test or benchmark POST /v1/talk, run concurrency sweeps or 50-request bursts, diagnose saturation and latency, compare benchmark results, or make a fixed pass/fail performance decision.
---

# RagBot Load Test

Treat load testing as a controlled staging experiment. Define measurable acceptance criteria and report pass or fail; never claim the system is "fully optimized."

## Guardrails

- Target staging only. Resolve the deployed route before sending traffic: the requested primary route is `POST /v1/talk`, while repository router prefixes may produce a different full path.
- Never change or test production infrastructure. Staging has one NVIDIA RTX 5880 Ada 48 GB; production's two NVIDIA L4 24 GB GPUs are context only, not authorization or a basis for extrapolating capacity.
- Never use customer data, log tokens, write full national codes, or store complete model answers unless explicitly required.
- Warn before traffic that creates PostgreSQL, Qdrant, MinIO, or other persistent records. Provide scoped cleanup instructions when required.
- Do not run a large live test automatically. Show the exact command and obtain human review before 50-concurrent traffic or an equivalently material load.
- Keep TLS verification enabled by default. Do not automatically retry failures.
- Change one major variable per experiment and benchmark before and after.
- Do not change model behavior without retrieval and answer-quality tests.

## Required workflow

Follow this order. Record evidence, file paths, and relevant line numbers for inspection steps.

1. Inspect the real `TalkRequest` schema and serialization.
2. Inspect the real `TalkResponse` schema and success semantics.
3. Inspect authentication and required headers without exposing secrets.
4. Inspect session-ID format and validation.
5. Inspect national-code validation, including the exact checksum implementation.
6. Determine whether test identities must already exist in PostgreSQL.
7. Determine whether requests create persistent records.
8. Determine cleanup requirements and prepare scoped cleanup instructions.
9. Inspect request-limiter capacity and scope.
10. Inspect limiter acquisition timeout and failure response. The expected acquisition timeout is 2 seconds; verify it.
11. Inspect `asyncio.wait_for`, cancellation behavior, and the expected 50-second application deadline.
12. Design a safe, staging-only workload and fixed acceptance criteria.
13. Build the standalone load-test program.
14. Validate it with mocked HTTP calls.
15. Run a minimal smoke test.
16. Run a reviewed concurrency sweep.
17. Run reviewed repeated bursts of 50 simultaneous requests.
18. Analyze failures, latency distributions, stage timings, and saturation signals.
19. Compare results with the fixed criteria and return a pass/fail decision.

Do not skip directly to live load because a payload "looks right." If schema, identity, persistence, cleanup, routing, or staging ownership remains uncertain, stop before live traffic and report the setup failure.

## Repository audit

Search with `rg` before assuming behavior. Inspect the FastAPI route registration, Pydantic models, dependencies, authentication, validators, limiter, timeout wrapper, persistence calls, and relevant environment-variable names. Treat `.env`, `.env.server_git`, tokens, credentials, identities, and banking data as sensitive; never print their values.

Produce a prerequisite table containing: item, verified behavior, evidence, test impact, and unresolved risk. Include the effective endpoint, payload example with synthetic/redacted fields, response success rule, required headers, identity provisioning, write footprint, cleanup plan, limiter capacity/failure signature, deadline signature, and observability available.

## Identity and session safety

- Give every virtual user a unique synthetic session ID.
- In multi-turn scenarios, retain that user's session ID; await its previous response before its follow-up while other users continue concurrently.
- Never share sessions across virtual users.
- Inspect exact national-code rules before generating any value.
- Never use a real customer national code.
- If the application requires valid Iranian checksums, match the repository implementation and use a verified staging/test namespace when available.
- Store only a one-way hash or a redacted identifier in results and logs. Do not put a full national code in filenames, exceptions, reports, or command output.
- If collision-free synthetic identities cannot be guaranteed, require an input fixture of pre-created staging-only identities. Keep the fixture out of result artifacts and version control.

## Load-generator contract

When implementation is requested, create a standalone async Python program using one reusable `httpx.AsyncClient` for the entire run. Do not create a client per request.

Support configuration for:

- base URL and endpoint
- concurrency and repetitions
- request timeout, with explicit connect, read, write, and pool timeouts
- warm-up count
- random seed and scenario
- workload mode and arrival rate
- maximum connections and maximum keep-alive connections
- output directory
- optional authentication token from environment or CLI
- TLS verification, enabled by default
- configurable default and strict acceptance thresholds

Define `total_requests = concurrency * repetitions`. In burst mode, repetitions are waves; `50 * 5` means five 50-request waves and 250 measured attempts. Exclude warm-ups from measured totals and acceptance statistics, but report their outcome separately.

Never expose a CLI token in metadata or logs. Prefer an environment variable. If CLI token support is required, redact parsed arguments and warn about shell-history/process-list exposure. Reject production-looking hosts and plaintext HTTP unless an explicit, reviewed staging exception is documented. Do not silently disable certificate verification.

### Workload modes

Implement all three:

1. **Burst:** Prepare a wave and release all requests as close together as possible with `asyncio.Event`, a barrier, or equivalent. This mode is mandatory for 50-simultaneous validation.
2. **Closed loop:** Maintain the configured number of virtual users; each user sends its next request only after its previous request completes.
3. **Arrival rate:** Schedule starts at the configured requests/second independently of prior completion. Track intended and actual start times and scheduler lag.

Preserve per-user ordering for multi-turn scenarios in every mode. Clearly document how repetitions map to requests in non-burst modes while preserving the total-request formula.

Configure `httpx.Timeout(connect=..., read=..., write=..., pool=...)` and `httpx.Limits(max_connections=..., max_keepalive_connections=...)`. Set a client read timeout that makes the 50-second application deadline observable rather than accidentally masking it, unless the experiment explicitly tests shorter client timeouts.

Do not retry automatically: retries hide overload, alter request rate, and corrupt attempt accounting.

## Request records and classification

Use monotonic time for durations and wall-clock UTC for human timestamps. Write one record per attempt with:

- run ID, wave number, virtual-user ID, request number, and scenario
- synthetic session ID and hashed/redacted national-code identity
- monotonic start/end and total client latency
- HTTP status, response byte size, and answer length
- success/failure classification, exception type, and sanitized error
- timeout category
- server request ID, timing headers, and stage timings when returned

Do not store complete answers by default. Parse enough of `TalkResponse` to validate its schema and measure answer length.

Classify failures exclusively and deterministically:

- limiter acquisition rejection
- application 50-second deadline timeout
- client read timeout
- client connect timeout
- HTTP connection-pool timeout
- connection error
- HTTP 4xx
- HTTP 5xx
- invalid response schema
- cancellation
- unexpected exception

Derive limiter and application-timeout signatures from audited server behavior, not guessed message text. Sanitize error bodies and exceptions before persistence. Preserve the HTTP status alongside the more specific failure category.

## Statistics and artifacts

Calculate total attempts, successes, failures, min, max, arithmetic mean, median, standard deviation, p50, p75, p90, p95, p99, throughput, wall-clock duration, and percentages within 10, 15, 20, and 50 seconds.

Report globally and group by wave, scenario, status code, and failure category. State the percentile method. Never report only an average. If latency percentiles use successful requests, label them as success-only and prominently state the number and percentage of failures excluded. Also report all-completed-attempt latency where meaningful; never turn failed attempts into zero-latency samples.

Create a timestamped directory such as `benchmarks/results/mobile-talk/<timestamp>/` containing:

- `requests.jsonl`: one record per measured request
- `requests.csv`: one record per measured request
- `summary.json`
- `report.md`
- a concise terminal summary

Write artifacts incrementally or atomically enough to retain completed records after interruption. Record: Git SHA, UTC timestamp, hostname, Python version, endpoint, concurrency, repetitions, total requests, seed, timeout values, mode, arrival rate, scenario, known limiter capacity, GPU model, Docker image versions, and relevant sanitized application configuration. Mark unavailable metadata as unknown; never invent it or capture secrets.

## Acceptance evaluation

Freeze criteria before a measured run. Make them configurable and include them in `summary.json`.

Default target:

- concurrency 50 and repetitions 5
- success rate at least 99%
- p95 end-to-end success latency at most 20 seconds, with excluded failures stated
- zero application deadline timeouts
- zero HTTP 5xx responses

Strict target:

- zero limiter rejections
- zero application deadline timeouts
- zero client timeouts
- zero HTTP 5xx responses
- 100% successful responses
- every successful request completes within 20 seconds

When strict limiter acceptance is requested, enforce zero limiter acquisition failures. Always report other 4xx categories even when they are not an explicit default threshold. Evaluate repeatability per wave as well as globally; a global pass must not conceal a materially failing wave. If a repeatability tolerance was not supplied, report wave variance and refrain from inventing one.

Exit with:

- `0`: completed and all selected criteria passed
- `1`: completed but one or more criteria failed
- `2`: invalid configuration or setup failure

Print each failed criterion with actual and threshold values. Never reinterpret a failed result as a pass after seeing the data.

## Validation

Use `pytest` and `httpx.MockTransport` or an equivalent mocked transport. Test:

- percentile calculations and documented interpolation
- average, minimum, maximum, median, and standard deviation
- empty result sets
- mixed successes and failures, including excluded-count reporting
- every timeout category and limiter-rejection classification
- deterministic random data for a fixed seed
- session uniqueness and multi-turn continuity
- national-code redaction and absence from serialized output
- `concurrency * repetitions` total calculation
- burst synchronization
- JSONL, CSV, JSON, and Markdown serialization
- acceptance evaluation and exit-code selection

Mock success, schema errors, 4xx, 5xx, limiter failure, application deadline, each httpx timeout, connection failure, cancellation, malformed timing headers, and slow responses. Verify no retry occurs and a single client/transport is reused.

Run unit tests before network traffic. Then run one low-impact synthetic smoke request (or the smallest safe count) against staging. Confirm route, authentication, response parsing, redaction, record creation, and cleanup before proposing a sweep. Record every executed command and result; never claim unrun tests passed.

## Live benchmark progression

1. Present the audited prerequisites, safety assessment, exact command, expected writes, cleanup, acceptance criteria, and estimated request count.
2. Obtain human review before a 50-concurrent run.
3. Run a smoke test.
4. Run a concurrency sweep such as `1, 2, 5, 10, 20, 30, 40, 50`, adjusting only with documented staging constraints.
5. Run at least five repeated 50-request burst waves when approved.
6. Keep payload/scenario, seed, warm-up, client limits, model settings, and acceptance criteria fixed across comparisons.
7. Preserve raw artifacts and analyze them before recommending a change.

## Analysis

Separate, using available client, application, service, and GPU evidence:

- limiter waiting/rejection
- FastAPI event-loop and thread-pool delay
- PostgreSQL delay
- TEI embedding delay
- Qdrant delay
- TEI reranking delay
- query rewriting delay
- vLLM scheduler queue, prefill, and decode time
- response persistence
- client/network overhead

Do not infer precise stage attribution from end-to-end latency alone. Label correlations and hypotheses as such.

Identify saturation from throughput flattening, sharp p95/p99 growth, increasing limiter rejection, accumulating vLLM waiting requests, rising vLLM queue time, KV-cache pressure, preemptions, GPU saturation, connection-pool starvation, database-pool starvation, and timeout growth. Align time windows and run IDs across evidence without logging prompts or banking data.

## One-variable experiments

Change one major variable per experiment, for example limiter capacity, limiter acquisition timeout, vLLM `max_num_seqs`, vLLM `max_num_batched_tokens`, maximum output tokens, prompt length, TEI concurrency, HTTP pool size, or PostgreSQL pool size.

For each experiment record:

- hypothesis and expected result
- baseline configuration and repeated benchmark
- exactly one changed major variable
- actual result and uncertainty/repeatability
- rollback procedure
- repeated after-change benchmark
- retrieval and answer-quality regression checks when model behavior may change

Do not combine infrastructure tuning with workload, prompt, or output-length changes. Roll back failed experiments. Every claimed performance improvement requires before-and-after evidence.

## Reusable prompt templates

### Prerequisites audit

> Use `$ragbot-load-test` to audit the repository for the staging mobile talk endpoint. Verify schemas, route, auth, headers, session and national-code validation, identity provisioning, persistent writes and cleanup, limiter capacity/failure behavior, and application timeout. Return an evidence table and blockers; do not send live traffic.

### Implementation

> Use `$ragbot-load-test` to implement a standalone async `httpx.AsyncClient` load generator and mocked tests for the audited staging talk API. Support burst, closed-loop, and arrival-rate modes, required metrics/artifacts, redaction, configurable criteria, and exit codes. Do not run live load.

### Smoke test

> Use `$ragbot-load-test` to validate mocked tests, show the exact staging smoke-test command and safety impact, then run only the smallest approved smoke test. Report writes, cleanup, parsing, redaction, and pass/fail evidence.

### 50-request burst

> Use `$ragbot-load-test` to prepare a reviewed staging burst test with concurrency 50 and configurable repetitions. Freeze criteria, show the exact command, request human review before live load, then analyze each wave and global results without automatic retries.

### Concurrency sweep

> Use `$ragbot-load-test` to design a staging concurrency sweep with one fixed scenario and configuration. Establish a baseline, show commands and cleanup, require review before material traffic, and identify the saturation knee from throughput, tail latency, failures, queues, pools, and GPU evidence.

### Result analysis

> Use `$ragbot-load-test` to analyze the supplied artifacts globally and by wave, scenario, status, and failure category. Report excluded failures beside success-only percentiles, assess repeatability, separate observable stages, identify saturation evidence, and distinguish facts from hypotheses.

### Acceptance decision

> Use `$ragbot-load-test` to evaluate the supplied run against criteria frozen in its metadata. Return pass or fail, every criterion's threshold and actual value, per-wave anomalies, artifact integrity issues, and the correct exit code. Never call the system fully optimized.
