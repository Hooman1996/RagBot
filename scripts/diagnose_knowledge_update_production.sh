#!/usr/bin/env bash
set -euo pipefail

mode="read-only"
confirmed="false"
for argument in "$@"; do
  case "$argument" in
    --synthetic-write-test) mode="synthetic" ;;
    --confirm-synthetic-write) confirmed="true" ;;
    *)
      echo "Unknown argument: $argument" >&2
      exit 2
      ;;
  esac
done

if [[ "$mode" == "synthetic" ]]; then
  if [[ "$confirmed" != "true" ]]; then
    echo "Synthetic writes refused: add --confirm-synthetic-write after provisioning an isolated test namespace." >&2
    exit 2
  fi
  exec python3 -m new_architecture.knowledge_update_diagnostics \
    --synthetic-update-test --confirm-synthetic-write
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
echo "knowledge-update production diagnostic (read-only)"
echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "repository_root=$repo_root"
echo "host=$(hostname)"
echo "python=$(python3 --version 2>&1)"

echo "application processes"
ps -eo pid=,ppid=,user=,lstart=,args= | \
  grep -E '[g]unicorn|[u]vicorn|[f]astapi.*main:app' || true
worker_count="$(pgrep -fc 'gunicorn|uvicorn|fastapi.*main:app' || true)"
echo "matched_process_count=$worker_count"

echo "application process working directories"
for process_id in $(pgrep -f 'gunicorn|uvicorn|fastapi.*main:app' || true); do
  process_cwd="unavailable"
  if [[ -r "/proc/$process_id/cwd" ]]; then
    process_cwd="$(readlink -f "/proc/$process_id/cwd" || true)"
  fi
  echo "pid=$process_id cwd=$process_cwd"
  if [[ -r "/proc/$process_id/environ" ]]; then
    echo "pid=$process_id selected_non_secret_environment"
    tr '\0' '\n' < "/proc/$process_id/environ" | \
      grep -E '^(POSTGRES_HOST|POSTGRES_PORT|POSTGRES_DB|POSTGRES_USER|QDRANT_URL|QDRANT_HOST|QDRANT_PORT|QDRANT_COLLECTION|MINIO_ENDPOINT|MINIO_BUCKET|DATA_INSERTION_DIRECTORY|KNOWLEDGE_BASE_CSV|WEB_CONCURRENCY)=' || true
  fi
done

echo "non-secret configuration names"
for name in POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER \
  QDRANT_URL QDRANT_HOST QDRANT_PORT QDRANT_COLLECTION \
  MINIO_ENDPOINT MINIO_BUCKET DATA_INSERTION_DIRECTORY KNOWLEDGE_BASE_CSV \
  WEB_CONCURRENCY; do
  if [[ -n "${!name:-}" ]]; then
    echo "$name=${!name}"
  else
    echo "$name=<unset>"
  fi
done

echo "read-only application diagnostics"
(
  cd "$repo_root"
  python3 -m new_architecture.knowledge_update_diagnostics \
    --check-configuration --check-paths --check-connections
)

echo "listening TCP ports"
if command -v ss >/dev/null 2>&1; then
  ss -ltnp 2>/dev/null || ss -ltn 2>/dev/null || true
else
  echo "ss unavailable"
fi

echo "container layout"
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.Networks}}' 2>&1 || true
else
  echo "docker unavailable"
fi

echo "No services were restarted and no data was written."
