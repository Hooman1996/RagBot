# RagBot environment audit

Audit date: 2026-07-29  
Repository: `/root/projects/faq`  
Scope: static, read-only configuration discovery plus a non-destructive local
validator. No endpoint, database, object store, vector store, vLLM, TEI,
container, or production configuration was contacted or changed.

## Executive summary

The repository has 73 known environment-variable names. The current `.env`
contains 59 assignments: 45 affect the verified FastAPI runtime, 8 are used
only by explicit setup/insertion/development commands, and 6 are apparently
unused or behaviorally ineffective. Fourteen referenced variables are absent;
all have defaults or belong to legacy/benchmark-only paths.

The current file passes the new staging validator's syntax, type, range, and
cross-field checks without a critical validation error. That does **not** mean
the deployment is safe: `.env` and `.env.server_git` are tracked in Git, and
credential-like literals also exist in source comments/test configuration.
Those are the most urgent findings.

## Counts

| Measure | Count | Interpretation |
|---|---:|---|
| Assignments in current `.env` | 59 | Unique names; values not reproduced |
| Present and effective on verified FastAPI runtime | 45 | Includes direct Uvicorn and performance settings |
| Present but command-specific | 8 | Setup, insertion, or development helpers |
| Present and apparently unused/behaviorally ineffective | 6 | Listed below |
| Referenced but missing from `.env` | 14 | Defaults, legacy, or load-test-only |
| Variables known across all entry points | 73 | Validator inventory |
| Secret/credential variables | 8 | Values always redacted |
| Variables with code defaults | 44 | Some defaults conflict or are unsafe |
| Overlap groups | 6 | Layered controls or aliases |
| Conflicting definition/behavior findings | 4 | Separate from normal layering |
| Combined overlap/conflict findings | 10 | Six overlap plus four conflict groups |
| Environment variables used only in unit tests | 0 | Tests exercise production names |
| Environment variables used only by benchmarks | 6 | `RAGBOT_*` metadata/auth |

### Count rules

“Active” means a value is consumed on the verified `main:app` import/startup or
request path. Merely calling `os.getenv` is not enough: the resulting value must
affect active behavior. Direct `python main.py` host/port are included. A
variable used only by a separately invoked setup/insertion tool is
command-specific, not active FastAPI runtime.

The six apparently unused/ineffective current names are:

- `ENVIRONMENT`: no repository consumer.
- `QDRANT_URL`: active code uses split Qdrant fields; only a legacy abstraction
  refers to the full URL.
- `LLM_MODEL`: loaded by `new_architecture/app/config.py:17`, never consumed.
- `EMBEDDING_MODEL`: captured by an unused constructor parameter at
  `utils/persian_hybrid_search.py:221`.
- `RERANKER_MODEL`: captured at `utils/RagSystem.py:46`; local reranker loading
  is commented out at `utils/RagSystem.py:133-137`.
- `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD`: still validated by the
  compatibility settings loader, but the former endpoint-level second rerank
  was unreachable and has been removed. The graph uses
  `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD`.

The eight present command-specific names are `DEFAULT_DB_HOST`,
`DEFAULT_DB_PORT`, `DEFAULT_DB_USER`, `DEFAULT_DB_PASSWORD`,
`DEFAULT_DB_NAME`, `MINIO_SECURE`, `KNOWLEDGE_BASE_CSV`, and
`DATA_INSERTION_DIRECTORY`.

## Audit contract and limits

- Audit question: enumerate and explain every repository environment variable,
  its precedence, validation, consumers, overlaps, and risks.
- External request timeout: 50 seconds (`AGENTS.md:7`,
  `utils/performance_config.py:85-87`).
- Staging hardware: one NVIDIA RTX 5880 Ada Generation GPU with 48 GB VRAM.
- Production hardware: two NVIDIA L4 GPUs with 24 GB each.
- Staging TEI ports: embedding 7997, reranking 7998 (`AGENTS.md:12,92`).
- Revision/configuration fingerprint/service versions/model identifiers:
  unknown for this static audit; secret-bearing configuration was not printed.
