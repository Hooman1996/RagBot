# Knowledge Update Architecture

## Decision

`chunks.content` in PostgreSQL is the canonical runtime knowledge text. The
`embeddings.vector` row and Qdrant point are synchronously maintained derived
representations. MinIO source objects and files below
`DATA_INSERTION_DIRECTORY` are ingestion inputs; neither participates in a live
answer edit or in the runtime answer read path.

An HTTP success from `PUT /knowledge-base/api/chunks/update` now means:

1. the submitted question/answer was normalized and embedded;
2. the target PostgreSQL chunk and embedding rows were locked and staged;
3. Qdrant acknowledged the targeted upsert with `wait=True`;
4. a Qdrant retrieve saw the new payload, revision, and vector;
5. PostgreSQL committed;
6. a new PostgreSQL connection saw the new content and vector; and
7. the current worker's BM25 cache was invalidated.

If any required stage fails, the endpoint returns failure. Before the
PostgreSQL commit, the transaction is rolled back and Qdrant is restored to the
captured prior point. A failed compensation or any failure after commit is
logged with `repair_required=true` and never represented as success.

## Stores and reconstruction

| Store | Runtime role | Authoritative | Reconstructable | Update rule |
|---|---|---:|---:|---|
| PostgreSQL `chunks.content` | Text supplied to BM25, retrieval result, and LLM context | Yes | Only from an external source or version history | Commit synchronously |
| PostgreSQL `embeddings.vector` | Durable copy of the generated vector | Derived | Yes, from normalized `chunks.content` and the configured embedder | Update in the same PostgreSQL transaction |
| PostgreSQL `chunk_versions` | Audit/version history | History | No | Append in the same transaction |
| PostgreSQL `knowledge_document_revisions` | Monotonic per-document cache revision | Coordination | Recreated at zero, then incremented by every supported mutation | Increment in the same transaction |
| Qdrant point vector | Semantic candidate selection | Derived | Yes, from normalized `chunks.content` | Targeted upsert, `wait=True`, then retrieve/verify |
| Qdrant payload | IDs, document filter, text diagnostics, revision | Derived | Yes, from PostgreSQL | Update with the point |
| BM25 corpus | Lexical candidate selection and returned `SearchResult.content` | No | Yes, from PostgreSQL | Local clear plus PostgreSQL revision check on every corpus access |
| MinIO document object | Original ingestion artifact | Source artifact, not runtime answer authority | Not from edited chunks | No live edit |
| `data_insertion_chunks/**` | Offline ingestion input | Source artifact, not runtime answer authority | Environment provisioned | No live edit |

## Vector policy

The ingestion and edit paths embed the full normalized chunk. For an FAQ that
is `question: ...\nanswer: ...`; therefore an answer-only change changes the
embedding input and the vector must be regenerated. An idempotent update with
identical complete embedding text reuses the stored vector. Qdrant point IDs equal the
integer PostgreSQL chunk IDs. Payload fields are `chunk_id`, `chunk_index`,
`document_id`, `document`, `content`, `text`, and `knowledge_revision` (while
preserving any pre-existing payload fields).

## Retrieval and context path

`DatabaseManager.get_chunks_by_document_titles()` fetches current chunk text.
`PersianHybridSearch` builds BM25 over that text and asks Qdrant for semantic
candidate chunk IDs. Fusion selects IDs, but the returned `SearchResult.content`
comes from PostgreSQL. `RAGSystem.generate_context()` extracts question and
answer from that content, and `agent_graph.handle_general` supplies the result
to the LLM.

The process-local BM25 entry is keyed by the sorted selected document titles.
Before reuse, each worker obtains the transactionally incremented per-document
revision from PostgreSQL. A revision mismatch rebuilds
the entry. This makes worker A's update visible to workers B-D without requiring
process-local messages or a single-worker deployment.

## Concurrency and transaction model

Updates to the same chunk use `SELECT ... FOR UPDATE OF c, e`. Lock acquisition
serializes them; the last lock holder to commit wins. Embedding occurs before
the lock. The Qdrant write/confirmation occurs while the row lock is held so a
second writer cannot interleave its point with the first transaction. This is a
short-lived saga, not distributed ACID:

- before commit: rollback PostgreSQL and compensate Qdrant;
- ambiguous commit response: use a fresh PostgreSQL connection to prove the
  outcome; compensate only when the old row is confirmed;
- after commit: return failure with a correlation ID and repair-required flag;
- repair: compare the canonical PostgreSQL content/vector with Qdrant and
  targeted-upsert the canonical representation.

No background task, `asyncio.create_task`, delayed sleep, or unawaited write is
part of this workflow.

## Deployment requirements

All app workers must use the same `POSTGRES_*` destination and
`QDRANT_COLLECTION`. `QDRANT_HOST`/`QDRANT_PORT` must resolve from the FastAPI
process namespace. `localhost` is valid only when the service is reachable in
that same namespace. MinIO remains a startup/ingestion dependency in the
current application lifespan, but not an edit or answer dependency.

The runtime source files are intentionally ignored by Git. They must be
provisioned for ingestion/reset operations, but their absence does not make an
already-ingested answer stale. Do not commit private source documents or
generated banking chunks to solve deployment provisioning.
