# RTX 5880 staging environment recommendations

Audit date: 2026-07-29  
Repository revision inspected: `f78e0eda91c55f6dfe871dd9cc366b04394ea730`  
Primary endpoint: `POST /api/mobile/v1/talk`

> **Measured update:** Live testing later on 2026-07-29 established a passing
> application configuration of `REQUEST_CONCURRENCY_LIMIT=50`,
> `TEI_HTTP_MAX_CONNECTIONS=64`, and `VLLM_HTTP_MAX_CONNECTIONS=64`, with all
> other performance/quality values retained at their live settings. See
> `RTX5880_FINAL_RECOMMENDATIONS.md`. That measured report supersedes the
> pre-experiment hypotheses below.

## Decision summary

The generated baseline is a **hypothesis**, not a proven optimized
configuration. Do not replace `.env` with it. The correct first comparison is
the unchanged current configuration, followed by one-variable experiments.

A prior artifact at
`benchmarks/results/mobile-talk/20260728T125841Z/report.md:1-55` recorded one
50-request wave with 100% success, p95 18.951 seconds, and maximum 19.204
seconds. It used an older Git revision, no warm-up, one repetition, unknown
live limiter/model-server configuration, and relaxed configured gates of 35
seconds p95 and 40 seconds maximum. It is useful evidence, but it does not
prove repeatability or the requested strict five-wave acceptance target.

## Effective configuration capture

### What was actually running

| Item | Observed effective state |
|---|---|
| Host | `silicon1` |
| GPU | NVIDIA RTX 5880 Ada Generation, 49,140 MiB reported memory |
| Driver / CUDA capability | Driver 595.58.03; driver-reported CUDA 13.2; compute capability 8.9 |
| ECC | `nvidia-smi -q` reported ECC disabled |
| Idle GPU | 0% utilization; 3,059 MiB used; 45,453 MiB free at capture |
| TEI embedding | Running; 1,538 MiB GPU memory |
| TEI reranker | Running; 1,506 MiB GPU memory |
| vLLM | No running host process or container; 0 MiB current allocation |
| FastAPI | No running Uvicorn/Gunicorn/FastAPI process |
| FastAPI workers | Effective current count 0; deployed count therefore not observable |

The prospective direct command `python3 main.py` creates one Uvicorn worker
because `main.py:1476-1480` calls `uvicorn.run` without `workers`. An external
Uvicorn/Gunicorn command could use more; no repository deployment unit was
found. Every worker would create its own request semaphore, blocking runner,
TEI/vLLM pools, Qdrant semaphore, and service clients (`main.py:213-319`).
Therefore `N` workers multiply each configured limit by approximately `N`.

### Environment precedence

`main.py:12-15`, `utils/RagSystem.py:14-15`, and
`utils/persian_hybrid_search.py:21-24` call `load_dotenv()` without
`override=True`. The order for the direct application entry point is:

1. Values already exported in the FastAPI process environment.
2. Missing keys filled from the discovered `.env`.
3. Defaults in `utils/performance_config.py:83-193`.
4. External Uvicorn/vLLM/TEI command-line flags for their own processes.

The audit shell had no exported overrides for the 28 performance variables.
Because FastAPI was not running, “current effective” below means the value a
new direct one-worker start would receive now, not a claim about an absent
process.

### External services

| Service | Effective runtime |
|---|---|
| TEI embedding | `ghcr.io/huggingface/text-embeddings-inference:cuda-1.9`, immutable image digest recorded locally; TEI 1.9.3; host port 7997 to container port 80 |
| TEI reranker | Same image/version; host port 7998 to container port 80 |
| Qdrant | `qdrant/qdrant:v1.16.2`, ports 6333/6334 |
| PostgreSQL | `postgres:latest`, port 5432; mutable tag prevents exact version reconstruction from the name |
| MinIO | `minio/minio`, ports 9000/9001; mutable tag prevents exact version reconstruction from the name |
| vLLM | Not running. Locally installed image identifies vLLM 0.26.0 and PyTorch 2.11.0+cu130 |

Both TEI containers use NVIDIA runtime, GPU 0, the same host model mount, Docker
bridge networking, and restart policy `no`. Neither is Compose-managed. The
effective TEI arguments are documented in
`RTX5880_MODEL_SERVER_BASELINE.md`. No current vLLM command exists to capture.
A historical prose file, `previous-async-tei-proposal.txt:57-76`, describes
vLLM settings, but it is not a deployment source and is not current evidence.

