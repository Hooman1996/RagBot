# Benchmark Specification

Use this reference for every RagBot inference benchmark. Keep unavailable metrics as `unknown`; never fabricate a value.

## Contents

1. Runtime inspection
2. Metrics
3. Workload matrices
4. Experiment manifest
5. Request records
6. Summary and artifacts
7. Analysis and acceptance
8. Safe command design

## Runtime inspection

Capture a sanitized snapshot with evidence and provenance:

| Area | Required fields |
|---|---|
| Host | UTC timestamp, hostname, environment proof, Git SHA, dirty-worktree indicator |
| GPU | model, UUID or redacted stable label, driver, CUDA, compute capability, total/free/used VRAM, utilization, temperature if useful, active processes |
| Containers | name, container ID, image name/tag/digest, command, state, health, GPU device requests/assignments, restart policy |
| Models | service, model path/ID, revision, tokenizer revision, dtype, quantization, maximum input/model length |
| vLLM | version, PyTorch version, tensor/pipeline parallelism, gpu-memory utilization, max sequences, max batched tokens, prefix cache, chunked prefill, eager/CUDA graph behavior |
| TEI | version and image, model/revision, dtype, max client batch size, max concurrent requests, max batch tokens when supported, input/token limits |
| Application | effective talk path, limiter, application/proxy/client deadlines, HTTP pool size/keepalive/pool timeout, database pool limits |

For each value include `value`, `source`, and `status`: `observed`, `inferred`, `version_default`, `unknown`, or `not_applicable`.

Verify service flags against the running binary or image:

1. Record the exact version or image digest.
2. Capture its entrypoint and launch command.
3. Run the same installed binary/image help safely, without starting a second model server.
4. Match configured flags to help output.
5. Use version-matched official documentation only if help is insufficient.
6. Mark absent or renamed flags rather than translating them silently.

Do not save complete container environments. Extract only an allowlist of non-secret performance keys, redact URL credentials and query strings, and record secret-bearing values only as `set`/`unset`.

## Metrics

### vLLM

Collect when exposed:

- requests running and waiting
- scheduler queue time
- time to first token (TTFT)
- prefill duration
- decode duration
- time per output token (TPOT)
- output tokens per second
- prompt and generated tokens
- end-to-end latency
- KV-cache utilization and cache hits
- preemption count
- rejections and status/failure reason
- GPU utilization and VRAM utilization
- CPU utilization
- model-server errors

Use vLLM Prometheus metrics when available and preserve a start snapshot, end snapshot, and measured-window scrape series. Verify metric names in the installed version. Correlate counter deltas and histogram buckets to the exact test window. If per-request metric/logging features are proposed, run A/B benchmarks with the feature off and on before permanent enablement.

### TEI embedding

Collect:

- client request latency
- queue latency where exposed
- client input count and server batch size where exposed
- input token count
- embeddings per second
- tokens per second
- p50, p95, p99
- errors and error rate
- rejected requests and rejected-request rate
- GPU utilization, VRAM utilization, and CPU utilization

Report both client-request throughput and embedding-item throughput for batched requests.

### TEI reranking

Collect:

- request latency
- query token length
- candidate count and individual candidate token lengths
- total pair count
- pairs per second
- tokens per second, with the exact token accounting definition
- p50, p95, p99
- errors and error rate
- rejected requests and rejected-request rate
- GPU utilization and VRAM utilization

Trace or inspect the staging client safely to confirm whether one query plus all candidates becomes one TEI request. Flag an N-requests-for-N-candidates pattern as a client behavior requiring separate evaluation.

### Full application

Collect or instrument non-sensitive durations for:

- client scheduling and HTTP connection-pool wait
- proxy/server ingress
- FastAPI admission/limiter/event-loop/thread-pool delay
- PostgreSQL/session reads and writes
- embedding request queue and execution
- Qdrant search
- reranking request queue and execution
- each vLLM call's queue, prefill, and decode
- response persistence/serialization
- network transit and unaccounted remainder

Use request IDs or synthetic run IDs, never customer identifiers or prompts, for correlation.

## Workload matrices

### vLLM

Run the Cartesian matrix:

- prompt classes: short, medium, long
- output caps: short, medium, long
- concurrency: 1, 5, 10, 20, 50

Define token ranges before the run and record actual prompt/generated counts. Use fixed prompts and seed. If sampling cannot be deterministic in the serving stack, use deterministic decoding and document possible residual nondeterminism. Report early-stop output lengths rather than pretending the cap was generated.

### Embedding

Include:

- one input per request
- multiple inputs in one request at declared sizes
- concurrent single-input requests
- short, realistic RagBot, and long input classes
- realistic Persian text from approved staging fixtures

Sweep concurrency through at least 1, 5, 10, 20, and 50 where safe. Keep total embedded items and offered load explicit so batching comparisons are fair.

### Reranking

Use fixed Persian queries and question/answer candidates from approved staging fixtures. Test candidate counts 3, 5, 10, 20, and 50 across realistic token-length classes. Record truncated inputs and server limits. Sweep safe concurrency and distinguish requests per second from pairs per second.

### Combined layers

Run all eight layers from `SKILL.md`. For simultaneous services:

