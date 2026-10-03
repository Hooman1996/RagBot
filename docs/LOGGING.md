# RagBot structured logging

## Contract and architecture

RagBot emits one UTF-8 JSON object per line to stdout. It does not connect to Logstash.

```text
RagBot -> JSON stdout -> infrastructure collector -> Logstash
```

Production infrastructure owns stdout collection, forwarding, retention, and access controls. The application uses only Python standard library logging, a bounded in-process queue, and one listener thread. There is no logging network client.

Schema `1.0` reserves these top-level fields: `@timestamp` (UTC ISO-8601), `schema_version`, `service`, `environment`, `event`, `level`, `request_id`, `upstream_request_id`, and `process.pid`. Structured event attributes live under `data`. The application sets event names; client input does not set top-level field names. Existing `request_complete` and admission events use this contract in Stage 1. Stage 2 will add separate `request_received` and `response_completed` events with shared correlation and sanitized bodies. The completion event will include start and completion timestamps, total duration, and existing stage durations.

## Correlation

The existing `RequestTrace` ContextVar supplies request ID to the logger before enqueueing. This is safe across asyncio tasks. Stage 1 preserves the current ingress and `X-Request-Id` response behavior: a syntactically valid incoming header can still become `RequestTrace.request_id`. New helpers create a server-owned opaque ID and validate a separate bounded `upstream_request_id`. Stage 2 will switch middleware to those helpers while preserving response header behavior. No request ID parameters are added to domain services.

## Sanitization policy

All structured event data passes through one recursive sanitizer. It copies dictionaries/lists/tuples, caps nesting and item counts, normalizes unsafe values, and never emits raw bytes, exceptions, or Python repr strings. Secret fields (passwords, password hashes, auth headers, cookies, CSRF values, tokens, API keys, and secrets) become `[REDACTED]`, case insensitively. The HMAC secret itself is scrubbed if found in text. Ordinary legacy logging messages are withheld because interpolated arguments and exception text might contain customer data; event name, level, logger name, request ID, and exception type remain available. Convert valuable legacy messages to reviewed structured events over later stages.

National-code fields use an HMAC-SHA256 pseudonym with a `pii_` prefix and 24 hexadecimal characters when `LOG_PII_HMAC_SECRET` is set. The same code and secret produce the same pseudonym. The key is dedicated to logging and must never be `WEB_SESSION_SECRET`. Without the key, national codes are `[REDACTED]`. Phone, mobile, and email fields are always redacted. `LOG_PII_REDACTION=false` is rejected at startup.

Free text is scrubbed using precompiled, bounded patterns for likely valid Iranian national codes, Iranian mobile numbers, email addresses, Iranian card numbers passing Luhn, Sheba/IBAN-like values, and bearer/JWT-like tokens. Text is capped before regex processing. Validation limits false matches but cannot identify every secret or PII pattern; clients of the structured API must avoid adding raw sensitive material under unrelated field names.

Binary data is represented by `binary_omitted` and `size_bytes`; upload bytes and base64 payloads are never logged. Stage 2 body capture must read only up to `LOG_BODY_MAX_BYTES`, record `body_truncated` and `original_size_bytes` when available from the bounded read or transport metadata, and log upload metadata such as filename, content type, and size. It must never buffer a streaming response for logging.

## Queue and latency

The queue holds at most 4096 events and has one listener thread. Normal request code only prepares a small log record and uses a nonblocking enqueue; JSON serialization, sanitization, stdout writes, and stdout flushes occur on the listener. On queue saturation, the handler increments `overflow_count` and writes the event synchronously to stdout so it is not silently dropped. Saturation can therefore increase request latency. `app.state.logging_runtime.handler.overflow_count` exposes the overflow counter, and `stream_handler.write_errors` exposes stdout write failures. Stdout failures are swallowed by logging and cannot change RAG behavior; the infrastructure must monitor its own collection health. Shutdown drains the queue before stopping the listener. No network call is made by logging.

Run `python benchmarks/logging_overhead.py` for a repeatable local comparison of legacy JSON preparation against sanitization plus enqueue under a 5,000-event burst. The two paths cover different work and neither includes full HTTP request processing; this is a micro-benchmark, not an end-to-end latency claim. A later stage will compare full RagBot request latency under concurrency before and after logging.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Root application log threshold. |
| `LOG_FORMAT` | `json` | Only supported format. |
| `LOG_SERVICE_NAME` | `ragbot` | Stable service identifier. |
| `ENVIRONMENT` | `unknown` | Deployment environment field. |
| `LOG_BODY_MAX_BYTES` | `32768` | Maximum body text for future capture. |
| `LOG_REQUEST_BODY` | `true` | Future request body capture switch. |
| `LOG_RESPONSE_BODY` | `true` | Future response body capture switch. |
| `LOG_PII_REDACTION` | `true` | Mandatory safety setting. |
| `LOG_PII_HMAC_SECRET` | unset | Dedicated pseudonymization key; unset means redaction. |

Production must generate and store `LOG_PII_HMAC_SECRET` through its deployment secret-management mechanism. Never commit a real value. The staging reference `.env.recommended.rtx5880-staging` was already deleted in the working tree before Stage 1 and remains untouched to preserve unrelated work.

## Stage boundary

Stage 1 implements schema, configuration, sanitizer, pseudonymization, free-text scrubbing, queue-based JSON stdout emitter, request-context injection, and migration of existing trace/admission events. It does not capture HTTP request/response bodies or change endpoint behavior. Stage 2 integrates two transaction events and trusted ingress IDs. Later stages audit all application log producers and validate performance and answer quality.