## Application variable classifications

“Candidate” is the value in `.env.recommended.rtx5880-staging`, not a measured
winner. Every value is read at import/startup and requires a FastAPI restart.
“Higher?” answers whether increasing the value is always beneficial; for every
row the answer is no.

| Variable | Class | Current effective | Code default | Candidate / safe test range | Expected effect and principal risk | Quality effect | References |
|---|---|---:|---:|---|---|---|---|
| `APPLICATION_REQUEST_TIMEOUT_SECONDS` | Correctness / timeout | 50 s | 50 s, maximum 50 | 50; do not sweep above contract | More time reduces deadline failures but violates the external contract above 50; lower values fail slow work sooner | None directly; truncated/fallback responses possible on failure | `utils/performance_config.py:85-87`; `mobile_api.py:85-100` |
| `REQUEST_CONCURRENCY_LIMIT` | Application admission | 32 | 32 | 32 candidate; test 24/32/40/50 | Higher admits more simultaneous pipelines but increases GPU, DB, thread and queue contention; limit is per worker | Indirect if overload causes failures | `main.py:86,222-223,361`; `mobile_api.py:85-95` |
| `REQUEST_ADMISSION_TIMEOUT_SECONDS` | Application admission / timeout | 12 s | 12 s | 12; test 8/12/16 | Higher lets queued requests wait longer; it does not increase processing capacity | None directly | `utils/performance_config.py:91-93`; `utils/concurrency.py:99-117` |
| `BLOCKING_CONCURRENCY_LIMIT` | Application admission for sync work | 16 | 16 | 16; test only after thread-wait telemetry | Higher can unblock DB/BM25 work but increases threads, connections and CPU contention | None directly | `main.py:87,222`; `utils/concurrency.py:15-88` |
| `TEI_HTTP_MAX_CONNECTIONS` | Client connection pool | 32 | 32 | 32; test paired pool capacity 32/48/64 only after pool-wait timing | Higher permits more TEI sockets but can overload TEI/shared GPU | None directly | `main.py:254-274`; `utils/persian_hybrid_search.py:252-266` |
| `TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS` | Client connection pool | 16 | 16 | 32 candidate; safe range 16-64 and never above max connections | More retained sockets can avoid handshakes; costs sockets and can retain stale connections | None | `utils/performance_config.py:100-102,164-171` |
| `TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS` | Client connection pool | 30 s | 30 s | 30; test 15-60 only if churn is observed | Longer retains idle sockets; shorter reconnects more | None | `utils/performance_config.py:103-105`; `main.py:260-268` |
| `TEI_HTTP_CONNECT_TIMEOUT_SECONDS` | Timeout | 3 s | 3 s | 3; safe 2-5 | Higher masks network/connect faults longer | None | `utils/performance_config.py:106-108`; `main.py:254-259` |
| `TEI_HTTP_READ_TIMEOUT_SECONDS` | Timeout | 15 s | 15 s | 15; safe 10-20 with failure review | Higher tolerates TEI queue/inference but consumes more endpoint budget | None unless fallback/failure behavior changes | Same as above |
| `TEI_HTTP_WRITE_TIMEOUT_SECONDS` | Timeout | 5 s | 5 s | 5; safe 3-10 | Higher tolerates slow request upload; normal payloads are small | None | Same as above |
| `TEI_HTTP_POOL_TIMEOUT_SECONDS` | Pool admission timeout | 5 s | 3 s | 5; test 3/5 only after measuring waits | Higher waits for a socket instead of failing, but hides undersized pools | None | `utils/performance_config.py:115-117`; `main.py:254-259` |
| `VLLM_HTTP_MAX_CONNECTIONS` | Client connection pool | 32 | 32 | 32; test paired pool capacity 32/48/64 after pool telemetry | Higher only helps if sockets are the bottleneck; vLLM scheduler/GPU may queue instead | None directly | `main.py:275-309`; `utils/RagSystem.py:76-108` |
| `VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS` | Client connection pool | 16 | 16 | 32 candidate; safe range 16-64 and not above max | Same trade-off as TEI keepalive | None | `utils/performance_config.py:127-129,181-187` |
| `VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS` | Client connection pool | 30 s | 30 s | 30; safe 15-60 | Same trade-off as TEI expiry | None | `utils/performance_config.py:130-132`; `main.py:284-294` |
| `VLLM_HTTP_CONNECT_TIMEOUT_SECONDS` | Timeout | 3 s | 3 s | 3; safe 2-5 | Higher delays detection of an unavailable server | None | `utils/performance_config.py:133-135`; `main.py:276-283` |
| `VLLM_HTTP_READ_TIMEOUT_SECONDS` | Timeout | 40 s | 45 s | 40; test 35/40 only after stage timing | A 40 s LLM read can still leave almost no budget after admission, rewrite, retrieval, persistence and reranking; 45 s is riskier | Shorter values may fail long valid answers | `utils/performance_config.py:136-138`; `utils/RagSystem.py:76-108,182-191` |
| `VLLM_HTTP_WRITE_TIMEOUT_SECONDS` | Timeout | 5 s | 5 s | 5; safe 3-10 | Higher tolerates large prompt upload but consumes more budget on faults | None | `utils/performance_config.py:139-141`; `main.py:276-283` |
| `VLLM_HTTP_POOL_TIMEOUT_SECONDS` | Pool admission timeout | 3 s | 3 s | 5 candidate; test 3/5 after telemetry | Higher waits longer for sockets; does not create GPU capacity | None | `utils/performance_config.py:142-144`; `main.py:276-283` |
| `QDRANT_CONCURRENCY` | Retrieval admission | 8 | 4 | 8; test 4/8/16 | Higher allows more vector calls but multiplies Qdrant/thread/DB pressure; per worker | None unless failures/order change | `utils/performance_config.py:145`; `utils/persian_hybrid_search.py:281,427-457` |
| `RAG_RETRIEVAL_TOP_K` | Retrieval / quality | 10 | 10 | 10; hold fixed | Higher expands context and prompt cost; lower can omit evidence | Direct retrieval and answer quality | `agent_graph.py:148-153`; `utils/persian_hybrid_search.py:492-549` |
| `RAG_SEMANTIC_CANDIDATE_LIMIT` | Retrieval / quality | 50 | 50 | 30 hypothesis; test 20/30/50 | Lower reduces Qdrant result and fusion work; higher can improve recall but grows work | Direct; evaluate top-k recall/MRR and answers | `utils/performance_config.py:147-149,188-192`; `utils/persian_hybrid_search.py:517-539` |
| `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD` | Retrieval / quality | 0.1 | 0.1 | 0.1; do not tune in performance sweep | Higher returns fewer related questions, not necessarily faster because scoring already occurred | Direct related-question relevance | `agent_graph.py:166-175` |
| `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` | Unused / legacy | 0.5 | 0.5 | Remove from future templates; retained by the settings parser for compatibility | No active runtime effect after removal of the dead endpoint-level rerank path | None | `utils/performance_config.py:76-77,153-155`; canonical threshold consumer: `agent_graph.py:168-175` |
| `RAG_MAX_NEW_TOKENS` | Generation / quality | 500 | 500 | 384 hypothesis; test 256/384/500 | Lower bounds decode latency and GPU work; higher increases tail latency and queueing | Direct answer completeness | `utils/RagSystem.py:251-267,360-367` |
| `RAG_CHITCHAT_MAX_NEW_TOKENS` | Generation / quality | 128 | 200 | 128; test 96/128/200 | Same decode trade-off for chitchat | Direct tone/completeness | `utils/RagSystem.py:258-262` |
| `RAG_REWRITE_MAX_TOKENS` | Generation / quality | 200 | 1000 | 128 hypothesis; test 64/128/256 | Lower sharply bounds rewrite decode; current 200 is already below old default | Direct retrieval query correctness | `utils/RagSystem.py:370-378`; `new_architecture/app/services/history/rewriting.py:244-275` |
| `TEI_EMBED_INSERT_BATCH_SIZE` | Data insertion | defaulted 32 | 32 | 32; test insertion separately | Higher improves insertion throughput until TEI/VRAM limit; not a talk-path control | Stored-vector correctness if failures/reordering occur | `utils/performance_config.py:118-120`; `new_architecture/insert_data.py:1397` |
| `TEI_EMBED_MAX_CLIENT_BATCH_SIZE` | Data insertion correctness | defaulted 50 | 50 | 50; must match server ceiling | Values below insertion batch reject local configuration; values above TEI server 50 can receive HTTP rejection | No talk-path effect; insertion completeness | `utils/performance_config.py:121-123,172-179`; `new_architecture/insert_data.py:1397-1398` |

