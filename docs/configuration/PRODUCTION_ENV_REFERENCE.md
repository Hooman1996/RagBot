# Production environment reference

This is the hand-over list of every environment variable the RagBot application reads. It is written for the team that configures production. It was built by tracing the code on `main` (helper functions, settings classes and f-strings included), not from older documents. Defaults are the exact code defaults.

`Production_ENV.example` is the template to copy. It has every key the running application needs, with secret values left empty.

## How configuration is loaded

- `main.py` calls `load_dotenv()` without override, so variables exported by the process manager win over a `.env` file.
- Almost every value is read once, at import or startup. A change needs a process restart.
- Most settings are validated at startup. An invalid value (wrong type, out of range, or a broken cross-check) stops the application rather than falling back to a default.
- Booleans:
  - The performance settings accept `true/false`, `1/0`, `yes/no` and `on/off`.
  - The logging settings reject `on/off`.
  - `QDRANT_HTTPS` and `SQLALCHEMY_ECHO` turn on only for the exact value `true`.
  - Use `true` and `false` everywhere.

## Before the first production start

### Startup fails if these are missing or invalid

| Variable | What to set |
|---|---|
| `WEB_SESSION_SECRET` | At least 32 random bytes from the secret manager. |
| `WEB_PUBLIC_ORIGIN` | The exact external origin users open, such as `https://chat.example.com`, with no path, query or trailing slash. |
| `TEI_EMBED_URL` | The production TEI embedding base URL. |
| `TEI_RERANK_URL` | The production TEI reranking base URL. |
| `MINIO_BUCKET` | The documents bucket. Empty or unset fails the startup bucket check. |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | The MinIO endpoint (`host:port`, no scheme) and credentials. |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Set all five. Three code paths read them with different defaults (see the PostgreSQL notes below). |
| `INTENT_CLASSIFIER_MODEL_PATH`, `INTENT_CLASSIFIER_THRESHOLD`, `INTENT_CLASSIFIER_DEVICE`, `INTENT_CLASSIFIER_REQUIRED` | All four are mandatory. With `INTENT_CLASSIFIER_REQUIRED=true`, `INTENT_CLASSIFIER_EXPECTED_SHA256` is mandatory too. |

### Set these explicitly even though startup would succeed without them

| Variable | Why |
|---|---|
| `QDRANT_COLLECTION` | Retrieval has no default. If unset, startup succeeds but every search targets a missing collection. An empty value is used as-is. |
| `QDRANT_API_KEY` | Without it the Qdrant client sends no authentication. |
| `EMBEDDING_MODEL` | Without it, creating a chunk in the KB manager returns 503. |
| `TEI_RERANK_VERIFIED_MAX_BATCH_SIZE` | Must equal the production reranker's `--max-client-batch-size`. It is used when TEI `/info` cannot be read. If it is unset, reranking refuses requests whenever `/info` is unreachable. |

### Values that must be exactly these in production

| Variable | Value | Why |
|---|---|---|
| `RAG_PIPELINE_DEBUG` | `false` | When true, it prints raw queries, history, chunks and answers to stdout, and with the prompt sub-flag also full prompts. |
| `WEB_COOKIE_MODE` | `https` | `local-http` is accepted only with `WEB_ENVIRONMENT=development`. |
| `WEB_ENVIRONMENT` | `production` | This is also the default. |
| `INTENT_CLASSIFIER_REQUIRED` | `true` | With `false`, a missing checkpoint silently turns the guardrail off, and every message is treated as actionable. |
| `LOG_PII_REDACTION` | `true` | The only accepted value. `false` stops startup. |
| `LOG_FORMAT` | `json` | The only accepted value. |

### Owner decisions

- **`ENVIRONMENT`.** The template has `development`. The destructive reset tools (`new_architecture/setup_dbs.py`, `new_architecture/knowledge_reset.py`) refuse to run only when `ENVIRONMENT=production`, and default to `development` when it is unset. The code distinguishes three cases:
  - `staging` enables the evaluation tools;
  - `production` blocks resets;
  - any other value counts as neither.

  Setting `production` is recommended.
