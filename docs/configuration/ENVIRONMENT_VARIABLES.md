# RagBot environment-variable reference

This is the complete configuration inventory for the repository as audited on
2026-07-29. It covers the FastAPI application, setup and insertion commands,
legacy modules, tests, and staging benchmarks. No secret value from `.env` is
reproduced here.

## How to read this reference

- **Required** means the active FastAPI startup cannot reliably work without
  the variable. “Command only” means it is required only when that named tool
  is run. “No” means a code default exists or the feature is optional.
- **Current status** is a classification of the current `.env`, never its
  secret value.
- **Default** is the actual code default, not necessarily a good deployment
  choice. “None” means missing data reaches a client or fails later.
- **Restart** identifies the process that reads the value. Most settings are
  read at import/startup and are not dynamically reloaded.
- **Sensitivity** is `secret`, `internal`, or `safe to document`.
- Paths ending in `:line` or `:start-end` are exact source references in this
  repository.

## Summary

| Variable | Required | Secret | Used by | Default | Restart required |
|---|---|---:|---|---|---|
| `ENVIRONMENT` | Apparently unused | No | No consumer found | None | None |
| `API_HOST` | No | No | Direct `python main.py` Uvicorn | `0.0.0.0` | FastAPI |
| `API_PORT` | No | No | Direct `python main.py` Uvicorn | `8080` | FastAPI |
| `QDRANT_URL` | Apparently unused/legacy | Internal | Legacy vector layer | None | Legacy command |
| `QDRANT_HOST` | No | Internal | FastAPI Qdrant clients | `localhost` | FastAPI |
| `QDRANT_PORT` | No | No | FastAPI Qdrant clients | `6333` | FastAPI |
| `QDRANT_API_KEY` | Production policy | Yes | Qdrant clients | None | FastAPI |
| `QDRANT_COLLECTION` | No | No | Retrieval and insertion | `hihelp_embeddings` | FastAPI/insertion |
| `QDRANT_VECTOR_SIZE` | No | No | Collection and response validation | `1024` active; `384` inactive | FastAPI/insertion |
| `QDRANT_HTTPS` | No | No | Qdrant client | `false` | FastAPI |
| `POSTGRES_HOST` | Yes | Internal | FastAPI and data tools | None on active manager | FastAPI/tool |
| `POSTGRES_PORT` | Yes | No | FastAPI and data tools | Mixed: none/`5432` | FastAPI/tool |
| `POSTGRES_DB` | Yes | Internal | FastAPI and data tools | Mixed: none/`hihelp_db`/`rag_db` | FastAPI/tool |
| `POSTGRES_USER` | Yes | Yes | FastAPI and data tools | Mixed: none/unsafe development default | FastAPI/tool |
| `POSTGRES_PASSWORD` | Yes | Yes | FastAPI and data tools | Mixed: none/unsafe development default | FastAPI/tool |
| `DEFAULT_DB_HOST` | Database setup | Internal | `setup_dbs.py` | None | Setup command |
| `DEFAULT_DB_PORT` | Database setup | No | `setup_dbs.py` | None | Setup command |
| `DEFAULT_DB_USER` | Database setup | Yes | `setup_dbs.py` | None | Setup command |
| `DEFAULT_DB_PASSWORD` | Database setup | Yes | `setup_dbs.py` | None | Setup command |
| `DEFAULT_DB_NAME` | Database setup | Internal | `setup_dbs.py` | None | Setup command |
| `MINIO_ENDPOINT` | Effectively yes | Internal | FastAPI and insertion | `localhost:9000` | FastAPI/tool |
| `MINIO_ACCESS_KEY` | Yes | Yes | FastAPI and insertion | Mixed: none/unsafe dev default | FastAPI/tool |
| `MINIO_SECRET_KEY` | Yes | Yes | FastAPI and insertion | Mixed: none/unsafe dev default | FastAPI/tool |
| `MINIO_SECURE` | Insertion only | No | Insertion; ignored by active FastAPI config | `false` | FastAPI/tool |
| `MINIO_BUCKET` | Yes | No | FastAPI and insertion | Mixed: none/`hihelp-documents`/`documents` | FastAPI/tool |
| `VLLM_URL` | No | Internal | OpenAI-compatible vLLM client | `http://localhost:8000/v1` | FastAPI |
| `TEI_EMBED_URL` | Yes | Internal | TEI embedding clients | None on active path | FastAPI/tool |
| `TEI_RERANK_URL` | Yes | Internal | TEI reranking client | Mixed: none/localhost `7998` | FastAPI |
| `EMBEDDING_MODEL` | Behaviorally unused | Internal | Loaded as legacy metadata | None | FastAPI |
| `EMBEDDING_MODEL_NAME` | Legacy only | Internal | Inactive local embedding class | None | Legacy command |
| `LLM_MODEL` | Behaviorally unused | Internal | Loaded only | None | None |
| `RERANKER_MODEL` | Behaviorally unused | Internal | Commented-out local reranker | None | None |
| `KNOWLEDGE_BASE_CSV` | Command only | Internal | Knowledge preparation | None | Tool only |
| `DATA_INSERTION_DIRECTORY` | Command only | Internal | Data insertion | None | Tool only |
| `APPLICATION_REQUEST_TIMEOUT_SECONDS` | No | No | FastAPI total deadline | `50` | FastAPI |
| `REQUEST_CONCURRENCY_LIMIT` | No | No | FastAPI semaphore | `32` | FastAPI |
| `REQUEST_ADMISSION_TIMEOUT_SECONDS` | No | No | FastAPI semaphore wait | `12` | FastAPI |
| `BLOCKING_CONCURRENCY_LIMIT` | No | No | Blocking-work runner | `16` | FastAPI |
| `TEI_HTTP_MAX_CONNECTIONS` | No | No | TEI HTTPX pool | `32` | FastAPI/tool |
| `TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS` | No | No | TEI HTTPX pool | `16` | FastAPI/tool |
| `TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS` | No | No | TEI HTTPX pool | `30` | FastAPI/tool |
| `TEI_HTTP_CONNECT_TIMEOUT_SECONDS` | No | No | TEI HTTPX | `3` | FastAPI/tool |
| `TEI_HTTP_READ_TIMEOUT_SECONDS` | No | No | TEI HTTPX | `15` | FastAPI/tool |
| `TEI_HTTP_WRITE_TIMEOUT_SECONDS` | No | No | TEI HTTPX | `5` | FastAPI/tool |
| `TEI_HTTP_POOL_TIMEOUT_SECONDS` | No | No | TEI HTTPX | `3` | FastAPI/tool |
| `TEI_EMBED_INSERT_BATCH_SIZE` | No | No | Data insertion | `32` | Tool only |
| `TEI_EMBED_MAX_CLIENT_BATCH_SIZE` | No | No | Batch-policy validation | `50` | FastAPI/tool |
| `VLLM_HTTP_MAX_CONNECTIONS` | No | No | vLLM HTTPX pool | `32` | FastAPI |
| `VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS` | No | No | vLLM HTTPX pool | `16` | FastAPI |
| `VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS` | No | No | vLLM HTTPX pool | `30` | FastAPI |
| `VLLM_HTTP_CONNECT_TIMEOUT_SECONDS` | No | No | vLLM HTTPX | `3` | FastAPI |
| `VLLM_HTTP_READ_TIMEOUT_SECONDS` | No | No | vLLM HTTPX | `45` | FastAPI |
| `VLLM_HTTP_WRITE_TIMEOUT_SECONDS` | No | No | vLLM HTTPX | `5` | FastAPI |
| `VLLM_HTTP_POOL_TIMEOUT_SECONDS` | No | No | vLLM HTTPX | `3` | FastAPI |
| `QDRANT_CONCURRENCY` | No | No | Retrieval semaphore | `4` | FastAPI |
| `RAG_RETRIEVAL_TOP_K` | No | No | Retrieval | `10` | FastAPI |
| `RAG_SEMANTIC_CANDIDATE_LIMIT` | No | No | Retrieval | `50` | FastAPI |
| `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD` | No | No | Web and mobile related questions | `0.1` | FastAPI |
| `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` | Legacy only | No | Settings parser only; no behavioral consumer | `0.5` | None |
| `RAG_MAX_NEW_TOKENS` | No | No | General generation | `500` | FastAPI |
| `RAG_CHITCHAT_MAX_NEW_TOKENS` | No | No | Chitchat generation | `200` | FastAPI |
| `RAG_REWRITE_MAX_TOKENS` | No | No | Query rewrite | `1000` | FastAPI |
| `SQLALCHEMY_POOL_SIZE` | Legacy only | No | Inactive SQLAlchemy pool | `5` | Legacy command |
| `SQLALCHEMY_MAX_OVERFLOW` | Legacy only | No | Inactive SQLAlchemy pool | `10` | Legacy command |
| `SQLALCHEMY_POOL_TIMEOUT` | Legacy only | No | Inactive SQLAlchemy pool | `30` | Legacy command |
| `SQLALCHEMY_POOL_RECYCLE` | Legacy only | No | Inactive SQLAlchemy pool | `3600` | Legacy command |
| `SQLALCHEMY_ECHO` | Legacy only | No | Inactive SQLAlchemy pool | `false` | Legacy command |
| `RAGBOT_STAGING_AUTH_TOKEN` | Load test only | Yes | Staging load generator | None | Load-test script |
| `RAGBOT_STAGING_LIMITER_CAPACITY` | No | No | Load-test report metadata | Source constant | Load-test script |
| `RAGBOT_STAGING_GPU_INFO` | No | Internal | Load-test report metadata | Source constant | Load-test script |
| `RAGBOT_VLLM_IMAGE` | No | Internal | Load-test report metadata | `unknown` | Load-test script |
| `RAGBOT_TEI_EMBED_IMAGE` | No | Internal | Load-test report metadata | `unknown` | Load-test script |
| `RAGBOT_TEI_RERANK_IMAGE` | No | Internal | Load-test report metadata | `unknown` | Load-test script |

