# A5 main-dashboard refinement and complete export validation

Status: **implemented for planner review with the limitations below**.
Branch `a5/coverage-dashboard-export`; verified direct base
`1cc29650b83c8ea8386960451dad5ef7628117c3`. The commit containing this report
is the review commit; the handoff supplies its verified local/remote full SHA.
No historical commit, run, coverage verdict or export was rewritten.

**Actual model dispatches: zero.** There were no inference capability probes,
retrieval calls, production/data-service calls, KB writes, factual-answer
generation, deployment, shared-service restarts, A6 work or full-input model runs.
Browser/backend tests use local synthetic authentication, artifacts and mocked
responses. Their simulated pilot is functional validation, not staging inference
or independent human labeling. Coverage/recommendation prompts, model settings,
retrieval behavior, eligibility rules, existing role privileges and pilot limits
are unchanged.

## Main-dashboard changes

The existing FastAPI/Jinja page keeps its branding, local fonts/icons, themes,
authentication and navigation. The repository frontend-design/testing/FastAPI
guidance was applied; design-taste's dashboard exclusion was respected. No
framework migration or external runtime asset was introduced.

- Input preparation remains separate from coverage evaluation. Run counters show
  imported queries, processed pilot numerator/denominator, pending rows, covered
  reachable, covered requiring retrieval work, possible gaps, context/review and
  excluded/errors. Completed-with-errors differs from a clean completed pilot;
  failed/interrupted/cancelled pilots have explicit labels.
- Query details keep a compact, scrollable selected-question header and accessible section links:
  assessment, aspects, numbered sources and question proposals. Native expandable
  groups keep technical provenance/validation separate. Source links open their
  collapsed source group before navigation. Conditions and surrounding numbered
  sentences remain available. Long table questions have a six-line preview; the
  selected query/full query forms remain readable in details, including multiline
  Persian and ZWNJ. Long selected text scrolls without hiding the rest of review.
- A new **Run download** section chooses a common frozen coverage source, per-row
  draft and review revisions, then displays a full-denominator summary before
  download. Coverage-only and single-draft downloads remain explicitly labeled;
  neither claims to include all other drafts.
- Direction switching changes reading direction only (`dir`); labels stay English
  and `lang=en`. Tables scroll within labeled, keyboard-focusable regions.
  Tablet navigation collapses at 900px; desktop branding remains intact.
- Request sequence/view guards discard stale row/run/source responses and stale
  errors. Same-view progress calls do not overlap. Import polling stops on view
  changes. Closing/detaching a recommendation panel stops its polling; completed
  old requests cannot repaint a newly selected query. Review returns focus safely.

The initial synthetic browser wait exposed progress remaining unpainted during
overlapping requests/stale import status. The narrowly scoped UI guards and a
deterministic delayed-response regression correct that interaction. No worker,
service-admission, cancellation policy or retrieval changes were made. No latency
or load-performance improvement is claimed from these functional observations.

## Run-level revision-selection semantics

`RunExportStore` uses the existing protected file/lease conventions and shared A1
encoder. A4's existing recommendation row projection was extracted unchanged into
a reusable helper, so both export paths share question/taxonomy/review serialization.

The caller explicitly pins one `rev_` coverage export and a list of selections:
source-row ID, `rec_` draft revision, required `rvw_` review revision ID (or the
explicit empty value meaning unreviewed/no decisions). No mutable latest review
is inferred. Duplicate row selections are rejected; each row can select at most
one draft revision, whose multiple proposals remain JSON within that row.

Draft creation from query details now uses the source selected in **Run download**.
It requires the user to select/freeze one first, rather than silently capturing an
unrelated source on every row. Existing draft revisions retain their source and
are shown with their revision/source distinction.

Before capture, every selected draft must match the same run, exact coverage
export revision/ID, CSV hash, source-manifest hash, row hash and snapshot. A later
otherwise-identical coverage capture is still a different source. Incompatible,
unknown, duplicate or unfinished selections receive explicit safe errors. Finished
error/interrupted drafts can be pinned for traceability; their empty proposals,
error state and non-approvable status remain explicit. Existing A4 freshness and
stale-policy checks still project review-needed outcomes without changing history.

The preview/capture summary shows every source row, coverage-evaluation count,
pending/excluded/context-review/error counts, selected draft rows and proposal
review states. It also discloses every unselected/incompatible row/draft combination.
Preview is advisory; capture revalidates and records its actual summary. Selected
draft/review reads share deterministic draft locks. Immutable source rows are not
read from mutable checkpoints while serializing. No pagination/filter parameter
can reduce the export denominator.

