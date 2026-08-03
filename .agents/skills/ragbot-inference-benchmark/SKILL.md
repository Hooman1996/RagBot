---
name: ragbot-inference-benchmark
description: Audit, benchmark, tune, and analyze the staging inference services used by RagBot: vLLM generation, Hugging Face TEI embedding, TEI reranking, shared-GPU contention, and full FastAPI talk-request latency. Use when Codex needs to inspect inference runtime configuration, build or run reproducible inference benchmarks, find saturation and bottlenecks, test 50 simultaneous talk requests against a 50-second deadline and 20-second p95 target, compare isolated versus combined services, tune vLLM or TEI one variable at a time, or make staging-to-production capacity recommendations.
---

# RagBot Inference Benchmark

Treat every benchmark as a controlled staging experiment. Determine the saturation point, dominant bottleneck, and fixed-criteria pass/fail result. Never declare the system "fully optimized."

Read [references/benchmark-spec.md](references/benchmark-spec.md) before designing, running, or analyzing a benchmark. Use its required matrices, metrics, artifacts, formulas, and report schema.

## Guardrails

- Operate only on staging unless the user explicitly authorizes a different non-production target. Never stop, reconfigure, benchmark, or otherwise touch production services.
- Treat staging as one NVIDIA RTX 5880 Ada GPU with 48 GB VRAM. Treat production as two separate NVIDIA L4 GPUs with 24 GB each; never describe them as one unified 48 GB memory space.
- Separate hardware-independent software findings from hardware-dependent serving parameters in every recommendation.
- Never transfer RTX 5880 serving parameters directly to dual-L4 production. Require production-like retesting and an explicit placement plan.
- Never use customer prompts, banking data, authentication values, or secrets. Use deterministic synthetic data or approved staging fixtures containing no customer data.
- Never print `.env` or `.env.server_git` values. Record relevant settings only through sanitized allowlists.
- Never expose a metrics endpoint publicly.
- Never make destructive changes automatically. Generate exact live benchmark, isolation, restore, and rollback commands for human review before running them.
- Before traffic that may create records, identify PostgreSQL, Qdrant, MinIO, and session side effects and provide scoped cleanup instructions.
- Do not change model behavior without retrieval and answer-quality tests. If their commands are unavailable, report that as a blocker to adopting the change.
- Do not claim success when required metrics are missing. Label unavailable evidence as `unknown`.

## Fixed target

Freeze acceptance criteria before collecting measured results:

- workload: 50 simultaneous `POST /v1/talk` requests
- application deadline: 50 seconds
- desired p95 end-to-end latency: at most 20 seconds
- success rate: at least 99% (with exactly 50 attempts, this requires all 50 to succeed)
- application-deadline timeouts, client timeouts, request rejections, and HTTP 5xx responses: zero

Resolve the actual deployed path before traffic. The repository router may expose `/api/mobile/v1/talk`; do not silently equate it with `/v1/talk`.

At minimum, report success rate, p50/p95/p99 end-to-end latency, timeout count, rejection count, HTTP 5xx count, achieved throughput, and whether all 50 requests were genuinely simultaneous. Compute latency percentiles over successful requests, state the excluded failure count, and use the separate zero-failure criteria so exclusions cannot hide a failed run. Mark the target **pass** only if every fixed criterion passes. Otherwise mark it **fail** or **inconclusive** when evidence is missing.

## Required workflow

Follow this order and preserve commands plus evidence:

1. Confirm the target is staging using hostname, deployment metadata, container labels/names, URLs, and operator-provided context. Stop before service mutation if staging ownership remains ambiguous.
2. Inspect the application route, request schema, authentication, persistence effects, limiter, connection pools, and timeout chain.
3. Audit hardware, containers, models, service versions, launch arguments, environment-variable names, and current service state.
4. Verify every proposed vLLM or TEI flag against the installed version's own `--help`, image entrypoint help, or version-matched official documentation. Do not assume a flag exists or has current semantics.
5. Freeze deterministic, non-customer request fixtures, seed, warm-up, measured duration/count, repetitions, acceptance criteria, and artifact directory.
6. Record current container state, exact restart commands, free VRAM, and rollback commands.
7. Run the eight mandatory benchmark layers separately.
8. Repeat every important configuration at least three times unless a different count was predeclared and justified. Never compare configurations from one run each.
9. Identify saturation with a concurrency sweep, then perform a reviewed 50-simultaneous full-application test.
10. Attribute latency and errors using client, application, service, GPU, CPU, database, and network evidence.
11. Make a fixed pass/fail/inconclusive decision and separate hardware-independent from hardware-dependent conclusions.
12. Restore the original service state and verify container health.

## Runtime audit

Inspect and record:

- GPU model, NVIDIA driver, CUDA version, compute capability, total/free/used memory, utilization, and active GPU processes
- Docker container names, image names/tags or digests, GPU assignments, state, health, command, and restart policy
- model paths or IDs and revisions, without credentials
- vLLM, TEI, and relevant PyTorch versions
- dtype, quantization, maximum model length, tensor parallelism, pipeline parallelism
- vLLM `gpu_memory_utilization`, `max_num_seqs`, `max_num_batched_tokens`, prefix caching, chunked prefill, and CUDA graph versus eager behavior
- TEI `max_client_batch_size`, `max_concurrent_requests`, `max_batch_tokens` where configured, and input-length limits
- application HTTP and database connection-pool limits, limiter capacity, client/server timeouts, proxy deadlines, and the effective 50-second application deadline

Distinguish `observed`, `inferred`, `default from version`, `unknown`, and `not applicable`. Do not treat absent launch flags as proof of a default until the installed version confirms it.

Prefer read-only commands first. Examples include `nvidia-smi`, `nvidia-smi -q`, `docker ps --no-trunc`, and targeted `docker inspect`. Sanitize environment and command output before saving it. Verify compute capability with an installed tool or version-appropriate runtime API; do not infer it solely from the marketing model name.

## Mandatory benchmark layers

Run and report each layer independently:

1. vLLM alone.
2. TEI embedding alone.
3. TEI reranker alone.
4. vLLM and embedding simultaneously.
5. vLLM and reranker simultaneously.
6. Embedding and reranker simultaneously.
7. All three inference services simultaneously.
8. Full application end to end.

Do not substitute layer 8 for service-level tests. All three inference services may compete for the staging GPU.

## Safe service isolation

Before stopping a service:

1. Prove the environment is staging.
2. Capture container state, image, command, mounts, networks, GPU assignment, restart policy, and health.
3. Derive and record exact restart and health-check commands.
4. Provide exact stop, restore, rollback, and verification commands for human review.
5. Confirm no target is a production container.

For each isolated run, ensure unrelated inference services are stopped or demonstrably idle, record free VRAM, start or confirm the tested service, warm it up, collect the benchmark and metrics, restore the original state, and verify health. Do not run service-stop commands merely because a benchmark was requested; present live commands first and obtain review.

## Measurement rules

- Use monotonic high-resolution clocks for durations and UTC wall-clock timestamps for correlation.
- Include a warm-up phase and exclude it from measured percentiles while reporting warm-up failures separately.
- Use exact model/service configuration, deterministic inputs, and a fixed random seed.
- Record input/output token counts using the model tokenizer where possible; state the counting method.
- Preserve raw per-request data before aggregation.
- Capture synchronized GPU/CPU monitoring and service metrics throughout the measured window.
- Use vLLM Prometheus metrics when available. If enabling per-request metrics, benchmark their overhead before retaining them.
- Avoid automatic retries; they alter offered load and hide overload.
- Use persistent HTTP clients and explicitly size connection pools so client pool wait can be measured rather than confused with server latency.
- Keep TLS verification enabled unless a documented staging-only exception is reviewed.

## Workloads and saturation

For vLLM, cross short/medium/long prompts with short/medium/long outputs and concurrency `1, 5, 10, 20, 50`. Use deterministic generation settings appropriate for benchmarking and record prompt/generated tokens.

