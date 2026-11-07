# Knowledge selection correction

Implemented for review on 2026-11-01. Code and offline verification only; no deployment.

## Root cause and inventory

The previous design combined three independent concerns: selecting prompts,
restricting an application instance to a company, and permanently binding a
conversation to that company. Web creation had no document selection and bound
ordinary sessions to Hibank. Selecting NegahBoom later therefore conflicted with
the stored binding. Mobile creation could derive its first binding from the talk
request's documents, creating the apparent web/mobile discrepancy. Fixed instance
configuration could also reject that mobile request. Neither restriction belongs
in per-request retrieval.

| Area inspected | Correction or preserved behavior |
| --- | --- |
| `platform_context.py` | Removed after replacing all callers. Removed environment validation, header interpretation, source ownership registry, conflicts, legacy identity inference, snapshot identity, and session/query platform guards. |
| `main.py` | Removed startup platform validation; web query, create, list, read, messages, export, pin, delete, feedback, comment, satisfaction and direct batch paths no longer bind/filter/check company. Existing ownership and authorization guards remain. |
| `mobile_api.py` | Removed prompt/platform forwarding and history filtering. Retained the pre-write UUID owner/status check as `validate_mobile_access`; resolver still rechecks after creation races. Close, history, feedback, comment and satisfaction no longer check company. |
| `answering_service.py` | Removed platform fields from the internal context (no HTTP body schema change). Selects the request-local prompt context from validated documents before rewriting. Shared web/mobile/batch/evaluation semantics remain. |
| `agent_service.py` | No platform resolution or selected prompt field in graph state. Replaces allowed documents/category/retrieval query/preclassification each turn. Preserves existing per-conversation concurrency serialization and execution policies. |
| `agent_graph.py` | Removed platform state field. Answer and chit-chat nodes select prompts from current allowed documents. Family-specific FAQ refusal detection remains; fresh retrieval and related questions remain unchanged. |
| `utils/RagSystem.py` | Local template selection replaces platform restrictions. No changes to shared Config, message roles, user templates, token/sampling settings, timeouts, limits or workflow contracts. |
| `new_architecture/app/services/history/rewriting.py` | Receives a local prompt context; default rewriting path and summary template remain unchanged. |
| `conversation_history.py` | Hydration ignores legacy identity fields. History formatting, reference context, trimming and provider ownership/lifecycle boundaries remain. |
| `new_architecture/app/services/history/database.py` | Empty metadata on new web/mobile sessions. Atomic JSON merge retained without creating/enforcing a platform field. UUID uniqueness, first-creator ownership, active/closed/deleted behavior unchanged. |
| `internal_evaluation_api.py` | Does not read the old header. Existing isolated history provider and execution policies remain. |
| `mass_answer_service.py`, `mass_answer_jobs.py`, evaluation history provider/state restoration | Inspected: shared answering service owns selection; batch is stateless, evaluation hydrates opaque state, and neither adds separate platform routing. No changes needed. |
| `utils/persian_hybrid_search.py`, `utils/revision_cache.py` | Inspected: BM25 cache keys already use sorted selected document titles plus revision; semantic retrieval is filtered by current documents. No answer/prompt cache or prior chunk state to invalidate. No retrieval/cache setting changes. |
| `static/js/api.js` | Checks HTTP/application failures; maps existing errorCode/errorDesc and HTTPException detail formats to safe localized messages, with a fallback for unknown/non-JSON failures. Never echoes arbitrary debug text. |
| `static/js/sidebar.js` | Direct create/history/download fetches now use checked transport. Failed creation clears its pending promise. Selection does not replace sessions. |
| `static/js/chat.js` | Session creation is inside the failure-recovery boundary. Errors use textContent, typing/sending controls recover, and current selected titles still accompany every query. |
| `static/js/categoryFilter.js`, `document_category.py` | Selection/category logic inspected and preserved: no company selection or restoration. Category-load errors now use the safe localized handler. Existing category constraints remain; General_FAQ and NegahBoom_FAQ both remain FAQ. |
| `env.example`, `Production_ENV.example` | Removed obsolete platform setting and fixed/shared-instance instructions. Private environment files untouched. |
| `docs/architecture/CHATBOT_PLATFORM.md`, Step 1 and Step 2 reports | Current guidance corrected; historical reports explicitly marked superseded with links here. |

New source files: `prompt_selection.py`, `mixed_source_prompts.py`.
New frontend test: `tests/chat_knowledge_selection.frontend.test.cjs`.
New documentation: this report.

Updated tests: `tests/test_platform_context.py` replaces obsolete restriction
expectations with correction regressions; `tests/test_negahboom_prompts.py`,
`tests/test_answering_service.py`, `tests/test_pipeline_terminal_debug.py` use
request-local prompts. `tests/test_coverage_check.py` no longer registers a
synthetic title with an ownership whitelist. `scripts/run_offline_tests.sh` adds
the chat harness to the required checks. Ownership and data-integrity tests were
not weakened.