- **`LOG_REQUEST_BODY` and `LOG_RESPONSE_BODY`.** Both default to `true` and are `true` in the template. They log PII-scrubbed request and response bodies, which still contain the customer's free-text question and the answer. This applies on `/api/query`, `/api/sessions/{id}/message`, `/api/mobile/v1/talk` and `/api/internal/evaluation/v1/turn`. Decide whether this meets the bank's logging policy.

## Network requirements (no variable controls these)

- **vLLM and TEI have no authentication.** The vLLM API key is hard-coded and no variable adds credentials, so both services must be reachable only from the application host.
- **vLLM must serve the model name `/app/model`.** That name is hard-coded in `utils/RagSystem.py`; `LLM_MODEL` does not change it.
- **The internal evaluation API is not protected by web login.** `/api/internal/evaluation/v1/*` is always mounted and no variable disables it. Block it at the ingress so it is not public.
- **MinIO always uses plain HTTP from the app.** The FastAPI app hard-codes `MINIO_SECURE=False` in `new_architecture/app/config.py` and ignores the variable. Keep MinIO on a private network.
- **Qdrant uses TLS only with `QDRANT_HTTPS=true`.** The template has `False`, so the Qdrant API key crosses the network unencrypted. Keep Qdrant on a private network or enable TLS.

## Reference by area

Required means startup fails without the variable. A blank in the template column means the value is a secret or must be filled in.

### Runtime and process

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `ENVIRONMENT` | No | reset tools `development` | `development` | Deployment stage. Guards the reset tools and is the last fallback for the log `environment` field. The audit does not read it. See Owner decisions. |
| `API_HOST` | No | `0.0.0.0` | `0.0.0.0` | Bind address, used only by `python main.py`. Ignored under `uvicorn main:app` or gunicorn. |
| `API_PORT` | No | `7000` | `8080` | Listen port, used only by `python main.py`. |

`WEB_CONCURRENCY` is not read by the app. The Uvicorn command line reads it for its worker count, but `uvicorn.run()` in `main.py` does not use it.

### Web login (web chat, analytics, KB manager)

These are validated at startup and on every login.

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `WEB_SESSION_SECRET` | Yes | none | (secret) | HMAC key that signs the browser session and CSRF cookies. At least 32 bytes. Use its own secret; never reuse it for `LOG_PII_HMAC_SECRET`. |
| `WEB_PUBLIC_ORIGIN` | Yes | none | (fill in) | The external origin, checked against the browser's `Origin` header on login and every state-changing request (CSRF protection). Must be `https://` in https mode. |
| `WEB_COOKIE_MODE` | No | `https` | `https` | `https` sets Secure cookies. `local-http` is for development only. |
| `WEB_ENVIRONMENT` | No | `production` | `production` | Browser-auth stage. Only `development` changes behavior: it allows `local-http`. Also the log environment fallback. |
| `WEB_SESSION_SECONDS` | No | `900` | `900` | Browser session lifetime in seconds, 300 to 7200. |

### Logging

These are validated at startup.

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `LOG_LEVEL` | No | `INFO` | `INFO` | Root log level: DEBUG, INFO, WARNING, ERROR or CRITICAL. |
| `LOG_FORMAT` | No | `json` | `json` | Must be `json`. |
| `LOG_PII_REDACTION` | No | `true` | `true` | Must be `true`. |
| `LOG_BODY_MAX_BYTES` | No | `32768` | `32768` | Largest body the HTTP log middleware inspects, 1 to 262144. Larger bodies are logged as `[TRUNCATED]`. |
| `LOG_SERVICE_NAME` | No | `ragbot` | `ragbot` | `service` field on every log event. ASCII letters, digits, `-` and `_`; at most 64 characters. |
| `LOG_ENVIRONMENT` | No | falls back to `WEB_ENVIRONMENT`, then `ENVIRONMENT`, then `unknown` | `production` | `environment` field on every log event. An empty value fails startup. |
| `LOG_REQUEST_BODY` | No | `true` | `true` | Logs PII-scrubbed request bodies on allowed routes. See Owner decisions. |
| `LOG_RESPONSE_BODY` | No | `true` | `true` | Logs PII-scrubbed response bodies on allowed routes. |
| `LOG_PII_HMAC_SECRET` | No | unset | commented out | Optional key for stable pseudonyms of PII in logs. Unset means PII is replaced with `[REDACTED]`. |