## CSV, manifest and access projection

New schemas: **`coverage-run-csv-1`**, **`coverage-run-manifest-1`**; new immutable
revision namespace `runex_`. Both download URLs pin the same revision. The manifest
contains `revision_selection_map` keyed by source row, draft/result/row/review
hashes, original code/prompts/model-serving identities, coverage source identity/
manifest/hash, snapshot, complete ordered IDs, counts, capture state/time and
permission projection. Coverage prompt/rubric/configuration fields remain the
original coverage fields, separate from recommendation provenance.

Coverage and production dimensions, requested/supported/missing aspects,
references/conditions, evaluation scope/budget/stopping reasons, errors and all
pending/context/excluded rows survive. Question/category/subcategory, proposed
new paths, related/equivalent IDs and per-proposal review are JSON cells. Multiple
proposals never multiply source rows. Eligibility/projection reasons and approval
availability are explicit. Independent gap confirmation remains `not_reviewed`
and real-query calibration pending. Approval concerns a question/taxonomy proposal;
it approves no factual answer, KB write or confirmed whole-KB absence.

UTF-8 BOM, comma/quoted CRLF records, Persian/ZWNJ, quotes/newlines, structured JSON,
formula protection and source ordering use the shared encoder. New coverage-source
and run manifests add `csv_display_policy=formula-prefix-map-1` and
`csv_escaped_cells`: only row IDs/field names where formula protection actually
added an apostrophe, never cell values. Decoding can now preserve an original
literal apostrophe exactly. Effective leading whitespace/control/bidi formula
prefixes are tested. Legacy manifests lacking this map retain their old decoder;
an original leading apostrophe may be retrospectively ambiguous. Old bytes are
not repaired or regenerated.

Five new routes use existing authentication, current default-deny results/export
capabilities, CSRF on POST, run ownership and safe fixed diagnostics:
`export-options`, `combined-export-preview`, `combined-export-revisions`,
`combined-export`, `combined-export-manifest` under `/api/knowledge-coverage/runs/{run_id}`.
Evidence additionally requires evidence permission and `kb_read` at every request.
An owner may select frozen source/draft identities without evidence privileges;
the server produces a separate restricted projection without disclosing the
privileged source bytes. Evidence, notes, gaps, proposal text/taxonomy and phase
maps are withheld. Grant revocation cannot retrieve an earlier privileged pair;
revoked export privilege denies both downloads. Existing single-revision routes
and historical bytes remain intact. No arbitrary server-path endpoint is added.

New pairs live in each protected run's `combined-exports/{evidence,restricted}/runex_…/`:
directories 0700, files 0600, outside Git/static. No root private run export was
created in A5; browser/test artifacts are isolated under `/tmp`.

## Row accounting and independent checks

| Check | Total | Coverage evaluated | Pending | Excluded | Context/review | Errors |
|---|---:|---:|---:|---:|---:|---:|
| Prescribed synthetic mixed-status fixture | 918 | 4 | 910 | 1 | 2 | 1 |
| Actual browser's mocked five-question pilot | 918 | 4 | 912 | 0 | 0 | 2 |
| Existing A2.2 customer run, read-only | 918 | 3 covered observations | 862 | 1 | 51 | 1 |

Coverage-evaluation counts overlap outcome categories; they are not a disjoint
sum. The browser has one failed selected evaluation plus one invalid imported
query, explaining its two errors. Five processed pilot rows never means 918
evaluations. The mixed fixture explicitly tests excluded/review/context and
covered-unreachable dimensions; browser models are deterministic fictional mocks.

Tests preserve exact 918 distinct row IDs/order, duplicate query text, no row
multiplication, mixed proposal reviews, proposed-path flags and empty unavailable
recommendations. Both Python CSV and independent pandas C-parser checks validate
row IDs/order and JSON/multiline content. Browser downloads are independently
parsed again and SHA/export IDs checked against their immutable manifest.
Changes to reviews and live row checkpoints after capture leave old bytes intact.

The protected customer check read only existing run
`r_bcc2b95676b8184e3bb4e6f7d25d8b84`, its 918 checkpoints and one existing
CSV/manifest pair: exact ordered row conservation/hash/identity passed. It copied
no query contents into this report, fixtures or screenshots and regenerated no
historical export. All **4,756** pre-A5 private artifact files and the preserved
`.env`, `.env_latest`, raw CSV and user's `.gitignore` hashes were checked unchanged.