## Detailed records

### Application and server

#### `ENVIRONMENT`

- **Meaning/category:** Intended deployment label; no code consumer was found.
- **Required/current/type:** Apparently unused; set; string with suggested values
  `development`, `staging`, or `production`.
- **Safe example/default/recommendation:** `staging`; no default. Keep only as
  operator metadata or add explicit validation before relying on it.
- **Effect/failure/impact:** Changing it currently changes nothing. It cannot
  enforce staging/production safety. Correctness risk comes from assuming it
  does.
- **Restart/sensitivity/related:** No restart; safe to document; related to the
  validator's `--mode`, which is not an application variable.
- **Sources:** defined `.env:4`, `env.example:4`; no consumer found.

#### `API_HOST` and `API_PORT`

- **Meaning/category:** Address and TCP port used only by direct
  `python main.py`. Host is a string; port must be an integer from 1 to 65535.
- **Required/current/examples:** Optional; both set. Safe examples:
  `API_HOST=0.0.0.0`, `API_PORT=8080`.
- **Defaults/recommendation:** `0.0.0.0` and `8080`. Bind to `127.0.0.1` when
  only a local proxy should connect. Use the deployment-assigned port.
- **Effect/failure/impact:** Host changes reachability/security. Port changes
  routing correctness. `API_PORT` is not explicitly converted to `int`, so an
  invalid value can fail at server startup.
- **Restart/sensitivity/related:** Restart FastAPI; host is internal and port is
  safe to document. CLI Uvicorn/Gunicorn settings take precedence when those
  servers are launched directly because this block does not execute.
- **Sources:** `.env:5-6`; loaded `main.py:15`; consumed `main.py:1476-1480`.

### Qdrant

#### `QDRANT_URL`

- **Meaning/category:** A complete Qdrant URL from an older abstraction.
- **Required/current/type:** Apparently unused by the verified runtime; set;
  HTTP(S) URL without embedded credentials.
