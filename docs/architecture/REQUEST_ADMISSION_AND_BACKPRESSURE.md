# Request admission and backpressure

## Purpose

Request admission prevents more expensive answer pipelines from entering one
FastAPI worker than its downstream resources can safely handle. It is a safety
boundary, not a throughput generator.

The current staging baseline is one FastAPI worker with capacity 50. Each
worker has its own independent limiter. If an operator starts two workers, the
host can admit up to 100 pipelines, even though each worker still reports a
capacity of 50. That multiplication also applies to blocking and Qdrant limits
and to outbound HTTP pools.

## Lifecycle

```text
request_received
  -> cheap HTTP/Pydantic validation
  -> admission_wait_start
     -> acquired: enter expensive pipeline
     -> timeout: HTTP 503 / SERVICE_BUSY
  -> pipeline and required persistence
  -> response object built
  -> admission_release
  -> FastAPI serialization and network return
```

The limiter must acquire with a bounded timeout, record ownership only after a
successful acquire, and release exactly once in `finally`. Cancellation before
acquisition owns no permit. Cancellation after acquisition still releases the
permit.

`REQUEST_ADMISSION_TIMEOUT_SECONDS` limits only queue waiting.
`APPLICATION_REQUEST_TIMEOUT_SECONDS` limits the complete mobile request,
including admission. An admission timeout is an overload response, while an
application timeout means admitted work exceeded the endpoint deadline.

Increasing the queue timeout cannot increase GPU, database, TEI, Qdrant, or
vLLM throughput. It only lets requests wait longer and may increase p95/p99.

## Nested limits

```text
outer request admission (50 per worker)
  +-- blocking runner (16 per worker)
  |     +-- PostgreSQL connection creation/query
  |     +-- normalization, BM25, CPU classification
  |     `-- synchronous Qdrant SDK execution
  +-- per-session lock (1 for the same internal session)
  +-- Qdrant admission (8 per worker)
  +-- TEI HTTP pool (64) -> TEI server queue
  `-- vLLM HTTP pool (64) -> vLLM scheduler/GPU queue
```

An admitted request retains its outer permit while waiting for every inner
resource. For example, 50 outer requests can be admitted while only eight are
inside Qdrant. The other requests are not idle from the admission system's
perspective: they are holding scarce outer capacity. This is permit hoarding,
but it is sometimes necessary to bound total in-flight state. Measure inner
wait before changing a limit.

## Expected overload behavior

Assuming one worker, capacity 50, and a 12-second admission timeout:

| Arrival | Expected behavior |
|---|---|
| 50 simultaneous | Up to 50 acquire immediately. No request should wait on outer admission. Inner queues can still add latency. |
| 75 simultaneous | Up to 50 acquire; about 25 wait. Every permit released before a waiter's individual 12-second deadline can be reused. Remaining waiters receive 503 `SERVICE_BUSY`. |
| 100 simultaneous | Up to 50 acquire; about 50 wait. Waiters should progressively acquire released permits. A blanket 50 timeouts is valid only if no outer permit becomes available to those waiters before their deadlines, or if arrival/measurement did not match this model. |
| 100 at 10 requests/s | Admission depends on service throughput. If completion rate keeps pace, most requests may acquire immediately; otherwise a queue develops. |

Strict FIFO fairness is not part of `asyncio.Semaphore`'s public contract.
Instrumentation may report ordering, but application correctness must not
assume request submission order equals admission order.

## Permit lifetime

For the mobile answer route, the permit begins before user/session database
work and ends after answer generation, agent-state persistence, assistant
message persistence, related-question selection, and response-object creation.
It ends before FastAPI response validation/serialization and socket transfer.

“Answer generation finished” is therefore earlier than “permit released.” A
model timing, graph timing, or answering-service timing must never be presented
as permit-hold time.

## Error semantics

| Failure | HTTP | Stable code | Meaning |
|---|---:|---|---|
| Admission timeout | 503 | `SERVICE_BUSY` | No permit was acquired before the queue deadline |
| Application deadline | 504 | `DEPENDENCY_TIMEOUT` | Total endpoint deadline expired |
| Client read timeout | No server HTTP response required | client classification | Client stopped waiting; server cancellation/work continuation must be measured |
| HTTP pool timeout | Normally dependency error | dependency-specific classification | No outbound connection became available in time |

Responses should carry a sanitized request ID plus admission wait and
permit-hold timing headers. Logs must not contain query text, answers,
credentials, national codes, session IDs, or customer data.

## Operational rules

- Treat all limits as per worker unless backed by a distributed coordinator.
- Keep one worker until aggregate multi-worker downstream capacity is measured.
- Do not raise outer capacity merely to avoid 503 responses.
- Do not raise Qdrant or blocking concurrency without measured queue wait and
  healthy downstream CPU, memory, connections, and latency.
- Do not extend admission beyond the user latency objective merely to convert a
  fast overload response into a slow success.
- Use a temporary second FastAPI process for candidate tests when safe. Never
  replace the active worker without explicit operator approval.
