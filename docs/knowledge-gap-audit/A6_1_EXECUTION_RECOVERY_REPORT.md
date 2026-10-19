# A6.1 full-input execution controls and durable recovery

Status: **implemented for planner review; synthetic validation only**.
Branch `a6.1/full-input-recovery`; verified direct base
`11daa97c91b83dd30f5e4b0cd3f0f57289387fdb`. The publication commit is the commit
containing this report; the handoff supplies the verified full local/remote SHA.
Origin target is verified as `Hooman1996/RagBot` without printing its authenticated
URL. No historical commit or private run/export was rewritten.

**Live model, embedding and reranking requests: ZERO.** No customer dataset
execution, production/data-service calls, KB edits, deployment, shared-service
restart, retention deletion or A6.2 load experiment occurred. Synthetic tests use
mocked services, isolated filesystem roots and temporary synthetic authentication.
Coverage/recommendation prompts, eligibility rules, production retrieval defaults,
model settings/timeouts/output limits and existing role privileges are unchanged.
Independent human labels remain unavailable/pending; these checks do not establish
model quality, throughput or release readiness.

## Execution and accounting

The default is still `pilot`, with one to five explicit user-query identities.
`subset` accepts a larger explicit selection. `full_input` rejects client-supplied
IDs and resolves every user-query identity from the authorized owned dataset.
The configurable maximum rejects oversized selections; nothing is silently
truncated. Invalid, context-dependent, excluded, duplicate and error records remain
represented. No selection depends on feedback, answers or failure flags.

Run creation persists dataset/snapshot, owner, source-order IDs, separate A1
chronological processing IDs, versions/settings and a durable creation intent
before scheduling. Owner/request-bound idempotency uses a deterministic owner/key
address and a short creation lock. Repeated starts return the same run; conflicting
reuse fails. Incomplete creation repairs the same address. Omitted API keys use the
canonical request identity; the page deliberately supplies/reuses a key and uses
a new key for a new submission. Active duplicate starts/resumes cannot steal the
OS run lease or launch another execution owner.

Exports still include every imported user-query row in original order, even for
a subset. `selected_for_execution` and `execution_selected_row_count` distinguish
that export denominator from execution selection. A1 cutoff history, timestamp/
timezone/tie provenance and user-only history remain unchanged; no assistant
history is invented. Missing times use A1's stable fallback without claiming
verified conversational order.

Progress separates imported, selected, processed, entry-model-evaluated,
pending/interrupted, context/review, excluded and error counts. Processed includes
terminal errors/invalid records; model-evaluated means a KB entry has locally validated findings across compatible
attempts. Attempted rows and completion-dispatch markers are separate counts; an
unreturned request is not counted as evaluated. Scope/preparation alone is not
KB evaluation. Legacy counts unavailable under this definition say not recorded. Full/subset runs
use `processed_rows`; the legacy pilot counter is limited to pilots/legacy views.
A completed run with errors is explicitly finished-with-errors. Completion is
row accounting, not a clean quality pass or independent human validation.

## State, checkpoints and recovery

Run transitions: `queued → running → completed`; cancellation/shutdown/worker loss
produce `cancelled`/`interrupted`, write failures produce `failed`, and incompatible
identities/source produce `incompatible`. Explicit compatible recovery returns to
`queued`; no startup routine automatically resumes unknown in-flight work.
Rows retain terminal completed/excluded/context/review/invalid results. Explicit
recovery replaces only pending/failed/interrupted/cancelled effective work and
continues the attempt count. Prior failures and results stay in separate attempt
files; effective results do not inherit obsolete errors or evidence.

`audit-boundaries-1` saves only completed redacted structured preparation/model
responses and frozen retrieval candidate/selection ID manifests. Request keys bind
query/history input, aspects and batch membership/phase through payload hashes,
plus source/snapshot, run configuration, code/schema/rubric/model and batch/token
policy identities. Restored hashes/schema/membership/citations and semantic proof
rules are checked again. Schema-valid output is not automatically valid evidence.
Production versus audit evidence scopes stay separate. A previously verified
identical proof avoids redispatch while still passing local checks.

Pinned retrieval membership prevents reordering on retry from silently changing
batch boundaries. Live source/index checks still run around restored selections;
this is not frozen Qdrant retrieval. Distinct entry IDs dispatched across attempts
remain charged against the same maximum 300 budget. An unresolved retained entry
cannot support a possible-gap conclusion merely because it is absent from a later
validated ledger. Completed rows are never re-evaluated on worker restart.

