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

For the current local development stack, RagBot listens on port 7000:

```bash
EVAL_RAGBOT_BASE_URL=http://127.0.0.1:7000
```

This address is an environment-specific service boundary. When Eval runs in a
separate container in a future deployment, `127.0.0.1` refers to that Eval
container and cannot reach RagBot; configure a reachable RagBot service name
or host instead.

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

## Container image

Build the standalone image from this directory:

```bash
docker build -t ragbot-eval-backend:local .
```

The image defaults to the API process:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Use the same immutable image for the worker by overriding its command:

```bash
python -m app.worker.postgres_worker
```

The container must receive PostgreSQL and RagBot addresses that are reachable
from its network. Container loopback does not refer to services on the host.
No database migration runs automatically during image or container startup.

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
