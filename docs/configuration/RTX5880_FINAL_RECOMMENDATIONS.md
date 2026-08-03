# RTX 5880 final measured recommendations

Audit and benchmark date: 2026-07-29  
Git revision: `f78e0eda91c55f6dfe871dd9cc366b04394ea730`  
Host: staging `silicon1`  
Endpoint: `POST /api/mobile/v1/talk`

## Outcome

The recommended application admission and HTTP-capacity configuration passed
the strict staging target:

- five synchronized waves of 50 requests;
- 250/250 successful responses;
- p95 18.612 seconds;
- maximum 19.279 seconds;
- 100% completed within 20 seconds;
- zero limiter rejections;
- zero application or client timeouts;
- zero HTTP 5xx responses.

This is a measured staging recommendation for the exact single-worker,
single-RTX-5880, vLLM 0.26.0 and TEI 1.9.3 deployment described below. It is
not proof for multiple FastAPI workers or the two-L4 production deployment.

## Recommended environment values

Only three effective values differ from the unchanged live baseline:

```dotenv
REQUEST_CONCURRENCY_LIMIT=50
TEI_HTTP_MAX_CONNECTIONS=64
VLLM_HTTP_MAX_CONNECTIONS=64
```

Keep these supporting values at their tested settings:

```dotenv
APPLICATION_REQUEST_TIMEOUT_SECONDS=50
REQUEST_ADMISSION_TIMEOUT_SECONDS=12
BLOCKING_CONCURRENCY_LIMIT=16

TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS=16
TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS=30
TEI_HTTP_CONNECT_TIMEOUT_SECONDS=3
TEI_HTTP_READ_TIMEOUT_SECONDS=15
TEI_HTTP_WRITE_TIMEOUT_SECONDS=5
TEI_HTTP_POOL_TIMEOUT_SECONDS=5

VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS=16
VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS=30
VLLM_HTTP_CONNECT_TIMEOUT_SECONDS=3
VLLM_HTTP_READ_TIMEOUT_SECONDS=40
VLLM_HTTP_WRITE_TIMEOUT_SECONDS=5
VLLM_HTTP_POOL_TIMEOUT_SECONDS=3

QDRANT_CONCURRENCY=8
RAG_RETRIEVAL_TOP_K=10
RAG_SEMANTIC_CANDIDATE_LIMIT=50
RAG_RELATED_QUESTIONS_RERANK_THRESHOLD=0.1

RAG_MAX_NEW_TOKENS=500
RAG_CHITCHAT_MAX_NEW_TOKENS=128
RAG_REWRITE_MAX_TOKENS=200

TEI_EMBED_INSERT_BATCH_SIZE=32
TEI_EMBED_MAX_CLIENT_BATCH_SIZE=50
```

The complete secret-free overlay is
`.env.recommended.rtx5880-staging`. Do not replace `.env` with it because the
overlay intentionally omits credentials and service addresses.

## Fixed server configuration

The passing run used the running vLLM container with:

```text
vLLM 0.26.0
tensor_parallel_size=1
max_model_len=4000
max_num_seqs=100
gpu_memory_utilization=0.75
kv_cache_dtype=fp8
prefix_caching=enabled
```

Both TEI 1.9.3 services used:

```text
max_concurrent_requests=100
max_client_batch_size=50
max_batch_tokens=16384
dtype=float16
auto_truncate=true
```

No model-server parameter was changed during the application experiments.

## Controlled results

Every measured configuration used the same synthetic identity/question
fixtures, seed `20260728`, five warm-ups, five burst waves, one FastAPI worker,
and strict acceptance rules.

| Configuration | Requests | Success | p50 | p95 | Maximum | Rejections/timeouts/5xx | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Current: request 32, admission 12, pools 32 | 250 | 85.6% | 13.469 s | 17.434 s* | 20.056 s* | 36 / 0 / 36 | Reject |
| Admission wait 16, request 32, pools 32 | 250 | 98.4% | 15.205 s | 25.996 s* | 28.122 s* | 4 / 0 / 4 | Reject |
| Request 50, pools 32 | 250 | 64.0% | 14.157 s | 16.064 s* | 17.019 s* | 0 / 90 / 90 | Reject |
| Request 50, pools 64 | 250 | 100% | 14.375 s | 18.612 s | 19.279 s | 0 / 0 / 0 | Accept |

`*` Successful-response percentiles exclude failed requests. The failure counts
therefore remain part of every decision.

The matching 30-concurrent comparison for the accepted configuration also
passed: 150/150 successes, p95 15.175 seconds, maximum 16.010 seconds.

## Why the accepted values work

With the original application limiter at 32, two slower scenario waves kept
all 32 slots busy longer than the 12-second admission timeout. Exactly 18 of
50 requests were rejected in each affected wave.

Increasing admission wait to 16 seconds reduced rejection, but serialized work
behind the first 32 and pushed p95 to 26 seconds. A longer wait is therefore
not a solution for the strict 20-second objective.

