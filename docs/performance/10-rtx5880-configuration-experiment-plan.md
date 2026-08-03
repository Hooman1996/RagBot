# RTX 5880 configuration experiment plan

Status: the initial plan was generated for review. On 2026-07-29, the user
authorized live staging tests. The accepted configuration and all executed
results are documented in
`docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md`. The commands below remain
the reusable experiment protocol.

## Acceptance contract

Primary endpoint: `POST /api/mobile/v1/talk`.

Every accepted configuration must demonstrate, across five repeated waves:

- 50 simultaneous requests per wave.
- 100% success for the strict target (and therefore at least 99%).
- Zero limiter rejections.
- Zero client timeouts.
- Zero application deadline timeouts.
- Zero HTTP 5xx responses.
- p95 no greater than 20 seconds.
- Every successful request no greater than 20 seconds.
- Reviewed retrieval and answer quality with no material regression.

A 30-request run is a diagnostic gate, not acceptance. A single 50-request
wave is not repeatability evidence.

## Safety gates

Before any live request:

1. Confirm the target is staging and the direct path is
   `/api/mobile/v1/talk`.
2. Confirm the synthetic identity fixture is reserved and absent from
   production. The endpoint creates persistent users/sessions/messages.
3. Confirm an authorized cleanup owner and rehearse the manual cleanup
   manifest process. `--cleanup` records a manifest; it does not delete data.
4. Capture the Git revision, complete process/container commands, image
   digests, worker count, GPU state and background workload.
5. Restore a running, reviewed vLLM service. It was absent during this audit.
6. Add or enable application stage telemetry before pool, Qdrant or rewrite
   conclusions. Current code does not emit the timing headers consumed by the
   load tool.
7. Use only synthetic prompts. Artifacts intentionally contain full synthetic
   queries, answers and identity values; store them in a restricted result
   directory and do not commit them.

## Fixed workload

Hold these constant for every comparison:

```text
scenario fixture: benchmarks/load/fixtures/persian_banking_scenarios.json
identity fixture: benchmarks/load/fixtures/staging_synthetic_identities.json
scenario: banking-faq
seed: 20260728
workload: synchronized burst
warm-up: 5 requests per invocation
repetitions: 5 waves
client read timeout: 55 seconds
acceptance: --strict
```

The runner writes `requests.jsonl`, `requests.csv`, `summary.json`,
`report.md`, `interactions.md`, and a manual cleanup manifest. Full answers
must be manually reviewed using the same rubric and blind ordering.

## Baseline capture and application launch

Do not edit `.env`. An environment value on the process command line overrides
the `.env` value because `load_dotenv()` does not override exported values.

Record the current baseline without values that may contain secrets:

```bash
git rev-parse HEAD
pgrep -af 'uvicorn|gunicorn|main:app'
docker ps --no-trunc \
  --format '{{.Names}}|{{.Image}}|{{.Command}}|{{.Ports}}'
nvidia-smi \
  --query-gpu=timestamp,name,memory.total,memory.used,memory.free,utilization.gpu,power.draw \
  --format=csv
nvidia-smi \
  --query-compute-apps=pid,process_name,used_memory \
  --format=csv
```

The direct one-worker experimental application command is:

```bash
mkdir -p /tmp/ragbot-rtx5880-experiments
env REQUEST_CONCURRENCY_LIMIT=32 \
  python3 -m uvicorn main:app \
  --host 127.0.0.1 \
  --port 7000 \
  --workers 1 \
  > /tmp/ragbot-rtx5880-experiments/fastapi.log 2>&1 &
echo "$!" > /tmp/ragbot-rtx5880-experiments/fastapi.pid
```

For a one-variable experiment, add exactly one override before `python3`.
Example:

```bash
env REQUEST_CONCURRENCY_LIMIT=24 \
  python3 -m uvicorn main:app \
  --host 127.0.0.1 \
  --port 7000 \
  --workers 1
```