**Native Excel/LibreOffice validation was not performed.** No `excel`,
`libreoffice`, `soffice`, `gnumeric` or `ssconvert` executable is installed. Parser
checks are not presented as native spreadsheet application acceptance.

## Exact validation commands and outcomes

All Python commands use:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

```bash
timeout 240 python -m pytest tests/test_knowledge_run_export.py tests/test_knowledge_recommendations.py tests/test_knowledge_coverage_calibration.py tests/test_knowledge_coverage_reliability.py tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py tests/test_structured_logging.py tests/test_offline_frontend.py -q
python -m pytest tests/test_knowledge_run_export.py -q
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit tests/test_knowledge_run_export.py tests/knowledge_run_export_browser_app.py
node --check static/js/knowledge_coverage.js
node --check static/js/knowledge_recommendations.js
node --check static/js/knowledge_run_export.js
node --check tests/knowledge_run_export.browser.cjs
git diff --check
git diff --cached --check
python -m tests.knowledge_run_export_browser_app --port 18765
node tests/knowledge_run_export.browser.cjs /tmp/faq-a21-browser-node http://127.0.0.1:18765 /tmp/faq-a5-browser-final
```

Final backend result: **545 passed, 203 subtests passed**, 39 warnings, 39.30 s.
Frontend DOM contracts: **5 coverage / 6 KB / 5 analytics passed**; the fourth
coverage test explicitly delays progress/row/run responses, verifies non-overlap
and read-only evidence users without export controls. The fifth delays CSV upload
while another run is selected; the upload cannot replace the newer view. Offline dependency audit
passed with **zero external runtime dependencies**. Compilation, JS syntax and
Git whitespace checks passed. Actual Chromium checks are described below.
Final read-only/no-export and stale-upload guards affect those negative frontend branches;
their deterministic regressions passed and does not change inference or exports.

The final focused export check, including explicit sufficient/insufficient
production-reachability round trips, passed **16 tests**, 3 warnings, 24.95 s.
The new export module contains 16 synthetic tests including parameterized formula
and taxonomy cases. Scope covers multiple row/draft/review revisions, several
proposals per row, changed reviews/checkpoints with old immutable downloads,
incompatible source/review/row identities, unfinished/error drafts, restricted
projection, privilege revocation, ownership, CSRF, Persian/ZWNJ/JSON and original
apostrophe round trips, exact denominators and CSV/manifest hashes. Relevant
P1–P4 and A1–A4 answering/history/canonicalization/configuration/privacy/consistency
regressions remain included. Comprehensive responses are mocked.

During construction, one 918-row fixture attempted to use the selected-pilot
checkpoint writer for a non-pilot import-state fixture; that identity guard
correctly rejected it. The fixture now writes explicitly prescribed non-pilot
import/checkpoint data in its isolated store. One API fixture used the same temp
capture directory as another fixture; isolating it fixed the test setup. No
production identity or correctness check was weakened. Earlier sandboxed
TestClient execution needed local IPC access; the complete suite ran with that
access. The extended screenshot harness also needed a null-safe wait while the export
selection was loading; this corrected the harness, not a model/eligibility rule.
Existing deprecation/NVML warnings are not silently treated as failures.

## Actual browser acceptance and screenshots

Isolated Chromium **153.0.8010.0** with Playwright, synthetic account 990001,
process-only test grants and an isolated loopback app; no real account or env
grant was changed. Seven actual check groups passed: upload/mapping and explicit
five-question progress; shared frozen source and two row drafts with multiple
proposals/review states; 918-row CSV/matching manifest and unchanged old bytes
after new review; incompatible-source disclosure; delayed row/run switching and
detached panel polling; 390/768/1280/1440 responsive RTL/LTR/light/dark, visible
focus/table scrolling; no page errors, KB writes or real inference dispatches.
Review votes are automated synthetic UI actions, not independent human labels.

Final browser CSV export ID: `7a17da81ca77bba10f96ab2c6747ed630b653c6f18745843827ff3d7d4a8204e`.
Revision: `runex_0e9db768dc06594061594d9a19910873`.
CSV SHA-256: `56b9da11131a8fec1b9fdf1c95a2dac14efdc2bf3cce1633f28a09cbb958de9f`.
Two selected rows each have two proposals; pinned review states are one approved,
one rejected and two unreviewed. The matching CSV/manifest retain all 918 IDs in
source order, including duplicates and errors. Independent post-download Python
CSV/pandas checks passed.