The request journal distinguishes prepared, dispatch marker, received response,
validated structured checkpoint, failure-before-dispatch and unknown completion.
The dispatch marker is durable before the SDK request. It conservatively covers
a crash between marker and actual send; it cannot prove the request reached the
server. Preparation/retrieval are opaque service boundaries and explicitly record
unobserved completion instead of claiming confirmed model dispatches. Tokenization
is not a completion dispatch. Journals contain only allowlisted metadata, IDs,
hashes, timings/tokens and safe categories, never filled prompts/raw outputs,
exception values, authorization headers or arbitrary source columns.

SDK network retries stay zero. The existing one fresh syntax-only recovery per
call remains bounded/versioned/counted. Unknown work is never silently retried.
`POST /runs/{id}/retry` offers:

- `stop` (default): refuse recovery if unfinished rows have unknown work.
- `skip_unknown`: leave those rows interrupted and continue other selected rows.
- `retry_unknown`: explicitly acknowledge possible duplicate work/cost and retry.

Recovery choices have their own immutable records. Prior unknown dispatches and
failures remain historical even after a successful explicit retry. Immutable old
CSV/manifest bytes are never regenerated. A known response without a completed
validated checkpoint is not usable evidence; a merely dispatched request is never
promoted to success. Exactly-once inference and remote-server cancellation are
not claimed.

## Worker ownership and safe cancellation

Existing tracked in-process jobs, a nonblocking per-run OS flock and the common
artifact-root global OS gate provide one worker owner and sequential coverage/
recommendation execution across local processes. Busy workers remain queued.
Queued cancellation persists before execution; checks before work prevent later
inference. A cross-process cancellation watcher cancels the owning local task.
Persistent cancellation cannot be overwritten by stale progress writes.

The existing blocking runner permits cancelled waiters to leave threads active.
Audit-local `DurableIO` drains short filesystem writes before releasing their
worker lease and closes lease descriptors acquired but never delivered to a
cancelled caller. Tests cover actual thread/permit balance and OS lease ownership.
Remote/model operations do not use this filesystem adapter. Cancellation returns
after durable intent and at most one second of waiting for the local task; it does
not wait for the whole audit. A failed/hung filesystem remains an operator
storage dependency, not a promised deadline or inference success.

Abrupt process death releases kernel leases. Inspection marks stale running work
interrupted and reconciles dirty indexes; recovery remains explicit. No PID-based
lock stealing exists. Locks assume the existing local filesystem and common
artifact root, not distributed multi-host queue semantics. The gate bounds locally
active workers; an unconfirmed remote completion can still run after local
cancellation. Operators must consider possible remote overlap/duplicate usage
before continuing/retrying. Immutable serving weight/tokenizer provenance remains
unverified where unavailable. Old pre-A6 runs cannot migrate through changed code;
legacy reads do not create recovery/index artifacts.

## Dashboard and export

The existing page adds execution mode, dataset/snapshot/selected-source summary,
effective budget/batch cap, sequential-duration guidance, recovery inspection and
explicit retry choices. No invented ETA/accuracy or automatic recommendations.
Existing themes, local assets, keyboard/RTL patterns, default-deny capabilities,
active-account, ownership and CSRF boundaries remain. Background dispatch checks
current account/grants; no real account was granted access.

New captures use `coverage-page-3`, `coverage-settings-4`, `coverage-csv-5` and
`coverage-export-manifest-5`. Additional CSV fields: execution mode/selection count,
selected flag, validated-model/dispatched flags, reuse/checkpoint/unknown counts
and content-free request journal JSON. The manifest adds frozen execution counts. Full/subset manifests carry actual scope and processing order, not pilot-only
labels. Restricted projections retain safe metadata while withholding evidence,
notes and drafts. Shared A1 encoding preserves BOM, JSON cells, quoting, Persian,
formula protection and exact row order/identity. A5's common frozen coverage source,
per-row recommendation/review selection and immutable permission-specific exports
remain unchanged; combined manifests propagate the pinned source's actual scope.
Historical schemas/revisions retain their original bytes and meaning.

## Failure injection and measurements

A complete fictional 918-row input includes duplicate queries and one invalid
query. The full-selection test interrupts at a completed-row boundary, freezes a
918-row partial export, explicitly recovers, retains completed rows and completes
all 918 rows with 917 prescribed mock exclusions plus one invalid/error record.
Only the unfinished synthetic evaluation is entered again; no completed model
boundary is repeated. A 500-row explicit subset and duplicate starts/idempotency
are also checked. All export row IDs/order and immutable partial bytes are verified.