If the real staging deployment uses a service manager, reproduce its exact
command and worker count instead. Do not compare a one-worker experiment to an
unknown multi-worker baseline.

Health checks:

```bash
curl -fsS --max-time 5 http://127.0.0.1:7000/api/health | jq
curl -fsS --max-time 3 http://127.0.0.1:7997/health
curl -fsS --max-time 3 http://127.0.0.1:7998/health
curl -fsS --max-time 3 http://127.0.0.1:8000/health
curl -fsS --max-time 3 http://127.0.0.1:8000/v1/models | jq \
  '{model_ids: [.data[].id]}'
```

`/api/health` only checks application object presence; the separate downstream
checks are mandatory.

## Exact first benchmark command

This is the first measured command after a one-request smoke test and cleanup.
It is five 30-request waves, not the unauthorized 50-request acceptance run:

```bash
run_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
result_dir="benchmarks/results/mobile-talk/rtx5880_baseline_current_c30_${run_stamp}"
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url http://127.0.0.1:7000 \
  --allow-http \
  --endpoint /api/mobile/v1/talk \
  --workload-mode burst \
  --concurrency 30 \
  --repetitions 5 \
  --warmup-requests 5 \
  --scenario banking-faq \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --seed 20260728 \
  --request-timeout 55 \
  --connect-timeout 5 \
  --write-timeout 10 \
  --pool-timeout 5 \
  --max-connections 50 \
  --max-keepalive-connections 50 \
  --strict \
  --cleanup \
  --output-dir "$result_dir"
```

The preceding state-changing smoke command is the same command with
`--concurrency 1 --repetitions 1 --warmup-requests 0 --scenario banking-smoke`
and a unique `rtx5880_smoke_c1_...` result directory.

After review and explicit approval, the matching 50-request acceptance command
changes only these two arguments and the directory label:

```text
--concurrency 50
--output-dir benchmarks/results/mobile-talk/rtx5880_baseline_current_c50_<UTC>
```

## Reusable exact case runner

The following shell function generates uniquely named 30- and 50-request
result directories. It assumes the application has already been restarted with
exactly the case value. It does not restart anything.

```bash
run_case () {
  case_name="$1"
  case_scenario="${2:-banking-faq}"
  for case_concurrency in 30 50; do
    case_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    case_dir="benchmarks/results/mobile-talk/rtx5880_${case_name}_c${case_concurrency}_${case_stamp}"
    python3 benchmarks/load/mobile_talk_load_test.py \
      --base-url http://127.0.0.1:7000 \
      --allow-http \
      --endpoint /api/mobile/v1/talk \
      --workload-mode burst \
      --concurrency "$case_concurrency" \
      --repetitions 5 \
      --warmup-requests 5 \
      --scenario "$case_scenario" \
      --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
      --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
      --seed 20260728 \
      --request-timeout 55 \
      --connect-timeout 5 \
      --write-timeout 10 \
      --pool-timeout 5 \
      --max-connections 50 \
      --max-keepalive-connections 50 \
      --strict \
      --cleanup \
      --output-dir "$case_dir" || return
  done
}
```

The 50 branch is intentionally visible and must not be invoked until the
command and staging cleanup are approved.

## Metrics capture

Start capture immediately before each `run_case`, using the same case name:

```bash
case_name='baseline_current'
metrics_dir="benchmarks/results/metrics/${case_name}_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$metrics_dir"
nvidia-smi dmon \
  --select pucvmet \
  --delay 1 \
  --count 1800 \
  > "$metrics_dir/nvidia-smi-dmon.txt" &
echo "$!" > "$metrics_dir/nvidia-smi-dmon.pid"
curl -fsS http://127.0.0.1:8000/metrics \
  > "$metrics_dir/vllm-before.prom"
curl -fsS http://127.0.0.1:7997/metrics \
  > "$metrics_dir/tei-embed-before.prom"
curl -fsS http://127.0.0.1:7998/metrics \
  > "$metrics_dir/tei-rerank-before.prom"
```

After the case:

```bash
curl -fsS http://127.0.0.1:8000/metrics \
  > "$metrics_dir/vllm-after.prom"
curl -fsS http://127.0.0.1:7997/metrics \
  > "$metrics_dir/tei-embed-after.prom"
curl -fsS http://127.0.0.1:7998/metrics \
  > "$metrics_dir/tei-rerank-after.prom"
kill "$(cat "$metrics_dir/nvidia-smi-dmon.pid")"
```

These commands capture server aggregates. Correlating per-request vLLM queue
time, TTFT, prefill/decode, TEI queueing, HTTP pool wait, Qdrant wait and
PostgreSQL latency requires request IDs and application spans/metrics. The
current application does not emit them. Do not interpret a null timing column
as zero.

## Experiment matrix

Run an unchanged baseline immediately before each family. Apply one major
variable, restart the affected process, run `run_case`, restore the baseline,
and repeat. Randomize candidate order when practical.

### A. Request admission

Hold all other settings at the captured baseline:

```bash
REQUEST_CONCURRENCY_LIMIT=24  # restart FastAPI; run_case request_limit_24
REQUEST_CONCURRENCY_LIMIT=32  # restart FastAPI; run_case request_limit_32
REQUEST_CONCURRENCY_LIMIT=40  # restart FastAPI; run_case request_limit_40
REQUEST_CONCURRENCY_LIMIT=50  # restart FastAPI; run_case request_limit_50
```

Record limiter rejections, admission wait, vLLM/TEI queueing, GPU saturation
and strict tail latency. Higher is not inherently better.

### B. Admission wait

Use the selected/baseline request limit and change only:

```bash
REQUEST_ADMISSION_TIMEOUT_SECONDS=8   # run_case admission_wait_8s
REQUEST_ADMISSION_TIMEOUT_SECONDS=12  # run_case admission_wait_12s
REQUEST_ADMISSION_TIMEOUT_SECONDS=16  # run_case admission_wait_16s
```

For mobile, this wait is inside the 50-second total deadline
(`mobile_api.py:85-95`). Measure wait explicitly before attributing changes.

### C. HTTP pools

The required first sweep treats downstream socket capacity as one paired major
factor:

```bash
TEI_HTTP_MAX_CONNECTIONS=32 VLLM_HTTP_MAX_CONNECTIONS=32  # run_case http_pools_32
TEI_HTTP_MAX_CONNECTIONS=48 VLLM_HTTP_MAX_CONNECTIONS=48  # run_case http_pools_48
TEI_HTTP_MAX_CONNECTIONS=64 VLLM_HTTP_MAX_CONNECTIONS=64  # run_case http_pools_64
```

Keep keepalive limits at or below max connections. This paired sweep identifies
whether the shared client-capacity hypothesis matters; it does not identify
which client. If a change appears beneficial, repeat two isolation series,
changing TEI only and vLLM only. Do not recommend an increase without measured
pool-acquisition wait.

### D. Qdrant concurrency

```bash
QDRANT_CONCURRENCY=4   # run_case qdrant_concurrency_4
QDRANT_CONCURRENCY=8   # run_case qdrant_concurrency_8
QDRANT_CONCURRENCY=16  # run_case qdrant_concurrency_16
```

Add Qdrant semaphore-wait timing first. Watch blocking-runner and PostgreSQL
contention because Qdrant calls run in the shared blocking runner.

### E. Semantic candidate count

```bash
RAG_SEMANTIC_CANDIDATE_LIMIT=20  # run_case semantic_candidates_20
RAG_SEMANTIC_CANDIDATE_LIMIT=30  # run_case semantic_candidates_30
RAG_SEMANTIC_CANDIDATE_LIMIT=50  # run_case semantic_candidates_50
```

For every value, run retrieval evaluation with the same fixture and limit:

