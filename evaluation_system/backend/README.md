# RagBot Evaluation Backend

This directory is a standalone evaluation service. The Eval API plans and
reports evaluation runs, while a separate PostgreSQL worker executes queued
runs. Both use the PostgreSQL `evaluation` schema and call a reachable RagBot
service through its internal HTTP API.

## Dependencies

- PostgreSQL
- A reachable RagBot HTTP service

Redis, Celery, Qdrant, GPUs, and local model services are not required. Set
`EVAL_RAGBOT_BASE_URL` to the RagBot service base URL.

## API

From `evaluation_system/backend` (or the root of a copied backend project):

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Deployment tooling may use `EVAL_API_HOST` and `EVAL_API_PORT` when constructing
the equivalent command.

## Worker

```bash
python -m app.worker.postgres_worker
```

The API and worker are separate processes from the same codebase or deployment
image. They must point to the same PostgreSQL database.

## Database initialization

`GET /api/v1/evaluation/system/database-status` reports migration status.
When `EVAL_ALLOW_DB_INIT=true`, initialize through
`POST /api/v1/evaluation/system/database-initialize` or the UI's **Initialize**
action. The existing Alembic migration creates and upgrades only the
`evaluation` schema. No separate database setup script is required.

## Development

1. Copy `.env.example` to `.env` and replace placeholders locally.
2. Install the packages in `requirements.txt`.
3. Start the API with the command above.
4. Start the worker in a separate process with the command above.

Do not store production credentials in `.env.example` or source control.
