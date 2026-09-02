#!/usr/bin/env bash
set -euo pipefail

repo_dir="/root/projects/faq"
python_bin="/root/miniconda3/envs/faq/bin/python"
active_env="$repo_dir/.env"
baseline="$repo_dir/.env.test.admission-baseline"
candidate="${1:-}"
concurrency="${2:-50}"
workload_mode="${3:-burst}"
arrival_rate="${4:-}"
temporary_port="${RAGBOT_ADMISSION_TEMP_PORT:-7100}"
fixture="${RAGBOT_ADMISSION_IDENTITY_FIXTURE:-}"
scenario_file="${RAGBOT_ADMISSION_SCENARIO_FILE:-$repo_dir/benchmarks/load/fixtures/persian_banking_scenarios.json}"
scenario="${RAGBOT_ADMISSION_SCENARIO:-banking-faq}"
seed="${RAGBOT_ADMISSION_SEED:-20260805}"
second_pid=""

usage() {
  printf 'Usage: %s CANDIDATE_FILE CONCURRENCY [burst|arrival-rate] [ARRIVAL_RATE]\n' "$0"
}

if [[ -z "$candidate" ]]; then
  usage
  exit 2
fi
candidate="$(realpath "$candidate")"
if [[ ! -f "$candidate" || ! -f "$baseline" || ! -f "$active_env" ]]; then
  printf 'Required environment file is missing.\n' >&2
  exit 2
fi
if [[ -z "$fixture" || ! -f "$fixture" ]]; then
  printf 'Set RAGBOT_ADMISSION_IDENTITY_FIXTURE to an operator-approved staging fixture.\n' >&2
  exit 2
fi
if [[ "$workload_mode" != "burst" && "$workload_mode" != "arrival-rate" ]]; then
  usage
  exit 2
fi
if [[ "$workload_mode" == "arrival-rate" && -z "$arrival_rate" ]]; then
  printf 'Arrival-rate mode requires ARRIVAL_RATE.\n' >&2
  exit 2
fi

safe_tmp_dir="$(mktemp -d /tmp/faq-admission.XXXXXX)"
backup="$safe_tmp_dir/env.backup"
cp -- "$active_env" "$backup"
chmod 600 "$backup"
original_hash="$(sha256sum "$active_env" | awk '{print $1}')"

cleanup() {
  status=$?
  trap - EXIT INT TERM HUP
  if [[ -n "$second_pid" ]] && kill -0 "$second_pid" 2>/dev/null; then
    kill "$second_pid" 2>/dev/null || true
    wait "$second_pid" 2>/dev/null || true
  fi
  current_hash="$(sha256sum "$active_env" | awk '{print $1}')"
  if [[ "$current_hash" != "$original_hash" ]]; then
    cp -- "$backup" "$active_env"
    chmod 600 "$active_env"
    printf 'WARNING: active .env changed during the test and was restored exactly.\n' >&2
  fi
  rm -r -- "$safe_tmp_dir"
  exit "$status"
}
trap cleanup EXIT INT TERM HUP

deployment_mode="$($python_bin - "$active_env" <<'PY'
import os
import sys
from dotenv import load_dotenv
load_dotenv(sys.argv[1], override=False)
print((os.getenv("ENVIRONMENT") or "unknown").strip().lower())
PY
)"
case "$deployment_mode" in
  staging|stage|stg|development|dev|test|qa) ;;
  *)
    printf 'Refusing test: ENVIRONMENT is not an explicit staging/dev/test value.\n' >&2
    exit 2
    ;;
esac

identity_count="$($python_bin - "$fixture" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as stream:
    print(len(json.load(stream).get("identities", [])))
PY
)"
if (( identity_count < concurrency )); then
  printf 'Fixture has %s identities; %s are required.\n' "$identity_count" "$concurrency" >&2
  exit 2
fi