## Safe correctness fixes

These are code/configuration issues, not claims that a numeric tuning value is
faster.

1. **P0 correctness — active `MINIO_SECURE` is ignored.**
   `new_architecture/app/config.py:34-43` hardcodes `False`; startup applies it
   at `new_architecture/app/services/db_connection/connection.py:61-66`.
   Separately, `new_architecture/insert_data.py:94,384-389` passes the raw
   non-empty string, so `"false"` is truthy. Fix and test strict boolean parsing
   in a separate authorized code task.
2. **P0 correctness/security — secret-bearing files and credential-like source
   literals are tracked.** `.env` is ignored by pattern but remains tracked;
   `.env.server_git` is also tracked. Credential-like literals exist at
   `new_architecture/setup_dbs.py:49-63,75-82` and `test_qdrant.py:10-11`.
   Rotate possibly exposed credentials and untrack live secret files through a
   reviewed security change; do not rewrite history casually.
3. **P1 failure risk — no running vLLM exists.** The application URL can be
   configured, but no current server is available. A FastAPI start would fail
   generation requests until the intended vLLM model command is restored.
4. **Resolved cleanup risk — duplicate FAQ rerank path.** The graph performs
   the single active TEI rerank (`agent_graph.py:168-175`). The former
   endpoint-level `CrossEncoder` blocks were unreachable because their global
   model was never initialized; they have been removed from `main.py` and
   `mobile_api.py`. This preserves current behavior while preventing accidental
   double reranking if that dead global were initialized later.
