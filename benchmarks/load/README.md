# Mobile talk staging load test

`mobile_talk_load_test.py` is a standalone asynchronous `httpx` load generator
for the mobile talk API. It supports synchronized burst waves, closed-loop
workers, and independently scheduled arrival-rate traffic. It sends no retries
and uses one reusable `httpx.AsyncClient` for the complete run.

This tool is staging-only. HTTPS is the default. Plain HTTP requires the
explicit `--allow-http` exception and is limited to loopback or explicit
staging/test/dev hosts. Disabled TLS verification, production-looking hosts,
and `0.0.0.0` client targets remain forbidden. Unit tests send no live traffic.

## Safety prerequisites

The repository contract and remaining deployment risks are documented in
[`docs/performance/06-load-test-prerequisites.md`](../../docs/performance/06-load-test-prerequisites.md).
Resolve these gates with the staging owner before sending even one request.

| Item | Verified behavior | Evidence | Test impact | Unresolved deployment risk |
|---|---|---|---|---|
| Effective endpoint | Repository-direct path is `POST /api/mobile/v1/talk`; a gateway may expose it as `POST /v1/talk` | `mobile_api.py:10,77`, `main.py:414-416` | Default `--endpoint` is `/v1/talk`; pass `/api/mobile/v1/talk` when targeting the app directly | Confirm the deployed reverse-proxy path |
| Request | Required strings: `session_id`, `query`, `national_code`; optional `documents` defaults to `["General_FAQ"]` | `mobile_api.py:22-26,96-98` | The runner sends the exact four-field JSON shape | External gateway validation remains unknown |
| Success | HTTP 200 and all six `TalkResponse` fields with valid types; the bot answer is in `answer` | `mobile_api.py` | Query and answer text remain in memory only; artifacts contain hashes, lengths, status, and timings | Deployed revision must match |
| Headers/auth | App route has no auth dependency; JSON is required; `X-Request-Id` is accepted on errors | `mobile_api.py:10,73-78`, `main.py:438-455` | Optional bearer token comes from `RAGBOT_STAGING_AUTH_TOKEN`; tokens are omitted from artifacts | Confirm gateway/network authentication |
| Session IDs | Truthy strings at the API; database column is unique `VARCHAR(36)` | `mobile_api.py:22-26`, `database.py:108-112,641-658` | Deterministic UUIDs are unique per virtual user and retained for follow-ups | Preflight every planned UUID; lookup is not user-scoped |
| National codes | No digit, length, or Iranian checksum validation in the endpoint | `mobile_api.py:22-26,96-98` | Generation is forbidden; an input fixture of reserved identities is mandatory | Staging owner must guarantee isolation/reservation |
| Identity provisioning | Unknown codes create persistent users | `database.py:203-245` | Use pre-created identities only | Confirm fixture identities and clean database ownership |
| Write footprint | A call can create a session, insert the prompt, store the answer, and update session metadata | `mobile_api.py:103-169`, `database.py:349-504,641-658` | Every live example is state-changing | Partial writes can remain after failures/timeouts |
| Cleanup | No safe API deletes by the external session UUID and no user-delete API is available | `main.py:744-754`, `mobile_api.py:195-202` | `--cleanup` writes a manifest only; an authorized operator must reconcile/delete run sessions and queries | Rehearse the database cleanup procedure first |
| Limiter | One `AdmissionLimiter` per worker is shared by the web and mobile answer routes | `main.py`, `mobile_api.py`, `utils/concurrency.py` | HTTP 503 plus `SERVICE_BUSY` is an admission timeout | Verify live worker count and effective capacity |
| Deadline | Admission plus application work share one configured endpoint deadline | `main.py`, `mobile_api.py`, `utils/concurrency.py` | HTTP 504 plus `DEPENDENCY_TIMEOUT` is an application deadline timeout; default client read timeout is 55 seconds | Cancellation may not stop already-submitted downstream work |
| Observability | The application emits content-free request/admission/stage headers and worker-local counters | `main.py`, `utils/request_instrumentation.py` | The runner records these headers when present; unavailable values stay null | Service schedulers still require their own telemetry |

Do not use real customer data. The built-in prompts are synthetic questions
from the reviewed FAQ/chitchat scenarios. Plaintext remains in memory only as
needed to send requests and validate responses. Persisted performance
artifacts contain run-salted hashes, lengths, classifications, and timings.

## Identity fixture

The ready-to-use synthetic fixture is
[`fixtures/staging_synthetic_identities.json`](fixtures/staging_synthetic_identities.json).
It contains 50 unique, deterministically generated 16-digit numeric strings
and 50 unique canonical UUID session IDs. These 16-digit values are not valid
Iranian 10-digit national codes. The application does not validate national
codes, but the staging owner must still preflight every value for absence,
reserve it, and confirm the gateway accepts the format before use.

