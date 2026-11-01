# Chat platform context and session binding (Step 1)

`CHATBOT_PLATFORM` accepts exactly `hibank`, `negahboom`, or `auto`. The default
when absent is `hibank`. Invalid values fail application startup. Restart an
instance after changing configuration.

For the shared development application at `localhost:7000`, set
`CHATBOT_PLATFORM=auto`. Hibank and NegahBoom may use the same PostgreSQL tables,
Qdrant collection, and MinIO bucket. No ingestion or storage migration is required
by this change. Production uses separate application instances and isolated
storage: configure each instance with `hibank` or `negahboom` respectively.
This change does not provision or modify production infrastructure.

## Resolution

The immutable `PlatformContext` is passed explicitly through answering, query
rewriting, and agent execution. The graph carries its stable `platform` ID.
There is no mutable per-request global platform selector.

Central ownership rules live in `platform_context.py`:

| Knowledge source | Owner | Document category |
| --- | --- | --- |
| `General_FAQ` | `hibank` | `FAQ` |
| `NegahBoom_FAQ` | `negahboom` | `FAQ` |
| Existing titles containing `قرارداد` | `hibank` | Existing contract category |
| Existing titles containing `ابلاغیه` | `hibank` | Existing circular category |

The local source inventory contains `General_FAQ`; the existing explicit contract
and circular title families come from `document_category.py`. Ownership never
uses that module's hash fallback. Register additional title owners centrally
before using them; unknown ownership fails closed. Available-title filtering
still runs through the existing database validator. Platform checks examine the
entire requested selection before filtering, so stale titles cannot conceal a
mixed-platform request. Both FAQ sources keep the existing FAQ prompt category
and related-question behavior.

An optional `X-Chatbot-Platform: hibank` or `X-Chatbot-Platform: negahboom` header
provides a signal without changing request bodies. Values are exact lowercase
IDs; empty values and `auto` are invalid headers. Document ownership, header,
stored session binding, and fixed instance mode must all agree. Conflicts return
the existing `INVALID_REQUEST` service error (HTTP 400).

For an existing session, its binding supplies the platform when documents or the
header are absent. A new conversation with no signal defaults to Hibank in auto
mode and to the configured platform in fixed mode. A fixed instance rejects the
other platform's sources, sessions, and headers.

## Sessions and history

New sessions store `chatbot_platform` in `chat_sessions.meta_data` during INSERT,
before conversation history is used. Mobile UUID uniqueness and
`INSERT ... ON CONFLICT DO NOTHING` select one authoritative first creator across
workers. A losing request reloads and validates the winner's owner, status, and
platform; it cannot rebind it. Agent asyncio locks continue to serialize agent
turns within a worker; platform correctness does not rely on those process-local
locks.

Metadata updates atomically merge JSON in PostgreSQL and restore the existing
binding in the same UPDATE. A stale agent-state or satisfaction update cannot
erase or replace the platform. Existing unbound sessions are permanently treated
as Hibank for compatibility; their next metadata update records Hibank. They
cannot become NegahBoom sessions.

Web session creation has no documents: use the header when creating a NegahBoom
session in auto mode, then select `NegahBoom_FAQ` on knowledge turns. A session
created without that header in auto mode is already Hibank and cannot switch.
Mobile talk can create a NegahBoom session directly from `NegahBoom_FAQ`.

Web and mobile listings return only sessions for the resolved platform. For
listings without a session signal, use the header to list NegahBoom in auto mode.
Specific history, close, messages, export, pin, delete, satisfaction, and query
feedback/comment operations validate the stored binding alongside existing
ownership checks. Mobile history retains its existing resolve-or-create behavior
and permits owned closed-session reads. Close remains idempotent.

National-code users remain shared across platforms in development. This provides
conversation binding, **not tenant-level identity isolation**. Existing ownership
and authentication rules are retained. Routes, request/response body schemas,
service deadlines, admission limits, and model/retrieval settings are unchanged.

Internal evaluation transports platform binding in agent state between isolated
turns. Old evaluation history is Hibank; a fresh evaluation may derive either
platform. Batch answering resolves ownership before its stateless agent turn;
the batch HTTP entrypoint also validates the optional header.

## Verification and limits

`tests/test_platform_context.py` uses synthetic data and offline doubles to check
resolution, fixed profiles, history/close scoping, concurrent contexts, UUID race
winners, and stale metadata writes. Existing regression suites also run through
`scripts/run_offline_tests.sh`. The race harness models PostgreSQL uniqueness and
statement atomicity; it is not a live PostgreSQL concurrency benchmark.

No prompts, models, retrieval settings, or national-code rules change in this
step. Platform-specific prompts and identifier validation are subsequent steps.
This foundation alone does not complete NegahBoom support.