- Workload, arrival pattern, warm-up, duration, sample count, pass/fail
  performance result: not applicable; no benchmark was run.
- Background workload and measured shared-GPU contention: unknown.

Staging observations must not be extrapolated to production without a
separately controlled benchmark. No performance change was made, so a
before/after benchmark was neither possible nor required.

## Critical findings

### C1 — Secret-bearing environment files are already tracked in Git

**Evidence:** `.gitignore:239-243` contains a `.env` ignore rule, but
`git ls-files` reports `.env`, `.env.server_git`, and `env.example` as tracked.
Git history shows `.env` in commits dated 2026-07-28 and `.env.server_git` in
the repository history.

**Impact:** The ignore rule does not protect a file after it has been added.
Anyone with repository/history access may have obtained credentials.

**Recommendation:** Treat all credentials ever stored in either tracked file as
potentially exposed. Rotate them through each owning system, move live secrets
to an approved secret mechanism, and stop tracking the live files in a separate
authorized change. Do not rewrite history casually; coordinate it. This audit
does not rotate, untrack, or rewrite anything.

### C2 — Credential-like literals exist in tracked Python source

**Evidence:** `new_architecture/setup_dbs.py:49-63,75-82` contains
credential-like values in comments. `test_qdrant.py:10-11` hardcodes an
endpoint and an API-key-like value; `test_qdrant.py:32-33` prints the endpoint
and a partially masked key.

**Impact:** Comments and test helpers are Git history. Masking only at print
time does not protect the source literal, and partial key output is still
unnecessary disclosure.

**Recommendation:** Determine whether the literals were ever valid and rotate
if uncertain. Replace them with synthetic placeholders/environment loading in
a separately reviewed change. Do not run `test_qdrant.py` until its target is
independently confirmed as non-production.

## High-priority findings

### H1 — Active FastAPI ignores `MINIO_SECURE`

`new_architecture/app/config.py:41` hardcodes `MINIO_SECURE=False`; the startup
client then consumes that value at
`new_architecture/app/services/db_connection/connection.py:61-66`. The current
environment assignment cannot enable TLS on this path.

Risk: silent plaintext transport or connection failure when operators expect
TLS. Canonical variable: `MINIO_SECURE`, after code validation is fixed.

### H2 — Insertion tools parse the same boolean inconsistently

`new_architecture/insert_data.py:94` returns the raw string from `os.getenv` and
passes it to MinIO at `new_architecture/insert_data.py:384-389`.
`new_architecture/data_insertion_with_api.py:94` correctly compares the string
to `"true"`. A non-empty string such as `"false"` is truthy in Python.

Risk: command-specific protocol mismatch. Add one strict shared boolean parser
in a future code change.

### H3 — Production Qdrant authentication is not assured

`QDRANT_API_KEY` is currently **empty**. Code accepts that and passes it to
Qdrant (`new_architecture/app/services/db_connection/connection.py:81-87`).
Whether this fails or permits anonymous access depends on the external Qdrant
deployment.

Risk: startup failure or unauthenticated vector-store access. The validator
therefore requires it in `--mode production`, clearly labeled as a security
policy stronger than current code.

### H4 — Database defaults conflict and include unsafe development credentials

The active `main.py:183-184` manager has no PostgreSQL defaults. Other modules
default to `hihelp_db` and unsafe development credentials
(`new_architecture/app/config.py:24-32`), while the inactive SQLAlchemy module
defaults to `rag_db` (`new_architecture/app/core/database.py:53-57`).
Insertion scripts also carry development credential defaults
(`new_architecture/insert_data.py:76-95`).

Risk: different entry points can connect to different databases or silently
use weak credentials. Canonical variables are the five `POSTGRES_*` fields,
with no production credential defaults.

### H5 — `API_PORT` is not converted or validated by the application

`main.py:1480` passes `os.getenv("API_PORT", "8080")` directly to
`uvicorn.run`; the result is a string. The current value is syntactically an
integer, but invalid text is accepted until server startup.