### Request admission and concurrency

These are read at import. They apply to web chat, the mobile API, mass answer and the audit.

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `APPLICATION_REQUEST_TIMEOUT_SECONDS` | No | `50` | `50` | Overall deadline for one answering request. Must be above 0 and at most 50. |
| `REQUEST_CONCURRENCY_LIMIT` | No | `32` | `256` | Most answering requests running at once. |
| `REQUEST_ADMISSION_TIMEOUT_SECONDS` | No | `12` | `45` | How long a request waits for a slot before it gets a busy error. |
| `BLOCKING_CONCURRENCY_LIMIT` | No | `16` | `48` | Worker-thread pool for blocking calls such as database and CPU work. |

The template values (256, 45 and 48) have not been benchmarked in this repository. A 45-second admission wait leaves little of the 50-second deadline for answering.

### vLLM (answer generation)

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `VLLM_URL` | No (app); yes (audit) | `http://localhost:8000/v1` | `http://localhost:8000/v1` | Base URL of the OpenAI-compatible vLLM server, including `/v1`. |
| `VLLM_HTTP_MAX_CONNECTIONS` | No | `32` | `256` | HTTP connection pool size. Must be at least the keep-alive count. |
| `VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS` | No | `16` | `128` | Idle keep-alive connections. |
| `VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS` | No | `30` | `30` | Idle keep-alive expiry. |
| `VLLM_HTTP_CONNECT_TIMEOUT_SECONDS` | No | `3` | `3` | Connect timeout. |
| `VLLM_HTTP_READ_TIMEOUT_SECONDS` | No | `45` | `60` | Read timeout for one completion. The template's 60 is longer than the 50-second request deadline, which cuts it short. |
| `VLLM_HTTP_WRITE_TIMEOUT_SECONDS` | No | `5` | `5` | Write timeout. |
| `VLLM_HTTP_POOL_TIMEOUT_SECONDS` | No | `3` | `15` | Wait for a free pooled connection. |
| `LLM_MODEL` | No | unset | `gemma-4-12B-it` | No effect on behavior; it is only a label. The model name sent is `/app/model`. |

### TEI embedding and the shared TEI connection pool

The embedding and reranking clients share one HTTP pool built from the `TEI_HTTP_*` keys.

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `TEI_EMBED_URL` | Yes | none | `http://localhost:7997` | TEI embedding base URL, used for query embeddings, the intent classifier and KB document embeddings. |
| `TEI_HTTP_MAX_CONNECTIONS` | No | `32` | `256` | Pool size. Must be at least the keep-alive count. |
| `TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS` | No | `16` | `128` | Idle keep-alive connections. |
| `TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS` | No | `30` | `30` | Idle keep-alive expiry. |
| `TEI_HTTP_CONNECT_TIMEOUT_SECONDS` | No | `3` | `3` | Connect timeout. |
| `TEI_HTTP_READ_TIMEOUT_SECONDS` | No | `15` | `15` | Read timeout for one TEI request. |
| `TEI_HTTP_WRITE_TIMEOUT_SECONDS` | No | `5` | `5` | Write timeout. |
| `TEI_HTTP_POOL_TIMEOUT_SECONDS` | No | `3` | `15` | Wait for a free pooled connection. |
| `TEI_EMBED_INSERT_BATCH_SIZE` | No | `32` | `32` | Batch size when the data-insertion tools embed documents. Must not exceed the next key; checked at app startup too. |
| `TEI_EMBED_MAX_CLIENT_BATCH_SIZE` | No | `50` | `50` | Upper bound used only to validate the insert batch size. |
| `EMBEDDING_MODEL` | Set it | unset | model path | Label stored with each KB chunk's embedding. TEI does the embedding; this does not choose the model. The KB manager returns 503 when it is unset. |