```bash
quality_dir="benchmarks/results/retrieval/semantic_candidates_20"
mkdir -p "$quality_dir"
python3 benchmarks/embedding/tei_query_task_equivalence.py local \
  --fixture benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json \
  --model /root/models/models--jinaai--jina-embeddings-v5-text-small-retrieval \
  --device cpu \
  --output "$quality_dir/local.json"
python3 benchmarks/embedding/tei_query_task_equivalence.py tei \
  --fixture benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json \
  --tei-url http://127.0.0.1:7997 \
  --output "$quality_dir/tei.json"
python3 benchmarks/embedding/tei_query_task_equivalence.py analyze \
  --fixture benchmarks/embedding/fixtures/persian_faq_retrieval_eval.json \
  --local-results "$quality_dir/local.json" \
  --tei-results "$quality_dir/tei.json" \
  --qdrant-url http://127.0.0.1:6333 \
  --collection hihelp_embeddings \
  --limit 20 \
  --output "$quality_dir/analysis.json" \
  --markdown-output "$quality_dir/report.md"
```

Repeat with directory/limit 30 and 50. Confirm the live collection name before
running. Reject a candidate with material top-1/top-3/recall/MRR or answer
quality regression.

### F. Answer output ceiling

```bash
RAG_MAX_NEW_TOKENS=256  # run_case answer_tokens_256
RAG_MAX_NEW_TOKENS=384  # run_case answer_tokens_384
RAG_MAX_NEW_TOKENS=500  # run_case answer_tokens_500
```

Record vLLM completion token counts, finish reason, answer length, completeness
and latency. The current load tool records text/length but not OpenAI usage or
finish reason; add safe numeric telemetry before deciding.

### G. Rewrite ceiling

```bash
RAG_REWRITE_MAX_TOKENS=64   # run_case rewrite_tokens_64
RAG_REWRITE_MAX_TOKENS=128  # run_case rewrite_tokens_128
RAG_REWRITE_MAX_TOKENS=256  # run_case rewrite_tokens_256
```

Record actual rewrite tokens and a synthetic rewrite text artifact. Flag a
rewrite if it exceeds the reviewed Persian query-length bound, is empty,
changes topic, or merely repeats history. Current code has no such validation;
instrument it before drawing conclusions. Do not include 1000 as a candidate.

### H. Chitchat ceiling

Use a fixed `banking-mixed` or dedicated chitchat fixture for all candidates:

```bash
RAG_CHITCHAT_MAX_NEW_TOKENS=96   # run_case chitchat_tokens_96 banking-mixed
RAG_CHITCHAT_MAX_NEW_TOKENS=128  # run_case chitchat_tokens_128 banking-mixed
RAG_CHITCHAT_MAX_NEW_TOKENS=200  # run_case chitchat_tokens_200 banking-mixed
```

Review tone, completeness, repetition, finish reason and actual token count.

### I. vLLM scheduler

This family is blocked until the intended model and current vLLM command are
restored and a baseline saturation point is measured. Verify every flag with:

```bash
docker run --rm --gpus all --entrypoint vllm \
  vllm/vllm-openai:latest serve --help=all
```

Then:

1. Sweep `max_num_seqs` around observed running+waiting saturation, e.g. the
   nearest supported/bracket values below, at and above it.
2. Restore the winning/baseline `max_num_seqs`.
3. Sweep `max_num_batched_tokens` around the observed token batch.
4. Test prefix caching and chunked prefill separately only after these numeric
   sweeps.

Change one server flag, recreate vLLM, warm it, run both load cases, and capture
queue time, TTFT, prefill/decode, tokens/s, KV-cache usage and preemptions.
Never choose values solely from the historical `max_num_seqs=100`.

### J. TEI

For embedding and reranker separately:

```text
max_concurrent_requests: 32, 64, 100
max_batch_tokens: 8192, 16384
```

Change one flag and one service at a time using the recreation pattern in
`docs/configuration/RTX5880_MODEL_SERVER_BASELINE.md`. For every case run:

1. Service-only synthetic embedding/reranking warm-up.
2. Isolated TEI benchmark.
3. The same benchmark while vLLM is active but idle.
4. The same benchmark during fixed vLLM generation.
5. Full 30 and reviewed 50 talk cases.

