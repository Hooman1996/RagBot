# A2 — main-dashboard end-to-end knowledge-coverage pilot

Status: **READY_FOR_PLANNER_REVIEW_WITH_LIMITATIONS**. The A2 page, bounded
pipeline, protected persistence and complete CSV are implemented and tested.
The actual five-query pilot reached retrieval, evaluation, reconciliation and
verification/broader search. Two strict model-output failures are retained.
This is not calibrated accuracy, human-reviewed ground truth, release acceptance
or authorization for a full-dataset run. Stop after A2; recommendations remain
unassessed. No production calls, KB edits, shared-service restart, deployment,
push, merge or infrastructure changes occurred. Production answering/retrieval
defaults and the separate evaluation-system frontend were not changed.

## Repository and scoped implementation

Repository `/root/projects/faq`; branch `a2/knowledge-coverage-pilot`; verified
base `95177141cecb448da6a5758c78ce972f913c8830`. The commit containing this
report is returned in the planner handoff and identified by `git log -1`.
A commit cannot embed its own final hash. Both live runs record the base plus
exact implementation-file hashes, including uncommitted A2 code at execution.

Scoped files:

- New `knowledge_audit/{api,evidence,jobs,model,pipeline,prompts,retrieval,schemas,service,settings,store}.py`:
  dashboard routes, strict responsibilities, snapshot evidence, protected
  checkpoints, request-local retrieval and bounded evidence decisions.
- `knowledge_audit/{export,preparation,runtime}.py`: shared A1/A2 serializer,
  audit-only explicit-subject context review and version identities. A1
  importer/history/snapshot/redactor remain the foundations.
- New `scripts/knowledge_coverage_pilot.py`: trusted operator archive/pilot CLI.
- `main.py`, `kb_manager.py`, `web_auth.py`, `web_permissions.py`,
  `mass_answer_jobs.py`, `utils/http_logging_middleware.py`: main app registration,
  capability-gated navigation, existing job tracker extension and metadata-only
  audit telemetry. Existing role permissions and job defaults stay unchanged.
- New `templates/knowledge_coverage.html`, `templates/_coverage_nav_link.html`,
  `static/css/knowledge_coverage.css`, `static/js/knowledge_coverage.js`;
  navigation in `templates/{index,analytics,kb_manager}.html`, asset registration
  in `versioned_assets.py` and offline audit in `scripts/audit_offline_frontend.py`.
- New `tests/test_knowledge_coverage_{pipeline,access_jobs}.py` and
  `tests/knowledge_coverage.frontend.test.cjs`; route inventory, HTTP logging and
  offline template checks in existing tests.
- `env.example`, `Production_ENV`, `.env.example.generated`,
  `scripts/validate_environment.py`; configuration documentation and this report,
  `A2_RUBRIC_AND_SCHEMAS.md`, implementation plan and dashboard/CSV contract.

Unrelated `.gitignore` edits, user-deleted staging template, private `.env` edits,
untracked `.env_latest`, input files and other untracked work are preserved.
Only scoped files and explicitly authorized ignored documents are staged.
Private envs, CSV input, artifacts and customer-derived fixtures are not committed.
All committed examples/tests are synthetic. Root `.env` loads through dotenv;
no secrets or raw customer/KB content were printed. Read AGENTS, A1, plan,
CSV contract and P0–P4/repair reports. Applied cloud-runtime, frontend-design,
FastAPI and Python-testing guidance. Design-taste dashboard exclusions were
respected; no framework migration or remote assets were introduced.

## A1 accounting and durable input

The supplied input remains unchanged: SHA-256
`f2e963046de586df6e187a33cac12ba3900c60d5a408066b50bc5fe2f896f3fe`.
UTF-8 without BOM, comma, 918 logical records; columns `date`, `session_id`,
`time`, `customer`, `national_code`, `query`, `bots_answer`, `دسته بندی`.
Explicit query/session/date/time mapping uses the same-named fields. Other
columns are excluded. There is no role or assistant-completion-time mapping;
nonempty `bots_answer` is not evidence that a reply preceded another turn.
No failure/feedback filtering or answer generation was performed.

