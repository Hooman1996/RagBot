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

PostgreSQL and RagBot are external dependencies. Their configured hostnames
are examples and must resolve from the Compose container network. Do not use
`127.0.0.1` for either dependency unless it actually runs in the same
container (the standard topology does not).

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

The future start command is `docker compose up -d`; it is intentionally not
run as part of packaging validation.

The normal browser path is same-origin through Nginx, so
`EVAL_CORS_ORIGINS` may remain empty. Set it only for an alternative direct,
cross-origin API deployment.

Database migration status remains available through
`GET /api/v1/evaluation/system/database-status`. Initialization is explicit
through `POST /api/v1/evaluation/system/database-initialize` and is allowed
only when `EVAL_ALLOW_DB_INIT=true`; container startup does not run migrations.