- **Safe example/default/recommendation:** `http://127.0.0.1:6333`; no default.
  Deprecate in favor of the split fields used by FastAPI.
- **Effect/failure/impact:** It does not override the active split fields.
  Keeping inconsistent values misleads operators.
- **Restart/sensitivity/related:** Legacy process only; internal;
  `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_HTTPS`.
- **Sources:** `.env:18`; legacy consumers
  `new_architecture/app/core/vector_db.py:310,718`; active construction uses
  `new_architecture/app/services/db_connection/connection.py:81-87`.

#### `QDRANT_HOST`, `QDRANT_PORT`, and `QDRANT_HTTPS`

- **Meaning/category:** Qdrant network host, port, and TLS switch.
- **Required/current/types:** Optional due defaults; all set. Host string, port
  integer 1-65535, boolean accepted by application only when exactly
  case-insensitive `true`.
- **Safe examples/defaults:** `localhost`, `6333`, `false`; these are also the
  defaults.
- **Recommendation/effect:** Use a resolvable Docker service name inside a
  container and `localhost` only when Qdrant shares the same network namespace.
  TLS must match the endpoint. Wrong values fail FastAPI startup while listing
  collections.
- **Impact/restart/sensitivity:** Network latency and TLS overhead; restart
  FastAPI; host is internal, port/TLS flag are safe to document.
- **Sources:** defaults `main.py:54-59`,
  `new_architecture/app/config.py:47-56`; passed to client
  `new_architecture/app/services/db_connection/connection.py:81-87`.

#### `QDRANT_API_KEY`

- **Meaning/category:** Credential accepted by Qdrant.
- **Required/current/type:** Code-optional; required by this manual's production
  security policy; currently empty; secret string.
- **Safe example/default/recommendation:** `change-me`; no default. Obtain it
  from an approved secret store and do not commit it.
- **Effect/failure/impact:** Missing/incorrect authentication can cause startup
  failure or, if Qdrant permits anonymous access, an insecure deployment.
- **Restart/related:** Restart FastAPI; secret; related to Qdrant TLS/address.
- **Sources:** loaded `main.py:58`; passed
  `new_architecture/app/services/db_connection/connection.py:81-87`; insertion
  `new_architecture/insert_data.py:109`.

#### `QDRANT_COLLECTION`

- **Meaning/category:** Name of the collection holding document vectors.
- **Required/current/type:** Optional due default; set; non-empty string.
- **Safe example/default/recommendation:** `hihelp_embeddings`; same code
  default. Use one intentionally provisioned collection per compatible
  embedding policy.
- **Effect/failure/impact:** Changing it changes persistent data selection and
  may create a new empty collection at startup. Wrong names produce empty or
  incorrect retrieval.
- **Restart/related:** Restart FastAPI and insertion tools; safe to document;
  related to vector size and embedding policy.
- **Sources:** defaults `main.py:56`,
  `new_architecture/app/config.py:51`; collection creation
  `new_architecture/app/services/db_connection/connection.py:92-104`;
  retrieval `utils/persian_hybrid_search.py:220,246`.

#### `QDRANT_VECTOR_SIZE`

- **Meaning/category:** Number of numeric elements in every vector.
- **Required/current/type:** Optional; set; positive integer.
- **Safe example/default/recommendation:** `1024`; active default and required
  by the verified TEI policy. Do not change without rebuilding a collection and
  running retrieval/answer-quality tests.
- **Effect/failure/impact:** A mismatch causes response validation or Qdrant
  insertion/search failure; it affects memory and vector-search cost.
- **Conflict:** Active code and TEI use 1024, while inactive
  `app/core/database.py` defaults to 384. Active configuration wins on the
  verified path.
- **Restart/related:** Restart FastAPI and insertion; safe to document; related
  to collection and embedding model.
- **Sources:** active defaults/validation `main.py:57`,
  `utils/persian_hybrid_search.py:284-290`,
  `utils/tei_embedding_client.py:14,44-67`; collection
  `new_architecture/app/services/db_connection/connection.py:96-102`; conflicting
  legacy default `new_architecture/app/core/database.py:70`.

### PostgreSQL

#### `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`

- **Meaning/category:** Target database server, TCP port, and database name used
  by FastAPI and insertion tools.
- **Required/current/types:** Required on the active path; all set. Host/database
  are internal strings; port is integer 1-65535.
- **Safe examples/defaults:** `localhost`, `5432`, `ragbot`. The active
  `db_manager` has no defaults; other modules default to `5432` and
  `hihelp_db`; inactive pool defaults the database to `rag_db`.
- **Recommendation/effect:** Configure the same target across all FastAPI
  managers. Changing the database changes persistent users, sessions, and
  documents. Wrong values fail at import/startup or first operation.
- **Performance/security:** Network placement affects latency. PostgreSQL
  connect, statement, and lock timeouts are hardcoded at 5 s, 10 s, and 3 s,
  not environment-controlled.
- **Restart/related:** Restart FastAPI or rerun the tool; internal except the
  port. Related to `POSTGRES_USER/PASSWORD` and `DEFAULT_DB_*`.
- **Sources:** raw required reads `main.py:183-184`; defaults
  `new_architecture/app/config.py:24-32`; connection options
  `new_architecture/app/services/history/database.py:26-36`; inactive conflict
  `new_architecture/app/core/database.py:53-57`.

#### `POSTGRES_USER` and `POSTGRES_PASSWORD`

- **Meaning/category:** Target database login.
- **Required/current/type:** Required and set; secret credential strings.
- **Safe example/default/recommendation:** `change-me`; active manager has no
  default. Never use legacy development credentials in staging or production;
  inject them from a secret manager where available.
- **Effect/failure/impact:** Incorrect credentials fail startup/queries.
  Rotation requires reconnecting. Permissions determine data security and
  correctness.
- **Restart/related:** Restart FastAPI and rerun standalone tools; secret;
  related to all `POSTGRES_*`.
