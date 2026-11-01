# Admission experiment plan: 50, 75, and 100 requests

## Status and safety gate

This is a command plan, not an executed benchmark. Every mobile talk request is
state-changing: it can create users/sessions and persist questions, answers,
and agent metadata. The full matrix must not run until the staging owner
provides at least 100 reserved identities, approves the write footprint and
cleanup, and types the confirmation required by the scripts.

The active `.env` is never used as an edit target. Candidate values are process
environment overlays for a second one-worker FastAPI instance on port 7100.
The active service on port 7000 remains running.

## Frozen workload

- Endpoint: `POST /api/mobile/v1/talk` on loopback staging.
- Scenario: one fixed reviewed synthetic scenario fixture.
- Seed: `20260805`.
- Warm-up: three requests, excluded from measured statistics.
- Waves: five per configuration.
- Retries: none.
- Client: one shared `httpx.AsyncClient`.
- Client max connections and keep-alive connections: equal to concurrency.
- Client read timeout: 55 seconds, so the 50-second application deadline is
  observable.
- Results: a unique timestamp/candidate/concurrency directory.

Matrix:

| Case | Arrival | Waves | Attempts |
|---|---|---:|---:|
| A | 50 simultaneous | 5 | 250 |
| B | 75 simultaneous | 5 | 375 |
| C | 100 simultaneous | 5 | 500 |
| D | 100 scheduled at 10 requests/s | 5 equivalent repetitions | 500 |

Do not compare cases that use different identities, query fixtures, seeds,
models, code revisions, background workloads, or worker counts.

## Required record schema

Each attempt must contain only sanitized metadata:

- client request ID and server request ID;
- submission index, wave, scenario ID, and hashed virtual-user alias;
- HTTP status, stable error code, body category, exclusive error type;
- client monotonic start/end and total latency;
- server receive offset when exposed;
- admission acquired boolean and outcome;
- admission wait, permit hold, pipeline, post-generation, and total duration;
- bounded stage durations, never stage content.

Do not store query text, answer text, national codes, authentication headers,
raw session IDs, prompts, retrieved document content, or credentials. Answer
quality review must use a separately controlled, access-restricted artifact;
the performance runner stores only answer length/token count and a run-salted
hash when needed.

## Metrics and acceptance

Record globally and per wave:

- attempts, successes, admission timeouts, application timeouts, client
  timeouts, pool timeouts, TEI/vLLM timeouts, and all HTTP 5xx;
- p50/p90/p95/p99/max total latency for all completed attempts and separately
  labeled success-only latency;
- admission wait and permit hold p50/p95/max;
- first permit release and permit release counts by 8, 10, and 12 seconds;
- waiters admitted before 12 seconds;
- Qdrant, blocking, database, TEI, vLLM, and HTTP-pool waits;
- event-loop lag, CPU, steal, run queue, context switches, threads, tasks,
  memory, sockets, PostgreSQL connections, GPU use/memory, vLLM running/waiting,
  TTFT, KV cache/preemptions, and TEI queue/latency.

The strict application target remains 100% success, zero admission/application/
client timeouts, zero HTTP 5xx, and every response within 20 seconds. Report
whether a case fails; do not redefine acceptance after seeing results.

## Baseline command review

Review only; prints the matrix and sends no traffic:

```bash
cd /root/projects/faq
scripts/run_admission_live_benchmark.sh \
  .env.test.admission-baseline
```

After explicit approval, an operator sets an untracked, reserved fixture and
runs the matrix:

```bash
cd /root/projects/faq
export RAGBOT_ADMISSION_IDENTITY_FIXTURE=/secure/path/staging-identities-100.json
export RAGBOT_ADMISSION_SCENARIO_FILE=/root/projects/faq/benchmarks/load/fixtures/persian_banking_scenarios.json
scripts/run_admission_live_benchmark.sh \
  .env.test.admission-baseline \
  --execute
```

The script requires the exact typed phrase
`RUN FULL STAGING ADMISSION MATRIX`. Do not place tokens on its command line.

## Exact one-case commands

Each command prompts for `RUN STAGING ADMISSION TEST` and starts a temporary
one-worker FastAPI process. These are commands to review, not commands executed
by this audit.

```bash
scripts/test_admission_configuration.sh .env.test.admission-baseline 50 burst
scripts/test_admission_configuration.sh .env.test.admission-baseline 75 burst
scripts/test_admission_configuration.sh .env.test.admission-baseline 100 burst
scripts/test_admission_configuration.sh .env.test.admission-baseline 100 arrival-rate 10
```

