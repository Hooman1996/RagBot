# Mobile talk load-test prerequisites

Date: 2026-07-28

Repository: `/root/projects/faq`

Source revision: `1ee2c1380b4b4fde4875b60661766e7b5f32ccd8`
on branch `main`; the worktree was clean at the start of this audit.

## Decision

Do not write or run the load tester yet.

The request contract and limiter behavior are statically verified below, but
live staging identity, effective process environment, worker count, deployed
revision, authentication/network controls, database isolation, cleanup
authority, and downstream cancellation behavior remain unverified. In
addition, `POST /api/mobile/v1/talk` is state-changing: it can create a user,
create a chat session, insert a query containing the prompt, store the answer,
and update session metadata. Those writes can be only partially complete after
a timeout ([mobile_api.py:103-169](../../mobile_api.py#L103),
[database.py:203-245](../../new_architecture/app/services/history/database.py#L203),
[database.py:641-658](../../new_architecture/app/services/history/database.py#L641),
[database.py:455-504](../../new_architecture/app/services/history/database.py#L455)).

No live API request, database query, TEI/vLLM inference, load test, or
production operation was performed in this preparation task.

## Audit context and limits

| Item | Finding and evidence |
|---|---|
| Target | FastAPI `POST /api/mobile/v1/talk` ([mobile_api.py:10](../../mobile_api.py#L10), [mobile_api.py:77-93](../../mobile_api.py#L77)) |
| External deadline | 50 seconds ([AGENTS.md:7](../../AGENTS.md#L7), [mobile_api.py:11](../../mobile_api.py#L11)) |
| Staging hardware | One NVIDIA RTX 5880 Ada Generation GPU with 48 GB VRAM ([AGENTS.md:8](../../AGENTS.md#L8)) |
| Production hardware | Two NVIDIA L4 GPUs with 24 GB each; staging results must not be presented as production results ([AGENTS.md:9](../../AGENTS.md#L9)) |
| Model serving | vLLM for generation and TEI for embedding/reranking ([AGENTS.md:10-15](../../AGENTS.md#L10)) |
| Deployed staging identity/revision | Unknown; repository revision alone does not establish the deployed revision |
| Effective runtime configuration and worker count | Unknown; direct execution declares no explicit worker count, while the limiter is created per process ([main.py:208-218](../../main.py#L208), [main.py:1448-1452](../../main.py#L1448)) |
| Model identifiers and vLLM version | Unknown; no live service was contacted |
| TEI evidence available in the repository | Stored runtime evidence identifies TEI image `cuda-1.9`, embedding port 7997, reranking port 7998, and their model paths; it is historical evidence, not proof of current deployment state ([docker-ps.txt:1-3](runtime/docker-ps.txt#L1)) |
| Dataset, concurrency, arrival pattern, warm-up, duration, sample count, pass criteria | Not yet defined; they must be fixed after the safety gates in this document are satisfied |
| Cold/warm mode, background workload, GPU sharing | Unknown; no benchmark was run |

## 1. Exact URL path

The full path component is:

```text
POST /api/mobile/v1/talk
```

The router contributes `/api/mobile`, the operation contributes `/v1/talk`,
and `main.py` includes the router without another prefix
([mobile_api.py:10](../../mobile_api.py#L10),
[mobile_api.py:77](../../mobile_api.py#L77),
[main.py:414-416](../../main.py#L414)). The staging scheme, hostname, port, and
any reverse-proxy prefix are not present in the route definition and remain
unknown.

## 2. Complete `TalkRequest` schema

The JSON request body is:

| Field | Pydantic type | Required | Default | Repository validation |
|---|---|---:|---|---|
| `session_id` | `str` | Yes | None | Must be present and truthy; no UUID parser, regex, or length validator |
| `query` | `str` | Yes | None | Must be present and truthy; whitespace-only text passes the explicit check |
| `national_code` | `str` | Yes | None | Must be present and truthy; no digit, checksum, regex, or length validator |
| `documents` | `List[str]` | No | `["General_FAQ"]` | No allow-list, item-format, list-size, or non-empty validation |

The model is declared without custom validators or model configuration
([mobile_api.py:22-26](../../mobile_api.py#L22)). The handler adds only a
truthiness check for the first three fields
([mobile_api.py:96-98](../../mobile_api.py#L96)). Missing fields or incompatible
JSON types are handled by FastAPI/Pydantic before the handler; empty strings
reach the handler and produce HTTP 400. No request-size limit is defined on
this route in the inspected application code.

`documents` controls PostgreSQL chunk selection for every supplied title
([rag_utils.py:44-50](../../utils/rag_utils.py#L44),
[database.py:587-594](../../new_architecture/app/services/history/database.py#L587)).
Only its first item controls prompt category and related-question behavior
([mobile_api.py:173-189](../../mobile_api.py#L173),
[agent_service.py:65-69](../../agent_service.py#L65)). A load tester must
therefore send a fixed, reviewed document list rather than arbitrary fuzzed
titles, except for the controlled empty-retrieval case described below.

## 3. Required headers and authentication

The operation requires a JSON body, so the client should send:

```text
Content-Type: application/json
```

No `Authorization` header, API key, cookie, FastAPI `Depends`, router-level
dependency, or authentication parameter protects this route. The source
explicitly labels these gateway endpoints “No Auth Required,” the router has
only a prefix and tags, and the handler accepts only the body plus `Request`
([mobile_api.py:10](../../mobile_api.py#L10),
[mobile_api.py:73-78](../../mobile_api.py#L73)). Although an
`OAuth2PasswordBearer` object exists for other application paths, it is not
attached to the mobile router when the router is included
([main.py:403-416](../../main.py#L403)).

`X-Request-Id` is optional. The application does not generate one. If supplied,
it is copied into the banking-shaped body for `ServiceError` responses; if
absent, the body uses `unknown_request`
([main.py:438-455](../../main.py#L438)). It is not returned on a successful
`TalkResponse`.

This static finding does not prove that a staging reverse proxy or API gateway
has no external authentication or required headers. Those controls must be
verified against the deployed staging route before a client is implemented.

## 4. Complete `TalkResponse` schema

Successful responses are validated against six required fields:

| Field | Type | Meaning in this implementation |
|---|---|---|
| `query_id` | `str` | PostgreSQL query-row integer ID converted to text, or `"unknown"` if the assistant write unexpectedly returns no row |
| `session_id` | `str` | The original caller-supplied mobile session ID, not the internal PostgreSQL session primary key |
| `query` | `str` | The original caller-supplied query |
| `answer` | `str` | Cleaned assistant answer |
| `related_questions` | `List[Dict[str, str]]` | FAQ-related question/answer dictionaries after optional reranking |
| `feedback_needed` | `bool` | Agent-state feedback flag |

The response model is defined at
[mobile_api.py:29-35](../../mobile_api.py#L29), and the returned values are
assembled at [mobile_api.py:193-202](../../mobile_api.py#L193). The assistant
message updates the same pending query row and returns its ID
([database.py:474-504](../../new_architecture/app/services/history/database.py#L474)).
The normal success status is FastAPI's default HTTP 200 because the route does
not declare another status code ([mobile_api.py:77](../../mobile_api.py#L77)).

## 5. Session-ID format and validation

At the API boundary, `session_id` is merely a required, truthy Python string;
there is no UUID validation, regex, canonicalization, or explicit length check
([mobile_api.py:22-26](../../mobile_api.py#L22),
[mobile_api.py:96-98](../../mobile_api.py#L96)). `resolve_mobile_session`
rejects only a falsey value and passes the string to the database
([database.py:774-780](../../new_architecture/app/services/history/database.py#L774)).

The persistence model and bootstrap DDL use a unique `VARCHAR(36)` for the
session UUID ([chat_session.py:27-28](../../new_architecture/app/models/chat_session.py#L27),
[database.py:108-112](../../new_architecture/app/services/history/database.py#L108)).
Consequently, a canonical 36-character UUID is the safest compatible format,
but UUID syntax is not enforced by this endpoint. An oversized value can fail
only at PostgreSQL insertion rather than at request validation.

There is also an ownership defect relevant to load-test safety:
`get_or_create_mobile_session(user_id, session_uuid)` first looks up the UUID
globally and returns the existing row without verifying that its `user_id`
matches the caller ([database.py:641-658](../../new_architecture/app/services/history/database.py#L641)).
A collision with any existing session UUID can therefore attach the request
path to another user's session.

## 6. National-code format and validation

At the API boundary, `national_code` is also only a required, truthy string.
There is no digits-only rule, ten-digit rule, Iranian national-code checksum,
normalization, or Pydantic field constraint
([mobile_api.py:22-26](../../mobile_api.py#L22),
[mobile_api.py:96-98](../../mobile_api.py#L96)).

The ORM model describes the database column as unique `String(20)`
([user.py:43-44](../../new_architecture/app/models/user.py#L43)). Provisioning
uses the exact string for lookup and for placeholder username/email generation
([database.py:203-234](../../new_architecture/app/services/history/database.py#L203)).
The application bootstrap DDL shown in this checkout does not itself declare a
`national_code` column in its `users` table definition
([database.py:85-105](../../new_architecture/app/services/history/database.py#L85));
the deployed schema therefore has an unverified migration/schema prerequisite.

## 7. Must identifiers exist in PostgreSQL first?

No.

- A missing national code is JIT-provisioned as a persistent user
  ([database.py:203-245](../../new_architecture/app/services/history/database.py#L203)).
- A missing mobile session UUID is inserted as a persistent chat session
  ([database.py:641-658](../../new_architecture/app/services/history/database.py#L641)).
- The endpoint invokes those operations before classification and inference
  ([mobile_api.py:103-122](../../mobile_api.py#L103)).

Existing identifiers are reused. Because national codes are globally unique
and sessions are globally looked up by UUID, test identifiers must be proven
absent before the run.

## 8. Persistent records created by a request

Yes. Depending on prior state and where a failure occurs, one call can:

1. Insert a `users` row for a new national code
   ([database.py:216-237](../../new_architecture/app/services/history/database.py#L216)).
2. Insert a `chat_sessions` row for a new mobile UUID
   ([database.py:641-658](../../new_architecture/app/services/history/database.py#L641)).
3. Insert a `queries` row containing the original prompt with status `pending`
   and increment the session query count
   ([database.py:349-386](../../new_architecture/app/services/history/database.py#L349)).
4. Store the answer in that query row, mark it completed, and update session
   activity ([database.py:474-504](../../new_architecture/app/services/history/database.py#L474)).
5. Store the agent state, including recent synthetic message content, in
   `chat_sessions.meta_data`
   ([agent_service.py:159-169](../../agent_service.py#L159)).

The user query is inserted before the agent graph runs
([mobile_api.py:135-153](../../mobile_api.py#L135)). A timeout or downstream
failure can therefore leave a persistent pending query without an answer.
User/session creation can remain even if the timeout happens earlier.

## 9. Cleanup requirement

Cleanup is required for every staging test run, including failed and timed-out
runs. There is no automatic rollback spanning user provisioning, session
creation, query insertion, inference, response storage, and metadata storage:
each `DatabaseManager._execute` call opens its own connection and commits
independently ([database.py:44-79](../../new_architecture/app/services/history/database.py#L44)).

There is an unauthenticated session-delete endpoint, but it expects the
internal integer session ID, while `TalkResponse.session_id` returns the
external UUID ([main.py:744-754](../../main.py#L744),
[mobile_api.py:195-202](../../mobile_api.py#L195)). Deleting a chat session
cascades to its query rows
([database.py:129-156](../../new_architecture/app/services/history/database.py#L129),
[database.py:339-343](../../new_architecture/app/services/history/database.py#L339)),
but no user-delete API exists in the inspected path. Cleanup should therefore
be an authorized, run-scoped staging database procedure that removes the
dedicated synthetic users after verifying their namespace; user deletion is
expected to cascade to sessions and queries under the declared foreign keys
([database.py:108-134](../../new_architecture/app/services/history/database.py#L108)).
The operator must verify the deployed schema and row counts before deletion.

## 10-12. Request limiter creation, capacity, and configuration

The limiter is created during FastAPI lifespan as:

```python
request_limiter = asyncio.Semaphore(REQUEST_CONCURRENCY_LIMIT)
```

It is then assigned to `app.state.request_limiter`, which the mobile handler
passes to `run_with_limit`
([main.py:208-218](../../main.py#L208),
[main.py:327-334](../../main.py#L327),
[mobile_api.py:89-93](../../mobile_api.py#L89)).

The repository-configured default capacity is **32 admitted AI requests per
application process**. `REQUEST_CONCURRENCY_LIMIT` is read from the process
environment with default `"32"`, and `env.example` also declares 32
([main.py:77-82](../../main.py#L77),
[env.example:66-68](../../env.example#L66)). It is configurable at process
startup with `REQUEST_CONCURRENCY_LIMIT`; it is not dynamically reloadable in
the shown code.

The same semaphore is used by the web query, mobile talk, and mass-answer
paths, so 32 is a shared per-process budget rather than 32 dedicated mobile
slots ([main.py:542-554](../../main.py#L542),
[mobile_api.py:89-93](../../mobile_api.py#L89),
[main.py:1006-1018](../../main.py#L1006)).

This is a per-process semaphore, not a cluster-wide limit. Total possible
admission is therefore approximately `worker_processes × effective_limit`.
The live staging worker count and externally injected environment are unknown,
so 32 is the verified source/default capacity, not a verified live aggregate
capacity. Those values must be captured from the deployed process before
choosing test concurrency.

The mobile acquire timeout is hard-coded to **2.0 seconds**
([mobile_api.py:89-93](../../mobile_api.py#L89)). Although
`REQUEST_ADMISSION_TIMEOUT_SECONDS` exists and is configurable for other
application endpoints, this mobile route does not use it
([main.py:77-82](../../main.py#L77)).

Admission wait happens before `operation()` starts, so it is outside the
50-second `asyncio.wait_for` interval
([concurrency.py:99-117](../../utils/concurrency.py#L99),
[mobile_api.py:79-93](../../mobile_api.py#L79)). Nominal boundary time can thus
approach 52 seconds, and cancellation cleanup can extend it further.

## 13. Two-second acquisition failure

If semaphore acquisition exceeds two seconds, `asyncio.wait_for` raises
`TimeoutError`; `run_with_limit` translates it to
`ServiceOverloadedError("Request concurrency limit reached")`
([concurrency.py:99-112](../../utils/concurrency.py#L99)).
`ServiceOverloadedError` has stable code `SERVICE_BUSY` and HTTP status 503
([service_errors.py:28-30](../../utils/service_errors.py#L28)). The global
`ServiceError` handler returns that status in the banking-shaped JSON error
body ([main.py:438-455](../../main.py#L438)).

Therefore the verified application result is **HTTP 503**, not 429.

## 14. Fifty-second execution timeout

The endpoint wraps `_gateway_talk` in `asyncio.wait_for(..., timeout=50.0)`.
On expiry it raises
`ServiceTimeoutError("AI request exceeded the 50-second deadline")`
([mobile_api.py:77-87](../../mobile_api.py#L77)).
`ServiceTimeoutError` maps to **HTTP 504** with stable code
`DEPENDENCY_TIMEOUT`
([service_errors.py:13-15](../../utils/service_errors.py#L13),
[main.py:438-455](../../main.py#L438)).

The 50 seconds cover only work after admission. Also, `asyncio.wait_for` waits
for cancellation to finish; a transactional worker call explicitly waits for
its thread to commit/rollback and clean up before re-raising cancellation
([concurrency.py:18-22](../../utils/concurrency.py#L18),
[concurrency.py:71-88](../../utils/concurrency.py#L71)). The observed response
can consequently exceed both 50 seconds of execution and roughly 52 seconds
including admission.

## 15. Cancellation propagation to TEI and vLLM

Static conclusion: cancellation reaches the **awaiting client coroutines**, but
the repository does not prove that it aborts already-started server-side GPU
work.

- The outer `asyncio.wait_for` cancels `_gateway_talk`, whose explicit
  `CancelledError` branch re-raises cancellation
  ([mobile_api.py:81-87](../../mobile_api.py#L81),
  [mobile_api.py:203-206](../../mobile_api.py#L203)).
- Agent processing awaits LangGraph directly
  ([agent_service.py:135-140](../../agent_service.py#L135)).
- TEI embedding and reranking use awaited `httpx.AsyncClient.post` calls and do
  not catch `CancelledError`
  ([persian_hybrid_search.py:280-300](../../utils/persian_hybrid_search.py#L280),
  [persian_hybrid_search.py:563-588](../../utils/persian_hybrid_search.py#L563)).
- vLLM generation uses an awaited non-streaming `AsyncOpenAI` completion and
  likewise does not catch `CancelledError`
  ([RagSystem.py:151-160](../../utils/RagSystem.py#L151),
  [RagSystem.py:326-343](../../utils/RagSystem.py#L326)).

There is no explicit TEI cancellation endpoint, vLLM abort request, downstream
request ID, or disconnect-to-server verification in this path. Whether TEI or
vLLM stops queued/running inference after the client socket is cancelled is
therefore **unknown and requires a separately authorized staging experiment
correlated with actual server metrics**.

Cancellation does not stop synchronous work already running in a thread. The
bounded runner shields that work; read-only work can continue in the
background, and selected writes wait for completion
([concurrency.py:15-22](../../utils/concurrency.py#L15),
[concurrency.py:56-88](../../utils/concurrency.py#L56)). User provisioning does
not request wait-on-cancel, so its worker may finish in the background after
the request has observed cancellation
([mobile_api.py:103-106](../../mobile_api.py#L103)). Session resolution,
user-message insertion, and assistant-message storage explicitly wait for
their workers to complete before cancellation is re-raised
([mobile_api.py:113-118](../../mobile_api.py#L113),
[mobile_api.py:135-165](../../mobile_api.py#L135)). The synchronous Qdrant
request also runs in that worker mechanism and cannot be forcibly cancelled
once started
([persian_hybrid_search.py:435-465](../../utils/persian_hybrid_search.py#L435)).

## 16. Request IDs and stage timings

The success schema exposes neither a request ID nor timings
([mobile_api.py:29-35](../../mobile_api.py#L29)). Service-error bodies merely
echo caller-provided `X-Request-Id`, falling back to `unknown_request`; the
application does not create a correlation ID
([main.py:438-455](../../main.py#L438)).

No endpoint stage timers or monotonic duration measurements exist in the
traced mobile path. The query table has a `response_time` column, but the
assistant-message path calls `update_query_response` without a response-time
argument, so it remains the default `None`
([database.py:388-430](../../new_architecture/app/services/history/database.py#L388),
[database.py:474-498](../../new_architecture/app/services/history/database.py#L474)).
Created/updated timestamps are persistence timestamps, not decomposed request,
queue, retrieval, TEI, Qdrant, or vLLM timings.

A future load client may send a sanitized, unique `X-Request-Id`, but useful
success-path correlation and stage attribution require separately authorized
instrumentation or server-side telemetry. It must never put national codes,
session UUIDs, prompts, credentials, or banking data into the request ID.

## 17. Staging safety assessment

The endpoint is **not safe for an unrestricted test on a shared staging
environment**. It has no application-level authentication, creates persistent
records, can leave partial records after timeout, accepts unvalidated identity
strings, has a cross-user session-UUID collision risk, and exercises shared
TEI/vLLM resources
([mobile_api.py:73-78](../../mobile_api.py#L73),
[mobile_api.py:103-169](../../mobile_api.py#L103),
[database.py:641-658](../../new_architecture/app/services/history/database.py#L641),
[AGENTS.md:8-15](../../AGENTS.md#L8)).

It is conditionally testable only after all of these gates are met:

1. Explicit authorization to generate state-changing staging traffic; never
   target production ([AGENTS.md:17-23](../../AGENTS.md#L17)).
2. Confirm deployed revision, base URL/proxy prefix, external gateway
   authentication, application worker count, effective limiter capacity,
   service health, model versions, and known background workloads.
3. Use a dedicated staging database or an operator-approved synthetic
   namespace, with preflight absence checks and a rehearsed cleanup query.
4. Use only fixed synthetic prompts and document titles; never use customer
   data, valid-looking identity data, authentication values, or banking data
   ([AGENTS.md:19-23](../../AGENTS.md#L19)).
5. Start with a single request, verify expected rows and cleanup, then use a
   low closed-loop concurrency below the verified per-process capacity. Define
   stop conditions for elevated error/timeout rate, queue growth, GPU pressure,
   or impact on other staging users.
6. Record only sanitized IDs, status, monotonic durations, byte/token counts,
   and aggregate metrics. Do not record request/response text.

## 18. Candidate scenario prompts

These are static, synthetic workload candidates. They are not yet validated
against the deployed classifier, Qdrant collection, model version, or output
length distribution, so a single-request staging calibration is required
before they become benchmark fixtures.

| Scenario | Request setup and synthetic prompt | What it exercises | Evidence and limitation |
|---|---|---|---|
| Chitchat | New session; `documents=["General_FAQ"]`; `سلام، خوبی؟` | Intent-classifier TEI embedding, local chitchat classification, then vLLM without retrieval | The classifier source uses this exact utterance as its chitchat example ([intent_classifier.py:89-106](../../intent_classifier.py#L89)); chitchat bypasses retrieval but still calls vLLM ([agent_graph.py:182-208](../../agent_graph.py#L182)). The deployed checkpoint must confirm routing. |
| Standalone FAQ | New session; `documents=["General_FAQ"]`; `آیا امکان افتتاح حساب مشترک به صورت غیرحضوری وجود دارد؟` | One-turn classification, retrieval, and concise FAQ answer | The exact question and one-line source answer exist in the checked-in corpus ([General_FAQ_147.txt:1-3](../../data_insertion_chunks/CHUNKS/General_FAQ/General_FAQ_147.txt#L1)). Deployed index parity remains unverified. |
| Follow-up FAQ | Same session, sequentially send `سقف انتقال وجه روزانه از طریق خدمات بانکی چقدر است؟`, then `سقف انتقال از طریق پل چقدر است؟` | Persisted state/history read plus vLLM query rewrite before the second turn, followed by normal FAQ retrieval | Non-chitchat history is read and rewritten when present ([mobile_api.py:121-133](../../mobile_api.py#L121), [rewriting.py:244-251](../../new_architecture/app/services/history/rewriting.py#L244)); the source FAQ explicitly covers the overall and پل limits ([General_FAQ_202.txt:1-3](../../data_insertion_chunks/CHUNKS/General_FAQ/General_FAQ_202.txt#L1)). Follow-up requests for one session must be sequential because agent state is guarded by a per-session lock ([agent_service.py:36-50](../../agent_service.py#L36)). |
| Retrieval hit | New session; `documents=["General_FAQ"]`; `سقف انتقال وجه روزانه از طریق خدمات بانکی چقدر است؟` | A high-confidence lexical/semantic match in the reviewed corpus | The exact question exists in the corpus ([General_FAQ_202.txt:1-3](../../data_insertion_chunks/CHUNKS/General_FAQ/General_FAQ_202.txt#L1)); search performs BM25 plus semantic retrieval and returns the top candidates ([persian_hybrid_search.py:500-552](../../utils/persian_hybrid_search.py#L500)). Verify deployed index parity and retrieved IDs without storing content. |
| Deterministic empty retrieval | New session; `documents=["STAGING_LOADTEST_EMPTY_FAQ"]`; synthetic out-of-domain prompt such as `راهنمای گزینه آزمایشی ناموجود چیست؟` | PostgreSQL returns no chunks and the search path returns an empty list before TEI retrieval embedding/Qdrant; classification TEI and answer-generation vLLM still run | Document titles are not allow-listed ([mobile_api.py:22-26](../../mobile_api.py#L22)); chunk lookup filters by exact title ([database.py:587-594](../../new_architecture/app/services/history/database.py#L587)); empty chunks return immediately ([persian_hybrid_search.py:500-512](../../utils/persian_hybrid_search.py#L500)). Preflight must prove the sentinel title is absent. |
| Semantic retrieval miss under `General_FAQ` | No prompt can deterministically guarantee a literal zero-result miss | An out-of-domain query can test answer refusal, but not a true retrieval miss | Qdrant retrieval has no score threshold and contributes its nearest IDs whenever the collection/filter returns points ([persian_hybrid_search.py:435-465](../../utils/persian_hybrid_search.py#L435), [persian_hybrid_search.py:524-552](../../utils/persian_hybrid_search.py#L524)). Use the controlled nonexistent document title above for a true empty-context branch; treat out-of-domain refusal as a separate quality scenario. |
| Short answer | New session; exact standalone FAQ prompt above | Likely short source-grounded output | The source answer is one line ([General_FAQ_147.txt:1-3](../../data_insertion_chunks/CHUNKS/General_FAQ/General_FAQ_147.txt#L1)), and the general prompt asks for direct, non-bloated output ([RagSystem.py:286-315](../../utils/RagSystem.py#L286)). Output length is not guaranteed; calibrate and classify by measured completion tokens. |
| Long answer | New session; `شرایط افتتاح حساب جاری چیست و آیا این فرآیند به صورت غیرحضوری امکان پذیر است؟` | Likely multi-item source-grounded output | The source answer contains an introduction plus six listed requirements ([General_FAQ_153.txt:1-11](../../data_insertion_chunks/CHUNKS/General_FAQ/General_FAQ_153.txt#L1)). Generation permits up to 500 tokens for non-chitchat answers ([RagSystem.py:220-224](../../utils/RagSystem.py#L220), [RagSystem.py:326-333](../../utils/RagSystem.py#L326)), but there is no minimum; classify the fixture by observed completion-token range after calibration. |

Important path detail: the endpoint classifies the query once before history
rewriting, and the LangGraph classifies it again after the user query is
persisted ([mobile_api.py:121-153](../../mobile_api.py#L121),
[agent_graph.py:85-112](../../agent_graph.py#L85),
[agent_graph.py:301-335](../../agent_graph.py#L301)). Even chitchat therefore
performs TEI embedding classification twice; “bypasses retrieval” does not mean
“bypasses TEI.”

## Safe staging-only identity strategy

Do not generate random valid-looking ten-digit Iranian national codes. The
endpoint does not check their validity and will reuse any matching user row
([database.py:203-214](../../new_architecture/app/services/history/database.py#L203)).
A randomly generated valid-looking value could therefore identify a real
staging user, expose their session history to subsequent calls, or append test
records to their profile.

Preferred strategy:

1. Use an isolated staging database restored from no customer data.
2. Have the staging data owner reserve a nonnumeric, unmistakably synthetic
   national-code namespace of at most 20 characters, for example a fixed
   `stglt_` prefix plus a short run ID. Nonnumeric values work only because
   this endpoint has no format validator; verify that the external staging
   gateway does not reject them before implementation
   ([mobile_api.py:22-26](../../mobile_api.py#L22),
   [user.py:43-44](../../new_architecture/app/models/user.py#L43)).
3. Preflight in PostgreSQL that every planned national code is absent. Abort on
   any match.
4. Generate canonical UUIDv4 session IDs, record only a cryptographic hash or
   sanitized run-local alias in benchmark artifacts, and preflight that every
   UUID is absent. Abort on any match because session lookup is not
   user-scoped ([database.py:641-658](../../new_architecture/app/services/history/database.py#L641)).
5. Use one national code per virtual user and one UUID per conversation.
   Reuse a UUID only for deliberate sequential follow-up turns; do not send
   concurrent turns to one session because they serialize on the per-session
   lock ([agent_service.py:36-50](../../agent_service.py#L36)).
6. After the run, stop traffic, reconcile planned versus created synthetic
   users/sessions/queries, delete only the verified reserved namespace in one
   operator-controlled transaction, verify zero remaining rows, and retain
   aggregate metrics only. Foreign keys declare cascading session/query
   cleanup ([database.py:108-134](../../new_architecture/app/services/history/database.py#L108)).

If nonnumeric sentinel codes cannot pass the external gateway, the alternative
must be a formally reserved block of test identities owned by staging—not
locally generated checksum-valid codes. Without either isolation or a reserved
identity block, staging load testing is not approved by this audit.

## Static request trace for load-test planning

| Order | Operation | Sync/async and resource | Timeout/cancellation | Evidence |
|---:|---|---|---|---|
| 1 | FastAPI body validation; no endpoint auth dependency | Async ASGI/Pydantic | Framework validation before handler | [mobile_api.py:22-26](../../mobile_api.py#L22), [mobile_api.py:73-78](../../mobile_api.py#L73) |
| 2 | Acquire request admission slot | Async semaphore | 2 s; 503 `SERVICE_BUSY` | [mobile_api.py:89-93](../../mobile_api.py#L89), [concurrency.py:99-117](../../utils/concurrency.py#L99) |
| 3 | Start endpoint execution deadline | `asyncio.wait_for` | 50 s; cancellation then 504 | [mobile_api.py:79-87](../../mobile_api.py#L79) |
| 4 | Find or create user | Synchronous psycopg2 in bounded worker | Per-operation DB timeouts; write may persist on cancellation | [mobile_api.py:103-109](../../mobile_api.py#L103), [database.py:26-38](../../new_architecture/app/services/history/database.py#L26), [database.py:203-245](../../new_architecture/app/services/history/database.py#L203) |
| 5 | Find or create session UUID mapping | Synchronous psycopg2 in bounded worker | Waits for worker completion on cancellation | [mobile_api.py:111-120](../../mobile_api.py#L111), [database.py:641-658](../../new_architecture/app/services/history/database.py#L641) |
| 6 | First intent classification | Async TEI embed plus worker-thread Torch classification | TEI 15 s read timeout; native coroutine cancellation | [mobile_api.py:121-133](../../mobile_api.py#L121), [intent_classifier.py:186-196](../../intent_classifier.py#L186), [intent_classifier.py:202-237](../../intent_classifier.py#L202) |
| 7 | For non-chitchat, read history and conditionally rewrite | psycopg2 worker; optional async vLLM | vLLM 45 s read timeout; cancellation propagates to client coroutine | [mobile_api.py:123-133](../../mobile_api.py#L123), [rewriting.py:81-142](../../new_architecture/app/services/history/rewriting.py#L81), [rewriting.py:244-251](../../new_architecture/app/services/history/rewriting.py#L244) |
| 8 | Insert original user query | Synchronous psycopg2 in bounded worker | Waits for completion on cancellation | [mobile_api.py:135-145](../../mobile_api.py#L135), [database.py:349-386](../../new_architecture/app/services/history/database.py#L349) |
| 9 | Lock session; load session and agent metadata | Async lock plus psycopg2 workers | Same-session turns serialize | [agent_service.py:36-50](../../agent_service.py#L36), [agent_service.py:70-84](../../agent_service.py#L70) |
| 10 | Invoke graph and classify a second time | Async LangGraph, TEI, worker Torch | Outer deadline applies | [agent_service.py:135-140](../../agent_service.py#L135), [agent_graph.py:301-335](../../agent_graph.py#L301) |
| 11a | General path: fetch chunks, BM25, TEI embedding, Qdrant, optional TEI reranking | psycopg2/CPU/Qdrant workers plus async TEI | Dependency timeouts; sync workers cannot be forcibly stopped | [agent_graph.py:139-173](../../agent_graph.py#L139), [persian_hybrid_search.py:500-552](../../utils/persian_hybrid_search.py#L500), [persian_hybrid_search.py:563-588](../../utils/persian_hybrid_search.py#L563) |
| 11b | Chitchat path: skip retrieval and call vLLM | Async OpenAI-compatible HTTP | vLLM 45 s read timeout | [agent_graph.py:182-208](../../agent_graph.py#L182), [RagSystem.py:151-160](../../utils/RagSystem.py#L151) |
| 12 | Generate general answer through vLLM | Async OpenAI-compatible HTTP | vLLM 45 s read timeout | [agent_graph.py:167-173](../../agent_graph.py#L167), [RagSystem.py:326-333](../../utils/RagSystem.py#L326) |
| 13 | Persist trimmed agent state | Synchronous psycopg2 in bounded worker | Waits for completion on cancellation | [agent_service.py:159-169](../../agent_service.py#L159) |
| 14 | Store assistant answer and update activity | Synchronous psycopg2 in bounded worker | Waits for completion on cancellation | [mobile_api.py:157-165](../../mobile_api.py#L157), [database.py:474-504](../../new_architecture/app/services/history/database.py#L474) |
| 15 | Read metadata, optionally rerank related questions locally, serialize response | psycopg2/CPU workers then Pydantic response | Outer deadline applies | [mobile_api.py:167-202](../../mobile_api.py#L167) |

MinIO is initialized at application startup but does not appear in this traced
request path; the repository map identifies its startup role separately
([AGENTS.md:100-110](../../AGENTS.md#L100)). It should not be treated as a
mobile-talk critical-path load-test dependency.

## Preconditions to close before implementation

- Obtain explicit authorization for state-changing staging traffic.
- Verify staging base URL, proxy prefix, network/auth headers, deployed
  revision, process/worker count, and effective
  `REQUEST_CONCURRENCY_LIMIT`.
- Confirm that staging contains no customer-derived users, sessions, prompts,
  or banking data, or use a clean isolated database.
- Reserve the synthetic national-code namespace and rehearse preflight and
  cleanup with the staging data owner.
- Verify the planned session UUIDs and sentinel document title are absent.
- Run one request per scenario, without retaining prompt/answer content in
  measurement artifacts, to validate classifier route, deployed-index hit,
  empty retrieval, completion-token bands, persistence, and cleanup.
- Define the benchmark protocol and stop conditions, including workload mix,
  open/closed-loop arrival model, cold/warm policy, concurrency steps, duration,
  sample count, p50/p95/p99 validity, throughput, error/timeout limits, and GPU
  safety thresholds.
- Separately test whether client cancellation actually removes work from TEI
  and vLLM queues before relying on the 50-second timeout as a capacity safety
  mechanism.

## Verification performed

`python3 -m unittest tests.test_p2_concurrency` completed successfully with
8 tests. This isolated suite checks the bounded runner and the stable
503/504 service-error mappings, including the source-level mobile cancellation
and exception boundaries
([test_p2_concurrency.py:259-268](../../tests/test_p2_concurrency.py#L259)).
It does not validate the deployed staging environment, live limiter capacity,
PostgreSQL schema/data, endpoint authentication at the gateway, retrieval
results, model behavior, or downstream server-side cancellation.