- **Sources:** `main.py:183-184`,
  `new_architecture/app/config.py:30-32`,
  `new_architecture/app/services/history/database.py:26-36`.

#### `DEFAULT_DB_HOST`, `DEFAULT_DB_PORT`, `DEFAULT_DB_NAME`

- **Meaning/category:** Administrative database used only to create the target
  database.
- **Required/current/type:** Required only for
  `new_architecture/setup_dbs.py`; set. Host/name strings, port integer.
- **Safe examples/defaults:** `localhost`, `5432`, `postgres`; no code defaults.
- **Recommendation/effect:** Do not point these at production from staging.
  Missing values create malformed async PostgreSQL URLs and setup fails.
- **Restart/impact:** Rerun setup command only; data-persistence and security
  impact; internal.
- **Sources:** reads `new_architecture/setup_dbs.py:55-59`; URL construction
  `new_architecture/setup_dbs.py:84-93`.

#### `DEFAULT_DB_USER` and `DEFAULT_DB_PASSWORD`

- **Meaning/category:** Administrative setup credential, distinct from the
  target application's login.
- **Required/current/type:** Setup-command only; set; secret strings.
- **Safe example/default/recommendation:** `change-me`; no defaults. Grant only
  the privileges needed for setup and source from an approved secret store.
- **Effect/failure/impact:** Wrong values stop setup; overly broad privileges
  increase security risk. Special URL characters are not percent-encoded by the
  script and can break connection URLs.
- **Restart/related:** Rerun setup only; secret; related to `DEFAULT_DB_*` and
  `POSTGRES_*`, but neither set overrides the other.
- **Sources:** reads `new_architecture/setup_dbs.py:57-58`; interpolated into
  URL `new_architecture/setup_dbs.py:84-88`.

### MinIO

#### `MINIO_ENDPOINT`

- **Meaning/category:** MinIO host and port, without a URL scheme.
- **Required/current/type:** Effectively required; set; `host:port` string.
- **Safe example/default/recommendation:** `localhost:9000`; default. Use a
  Docker service name only from another container.
- **Effect/failure/impact:** Wrong topology or port makes FastAPI startup fail.
  Network placement affects startup/object latency.
- **Restart/related:** Restart FastAPI/tool; internal; related to
  `MINIO_SECURE`.
- **Sources:** default `new_architecture/app/config.py:36`; passed
  `new_architecture/app/services/db_connection/connection.py:61-66`.

#### `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`

- **Meaning/category:** MinIO authentication pair.
- **Required/current/type:** Required and set; secret strings.
- **Safe example/default/recommendation:** `change-me`; active config has no
  defaults. Avoid the unsafe development defaults present in insertion/legacy
  modules.
- **Effect/failure/impact:** Incorrect values fail startup; exposure permits
  object access. Rotation requires reconnecting.
- **Restart/related:** Restart FastAPI/tool; secret; related to endpoint/TLS.
- **Sources:** active reads `new_architecture/app/config.py:38-40`; client
  `new_architecture/app/services/db_connection/connection.py:61-66`; unsafe
  data-tool defaults `new_architecture/insert_data.py:91-95`.

#### `MINIO_SECURE`

- **Meaning/category:** Whether MinIO uses TLS.
- **Required/current/type:** Optional; set; boolean.
- **Safe example/default/recommendation:** `false` locally, `true` when the
  endpoint provides TLS. Active FastAPI currently hardcodes `False`, so the
  environment value does not take effect there.
- **Effect/failure/impact:** In insertion tools it selects HTTP/HTTPS. One
  insertion script passes the raw string without boolean parsing, so even
  `"false"` can behave incorrectly. This is a security and correctness risk.
- **Restart/related:** Restart FastAPI or rerun insertion; safe to document;
  related to endpoint. Fixing code is outside this audit.
- **Sources:** ignored active setting `new_architecture/app/config.py:41`;
  consumed `new_architecture/app/services/db_connection/connection.py:61-66`;
  inconsistent parsers `new_architecture/insert_data.py:94`,
  `new_architecture/data_insertion_with_api.py:94`.

#### `MINIO_BUCKET`

- **Meaning/category:** Persistent object bucket.
- **Required/current/type:** Required and set; non-empty string.
- **Safe example/default/recommendation:** `ragbot-documents`; active config has
  no default. Choose one explicit bucket and keep all tools aligned.
- **Effect/failure/impact:** Startup creates it if absent, so a typo silently
  creates/selects different persistent storage. Defaults conflict:
  `hihelp-documents` in insertion and `documents` in the inactive pool.
- **Restart/related:** Restart FastAPI/tool; safe to document; related to data
  persistence and MinIO credentials.
- **Sources:** active read `new_architecture/app/config.py:43`; create/check
  `new_architecture/app/services/db_connection/connection.py:68-71`; conflicts
  `new_architecture/insert_data.py:95`,
  `new_architecture/app/core/database.py:64`.

### vLLM and TEI service URLs

#### `VLLM_URL`

- **Meaning/category:** Base URL for vLLM's OpenAI-compatible API, including
  `/v1`.
- **Required/current/type:** Optional due default; set; HTTP(S) URL without
  credentials.
- **Safe example/default/recommendation:** `http://localhost:8000/v1`; default.
  Use the actual service name inside Docker. This repository does not define
  vLLM's model path, `max_num_seqs`, `max_num_batched_tokens`, or server port.
- **Effect/failure/impact:** Wrong URL fails generation at request time. Network
  placement affects latency; model/server behavior is not selected by
  `LLM_MODEL`.
- **Restart/related:** Restart FastAPI, not vLLM; internal; related to
  `VLLM_HTTP_*`.
- **Sources:** reads `main.py:297`, `utils/RagSystem.py:51`; passed to
  `AsyncOpenAI` `utils/RagSystem.py:74-108`.

#### `TEI_EMBED_URL`

- **Meaning/category:** Base URL for query/document embedding.
- **Required/current/type:** Required and set; HTTP(S) URL without credentials.
- **Safe example/recommendation:** `http://127.0.0.1:7997` for the documented
  host-local staging layout. Inside Docker, use the embedding container's
  service name and internal port.