User-confirmed Jalali/Asia/Tehran timestamps all parse: 918 valid, zero missing,
malformed or unresolved; 560 sessions; no equal-time groups in this input;
68 duplicate query occurrences retained separately. History states are
560 unavailable and 358 user-only. A1's 10 prepared rows are its bounded
chronological sample, 857 are pending model preparation, and 51 have a
conservative subject/ellipsis guard plus unavailable context. The 51 are not
knowledge gaps or evidence that all user-only conversations are unusable.

A2 reuses the A1 history provider and production preparation components.
Only preceding same-session events enter history; current/future/equal-cutoff
events are excluded unless an explicit authoritative sequence establishes order.
Timezone/calendar and chronology uncertainties remain recorded. No latest-state
history or fictional assistant replies are injected. Scope can review an A1
ellipsis rejection only when the actual original has an explicit banking subject
and the scope decision confirms self-contained meaning. A subject-free follow-up
cannot pass this guard. Incomplete history alone is not a blanket veto.

Durable root: `/root/projects/faq-private/knowledge-coverage` (configured).
Directory permissions 0700; files 0600, owner-only, no symlink traversal;
outside Git, `/tmp` and static roots. A1 archive
`archive/a1_f9dc536c1ebc9ba52dd00069c9cefdc9` contains byte-identical validated
preparation/snapshot manifests and redacted content plus its protected privacy
key; per-file SHA-256 checks passed. Dataset
`d_62ca6afb6cb231e3105f8aa4746ac3b0` preserves every original row identity/order,
UTC time and opaque session reference. Only mapped redacted events are stored;
the raw CSV was read transiently in memory, not copied to the durable store.

Regex redaction preserves consistent keyed placeholders and handles the
repository's supported identifiers/authentication/banking patterns. It cannot
reliably recognize every unlabeled name, address, amount or sensitive fact.
Artifacts therefore remain private even after redaction; redaction-changed full
witnesses require review. Fixed error codes replace exception text/model output
dumps. Audit HTTP bodies and arbitrary resource path text are not logged;
existing Uvicorn access logging is disabled.

## Model/evidence/retrieval behavior

Rubric `coverage-rubric-2`; schemas `scope-1`, `aspects-2`, `batch-1`,
`reconciliation-1`, `verification-1`; segmenter `answer-sentences-1`.
See [A2_RUBRIC_AND_SCHEMAS.md](A2_RUBRIC_AND_SCHEMAS.md) for rules and synthetic
examples. Prompts/schemas have distinct hashes. Strict JSON validation, entry/
aspect membership and snapshot-numbered citation checks precede judgments.
Customer/KB strings cannot authorize tool actions or change the rubric.

Snapshot identity is preserved from A1:
`41bffc05e91c02e288c81f23a45606de54746ead33e11e9ddb24b7d2402e16ef`;
1,526 complete redacted records with source content hashes/taxonomy;
67 source records changed under redaction. PostgreSQL capture uses read-only
REPEATABLE READ with actual transactional content matching bracketing
source/index signatures. A signature alone is not the content snapshot.

Production baseline calls the actual configured retrieval and context-selection
path. In this pilot that yielded 50 candidates and 10 selected contexts, using
question/category/subcategory rerank text. Baseline sufficiency is evaluated
independently, including equivalent evidence from different IDs. It is not a
check for overlap with the audit witness, nor proof of actual customer-answer
quality. Audit overrides are request-local 150/150/150, full-pool unchanged
reranking, up to 50 initial entries; unresolved eligible rows broaden to
300/300/300, globally reranked. Only newly encountered audit entries are evaluated
after expansion; old supports remain. Distinct evaluated entries include the
baseline and never exceed the selected budget (maximum 300).

Each model batch contains at most five full Q/A entries plus metadata, with
fewer when needed. Full messages/rubric/schema/conditions are counted by the
served vLLM `/tokenize` chat template; counts must match completion prompt usage.
Actual served limit was 8,192 tokens, reserved output 1,200, margin 128.
No character-count estimate or silent fact truncation is used. An oversized entry
or evidence bundle is explicitly unresolved. Complementary bounded bundles
preserve aspect/source mapping and source content. Compatibility checks conditions,
dependencies and contradictions; every proposed full result gets verification.
Rejected/ambiguous verification remains review-needed. Partial CSV evidence is
also cited, without claiming its combined conditions establish full coverage.