Real child-process termination after completed batch and verification checkpoints
reconstructs the proof with **exactly one mocked dispatch each** for scope,
aspects, batch and verification. Unknown dispatches require an explicit choice;
pre-dispatch work is not counted completed. Other tests cover competing processes,
queued/active cancellation, cancellation/progress races, disk/write failures,
invalid citations/hash tampering, changed snapshot/code/model/settings, owner and
revoked permissions, CSRF and historical export preservation.

Two late synthetic regressions reproduced **2 failures** before correction:
active-attempt progress lacked an outcome after clearing old result fields; and
an interruption record could overwrite an archived result following a row-write
failure. Both are corrected and pass. Separate real-thread cancellation tests
confirm checkpoint draining and undelivered-descriptor cleanup.

The benchmark holds writer durability/input/configuration constant and compares
the former repeated full-row read policy with the rebuildable index. Rows remain
authoritative; a durable dirty marker ensures a failed row/index pair is rebuilt.
The index contains bounded redacted summaries rather than full evidence. Historical
reads keep their old read-only path. Five poll/checkpoint iterations use identical
918-row fictional input; these are local file-I/O measurements, not production
throughput or a service-load experiment.

| Operation | Former scan median | Indexed median | Row reads across five iterations |
|---|---:|---:|---:|
| Progress poll | 811.815 ms | 7.405 ms | 4,590 → 0 |
| Checkpoint plus progress | 775.184 ms | 35.454 ms | 4,595 → 5 |

The final measurements include owner checks, durable writes, index reads and
rebuildable metadata. Results are small-sample observations without a capacity or
statistical confidence claim.

## Exact validation

Environment for all Python commands:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Final comprehensive command (all fixtures/services mocked or isolated):

```bash
timeout 360 python -m pytest \
  tests/test_knowledge_execution_recovery.py \
  tests/test_knowledge_run_export.py tests/test_knowledge_recommendations.py \
  tests/test_knowledge_coverage_calibration.py tests/test_knowledge_coverage_reliability.py \
  tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py \
  tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py \
  tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py \
  tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py \
  tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py \
  tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py \
  tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py \
  tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py \
  tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py \
  tests/test_performance_config.py tests/test_validate_environment.py \
  tests/test_answering_service.py tests/test_history_aware_query_routing.py \
  tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py \
  tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py \
  tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py \
  tests/test_structured_logging.py tests/test_offline_frontend.py -q
```

Final result: **582 passed, 44 warnings, 203 subtests passed in 192.94s (0:03:12)**. The preceding final sweep exposed
a cancellation-watcher race (1 failed, 580 passed / 203 subtests, 197.68s).
A deterministic delayed-cleanup regression reproduced it (1 failed, 36 deselected,
11.98s): the watcher could cancel an already-cancelling task during durable
interruption. The watcher now checks pending cancellation before cancelling,
allowing cleanup to finish. Both the new regression and the original cancellation/
recovery test then passed (2 passed, 48 deselected, 12.92s). Earlier complete validation passed
576 tests / 203 subtests before the final metadata/queued-revision guards; focused
recovery/recommendation/export regressions then passed 122 cases. A synthetic
accounting fixture initially failed to trigger its intended transport error after
history rewriting; it was corrected to key off the explicit original scope input,
without changing the expected counts or weakening validation. The final targeted
accounting/legacy/progress check passed 3 cases (33 deselected). Known warnings are
deprecations, unavailable NVML and Linux fork warnings; process failure tests
completed. No warning is represented as a new service or GPU validation.

Additional executed commands:

```bash
# Reproductions before the narrow corrections: 2 failed, 26 deselected, 12.06s.
timeout 30 python -m pytest tests/test_knowledge_execution_recovery.py -q \
  -k 'progress_remains or result_archive'
# Narrow post-correction recovery/permissions tests: 64 passed, 1 deselected.
timeout 100 python -m pytest tests/test_knowledge_execution_recovery.py \
  tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_coverage_corrections.py \
  -q -x -k 'not full_918'
# Additional before-dispatch/code/snapshot faults: 3 passed, 31 deselected.
timeout 60 python -m pytest tests/test_knowledge_execution_recovery.py -q \
  -k 'crash_before_dispatch or changed_code_recovery or changed_snapshot_recovery'
# Final queue/recovery/export subset: 122 passed, 2 deselected, 31.73s.
timeout 120 python -m pytest tests/test_knowledge_execution_recovery.py \
  tests/test_knowledge_recommendations.py tests/test_knowledge_run_export.py \
  tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_coverage_corrections.py \
  -q -k 'not full_918'
# Watcher race: before 1 failed; after 2 passed, 48 deselected.
timeout 60 python -m pytest tests/test_knowledge_execution_recovery.py \
  tests/test_knowledge_coverage_access_jobs.py -q \
  -k 'cancel_monitor or cancel_and_interrupted'
python scripts/benchmark_coverage_progress.py --iterations 5
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit scripts/benchmark_coverage_progress.py \
  scripts/validate_environment.py tests/test_knowledge_execution_recovery.py \
  tests/knowledge_execution_browser_app.py
node --check static/js/knowledge_coverage.js
node --check static/js/knowledge_run_export.js
git diff --check
```

Frontend Node suites: **5 + 6 + 5 passed**. Offline dependency audit: **PASS,
zero external runtime dependencies**. Compilation, JS syntax and whitespace checks
passed. Old recommendation/export permission, malformed-output, formula/JSON/
Persian, immutable-review/source and production-proof regressions remain included.
No connectivity benchmark, actual retrieval recall, server resource/load,
production-throughput or calibrated model accuracy result is claimed.

## Actual browser checks

```bash
python -m tests.knowledge_execution_browser_app --port 18766
node tests/knowledge_execution.browser.cjs /tmp/faq-a21-browser-node \
  http://127.0.0.1:18766 /tmp/faq-a61-browser-publish
```

Actual isolated Playwright/Chromium **153.0.8010.0** passed three check groups,
including a final repeat after the cancellation-watcher correction:
918-row Persian/multiline upload/mapping and default-pilot/full selection; active
cancellation, refusal of unknown-work default retry, explicit duplicate-work
acknowledgement, recovery and repeated immutable 918-row CSV/manifest downloads;
and a nine-row larger subset finishing with its invalid row explicitly reported,
evidence inspection, keyboard operation, light desktop and 390px dark RTL view
without page-wide overflow. The browser's full-selection run was cancelled and
partially recovered; it is not presented as a completed 918-row model audit.
Backend mocks separately completed/recovered all 918 synthetic rows.

The fixture grants only a temporary synthetic process-local account, uses isolated
private `/tmp` artifacts and restricts browser requests to its loopback origin.
It does not initialize real inference/data services. The isolated server was
stopped after checks; no shared service was restarted. Early browser harness
attempts needed waits for asynchronous selection rendering and explicit theme
selection; successful final captures are listed below. Screenshots were actually
opened and visually inspected, including both themes and Persian/RTL content.

- [Full-input selection · light](assets/a6_1_synthetic/a61-full-input-light.png)
- [Unknown-work recovery · light](assets/a6_1_synthetic/a61-recovery-light.png)
- [Subset completed with errors · dark RTL](assets/a6_1_synthetic/a61-subset-dark-rtl.png)
- [Browser check inventory](assets/a6_1_synthetic/checks.json)
- [Content-free progress measurements](assets/a6_1_synthetic/progress-benchmark.json)

No new 768/1280 screenshot matrix, screen-reader acceptance, native Excel/
LibreOffice import or real-account/live-inference browser validation was performed.
Native spreadsheet applications remain unavailable. A5's historical wider visual
matrix is retained rather than relabeled as new A6 testing.

## Recovery operator steps

1. Inspect the owned run's mode, selected/imported/processed counts, error/unknown
   counts, immutable identities and selected row details. A cancelled/interrupted
   state does not mean remote inference stopped.
2. Confirm the original code/settings/snapshot/serving identities still match.
   Fix storage failures first. Incompatible or historical pre-A6 runs require a
   new run; do not edit pinned identities or copy checkpoints to evade the gate.
3. Inspect request/attempt metadata and retained structured checkpoints. If remote
   completion is unknown, check available serving evidence through the operator
   process and choose stop, skip, or explicit duplicate-work retry. No automatic
   server cancellation or exactly-once claim is available.
4. Use the protected page's recovery choice and resume action (or the owned,
   authenticated/CSRF-protected retry API). Completed rows are retained; unknown
   skipped rows stay interrupted. Repeated requests cannot acquire another owner.
5. Inspect terminal errors/review states and prepare a **new** immutable coverage
   export if needed. Existing drafts continue using their explicitly selected old
   coverage source. Select new coverage/draft/review revisions deliberately; old
   downloads remain byte-identical.