- **Effect/failure/impact:** Missing fails RAG initialization; malformed/wrong
  values fail embedding. It must point to embedding, not reranking.
- **Correctness:** Query payload uses `prompt_name="query"` while stored
  documents use raw semantics; returned vectors must match
  `QDRANT_VECTOR_SIZE`.
- **Restart/related:** Restart FastAPI/tool, not TEI itself; internal; related to
  TEI timeouts and vector size.
- **Sources:** active read/validation
  `utils/persian_hybrid_search.py:225,248-250`; request
  `utils/tei_embedding_client.py:104-143`; prompt policy
  `utils/tei_embedding_client.py:14-41`.

#### `TEI_RERANK_URL`

- **Meaning/category:** Base URL for the separate reranker service.
- **Required/current/type:** Required and set; HTTP(S) URL.
- **Safe example/recommendation:** `http://127.0.0.1:7998` for documented
  staging. Never point it at the embedding port.
- **Effect/failure/impact:** Missing currently reaches `.rstrip()` and fails RAG
  initialization; wrong service causes protocol/request failures.
- **Restart/related:** Restart FastAPI, not TEI reranker; internal; related to
  TEI HTTP settings and rerank thresholds.
- **Sources:** `utils/RagSystem.py:52,109`,
  `utils/persian_hybrid_search.py:226,274`; staging ports `AGENTS.md:12,92`.

#### `EMBEDDING_MODEL`, `LLM_MODEL`, `RERANKER_MODEL`

- **Meaning/category:** Historical local-model path/name metadata.
- **Required/current/type:** Not behaviorally required; all set; internal
  strings/paths.
- **Safe examples/default/recommendation:** Leave blank unless a documented
  legacy command needs them; no defaults. Actual vLLM/TEI models are selected
  by external server startup commands, which are absent from this repository.
- **Effect/failure/impact:** `LLM_MODEL` is loaded but never consumed.
  `EMBEDDING_MODEL` is captured by an unused constructor parameter.
  `RERANKER_MODEL` feeds a parameter whose local loading code is commented out.
  Changing them does not select active served models.
- **Restart/related:** No effective runtime restart, though values are read at
  import; internal. Related to service URLs and `EMBEDDING_MODEL_NAME`.
- **Sources:** loads `new_architecture/app/config.py:16-18`; unused parameters
  `utils/persian_hybrid_search.py:221`,
  `utils/RagSystem.py:46,133-137`.

#### `EMBEDDING_MODEL_NAME`

- **Meaning/category:** Likely alias for a local embedding model in an inactive
  service.
- **Required/current/type:** Legacy only; missing; internal path/string.
- **Safe example/default/recommendation:** Leave unset. If the legacy service is
  revived, consolidate on `EMBEDDING_MODEL`.
- **Effect/failure/impact:** The default argument becomes `None`; failure is
  delayed until that class is instantiated.
- **Restart/related:** Legacy process; internal; overlaps `EMBEDDING_MODEL`.
- **Sources:** `new_architecture/app/services/embedding/embedding.py:29-32`;
  no verified active importer.

### Data preparation

#### `KNOWLEDGE_BASE_CSV`

- **Meaning/category:** Input CSV path for the chunk-preparation helper.
- **Required/current/type:** Required only for that helper; set; file path.
- **Safe example/default/recommendation:** `/path/to/synthetic-knowledge-base.csv`;
  no default. Use an existing readable, non-customer test file first.
- **Effect/failure/impact:** Missing/invalid path fails during `pandas.read_csv`;
  affects inserted knowledge and therefore answer correctness.
- **Restart/related:** Rerun helper only; internal; related to insertion
  directory.
- **Sources:** `hihelp_knowledge_changer.py:8,14-15`.

#### `DATA_INSERTION_DIRECTORY`

- **Meaning/category:** Root containing `DOCUMENTS` and `CHUNKS`.
- **Required/current/type:** Required for insertion tools; set; directory path.
- **Safe example/default/recommendation:** `/path/to/ragbot-data`; no default.
  Verify the target environment before running because insertion writes data.
- **Effect/failure/impact:** Missing causes import-time path errors; wrong path
  inserts incorrect/no data.
- **Restart/related:** Rerun insertion only; internal/data-persistence impact;
  related to TEI batch size and storage settings.
- **Sources:** `new_architecture/insert_data.py:132-145`,
  `new_architecture/data_insertion_with_api.py:133`.

### Timeouts

#### `APPLICATION_REQUEST_TIMEOUT_SECONDS`

- **Meaning/category:** Total FastAPI deadline for a web/mobile AI operation.
- **Required/current/type:** Optional; set; positive float, maximum 50.
- **Safe example/default/recommendation:** `50`; code default and external
  maximum. Lower only with measured evidence and acceptable timeout rate.
- **Effect/failure/impact:** Lower values cancel sooner; higher values above 50
  are rejected at import. It bounds queueing plus all downstream work.
- **Restart/related:** Restart FastAPI; safe; related to every timeout below.
- **Sources:** validation `utils/performance_config.py:83-87`; endpoint use
  `main.py:569-581,1032-1045`, `mobile_api.py:80-100`.

#### `REQUEST_ADMISSION_TIMEOUT_SECONDS`

- **Meaning/category:** Maximum time waiting for an application semaphore slot.
- **Required/current/type:** Optional; set; positive float.
- **Safe example/default/recommendation:** `12`; default. Keep below the total
  deadline so admitted work retains a useful execution budget.
- **Effect/failure/impact:** Higher values increase queueing; lower values cause
  faster busy responses.
- **Restart/related:** Restart FastAPI; latency/queueing/timeout impact; related
  to request concurrency and total deadline.
- **Sources:** default `utils/performance_config.py:91-93`; semaphore wait
  `utils/concurrency.py:96-112`; consumers `main.py:581`,
  `mobile_api.py:86-94`.

