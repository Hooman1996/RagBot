# NegahBoom Step 1 review report

Implemented platform context and session binding only. No commit, push,
ingestion, database reset, production change, or private environment-file edit
was performed. Pre-existing unrelated work remains in place.

## Changed files

| Files | Change |
| --- | --- |
| `platform_context.py` (new) | Frozen context, stable IDs, configuration validation, central source ownership, conflict resolution, legacy-session rules, session/query access helpers |
| `answering_service.py` | Resolve and validate platform before history rewriting; pass context explicitly to rewriting and agent execution; retain available-title filtering |
| `agent_service.py`, `agent_graph.py` | Carry platform through persisted and stateless graph execution; validate session binding before generation |
| `new_architecture/app/services/history/database.py` | Insert binding with new sessions; validate mobile UUID conflict winners; preserve binding atomically during metadata updates; query-to-session lookup |
| `new_architecture/app/services/history/rewriting.py` | Accept explicit platform context, with unchanged rewrite prompts |
| `main.py` | Validate configuration at startup; bind web sessions; enforce platform on web conversation/session/query operations; filter listings; validate batch header/source consistency |
| `mobile_api.py` | Resolve talk/history/close context; filter listings; enforce session and feedback/comment/satisfaction consistency |
| `internal_evaluation_api.py` | Forward optional header to isolated evaluation answering; carry binding between evaluation turns in agent state |
| `env.example`, `Production_ENV.example` | Document `CHATBOT_PLATFORM` and its compatibility default without secrets |
| `docs/architecture/CHATBOT_PLATFORM.md` (new) | Configuration, ownership, header, lifecycle, concurrency, and compatibility documentation |
| `tests/test_platform_context.py` (new) | 29 focused synthetic tests covering resolution, conflicts, fixed instances, startup validation, web/mobile access, history/close, legacy sessions, concurrent contexts, first-creation races, and metadata persistence |
| `tests/test_answering_service.py`, `tests/test_mobile_history_content.py`, `tests/test_pipeline_terminal_debug.py`, `tests/test_internal_evaluation_parity.py`, `tests/test_health_checks.py`, `tests/test_coverage_check.py` | Update regression fixtures for explicit context, session metadata/header reads, and registered synthetic source ownership |
| `docs/architecture/NEGAHBOOM_STEP1_REPORT.md` (new) | This review and verification record |

## Resolution and compatibility decisions

- Absent configuration means fixed `hibank`, preserving existing calls. Invalid
  values fail startup. `auto` is intended for shared development at
  `localhost:7000`; separate production instances use fixed `hibank` or
  `negahboom` and isolated storage.
- `General_FAQ` belongs to Hibank and `NegahBoom_FAQ` to NegahBoom. Both remain
  category `FAQ`, retaining existing related-question behavior. The explicit
  contract/circular title families already in the code remain Hibank-owned.
  Unknown owners fail closed; the category hash fallback does not choose owners.
- Header, complete requested document selection, fixed configuration, and stored
  session binding must agree. No order-dependent first-document routing is used
  for platform selection. Existing available-title filtering remains intact.
- Existing sessions supply their binding when documents/header are absent.
  New conversations with no signal use Hibank in auto mode or the fixed mode.
  Web session creation has no document field: creating a NegahBoom session in
  auto mode requires `X-Chatbot-Platform: negahboom` at creation time.
- New sessions bind in INSERT. Mobile UUID uniqueness selects the first creator
  across workers. Losing requests validate the authoritative winner. PostgreSQL
  metadata UPDATE restores the existing platform in the same atomic statement,
  protecting it from stale snapshots or attempted overwrites.
- Legacy unbound sessions are Hibank and cannot be claimed by NegahBoom. Their
  next metadata update records the Hibank binding.
- Existing ownership checks, closed-session history reads, idempotent close,
  routes, body schemas, service limits, prompts, retrieval/model settings, and
  national-code rules remain. Mobile owner/status validation runs before platform
  conflict checks on existing sessions. Development identity remains shared by national
  code; this step does not implement tenant-level identity isolation.

## Verification actually run

Final required command (existing environment selected through PATH):

```bash
PATH=/root/miniconda3/envs/faq/bin:$PATH scripts/run_offline_tests.sh
```

Final result: **PASS**, exit 0.

- Pytest with `tests.offline_guard`: **964 passed**, **26 deselected**,
  **295 subtests passed**, 86 warnings, 53.92 seconds.
- All four Node frontend harnesses: **PASS**.
- Offline frontend audit: **PASS**, zero external runtime dependencies.
- Tracked-secret check: **PASS**, zero matches.

Additional completed checks:

- Focused platform test file: **29 passed** (offline).
- Earlier combined answering/mobile/evaluation/agent/context regression run:
  **102 passed**, **30 subtests passed** (before the last two focused tests and
  the final fixture corrections; the final full suite includes those changes).
- `ruff check platform_context.py tests/test_platform_context.py`: **PASS**.
- `python -m compileall -q` on the changed runtime Python modules: **PASS**.
- `git diff --check`: **PASS**.

Verification environment notes: the default Python lacks pytest. The existing
`faq` environment was used instead. Sandboxed Starlette TestClient hangs were
reproduced with a minimal FastAPI app; the same app returned HTTP 200 outside the
sandbox. The final required script ran outside the sandbox with its offline
network/database guard enabled. Obsolete sandboxed test runs were stopped. An
initial full run exposed two test-fixture mismatches (unregistered synthetic
source and missing mock request/session fields); both were corrected before the
passing final run. An exploratory broader Ruff check reported style/import
findings in existing runtime modules; no whole-repository lint pass is claimed.

## Remaining limits and subsequent steps

Concurrency tests use a synthetic storage harness modeling PostgreSQL UUID
uniqueness and atomic UPDATE, plus the real AgentService/ProductionHistoryProvider
with fake persistence. No live PostgreSQL concurrency test or staging HTTP/model
smoke test was run. No retrieval/answer-quality experiment or performance
benchmark was run: prompts, model behavior, retrieval configuration, and service
limits were not changed or tuned. No production connectivity checks were run.

Additional source titles without an existing contract/circular marker must be
registered in the central ownership map before use. The web frontend is not
updated to send the optional header in this step.

**Platform-specific prompts and identifier validation are subsequent steps.
This foundation alone does not complete NegahBoom support.**
