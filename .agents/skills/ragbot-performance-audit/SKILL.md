---
name: ragbot-performance-audit
description: Perform evidence-based performance audits and controlled optimization experiments for this production-oriented Agentic RAG chatbot. Use when investigating request latency, timeouts, throughput, concurrency, event-loop blocking, database or vector-search performance, vLLM or Hugging Face TEI serving, GPU contention, prompt growth, client connection pooling, or when validating a proposed performance change with before-and-after benchmarks.
---

# RAGBot Performance Audit

## Operating rules

Treat the root `AGENTS.md` as authoritative repository guidance and read it before acting.

- Inspect architecture in read-only mode before proposing or making modifications.
- Never change production infrastructure from this staging repository.
- Never run load, stress, soak, or fault tests against production.
- Obtain explicit authorization before generating staging load or invoking a state-changing endpoint.
- Use synthetic, non-customer benchmark inputs. Never record prompts, customer data, authentication values, banking data, or secrets.
- Redact endpoint credentials, headers, query parameters, database values, document content, and prompt text from artifacts.
- Use monotonic clocks for durations and a sanitized correlation ID for cross-component traces.
- Separate facts measured directly from hypotheses and inferences.
- Change one major optimization variable per experiment.
- Require comparable before-and-after benchmarks for every performance change.
- Do not change model behavior without retrieval and answer-quality tests.
- Stop an experiment if it threatens service stability, corrupts benchmark validity, or approaches an unsafe resource limit.

Do not modify code during discovery. After discovery, make changes only when the user explicitly asks for optimization or implementation. An audit request alone authorizes inspection, measurement planning, and safe read-only diagnostics, not source or infrastructure changes.

## Audit contract

At the start, record:

1. Audit question and target endpoint or workload.
2. Staging environment identity, revision, configuration fingerprint, model identifiers, and service versions without secret values.
3. External request timeout: 50 seconds.
4. Hardware: staging has one NVIDIA RTX 5880 Ada Generation GPU with 48 GB VRAM; production has two NVIDIA L4 GPUs with 24 GB each. Do not extrapolate staging results to production without labeling the inference.
5. Test dataset, concurrency, arrival pattern, warm-up, duration, sample count, and pass/fail criteria.
6. Whether the run is cold-start, warm, or both.
7. Known background workloads and whether vLLM and TEI share the staging GPU.

If a required detail cannot be verified, mark it `unknown`; do not guess.

## Phase 1: Read-only architecture discovery

### Establish repository state

- Read root `AGENTS.md`.
- Run read-only status and file inventory commands.
- Preserve all user-owned changes in a dirty worktree.
- Locate entry points, routers, graph construction, graph nodes, service clients, configuration sources, instrumentation, benchmarks, and tests.
- Do not print `.env` values. Inspect only necessary variable names or explicitly safe values such as known staging ports.

Start from these verified paths, then confirm they still match the worktree:

- FastAPI entry point: `main.py`, application `main:app`
- Routers: `mobile_api.py`, `kb_manager.py`
- Graph and nodes: `agent_graph.py`
- Graph invocation and state persistence: `agent_service.py`
- vLLM client: `utils/RagSystem.py`
- TEI embedding and reranking clients: `utils/persian_hybrid_search.py`
- PostgreSQL chat operations: `new_architecture/app/services/history/database.py`
- Startup PostgreSQL, Qdrant, and MinIO clients: `new_architecture/app/services/db_connection/connection.py`
- SQLAlchemy pool implementation: `new_architecture/app/core/database.py`
- Service configuration: `new_architecture/app/config.py`, `env.example`, and environment variables

### Trace every request path

For each audited FastAPI endpoint, trace the complete path from socket-facing request to response:

1. ASGI server and middleware.
2. FastAPI route and dependency resolution.
3. Authentication and validation.
4. Session/history reads and writes.
5. Query normalization and rewriting.
6. Intent classification.
7. Agent service and every LangGraph node and conditional edge.
8. Embedding request to TEI.
9. PostgreSQL chunk retrieval.
10. Qdrant vector search and any local hybrid-search work.
11. Reranking request to TEI.
12. Context and prompt construction.
13. vLLM request, queueing, prefill, decode, and completion.
14. Answer cleanup, state persistence, response serialization, and network return.
15. Error, retry, fallback, cancellation, and timeout paths.

Produce a trace table with:

| Order | Caller | Operation | File/symbol | Sync or async | Resource/client | Timeout/retry | Expected metric |
|---|---|---|---|---|---|---|---|

Account for parallel branches and conditional paths. Reconcile all component spans with end-to-end latency; unexplained time is a finding.

### Inventory every sync/async boundary

Find every boundary on the traced path, including:

- `async def` calling synchronous functions.
- `await` points and missing `await` calls.
- `asyncio.to_thread`, executors, thread pools, and background tasks.
- Synchronous psycopg2, Qdrant, MinIO, filesystem, model, tokenization, JSON, template, compression, and logging operations.
- Async HTTP requests and client initialization or teardown.
- LangGraph sync versus async invocation.
- Locks, semaphores, queues, and concurrency limiters.

Record:

| File/symbol | Caller context | Callee type | Boundary mechanism | Runs on event loop? | Blocking risk | Evidence |
|---|---|---|---|---|---|---|

### Detect event-loop blocking

Use static inspection first. Flag synchronous network, database, filesystem, CPU-heavy, GPU synchronization, serialization, tokenization, or sleep work called directly by `async def`.

When runtime measurement is authorized and available:

- Measure event-loop lag under idle and representative load.
- Capture task and thread activity with low-overhead profilers appropriate to the environment.
- Compare endpoint latency at concurrency 1 and increasing concurrency.
- Look for stair-step latency, serialized spans, thread-pool saturation, long GIL-held CPU work, and cancellation that fails to stop downstream work.
- Attribute each suspected blocker to a stack, span, or controlled experiment.

Do not label code event-loop blocking solely because it is synchronous; prove that it executes on the event-loop thread or state that this is an unverified risk.

## Phase 2: Client, storage, and retrieval audit

### HTTP client lifetime and connection pools

For every HTTP client used for vLLM, TEI, or another dependency:

- Identify construction and close locations, process scope, worker scope, and request scope.
- Detect clients created at import time, as default arguments, inside hot paths, or never closed.
- Record sync versus async implementation.
- Inspect pool limits, keep-alive limits, idle expiry, DNS behavior, HTTP version, TLS, connect/read/write/pool timeouts, retries, backoff, and cancellation.
- Measure connection reuse, new connections, pool-acquire wait, active/idle connections, and socket errors when observable.
- Verify that client limits align with application concurrency and downstream server capacity.

Distinguish downstream queue time from client pool wait and network time.

### PostgreSQL

Trace every query on the critical path and record query count, cumulative time, rows returned, and transaction boundaries.

- Identify whether the verified request path uses direct psycopg2 connections, the SQLAlchemy pool, or both.
- Measure connection creation and pool-acquire wait separately from query execution.
- Inspect pool size, overflow, timeout, recycling, health checks, connection leaks, idle transactions, commits, rollbacks, and concurrency limits.
- Detect N+1 queries, repeated session/history reads, excessive commits, large JSON metadata, unbounded result sets, missing pagination, and unnecessary row materialization.
- Use `pg_stat_statements`, PostgreSQL activity views, and slow-query data only when available and authorized.
- Use `EXPLAIN (ANALYZE, BUFFERS)` only on safe staging `SELECT` statements with representative sanitized parameters. Never use it on mutating SQL.
- Report plans, cardinality errors, scans, sorts, buffer reads/hits, lock waits, and index opportunities with evidence.

Do not claim the SQLAlchemy pool serves the active path merely because it exists in the repository.

### Qdrant