allowed='^(APPLICATION_REQUEST_TIMEOUT_SECONDS|REQUEST_CONCURRENCY_LIMIT|REQUEST_ADMISSION_TIMEOUT_SECONDS|BLOCKING_CONCURRENCY_LIMIT|TEI_HTTP_MAX_CONNECTIONS|TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS|TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS|TEI_HTTP_CONNECT_TIMEOUT_SECONDS|TEI_HTTP_READ_TIMEOUT_SECONDS|TEI_HTTP_WRITE_TIMEOUT_SECONDS|TEI_HTTP_POOL_TIMEOUT_SECONDS|VLLM_HTTP_MAX_CONNECTIONS|VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS|VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS|VLLM_HTTP_CONNECT_TIMEOUT_SECONDS|VLLM_HTTP_READ_TIMEOUT_SECONDS|VLLM_HTTP_WRITE_TIMEOUT_SECONDS|VLLM_HTTP_POOL_TIMEOUT_SECONDS|QDRANT_CONCURRENCY)$'

load_overlay() {
  local file="$1"
  local key value
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    if [[ ! "$key" =~ $allowed ]]; then
      printf 'Refusing non-allowlisted variable %s in %s.\n' "$key" "$file" >&2
      exit 2
    fi
    printf -v "$key" '%s' "$value"
    export "$key"
  done < "$file"
}

load_overlay "$baseline"
load_overlay "$candidate"

printf 'Candidate configuration (non-secret allowlist):\n'
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" == \#* ]] && continue
  printf '  %s=%s\n' "$key" "$value"
done < "$candidate"
printf 'Active .env SHA-256 before test: %s\n' "$original_hash"
printf 'Existing FastAPI processes:\n'
pgrep -af 'uvicorn|gunicorn' || true

if [[ "${RAGBOT_ADMISSION_CONFIRMED:-}" != "RUN STAGING ADMISSION TEST" ]]; then
  read -r -p 'Type RUN STAGING ADMISSION TEST to start a second FastAPI instance and state-changing load: ' confirmation
  if [[ "$confirmation" != "RUN STAGING ADMISSION TEST" ]]; then
    printf 'Confirmation did not match; nothing was started.\n' >&2
    exit 2
  fi
fi

if ! rg -q 'query_hash' "$repo_dir/benchmarks/load/mobile_talk_load_test.py"; then
  printf 'Refusing live run: sanitized benchmark schema is not installed.\n' >&2
  exit 2
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
candidate_name="$(basename "$candidate" | tr -cs '[:alnum:]._-' '_')"
result_dir="${RAGBOT_ADMISSION_RESULT_ROOT:-$repo_dir/benchmarks/results/admission}/$timestamp-$candidate_name-c$concurrency-$workload_mode"
mkdir -p "$result_dir"

curl -fsS --max-time 5 "http://127.0.0.1:7000/api/health" >/dev/null
printf 'Existing FastAPI health: HTTP 200\n'

cd "$repo_dir"
"$python_bin" -m uvicorn main:app \
  --host 127.0.0.1 \
  --port "$temporary_port" \
  --workers 1 \
  --log-level warning \
  --no-access-log \
  >/dev/null 2>&1 &
second_pid=$!
printf '%s\n' "$second_pid" >"$result_dir/temporary-fastapi.pid"

healthy=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$temporary_port/api/health" >/dev/null; then
    healthy=1
    break
  fi
  sleep 1
done
if [[ "$healthy" != 1 ]]; then
  printf 'Temporary FastAPI instance failed health check.\n' >&2
  exit 1
fi

args=(
  --base-url "http://127.0.0.1:$temporary_port"
  --allow-http
  --endpoint /api/mobile/v1/talk
  --workload-mode "$workload_mode"
  --concurrency "$concurrency"
  --repetitions 5
  --warmup-requests 3
  --scenario "$scenario"
  --input-file "$fixture"
  --scenario-file "$scenario_file"
  --output-dir "$result_dir/load"
  --seed "$seed"
  --request-timeout 55
  --max-connections "$concurrency"
  --max-keepalive-connections "$concurrency"
  --cleanup
)
if [[ "$workload_mode" == "arrival-rate" ]]; then
  args+=(--arrival-rate "$arrival_rate")
fi

"$python_bin" benchmarks/load/mobile_talk_load_test.py "${args[@]}"
curl -fsS --max-time 5 "http://127.0.0.1:$temporary_port/api/health" >/dev/null
printf 'Temporary FastAPI post-test health: HTTP 200\n'
printf 'Results: %s\n' "$result_dir"