For embedding, test one input per request, multiple inputs per client request, concurrent single-input requests, short/realistic/long inputs, and realistic Persian staging fixtures.

For reranking, test realistic Persian queries and question/answer candidates with candidate counts `3, 5, 10, 20, 50`. Record query length, candidate token lengths, total pairs, and verify whether the client sends one batched request rather than one request per candidate.

Define practical saturation as the first sustained region where one or more occur:

- throughput stops increasing materially while offered concurrency rises
- p95 or p99 rises sharply
- vLLM waiting requests or queue time grows continuously
- queue time dominates execution
- KV cache nears exhaustion or preemptions increase
- GPU saturation no longer produces throughput gains
- errors, rejections, timeouts, OOMs, or TEI delays increase
- VRAM pressure causes instability

State the numeric rule used for "materially" and "sharply" before analysis. Report the highest stable operating point and the first saturated point; do not merely report the highest tested concurrency.

## Tuning discipline

Establish a repeated baseline first. Change exactly one major variable per experiment:

1. Record baseline.
2. State the hypothesis and expected effect.
3. Change only one variable.
4. Record the exact change and rollback.
5. Warm up.
6. Repeat the same measured workload.
7. Compare p50, p95, p99, TTFT, throughput, queue time, errors, and resource use.
8. Check retrieval and answer quality when behavior could change.
9. Accept, reject, or mark inconclusive against predeclared criteria.

For vLLM, eligible variables include `gpu_memory_utilization`, `max_model_len`, `max_num_seqs`, `max_num_batched_tokens`, prefix caching, chunked prefill, dtype, quantization, CUDA graph/eager behavior, maximum generation tokens, tensor parallelism, and model replication.

For TEI, test one at a time: `max_concurrent_requests`, `max_client_batch_size`, `max_batch_tokens`, client-side batching, HTTP pool size, model image architecture/tag, and input-length constraints. Never assume increasing concurrency improves throughput; it may only deepen an internal queue.

## Contention and attribution

Calculate percent degradation as:

`100 * (isolated_metric - combined_metric) / isolated_metric` for higher-is-better metrics, and
`100 * (combined_metric - isolated_metric) / isolated_metric` for lower-is-better metrics.

Handle zero denominators explicitly. Compare vLLM alone with vLLM+embedding, vLLM+reranking, and all services; compare embedding alone and reranking alone with all services. Analyze queue time, TTFT, prefill, decode throughput, TEI latency, GPU/VRAM pressure, errors, preemption, rejection, and OOM behavior.

Separate application delay, HTTP connection-pool wait, TEI queueing, Qdrant latency, vLLM queue/prefill/decode, GPU contention, CPU/event-loop/thread-pool bottlenecks, PostgreSQL latency, persistence, and network overhead. Do not attribute uninstrumented time to a convenient component; label it unaccounted.

## Outputs

Write each run under:

`benchmarks/results/inference/<service-or-layer>/<UTC-timestamp>/`

Save raw JSON Lines, CSV, summary JSON, Markdown report, sanitized configuration snapshot, GPU-monitoring output, and service-metrics snapshots. Include timestamp, Git commit, seed, commands, repetitions, hardware metadata, container versions, model revisions, all configurations, workload, warm-up, raw-result paths, percentile method, missing metrics, rollback, and final service-state verification.

## Hardware transfer

Label findings explicitly:

- **Hardware-independent:** async correctness, persistent HTTP clients, request batching, prompt/output-token reduction, unnecessary model-call elimination, connection pooling, cancellation, backpressure, and instrumentation.
- **Hardware-dependent:** `max_num_seqs`, `max_num_batched_tokens`, `gpu_memory_utilization`, replication, tensor parallelism, KV-cache capacity, TEI placement, GPU partitioning, quantization, and maximum service concurrency.

Recommend production experiments for hardware-dependent settings. Two L4 GPUs invite placement, replication, and parallelism choices; aggregate VRAM does not make a single 48 GB allocation.

## Reusable prompts

### Runtime configuration audit