Source/index signatures are checked around retrieval and at successful row end;
retrieved raw-content hashes must match the frozen source records. Detected
source/index/serving/code revision drift makes a run incompatible and withholds
positive conclusions. Qdrant remains live: bracketing checks cannot freeze it
or prove absence of transient ABA writes/physical-ID-only changes. Immutable
weights/tokenizer revisions were not exposed, so identical served IDs cannot
prove identical weights. Full-run acceptance must address these limitations.

## Actual staging pilot

Services were restricted to previously confirmed loopback staging targets,
matching root `.env`, including reranker. CLI construction bypassed FastAPI
lifespan, DB initialization and the answering graph. Only read-only KB/source/
index operations, preparation and audit model calls ran. Calls were sequential
and used existing admission controls. No full-dataset model/retrieval run occurred.

Selection `a2-pilot-strata-1` sorts a stable hash of source row IDs, then picks
available-history and query-length strata with banking-subject vocabulary as a
sampling hint. It excludes invalid/A1 unresolved records from this initial
eligible pool but retains them in exports. It never reads answer/feedback/failure
columns. The following FIVE distinct IDs were used in both runs, with necessary
preceding history. No additional input query was modeled after them.

| Source ordinal / opaque row ID | Final outcome | Distinct evaluated entries | Audit model calls | Prompt / output tokens | Row time |
|---|---|---:|---:|---:|---:|
| 387 / `row_bd526b97ad9940b1d6a15871aac7b0ab` | Excluded: private account lookup | 0 | 1 | 863 / 74 | 3.703 s |
| 518 / `row_db3be7cdd0b505a4def0a73355236a6f` | Error: `invalid_model_schema` in batch | 130 | 51 | 117434 / 6088 | 242.474 s |
| 486 / `row_7a55dfd6fb2e3bf750d99fa30e975d30` | Covered and reachable; verified full | 10 | 10 | 19181 / 2697 | 105.570 s |
| 320 / `row_85acf8adf43bd6feb04d01f90927b68e` | Error: `invalid_model_schema` in batch | 0 validated entries | 3 | 4390 / 1044 | 46.339 s |
| 121 / `row_dedce881f722f95251e3f326f002f465` | Possible partial gap; candidates exhausted | 300 | 64 | 175552 / 5973 | 258.754 s |

The first selected query has user-only preceding history; others have unavailable
history but self-contained questions. Zero validated entries for ordinal 320
means its first batch failed schema validation; it does not mean no records were
sent. Entries in malformed batches do not become validated coverage evidence.

First run `r_47f449d49cddbd569dd6b7ffa1811c86`, rubric 1/aspects 1, stopped
at scope/aspects: one exclusion, four aspect ambiguities. It made 10 vLLM
completions and 5 embedding POSTs, 7,744 prompt / 739 output tokens; no retrieval
or batch coverage. This exposed confusion between an unknown requested answer
and an unclear question. Aspect rubric 2 clarified that distinction; the first
run and its original files are retained rather than presenting it as end-to-end.

Final run `r_d67252eb2cfc6c33d849dc6c030964e5` ran from
05:08:00 to 05:19:15 UTC on 2026-10-14 (about 675 seconds). Actual POST calls:
**130 vLLM completions, 15 embedding, 28 reranking**. The 129 structured audit
calls were scope 5, aspects 4, batches 96, reconciliation 22, verification 2;
127 validated, 2 schema failures. One additional completion was history rewrite.
All returned completions together used **319,028 prompt / 15,890 output tokens**.
Both full verifications accepted (independent baseline and audit proofs for the
same covered query); no other full verdict was accepted. Reconciliation executed
on unresolved complementary evidence without establishing another full proof.
Two rows reached broader 300 candidates; one then failed schema validation.
Audit token peak was 3,477 prompt / 840 output; every recorded preflight plus
reserved output/margin fit 8,192. Tokenization/signature metadata requests are
not included in the model/embedding/reranking POST counts above.

