# RagBot Evaluation System — Clean Server Start Procedure

This guide describes the **first-time clean deployment** of the RagBot Evaluation System on a server where the supporting infrastructure is already available.

## Target architecture

```text
Browser
   ↓
Eval Frontend :8088
   ↓
Eval API
   ↓
PostgreSQL
   ↑
Eval Worker
   ↓
RagBot :7000
   ↓
Qdrant / TEI / vLLM / MinIO / PostgreSQL
```

The Eval system consists of three running containers:

```text
eval-api
eval-worker
eval-frontend
```

The API and worker use the same backend Docker image. The frontend uses its own Docker image.

---

## 1. Expected directory structure

```text
/root/projects/faq/
├── .env
├── main.py
├── ...
│
└── evaluation_system/
    ├── backend/
    │   ├── Dockerfile
    │   ├── .env.example
    │   └── ...
    │
    ├── frontend/
    │   ├── Dockerfile
    │   ├── .env.example
    │   └── ...
    │
    └── deployment/
        ├── docker-compose.yml
        ├── docker-compose.local.yml
        └── .env
```

The root `.env` belongs to **RagBot only**.

The Eval deployment uses:

```text
evaluation_system/deployment/.env
```

The backend and frontend `.env.example` files are templates/documentation only when Docker Compose is used.

---

## 2. RagBot root `.env`

File:

```text
/root/projects/faq/.env
```

Keep the existing RagBot configuration for PostgreSQL, Qdrant, MinIO, TEI, vLLM, retrieval, generation, intent classifier, capacity, and debugging.

Remove the obsolete old embedded Eval section, especially:

```text
EVAL_REDIS_URL
EVAL_USE_CELERY
EVAL_CELERY_QUEUE
EVAL_CELERY_POOL
EVAL_CELERY_CONCURRENCY
```

The new Eval system no longer uses Redis or Celery.

---

## 3. Backend `.env.example`

File:

```text
/root/projects/faq/evaluation_system/backend/.env.example
```

This is only a safe template for running the backend manually outside Docker:

```dotenv
EVAL_ENABLED=true
EVAL_API_HOST=0.0.0.0
EVAL_API_PORT=8090

POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=eval_local
POSTGRES_USER=eval_local
POSTGRES_PASSWORD=replace-with-a-local-password

EVAL_ALLOW_DB_INIT=false
EVAL_CORS_ORIGINS=http://127.0.0.1:4173

EVAL_SESSION_CONCURRENCY=1
EVAL_REPEAT_MAX=100
EVAL_WORKER_POLL_INTERVAL_SECONDS=1
EVAL_WORKER_STALE_AFTER_SECONDS=300
EVAL_SSE_POLL_INTERVAL_SECONDS=1
EVAL_MAX_UPLOAD_BYTES=20971520
EVAL_MAX_DATASET_ROWS=50000

EVAL_RAGBOT_BASE_URL=http://127.0.0.1:7000
EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS=70
```

When using Docker Compose, do **not** create `evaluation_system/backend/.env`.

---

## 4. Frontend `.env.example`

File:

```text
/root/projects/faq/evaluation_system/frontend/.env.example
```

```dotenv
# Development-only Vite proxy target.
EVAL_API_DEV_PROXY=http://127.0.0.1:8090
```

This is only for running `npm run dev` outside Docker.

When the frontend runs through Docker/Nginx, no runtime frontend `.env` is required.

---

## 5. Create the Eval deployment `.env`

Create:

```text
/root/projects/faq/evaluation_system/deployment/.env
```

Use:

```dotenv
# ==========================================
# IMAGE / FRONTEND
# ==========================================
EVAL_IMAGE_TAG=local
EVAL_FRONTEND_PORT=8088

# ==========================================
# OPTIONAL BUILD PACKAGE MIRRORS
# ==========================================
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
NPM_REGISTRY_URL=https://mirrors.cloud.tencent.com/npm/

# ==========================================
# POSTGRESQL
# ==========================================
POSTGRES_HOST=host.docker.internal
POSTGRES_PORT=5432
POSTGRES_DB=hihelp_db
POSTGRES_USER=admin
POSTGRES_PASSWORD=<YOUR_POSTGRES_PASSWORD>

# ==========================================
# DATABASE INITIALIZATION
# ==========================================
# Enable only for the first initialization.
EVAL_ALLOW_DB_INIT=true

# ==========================================
# BROWSER / CORS
# ==========================================
EVAL_CORS_ORIGINS=

# ==========================================
# EVALUATION SETTINGS
# ==========================================
EVAL_SESSION_CONCURRENCY=1
EVAL_REPEAT_MAX=100

EVAL_WORKER_POLL_INTERVAL_SECONDS=1
EVAL_WORKER_STALE_AFTER_SECONDS=300
EVAL_SSE_POLL_INTERVAL_SECONDS=1

EVAL_MAX_UPLOAD_BYTES=20971520
EVAL_MAX_DATASET_ROWS=50000

# ==========================================
# RAGBOT
# ==========================================
EVAL_RAGBOT_BASE_URL=http://host.docker.internal:7000
EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS=70
```

Protect it:

```bash
chmod 600 /root/projects/faq/evaluation_system/deployment/.env
```

Do not commit this real `.env` file.

---

## 6. Main Eval `docker-compose.yml`

File:

```text
/root/projects/faq/evaluation_system/deployment/docker-compose.yml
```

Use the committed project version. It should define:

```text
eval-api      -> build ../backend and run Uvicorn
eval-worker   -> use the same backend image and run postgres_worker
eval-frontend -> build ../frontend and run Nginx
```

The API and worker receive their PostgreSQL and RagBot settings from `deployment/.env`.

---

## 7. Create `docker-compose.local.yml`

Create:

```text
/root/projects/faq/evaluation_system/deployment/docker-compose.local.yml
```

Contents:

```yaml
services:
  eval-api:
    extra_hosts:
      - "host.docker.internal:host-gateway"

  eval-worker:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

This is required for the clean-server topology where RagBot and PostgreSQL are reachable through host-published ports.

---

# Clean Server Deployment Procedure

## 8. Start the existing infrastructure

Before starting RagBot or Eval, make sure the supporting containers are running:

```bash
docker ps
```

Expected infrastructure includes:

```text
postgres-server
qdrant-server
minio-server
tei-embedding
tei-reranker
gemma4-vllm
```

The new Eval system does not require Redis or Celery.

---

## 9. Start RagBot

For the clean-server test:

```bash
cd /root/projects/faq
conda activate faq

uvicorn main:app \
  --host 0.0.0.0 \
  --port 7000
```

In production, the production team's RagBot Compose deployment replaces this manual command.

Verify RagBot:

```bash
curl -f http://127.0.0.1:7000/api/documents
```

Then:

```bash
curl -f \
  http://127.0.0.1:7000/api/internal/evaluation/v1/runtime-snapshot
```

Do not continue until both succeed.

---

## 10. Validate Eval Compose configuration

Open another terminal:

```bash
cd /root/projects/faq/evaluation_system/deployment
```

Validate:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  config
```

If this succeeds, the Compose file and required environment variables are valid.

---

## 11. Build the Eval images from scratch

Run:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  build
```

### Backend image

Docker:

```text
loads the Python base image
installs requirements.txt inside the image
copies the backend source code
copies Alembic and scripts
creates ragbot-eval-backend:local
```

### Frontend image

Docker:

```text
loads the Node build image
runs npm ci inside Docker
builds the React/Vite application
loads a clean Nginx image
copies the compiled frontend into Nginx
creates ragbot-eval-frontend:local
```

On a genuinely clean server this build may require public internet access or approved internal package/container mirrors.

The server itself does not need Python packages, npm packages, Node, or Nginx installed directly on the host.

Verify:

```bash
docker images | grep ragbot-eval
```

Expected:

```text
ragbot-eval-backend    local
ragbot-eval-frontend   local
```

---

## 12. Start the Eval containers

Run:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  up -d
```

This starts containers from the images built in the previous step:

```text
eval-api
eval-worker
eval-frontend
```

Check:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  ps
```

---

## 13. Inspect startup logs

API:

```bash
docker logs -f deployment-eval-api-1
```

Worker:

```bash
docker logs -f deployment-eval-worker-1
```

Frontend:

```bash
docker logs -f deployment-eval-frontend-1
```

Press `Ctrl+C` to stop following logs. The containers continue running.

There should be no repeated PostgreSQL connection failures, RagBot connection failures, import errors, or worker crashes.

---

# First-Time Database Initialization

## 14. Check database status

Because this is a clean database/schema, check:

```bash
curl \
  http://127.0.0.1:8088/api/v1/evaluation/system/database-status
