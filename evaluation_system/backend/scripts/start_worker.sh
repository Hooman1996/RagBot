#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
# The Python launcher loads the normal root .env and passes the configured
# EVAL_CELERY_POOL/EVAL_CELERY_CONCURRENCY explicitly to Celery. V1 defaults
# are pool=solo and concurrency=1 so CUDA is never initialized after a fork.
exec python3 -m evaluation_system.backend.scripts.start_worker