5. **P1 timeout risk — stage waits are not observable.** No application code
   emits the timing headers recognized at
   `benchmarks/load/mobile_talk_load_test.py:810-818`. HTTP pool acquisition,
   Qdrant semaphore acquisition, blocking-runner acquisition, PostgreSQL,
   rewrite, TEI and vLLM stages cannot currently be attributed from endpoint
   responses.
6. **P1 quality/cost risk — rewrite length is not validated.**
   `extract_rewritten_query` accepts any non-empty content inside tags or after
   a thought marker (`rewriting.py:255-275`). It has no character/token/query
   similarity bound. `RAG_REWRITE_MAX_TOKENS` bounds generation only.

## Requested configuration checks

| Question | Result |
|---|---|
| Does `ENVIRONMENT` affect runtime? | No repository consumer; operational label only. |
| Is `QDRANT_URL` active? | No on verified `main:app`; split host/port/HTTPS fields win. Legacy-only references are listed in `ENVIRONMENT_VARIABLES.md`. |
| Do `EMBEDDING_MODEL`, `LLM_MODEL`, `RERANKER_MODEL` configure servers? | No. They are loaded/captured, but active clients use TEI/vLLM URLs; local model loading is absent/commented (`config.py:16-18`; `RagSystem.py:44-56,133-138`). |
| Are `DEFAULT_DB_*` and `POSTGRES_*` separated? | Yes: setup connects to the default/admin DB with `DEFAULT_DB_*` and creates/uses the target from `POSTGRES_*` (`setup_dbs.py:55-93`). Reserved URL characters are not encoded. |
| Can inactive 384 dimensions become active? | Not on verified `main:app`; `new_architecture/app/core/database.py:70` is not imported. Importing that alternate module could create/use an incompatible 384-dimensional collection. Active policy validates 1024 (`tei_embedding_client.py:14,44-67`). |
| Is admission inside the mobile 50 s deadline? | Yes. `asyncio.wait_for` wraps `run_with_limit` at `mobile_api.py:85-95`. A mobile request cannot consume admission plus a fresh 50 s processing budget. |
| Is the web `/api/query` behavior the same? | No. It acquires first, then starts its 50 s `wait_for` (`main.py:565-582`), so that endpoint can consume admission timeout plus application timeout. |
| Does 40 s vLLM read leave enough time? | Not guaranteed. It can consume most remaining budget and is a P1 risk until stage timings show actual distributions. |
| Are HTTP pool waits measured? | No. Only pool timeout exceptions/total request latency are observable. |
| Is Qdrant semaphore wait measured? | No (`persian_hybrid_search.py:435-455`). |
| Do workers multiply limits? | Yes. All limiters/pools are created in each lifespan (`main.py:213-319`). Current worker count is unobservable because FastAPI is stopped. |
| Do model services share GPU? | Both TEIs do. vLLM is stopped, but the historical command and intended architecture place it on GPU 0 too. Combined contention must be measured. |
| Does reranking delay endpoint response? | Yes. Graph reranking precedes generation, and mobile reranking occurs after answer generation/persistence but before returning. |
| Are rewrites bounded and validated? | Generation is bounded by 200 current tokens; semantic/length validation is absent. |