Across both runs, the same five distinct queries caused 140 completions,
20 embedding and 28 reranking calls, 326,772 prompt / 16,629 output tokens.
This is an operational pilot, not a paired performance benchmark, GPU/capacity
claim or accuracy estimate. Repeated compatibility checks are costly; tuning
requires a separately authorized controlled A3 experiment.

## Results, export and access

Final full-input CSV: **918 rows = 1 covered/reachable + 1 possible partial gap
+ 1 excluded + 2 error + 51 needs context + 862 pending**. All five pilot rows
were preparation-completed; inherited preparation counts become prepared 15,
pending_model 852, needs_context 51. This does not mean 918 rows were replayed
through a model. Unevaluated rows retain `not_evaluated`, never coverage failure.
All recommendation cells are empty arrays with status `unassessed`.

Protected final files:
`/root/projects/faq-private/knowledge-coverage/runs/r_d67252eb2cfc6c33d849dc6c030964e5/`
contains `coverage.csv`, `export-manifest.json`, `pilot-summary.json`, per-row
results and metadata-only model/completion measurements. Export identity
`7b00b579fd7c005fadc5998aef3d66defbf3ea8f9c784bbb50e65908c9efa882`;
CSV SHA-256 `6861622361b9bcf2eda35a92ea97f3fe9d81868cbdc53d8d8851d7fbe247e7ca`.
Configuration ID `b7466c5c210725502db688496a555a22ce7d859782429382d4cb3de1f81ffa8a`.
Independent CSV parsing verified original 918 IDs/order, exactly five selection
flags, all manifest/export IDs, file hash and unassessed recommendations.
All inspected durable run permissions were 0700/0600; A1 archive hashes match.

Original pilot files are preserved in each run's `pilot-original/`. Saved-evidence
projection corrected A2 selection flags and partial citation/aspect export fields
without new inference; metadata records its code identity. Runtime configuration
manifest capture was added after the live run started, so these historical runs
explicitly label their full runtime configuration as a **post-pilot observation**,
not configuration frozen at creation. Original run code/prompt/serving hashes and
retrieval depths remain intact. New runs capture this configuration before rows
execute. An older pilot cannot resume through changed code; it becomes incompatible.

The main dashboard uses existing Jinja, sidebar, themes, local fonts/assets,
CSRF cookies, active-user authentication and same-origin checks. Uploads are
bounded streaming JSON/base64 with explicit mapping, calendar and timezone;
raw input stays in memory, no multipart spool or arbitrary server-path endpoint.
Dataset summaries, preparation states, explicit up-to-five selection, budgets,
read-only snapshot capture, progress/cancellation/retry, filters/pagination,
numbered evidence/conditions and full-row CSV/manifest downloads are functional.
RTL/LTR direction and Persian fonts/query text are supported; English interface
labels are not presented as a Persian translation. Responsive styling and focus
controls are implemented; actual visual verification remains outstanding.

Capabilities are explicit per-user `coverage_run_start`, `coverage_results_view`,
`coverage_evidence_view`, `coverage_export_download`. Default grants `{}` deny
all new access, including admins; existing role privileges are not broadened.
KB capture/start/evidence additionally require existing `kb_read`; evidence and
exports also require results access. Ownership applies to datasets, runs, rows
and exports. Identical validated snapshots may be explicitly registered for
another owner by trusted capture/operator code; no browser arbitrary-ID grant
exists. Operator namespace 0 is not a web account. To review live artifacts in
the dashboard, explicitly assign a real account when importing and grant that
account's capabilities; no real account was granted access during this work.
Results-only exports omit protected evidence arrays/reasons. No-store responses
and safe download filenames apply. Filtering never reduces the export denominator.

Existing in-process job tracking plus owner-only atomic file checkpoints and OS
leases serialize audit work without Redis/Celery/new DB schema. Completed rows
are skipped on recovery; interrupted/failed attempts replace the same row ID.
Cancellation is persisted and checked before sequential model calls. Stale running
leases are detected; recovery is explicit, not automatic boot-time replay.
This is row-level recovery: partial remote calls can repeat after interruption,
and there is no exactly-once remote inference guarantee or cross-host durable queue.
Queued-before-crash recovery may require explicit operator retry; retention and
large-run traffic/lease hardening remain later acceptance work.

