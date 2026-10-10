# Structured logging production handoff

**Release gate:** Controlled Stage 4.1 DEV attribution supports manual merge review of the logging feature; see [the measured audit](performance/STRUCTURED_LOGGING_STAGE4_1.md). No automatic merge is authorized. The current DEV stack still has dependency failures at 200 concurrency; production-like capacity validation on deployment hardware remains separate.

## Data flow

```text
RagBot JSON stdout -> infrastructure collector -> Logstash
Uvicorn/process stderr -> separate operational stream
```

RagBot opens no logging network connection. It needs no `LOGSTASH_HOST`, `LOGSTASH_PORT`, or Logstash credentials. The deployment collector owns forwarding, retention, access control, and UTF-8 one-JSON-object-per-line parsing. Preserve `@timestamp`, `schema_version`, and correlation fields; do not merge multiline stderr into RagBot JSON. Disable Uvicorn access logging in deployment so it cannot duplicate access events or expose URL query strings. Keep Uvicorn startup/error stderr available.

## Production settings

| Variable | Recommended value | Purpose |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Application threshold. |
| `LOG_FORMAT` | `json` | Required application format. |
| `LOG_SERVICE_NAME` | `ragbot` | Stable service field. |
| `LOG_ENVIRONMENT` | `production` | Log environment metadata. |
| `LOG_BODY_MAX_BYTES` | `32768` | Per-side eligible body capture limit. |
| `LOG_REQUEST_BODY` | `true` | Capture eligible request JSON/text. |
| `LOG_RESPONSE_BODY` | `true` | Capture eligible response JSON/text. |
| `LOG_PII_REDACTION` | `true` | Mandatory redaction policy. |
| `LOG_PII_HMAC_SECRET` | unset | Optional; national codes become `[REDACTED]` by default. |

No extra logging secret is needed for normal deployment. Leave `LOG_PII_HMAC_SECRET` unset and national codes are logged as `[REDACTED]`. If operators specifically need to recognize repeated national codes without seeing the original values, configure this optional dedicated key through the secret manager: the same code then produces the same `pii_...` label. Use the same dedicated key across replicas only when those labels must match. Never commit or log the key, and never reuse `WEB_SESSION_SECRET`. All tracked env references show this setting as a comment, not an active placeholder.

## Contract and privacy

Schema version is `1.0`. Eligible HTTP transactions emit `request_received` and `response_completed` with one RagBot-generated `request_id`; a valid inbound `X-Request-Id` is retained separately as `upstream_request_id`. The response `X-Request-Id` contains the RagBot ID. Detached mass-answer records use `operation_id` and `parent_request_id` with `request_id=null`; queued, started, and one terminal event identify a job without its content. The final HTTP event includes total and existing stage durations.

The central sanitizer redacts credential fields, browser/customer identity fields, phone and email fields, and banking identifiers in free text. National-code fields use a bounded HMAC pseudonym when configured. JSON/text bodies are bounded and sanitized before enqueue, then defensively sanitized at formatting. Multipart, file, binary, CSV/XLSX, PDF/image, and event-stream bodies are metadata only. Truncated bodies record size and omission metadata. Avoid sending secrets in unrelated field names: pattern matching is defense in depth, not a data classification guarantee.

## Health and alerts

The existing authorized `GET /api/metrics/admission` response includes `logging.queue_capacity`, `queue_depth`, `overflow_count`, `stdout_write_errors`, and `listener_alive`. Preserve its authorization policy. Alert on any overflow or stdout write error, a dead listener, sustained queue depth near capacity, and increased response error rate. The bounded queue normally enqueues without blocking; only actual saturation uses a synchronous safe stdout fallback, which can increase latency. Operations should monitor collector health separately from RagBot.

## Rollback

Revert to the pre-logging application release if needed. Logging adds no database schema and needs no database rollback. Keep collector routing aligned with the released application's stdout contract.