#### `TEI_HTTP_CONNECT_TIMEOUT_SECONDS`, `TEI_HTTP_READ_TIMEOUT_SECONDS`,
`TEI_HTTP_WRITE_TIMEOUT_SECONDS`, `TEI_HTTP_POOL_TIMEOUT_SECONDS`

- **Meaning/category:** Separate limits for opening a connection, waiting for
  TEI response bytes, sending the request, and waiting for a pooled connection.
- **Required/current/type:** Optional; all set; positive floats.
- **Safe examples/defaults:** `3`, `15`, `5`, `3` seconds.
- **Recommendation/effect:** Keep each operation and any preceding queue time
  within the 50-second endpoint budget. Read timeout most directly bounds TEI
  inference; pool timeout exposes client saturation.
- **Failure/impact:** Invalid/non-positive values fail at import. Timeouts become
  service timeout/unavailable errors; they affect latency, queueing, and
  throughput.
- **Restart/related:** Restart FastAPI/insertion; safe; related to TEI pool
  sizes and both TEI URLs.
- **Sources:** defaults/validation `utils/performance_config.py:106-117`;
  HTTPX construction `main.py:254-274`,
  `utils/persian_hybrid_search.py:251-273`.

#### `VLLM_HTTP_CONNECT_TIMEOUT_SECONDS`, `VLLM_HTTP_READ_TIMEOUT_SECONDS`,
`VLLM_HTTP_WRITE_TIMEOUT_SECONDS`, `VLLM_HTTP_POOL_TIMEOUT_SECONDS`

- **Meaning/category:** The same four client phases for vLLM.
- **Required/current/type:** Optional; all set; positive floats.
- **Safe examples/defaults:** `3`, `45`, `5`, `3` seconds.
- **Recommendation/effect:** The 45-second read timeout is deliberately below
  the 50-second total, but admission, pool wait, connect, and write time also
  consume the total budget. It is not a separate 56-second allowance.
- **Failure/impact:** Invalid values fail at import; expiry surfaces as a model
  timeout. Larger read values can leave less time for persistence/response.
- **Restart/related:** Restart FastAPI; latency/queueing impact; related to
  vLLM pool sizes and total deadline.
- **Sources:** defaults `utils/performance_config.py:133-143`; HTTPX/OpenAI
  clients `main.py:275-309`, `utils/RagSystem.py:74-108`.

#### `TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS` and
`VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS`

- **Meaning/category:** Seconds an idle reusable HTTP connection remains open.
- **Required/current/type:** Optional; set; positive floats; default `30`.
- **Recommendation/effect:** Keep defaults until connection-reuse measurements
  justify change. Too low adds connection setup; too high retains idle sockets.
- **Failure/impact:** Invalid values fail at import; affects latency, socket
  memory, and connection churn.
- **Restart/related:** Restart FastAPI/tool; safe; related to corresponding pool
  limits.
- **Sources:** `utils/performance_config.py:103-104,130-131`; applied
  `main.py:260-295`.

### Concurrency and pools

#### `REQUEST_CONCURRENCY_LIMIT`

- **Meaning/category:** Maximum admitted AI operations per FastAPI process.
- **Required/current/type:** Optional; set; positive integer.
- **Safe example/default/recommendation:** `32`; code default and current
  documented strategy, not a proof that 32 requests meet latency targets.
- **Effect/failure/impact:** Higher values increase downstream queueing/GPU
  contention; lower values reject/wait earlier. Every worker gets its own
  semaphore.
- **Restart/related:** Restart FastAPI; throughput/latency/memory impact;
  related to all pool/concurrency variables.
- **Sources:** default `utils/performance_config.py:88-90`; semaphore
  `main.py:222-223`; usage `main.py:569-581`, `mobile_api.py:86-94`.

#### `BLOCKING_CONCURRENCY_LIMIT`

- **Meaning/category:** Maximum synchronous database/Qdrant/filesystem jobs
  offloaded from async paths.
- **Required/current/type:** Optional; set; positive integer; default `16`.
- **Recommendation/effect:** Keep until event-loop/thread measurements justify
  change. Higher values increase threads and downstream pressure; lower values
  serialize blocking work.
- **Failure/impact:** Invalid values fail import; affects queueing, throughput,
  memory, and cancellation behavior.
- **Restart/related:** Restart FastAPI; safe; related to request concurrency.
- **Sources:** `utils/performance_config.py:94-96`; constructed
  `main.py:222-233`; async usage visible in `mobile_api.py:107-124`.

#### `TEI_HTTP_MAX_CONNECTIONS` and
`TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS`

- **Meaning/category:** Total and idle-reusable TEI client connections per
  process.
- **Required/current/type:** Optional; set; positive integers; defaults `32`
  and `16`.
- **Recommendation/effect:** Keep-alive must not exceed total. Raising total can
  reduce client pool waits but overload TEI; raising keep-alive retains sockets.
- **Failure/impact:** Invalid or reversed values fail import; affects throughput,
  latency, sockets, memory, and TEI queueing.
- **Restart/related:** Restart FastAPI/tool; safe; not the TEI server's
  `max_concurrent_requests`.
- **Sources:** validation `utils/performance_config.py:97-102,164-171`;
  applied `main.py:260-273`.

#### `VLLM_HTTP_MAX_CONNECTIONS` and
`VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS`

- **Meaning/category:** Total and reusable vLLM client connections per process.
- **Required/current/type:** Optional; set; positive integers; defaults `32`
  and `16`.
- **Recommendation/effect:** Keep-alive must not exceed total. These client
  limits do not configure vLLM scheduler concurrency.
- **Failure/impact:** Invalid/reversed values fail import; values affect client
  pool waits, sockets, vLLM queueing, throughput, and latency.
- **Restart/related:** Restart FastAPI, not vLLM; safe; related to
  `REQUEST_CONCURRENCY_LIMIT`.
- **Sources:** validation `utils/performance_config.py:124-129,180-187`;
  applied `main.py:284-309`.

#### `QDRANT_CONCURRENCY`

