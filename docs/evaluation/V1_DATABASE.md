# RagBot Evaluation V1 database

## Isolation boundary

Evaluation uses the existing RagBot PostgreSQL connection configuration and a dedicated schema named `evaluation`. `EvaluationBase.metadata` contains only evaluation objects. Every FK target begins with `evaluation.`; there are no relationships to users, production sessions, queries, tickets, or knowledge tables. Cascades therefore cannot leave the evaluation schema.

## Tables

- `evaluation.datasets`: normalized import/manual dataset header, SHA256, row/session counts, parser issues in JSONB metadata.
- `evaluation.dataset_sessions`: one logical source session or one unique synthetic row session.
- `evaluation.dataset_turns`: ordered normalized user queries and source row/time fields.
- `evaluation.runs`: durable orchestration state, actual config snapshot, counters, cancellation/heartbeat/failure fields.
- `evaluation.run_sessions`: one isolated repetition of one logical session, with a unique opaque `evaluation_session_key` and stored divergence summary.
- `evaluation.run_turns`: generated Q/A ledger, actual normalized/rewrite/intent/fallback values, history/context hashes, infrastructure error classification, and state-after metadata.
- `evaluation.stage_results`: ordered full evaluation artifacts and hashes for the eight pipeline stages.

All PKs are PostgreSQL UUIDs. Timestamps use `timestamptz`; artifacts/metadata use JSONB. FK columns, status/list paths, source session IDs, chronological source ordering, turn indexes, repeat indexes, and created timestamps have explicit indexes. Deterministic uniqueness includes dataset source rows/source IDs, dataset/run turn indexes, repetition identity, request ID, evaluation session key, and one row per turn/stage/order. Database checks enforce nonnegative counters/durations, bounded progress counters, valid status/type values, 64-character SHA256 fields, and finish times not preceding start times.

## Deletion

- Dataset deletion cascades only through evaluation dataset children and associated evaluation runs.
- Run deletion cascades only through evaluation run sessions, turns, and stages.
- `SET NULL` is used for optional evaluation lineage references.
- No API drops tables or schemas.

## Migration environment

The independent Alembic environment is:

```text
evaluation_system/backend/alembic.ini
evaluation_system/backend/alembic/
```

Current head/revision:

```text
20260831_0001
```

Alembic stores its version in `evaluation.alembic_version`. The environment uses only `EvaluationBase.metadata`, filters schema discovery to `evaluation`, and builds its DSN from the same `POSTGRES_*` environment variables without rendering it.

The initial migration creates only the evaluation schema, seven evaluation tables, indexes, and constraints. Its operator-only downgrade drops those seven tables only. It does not call application metadata, `create_all`, `drop_all`, `DatabaseManager.init_db`, MinIO, or Qdrant.

## Safe status and initialization

Read-only status:

```bash
evaluation_system/backend/scripts/migration_status.sh
```

Equivalent:

```bash
python3 -m evaluation_system.backend.scripts.migration_status
```

The command/API reports `NOT_INITIALIZED`, `READY`, `UPGRADE_REQUIRED`, or `ERROR`, current/head revision, and an allowlisted set of missing evaluation table/index names. It does not print the DSN, host, username, or password.

Initialization is available only through `POST /api/v1/evaluation/system/database-initialize` when `EVAL_ALLOW_DB_INIT=true` and the body contains:

```json
{"confirmation":"CREATE_EVALUATION_TABLES"}
```

The server obtains `pg_try_advisory_lock(hashtext('ragbot:evaluation:migrations:v1'))`, creates the fixed schema if required, and runs only predefined `alembic upgrade head`. Concurrent initialization returns conflict. Repeating an upgrade-to-head is idempotent. There is no arbitrary SQL parameter and no reset/drop endpoint.

This implementation pass did not run the migration or status command against the configured database.

The deployment role must have `CREATE` privilege on the current database so it can create the `evaluation` schema. This was intentionally not probed against the configured database in this pass; a permission failure from the status/initialization workflow is a deployment blocker and must not be worked around by writing evaluation tables into a production schema.
