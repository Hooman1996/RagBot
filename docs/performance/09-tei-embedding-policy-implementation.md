# TEI embedding policy implementation

Date: 2026-07-29

## Outcome

The measured recommendation from
`08-tei-query-task-equivalence.md` is implemented without rebuilding or
mutating the existing Qdrant collection:

- Online search queries use TEI `/embed` with `prompt_name="query"` and
  `normalize=true`.
- Stored FAQ/document vectors use normalized raw document text with no
  `prompt_name` and no manual prefix.
- Query and document calls share one validated asynchronous TEI client.
- Both active bulk insertion programs batch TEI requests and retain one
  `httpx.AsyncClient` for the complete embedding stage.
- Synchronous knowledge-base create/update/revert operations use the same
  raw-document payload builder and response validator with the application's
  existing persistent synchronous HTTP client.

Existing Qdrant data remains compatible. No collection rebuild is required.

## Evidence carried forward

The preceding audit measured the production-relevant policy against the
existing raw-document collection:

| Metric | Raw query | `prompt_name="query"` |
|---|---:|---:|
| Top-1 accuracy | 0.50 | 0.80 |
| Top-3 accuracy | 0.90 | 1.00 |
| Recall@3 | 0.65 | 0.80 |
| Recall@10 | 0.85 | 0.95 |
| MRR@10 | 0.6833 | 0.8833 |

Raw TEI had mean cosine similarity `0.999646` to the previous local
`task="retrieval.query"` behavior, mean overlap@10 `0.99`, and identical
measured retrieval metrics. Ten sampled Qdrant vectors matched normalized raw
documents at mean cosine `0.999949`. These measurements support changing only
the query role while retaining raw stored-document semantics.

## Runtime contract inspected

The installed embedding service observed by the audit was:

- image `ghcr.io/huggingface/text-embeddings-inference:cuda-1.9`
- digest
  `sha256:249a0bc87522bfe2f1012b4d194f0225878f47079115ada3aeb0b1ef257b402a`
- TEI `1.9.3`, revision
  `06670157fb6c1523482219bdb2d1660277d38088`
- model
  `/app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval`
- last-token pooling, float16, 16,384-token maximum input and batch-token
  limits
- maximum client batch size 50 and maximum concurrent requests 100

Startup command:

```text
./entrypoint.sh \
  --model-id /app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval \
  --max-client-batch-size 50 \
  --max-concurrent-requests 100
```

TEI 1.9.3 accepts an `/embed` request object with `inputs` as either one string
or a list of strings and accepts the observed `prompt_name` and `normalize`
properties. Both a single string and a batch return `list[list[float]]`; a
single string does not return a bare `list[float]`. Live audit probes proved
that `normalize=true` is accepted. The installed service had no OpenAPI
document, so the live probes and image/model inspection are the
version-specific schema evidence.

The configured `TEI_EMBED_URL` is `http://localhost:7997`, without a trailing
slash. The shared client rejects a missing URL and removes trailing slashes
before appending `/embed`.

## Files inspected

The repository-wide inspection included:

- prior audit, benchmark, measured report, analysis JSON, and retrieval fixture
- `utils/persian_hybrid_search.py`, `utils/RagSystem.py`,
  `utils/performance_config.py`, `utils/service_errors.py`, `main.py`,
  `intent_classifier.py`, and `kb_manager.py`
- `new_architecture/data_insertion_with_api.py`,
  `new_architecture/insert_data.py`, and `new_architecture/setup_dbs.py`
- Qdrant initialization in
  `new_architecture/app/services/db_connection/connection.py`,
  `new_architecture/app/core/database.py`, and the two insertion programs
- the dormant local embedding service at
  `new_architecture/app/services/embedding/embedding.py`
- every repository Python occurrence of `SentenceTransformer`, `.encode(`,
  `/embed`, TEI embedding helpers, and Qdrant point writes
- `env.example`, local environment metadata, and all available tests

`setup_dbs.py` only creates PostgreSQL structures and sample relational data.
It does not initialize Qdrant and does not embed data, so it was not changed.
The two insertion programs retain `VectorParams(size=1024,
distance=Distance.COSINE)` when creating a missing collection; they do not
delete or recreate an existing collection.

The local `SentenceTransformer` service under
`new_architecture/app/services/embedding/embedding.py` is dormant in the
verified application and insertion paths. It was not changed because removing
unused architecture code is outside this policy migration.

## Files changed

- `utils/tei_embedding_client.py`
- `utils/tei_embedding_batches.py`
- `utils/persian_hybrid_search.py`
- `utils/performance_config.py`
- `kb_manager.py`
- `new_architecture/data_insertion_with_api.py`
- `new_architecture/insert_data.py`
- `env.example`
- `benchmarks/embedding/verify_tei_embedding_policy.py`
- `tests/test_tei_embedding_policy.py`
- `tests/test_p0_p1_repairs.py`
- `tests/test_performance_config.py`
- this document

## Previous and new behavior

Previously, online queries posted raw text:

```json
{"inputs": "query text", "normalize": true}
```