### TEI reranking

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `TEI_RERANK_URL` | Yes | none in retrieval | `http://localhost:7998` | TEI reranker base URL, used for context reranking, related questions and the `/info` capability check. |
| `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` | No | `50` | `50` | Most texts per rerank request. The client sends `min(this, the server's /info limit)`. |
| `TEI_RERANK_VERIFIED_MAX_BATCH_SIZE` | Set it | unset | `50` | Operator-verified batch limit used when `/info` cannot be read. Must equal the production reranker's `--max-client-batch-size`. |
| `TEI_RERANK_CAPABILITY_TTL_SECONDS` | No | `600` | `600` | How long a successful `/info` result is cached. |
| `TEI_RERANK_CAPABILITY_RETRY_SECONDS` | No | `30` | `30` | Wait before checking `/info` again after a failure. |
| `RERANKER_MODEL` | No | unset | model path | No effect on behavior; it is only a label. |

### Retrieval and answer generation

These are read at import. Changing them changes answers, so any change needs the retrieval and answer-quality tests (`docs/performance/RELEASE_EVALUATION_RUNBOOK.md`). Some template values differ from the code defaults, so **copy every key**: leaving one out silently changes behavior.

| Variable | Code default | Template | What it does |
|---|---|---|---|
| `RAG_QUERY_CANONICALIZATION_ENABLED` | `true` | `true` | Applies the reviewed query-alias canonicalization before search. |
| `RAG_RETRIEVAL_TOP_K` | `10` | `50` | Distinct fused (BM25 plus dense) results returned by retrieval. Must be at least `RAG_CONTEXT_RERANK_TOP_K`. |
| `RAG_BM25_CANDIDATE_LIMIT` | `50` | `50` | Lexical candidates per query before fusion. |
| `RAG_SEMANTIC_CANDIDATE_LIMIT` | `50` | `50` | Dense Qdrant candidates per query before fusion. |
| `RAG_CONTEXT_RERANK_ENABLED` | `true` | `true` | Reranks retrieved results before building the answer context. |
| `RAG_CONTEXT_RERANK_TOP_K` | `10` | `10` | Reranked results kept for the answer context. |
| `RAG_RELATED_QUESTIONS_TOP_K` | `3` | `3` | Top results used for related-question suggestions. |
| `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD` | `0.1` | `0.1` | Minimum rerank score for a related question to be shown, 0 to 1. |
| `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` | `0.5` | `0.5` | No effect: it is validated (0 to 1) but nothing uses it. |
| `RAG_MAX_NEW_TOKENS` | `500` | `500` | Maximum tokens for a knowledge-base answer. |
| `RAG_CHITCHAT_MAX_NEW_TOKENS` | `200` | `96` | Maximum tokens for a chit-chat answer. |
| `RAG_REWRITE_MAX_TOKENS` | `1000` | `128` | Maximum tokens for the history-aware query rewrite. |
| `RAG_ANSWER_TEMPERATURE`, `RAG_ANSWER_TOP_P`, `RAG_ANSWER_SEED` | `0.0`, `1.0`, `42` | same | Sampling for knowledge-base answers. Temperature at least 0; top_p above 0 and at most 1; seed at least 0. |
| `RAG_CHITCHAT_TEMPERATURE`, `RAG_CHITCHAT_TOP_P`, `RAG_CHITCHAT_SEED` | `0.0`, `1.0`, `42` | same | Sampling for chit-chat. |
| `RAG_REWRITE_TEMPERATURE`, `RAG_REWRITE_TOP_P`, `RAG_REWRITE_SEED` | `0.0`, `1.0`, `42` | same | Sampling for query rewriting. |

### Pipeline debug reports