Risk: late startup failure and implementation-version-dependent coercion. The
new validator enforces 1-65535; future application code should parse explicitly.

### H6 — Service URLs lack application-level validation

`VLLM_URL`, `TEI_EMBED_URL`, and `TEI_RERANK_URL` are passed/called as strings.
Only TEI presence is checked (`utils/persian_hybrid_search.py:248-250`);
scheme, credentials, host, and correct embedding/reranker port are not
validated.

Risk: failures occur during startup or first request, and a credential-bearing
URL could leak through error handling. The validator rejects malformed URLs and
embedded credentials.

## Medium-, low-, and informational findings

| Severity | Finding | Evidence and consequence |
|---|---|---|
| Medium | `QDRANT_VECTOR_SIZE` defaults conflict | Active retrieval/TEI is 1024 (`utils/tei_embedding_client.py:14`); inactive pool uses 384 (`new_architecture/app/core/database.py:70`). Activating the wrong module can create an incompatible collection. |
| Medium | `MINIO_BUCKET` defaults conflict | Insertion defaults `hihelp-documents` (`new_architecture/insert_data.py:95`); inactive pool defaults `documents` (`new_architecture/app/core/database.py:64`); active config has no default (`new_architecture/app/config.py:43`). Typos may create a different bucket. |
| Medium | Setup URLs interpolate credentials without URL encoding | `new_architecture/setup_dbs.py:84-93`. Reserved characters in user/password can make a malformed URL; exceptions may expose connection context. |
| Medium | Values are captured at import/default-argument time | `utils/RagSystem.py:44-56`, `utils/persian_hybrid_search.py:217-231`, `new_architecture/app/services/history/database.py:26-29`. Reloading the file alone has no effect. |
| Medium | SQLAlchemy pool variables do not tune the active path | Engine settings exist at `new_architecture/app/core/database.py:74-78,102-120`, while verified runtime uses per-operation psycopg2 connections (`main.py:183-184`, `new_architecture/app/services/history/database.py:26-42`). Operators may tune ineffective controls. |
| Low | Qdrant HTTPS is logged on startup failure | `new_architecture/app/services/db_connection/connection.py:107-110`. The boolean is not secret, but configuration logging should use structured, allowlisted fields. |
| Low | Existing `env.example` is incomplete relative to code | It has 61 names and includes the two TEI batch settings absent from `.env`, but omits 12 other referenced legacy/load-test/pool names. Generated template has all 73. |
| Informational | No deployment manifests were found | No Dockerfile, Compose, Kubernetes, systemd, or repository shell startup definition exists. vLLM/TEI server model, batching, and concurrency settings cannot be audited here. |
| Informational | Redis is outside the verified runtime | `new_architecture/app/core/cache.py:44-45` has hardcoded socket timeouts, but no environment-variable consumer and no verified `main.py` import. |

## Complete inventory by usage class

### Present in `.env` and effective in active FastAPI code (45)

`API_HOST`, `API_PORT`, `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY`,
`QDRANT_COLLECTION`, `QDRANT_VECTOR_SIZE`, `QDRANT_HTTPS`, `POSTGRES_HOST`,
`POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`,
`VLLM_URL`, `TEI_EMBED_URL`, `TEI_RERANK_URL`,
`APPLICATION_REQUEST_TIMEOUT_SECONDS`, `REQUEST_CONCURRENCY_LIMIT`,
`REQUEST_ADMISSION_TIMEOUT_SECONDS`, `BLOCKING_CONCURRENCY_LIMIT`,
all seven `TEI_HTTP_*` settings, all seven `VLLM_HTTP_*` settings,
`QDRANT_CONCURRENCY`, `RAG_RETRIEVAL_TOP_K`,
`RAG_SEMANTIC_CANDIDATE_LIMIT`,
`RAG_RELATED_QUESTIONS_RERANK_THRESHOLD`,
`RAG_MAX_NEW_TOKENS`, `RAG_CHITCHAT_MAX_NEW_TOKENS`, and
`RAG_REWRITE_MAX_TOKENS`.