The active bulk insertion scripts loaded `SentenceTransformer` on CUDA and
called local `encode(..., task="retrieval.passage",
normalize_embeddings=True)`. For this exact model the task argument was unused,
so the effective stored-vector policy was normalized raw text.

Online queries now send:

```json
{
  "inputs": "query text",
  "prompt_name": "query",
  "normalize": true
}
```

The input remains the caller's query. It is not manually prefixed with
`Query: `, so the prompt cannot be applied twice.

Document batches now send:

```json
{
  "inputs": ["raw document 1", "raw document 2"],
  "normalize": true
}
```

There is deliberately no `prompt_name`, `Document: ` prefix, or second local
normalization of the returned vector. The insertion programs preserve the
existing Parsivar text normalization before embedding, Qdrant point IDs,
ordering, collection, payload fields, upload behavior, duplicate check, and
PostgreSQL transaction sequence.

## Shared client, batching, and lifecycle

`TeiEmbeddingClient` exposes:

- `embed_query(query: str) -> list[float]`
- `embed_documents(documents: Sequence[str]) -> list[list[float]]`

It calls `raise_for_status()`, validates JSON response shape and count, rejects
boolean/non-numeric/NaN/infinite values, enforces 1024 dimensions, preserves
batch order, returns Python lists for Qdrant, and performs no NumPy conversion
or second normalization.

`TEI_EMBED_INSERT_BATCH_SIZE` controls insertion batches and defaults to 32.
`TEI_EMBED_MAX_CLIENT_BATCH_SIZE` records the known server maximum and defaults
to 50. Configuration loading rejects non-positive timeouts or batch values and
rejects an insertion batch larger than the known server maximum.

Each insertion batch is one TEI request containing a list of raw texts. A
batch is fully validated before its vectors can be included in a Qdrant write;
the current scripts validate all batches for a document before uploading that
document's points. A `TeiInsertionSession` owns one event loop and one
`httpx.AsyncClient` for the complete embedding stage and closes both on normal
completion or exception. The online application continues to inject its
lifespan-owned reusable async and sync clients and closes them during FastAPI
shutdown.

No retry was added because the existing embedding paths had no retry policy.
In particular, non-transient 4xx responses are not retried. HTTP status errors
propagate. Bulk failures add batch number, batch size, and source chunk IDs
without including document text.

## Tests and checks

Passed:

```text
/root/miniconda3/envs/faq/bin/python -m unittest \
  tests.test_tei_embedding_policy \
  tests.test_performance_config \
  tests.test_p0_p1_repairs

Ran 31 tests: OK
```

The modified Python files and the repository's Python source compiled:

```text
/root/miniconda3/envs/faq/bin/python -m compileall -q \
  utils new_architecture benchmarks/embedding tests
```

Full unittest discovery ran 74 tests. Seventy-three passed, while the existing
`tests/benchmarks/test_tei_query_task_equivalence.py` could not import because
`pytest` is not installed in the available Python environment:

```text
ModuleNotFoundError: No module named 'pytest'
```

Exact command for the intended environment:

```bash
python -m pytest -q
```

No repository-owned Python dependency file, lint command, or type-check command
exists. `pytest`, `ruff`, and `mypy` are absent from the inspected environment,
and no packages were installed.

The non-writing live smoke command was attempted against
`http://127.0.0.1:7997`, but TEI was not listening in this execution
environment (`httpx.ConnectError: All connection attempts failed`). It made no
Qdrant calls. Run it where the staging TEI endpoint is reachable:

```bash
/root/miniconda3/envs/faq/bin/python \
  benchmarks/embedding/verify_tei_embedding_policy.py \
  --tei-url http://127.0.0.1:7997
```

The script stages inference sequentially—query first, then one document
batch—and verifies payload roles, dimensions, and approximately unit norms. It
does not read or write Qdrant.

## Limitations and compatibility

- The live smoke check could not complete because TEI was unavailable during
  this implementation run.
- The repository has no identified answer-quality test command. The measured
  retrieval evaluation from the prior audit is the before/after quality
  evidence; answer-quality was not rerun.
- The dormant generic local embedding service remains present but is not used
  by the verified online query, KB mutation, or insertion paths.
- No full insertion was run, and no Qdrant collection or point was changed.

Existing vectors remain 1024-dimensional normalized raw-document vectors under
cosine distance. A document-side prompt would change their semantic policy and
would require a full collection rebuild plus retrieval evaluation. This
implementation does not introduce one, so the existing collection does not
require rebuilding.

## Operator commands

Focused tests:

```bash
/root/miniconda3/envs/faq/bin/python -m unittest \
  tests.test_tei_embedding_policy \
  tests.test_performance_config \
  tests.test_p0_p1_repairs
```

Non-writing TEI verification:

```bash
/root/miniconda3/envs/faq/bin/python \
  benchmarks/embedding/verify_tei_embedding_policy.py \
  --tei-url http://127.0.0.1:7997
```

Manual insertion, after configuration and operator confirmation:

```bash
/root/miniconda3/envs/faq/bin/python \
  new_architecture/data_insertion_with_api.py
```