- use a barrier or scheduled start
- declare per-service offered load
- use the same isolated workload during combined runs
- capture one synchronized GPU/CPU/metrics timeline
- avoid client-machine saturation
- repeat service start order across runs or hold it fixed and record it

For the full application, prove 50 requests were released simultaneously and size the client connection pool to at least the required in-flight load. Report client scheduling lag and pool wait.

## Experiment manifest

Freeze a machine-readable manifest before the measured run:

```json
{
  "run_id": "inference-<layer>-<UTC timestamp>",
  "layer": "vllm|embedding|reranker|vllm_embedding|vllm_reranker|embedding_reranker|all_services|application",
  "environment": "staging",
  "git_sha": "<sha>",
  "seed": 20260728,
  "warmup": {"requests": 0, "duration_s": 0},
  "measured": {"requests": 0, "duration_s": 0, "repetitions": 3},
  "concurrency": 0,
  "acceptance": {},
  "config_snapshot": "config.json",
  "fixture_id": "<non-sensitive fixture version>"
}
```

Choose request-count or duration semantics explicitly. If both apply, state the stopping rule. Important comparisons require multiple runs per configuration; default to at least three.

## Request records

Use monotonic high-resolution timestamps for durations. JSONL and CSV should contain one measured attempt per row with applicable fields:

- schema version, run/repetition/layer/request IDs
- UTC start and monotonic start/end/duration
- intended start, actual start, and scheduler lag
- service, request shape, fixture label, input count, candidate count
- prompt/query/candidate/input token counts and generated tokens
- queue, TTFT, prefill, decode, TPOT, and end-to-end durations
- HTTP pool wait and application stage timings
- status, sanitized error category, HTTP status, rejection, timeout, cancellation
- response size or output-token count, not full generated text by default

Define failures exclusively: client scheduling failure, pool timeout, connect timeout, read/deadline timeout, rejection, HTTP 4xx, HTTP 5xx, invalid response, cancellation, server/model error, OOM, or unexpected sanitized exception. Do not retry automatically.

## Summary and artifacts

Create:

```text
benchmarks/results/inference/<layer>/<UTC-timestamp>/
├── manifest.json
├── requests.jsonl
├── requests.csv
├── summary.json
├── report.md
├── config.json
├── commands.txt
├── gpu-monitor.csv
├── service-metrics-start.txt
├── service-metrics-series.*
└── service-metrics-end.txt
```

Names may vary only when the report maps them clearly. Save outputs incrementally or atomically so interruption preserves completed attempts.

Summarize per run and across repetitions:

- attempts, successes, failures, success/error/rejection/timeout rates
- min, max, mean, median, standard deviation, p50, p95, p99
- throughput and useful-work throughput
- token/item/pair throughput as applicable
- offered versus achieved load
- warm-up results separately
- GPU/VRAM/CPU statistics
- service queue, model execution, client pool, and unaccounted time

State the percentile algorithm. Prefer percentile statistics over averages for acceptance. Never convert failures to zero-latency observations. If latency percentiles exclude failed requests, label them success-only and prominently report the excluded count.

`summary.json` must include the frozen criteria, actual values, criterion-level pass/fail/unknown, and overall `pass`, `fail`, or `inconclusive`.

## Analysis and acceptance

Before data collection define numeric saturation signals, for example:

- throughput gain below a declared percentage across the next concurrency step
- p95 or p99 increase above a declared percentage
- waiting count or queue time rising throughout a steady measured window
- error/timeout/rejection rate above a declared threshold
- KV cache, preemption, or VRAM thresholds supported by the installed service

Do not invent universal thresholds. Report sensitivity when the conclusion depends on a chosen threshold.

For degradation calculations:

- higher is better: `100 * (isolated - combined) / isolated`
- lower is better: `100 * (combined - isolated) / isolated`

Report negative degradation as an improvement. Mark undefined ratios when the isolated value is zero. Compare repetition distributions, not only aggregated means.

Evaluate the application target using the predeclared policy. At minimum address:

- exactly 50 simultaneous attempts
- p95 end-to-end latency at most 20 seconds
- success rate at least 99% (all 50 must succeed at this sample size)
- zero application-deadline timeouts, client timeouts, request rejections, and HTTP 5xx responses
- no request exceeding the 50-second application deadline

Use:

- **pass:** all required evidence exists and every criterion passes
- **fail:** evidence exists and at least one criterion fails
- **inconclusive:** required evidence or valid workload execution is missing

Name the dominant bottleneck only when correlated evidence supports it. Otherwise list ranked hypotheses and the next discriminating experiment.

## Safe command design

Present live commands as a reviewed runbook with:

1. read-only environment proof
2. state capture
3. sanitized configuration capture
4. exact stop/idle isolation commands
5. health checks
6. warm-up
7. measured benchmark
8. metrics collection
9. restoration
10. post-restore health verification
11. rollback

Use explicit container names resolved from read-only inspection. Never use broad globs, production-looking hosts, or destructive cleanup. Avoid saving unfiltered `docker inspect`, environments, headers, tokens, or prompts in artifacts. Make rollback idempotent where practical and explain what state it restores.