```json
{
  "identities": [
    {
      "alias": "vu-001",
      "national_code": "2268715628155917",
      "session_id": "97a71bb1-37d8-5f0d-b0a2-d7a96b0772a7"
    }
  ]
}
```

The ready-to-use Persian question set is
[`fixtures/persian_banking_scenarios.json`](fixtures/persian_banking_scenarios.json).
Select one of `banking-smoke`, `banking-faq`, `banking-follow-up`, or
`banking-mixed` using `--scenario`, and provide the file using
`--scenario-file`.

The runner does not record the fixture national code or session ID in result
artifacts. It records only run-salted hashes for correlation.
`--national-code-mode iranian-checksum` intentionally exits with code 2 because
a generated checksum-valid code could collide with an existing user.

## Request-count and continuity semantics

For every workload:

```text
total_requests = concurrency × repetitions
```

In burst mode, each repetition is a separate synchronized wave. Therefore
`--concurrency 50 --repetitions 5` means five waves of 50 and 250 measured
requests. The next wave starts only after the prior wave completes.

In closed-loop mode, `concurrency` workers each issue `repetitions` sequential
requests. In arrival-rate mode, the same total is scheduled at the requested
requests-per-second rate, independently of prior global completion.

Every virtual user uses the unique UUID supplied by its identity fixture. If a
custom fixture omits `session_id`, the runner creates a deterministic UUID.
Scenario steps cycle across that user's requests. Follow-up requests wait for
the same user's prior request in all modes, while different users remain
concurrent. In arrival-rate mode, any wait required to preserve that ordering
appears in `scheduler_lag_ms`.

Warm-up requests use separate warm-up session UUIDs and are excluded from raw
measured-request files and acceptance statistics. Their aggregate outcome is
included in `summary.json`. Any failed warm-up aborts the measured workload
with exit code 2 and writes `warmup-summary.json`; cleanup may still be needed
because the endpoint can persist state before returning an error.

## Environment-controlled performance settings

Application-side performance settings are loaded and validated by
`utils/performance_config.py`. Restart FastAPI after changing any value.

| Area | Environment variables |
|---|---|
| Deadline and admission | `APPLICATION_REQUEST_TIMEOUT_SECONDS` (maximum 50), `REQUEST_CONCURRENCY_LIMIT`, `REQUEST_ADMISSION_TIMEOUT_SECONDS` |
| Blocking work | `BLOCKING_CONCURRENCY_LIMIT` |
| TEI client | `TEI_HTTP_MAX_CONNECTIONS`, `TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS`, `TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS`, `TEI_HTTP_CONNECT_TIMEOUT_SECONDS`, `TEI_HTTP_READ_TIMEOUT_SECONDS`, `TEI_HTTP_WRITE_TIMEOUT_SECONDS`, `TEI_HTTP_POOL_TIMEOUT_SECONDS` |
| vLLM client | `VLLM_HTTP_MAX_CONNECTIONS`, `VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS`, `VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS`, `VLLM_HTTP_CONNECT_TIMEOUT_SECONDS`, `VLLM_HTTP_READ_TIMEOUT_SECONDS`, `VLLM_HTTP_WRITE_TIMEOUT_SECONDS`, `VLLM_HTTP_POOL_TIMEOUT_SECONDS` |
| Retrieval | `QDRANT_CONCURRENCY`, `RAG_RETRIEVAL_TOP_K`, `RAG_SEMANTIC_CANDIDATE_LIMIT`, `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD`, `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` |
| Generation | `RAG_MAX_NEW_TOKENS`, `RAG_CHITCHAT_MAX_NEW_TOKENS`, `RAG_REWRITE_MAX_TOKENS` |

The first admission experiment keeps every previous default except:

```text
REQUEST_CONCURRENCY_LIMIT=32
REQUEST_ADMISSION_TIMEOUT_SECONDS=12
APPLICATION_REQUEST_TIMEOUT_SECONDS=50
```

This tests whether the 18 requests previously rejected after two seconds can
wait for one of the 32 application slots. Do not change another performance
setting during the comparison. Restart the application, repeat the same
50-request workload at least three times, and compare against the preserved
two-second baseline. For the mobile endpoint, the 50-second deadline covers
both admission waiting and application processing.

The vLLM server scheduler settings (`max_num_seqs`,
`max_num_batched_tokens`, GPU-memory utilization, prefix caching, chunked
prefill, model length, dtype, and quantization) belong to the separately
launched vLLM service. This repository has no Docker or service launch
definition for that process, so the FastAPI environment variables above do
not configure those server flags.

## Safe command examples

Set the actual reviewed staging URL. The included identity fixture contains
only synthetic data; copy it into the staging owner's controlled workflow if
that deployment requires fixtures outside the repository. Prefer an
environment variable for a gateway token:

```bash
export RAGBOT_STAGING_AUTH_TOKEN='<obtain from approved secret source>'
```

The examples assume the gateway exposes `/v1/talk`. If the test targets this
FastAPI application directly, use `--endpoint /api/mobile/v1/talk`.

### Local HTTP on port 7000

`API_HOST=0.0.0.0` means the server listens on all interfaces. A client on the
same machine must use `127.0.0.1`, not `0.0.0.0`. After starting the
application and confirming port 7000 is listening, run:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url http://127.0.0.1:7000 \
  --allow-http \
  --endpoint /api/mobile/v1/talk \
  --workload-mode burst \
  --concurrency 1 \
  --repetitions 1 \
  --scenario banking-smoke \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --max-connections 1 \
  --max-keepalive-connections 1 \
  --cleanup
```

This endpoint writes users, sessions, queries, answers, and metadata to the
services configured by `.env`; local HTTP does not make those writes ephemeral.

### 1. Smoke test

One state-changing measured request:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url https://ragbot-staging.example \
  --endpoint /v1/talk \
  --concurrency 1 \
  --repetitions 1 \
  --scenario banking-smoke \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --max-connections 1 \
  --max-keepalive-connections 1 \
  --cleanup
```

### 2. Ten concurrent requests

Run only after the smoke request, persistence inspection, and cleanup succeed:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url https://ragbot-staging.example \
  --endpoint /v1/talk \
  --workload-mode burst \
  --concurrency 10 \
  --repetitions 1 \
  --scenario banking-faq \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --max-connections 10 \
  --max-keepalive-connections 10 \
  --cleanup
```

### 3. One 50-request burst

This is material staging traffic. Review the command, live limiter/worker
capacity, background workload, GPU state, stop conditions, and cleanup plan
before executing it:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url https://ragbot-staging.example \
  --endpoint /v1/talk \
  --workload-mode burst \
  --concurrency 50 \
  --repetitions 1 \
  --scenario banking-faq \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --request-timeout 55 \
  --max-connections 50 \
  --max-keepalive-connections 50 \
  --cleanup
```

### 4. Five repeated waves of 50

This is the requested 250-measured-request validation command. It is generated
for manual review and was not run while creating this tool:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url https://ragbot-staging.example \
  --endpoint /v1/talk \
  --workload-mode burst \
  --concurrency 50 \
  --repetitions 5 \
  --scenario banking-faq \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --seed 20260728 \
  --request-timeout 55 \
  --acquire-start-delay 0.05 \
  --max-connections 50 \
  --max-keepalive-connections 50 \
  --cleanup
```

### Requested five-wave local example

This is the exact manual command for five 30-request waves (150 measured
requests). It was not run automatically:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url http://127.0.0.1:7000 \
  --allow-http \
  --endpoint /api/mobile/v1/talk \
  --workload-mode burst \
  --concurrency 30 \
  --repetitions 5 \
  --scenario banking-faq \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --request-timeout 55 \
  --max-connections 30 \
  --max-keepalive-connections 30 \
  --minimum-success-rate 1.0 \
  --maximum-p95 20 \
  --maximum-success-latency 20 \
  --cleanup
```

### 5. Mixed realistic workload

Closed-loop workers rotate several short and longer Persian banking questions
while preserving each user's session:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url https://ragbot-staging.example \
  --endpoint /v1/talk \
  --workload-mode closed-loop \
  --concurrency 10 \
  --repetitions 6 \
  --scenario banking-mixed \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --max-connections 10 \
  --max-keepalive-connections 10 \
  --cleanup
```

An open arrival-rate variant is:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url https://ragbot-staging.example \
  --endpoint /v1/talk \
  --workload-mode arrival-rate \
  --arrival-rate 2 \
  --concurrency 10 \
  --repetitions 6 \
  --scenario banking-mixed \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --max-connections 10 \
  --max-keepalive-connections 10 \
  --cleanup
```

### 6. Strict 20-second acceptance test

Strict mode requires no limiter rejection, application/client timeout, or HTTP
5xx; 100% success; and every successful request at or below 20 seconds:

```bash
python3 benchmarks/load/mobile_talk_load_test.py \
  --base-url https://ragbot-staging.example \
  --endpoint /v1/talk \
  --workload-mode burst \
  --concurrency 50 \
  --repetitions 5 \
  --scenario banking-faq \
  --input-file benchmarks/load/fixtures/staging_synthetic_identities.json \
  --scenario-file benchmarks/load/fixtures/persian_banking_scenarios.json \
  --request-timeout 55 \
  --max-connections 50 \
  --max-keepalive-connections 50 \
  --strict \
  --cleanup
```

## Acceptance and exit codes

Default criteria are:

- at least 99% successful responses, globally and in every wave;
- successful-response p95 at most 20 seconds, globally and in every wave;
- maximum successful latency at most 20 seconds, globally and in every wave;
- zero application deadline timeouts;
- zero limiter acquisition failures;
- zero HTTP 5xx responses.

Thresholds are configurable with `--minimum-success-rate`, `--maximum-p95`,
`--maximum-success-latency`, `--maximum-application-deadline-timeouts`,
`--maximum-limiter-rejections`, and `--maximum-http-5xx`. Latency CLI values
are seconds.

Exit codes are 0 for a completed passing test, 1 for a completed test whose
criteria fail, and 2 for unsafe/invalid configuration or setup failure.

## Artifacts and privacy

Unless `--output-dir` is given, results are written under:

```text
benchmarks/results/mobile-talk/<UTC timestamp>/
```

The directory contains `requests.jsonl`, `requests.csv`, `summary.json`,
`report.md`, and `interactions.md`. `--cleanup` also adds
`cleanup-manifest.json`. Request records contain run-salted identifier/query/
answer hashes, lengths, timings, classifications, schema validity, request
IDs, and recognized server timing headers. They contain no authentication
token, national code, session ID, query text, or answer text.

CSV is UTF-8 and uses standard CSV quoting. `interactions.md` presents hashes,
lengths, outcomes, and timings. Perform answer-quality review in a separately
access-controlled workflow. The tool calculates descriptive quality-supporting
metrics but does not score semantic correctness. Answer lengths are Unicode character
counts over schema-valid answers. Duplicate count means repeated exact answer
occurrences beyond the first; duplicate and empty-answer percentages use the
number of schema-valid answers as their denominator.

Percentiles use R-7 linear interpolation. Success latency percentiles are
explicitly labeled success-only and always show the excluded failure count.
All completed-attempt latency is reported separately. Metrics are available
globally and by wave, scenario step, status code, and failure category.

## Performance metric guide

- **Total attempts:** Total number of requests sent by the load generator.
- **Successful requests:** Requests that returned the expected HTTP status and a valid `TalkResponse`.
- **Success rate:** Successful requests divided by total attempts.
- **Minimum latency:** The fastest successful request in the measured run.
- **Maximum latency:** The slowest successful request.
- **Average latency:** Sum of successful-request latencies divided by the number of successful requests. Averages can hide slow tail requests.
- **Median or p50:** Half of successful requests completed faster and half completed slower.
- **p75:** 75% of successful requests completed within this duration.
- **p90:** 90% completed within this duration.
- **p95:** 95% completed within this duration. p95 is usually more useful than the average for understanding user-facing performance.
- **p99:** 99% completed within this duration. p99 reveals tail latency, queueing, and occasional slow requests.
- **Standard deviation:** Measures how spread out request times are. A low value means consistent latency; a high value means unstable latency.
- **Throughput:** Number of completed requests divided by total wall-clock test duration. Throughput is not the same as concurrency.
- **Concurrency:** Number of requests intended to be active simultaneously.
- **Repetitions:** Number of repeated workload waves.
- **Total wall-clock duration:** Time between releasing the first measured request and receiving the last measured response.
- **Excluded failures:** Failed requests excluded from successful-request latency percentiles. They must still appear in failure counts.
- **Limiter rejection:** A request that could not acquire an application limiter slot within the configured acquisition timeout.
- **Application deadline timeout:** A request that entered application processing but exceeded the endpoint's 50-second deadline.
- **Client timeout:** The load generator stopped waiting before receiving a response.
- **Percentage within 10, 15, 20, and 50 seconds:** Percentage of successful requests completing within each latency threshold.

### Worked example

```text
PASS: 30/30 successful (100.00%); p95=9298.75 ms; max=9306.84 ms; excluded_failures=0; throughput=3.221 req/s
```

All 30 requests completed successfully. 95% completed in approximately 9.30
seconds or less. The slowest request completed in approximately 9.31 seconds.
No failed requests were excluded from latency calculations. The full burst
completed at an effective rate of approximately 3.22 requests per second.

Concurrency 30 does not mean throughput 30 requests per second. One repetition
is not enough to establish stability; multiple repeated waves are needed.
Passing at concurrency 30 does not prove concurrency 50 will pass. Review
response quality separately in an access-controlled quality artifact.

The runner does not execute cleanup itself. Stop traffic, reconcile the
manifest against the staging database, remove only run-created sessions and
queries using the staging owner's approved transaction, verify zero remaining
run sessions, and preserve only sanitized benchmark artifacts. Pre-created
fixture identities should not be deleted merely because they were used by a
run.

## Unit tests

The repository has no configured Python linter or type checker. The isolated
test command is:

```bash
python3 -m unittest -v tests.benchmarks.test_mobile_talk_load_test
```

The tests use `httpx.MockTransport`; they make no network requests and create
no application records.
