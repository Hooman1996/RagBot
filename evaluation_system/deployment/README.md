# Standalone Eval deployment

This directory is a local integration helper and architecture reference. It is
not a fourth product or a separately published repository. Keep it beside
`../backend` and `../frontend`; the sibling build contexts intentionally match
the permanent development layout. Production teams may deploy the two images
with their own platform instead of this Compose file.

This deployment packages three application services:

```text
Browser -> Eval Frontend/Nginx -> Eval API -> PostgreSQL
                                  Eval Worker -> PostgreSQL
                                  Eval Worker -> RagBot HTTP API
```

PostgreSQL and RagBot are external dependencies. Their configured addresses
must be reachable from the Eval containers. Container `127.0.0.1` does not
reach a service on the Docker host.

For the current single-host Linux development topology, set these values in
the Eval deployment `.env`:

```ini
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5432
EVAL_RAGBOT_BASE_URL=http://host.docker.internal:7000
```

The shared Compose backend configuration maps `host.docker.internal` to the
Docker host gateway for **both** Eval API and worker. The frontend uses the
private `eval-api` service name. For production, prefer infrastructure DNS or
service-discovery names reachable from the Eval containers, for example:

```ini
POSTGRES_HOST=postgres.internal
EVAL_RAGBOT_BASE_URL=http://ragbot.internal:8080
```

These are illustrative names, not actual production endpoints. If production
intentionally routes through its Docker host, the host-gateway mapping can be
used there too; it is not the preferred production default.

## Build

Each component builds independently from its own directory:

```bash
cd ../backend
docker build \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  -t ragbot-eval-backend:local .

cd ../frontend
docker build \
  --build-arg NPM_REGISTRY_URL=https://mirrors.cloud.tencent.com/npm/ \
  -t ragbot-eval-frontend:local .
```

The API and worker use the same `ragbot-eval-backend` image with different
commands. The frontend image contains the built SPA and Nginx. Nginx exposes
the browser-facing port and proxies only `/api/v1/evaluation/` to `eval-api`.
The pip index is a configurable build argument; the example above uses an
optional mirror, while the Dockerfile and Compose default to PyPI.
The frontend registry is configurable in the same way and defaults to the
official npm registry.

## Configure and validate

From this directory, copy `.env.example` to an untracked `.env`, replace the
placeholder database password and example network addresses, then validate:

```bash
docker compose config
```

For validation without creating `.env`, the committed example can be used:

```bash
docker compose --env-file .env.example config
```

Start or recreate only the required Eval services with `docker compose up -d
--no-deps eval-api eval-worker`; include `eval-frontend` only when its image or
configuration changed.

The normal browser path is same-origin through Nginx, so
`EVAL_CORS_ORIGINS` may remain empty. Set it only for an alternative direct,
cross-origin API deployment.

## First deployment and database initialization

Eval owns only the PostgreSQL `evaluation` schema and its own tables. RagBot
does not initialize them; do not change the root RagBot `.env` or restart
RagBot for this step. Container startup does not run migrations.

1. Set `EVAL_ALLOW_DB_INIT=true` in the Eval deployment `.env`, then deploy or
   recreate Eval API and worker.
2. Open the Eval UI and enter `CREATE_EVALUATION_TABLES` to confirm the
   initialization or upgrade.
3. The Eval backend runs its predefined Alembic migration for the `evaluation`
   schema. The browser cannot run arbitrary SQL.
4. Confirm database status is `READY` in the UI or through
   `GET /api/v1/evaluation/system/database-status`.
5. Restore `EVAL_ALLOW_DB_INIT=false` and recreate Eval API and worker with
   normal production settings.

The API endpoint `POST /api/v1/evaluation/system/database-initialize` requires
the same gate and explicit confirmation. Never run initialization as a network
verification step.

## Non-destructive Linux network checks

Run these from this directory after the Eval backend services are recreated:

```bash
docker compose config
docker compose exec eval-api getent hosts host.docker.internal
docker compose exec eval-worker getent hosts host.docker.internal

# Use -T when passing a heredoc through docker compose exec.
docker compose exec -T eval-api python - <<'PY'
from sqlalchemy import create_engine, text
from app.config import EvaluationSettings
settings = EvaluationSettings.from_environment()
engine = create_engine(settings.sqlalchemy_url(async_driver=False), hide_parameters=True)
try:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    print("PostgreSQL SELECT 1: OK")
finally:
    engine.dispose()
PY

docker compose exec -T eval-worker python - <<'PY'
import httpx
from app.config import EvaluationSettings
settings = EvaluationSettings.from_environment()
response = httpx.get(
    settings.ragbot_base_url + "/api/internal/evaluation/v1/runtime-snapshot",
    timeout=10,
)
print("RagBot runtime snapshot HTTP status:", response.status_code)
response.raise_for_status()
PY

curl -s http://127.0.0.1:8088/api/v1/evaluation/system/database-status | python -m json.tool
```

Before migration, `NOT_INITIALIZED` or `UPGRADE_REQUIRED` is expected; an
existing deployment may report `READY`. A hostname failure must not leave the
endpoint at `DATABASE_STATUS_ERROR`.