Capture request/queue/inference durations, queue depth, batch size/tokens, GPU
memory/utilization and failures. Test embedding and reranking independently;
their input lengths and work differ.

## Quality review

There is no repository-defined automated answer-quality scorer. For every
quality-sensitive candidate:

1. Blind the configuration label in `interactions.md`.
2. Review every answer for factual grounding, completeness, refusal behavior,
   Persian clarity, unsupported claims and truncation.
3. For rewrites, review topic preservation and resolved references.
4. For related questions, score relevance and duplicates.
5. Reject any material regression even if latency improves.

Store reviewer decisions beside the result directory. Do not use customer
prompts or answers.

## Comparison table

For every 30- and 50-request case, record:

| Area | Required measures |
|---|---|
| Endpoint | success, limiter rejection, client timeout, application timeout, HTTP 5xx, p50/p90/p95/p99/max, throughput, percent within 20 s |
| GPU | utilization, memory, power, OOM |
| vLLM | running/waiting, queue, TTFT, prefill, decode, prompt/output tokens/s, KV-cache, preemptions |
| TEI | request, queue, tokenization and inference duration; queue; batch requests/tokens |
| Qdrant | semaphore wait and query duration |
| HTTP | pool acquisition wait by TEI/vLLM client |
| PostgreSQL | connect/query/commit duration and errors |
| Quality | answer length/tokens/finish reason, retrieval metrics, blinded answer review |

## Stop conditions

Stop the current run and restore baseline on any GPU OOM, sustained thermal or
power anomaly, production-target uncertainty, real-customer data discovery,
unexpected database target, repeated 5xx/deadline failures, or loss of cleanup
ownership.

## Exact rollback

For a direct experimental FastAPI process:

```bash
kill "$(cat /tmp/ragbot-rtx5880-experiments/fastapi.pid)"
unset APPLICATION_REQUEST_TIMEOUT_SECONDS REQUEST_CONCURRENCY_LIMIT \
  REQUEST_ADMISSION_TIMEOUT_SECONDS BLOCKING_CONCURRENCY_LIMIT \
  TEI_HTTP_MAX_CONNECTIONS TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS \
  TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS TEI_HTTP_CONNECT_TIMEOUT_SECONDS \
  TEI_HTTP_READ_TIMEOUT_SECONDS TEI_HTTP_WRITE_TIMEOUT_SECONDS \
  TEI_HTTP_POOL_TIMEOUT_SECONDS VLLM_HTTP_MAX_CONNECTIONS \
  VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS \
  VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS VLLM_HTTP_CONNECT_TIMEOUT_SECONDS \
  VLLM_HTTP_READ_TIMEOUT_SECONDS VLLM_HTTP_WRITE_TIMEOUT_SECONDS \
  VLLM_HTTP_POOL_TIMEOUT_SECONDS QDRANT_CONCURRENCY \
  RAG_RETRIEVAL_TOP_K RAG_SEMANTIC_CANDIDATE_LIMIT \
  RAG_RELATED_QUESTIONS_RERANK_THRESHOLD \
  MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD RAG_MAX_NEW_TOKENS \
  RAG_CHITCHAT_MAX_NEW_TOKENS RAG_REWRITE_MAX_TOKENS
python3 -m uvicorn main:app \
  --host 127.0.0.1 \
  --port 7000 \
  --workers 1 \
  > /tmp/ragbot-rtx5880-experiments/fastapi.log 2>&1 &
echo "$!" > /tmp/ragbot-rtx5880-experiments/fastapi.pid
curl -fsS --max-time 5 http://127.0.0.1:7000/api/health | jq
```

This reloads the unchanged `.env`; it does not edit it. If staging normally
uses another service command, rollback means restart that exact recorded
baseline command instead. TEI/vLLM container rollback is specified in
`RTX5880_MODEL_SERVER_BASELINE.md`.