> Use `$ragbot-inference-benchmark` to perform a read-only staging runtime audit. Record GPU/driver/CUDA/compute capability/memory/processes, Docker images and GPU assignments, model paths/revisions, vLLM/TEI/PyTorch versions, verified launch flags, dtype/quantization/model length/parallelism, vLLM scheduler and cache settings, TEI limits, and application pool/timeouts. Verify flags against installed-version help, redact secrets, save a sanitized configuration snapshot, and list unknowns without benchmarking or changing services.

### vLLM isolated benchmark

> Use `$ragbot-inference-benchmark` to design a staging-only isolated vLLM benchmark across short/medium/long prompts and outputs at concurrency 1, 5, 10, 20, and 50. First show service-isolation, rollback, warm-up, metrics, artifact, and live benchmark commands for review. Collect TTFT, queue, prefill, decode, TPOT, throughput, token counts, KV-cache, preemption, errors, GPU/CPU, and repeated-run p50/p95/p99 results. Identify saturation and do not call the service fully optimized.

### TEI embedding isolated benchmark

> Use `$ragbot-inference-benchmark` to design a staging-only isolated TEI embedding benchmark using deterministic, non-customer Persian fixtures. Test single-input requests, multi-input client batches, concurrent singles, and short/realistic/long inputs. Show isolation and rollback commands first; collect latency/queue/batch/tokens, embeddings/s, tokens/s, p50/p95/p99, rejection/error, GPU/VRAM/CPU, raw artifacts, and repeated-run saturation evidence.

### TEI reranker isolated benchmark

> Use `$ragbot-inference-benchmark` to design a staging-only isolated TEI reranker benchmark using deterministic, non-customer Persian queries and candidates. Test 3, 5, 10, 20, and 50 candidates, record query/candidate token lengths, pairs and tokens per second, latency percentiles, rejection/errors, GPU/VRAM, and verify one batched rerank request versus per-candidate calls. Present isolation, live, restore, and rollback commands for review before execution.

### Combined GPU-contention benchmark

> Use `$ragbot-inference-benchmark` to benchmark all mandatory isolated, pairwise, all-service, and full-application layers on staging. Hold workloads/configuration fixed, repeat runs, capture synchronized service/GPU metrics, quantify isolated-to-combined degradation, distinguish client pool waits from service queues, identify the dominant contention mechanism and saturation point, and restore the original container state.

### vLLM tuning matrix

> Use `$ragbot-inference-benchmark` to create a one-variable-at-a-time vLLM tuning matrix from a repeated baseline. Verify each flag against the installed version. For every candidate variable, state the hypothesis, exact single change, fixed workload, repeated runs, quality checks, acceptance rule, and rollback. Compare p50/p95/p99, TTFT, queue, throughput, KV cache, preemption, errors, and GPU/VRAM without transferring RTX 5880 parameters directly to L4.

### TEI tuning matrix

> Use `$ragbot-inference-benchmark` to create a one-variable-at-a-time TEI tuning matrix for embedding and reranking. Test concurrency, client batch, batch-token, HTTP-pool, image/tag, and input constraints independently after version verification. Use repeated fixed workloads and report whether changes increase useful throughput or merely deepen queues, with exact rollback and quality checks.

### Saturation analysis

> Use `$ragbot-inference-benchmark` to analyze these benchmark artifacts. Apply predeclared saturation rules, locate the highest stable and first saturated points, identify the dominant bottleneck, separate every latency stage and unaccounted time, evaluate the 50-simultaneous, 50-second deadline, p95<=20-second criteria as pass/fail/inconclusive, and state missing evidence. Never say fully optimized.

### Staging-to-production recommendation

> Use `$ragbot-inference-benchmark` to turn staging results into a production experiment plan. Separate hardware-independent findings from hardware-dependent parameters, account for one 48 GB RTX 5880 versus two separate 24 GB L4 GPUs, avoid direct parameter transfer, propose placement/replication/parallelism hypotheses, define production-like retests and acceptance criteria, and make no production change.
