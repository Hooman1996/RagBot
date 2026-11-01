# RagBot Evaluation V1 startup and use

## One-time configuration

Add the documented `EVAL_*` values from `.env.example.generated` to the root `.env` through the deployment's approved configuration process. At minimum, enable evaluation, configure Redis when Celery is enabled, and decide whether UI-driven database initialization is allowed. Do not create an evaluation token.

Build the static UI in a connected build environment:

```bash
cd /root/projects/faq/evaluation_system/frontend
npm ci
npm run build
```

The complete runtime frontend is now in `evaluation_system/frontend/dist`; npm and internet access are not needed at runtime.

## Normal startup

With PostgreSQL, Qdrant, MinIO, TEI, vLLM, and (when enabled) Redis already available:

```bash
cd /root/projects/faq
python main.py
```

In a second terminal:

```bash
cd /root/projects/faq
evaluation_system/backend/scripts/start_worker.sh
```

The worker reads the root `.env`, including queue, pool, and concurrency settings. If `EVAL_USE_CELERY=false`, do not start it; the API reports that background execution is unavailable.

The CUDA-safe V1 defaults are:

```dotenv
EVAL_CELERY_POOL=solo
EVAL_CELERY_CONCURRENCY=1
```

The resulting command is:

```bash
python3 -m celery -A evaluation_system.backend.app.worker.celery_app:celery_app \
  worker --queues=ragbot-evaluation --loglevel=INFO --pool=solo --concurrency=1
```

Do not use Celery `prefork` for the CUDA-backed evaluation runtime. The worker initializes the canonical RagBot runtime lazily once in its own process and reuses it across evaluation runs. It does not create a separate classifier per CSV row.

Celery may warn when a development worker runs as root. That warning is not the CUDA fork failure. Production should run the worker as the same non-root service user used by the deployment when one is available; development may continue under the current environment.

Open `http://<ragbot-host>:<ragbot-port>/evaluation`.

## First-time database setup

1. Sign in with an existing RagBot username and password.
2. Confirm the page reports `NOT_INITIALIZED` or `UPGRADE_REQUIRED`.
3. If `EVAL_ALLOW_DB_INIT=true`, choose **Create Evaluation Tables** or **Upgrade Evaluation Tables**.
4. Enter the exact confirmation `CREATE_EVALUATION_TABLES`.
5. Wait for the status to refresh to `READY`.

The action runs only predefined evaluation Alembic upgrades under a PostgreSQL advisory lock. It accepts no SQL and exposes no drop action. If initialization is disabled, follow the operator message shown by the UI.

## Use

For Dataset Inspector, upload a CSV/XLSX with required `query` and optional `session_id,time`, inspect validation warnings, select a datasource, and start the run. Rows sharing a session ID execute sequentially; every blank session ID is a separate one-turn session.

For Stability Inspector, choose a single query, an ordered user-only conversation, or a file; select the repeat count and datasource; then start the run. Every repetition receives fresh evaluation-only history.

Progress arrives over SSE. Runs continue if the browser closes and can be reopened from PostgreSQL-backed run history after signing in again.

## Authentication limitation preserved in V1

The existing RagBot `/api/login` authenticates against the existing users table but does not issue a cookie or bearer token. The integrated evaluation control plane therefore uses authenticated state in the running RagBot process. A browser reload or application restart requires signing in again. No password-storage behavior was changed.