### Present but command-specific (8)

- Database setup: all five `DEFAULT_DB_*`.
- Data insertion: `MINIO_SECURE`, `DATA_INSERTION_DIRECTORY`.
- Development knowledge preparation: `KNOWLEDGE_BASE_CSV`.

### Present but apparently unused or behaviorally ineffective (6)

`ENVIRONMENT`, `QDRANT_URL`, `EMBEDDING_MODEL`, `LLM_MODEL`,
`RERANKER_MODEL`, `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD`.

### Referenced but missing from `.env` (14)

| Variable | Usage | Missing behavior |
|---|---|---|
| `TEI_EMBED_INSERT_BATCH_SIZE` | Data insertion | Defaults to 32 |
| `TEI_EMBED_MAX_CLIENT_BATCH_SIZE` | Cross-field policy | Defaults to 50 |
| `SQLALCHEMY_POOL_SIZE` | Legacy pool | Defaults to 5 |
| `SQLALCHEMY_MAX_OVERFLOW` | Legacy pool | Defaults to 10 |
| `SQLALCHEMY_POOL_TIMEOUT` | Legacy pool | Defaults to 30 |
| `SQLALCHEMY_POOL_RECYCLE` | Legacy pool | Defaults to 3600 |
| `SQLALCHEMY_ECHO` | Legacy pool | Defaults to false |
| `EMBEDDING_MODEL_NAME` | Legacy local embedding | Becomes `None`; fails if instantiated |
| `RAGBOT_STAGING_AUTH_TOKEN` | Load testing | No bearer token |
| `RAGBOT_STAGING_LIMITER_CAPACITY` | Load-test metadata | Uses source description |
| `RAGBOT_STAGING_GPU_INFO` | Load-test metadata | Uses source description |
| `RAGBOT_VLLM_IMAGE` | Load-test metadata | `unknown` |
| `RAGBOT_TEI_EMBED_IMAGE` | Load-test metadata | `unknown` |
| `RAGBOT_TEI_RERANK_IMAGE` | Load-test metadata | `unknown` |

### Test-only and benchmark-only

No unique environment name is used only by unit tests. Tests patch the same
performance variables used in production
(`tests/test_performance_config.py:14-82`).

The six benchmark-only variables are `RAGBOT_STAGING_AUTH_TOKEN`,
`RAGBOT_STAGING_LIMITER_CAPACITY`, `RAGBOT_STAGING_GPU_INFO`,
`RAGBOT_VLLM_IMAGE`, `RAGBOT_TEI_EMBED_IMAGE`, and
`RAGBOT_TEI_RERANK_IMAGE`
(`benchmarks/load/mobile_talk_load_test.py:1308-1320,1820`).

### Legacy or inactive

`QDRANT_URL`, `EMBEDDING_MODEL_NAME`, and all five `SQLALCHEMY_*` settings are
legacy/inactive on the verified FastAPI path. `EMBEDDING_MODEL`, `LLM_MODEL`,
and `RERANKER_MODEL` are loaded on active imports but do not affect active
model serving.

## Overlap and precedence analysis

| Group | Duplicate? / precedence | Consolidation and risk |
|---|---|---|
| `QDRANT_URL` vs host/port/HTTPS | Conceptual duplicate. Active split fields win; URL is ignored. | Deprecate full URL or explicitly adopt it, not both. Inconsistency misleads operators. |
| `POSTGRES_*` vs `DEFAULT_DB_*` | Not duplicates. Target application DB vs administrative setup DB. Neither overrides the other. | Keep both only for setup; name/document the roles clearly. Wrong pairing can mutate the wrong database. |
| `EMBEDDING_MODEL` vs `EMBEDDING_MODEL_NAME` | Likely alias across two local-model implementations; neither selects active TEI model. | Consolidate if local embedding is revived. Today the canonical active control is external TEI deployment plus `TEI_EMBED_URL`. |
| Total/admission/TEI/vLLM timeouts | Not duplicates; each bounds a layer. Process env overrides `.env`; code defaults are last. | Keep separate, but validate the latency budget. Downstream operations must fit inside 50 seconds. |
| Request/blocking/HTTP/Qdrant/SQL pool limits | Not duplicates; different admission/resource boundaries. | Keep separate and tune one variable per measured experiment. Equal values do not guarantee equal throughput. |
| TEI insertion/max batch | Hierarchical controls; insertion size must be at most the known maximum. | Keep both only if maximum represents verified server policy; otherwise source it from deployment metadata. |

