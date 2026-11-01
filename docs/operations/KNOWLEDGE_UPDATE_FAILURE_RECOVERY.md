# Knowledge Update Failure Recovery

## Consistency model

PostgreSQL `chunks.content` is authoritative. PostgreSQL embedding data,
Qdrant, and BM25 are dependent representations. The endpoint uses a
compensating transaction because PostgreSQL and Qdrant cannot share an ACID
transaction.

Before PostgreSQL commit, any failure rolls back SQL and attempts to restore
the captured Qdrant point. After commit, no automatic rollback of authoritative
knowledge is attempted; the request fails with `repair_required=true` and an
operator repairs Qdrant from PostgreSQL. This avoids silently reverting an
already-visible authoritative edit.

## Reason codes

| Internal reason | Meaning | Expected state | Action |
|---|---|---|---|
| `EMBEDDING_FAILED` | TEI rejected/timed out | All stores old | Fix TEI and retry same edit |
| `POSTGRES_UPDATE_FAILED` | Lock, row update, version insert, or commit failed | SQL rolled back and Qdrant compensated only when non-commit is proven; ambiguous commit is repair-required | Inspect correlated logs; verify both stores before retry |
| `QDRANT_UPDATE_FAILED` | Upsert call failed | SQL rolled back; old point restored/deleted | Fix Qdrant and retry |
| `QDRANT_CONFIRMATION_FAILED` | Read-back did not match | SQL rolled back; old point restored/deleted | Inspect collection/replica/endpoint and retry |
| `KNOWLEDGE_VERIFY_FAILED` | Fresh SQL read did not match after commit | Repair required | Treat PostgreSQL as canonical, then targeted-repair Qdrant |
| `CACHE_INVALIDATION_FAILED` | Local clear raised after commit | Persistent stores new; repair flag set | Verify revision query and recycle only the affected worker under an approved procedure |

The normal UI receives only a safe message, tracking ID, and repair flag. It
does not receive credentials, SQL, endpoints, answer text, or exception traces.

## Triage

1. Record `knowledge_update_id`, chunk ID, timestamp, worker PID, and response
   status.
2. Find all ordered stage logs for the ID. Do not log or paste the answer.
3. In a fresh PostgreSQL connection, read `chunks.content`, `embeddings.vector`,
   and latest `chunk_versions` entry for that one synthetic/approved chunk.
4. In a fresh Qdrant client, retrieve that point with payload and vector.
5. Compare SHA-256 content fingerprints and vector length/value tolerance.
6. If PostgreSQL committed, it wins. Targeted-upsert only that point from the
   canonical row, with `wait=True`, then retrieve it again.
7. Confirm the corpus revision query changed and issue a fresh chatbot request
   through another worker.

Never reset a collection, bucket, database, or whole knowledge directory to
repair one point.

## Safe targeted verification pattern

Use a pre-approved synthetic chunk ID. The SQL below reveals content, so run it
only in a protected terminal and compare a hash rather than copying output:

```sql
SELECT c.id,
       encode(digest(c.content, 'sha256'), 'hex') AS content_sha256,
       c.updated_at,
       jsonb_array_length(e.vector::jsonb) AS vector_dimension
FROM chunks c
JOIN embeddings e ON e.chunk_id = c.id
WHERE c.id = :synthetic_chunk_id;
```

Retrieve the same Qdrant point and hash `payload.content` locally. Confirm
`payload.knowledge_revision` matches the successful response and the vectors
match within floating-point tolerance.

## Compensation failure

If logs contain `QDRANT_COMPENSATION_FAILED`, stop automated retries for that
chunk. Determine whether PostgreSQL committed:

- not committed: restore/upsert the last `chunk_versions` content and its
  regenerated vector to Qdrant;
- committed: regenerate from current `chunks.content` and targeted-upsert it;
- uncertain: establish PostgreSQL transaction outcome first; never choose the
  Qdrant payload as canonical merely because it is newer.

After repair, use a fresh DB connection, fresh Qdrant client, and a fresh
chatbot request routed to each app instance. The old answer must be absent from
the selected LLM context.

## Schema or configuration mismatch

If rows or points cannot be found, compare the exact PostgreSQL database/schema
and Qdrant collection used by the update worker and answering worker. The repo
contains historical schema/config variants; do not run destructive migrations
or setup scripts as diagnosis. Capture `information_schema.columns`, current
database/schema, collection metadata, process environment names, and deployed
SHA, then plan a reviewed migration separately.

## MinIO/filesystem incidents

MinIO and ingestion files do not need repair after an answer edit. If app
startup is blocked by MinIO or future re-ingestion must preserve the edit,
resolve that as a source-governance workflow: export the canonical approved
answer, update the controlled source, regenerate into an isolated namespace,
quality-test, then deploy. Do not overwrite source objects during incident
triage.