## Exact checks executed

Environment prefix for Python commands:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Final combined synthetic/regression command (actual result **394 passed,
203 subtests passed, 39 warnings, 21.11 seconds**):

```bash
python -m pytest tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py tests/test_structured_logging.py tests/test_offline_frontend.py -q
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit main.py kb_manager.py web_permissions.py web_auth.py mass_answer_jobs.py scripts/knowledge_coverage_pilot.py scripts/validate_environment.py scripts/audit_offline_frontend.py utils/http_logging_middleware.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py
node --check static/js/knowledge_coverage.js
git diff --check
git diff --cached --check
```

Node results: 3 audit, 6 KB, 5 analytics tests passed. Offline frontend audit
passed, zero external runtime dependencies. Compilation/JS syntax and Git
whitespace checks passed. Regression coverage includes P1–P4, A1 chronological
prep/parity/privacy/CSV/snapshot, taxonomy/permissions/configuration, lifecycle
and logging. A2 synthetic cases cover complementary cross-batch facts, conflicts,
equivalent production sources, referrals, false-full rejection, malformed schemas,
bad citations/injection, token overflow, drift, cancellation/recovery/lease,
owner/CSRF/default deny, partial citations and full-row CSV identity. Served-token
counting is tested with mocked HTTP; comprehensive model outputs are mocked.
Existing deprecation/NVML warnings are not pass failures.

An early expectation assumed one verifier call where independent baseline and
audit each correctly required one; the test was corrected. A logging assertion
needed the async logging queue flushed. A sandboxed TestClient run hung and was
interrupted; the complete suite above ran with approved socket access and passed.
No failed check is represented as a pass.

Actual CLI commands:

```bash
python scripts/knowledge_coverage_pilot.py import-a1 --a1-directory /tmp/ragbot-a1-final-20261013 --csv /root/projects/faq/Eval_System_Test.csv
python scripts/knowledge_coverage_pilot.py pilot --dataset-id d_62ca6afb6cb231e3105f8aa4746ac3b0 --snapshot-id 41bffc05e91c02e288c81f23a45606de54746ead33e11e9ddb24b7d2402e16ef --entry-budget 300 --confirmed-staging
```

The pilot command ran twice on the same selected IDs as described above.
Protected regeneration/hash verification used a local temporary operator script
with no service/model calls; original exports were retained. It is not an
additional preparation/evaluation pipeline.

Actual browser checks were **unperformed**: no browser binary/Playwright was
available. `python -m pip install --target /tmp/faq-a2-browser playwright`
failed after download timeouts; no application dependency changed. DOM/transport
checks exercised upload/progress/results/evidence/export/Escape focus/RTL controls,
but do not prove painted layout, contrast, real browser keyboard behavior or
Excel import. No private screenshots were saved. Browser/Excel checks remain
planner-review blockers for visual/export acceptance.

## Configuration and next review

Five permanent variables were added with documented defaults/ranges in
[ENVIRONMENT_VARIABLES.md](../configuration/ENVIRONMENT_VARIABLES.md): artifact
directory, explicit grant JSON, upload-byte limit, reserved model output tokens
and token margin. Updated `env.example`, `Production_ENV`, `.env.example.generated`
and validator specs; the generated-named template is source-authored, with no
automatic generator to update. Existing private `.env` and `.env_latest` received
only missing keys; previous values remain intact. Neither private file is
committed and the deleted staging template was not recreated. Effective settings
and safe grant/config/code/prompt identities appear in run/export manifests.

Recommended next pilot scope, only after planner authorization: inspect the two
strict schema failures using privacy-safe schema diagnostics; validate scope,
aspects and witnesses against the frozen snapshot with authorized human reviewers;
run actual browser/RTL/keyboard and spreadsheet checks; then repeat a small
explicit varied sample with all identities frozen at creation. Calibration,
evidence-combination/call-efficiency tuning, traffic interference, immutable model
revisions, retention and full-run hardening remain outstanding. Do not infer
whole-KB absence, human accuracy or full-dataset readiness from these five queries.