Keep `RAG_PIPELINE_DEBUG=false` in production. The sub-flags matter only when it is true, and print to stdout, the same stream as the JSON logs.

| Variable | Code default | Template | What it does |
|---|---|---|---|
| `RAG_PIPELINE_DEBUG` | `false` | `false` | Master switch for per-request terminal reports. |
| `RAG_PIPELINE_DEBUG_QUERY`, `_NORMALIZATION`, `_HISTORY`, `_REWRITE`, `_INTENT`, `_RETRIEVAL`, `_RERANK`, `_CONTEXT`, `_ANSWER`, `_TIMINGS` | `true` | `false` | Which stages the report shows. |
| `RAG_PIPELINE_DEBUG_PROMPT` | `false` | `false` | Shows the full prompt. |
| `RAG_PIPELINE_DEBUG_CHUNK_MAX_CHARS` | `1200` | `1200` | Truncation length for printed chunks. |
| `RAG_PIPELINE_DEBUG_FULL_CHUNKS` | `false` | `false` | Prints chunks without truncation. |

### Mass answer (`POST /api/mass-answer`)

| Variable | Code default | Template | What it does |
|---|---|---|---|
| `MASS_ANSWER_ROW_CONCURRENCY` | `4` | `4` | Rows answered at once. These share the GPU with live chat. |
| `MASS_ANSWER_ROW_TIMEOUT_SECONDS` | `50` | `50` | Deadline per row. |
| `MASS_ANSWER_DIRECT_MAX_ROWS` | `20` | `20` | Files with more rows than this run as a background job. |
| `MASS_ANSWER_JOB_RETENTION_HOURS` | `24` | `24` | How long job results stay available. |
| `MASS_ANSWER_MAX_ROWS` | `5000` | `5000` | Largest accepted row count. |
| `MASS_ANSWER_MAX_UPLOAD_MB` | `10` | `10` | Largest accepted upload, in MiB. |

### Intent classifier (guardrail)

This is loaded at startup. Any error stops the application.

| Variable | Required | Template | What it does |
|---|---|---|---|
| `INTENT_CLASSIFIER_MODEL_PATH` | Yes | checkpoint path | Path to the guardrail `.pt` checkpoint. |
| `INTENT_CLASSIFIER_THRESHOLD` | Yes | `0.9489644765853882` | Decision threshold, strictly between 0 and 1. |
| `INTENT_CLASSIFIER_DEVICE` | Yes | `cuda` | Torch device, such as `cpu`, `cuda` or `cuda:1`. Note that `scripts/validate_environment.py` accepts only `cpu` or `cuda`. |
| `INTENT_CLASSIFIER_REQUIRED` | Yes | `true` | With `true`, a missing checkpoint or checksum mismatch stops startup. Keep it `true`. |
| `INTENT_CLASSIFIER_EXPECTED_SHA256` | Yes when required | checksum | SHA-256 of the checkpoint file, 64 hex characters. |

### PostgreSQL

The running application reads these variables in three ways:

- the chat-history manager in `main.py` has no defaults, so an unset value falls through to the libpq `PG*` variables or the local socket;
- the startup connection uses `new_architecture/app/config.py`, whose defaults are `5432`, `hihelp_db`, `postgres` and `postgres`;
- the KB manager requires all five and fails at request time.

Set all five so every path reaches the same database.

| Variable | Required | Template | What it does |
|---|---|---|---|
| `POSTGRES_HOST` | Yes | host | Database host for chat sessions and relational data. |
| `POSTGRES_PORT` | Yes | `5432` | Database port. |
| `POSTGRES_DB` | Yes | `chatbot` | Database name. |
| `POSTGRES_USER` | Yes | (fill in) | Database role. |
| `POSTGRES_PASSWORD` | Yes | (secret) | Database password. Never rely on the `postgres` fallback in `new_architecture/app/config.py`. |
| `DEFAULT_DB_HOST`, `DEFAULT_DB_PORT`, `DEFAULT_DB_USER`, `DEFAULT_DB_PASSWORD`, `DEFAULT_DB_NAME` | Setup tool only | host, port, blanks | Maintenance-database connection that `new_architecture/setup_dbs.py` uses to create the target database. The app does not read them. |