- **Meaning/category:** Per-search-engine semaphore around Qdrant operations.
- **Required/current/type:** Optional; set; positive integer; default `4`.
- **Recommendation/effect:** Keep default absent a controlled latency/recall
  benchmark. Higher values increase Qdrant/network pressure; lower values
  increase application queueing.
- **Failure/impact:** Invalid values fail import; affects throughput and latency,
  not Qdrant's own server pool settings.
- **Restart/related:** Restart FastAPI; safe; related to request concurrency.
- **Sources:** default `utils/performance_config.py:145`; semaphore
  `utils/persian_hybrid_search.py:280-282`.

#### `SQLALCHEMY_POOL_SIZE`, `SQLALCHEMY_MAX_OVERFLOW`,
`SQLALCHEMY_POOL_TIMEOUT`, `SQLALCHEMY_POOL_RECYCLE`, `SQLALCHEMY_ECHO`

- **Meaning/category:** Base connections, temporary overflow, pool wait,
  connection lifetime, and SQL logging for a SQLAlchemy implementation.
- **Required/current/types:** Legacy/inactive; all missing and therefore
  defaulted to `5`, `10`, `30`, `3600`, `false`. Integers are non-negative or
  positive; echo is boolean.
- **Recommendation/effect:** Do not tune for the active FastAPI path: it uses
  per-operation psycopg2 connections. If this pool is activated, size it
  against database capacity and keep SQL echo off around sensitive data.
- **Failure/impact:** Invalid integers fail module import. Pool values affect
  connections, queueing, latency, memory; echo can expose query data.
- **Restart/related:** Restart only a process that imports this legacy module;
  safe except logs; related to request concurrency and PostgreSQL capacity.
- **Sources:** definitions `new_architecture/app/core/database.py:53-78`;
  engine `new_architecture/app/core/database.py:102-120`; verified active path
  instead uses `main.py:183-184`.

### Retrieval, reranking, and generation

#### `RAG_RETRIEVAL_TOP_K` and `RAG_SEMANTIC_CANDIDATE_LIMIT`

- **Meaning/category:** Final retrieved result count and larger semantic
  candidate pool considered before ranking.
- **Required/current/type:** Optional; set; positive integers; defaults `10`
  and `50`.
- **Recommendation/effect:** `TOP_K` must not exceed candidate limit. Larger
  pools may improve recall but increase Qdrant transfer, PostgreSQL material,
  reranking, prompt size, latency, and memory.
- **Failure/impact:** Invalid/reversed values fail import. Any change can alter
  answers, so run retrieval and answer-quality tests plus before/after latency
  benchmarks.
- **Restart/related:** Restart FastAPI; safe; related to vector collection and
  rerank thresholds.
- **Sources:** validation/defaults
  `utils/performance_config.py:146-149,188-192`; consumers in retrieval
  `utils/persian_hybrid_search.py:430-570`.

#### `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD`

- **Meaning/category:** Minimum TEI reranker score for related-question output
  on both web and mobile paths.
- **Required/current/type:** Optional; set; float from 0 through 1; default
  `0.1`.
- **Recommendation/effect:** Keep `0.1` until quality evaluation. Higher values
  return fewer, more selective suggestions; lower values return more and may
  reduce relevance.
- **Failure/impact:** Out-of-range values fail import. Changes affect answer UI
  behavior/quality, not model-serving capacity directly.
- **Restart/related:** Restart FastAPI; safe; related to candidate counts.
- **Sources:** validation `utils/performance_config.py:150-152`; canonical
  consumption `agent_graph.py:168-175`.

#### `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD`

- **Meaning/category:** Legacy threshold for a former second, endpoint-level
  mobile rerank.
- **Required/current/type:** Apparently unused; set; float from 0 through 1;
  compatibility default `0.5`.
- **Recommendation/effect:** Do not add it to new configurations. The settings
  loader still validates it for compatibility, but no active request path
  consumes it.
- **Failure/impact:** A malformed or out-of-range value can still fail settings
  loading even though a valid value has no runtime effect.
- **Restart/related:** No behavioral change to activate; remove only as a
  reviewed configuration cleanup.
- **Sources:** compatibility parsing
  `utils/performance_config.py:76-77,153-155`; single active rerank
  `agent_graph.py:168-175`.

#### `RAG_MAX_NEW_TOKENS`, `RAG_CHITCHAT_MAX_NEW_TOKENS`,
`RAG_REWRITE_MAX_TOKENS`

- **Meaning/category:** Maximum completion tokens for general answers, chitchat,
  and query rewriting.
- **Required/current/type:** Optional; set; positive integers; defaults `500`,
  `200`, `1000`.
- **Recommendation/effect:** Treat changes as model-behavior changes. Larger
  limits permit longer output and can increase decode time, GPU/KV usage, and
  timeout risk; smaller limits can truncate output.
- **Failure/impact:** Invalid values fail import. A large rewrite ceiling is a
  latency risk even if typical output is short.
- **Restart/related:** Restart FastAPI; safe; related to vLLM read timeout,
  total deadline, and external vLLM context/model-length settings.
- **Sources:** defaults `utils/performance_config.py:156-162`; selection/use
  `utils/RagSystem.py:252-265,365`.

#### `TEI_EMBED_INSERT_BATCH_SIZE` and
`TEI_EMBED_MAX_CLIENT_BATCH_SIZE`

- **Meaning/category:** Documents per insertion request and the known
  client-side ceiling.
- **Required/current/type:** Optional; both missing/defaulted to `32` and `50`;
  positive integers.
- **Recommendation/effect:** Batch size must not exceed maximum. Defaults are
  repository policy, not a verified TEI server limit in this audit. Larger
  batches can improve throughput but increase latency, payload memory, and GPU
  work.
- **Failure/impact:** Invalid/reversed values fail import. Server/client limit
  mismatch fails insertion requests.
- **Restart/related:** Rerun insertion; settings module also requires FastAPI
  restart to reload; safe; related to TEI service startup flags, which are not
  present in this repository.