## Good initial defaults versus values requiring measurement

Keep unchanged initially: total deadline 50, application concurrency 32,
admission 12, blocking concurrency 16, TEI connect/read/write settings,
vLLM connect/read/write settings, retrieval top-k 10, both thresholds, and
chitchat 128. These are starting points, not certified values.

The generated candidate changes only these current values:

| Variable | Current | Candidate | Why it may help | Regression / proof / rollback |
|---|---:|---:|---|---|
| `TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS` | 16 | 32 | Avoid reconnect churn if 32 concurrent sockets are active | More retained sockets; prove with connection/pool telemetry; rollback to 16 |
| `VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS` | 16 | 32 | Same hypothesis for vLLM | Same; rollback to 16 |
| `VLLM_HTTP_POOL_TIMEOUT_SECONDS` | 3 | 5 | Align reviewed wait with potential short socket contention | Can hide undersized pool and consume endpoint budget; rollback to 3 |
| `RAG_SEMANTIC_CANDIDATE_LIMIT` | 50 | 30 | Reduce Qdrant/fusion work and prompt candidate preparation | Recall/answer degradation; run retrieval and answer-quality gates; rollback to 50 |
| `RAG_MAX_NEW_TOKENS` | 500 | 384 | Bound decode tail | Incomplete answers; inspect full answers/token counts; rollback to 500 |
| `RAG_REWRITE_MAX_TOKENS` | 200 | 128 | Rewrites should be short; reduces worst-case decode | Truncated/incorrect retrieval query; inspect rewrites and quality; rollback to 200 |

`TEI_HTTP_POOL_TIMEOUT_SECONDS` is already 5 and `QDRANT_CONCURRENCY` is
already 8, so the candidate does not change them. The generated file also adds
the two insertion defaults explicitly; this makes the intended server/client
batch relationship visible but has no mobile latency effect.

Do not change `RAG_RETRIEVAL_TOP_K`, either rerank threshold, semantic candidate
limit, answer/chitchat/rewrite token ceilings, embedding prompt policy, vector
dimension, distance metric, model, dtype, or quantization without retrieval
and answer-quality testing.

## Unused or legacy settings

- `ENVIRONMENT`: no active behavior.
- `QDRANT_URL`: legacy full URL; active runtime uses split fields.
- `EMBEDDING_MODEL`, `LLM_MODEL`, `RERANKER_MODEL`: do not start or configure
  the external services.
- `new_architecture/app/core/database.py` pool/vector defaults: not in the
  verified startup import path.

## Final values not yet proven

Every changed value in `.env.recommended.rtx5880-staging` is unproven as a
combined set. The external vLLM scheduler cannot receive a defensible final
value until a current model is running and prompt lengths, KV-cache use,
queueing, TTFT, decode throughput and preemptions are captured. TEI server
limits are also held at their observed values pending isolated/combined tests.

## Restart and rollback

All application variables above are imported into process-global settings at
startup (`utils/performance_config.py:196`), so restart every FastAPI worker.
Changing a TEI command-line flag requires recreating that TEI container, not
merely restarting it. Changing a vLLM flag requires restarting/recreating the
vLLM service. The model-server document gives reversible reviewed command
patterns.

For an application experiment, preserve the baseline process, stop only the
experimental process using its recorded PID/service manager, remove the one
environment override, and start the original command again. Never copy the
generated file over `.env`; that would discard service and secret settings.