`SQLALCHEMY_POOL_SIZE`, `SQLALCHEMY_MAX_OVERFLOW`, `SQLALCHEMY_POOL_TIMEOUT`, `SQLALCHEMY_POOL_RECYCLE` and `SQLALCHEMY_ECHO` are read only by `new_architecture/app/core/database.py`, which nothing imports. They have no effect.

### Qdrant

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `QDRANT_HOST` | No | `localhost` | host | Qdrant host. |
| `QDRANT_PORT` | No | `6333` | `6333` | Qdrant HTTP port. |
| `QDRANT_API_KEY` | Set it | unset (no auth) | (secret) | Qdrant API key. |
| `QDRANT_HTTPS` | No | `false` | `False` | TLS to Qdrant; only the exact value `true` enables it. |
| `QDRANT_COLLECTION` | Set it | none in retrieval | (fill in) | Vector collection name. Startup creates it if it is missing. |
| `QDRANT_VECTOR_SIZE` | No | `1024` | `1024` | Embedding dimension, checked against TEI output and used when the collection is created. |
| `QDRANT_CONCURRENCY` | No | `4` | `32` | Most Qdrant searches running at once. |

`QDRANT_URL` is only printed by the knowledge-update diagnostics. The app uses `QDRANT_HOST` and `QDRANT_PORT`.

### MinIO

| Variable | Required | Code default | Template | What it does |
|---|---|---|---|---|
| `MINIO_ENDPOINT` | Yes | `localhost:9000` | `host:port` | MinIO endpoint, with no scheme. |
| `MINIO_ACCESS_KEY` | Yes | unset | (secret) | MinIO access key. |
| `MINIO_SECRET_KEY` | Yes | unset | (secret) | MinIO secret key. |
| `MINIO_BUCKET` | Yes | none | (fill in) | Bucket for source documents. Startup checks that it exists, and the health check uses it. |
| `MINIO_SECURE` | Tools only | `false` | `False` | TLS for the data-insertion and reset tools only; the app ignores it. `new_architecture/insert_data.py` treats any non-empty value, `False` included, as on. |

### Knowledge-coverage check (every environment)

The check (`coverage_check/`) is on unless `KNOWLEDGE_COVERAGE_ENABLED=false`, and behaves the same whatever `ENVIRONMENT` says. Access is by role, from `COVERAGE_ROLE_CAPABILITIES` in `web_permissions.py`: `admin` can start, cancel and resume checks and view every check; `dashboard_viewer` can view every check and download its CSV; every other role has no access. With the flag `false`, every coverage route returns 404, the sidebar link is hidden and none of the other keys are loaded. Any invalid value stops startup with the variable's name.

**Production note.** `KNOWLEDGE_COVERAGE_ARTIFACT_DIR` must point to a persistent directory on the production host. Checks use the production vLLM and TEI, one question at a time, and every retrieval and model call is admitted through the same request limiter as chat.

The six keys marked "page" are only defaults: the page shows them in editable fields, the server checks every submitted value against the same ranges, and each run stores the values it used.

