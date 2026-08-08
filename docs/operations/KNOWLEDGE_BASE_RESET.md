# Knowledge-Base Reset

## Reset modes

### DATABASE_SCHEMA_RESET

Run `python new_architecture/setup_dbs.py` and confirm the PostgreSQL prompt.
This drops and recreates the explicit repository-owned application tables,
including `chunk_versions` and `mass_answer_jobs`. Foreign-key dependencies and
sequences are recreated. It does not silently touch Qdrant, MinIO, or generated
files.

### KNOWLEDGE_BASE_RESET

```bash
python -m new_architecture.knowledge_reset \
  --reset-knowledge \
  --confirm 'RESET KNOWLEDGE'
```

This operation is idempotent and scoped to:

- PostgreSQL documents, chunks, embeddings, chunk versions, collection counters,
  and stale datasource selections;
- all points in the configured `QDRANT_COLLECTION` only;
- objects under `MINIO_KNOWLEDGE_PREFIX` in the configured `MINIO_BUCKET`, or
  the entire configured bucket when the prefix is empty.

It preserves PostgreSQL users, chat sessions, queries, feedback, tickets,
collections, and unrelated operational data. Historical query retrieval data
is not treated as an active selection.

The configured MinIO bucket must be application-dedicated when
`MINIO_KNOWLEDGE_PREFIX` is empty. Set a dedicated prefix for shared buckets.
The bucket itself and unrelated Qdrant collections are never deleted.

### FULL_DEV_RESET

```bash
python -m new_architecture.knowledge_reset \
  --full-dev-reset \
  --confirm 'RESET KNOWLEDGE'
```

This performs `KNOWLEDGE_BASE_RESET` and removes nonplaceholder generated source
documents and numbered chunks under `DATA_INSERTION_DIRECTORY`. `.gitkeep` and
other hidden placeholders are preserved. It is refused in production.

## Dry run and validation

Dry runs require no confirmation and make no changes:

```bash
python -m new_architecture.knowledge_reset --full-dev-reset --dry-run
```

Validate every store:

```bash
python -m new_architecture.knowledge_reset --validate
```

The validator reports PostgreSQL datasource/document/chunk counts and orphans,
Qdrant point counts and distinct datasource metadata, MinIO object counts and
prefixes, filesystem counts, and stale selection counts. It exits `0` only when
all reported knowledge state, including generated files, is empty; otherwise it
exits `1`.

## Recommended clean developer workflow

1. Run `python new_architecture/setup_dbs.py`.
2. Confirm the PostgreSQL schema reset.
3. Confirm the cross-store knowledge reset and type `RESET KNOWLEDGE`.
4. Confirm local generated-file cleanup for a full development reset.
5. Run `python -m new_architecture.knowledge_reset --validate`; expect exit 0.
6. Place the current source CSV at its configured input path.
7. Run `python hihelp_knowledge_changer.py`. Use `--source-name NAME` only when
   the desired datasource name differs from the source filename stem.
8. Run `python new_architecture/data_insertion_with_api.py` and type `yes`.
9. Run `python -m new_architecture.knowledge_reset --validate`. It should now
   exit 1 because one datasource exists; inspect the report and verify exactly
   one PostgreSQL datasource and only its Qdrant/MinIO metadata.
10. Restart all FastAPI workers, or call `/api/initialize` on each worker. A web
    `/api/documents` refresh also clears that worker's BM25 cache.
11. Call `GET /api/documents` and verify `count == 1`.

No manual stale-record hunting is required.

## Current staging repair (prepared, not executed)

The 2026-08-08 read-only audit found 2 PostgreSQL document rows (one blank and
one `General_FAQ`), 1,426 chunks/embeddings, 1,426 matching Qdrant points, 6
MinIO objects, and 1,426 generated chunk files.
The reset dry run also identifies 7 persisted selections to clear: five chat
agent states and two mass-answer jobs.

Review the exact scope:

```bash
python -m new_architecture.knowledge_reset --full-dev-reset --dry-run
```

Then, during an approved staging maintenance window:

```bash
python -m new_architecture.knowledge_reset \
  --full-dev-reset \
  --confirm 'RESET KNOWLEDGE'
python -m new_architecture.knowledge_reset --validate
```

That one service command performs the PostgreSQL metadata/selection cleanup,
configured Qdrant collection cleanup, configured MinIO bucket/prefix cleanup,
and generated-file cleanup. Do not substitute broad bucket or collection
deletion commands.

After generating and inserting the desired source, validate metadata and
restart the FastAPI workers before serving mobile or multi-worker traffic.

## Failure semantics

External stores are cleared before PostgreSQL. If Qdrant or MinIO fails, the
service stops and does not erase the relational inventory. Because there is no
distributed transaction across PostgreSQL, Qdrant, and MinIO, a later external
phase can still leave a partial reset; the command reports the failed phase,
returns exit 2, and never prints success. Retry is safe and idempotent.

## Production safety

- `FULL_DEV_RESET` is always refused in production.
- Knowledge reset requires `--allow-production-reset` and the stronger exact
  phrase `RESET PRODUCTION KNOWLEDGE` when `ENVIRONMENT=production`.
- `setup_dbs.py` refuses a production schema reset without the same explicit
  flag, requires `RESET PRODUCTION SCHEMA`, and still prompts separately for
  cross-store deletion.
- Real `.env` files and secrets are never printed or changed.
- Production infrastructure must not be reset from this staging repository.
