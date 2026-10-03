# RagBot structured logging

## Contract

RagBot application events are UTF-8 JSON objects, one per stdout line. RagBot has no Logstash network client.

```text
RagBot -> JSON stdout -> infrastructure collector -> Logstash
```

The infrastructure owns collection, forwarding, retention, and access controls. Uvicorn startup/error logs are a separate stream; see [Uvicorn](#uvicorn-and-stdout) below.

Schema `1.0` reserves `@timestamp` (UTC ISO-8601), `schema_version`, `service`, `environment`, `event`, `level`, `request_id`, `upstream_request_id`, and `process.pid`. Event-specific fields are under `data`; client values do not set top-level field names. HTTP transactions emit one `request_received` event and one `response_completed` event when response handling completes. Internal admission events remain separate. The older `request_complete` event has been removed.

A typical request event contains `data.http.method`, `data.http.path`, and `data.request` with `received_at`, media type, content length, observed/original size, body omission/truncation flags, and a sanitized body when eligible. The response event contains `data.http.status_code`, `data.response` with analogous metadata, and `data.timing.started_at`, `completed_at`, `total_ms`, and measured `durations_ms`. It also carries admission timing when available. Missing stage durations are omitted rather than invented. Unhandled failures add `data.error.type`, never exception text or traceback. Query-string values are not logged.

## Correlation and HTTP observation

One outer pure ASGI middleware creates a server-owned UUID-like `RequestTrace.request_id` for every HTTP request. A valid bounded incoming `X-Request-Id` is retained only as `upstream_request_id`; malformed or oversized values become null. The formatter also scrubs this retained upstream value for free-text PII patterns without changing ordinary IDs. The response `X-Request-Id` is always RagBot's ID. The existing ContextVar makes that ID available to ordinary application logs under asyncio concurrency. There are no new request-ID parameters in domain services.

The middleware tees ASGI `receive` and `send` messages. It forwards each message without replay, eager request-body reads, whole-stream buffering, or changes to response chunk boundaries. It retains at most `LOG_BODY_MAX_BYTES` of eligible request or response body bytes and counts bytes as they naturally flow. Request logging occurs after `more_body=False` if downstream consumes the body; otherwise the request event is emitted before the transaction ends with metadata for observed bytes. Response completion is logged after the final response body message or on failure. Existing instrumentation headers are injected at `http.response.start`; stage measurements and endpoint behavior are unchanged. Streaming duration is included in `total_ms`.

## Background operations

A detached operation has its own bounded, validated `operation_id` and a
`parent_request_id` copied from the request that created it. The envelope keeps
`schema_version=1.0`; the two fields are additive and null on ordinary HTTP
logs. A mass-answer job uses its server-generated UUID `job_id` as
`operation_id`. The queued event is emitted while the originating request is
active; the detached task then clears its inherited `RequestTrace` through a
ContextVar boundary. Its events therefore have `request_id=null`,
`operation_id=<job_id>`, and `parent_request_id=<originating request_id>`.
Generated identifiers are bounded and scrubbed again at JSON formatting.

```text
HTTP request:          request_id=A
Queued background job: operation_id=B, parent_request_id=A, request_id=null
```

Mass-answer emits `mass_answer_job_queued`, `mass_answer_job_started`, and
exactly one terminal event: `mass_answer_job_completed`,
`mass_answer_job_failed`, or `mass_answer_job_cancelled`. The terminal records
contain counts/timings or an exception *type*; they never contain file names,
questions, answers, job access tokens, user IDs, or exception messages.
Cancellation retains the existing database failure-state contract. Direct
batches emit safe start/completion events. Starlette's post-response artifact
cleanup also uses an explicit background context. Awaited row workers and
blocking-runner tasks remain part of their caller's context. `asyncio.to_thread`
propagates the current ContextVars, so request work keeps its request ID and
background work keeps its operation and parent IDs.

The canonical per-request RAG timing record remains
`response_completed.data.timing.durations_ms`. Normal production execution
does not add separate events for normalization, history, rewrite, intent,
embedding, Qdrant, reranking, vLLM, or response building; this limits queue
pressure and duplicate timing data.

## Route and body policy

The central route policy logs sanitized JSON/text bodies for business APIs, login, mobile, knowledge-base JSON, and internal Eval endpoints. It does not alter routing or authentication. Health, documentation, UI pages, and download routes use metadata only. Static assets retain request tracing and response headers but skip the transaction events to avoid noise. OCR and mass-answer upload routes use metadata only. Any binary or multipart request disables body logging for both sides of that transaction, even if the response is JSON.

Bodies are captured only when `LOG_REQUEST_BODY` or `LOG_RESPONSE_BODY` is enabled for that side. JSON is parsed only from a complete bounded capture. Malformed JSON or invalid UTF-8 is represented by safe omission metadata; parsing errors do not affect the HTTP response. Text bodies use the central sanitizer. Multipart, octet-stream, PDF, image, CSV, spreadsheet, other file media, and event streams are metadata only. File bytes are never base64 encoded or logged. Body truncation logs `[TRUNCATED]` and `body_truncated=true`; `original_size_bytes` is recorded when known from the observed stream or transport metadata. Unknown sizes remain null. Upload metadata is limited to media type and size; file names are not parsed from multipart data solely for logging.

## Privacy

The central sanitizer copies nested structures, caps depth/items/text, and never emits Python repr strings, raw binary data, or exception text. Secret fields such as passwords, hashes, auth headers, cookies, CSRF values, tokens, API keys, and secrets become `[REDACTED]` case insensitively. HTTP bodies are sanitized *before* structured events are enqueued; the listener formatter sanitizes defensively again. Ordinary legacy log messages remain withheld because arbitrary interpolation can contain customer data.

National-code fields use HMAC-SHA256 with a dedicated `LOG_PII_HMAC_SECRET` and a `pii_` plus 24-hex-character prefix. The same code and key produce the same pseudonym. With no logging key, they become `[REDACTED]`. Phone, mobile, email, username, full name, and display name fields are always redacted. Job access fields are treated as secrets. Normal fields such as `service_name` are retained. A redaction marker or existing pseudonym is preserved through defensive re-sanitization. The key must never be `WEB_SESSION_SECRET`; production generates and stores it through deployment secret management, never Git. `LOG_PII_REDACTION=false` is rejected at startup.

Free text is scrubbed with bounded precompiled patterns for likely Iranian national codes, Iranian mobile numbers, email, Luhn-valid card numbers, Sheba/IBAN-like values, bearer/JWT-like tokens, and inline credential assignments. Persian/Arabic digits are supported where applicable. Pattern matching cannot identify every possible secret; avoid adding raw sensitive material under unrelated field names.

## Debug and plaintext stdout policy

The terminal pipeline observer may contain raw query, history, retrieval,
prompt, answer, session, and exception content. While RagBot's structured JSON
runtime is active, it does not print that report. It emits one content-free
`pipeline_debug_report_suppressed` event with only stage count and optional
exception type. The independent in-memory Eval observer and Eval HTTP payloads
retain their existing behavior. Terminal report printing remains available for
explicit offline/dev use without the application JSON runtime.

The active startup prints in the RAG system and Persian processor are now safe
structured lifecycle events. Important knowledge-base failure logs are safe
structured events; mass-answer row exceptions contribute to aggregate job
counts rather than one log per row. CLI/offline tools such as
`utils/extract_text_chunks.py` keep their terminal prints. Third-party and
Uvicorn stderr output remains separately routed as described below.

## Queue and latency

`LoggingRuntime.snapshot()` reports worker-local `queue_capacity`,
`queue_depth`, `overflow_count`, `stdout_write_errors`, and `listener_alive`.
The existing `GET /api/metrics/admission` response includes these under
`logging`, preserving its current authorization behavior and other fields.
The queue and saturation fallback are unchanged.

Normal request handling performs bounded observation/sanitization and a nonblocking `queue.put_nowait()`. One listener thread performs JSON formatting and stdout writes. No logging network call, per-request worker, database call, model call, or file sync is made. The queue holds at most 4096 events. Only when it is full does the handler increment `app.state.logging_runtime.handler.overflow_count` and synchronously write the safe event to stdout, preserving it at the cost of possible request latency. `stream_handler.write_errors` counts failed stdout writes. Logging failures do not change HTTP behavior; the infrastructure must monitor collection health. Shutdown drains the queue before stopping the listener.

Run `python benchmarks/logging_overhead.py` for the Stage 1 sanitizer/enqueue micro-benchmark and `python benchmarks/http_logging_overhead.py` for Stage 2's small in-process ASGI endpoint comparison (disabled versus enabled, median/p95, plus 50 concurrent requests). On the Stage 2.1 local recheck (1,000 in-process HTTP requests), the disabled endpoint measured median/p95 5.5/6.1 µs and the enabled endpoint 291.7/376.3 µs; added median/p95 was 286.2/370.2 µs. Fifty concurrent requests had 50 unique IDs and `overflow_count=0`. The Stage 1 sanitizer/enqueue recheck (5,000 samples) measured median/p95 247.7/727.0 µs versus 4.9/5.1 µs for the old JSON preparation baseline. Repeated local sanitizer runs varied substantially (median 230.1–685.8 µs), so these numbers should be treated as rough estimates. These measurements exclude model inference and external services; they are local micro-benchmarks, not production latency conclusions.

Stage 3 local recheck: HTTP disabled median/p95 5.4/12.8 µs, enabled 291.8/363.6 µs, added 286.4/350.9 µs; 50 concurrent requests had 50 unique IDs and `overflow_count=0`. The sanitizer/enqueue recheck measured 346.1/826.4 µs median/p95 versus 4.9/5.2 µs baseline. These runs are noisy local measurements; Stage 3 does not establish a production latency result. The final production-like RagBot concurrency benchmark belongs to the final logging stage. No zero-overhead claim is made.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Root application log threshold. |
| `LOG_FORMAT` | `json` | Only supported application format. |
| `LOG_SERVICE_NAME` | `ragbot` | Stable service identifier. |
| `LOG_ENVIRONMENT` | fallback | Log classification only: `LOG_ENVIRONMENT`, then `WEB_ENVIRONMENT`, then `ENVIRONMENT`, then `unknown`. |
| `LOG_BODY_MAX_BYTES` | `32768` | Maximum retained bytes per eligible request/response body. |
| `LOG_REQUEST_BODY` | `true` | Enable eligible request body capture. |
| `LOG_RESPONSE_BODY` | `true` | Enable eligible response body capture. |
| `LOG_PII_REDACTION` | `true` | Mandatory safety setting. |
| `LOG_PII_HMAC_SECRET` | unset | Dedicated national-code pseudonymization key; unset means redaction. |

`.env.example.generated` sets `LOG_ENVIRONMENT=staging`. `Production_ENV` sets `LOG_ENVIRONMENT=production` and contains only non-secret logging defaults; the HMAC key belongs in deployment secret management.

## Uvicorn and stdout

The installed Uvicorn defaults route `uvicorn.access` to **stdout** as plaintext and include the URL query string in its request line. `uvicorn.error` startup/error logs go to **stderr** as plaintext. RagBot's logging runtime disables the duplicate `uvicorn.access` logger for its lifespan because the structured HTTP pair supplies access records without raw query values, then restores the prior logger state at shutdown. The repository's direct `python main.py` launch also sets `access_log=False`. External Uvicorn CLI/process-manager launch commands should disable access logs as an additional deployment safeguard and must keep the application lifespan enabled. Uvicorn startup/error logs remain on stderr; the infrastructure collector should route RagBot JSON stdout and Uvicorn/process stderr separately. This repository does not define the production launch command.