There is no full PostgreSQL `DATABASE_URL`, so split `POSTGRES_*` fields are
canonical. There are no TEI host/port aliases. `VLLM_URL` is canonical for the
application client; `LLM_MODEL` does not override the served model.

Actual Python dotenv precedence is:

1. Existing process environment, including shell exports or container-provided
   variables.
2. `.env` fills keys that are not already present because every
   `load_dotenv()` uses the default `override=False`.
3. Entry-point-specific `os.getenv` defaults.
4. Missing no-default values become `None`.

No Compose/Kubernetes/systemd layer exists in the repository. External server
CLI flags have their own precedence but cannot be reconstructed here.

## Validation audit

### What is already validated

`utils/performance_config.py:9-48,83-193` validates positive integers/floats,
the 50-second maximum, probabilities, keep-alive not exceeding total
connections, insertion batch not exceeding maximum, and top-k not exceeding
candidate limit. Invalid settings fail during import, before FastAPI startup.

`utils/tei_embedding_client.py:44-78,89-102` validates presence, positive
dimension, response count/dimension, numeric values, and finite values.

### Validation gaps

1. Parse `API_PORT`, Qdrant port/vector size, and every database port explicitly
   before constructing clients.
2. Use one strict boolean parser. Current “equals `true`” logic silently treats
   misspellings as false, while one insertion script passes raw strings.
3. Validate service URL scheme/host, prohibit embedded credentials, and verify
   embedding/reranking endpoints are distinct.
4. Require non-empty secrets before startup; do not retain production password
   defaults.
5. Validate MinIO endpoint syntax separately from HTTP URLs.
6. Validate collection/bucket/database identifiers as non-empty and within
   service naming rules.
7. Enforce `QDRANT_VECTOR_SIZE == 1024` for the current embedding policy, or
   derive a single canonical dimension and check collection metadata.
8. Verify configured insertion batch does not exceed the **actual deployed**
   TEI server limit, not only another client variable.
9. Percent-encode PostgreSQL URL credentials in `setup_dbs.py`.
10. Validate that the sum/ordering of admission and downstream timeout budgets
    leaves time inside the endpoint deadline.
11. Avoid import-time default arguments for environment values; load one typed
    settings object at startup.
12. Fail when staging load-test targets or identities appear production-like.

No validation code was changed in this task. The new script is an external,
non-destructive preflight check.

## Configuration consistency checks