Synthetic rendered evidence:

- [1440 dark ltr](assets/a5-1440-dark-ltr.png)
- [1440 light rtl](assets/a5-1440-light-rtl.png)
- [1280 dark rtl](assets/a5-1280-dark-rtl.png)
- [1280 light ltr](assets/a5-1280-light-ltr.png)
- [768 dark ltr](assets/a5-768-dark-ltr.png)
- [768 light rtl](assets/a5-768-light-rtl.png)
- [390 dark rtl](assets/a5-390-dark-rtl.png)
- [390 light ltr](assets/a5-390-light-ltr.png)
- [run selection light](assets/a5-run-selection-light.png)
- [proposal review light](assets/a5-proposal-review-light.png)

The proposal viewport was recaptured read-only from the same completed synthetic
fixture after inspection showed an element screenshot clipped the scrollable
parent. No evaluation/review/export was rerun or changed for that capture. A final
read-only layout pass at all eight width/theme/direction combinations also
checked that the selected row identity stays below the top bar while scrolling
proposal controls. The details pane is bounded to the available viewport; long
question text scrolls inside its compact header and remains present in full.
Rendered screenshots were actually inspected, including long Persian/multiline
text, badges, table scrolling, both themes and tablet/mobile layouts. Only
fictional screenshots are committed; CSVs, manifests, authentication and other
test artifacts stay in `/tmp/faq-a5-browser-final/`. This is browser/layout/
keyboard validation, not a full assistive-technology or native-spreadsheet audit.

## Configuration, preservation and A6 boundary

**No new environment variables, role privileges or real grants.** Existing local
runtime envs and all env templates remain unchanged. Root dotenv is read through
the established project mechanism without displaying values. The deleted staging
template, user's ignore edits, raw datasets and all unrelated/untracked work are
preserved and excluded. Outgoing code/tests/docs/screenshots were reviewed for
private envs/credentials, customer content and private artifacts before commit.
Only the A5 branch is published with an ordinary push; no other branch/tag or
shared service is changed.

A5 is ready for planner code review and operational-stage planning. Independent
human gap/question quality labels, native spreadsheet acceptance, immutable model
weight/tokenizer provenance and earlier repair/release gates remain unresolved.
Larger input execution, retention/cleanup, durable worker recovery and idempotent
dispatch, broader cancellation/lifecycle hardening, admission/resource/load
validation and actual full-run readiness remain **A6**, not implemented here.
Current five-query limits, 300-entry cap and sequential model policy stay intact.

## Scoped publication files

Only these 30 scoped files are committed:

```text
docs/knowledge-gap-audit/A5_DASHBOARD_EXPORT_REPORT.md
docs/knowledge-gap-audit/DASHBOARD_AND_CSV_CONTRACT.md
docs/knowledge-gap-audit/IMPLEMENTATION_PLAN.md
docs/knowledge-gap-audit/assets/a5-1280-dark-rtl.png
docs/knowledge-gap-audit/assets/a5-1280-light-ltr.png
docs/knowledge-gap-audit/assets/a5-1440-dark-ltr.png
docs/knowledge-gap-audit/assets/a5-1440-light-rtl.png
docs/knowledge-gap-audit/assets/a5-390-dark-rtl.png
docs/knowledge-gap-audit/assets/a5-390-light-ltr.png
docs/knowledge-gap-audit/assets/a5-768-dark-ltr.png
docs/knowledge-gap-audit/assets/a5-768-light-rtl.png
docs/knowledge-gap-audit/assets/a5-proposal-review-light.png
docs/knowledge-gap-audit/assets/a5-run-selection-light.png
knowledge_audit/api.py
knowledge_audit/export.py
knowledge_audit/recommendation_store.py
knowledge_audit/run_export.py
knowledge_audit/run_export_api.py
static/css/knowledge_coverage.css
static/js/knowledge_coverage.js
static/js/knowledge_recommendations.js
static/js/knowledge_run_export.js
templates/knowledge_coverage.html
tests/knowledge_coverage.frontend.test.cjs
tests/knowledge_run_export.browser.cjs
tests/knowledge_run_export_browser_app.py
tests/test_knowledge_run_export.py
tests/test_web_permissions.py
versioned_assets.py
web_permissions.py
```