For a candidate, replace the first argument with exactly one of:

```text
.env.test.admission-keepalive-32
.env.test.admission-keepalive-64
.env.test.admission-qdrant-12
.env.test.admission-qdrant-16
.env.test.admission-blocking-20
.env.test.admission-blocking-24
.env.test.admission-timeout-15
.env.test.admission-timeout-18
```

Run the baseline before and after each candidate to detect background drift.
Change one major variable per comparison.

## Resource capture commands

Run in separate operator terminals with the same UTC timestamp/run ID. These
commands are read-only; output directories must be untracked.

```bash
result=/tmp/faq-admission-metrics-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$result"

pidstat -h -r -u -w -p "$(pgrep -n -f 'uvicorn main:app')" 1 \
  >"$result/fastapi-pidstat.txt"
vmstat 1 >"$result/vmstat.txt"
nvidia-smi dmon -s pucvmet -d 1 >"$result/nvidia-dmon.txt"
curl -fsS http://127.0.0.1:8000/metrics >"$result/vllm.prom"
curl -fsS http://127.0.0.1:7997/metrics >"$result/tei-embed.prom"
curl -fsS http://127.0.0.1:7998/metrics >"$result/tei-rerank.prom"
```

For process task/thread/socket snapshots:

```bash
pid="$(pgrep -n -f 'uvicorn main:app')"
ps -L -p "$pid" -o pid,tid,psr,pcpu,stat,comm
ls "/proc/$pid/task" | wc -l
ls "/proc/$pid/fd" | wc -l
ss -tanp
```

PostgreSQL connection counts should be collected through an operator-approved
read-only role; never put a password in the command line:

```sql
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state
ORDER BY state;
```

## Decision rules

- Increase keep-alive only when connection churn or pool wait is measured and
  the candidate improves comparable end-to-end results.
- Increase Qdrant only when its semaphore wait is material and Qdrant service
  latency, CPU, and memory stay healthy.
- Increase blocking concurrency only when blocking wait is material and CPU,
  event-loop lag, and database contention do not regress.
- Increase admission timeout only if the product accepts the added queue delay;
  18 seconds is especially likely to conflict with a 20-second strict target.
- Test request capacity 40, 50, and 60 as separate process overlays only after
  instrumentation is present. Choose from throughput, p95/p99, failures, and
  resource saturation—not from fewer 503 responses alone.

No non-baseline value is recommended yet because no controlled after-change
measurement exists.

## Temporary-instance rollback

`test_admission_configuration.sh` records the temporary PID, stops only that
process on success/failure/interrupt, compares the active `.env` hash, and
restores its private byte-for-byte backup if an external action changed the
file during the run. It never restarts the active service or any model/data
service.

## Manual active-service restart (approval required)

The observed process is an interactive Uvicorn reload command, not a verified
systemd/Gunicorn service. Do not kill it by guessed PID. After explicit
approval, the operator who owns its terminal should:

1. Save the exact current command and PID tree:

   ```bash
   cd /root/projects/faq
   pgrep -af 'uvicorn|gunicorn'
   curl -fsS http://127.0.0.1:7000/api/health >/dev/null
   ```

2. Stop only that Uvicorn command with one `Ctrl-C` in its owning terminal.
3. Start the same reviewed command from the same environment:

   ```bash
   cd /root/projects/faq
   /root/miniconda3/envs/faq/bin/python -m uvicorn main:app \
     --host 0.0.0.0 --port 7000 --workers 1
   ```

4. Verify health and one worker:

   ```bash
   curl -fsS http://127.0.0.1:7000/api/health >/dev/null
   pgrep -af 'uvicorn|gunicorn'
   ```

Do not add `--reload` to a controlled benchmark process because source edits
would silently replace the worker and invalidate the run.

## Code rollback

Before an approved implementation test, capture a patch outside the repository:

```bash
cd /root/projects/faq
git diff --binary -- \
  main.py mobile_api.py utils/concurrency.py benchmarks/load tests \
  >/tmp/faq-admission-code.patch
```

To reverse only those reviewed uncommitted changes, inspect the patch first and
then apply its reverse; this does not touch `.env`:

```bash
cd /root/projects/faq
git apply --check --reverse /tmp/faq-admission-code.patch
git apply --reverse /tmp/faq-admission-code.patch
```

Restarting the active FastAPI worker after code rollback still requires a
separate explicit approval.