| Check | Result | Severity | Evidence |
|---|---|---|---|
| Embedding URL uses staging port 7997 | Consistent by repository guidance/current classification; private address omitted | Informational | `AGENTS.md:12,92`; `.env:65` |
| Reranker URL uses staging port 7998 | Consistent by repository guidance/current classification | Informational | `AGENTS.md:12,92`; `.env:66` |
| Query uses `prompt_name="query"` | Consistent | Informational | `utils/tei_embedding_client.py:14-25` |
| Stored documents use raw semantics | Consistent | Informational | `utils/tei_embedding_client.py:29-41,81-87` |
| Vector dimension is 1024 | Active path consistent; legacy 384 conflict | Medium | `utils/tei_embedding_client.py:14`; `new_architecture/app/core/database.py:70` |
| Qdrant distance is cosine | Consistent | Informational | `new_architecture/app/services/db_connection/connection.py:96-102`; insertion `new_architecture/insert_data.py:410-415` |
| Endpoint deadline is at most 50 seconds | Consistent; current status set and validator accepted | Informational | `utils/performance_config.py:85-87` |
| Limiter and client pools are cross-valid | Current values pass repository relationships | Informational | `utils/performance_config.py:164-192`; validator result |
| TEI insertion batch within configured client maximum | Both absent, defaults 32 <= 50 | Informational | `utils/performance_config.py:118-123,172-179` |
| Actual TEI server batch/admission limits | Unknown; no startup manifest | Medium | No Docker/Compose/systemd/Kubernetes definition found |
| vLLM model path, max sequences/tokens/model length | Unknown; `LLM_MODEL` ineffective | Medium | `utils/RagSystem.py:44-52`; no startup definition |
| Staging load tests cannot point to production | Not enforceable from environment metadata | High | Load generator accepts operator URL/fixtures; `ENVIRONMENT` is unused |
| Published/internal Docker ports match URLs | Unknown | Informational | No repository Docker definitions found |
| MinIO TLS follows environment | Inconsistent | High | `new_architecture/app/config.py:41` |

## What belongs in an example and what must remain secret

Safe to show as synthetic/default examples: ports, timeouts, concurrency, batch
sizes, thresholds, token limits, booleans, `localhost`, documented staging TEI
ports, collection/bucket examples, and placeholder paths/model identifiers.

Must remain secret: `QDRANT_API_KEY`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `DEFAULT_DB_USER`, `DEFAULT_DB_PASSWORD`,
`MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, and
`RAGBOT_STAGING_AUTH_TOKEN`. In production these should not be stored in a
Git-tracked `.env`; use the approved deployment secret mechanism.

Internal but not authentication secrets: private hosts/URLs, database and
bucket names, model paths, container images, and GPU placement. Avoid publishing
them unnecessarily.

## Existing example comparison

`env.example` has 61 assignment names. Relative to `.env`, it adds
`TEI_EMBED_INSERT_BATCH_SIZE` and `TEI_EMBED_MAX_CLIENT_BATCH_SIZE`; it does not
omit any of the current `.env` names.

`.env.example.generated` has all 73 known names, including the five inactive
SQLAlchemy settings, legacy alias/full URL, and six staging load-test variables.
It was authored from source defaults and safe examples, not copied from the
current `.env`.

## Recommendations ranked by priority

1. **Immediate/security:** Rotate every potentially exposed credential; confirm
   whether source literals were valid; stop tracking live env files in a
   separately authorized Git change.
2. **Immediate/security:** Make `MINIO_SECURE` effective and strictly parsed
   before any TLS-dependent deployment.
3. **High/correctness:** Introduce one typed settings layer with strict
   required-secret, URL, port, boolean, identifier, and cross-field validation.
4. **High/safety:** Add a staging-target allowlist/production denylist to load
   tooling; do not rely on unused `ENVIRONMENT`.
5. **High/clarity:** Remove or formally deprecate behaviorally ineffective model
   names and `QDRANT_URL`; document external vLLM/TEI server configuration.
6. **Medium/correctness:** Consolidate vector dimension, database name, bucket,
   and credentials defaults; remove unsafe credential defaults.
7. **Medium/performance:** Expose hardcoded PostgreSQL/Qdrant timeout controls
   only if operational evidence requires them; benchmark one major variable at
   a time.
8. **Medium/operations:** Add CI that runs the synthetic validator tests and
   compares environment names without reading the real `.env`.

## Validation artifacts and commands

Created:

- `scripts/validate_environment.py`
- `tests/test_validate_environment.py`
- `.env.example.generated`

Run the synthetic tests:

```bash
python3 -m unittest tests.test_validate_environment -v
```

Validate the current file without values:

```bash
python3 scripts/validate_environment.py \
  --env-file .env \
  --mode staging \
  --show-optional \
  --format text
```

Machine-readable output is also redacted:

```bash
python3 scripts/validate_environment.py \
  --env-file .env \
  --mode staging \
  --format json
```
