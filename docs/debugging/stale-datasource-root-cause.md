# Stale Datasource Root Cause

## Outcome

The stale UI was not one bug. Four independent lifecycle defects combined:

1. The schema-reset script dropped PostgreSQL ORM tables but did not clear the
   configured Qdrant collection, configured MinIO bucket, generated files, or
   running-process caches.
2. The insertion script treated every `DOCUMENTS` directory entry as a source.
   For `.gitkeep`, `filename.split(".")[0]` became an empty title, creating a
   blank PostgreSQL document and uploading `.gitkeep` to MinIO.
3. The chunk generator hardcoded `General_FAQ` for both the manifest and chunk
   directory. Running it recreated `General_FAQ` even when the operator believed
   a differently named source was being inserted.
4. `/api/documents` served the module-global startup snapshot
   `available_documents`. A database reset underneath a running process did not
   invalidate that list or the BM25 cache. Mobile and graph defaults also
   injected `General_FAQ` when no datasource was supplied.

The backend has been corrected rather than merely hiding rows in JavaScript.

## Read-only current-state evidence (2026-08-08)

No knowledge content, secrets, authentication values, or banking data was read
or printed.

### PostgreSQL

| Item | Result |
| --- | --- |
| Collections | 2: ID 1 `Test Collection` (0 docs), ID 2 `Hi_Help` (2 docs) |
| Documents | 2 |
| Document ID 1 | blank title, filename `.gitkeep`, 0 chunks |
| Document ID 2 | `General_FAQ`, filename `General_FAQ.csv`, 1,426 chunks |
| Chunks | 1,426 |
| Embeddings | 1,426 |
| Chunk/embedding orphans | 0 / 0 |
| Chat sessions | 6; five nested `agent_state.allowed_docs` values select `General_FAQ` |
| Mass-answer jobs | 2; both store `selected_documents = ["General_FAQ"]` |
| Views/materialized views | 0 / 0 |
| Sequences | 10 application table sequences |

All knowledge foreign keys use the expected cascade relationships except
`documents.collection_id`, which uses `SET NULL`. Dropping/recreating tables
resets sequences; knowledge metadata deletion preserves operational sequences.

### Qdrant

- One collection exists: the configured application collection.
- It has no aliases.
- It contains 1,426 points.
- Every point identifies document ID 2 and name `General_FAQ`.
- No point is missing datasource ID/name metadata.

The insertion script uses PostgreSQL chunk IDs as deterministic Qdrant point
IDs and upserts them. It had no cleanup step, so resetting PostgreSQL could
leave all old points behind. A later schema reset can also reuse integer chunk
IDs, allowing new upserts to overwrite some old points while leaving an old
tail when the replacement is shorter.

### MinIO

- The configured bucket contains 6 objects under `user_2`.
- Five filenames end in `General_FAQ.csv`; only one is referenced by the current
  PostgreSQL `documents` row.
- One object is the uploaded `.gitkeep` referenced by the blank document row.
- Therefore four `General_FAQ` objects are already orphaned from PostgreSQL.
- Object metadata has only normal HTTP/S3 headers; datasource identity comes
  from the object name/path, not custom metadata.

The old insertion path used a UUID per upload and never removed prior objects,
so every reinsertion accumulated another object.

### Filesystem and process/browser state

- `DOCUMENTS` contains `.gitkeep` and `General_FAQ.csv`.
- `CHUNKS/General_FAQ` contains 1,426 numbered chunks.
- No generated metadata JSON or manifest beyond the CSV was found.
- `new_architecture.app.core.cache` supports Redis but is not imported by the
  verified application startup path.
- `PersianHybridSearch` has a worker-local `_bm25_cache` keyed by selected
  document names.
- Five of six chat sessions persist `agent_state.allowed_docs = ["General_FAQ"]`;
  these are valid against the current row but would become stale on deletion.
- Datasource selections in the active chat UI are in JavaScript memory, not
  `localStorage` or `sessionStorage`. Browser storage is used for unrelated
  theme/language/authentication preferences.

The FastAPI service was not listening on the documented local port during the
audit, so a live endpoint/restart A/B test was unavailable. Static tracing is
conclusive: startup populated `available_documents`; only startup or
`POST /api/initialize` refreshed it before this fix.

## Exact mismatch in the old reset

`setup_dbs.py` imported SQLAlchemy models, dropped `chunk_versions`, called
`Base.metadata.drop_all()`, and recreated those tables. It did not know about
Qdrant points, MinIO objects, local source/chunk files, mass-answer selection
JSON, `agent_state.allowed_docs`, or worker caches. `mass_answer_jobs` was not an
ORM model and therefore also survived the old schema-drop operation.

The prompt said “DROP and RECREATE all tables,” but its actual scope was only
ORM-known PostgreSQL tables plus `chunk_versions`. That wording reasonably
suggested a clean knowledge system while derived stores remained populated.

## Fix mapping

| Defect | Fix |
| --- | --- |
| `.gitkeep` creates blank document | Pure discovery rule ignores hidden, placeholder, empty, and chunkless sources |
| Hardcoded `General_FAQ` | Generator derives name from input stem or explicit `--source-name` |
| Old tail chunks | Generator removes old numbered chunks before replacement |
| PostgreSQL-only reset | Canonical `new_architecture.knowledge_reset` service coordinates PostgreSQL, Qdrant, MinIO, selections, validation, and optional local cleanup |
| Unclear reset prompt | Explicit schema reset, cross-store reset, exact confirmation, dry run, and production guard |
| Stale API snapshot | `/api/documents` queries PostgreSQL live and returns an empty list when clean |
| Invalid backend selections | Answering service validates every requested title against current documents/chunks |
| Default `General_FAQ` | Removed from mobile request and graph retrieval defaults |
| Stale BM25 corpus | Datasource refresh/initialize clears the worker-local cache; worker restart remains the safe fleet-wide operation |
| Orphan MinIO accumulation | Reset clears only configured bucket/prefix scope; insert compensation removes a failed new upload |

## Acceptance interpretation

After `FULL_DEV_RESET`, validator output must show zero PostgreSQL documents and
chunks, zero Qdrant points, zero in-scope MinIO objects, zero generated source
documents/chunks, and zero stale selections. `GET /api/documents` returns
`{"documents": [], "count": 0, "categories": []}`.

After one valid source is generated and inserted, PostgreSQL remains the source
of truth and exactly that source appears. A second full reset returns to the
same zero state. Directories containing only `.gitkeep` are never ingestible.
