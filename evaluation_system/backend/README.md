# RagBot Evaluation Backend

This directory is an independently buildable FastAPI control plane and worker.
The API manages datasets, plans runs, reports traces, and streams PostgreSQL-
backed SSE events. The worker claims queued runs from PostgreSQL and calls
RagBot over HTTP.

```text
Eval API <-> PostgreSQL evaluation schema <-> Eval Worker -> RagBot HTTP API
```

Its only external runtime dependencies are PostgreSQL and a reachable RagBot
HTTP service. It does not use Redis, Celery, Qdrant, TEI, vLLM, models, or GPUs.

## Development and validation

Run all commands from this directory, which is the future repository root:

```bash
python -m pip install -r requirements-dev.txt
conda run -n faq python -m pytest tests -q
python -m compileall -q app scripts alembic
```

Copy `.env.example` to an untracked `.env` and replace local placeholders.
The API and worker are separate processes and must use identical PostgreSQL
connection settings:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090
python -m app.worker.postgres_worker
```

## Configuration

`.env.example` lists every supported setting. The main groups are:

- `POSTGRES_*`: database host, port, database, user, and password.
- `EVAL_RAGBOT_BASE_URL` and `EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS`: reachable
  RagBot service and per-call timeout.
- `EVAL_WORKER_POLL_INTERVAL_SECONDS`, `EVAL_WORKER_STALE_AFTER_SECONDS`, and
  `EVAL_SESSION_CONCURRENCY`: worker polling, recovery, and bounded execution.
- `EVAL_MAX_UPLOAD_BYTES`, `EVAL_MAX_DATASET_ROWS`, and `EVAL_REPEAT_MAX`:
  input and planning limits.
- `EVAL_SSE_POLL_INTERVAL_SECONDS`: PostgreSQL event polling interval.
- `EVAL_ALLOW_DB_INIT`: explicit database-initialization gate.
- `EVAL_API_HOST`, `EVAL_API_PORT`, `EVAL_CORS_ORIGINS`, and `EVAL_ENABLED`:
  API binding and exposure settings.

The default `http://127.0.0.1:7000` RagBot URL is a local-development example,
not a production default. In production, configure a DNS/service address that
is reachable from the backend process or container. Do not commit real
credentials or private infrastructure addresses.

## Database initialization

The backend owns only the PostgreSQL `evaluation` schema. It has no foreign
keys into RagBot application schemas. Container startup never runs migrations.

`GET /api/v1/evaluation/system/database-status` reports status. Initialization
requires `EVAL_ALLOW_DB_INIT=true` and an explicit request to
`POST /api/v1/evaluation/system/database-initialize` (or the equivalent UI
action). Alembic then creates or upgrades only the `evaluation` schema. Keep the
gate false during normal operation. Rollback of an application image must not
delete evaluation data.

## Container roles

Build one image from this directory:

```bash
docker build -t ragbot-eval-backend:local .
```

The image runs as non-root UID/GID `10001:10001` and defaults to the API:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Use the exact same immutable image for the worker by overriding its command:

```bash
python -m app.worker.postgres_worker
```

`PIP_INDEX_URL` is a build argument and defaults to official PyPI. Tests,
documentation, local `.env` files, and parent-project sources are excluded from
the runtime image.

## Service contract

The backend exposes the browser/control-plane namespace
`/api/v1/evaluation/*`. Its RagBot client depends only on:

- `GET /api/documents`
- `POST /api/internal/evaluation/v1/turn`
- `GET /api/internal/evaluation/v1/runtime-snapshot`

If that transport contract changes, update the client, types, and contract
tests in a coordinated release. Pipeline behavior may evolve without changing
the transport contract; runtime snapshots preserve RagBot identity and config
for traceability.