- **Sources:** defaults/relationship
  `utils/performance_config.py:118-123,172-179`; insertion
  `new_architecture/insert_data.py:1378-1397`,
  `utils/tei_embedding_batches.py:66-106`.

### Staging load-test variables

#### `RAGBOT_STAGING_AUTH_TOKEN`

- **Meaning/category:** Optional bearer token for the staging mobile-talk load
  generator.
- **Required/current/type:** Required only when the gateway requires it;
  missing; secret string.
- **Safe example/default/recommendation:** `change-me`; no default. Export it
  temporarily from an approved secret source; do not use `--auth-token` because
  command arguments can appear in history/process lists.
- **Effect/failure/impact:** Missing authentication yields authorization
  failures; it does not change FastAPI authentication configuration.
- **Restart/related:** Start a new load-test process only; secret; staging only.
- **Sources:** `benchmarks/load/mobile_talk_load_test.py:1820-1837,1864-1868`;
  guidance `benchmarks/load/README.md:24,145`.

#### `RAGBOT_STAGING_LIMITER_CAPACITY` and `RAGBOT_STAGING_GPU_INFO`

- **Meaning/category:** Operator-supplied report metadata, not live
  configuration.
- **Required/current/type:** Optional; missing; strings.
- **Safe examples/defaults:** `unknown`; source constants supply descriptive
  defaults. Record only sanitized, non-secret facts.
- **Effect/failure/impact:** Changes report context only; incorrect metadata can
  invalidate benchmark interpretation.
- **Restart/related:** New load-test process; internal; staging only.
- **Sources:** `benchmarks/load/mobile_talk_load_test.py:1308-1313`.

#### `RAGBOT_VLLM_IMAGE`, `RAGBOT_TEI_EMBED_IMAGE`,
`RAGBOT_TEI_RERANK_IMAGE`

- **Meaning/category:** Container-image identifiers copied into benchmark
  reports.
- **Required/current/type:** Optional; missing/defaulted to `unknown`; internal
  strings.
- **Safe example/recommendation:** `unknown` when not independently verified.
  These values do not start or configure any server.
- **Effect/failure/impact:** Report metadata only; stale identifiers undermine
  reproducibility but do not affect runtime.
- **Restart/related:** New load-test process; internal; related to externally
  managed vLLM/TEI deployment.
- **Sources:** `benchmarks/load/mobile_talk_load_test.py:1314-1320`.

## Precedence and loading

The verified Python entry points call `load_dotenv()` without
`override=True`: `main.py:12-15`, `new_architecture/app/config.py:1-5`,
`utils/RagSystem.py:14-15`, `utils/persian_hybrid_search.py:21-24`,
`new_architecture/setup_dbs.py:39-43`, and insertion scripts at
`new_architecture/insert_data.py:33-36` and
`new_architecture/data_insertion_with_api.py:33-36`.

For those entry points the effective order is:

1. An already exported process environment value wins.
2. `load_dotenv()` searches for `.env` and fills only missing process keys.
3. Each `os.getenv(name, default)` supplies its local hardcoded default.
4. A missing `os.getenv(name)` becomes `None`, often failing at startup or first
   use.

Docker Compose, Kubernetes, systemd, Dockerfiles, and repository-owned shell
startup scripts were not found, so there is no repository-specific precedence
to add. If Uvicorn/Gunicorn is launched with command-line host, port, or worker
flags, those server CLI flags govern that external launch; `main.py:1476-1480`
does not execute. vLLM and TEI server command-line flags are external and are
not controlled by variables in this repository.

Several values are captured at module import or even as function default
arguments (`utils/RagSystem.py:44-56`,
`utils/persian_hybrid_search.py:217-231`,
`new_architecture/app/services/history/database.py:26-29`). Changing `.env`
after import has no effect until the process restarts.

## Important relationships

### Timeout layers

`APPLICATION_REQUEST_TIMEOUT_SECONDS` is the entire FastAPI operation budget.
`REQUEST_ADMISSION_TIMEOUT_SECONDS` is only the wait for an application slot.
TEI and vLLM connect/read/write/pool values protect individual client phases.
They are not duplicates and none automatically subtracts time from another.
A downstream read timeout should normally be shorter than the total deadline,
leaving time for admission, connection, persistence, and response serialization.
PostgreSQL uses hardcoded connect/statement/lock timeouts of 5/10/3 seconds;
Qdrant uses a hardcoded 10-second client timeout
(`new_architecture/app/services/db_connection/connection.py:43-50,81-87`).

### Concurrency layers

`REQUEST_CONCURRENCY_LIMIT` admits application operations.
`BLOCKING_CONCURRENCY_LIMIT` limits synchronous work offloaded from async code.
HTTP maximum connections constrain client sockets. `QDRANT_CONCURRENCY` guards
vector calls. TEI server admission and vLLM `max_num_seqs` are external and
unknown. Setting every number to 50 would not mean 50 requests finish quickly:
the slowest queue, database, or shared GPU still determines throughput.

### URL versus host and port

`TEI_EMBED_URL=http://127.0.0.1:7997` is one complete address used directly by
HTTPX. A hypothetical `TEI_EMBED_HOST` plus `TEI_EMBED_PORT` does not exist in
this repository. Qdrant is the opposite: active code uses `QDRANT_HOST`,
`QDRANT_PORT`, and `QDRANT_HTTPS`; `QDRANT_URL` does not override them.

`localhost` means “this same process/container.” From a Docker container it
does not mean the host machine or another container. A Docker service name is
needed for another container on the same Compose network.

## Settings not present

No repository environment consumers or startup manifests were found for
Uvicorn/Gunicorn worker count, vLLM `max_num_seqs`,
`max_num_batched_tokens`, max model length/model path, TEI server
`max_concurrent_requests`/max client batch size flags, Qdrant server connection
pool, Redis runtime, JWT secret/token lifetime/authentication flags,
observability exporters, or a full `DATABASE_URL`. These may be configured
outside the repository, but inventing local variables would not affect the
current code.