Raising application admission to 50 without raising HTTP capacity caused
exactly 18 of 50 requests per wave to receive HTTP 504 after roughly 3.9
seconds. Only the first 32 pipelines produced vLLM work. This is consistent
with exhaustion of the 32-connection application HTTP pool.

Admitting 50 requests and providing 64 TEI/vLLM connections removed both
queues. The final run completed every request within 20 seconds.

## Inference and GPU evidence

During the accepted 50-concurrent run:

- GPU utilization averaged 84.2% and reached 100%.
- Minimum observed free VRAM was approximately 5,793 MiB. The extra
  experimental FastAPI process remained resident alongside the original app,
  so this is conservative relative to one application process.
- Maximum observed temperature was 81°C and power reached approximately
  286 W.
- vLLM handled 510 model requests for 255 talk/warm-up requests because
  non-chitchat flows can perform rewrite plus answer generation.
- Average vLLM queue time was approximately 0.418 seconds.
- Average vLLM TTFT was approximately 1.334 seconds.
- Average vLLM request duration was approximately 6.426 seconds.
- No vLLM preemptions were recorded.

The GPU reached saturation transiently, but scheduler queueing and preemption
did not dominate the accepted workload. Do not raise application concurrency
beyond 50 without a new saturation sweep.

## Quality status

The accepted experiment changed only application admission and HTTP socket
capacity. Retrieval settings, prompts, model, quantization, token ceilings and
sampling behavior were unchanged.

All 250 accepted responses were schema-valid and non-empty. Supporting answer
statistics were:

- median length: 223 characters;
- minimum: 93;
- maximum: 638;
- no answer was identical to its query.

Full synthetic query/answer pairs are retained in the run's
`interactions.md` for human review. No automated semantic answer-quality suite
exists, so this report does not claim that semantic quality was independently
certified.

## Deployment instructions

Apply only these three changes to the approved staging configuration:

```dotenv
REQUEST_CONCURRENCY_LIMIT=50
TEI_HTTP_MAX_CONNECTIONS=64
VLLM_HTTP_MAX_CONNECTIONS=64
```

Restart every FastAPI worker. Do not restart vLLM or TEI for these
application-side changes. Verify:

```bash
curl -fsS --max-time 5 http://127.0.0.1:7000/api/health
curl -fsS --max-time 5 http://127.0.0.1:8000/health
curl -fsS --max-time 5 http://127.0.0.1:7997/health
curl -fsS --max-time 5 http://127.0.0.1:7998/health
```

Rollback:

```dotenv
REQUEST_CONCURRENCY_LIMIT=32
TEI_HTTP_MAX_CONNECTIONS=32
VLLM_HTTP_MAX_CONNECTIONS=32
```

Then restart every FastAPI worker and repeat the health checks.

## Recommendations

1. Apply the three measured application values above as one coordinated
   capacity configuration. Using request limit 50 with pools 32 is unsafe.
2. Keep `REQUEST_ADMISSION_TIMEOUT_SECONDS=12`. Do not adopt 16; it measurably
   worsened tail latency and still failed requests.
3. Keep one FastAPI worker until multi-worker capacity is measured. Every
   worker independently creates a 50-request limiter and two 64-connection
   pools; two workers would double offered downstream capacity.
4. Keep the current vLLM/TEI server settings. The full target passed, so server
   tuning is not required for the stated objective.
5. Do not reduce semantic candidates or generation/rewrite token ceilings on
   performance evidence alone. Those changes require retrieval and human
   answer-quality gates.
6. Add separate application metrics for admission wait, HTTP pool wait,
   rewrite, embedding, Qdrant, reranking, vLLM and PostgreSQL. The current load
   tool cannot distinguish a generic downstream 504 from the endpoint's total
   deadline without those timings.
7. The inactive endpoint-level related-question rerank has been removed.
   `agent_graph.py` now owns the only rerank call. Keep
   `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD` as the canonical threshold;
   `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` is legacy and has no active
   runtime effect.
8. Reconcile every generated cleanup manifest with the staging database. The
   load generator does not automatically delete synthetic users or sessions.
9. Pin mutable `latest` Docker tags to immutable digests.
10. Retest on the two-L4 production topology. RTX 5880 scheduler and memory
    results do not transfer directly to two separate 24 GiB GPUs.

## Artifacts

Accepted runs:

- `benchmarks/results/mobile-talk/rtx5880_request50_pool64_c30_20260729T124800Z`
- `benchmarks/results/mobile-talk/rtx5880_request50_pool64_c50_20260729T125100Z`
- `benchmarks/results/metrics/rtx5880_request50_pool64_c30_20260729T124800Z`
- `benchmarks/results/metrics/rtx5880_request50_pool64_c50_20260729T125100Z`

Rejected comparisons are retained under similarly named
`rtx5880_live_baseline`, `rtx5880_admission16`, and
`rtx5880_requestlimit50` directories. They must not be deleted until the
cleanup manifests and conclusions are reviewed.