- Identify client lifetime, sync/async mode, connection settings, timeouts, retries, and whether sync calls run on the event loop.
- Trace embedding dimension, collection, filters, payload selection, `limit`, candidate counts, search parameters, and result materialization.
- Separate client/network latency, Qdrant queue or service time, vector search, payload transfer, and application-side hybrid fusion.
- Inspect collection size, vector count, segment count, index status, optimizer activity, quantization, replication, and relevant HNSW/search settings using read-only APIs.
- Measure recall-sensitive settings only with a retrieval-quality dataset.
- Detect oversized payloads, unnecessary vectors/payload fields, broad filters, repeated collection checks, and blocking client calls.

Never tune search parameters using latency alone; preserve or measure retrieval quality.

### MinIO

- Determine whether MinIO is on the audited request's critical path. If it is not, state that explicitly.
- If it is, trace client lifetime, connection reuse, DNS/TLS, bucket checks, object metadata calls, downloads/uploads, byte counts, streaming versus buffering, retries, and timeouts.
- Measure time to first byte, transfer duration, throughput, and application processing after transfer.
- Detect startup bucket creation/checks leaking into request handling, repeated metadata calls, whole-object buffering, synchronous SDK calls on the event loop, and unbounded object sizes.

Do not optimize MinIO when it is outside the measured critical path.

## Phase 3: Model-serving and GPU audit

### vLLM

Collect server-side metrics or traces and correlate them with application requests. Inspect the actual vLLM version and exported metric names rather than assuming names.

Measure:

- Request queue time.
- Time to first token (TTFT).
- Prefill time and prefill tokens.
- Decode time.
- Inter-token latency or time per output token.
- End-to-end generation latency.
- Input/prompt tokens and output/completion tokens.
- Total tokens, tokens per second, and requests per second.
- Running, waiting, preempted, and aborted requests when exposed.
- Batch size, batching behavior, KV-cache use, cache pressure, prefix-cache behavior, and scheduler saturation when exposed.
- Errors, cancellations, client timeouts, and server work continuing after client cancellation.

Decompose approximately:

`generation latency = queue + prefill + decode + network/client overhead`

Keep exact measured fields separate when the server reports a different decomposition. Report cold and warm behavior separately.

### TEI embedding and reranking

Audit the embedding endpoint on staging port `7997` and reranking endpoint on staging port `7998`.

For each service, measure:

- Client pool-acquire, connect, request-write, queue, inference, response-read, and total latency where observable.
- Batch size, input count, token count, truncation, payload bytes, and output bytes.
- Queue depth, active requests, batch utilization, throughput, errors, and timeouts from the service's actual metrics.
- Embedding latency separately from Qdrant search latency.
- Reranking latency as a function of candidate count and candidate token length.
- Whether batching improves throughput while harming per-request tail latency.

Inspect the deployed TEI version and `/metrics` output before naming metrics. Do not send prompt or document text to logs.

### GPU contention

Because staging has one shared 48 GB GPU, determine which processes and services use it and whether they compete.

Correlate over time:

- Per-process GPU utilization and memory.
- SM, tensor, memory-controller, and encoder/decoder utilization when available.
- Allocated/reserved memory, KV-cache consumption, and out-of-memory events.
- Power, clocks, temperature, thermal or power throttling.
- PCIe transfer activity.
- vLLM running/waiting work and TEI queues.
- CPU, RAM, disk, and network saturation that can masquerade as GPU limits.

Use `nvidia-smi`, DCGM, or existing Prometheus/Grafana telemetry when available. Match sample timestamps to benchmark phases. Avoid installing agents or changing GPU settings during an audit unless separately authorized.

Classify contention as measured, inferred, or unknown. Do not assume GPU contention solely because services share a device.

### Prompt and history growth

Measure without storing content:

- Prompt tokens by component: system instructions, retrieved context, conversation history, rewritten query, tool or schema text, and other scaffolding.
- Output tokens.
- History turns, characters, serialized bytes, and database metadata size.
- Retrieved chunk count, chunk token distribution, duplicates, and context utilization.
- TTFT and prefill latency versus prompt length.
- End-to-end latency and timeout rate versus conversation depth.

Use token counts, hashes, synthetic identifiers, and aggregate distributions; never persist raw prompts or customer content. Detect unbounded history, repeated instructions, duplicated context, ineffective trimming, and token growth across turns.

## Phase 4: Benchmark design and execution

### Define the baseline

Use a representative, synthetic workload with fixed scenarios and deterministic selection rules. Include the important route classes, such as chitchat, retrieval-heavy FAQ, long-history, reranking-heavy, and failure/timeout paths where safe.

Keep constant:

- Code revision and configuration except for the declared experiment variable.
- Model, tokenizer, quantization, and serving versions.
- Dataset and request ordering or random seed.
- Prompt and expected output-token bounds.
- Warm-up policy and cache policy.
- Concurrency, arrival model, duration, and sample count.
- Background workload or isolation.
- Hardware and service placement.

Record raw per-request timings in sanitized form. Do not average percentiles across runs; combine comparable raw samples or report runs separately.

### Required metrics

For end-to-end latency and every material component, report:

- Sample count.
- p50, p95, and p99 latency.
- Mean, minimum, and maximum as secondary context.
- Throughput in requests/second and, where useful, tokens/second.
- Success rate, error rate, and timeout rate.
- Concurrency and achieved request rate.
- Prompt, completion, and total-token distributions.

Define timeout rate as requests exceeding or terminated by the 50-second external limit, and separately report application, client, and downstream timeout causes.

Use enough samples for tail percentiles. If sample size is insufficient for a defensible p99, label p99 unstable rather than presenting false precision. Include confidence intervals or repeated-run variability when practical.

### Run controlled experiments

For each experiment:

1. State one major optimization variable and a falsifiable hypothesis.
2. Define primary latency/throughput metric, guardrail metrics, quality gates, and rollback condition.
3. Capture the before benchmark.
4. Apply only the authorized change.
5. Verify effective configuration and service health.
6. Capture the after benchmark under the same protocol.
7. Run retrieval and answer-quality tests for any model-behavior-affecting change.
8. Compare absolute and percentage changes in p50, p95, p99, throughput, timeout rate, resource use, and quality.
9. Repeat or revert when results are noisy, unsafe, or regress guardrails.

Examples of major variables that must not be combined in one experiment include model parameters, prompt construction, retrieval candidate count, reranker candidate count, Qdrant search parameters, HTTP pool limits, database pool limits, vLLM batching/scheduler settings, and TEI batching settings.

## Phase 5: Findings and handoff

Deliver:

1. Executive summary with the measured bottleneck and user impact.
2. Environment and benchmark protocol.
3. Complete request trace.
4. Sync/async boundary and event-loop-blocking inventory.
5. End-to-end latency budget showing p50, p95, and p99 by component.
6. Throughput, error, and timeout results.
7. PostgreSQL, Qdrant, MinIO, HTTP-client, vLLM, TEI, GPU, and prompt-growth findings.
8. Evidence for every finding: file/symbol, metric, trace, profile, query plan, or controlled result.
9. Ranked recommendations by expected impact, risk, effort, and quality implications.
10. An experiment card for each recommendation, with exactly one major variable.
11. Before-and-after results for implemented changes.
12. Unknowns, limitations, and production-extrapolation caveats.

Use this experiment table:

| Experiment | Major variable | Baseline | After | p50 | p95 | p99 | Throughput | Timeout rate | Quality | Decision |
|---|---|---|---|---|---|---|---|---|---|---|

Use this finding format:

```text
Finding:
Evidence:
Critical-path impact:
Confidence:
Recommendation:
Single-variable experiment:
Safety and quality gates:
```

Do not present a proposed optimization as a verified improvement without a comparable after benchmark.