## Deterministic per-request prompt rules

1. Validate the requested titles using the existing available-document mechanism.
   The resulting list is the retrieval scope for this turn only.
2. Look up optional exact-title associations in the centralized, immutable
   `SOURCE_PROMPT_FAMILIES` mapping in `prompt_selection.py`.
   `NegahBoom_FAQ` explicitly maps to `negahboom`. Unassociated titles use the
   established Hibank/category fallback. This mapping is not an access whitelist.
   Adding an available source requires no prompt registration.
3. A nonempty selection resolving entirely to one family uses that family.
   Consequently General_FAQ-only uses unchanged Hibank prompts, and
   NegahBoom_FAQ-only uses the approved NegahBoom answer, chit-chat and rewrite
   prompts. Duplicate titles do not affect selection.
4. A combination resolving to both families uses the separate neutral Hibot
   bundle in `mixed_source_prompts.py`. Order does not matter. It grounds service
   claims in current source evidence and keeps source-specific facts distinct,
   without exclusive company representation. FAQ user formatting and related
   question processing remain the normal paths.
5. Empty selection retains the established non-platform fallback: Hibank prompts
   for conversational turns; substantive knowledge requests still require at
   least one current available source. No legacy binding supplies an identity.
6. Category selection remains separate. Single-family contract/notification workflows
   retain their original Config templates. Mixed-family requests remain neutral
   even when a document workflow is selected, using separate neutral templates
   and the existing document user-template placeholders. Category hashes never choose identity.
7. Resolve the family before rewriting; the graph derives the same deterministic
   bundle from this turn's allowed documents. All choices are local values, never
   shared Config/global mutations or a new persisted prompt-family field.

NegahBoom's introduction remains exactly:

> من Hibot هستم، دستیار هوشمند بانکداری باز

Both original prompt modules (`new_architecture/app/config.py` and
`negahboom_prompts.py`) are byte-identical to HEAD. Tests additionally compare
all eight pre-existing prompt hashes in `step2_existing_prompt_hashes.json` and
actual fake-client message roles/content for FAQ, chit-chat and document paths.

## Compatibility, metadata, and evidence

`CHATBOT_PLATFORM` is never read by application routing or startup, regardless of
presence or value. `X-Chatbot-Platform` is ignored, including old/invalid values.
No replacement instance-mode setting exists. New sessions receive no company
binding. Old top-level metadata remains untouched by ordinary JSON merges. Old
agent-state identity fields are excluded from graph execution; when an existing
snapshot contains them, ordinary saves preserve those opaque values without
consulting or rebinding them. No migration or cleanup is needed or performed.

Conversation messages and ordinary reference resolution remain available when
sources change. Current titles overwrite stale allowed documents before every
graph execution; retrieval executes again. FAQ answer messages contain only
current retrieved evidence, not previous assistant messages. History remains
input to reference rewriting, not substitute answer evidence. Retry and cache
paths do not restore a prior source or prompt choice. Existing same-conversation
serialization, HTTP request limits and deadlines remain in place.

Production deployments keep separate storage/configuration through ordinary
PostgreSQL, Qdrant, MinIO and model configuration. The application introduces no
company-level session isolation. No re-ingestion is required.

## Offline verification

Verification uses synthetic records, fake completions, in-memory services and
`tests.offline_guard`, which blocks unmocked socket connections/DNS and psycopg2
connections. FastAPI tests replace lifespan with an empty fixture; configured
application startup is never run.

