# Knowledge Source Lifecycle

## Canonical identity

PostgreSQL `documents` is the canonical datasource identity table. A source is
selectable only when its title is nonblank and at least one row in `chunks`
references it. `DatabaseManager.get_available_documents()` enforces this rule.

`collections` groups documents; a collection is not itself a selectable
datasource. Qdrant and MinIO are derived stores and must not be used to build the
UI datasource list.

## Lifecycle

```text
source CSV (KNOWLEDGE_BASE_CSV)
  |
  v
hihelp_knowledge_changer.py
  |-- DOCUMENTS/<source-name>.csv
  `-- CHUNKS/<source-name>/<source-name>_<index>.txt
          |
          v
new_architecture/data_insertion_with_api.py
  |-- PostgreSQL documents (canonical ID/name + MinIO path)
  |     `-- chunks -> embeddings metadata
  |-- Qdrant configured collection
  |     `-- point payload: chunk_id, chunk_index, document_id, document
  `-- MinIO configured bucket/prefix
        `-- source object
          |
          v
GET /api/documents
  |-- live PostgreSQL query
  |-- nonblank title
  `-- EXISTS(chunk)
          |
          v
CategoryFilter/Chat in-memory datasource list and selectedDocs
          |
          v
AnsweringService server-side selection validation
          |
          v
AgentState.allowed_docs -> filtered PostgreSQL/BM25/Qdrant retrieval
```

The knowledge-base manager uses
`GET /knowledge-base/api/documents`, also backed by PostgreSQL. It defensively
excludes blank titles but can show valid management records independently of the
chat selection endpoint.

## Store responsibilities

| Store | Responsibility | Datasource-list authority |
| --- | --- | --- |
| Filesystem | Source staging and generated chunks | No |
| PostgreSQL `documents`/`chunks` | Canonical identity, relationships, usable-source status | Yes |
| PostgreSQL session/job JSON | Persisted selections and historical operational state | No |
| Qdrant | Derived vector points and document filter payload | No |
| MinIO | Derived source objects | No |
| Process memory | BM25 corpus cache and UI snapshot | No |
| Browser memory | Current-page selected tags | No |

The active FastAPI path does not import `new_architecture.app.core.cache`; its
optional Redis/in-memory cache is therefore not a datasource store. Browser
`localStorage` persists theme, language, login preferences, and authentication,
not datasource selection. `Chat.selectedDocs` and legacy sidebar selections are
page-memory only.

## Ingestion semantics

`new_architecture.knowledge_sources.discover_knowledge_sources()` is the single
filesystem admission rule. It ignores:

- hidden files, including `.gitkeep`;
- known placeholder files;
- empty files;
- document files with an empty stem;
- directories without a matching nonempty source document;
- sources without at least one nonempty numbered `.txt` chunk.

The chunk generator derives the datasource name from the input CSV stem unless
`--source-name` or `KNOWLEDGE_SOURCE_NAME` is set. Before writing a replacement,
it removes old numbered chunks for that same datasource so a shorter dataset
cannot inherit stale tail chunks.

The insertion script verifies that every discovered datasource obtains a
document row and chunks. It reports a nonzero exit status on partial failure and
compensates a PostgreSQL document-insert failure by removing the just-uploaded
MinIO object. If PostgreSQL embedding metadata fails after a Qdrant upload, the
new Qdrant point IDs are removed.

## Selection and cache consistency

All client-supplied datasource names are revalidated against current
PostgreSQL documents and chunks before retrieval. Blank, duplicate, and removed
names are discarded. A general knowledge request with no current datasource is
rejected; the agent no longer invents `General_FAQ` as a fallback.

Agent state may contain `chat_sessions.meta_data.agent_state.allowed_docs`.
Mass-answer jobs contain `selected_documents`. A knowledge reset removes names
that no longer exist while preserving unrelated session/job data.

The web datasource endpoint queries PostgreSQL on every call, sends
`Cache-Control: no-store`, and clears the worker-local BM25 corpus cache. An
already-running mobile-only or multi-worker deployment should still restart all
FastAPI workers after an external reset or ingestion so every worker discards
its local BM25 cache.