```

Before initialization, the evaluation database will not yet be `READY`.

Container startup intentionally does not automatically create or migrate the Eval schema.

---

## 15. Open the Eval UI

Open:

```text
http://127.0.0.1:8088
```

The UI should detect that the Eval database is not initialized.

Because the first-start `.env` contains:

```dotenv
EVAL_ALLOW_DB_INIT=true
```

initialization is permitted.

Use the UI's database initialization workflow.

The backend also exposes:

```text
POST /api/v1/evaluation/system/database-initialize
```

but the UI is the normal operator workflow.

---

## 16. Verify initialization

After initialization:

```bash
curl \
  http://127.0.0.1:8088/api/v1/evaluation/system/database-status
```

Expected:

```text
READY
```

The Eval initialization must only create/manage Eval-owned database structures and must not alter RagBot application tables.

---

## 17. Disable database initialization

Edit:

```text
/root/projects/faq/evaluation_system/deployment/.env
```

Change:

```dotenv
EVAL_ALLOW_DB_INIT=true
```

to:

```dotenv
EVAL_ALLOW_DB_INIT=false
```

Then recreate the Eval containers so the new environment value is loaded:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  up -d --force-recreate
```

No image rebuild is required because only an environment variable changed.

---

# Final Validation

## 18. Verify frontend

```bash
curl -I http://127.0.0.1:8088/
```

Expected: HTTP 200.

## 19. Verify database

```bash
curl \
  http://127.0.0.1:8088/api/v1/evaluation/system/database-status
```

Expected: `READY`.

## 20. Verify RagBot datasource discovery

```bash
curl \
  http://127.0.0.1:8088/api/v1/evaluation/datasources
```

Expected to include available RagBot datasources such as `General_FAQ`.

## 21. Verify running containers

```bash
docker ps
```

Expected overall services include:

```text
postgres-server
qdrant-server
minio-server
tei-embedding
tei-reranker
gemma4-vllm

deployment-eval-api-1
deployment-eval-worker-1
deployment-eval-frontend-1
```

---

# Normal Operation After First Deployment

Once the images are built, the database is initialized, and `EVAL_ALLOW_DB_INIT=false`, normal startup is:

```bash
cd /root/projects/faq/evaluation_system/deployment

docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  up -d
```

No `pip install`, `npm install`, or DB initialization runs during normal startup.

---

# Stopping the Eval System

```bash
cd /root/projects/faq/evaluation_system/deployment

docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  down
```

This stops/removes only the Eval API, worker, frontend containers, and their Compose network. It does not stop RagBot, PostgreSQL, Qdrant, MinIO, TEI, or vLLM.

---

# Rebuilding After Eval Code Changes

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  build
```

Then:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  --env-file .env \
  up -d
```

Docker can reuse cached dependency layers when requirements/package-lock files have not changed.

---

# Production Recommendation

The procedure above intentionally builds images directly on the clean server so the full lifecycle is visible.

For mature production, the preferred process is:

```text
CI/build server
    ↓
build backend image
build frontend image
    ↓
push immutable images to company registry
    ↓
production server
    ↓
docker pull
docker compose up -d
```

The production server then does not need public PyPI/npm access.

It only needs access to the company's container registry and the runtime dependencies such as PostgreSQL and RagBot.

---

# First-Time Deployment Summary

```text
1. Start PostgreSQL, Qdrant, MinIO, TEI and vLLM.

2. Start RagBot.

3. Verify:
      /api/documents
      /api/internal/evaluation/v1/runtime-snapshot

4. Create:
      deployment/.env
      deployment/docker-compose.local.yml

5. Validate:
      docker compose ... config

6. Build:
      docker compose ... build

7. Start:
      docker compose ... up -d

8. Open:
      http://127.0.0.1:8088

9. Initialize Eval DB once.

10. Verify:
       database-status = READY

11. Set:
       EVAL_ALLOW_DB_INIT=false

12. Recreate containers.

13. Use the Evaluation System normally.
```