These are future authorized-operator steps; none was executed on customer runs
in A6.1.

## Configuration, preservation and remaining gates

New permanent variable: `KNOWLEDGE_COVERAGE_MAX_RUN_ROWS=10000`, integer **5–100000**.
Defaults, strict validation, runtime/export identity and documentation are updated.
All applicable root tracked templates (`env.example`, `env.review.example`,
`Production_ENV`, `.env.example.generated`) and existing private `.env`/`.env_latest`
received the key. The generated-named example is source-authored; no separate
generator exists. Existing private file bytes preceding the appended key were
hash-verified. The deleted staging template was not recreated. The separate
evaluation-system configuration/frontend is unchanged.

**4,756 historical private artifact files verified unchanged**, with zero added
files in the actual durable private artifact root. Raw supplied CSV hash, original
private env bytes, user ignore edits and deleted template state are preserved.
All new execution/fault/browser artifacts were synthetic in protected temporary
roots; only synthetic screenshots and content-free measurements enter Git.
New operational artifacts follow the existing configured durable root outside
Git/static, 0700 directories/0600 files, owner checks and no symlink traversal.
Existing regex redaction is not comprehensive name/address/banking-fact detection;
private access and authorized human review remain necessary.

No user-unrelated modifications/untracked inputs/private envs are staged.
Authorized ignored documentation/assets are explicitly added without modifying
the ignore rule. Historical pre-P0 credential exposure remains a separate owner
responsibility: assess/rotate affected external credentials and decide coordinated
history handling through the operator process. No values are printed, external
credentials rotated or history rewritten.

A6.1 is reviewable as execution/recovery foundations. **A6.2 is not implemented**:
retention/expiry/deletion, approved staging service-load/resource/interference
validation, larger-run capacity acceptance and production readiness remain future
gates. Maximum configured size is not measured capacity. Source/index bracketing
cannot freeze live Qdrant or detect every ABA/unchanged-alias serving change.
Unknown remote usage/completion remains unknown; local sequential admission does
not guarantee the remote server has finished abandoned work. New A6 startup does
not dispatch unjournaled schema capability completions; strict server JSON schemas
and local validation still apply, with unsupported serving failing closed.
Independent human gap/answer/question validation and earlier release blockers
remain pending. No actual customer full-input run is authorized by this report.

## Scoped publication files

The publication includes only these 40 authorized files (including five synthetic
browser/measurement assets):

```text
.env.example.generated
Production_ENV
env.example
env.review.example
docs/configuration/ENVIRONMENT_VARIABLES.md
docs/knowledge-gap-audit/DASHBOARD_AND_CSV_CONTRACT.md
docs/knowledge-gap-audit/IMPLEMENTATION_PLAN.md
docs/knowledge-gap-audit/A6_1_EXECUTION_RECOVERY_REPORT.md
knowledge_audit/api.py
knowledge_audit/export.py
knowledge_audit/jobs.py
knowledge_audit/model.py
knowledge_audit/pipeline.py
knowledge_audit/recommendation_jobs.py
knowledge_audit/run_export.py
knowledge_audit/service.py
knowledge_audit/settings.py
knowledge_audit/store.py
knowledge_audit/durable_io.py
knowledge_audit/execution.py
knowledge_audit/recovery.py
scripts/validate_environment.py
scripts/benchmark_coverage_progress.py
static/js/knowledge_coverage.js
static/js/knowledge_run_export.js
templates/knowledge_coverage.html
tests/knowledge_coverage.browser.cjs
tests/knowledge_coverage.frontend.test.cjs
tests/knowledge_recommendations.browser.cjs
tests/test_knowledge_coverage_access_jobs.py
tests/test_knowledge_coverage_corrections.py
tests/test_knowledge_coverage_reliability.py
tests/knowledge_execution.browser.cjs
tests/knowledge_execution_browser_app.py
tests/test_knowledge_execution_recovery.py
docs/knowledge-gap-audit/assets/a6_1_synthetic/a61-full-input-light.png
docs/knowledge-gap-audit/assets/a6_1_synthetic/a61-recovery-light.png
docs/knowledge-gap-audit/assets/a6_1_synthetic/a61-subset-dark-rtl.png
docs/knowledge-gap-audit/assets/a6_1_synthetic/checks.json
docs/knowledge-gap-audit/assets/a6_1_synthetic/progress-benchmark.json
```