| Variable | Code default | What it does |
|---|---|---|
| `KNOWLEDGE_COVERAGE_ENABLED` | `true` | Feature flag; `true` or `false`. |
| `KNOWLEDGE_COVERAGE_ARTIFACT_DIR` | `/root/projects/faq-private/knowledge-coverage` | Private run folders. Must be an absolute path outside the repository and not under `/tmp`. |
| `KNOWLEDGE_COVERAGE_UPLOAD_MAX_BYTES` | `5242880` | Largest CSV upload (1024 to 20971520). |
| `KNOWLEDGE_COVERAGE_MAX_ROWS` | `10000` | Most CSV rows per check (1 to 100000). |
| `KNOWLEDGE_COVERAGE_DEPTH` | `150` | Page. Retrieval depth: `top_k` and the BM25 and semantic candidate limits (1 to 1000). |
| `KNOWLEDGE_COVERAGE_KEEP` | `50` | Page. Chunks kept after rerank (1 to `DEPTH`). |
| `KNOWLEDGE_COVERAGE_BATCH_SIZE` | `5` | Page. Chunks per model call (1 to 20). |
| `KNOWLEDGE_COVERAGE_BROADER_ENABLED` | `false` | Page. Wider search when a question is not answered. |
| `KNOWLEDGE_COVERAGE_BROADER_DEPTH` | `200` | Page. Wider-search depth (greater than `DEPTH`, at most 1000). |
| `KNOWLEDGE_COVERAGE_BROADER_KEEP` | `50` | Page. New chunks judged in the wider search (1 to 1000). |
| `KNOWLEDGE_COVERAGE_COMBINE_MAX` | `10` | Most partial chunks sent to the one combine call (2 to 20). |
| `KNOWLEDGE_COVERAGE_CHUNK_MAX_CHARS` | `4000` | Characters of each chunk sent to the model (500 to 20000). |
| `KNOWLEDGE_COVERAGE_MODEL_MAX_TOKENS` | `300` | Output tokens per model call (64 to 2048). |

The old audit's keys (`KNOWLEDGE_COVERAGE_TOKEN_MARGIN`, `_BATCH_MAX_ENTRIES`, `_MAX_RUN_ROWS`, `_MAX_COMPLETIONS`, `_MAX_TOKENS`, `_MAX_EXECUTION_SECONDS`, `_MAX_CONSECUTIVE_FAILURES`, `_MIN_FREE_BYTES`, `_PACE_MS`, `_RETENTION_DAYS`, `_INITIAL_DEPTH`, `_INITIAL_ENTRIES`, `_MAX_ENTRY_BUDGET`, `_VERIFICATION_PASSES`, `_DEDUPE`, `_REQUIRE_SECOND_REVIEWER`, `_PUBLIC_CONTACTS` and `KNOWLEDGE_RECOMMENDATION_MAX_COMPLETIONS`) are read only by `knowledge_audit/`, which the app no longer mounts. They are removed with that code in step 22.

### Knowledge ingestion tools (command-line only)

| Variable | Used by | What it does |
|---|---|---|
| `DATA_INSERTION_DIRECTORY` | insertion, reset and knowledge-changer tools | Root of the generated document and chunk files. |
| `KNOWLEDGE_BASE_CSV` | `hihelp_knowledge_changer.py` | Source FAQ CSV. |
| `KNOWLEDGE_SOURCE_NAME` | `hihelp_knowledge_changer.py` | Optional data-source name. The file name is used when it is unset. |
| `MINIO_KNOWLEDGE_PREFIX` | insertion and reset tools | Optional object-key prefix for knowledge files in MinIO. |
| `RAGBOT_SEED_PASSWORD_<USER>` | `new_architecture/add_users.py` | Seed passwords for `admin` and four demo users. Do not run this tool against production. |

## Keys with no effect

| Key | Status |
|---|---|
| `QUERY_EMBEDDING_MODEL` | In the template, but nothing reads it. |
| `EMBEDDING_MODEL_NAME` | Listed in `scripts/validate_environment.py`, but nothing reads it. |
| `LLM_MODEL`, `RERANKER_MODEL` | Labels only; they select no model. |
| `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` | Validated, but unused. |
| `MINIO_SECURE` | Ignored by the app; read only by the command-line tools. |
| `SQLALCHEMY_*` | Read only by a module nothing imports. |
| `QDRANT_URL`, `WEB_CONCURRENCY` | Printed by diagnostics only. |

Test and benchmark helpers (`RAGBOT_STAGING_*`, `RAGBOT_TEST_*`, `RAGBOT_ADMISSION_*`, `RAGBOT_*_IMAGE`, `BROWSER_NODE_DIR`, `REQUIRE_BROWSER`) are never read by the application and are not needed in production.