- Initial focused command: `/root/miniconda3/envs/faq/bin/python -m pytest -p tests.offline_guard tests/test_negahboom_prompts.py tests/test_answering_service.py tests/test_p0_p1_repairs.py tests/test_mobile_history_content.py -q` — **68 passed, 3 subtests passed**.
- `PATH=/root/miniconda3/envs/faq/bin:$PATH bash scripts/run_offline_tests.sh` — **1025 passed, 26 deselected, 295 subtests passed**, five Node harnesses passed, frontend audit passed (zero external runtime dependencies), tracked-secret check passed (zero matches). Includes retrieval regressions and offline retrieval/answer-quality evaluation tooling tests; these are not live labelled quality evaluations.
- `node tests/chat_knowledge_selection.frontend.test.cjs` after final control recovery changes — **3 passed**. Exercises actual API/session/document-tag/query flow, same-session switching, safe HTTP/application/non-JSON/network errors, and creation retry.
- `/root/miniconda3/envs/faq/bin/ruff check prompt_selection.py mixed_source_prompts.py tests/test_platform_context.py tests/test_negahboom_prompts.py` — **passed**.
- Final focused command: `/root/miniconda3/envs/faq/bin/python -m pytest -p tests.offline_guard tests/test_negahboom_prompts.py tests/test_answering_service.py tests/test_p0_p1_repairs.py tests/test_mobile_history_content.py tests/test_platform_context.py tests/test_internal_evaluation_api.py tests/test_release_evaluation_tools.py tests/test_revision_aware_cache.py -q` — **124 passed, 11 subtests passed**.
- Final snapshot command, run from `/tmp/faq-knowledge-correction-acuwlx94`: `GIT_DIR=/root/projects/faq/.git GIT_WORK_TREE=/tmp/faq-knowledge-correction-acuwlx94 PATH=/root/miniconda3/envs/faq/bin:$PATH bash scripts/run_offline_tests.sh` — **1027 passed, 26 deselected, 295 subtests passed** in 71.17 seconds; all five Node harnesses and the offline frontend audit passed. The snapshot secret check correctly reported **NOT RUN (no local env files)**; the real-worktree tracked-secret check separately returned **0 matches**, as did the explicit scan of all four intended new files against local credential candidates (without printing values).
- `git diff --check`, Node syntax checks for `api.js`, `sidebar.js`, `chat.js`, `categoryFilter.js`, and Python compilation of all changed/new runtime and test modules — **passed**. The source/new-file status and whitespace audit passed.
- Final snapshot source parity: all intended changed/new source files match the worktree; the final report was copied into that snapshot after recording these results. The obsolete module is absent. No unrelated untracked file is required.

The web matrix covers absent/hibank/negahboom/auto/arbitrary obsolete environment
values and absent/hibank/negahboom/obsolete stored bindings. Each case creates an
ordinary web session and runs General → NegahBoom → General → newly available FAQ
in that same session, preserving prior messages and checking actual completion
evidence and rewrite bundles. Mobile tests run equivalent source changes with the
same UUID/internal session and history. Separate regressions cover both listing
paths, legacy metadata merges, concurrent same-user/cross-user UUID creation,
close ownership, empty selections, mixed-source ordering/concurrency, evaluation
state switching and stateless batch execution. Existing authentication, web
feedback/comment/export/pin/delete/satisfaction ownership and mobile lifecycle
regressions remain in the full suite.

Initial nonpassing attempts: default Python lacked pytest; the existing faq
interpreter resolved this without installation. A sandboxed TestClient run hung
in the previously documented cross-thread portal condition and was interrupted.
Successful handler/full-suite runs used the permitted executor outside that
sandbox while retaining the offline guard. New test fixtures were corrected for
formatted rewrite placeholders, the stub internal context, missing synthetic
message timestamps and minimal DOM rendering. These attempts are not counted as
passing verification. Lint import/fixture style findings were corrected.

## Worktree and snapshot audit

The starting worktree had no modified tracked files. Pre-existing untracked items
are intentionally excluded and untouched: `NegahBoom_FAQ.csv`,
`benchmarks/admission/`, the three Persian pipeline/normalization diagnostic files
under `benchmarks/`, `data_insertion_chunks/.add-knowledge.lock`, `docs/ingestion/`,
`negahboom_data_ingestion/`, and `test.json`. They are not dependencies of this
correction. In particular, historical/private ingestion notes outside the tracked
change set are not current runtime instructions.

The disposable review snapshot is assembled from HEAD's tracked files, overlays
only modified tracked paths, removes the obsolete module, and adds only the four
new source/test/document paths named above. No private environment, ingestion
artifacts, unrelated untracked files or installed dependency trees are copied.
Read-only Git metadata is supplied only for baseline-byte tests. Snapshot
verification passed with the final results recorded above. The final inventory is
26 changed tracked paths (including the obsolete module deletion) and four new
files. No index changes, commit or push were used to assemble it.

## Remaining verification and rollout

After separate deployment authorization, restart application workers and refresh
the browser so the new Python code and versioned JavaScript are loaded. No
configuration edit, session reset, migration, backfill, ingestion or re-ingestion
is necessary.

On authorized staging, smoke-test the same web/mobile session switching and
history with real services, plus mixed-source and ambiguous/clear follow-ups.
Run the labelled retrieval and blind answer-quality procedures in
`docs/performance/RELEASE_EVALUATION_RUNBOOK.md`, including NegahBoom identity,
neutral mixed-source attribution, refusals, related questions and source-switch
references. Fake-client tests establish routing, evidence boundaries and prompt
construction; they do not establish live answer quality, service readiness or
production capacity. No live-service readiness claim is made here.

No live PostgreSQL, Qdrant, MinIO or model service was accessed or modified. No
setup, migration, database initialization, ingestion, backfill, deployment, commit
or push was performed. Stop ready for review.
