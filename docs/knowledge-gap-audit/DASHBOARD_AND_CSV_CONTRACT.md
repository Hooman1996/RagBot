# Main-dashboard and CSV contract

Contract version `p0-contract-1`; final coverage UI/export remains a specification.
A1 adds the separate preparation-only schema below. No page, route, permissions,
jobs, database schema or framework was implemented in P0 or A1.
The primary deliverable of a completed run is a CSV with one result per selected
input row. Private internal JSON/evidence supports it but cannot replace it.

## Existing integration and design read

Reading this as an enterprise banking knowledge-review workspace for analysts
and knowledge editors: restrained, evidence-led, aligned with the existing
Negah Bank main dashboard. Its distinctive element is a requested-aspect-to-
numbered-evidence ledger that shows why a query is covered or still unresolved.
Use that structure for meaning; avoid decorative metrics, images or marketing
layouts. `design-taste-frontend` excludes dashboards and tables. `frontend-design`
guides intentional typography/hierarchy while the existing product system wins
over generic framework/font defaults.

Verified stack and integration points:

- FastAPI `main:app`, Jinja2 templates under `templates/`, same-origin vanilla
  JS and CSS under `static/`; `/app` renders `templates/index.html`, analytics
  renders `templates/analytics.html`, KB manager `templates/kb_manager.html`.
  This is separate from `evaluation_system/frontend`; do not migrate to React
  or create a separate app.
- Navigation lives in `.sidebar__nav` in index, analytics and KB templates;
  links are permission-gated with Jinja `permissions`. New page should reuse
  this shell/header, logout/theme/language controls and capability-gated link.
  A shared shell extraction can be separately reviewed if needed; not in P0.
- `static/css/base.css` tokens: base `#080d1a`, surface `#0d1526`, primary text
  `#f0f4ff`, secondary `#8b9dc3`, emerald accent `#10b981`, amber `#f59e0b`;
  spacing 4/8/16/24/32 px, standard radii 6/10/16 px. Preserve dark/light themes;
  validate text contrast rather than use muted color for critical evidence.
- Existing Inter for English UI and JetBrains Mono for IDs/data are local under
  `static/vendor/google-fonts/`. Persian Vazirmatn 33.003 is local under
  `static/vendor/vazirmatn/` and used by KB CSS. Use it explicitly for Persian
  question/evidence; do not rely on English fallback to render long Persian text.
  Headers ~22 px, body/evidence ~15–16 px, table utility labels ~13 px are proposed
  page-local scale choices, not a change to global root font sizing.
- `static/css/app.css`, `web_controls.css`, `analytics.css` and `kb_manager.css`
  provide existing shell/table/control patterns. Reuse locally available
  `static/icons.svg` symbols and bank asset if the shell needs it. No new CDN,
  framework, library installation, decorative imagery or icon family.
- `versioned_assets.py` provides asset digests/integrity and a registered asset
  list; later page CSS/JS must be registered. `VENDOR_MANIFEST.json` pins local
  vendor assets. Offline audit already passes, zero external dependencies.
- Existing frontend verification: `scripts/audit_offline_frontend.py`,
  `tests/test_offline_frontend.py`, Node analytics/KB frontend test files;
  Python auth/permission tests use ASGI TestClient with synthetic DB stubs.
  No checked-in Playwright/screenshot runner was found. Browser visual execution
  must be arranged later; static/Node tests do not prove visual accessibility.

Proposed nonconflicting page: **`GET /knowledge-coverage`**, main dashboard.
Proposed browser API family **`/api/knowledge-coverage/runs`** for start/list,
run-specific status/results/detail/export/retry/cancel, and recommendation review.
Current route inventory has no matching page/API family. Names are reserved
proposals, not routes authorized for implementation in P0.

## Authentication, permissions and ownership

`web_auth.py` validates signed HttpOnly `ragbot_web_session` and a DB active user,
SameSite strict cookies, origin and `X-CSRF-Token` derived from a nonce for unsafe
methods. `static/js/web_auth.js` adds the token to same-origin browser mutations
and handles unauthenticated redirects. New browser routes must remain inside
this boundary, not use mobile or internal-evaluation authentication exclusions.
`web_permissions.py` has an explicit method/path allowlist; unknown roles and
unclassified routes deny. Navigation visibility is not authorization.

Existing roles: admin (current listed permissions), user/moderator (chat),
analytics_viewer, knowledge_editor (KB read/write), dashboard_viewer (chat plus
analytics/KB read). None currently has audit capabilities. Do not reuse `batch`,
`analytics`, `downloads` or `kb_write` as a blanket grant for private audit data.

Proposed capabilities, assignments require later reviewed policy:

| Capability | Allowed operation / limits |
|---|---|
| `coverage_run_start` | Import/mapping validation, start/cancel/retry owned runs with allowed KB and input sources. Does not permit arbitrary DB sessions or KB updates. |
| `coverage_results_view` | Authorized run list/status and redacted result metadata for owned or explicitly shared runs. |
| `coverage_evidence_view` | Private, redacted snapshot evidence and safe query detail for the same authorized run; also requires KB/source access. Results access alone does not reveal customer history or KB excerpts. |
| `coverage_export_download` | Download sanitized complete/explicitly partial CSV for that run; requires results visibility and an appropriate evidence entitlement for fields included. No raw source-file export. |
| `coverage_recommendation_review` | Record accept/reject/edit-question-or-taxonomy review on that run; no automatic KB mutation, answer generation or global taxonomy creation. |

An evidence-restricted export keeps schema/row count but blanks restricted
evidence/justification cells with `evidence_visibility=restricted`; no links or
copied text can bypass the evidence gate. Permission checks run on every API,
download, pagination/search and detail request. Enforce owner ID and authorized
source scope explicitly; permitted reviewers need an explicit sharing grant.
Return safe 404/403 semantics without leaking run existence. DB-source access
requires separate approved source authorization, not merely permission to upload.

`main.py:require_owned_session`/`require_owned_query` provide ownership precedents.
Mass jobs use `job_access_token`/`X-Job-Access` signed per job and requester;
do not assume that alone checks stored owner or entitles cross-run evidence.
For new runs use stored-owner/grant checks and browser session authorization;
download URLs must not contain authentication secrets. CSRF covers upload/start,
cancel/retry, settings changes and recommendation review, never just the UI button.

## Jobs, progress and execution boundary

`main.py:_create_mass_answer_job` returns HTTP 202 with job/status/result URLs;
`MassAnswerJobManager.start` uses tracked `asyncio.create_task`; PG job metadata,
polling, result `FileResponse`, progress counts and TTL cleanup exist. Reuse the
concepts/transport/error vocabulary where appropriate, not the mass-answer
executor that generates answers or its schema as an unreviewed audit store.
In-process tasks disappear on restart; this is not a durable worker/resume system.

Later architecture: short request validates/stores a run manifest and enqueues
bounded work; status/results/export requests stay short. Persist per-row
checkpoint/status and worker ownership; cancellation/interruption produce
explicit rows, never disappear. For pilot a reviewed single-worker implementation
can checkpoint interrupted runs and retry safely, but must not pretend restart
recovery is automatic if absent. Add durable leases/resume before full runs.
Do not hold a normal HTTP request open for the whole audit. Enforce per-step
model budgets and per-service concurrency; do not inherit normal chat capacity
as audit throughput. No tables/queues/settings introduced in P0.

Counts use the selected input manifest as denominator: completed/invalid/excluded/
needs-context/failed all contribute terminal rows. Show rows processed of selected
rows plus error count; no fake percentage or model-confidence probability.
Record subset scope and snapshot on every view/export. Retry targets identified
failed/interrupted rows and supersedes a prior row result without adding/removing
source identities; include attempt count and final error/uncertainty.

## Proposed page composition

```text
existing sidebar | Coverage audit               theme / language / logout
                 | Input scope, snapshot, subset/full label
                 | Import & mapping / DB source / session-time policy
                 | KB scope + validated settings + Start run
                 | Run status: processed / selected; failures; retry; Download CSV
                 | Search + status / taxonomy / reachability filters
                 | Paginated result table       | Selected query & evidence panel
                 |                              | Intended/effective/retrieval text
                 |                              | Requested → supported/unresolved
                 |                              | Numbered KB evidence & verifier
                 |                              | Scope/depth/errors/recommendations
```

Inputs support query-column mapping (required), optional source query/session/
timestamp/feedback/referral/assistant columns, safe preview, parse validation,
encoding policy and source timezone configuration. Unsupported columns are not
copied into exports. Preserve the source unchanged in authorized private storage.
For DB sources expose only preapproved sources/filters; never a free-form SQL box.
Validate KB/datasource selection against run and user scope; show available snapshot
versions, and explain if mixed or non-FAQ sources require review. Settings are
validated with bounds, units and the actual served token budget. All rows selected
by default; explicit subset selection has a persistent pilot badge/description.

Main table columns: source row reference, redacted query excerpt, processing label,
coverage label, unresolved aspect count, production reachability, evaluated depth,
review/error indicator. Expand detail rather than squeeze all CSV fields into a
wide grid. Native semantic table headers, predictable pagination and visible
filter/result counts; filtering never changes download completeness.

Evidence panel shows redacted original/standalone/canonical text distinctly,
history availability, requested aspects and supported/unresolved conditions;
source titles/IDs and clickable sentence numbers anchored to immutable evidence,
support arrangement, concise justification, verifier outcome, baseline reachability,
depth/stopping reason and relevant versions. A combination of entries has a clear
aspect-to-source mapping across batches, not one unexplained list of links.
No chain-of-thought and no confidence gauges. Recommendation area shows question,
category/subcategory, new-path flags, equivalent FAQs and review controls; never a
draft answer. A snapshot mismatch disables misleading evidence and labels review.

Desktop: results plus side panel with controlled text width. Narrow layouts:
table has a bounded horizontal scroll region; detail opens as a full-width
accessible panel with return-to-row focus. Use `dir=auto`/`bdi` for mixed queries,
RTL Persian paragraphs and LTR isolated IDs/timestamps. Logical padding/alignment,
wrapping of long IDs, no reversed number/sentence ordering. Visible focus, native
controls, labeled inputs/errors, keyboard table-to-detail navigation, Escape close,
focus restoration, polite status updates, adequate contrast and reduced motion.

States: empty (choose/import source), mapping errors (identify record safely),
loading (real pending count), queued/running (real progress), interrupted/partial
(retry explanation and partial export), failed (safe code and next action),
completed (row-accounting verified download), evidence restricted/expired/mismatched.
Status text/icons accompany restrained emerald/amber/red cues; color alone never
communicates the result. Real data only; no invented success metrics or fake results.

## CSV schema v1 proposal

One ordered output row per accepted input record. `source_row_id` is assigned
before validation/deduplication from source fingerprint + record ordinal (not
physical line number: quoted newlines span lines). DB sources use a frozen ordered
selection manifest and immutable query ID; `source_query_id` may be absent or
duplicate in CSV and never replaces row identity. Safe opaque session reference
uses keyed pseudonymization scoped to run/authorized source, not a raw session ID
or unsalted hash. Row order returns to input-manifest order after parallel work.

| Stable field name | Type / meaning |
|---|---|
| `schema_version`, `run_id` | Contract version and opaque run ID. |
| `source_row_id`, `source_query_id`, `source_record_ordinal` | Unique row identity, optional sanitized/opaque query reference, 1-based CSV data-record ordinal or DB manifest ordinal. |
| `safe_session_ref`, `timestamp`, `timestamp_status` | Pseudonymous session; ISO-8601 with offset/UTC or empty; `resolved`, `missing`, `unresolved`, `ambiguous`. |
| `input_query_redacted`, `standalone_query_redacted`, `canonical_retrieval_query_redacted` | Three distinct safe textual forms; empty if unavailable/unsafe to disclose. |
| `history_status`, `scope_status`, `processing_status`, `coverage_status` | Machine-readable states below; none derived from assumed failure flags. |
| `support_arrangement`, `production_reachability` | Evidence combination and source-default selection relationship below. |
| `requested_aspects`, `supported_aspects`, `unresolved_aspects` | JSON arrays of objects with stable aspect ID, safe description/conditions and uncertainty codes. |
| `supporting_faq_ids`, `supporting_chunk_ids`, `supporting_sentence_refs` | JSON arrays of stable IDs and reference objects, never generation ordinal IDs alone. Sentence refs contain snapshot ID, FAQ/chunk ID, sentence number and aspect IDs. |
| `explanation`, `verification_result`, `verification_reason` | Concise grounded redacted explanation; `accepted`, `rejected`, `not_run`, `error`; safe short reason/code. |
| `production_candidate_ids`, `production_context_ids`, `production_baseline_version` | Separate baseline ID arrays/version; reflect retrieval/context only, not a claim of actual answer success. |
| `retrieved_candidate_count`, `evaluated_entry_count`, `stopping_reason` | Nonnegative actual counts and terminal reason below; no copied configured limit masquerading as actual count. |
| `proposed_question`, `category`, `subcategory` | JSON arrays of redacted strings aligned by recommendation index, even for one recommendation; `[]` when none. No answers. |
| `proposed_new_category`, `proposed_new_subcategory` | Aligned JSON boolean arrays; empty when not recommended. No guessed taxonomy path. |
| `related_existing_faq_ids`, `equivalent_existing_faq_ids` | Aligned nested JSON ID arrays per recommendation. |
| `recommendations`, `recommendation_status` | JSON object array with recommendation_id, question, taxonomy/new-path flags, related/equivalent IDs and review status; `not_run`, `proposed`, `reviewed`, `not_applicable`, `error`. This object representation is authoritative; aligned columns project it for users. |
| `review_reason`, `error_code`, `error_reason`, `attempt_count` | Safe review/error labels, sanitized short reason; no exception dump or credentials. |
| `evidence_visibility`, `uncertainty_codes` | `visible`, `restricted`, `expired`, `snapshot_mismatch`; JSON safe code array. |
| `kb_snapshot_id`, `kb_signature`, `taxonomy_version`, `code_version` | Immutable snapshot plus fingerprint and taxonomy/code versions. |
| `model_versions`, `tokenizer_versions`, `prompt_versions`, `rubric_version`, `normalization_version`, `alias_version`, `classifier_version`, `run_settings_version` | JSON maps for multiple model/prompt roles; other version strings/hashes. No prompt text. |
| `input_scope`, `selected_input_row_count`, `source_input_row_count` | `full`/`pilot_subset`; selected and original source counts, distinct from filtered UI count. |

All lists and multi-recommendations use compact UTF-8 JSON in a quoted CSV cell;
no pipe/comma-delimited ambiguous arrays. Unknown scalar fields are empty, known
empty arrays `[]`, map fields `{}`. Count fields use ASCII nonnegative integers;
enum values use lowercase ASCII. Status columns are independent:

| Field | Allowed initial values |
|---|---|
| `processing_status` | `completed`, `invalid_input`, `excluded`, `needs_context`, `needs_review`, `failed`, `interrupted`, `cancelled`, `pending` (partial export only). |
| `scope_status` | `kb_question`, `chitchat`, `personal_request`, `out_of_scope`, `unknown`, `routing_error`. |
| `history_status` | `not_needed`, `complete`, `user_only`, `incomplete`, `unavailable`, `ambiguous`. |
| `coverage_status` | `full`, `partial`, `possible_gap`, `needs_context`, `needs_review`, `not_evaluated`, `error`. `full` requires verifier acceptance and no unresolved aspects/conflict. |
| `support_arrangement` | `single_entry`, `within_batch_combination`, `cross_batch_combination`, `none`, `unknown`. |
| `production_reachability` | `selected_single_entry`, `selected_combination`, `partial_selected`, `retrieved_not_selected`, `outside_production_candidates`, `not_applicable`, `unknown`. Derive from whether all required supporting entries are in selected contexts, only some are, only retrieved, or outside baseline. It describes evidence availability, not generated-answer correctness. |
| `stopping_reason` | `verified_full`, `initial_pilot_limit`, `evaluation_limit`, `candidate_exhausted`, `time_budget`, `needs_context`, `scope_excluded`, `conflict`, `invalid_input`, `processing_error`, `cancelled`, `interrupted`, `pending`. |

`possible_gap` means unresolved aspects after a recorded bounded search, not
global KB absence. Invalid/excluded rows have `not_evaluated`, zero evaluated
entries and explicit reasons. Verifier/error/context uncertainty cannot be
silently labeled `full` or counted as uncovered. Full runs may include failed rows
and are labeled completed-with-errors when row accounting is complete.

## Row accounting and export safety

Manifest invariant: selected record count equals exported row count, and the
multiset of exported source_row_id equals selected manifest IDs exactly once.
Check both counts and IDs (equal counts can still hide replacement/duplication).
Accepted CSV blank data records are retained as invalid input; mapping/type/
timestamp errors receive rows. File-level syntax failures that cannot establish
record boundaries are rejected before run acceptance with safe location details;
do not fabricate identities for unparseable bytes. Preserve original file bytes
and hash privately; no source-file mutation.

Deduplication key includes effective meaning, canonical wording, chronological
history digest/completeness, scope/snapshot, versions and settings; identical text
in different histories is not automatically equivalent. Row-specific identity,
timestamps and safe session references remain separate in CSV. Retries supersede
the same row, never append additional final rows. Partial/interrupted downloads
still represent **every selected row**, using pending/interrupted/cancelled states
as appropriate. Label partial filename/UI state and do not present it as a final
full run. Final download is enabled when no pending rows remain and accounting
passes; an explicit failed/invalid result is a terminal row, not a reason to drop it.

Use Python `csv` or the established safe writer after verifying compatibility
(`mass_answer_files.py:write_safe_output` is a precedent, not sufficient unchanged:
it uses LF records and its `_neutralize_formula` checks only direct leading
formula characters, without whitespace/control-prefix handling).
Use comma separator, double quotes escaping double quotes, CRLF records and
UTF-8 with BOM (`utf-8-sig`) for Excel Persian compatibility; proper quoted
multiline cells. Readers should use UTF-8-sig to consume BOM. Test Persian letters,
ZWNJ, mixed LTR, commas, quotes and embedded newlines with independent reader
round trips and an actual Excel/import check when available. No locale-dependent
semicolon substitution without explicit schema policy.

CSV quoting alone does not prevent spreadsheet formulas. On **every exported
untrusted text cell** (including IDs, proposals, reasons and model-derived text),
inspect the first effective character after leading whitespace/control/bidi
format characters; protect `=`, `+`, `-`, `@` and leading tab/CR/LF by prefixing
an apostrophe to the entire cell. Do not destructively strip Persian text or
leading characters from source. Serialize JSON arrays/maps first, then apply
cell-level protection; JSON wrappers keep embedded strings inert, but must still
be tested with spreadsheet readers. Typed enum/count/boolean fields are generated
from validated values. Document export protection as a display transformation;
safe internal text remains distinguishable from an apostrophe-prefixed CSV view.

Never blindly repeat all source columns: export only mapped sanitized fields,
redacted queries/proposals/justification and safe source references. Apply
approved redaction before storage/render/export; automated detection alone is not
proof that banking data is safe. If redaction changes meaning materially, mark
review/uncertainty and retain protected original only in authorized private
storage. Operational telemetry uses opaque run/row references, counts, timings,
service/request sizes, versions and safe error codes, never CSV content.

Download requires run/owner/capability checks, no-store headers, safe attachment
filename, and private artifact path checks against traversal. Pagination/filtering
never restricts the CSV to the visible page. Evidence IDs must resolve against the
run snapshot; mismatches are labeled, not repaired by showing current KB content.
Retention/expiry affects detail and export consistently. CSV version changes need
an explicit migration/compatibility contract, not silent header changes.

The A2 pilot must ship this functional page and initial schema-conforming CSV;
A3/A4 extend evaluation/recommendations, A5/A6 refine and harden. Every stage is
reviewed independently. P0 stops with these documents and baseline observations.

## Implemented A1 preparation export

`knowledge_audit.export.export_preparation` implements `a1-preparation-csv-1`
and `a1-preparation-manifest-1`, distinct from the final coverage schema v1.
Every selected CSV user record appears exactly once in original record order,
including invalid records/unknown roles and preparation failures. Explicit
assistant/system records are history-only. Unknown roles retain invalid selected
results rather than silently disappearing.

| Fields | A1 meaning |
|---|---|
| `schema_version`, `run_id`, `export_id` | Preparation schema, opaque run, shared manifest/export content identity. |
| `source_row_id`, `source_query_id`, `source_record_ordinal`, `processing_ordinal` | Dataset-byte identity plus ordinal; optional keyed opaque query reference; separate source/processing order. |
| `safe_session_ref`, `timestamp`, `timestamp_status`, `timestamp_provenance` | Keyed run/source session; UTC timestamp or empty; resolved/missing/invalid/unresolved/ambiguous; parser/calendar/timezone/source-offset provenance. |
| `input_query_redacted`, `normalized_query_redacted`, `standalone_query_redacted`, `canonical_retrieval_query_redacted` | Distinct original, normalized, history-resolved semantic and eligible alias retrieval wording. Unavailable forms remain empty. |
| `existing_intent`, `scope_status` | Existing classifier result; scope only `chitchat` or `unknown`; no new scope classification. |
| `processing_status`, `coverage_status`, `preparation_status` | Always `preparation_only`; coverage empty; preparation `prepared`, `pending_model`, `needs_context`, `uncertain_preparation`, `invalid_input` or `failed`. |
| `model_selected`, `model_prepared`, `rewrite_status` | Bounded selection and actual successful preparation booleans; rewrite/not-run/fallback/context state. Selection alone does not prove a service call. |
| `history_status`, `history_provenance` | User-only/incomplete/unavailable/ambiguous; cutoff, preceding row IDs/digest, ordering/time uncertainty, redaction and capture limitations. No history text is copied into the CSV. |
| `preparation_errors`, `uncertainty_codes` | JSON arrays of fixed safe diagnostic codes. |
| `kb_snapshot_id`, `configuration_id`, `preparation_code_id`, `input_id` | Frozen content, effective configuration, base plus exact source hashes, input bytes identity. |
| `input_scope`, `selected_input_row_count`, `source_input_row_count` | Full input preparation with bounded model sample; selected/source denominators; manifest lists exact selected/sample IDs. |

CSV uses UTF-8 BOM, comma separator, quoted cells, CRLF records, JSON cells and
effective-leading-character formula protection. Typed generated opaque IDs are
preserved; query text is redacted before storage. Formula protection is a display
transformation. Manifest includes file hash, counts/mapping/time policy, runtime
configuration, code/artifact hashes, snapshot and obtainable serving identities.
No arbitrary source columns or coverage/recommendation fields are projected.
A2 must create its distinct coverage schema and preserve complete row accounting.

## Implemented A2 pilot contract

Implemented A3 versions `coverage-page-2`, `coverage-csv-4`,
`coverage-export-manifest-4`, rubric `coverage-rubric-4`. This section specifies
the shipped pilot where it is narrower/different from the future v1 proposal
above. See [A2_END_TO_END_PILOT_REPORT.md](A2_END_TO_END_PILOT_REPORT.md) and
[A2_RUBRIC_AND_SCHEMAS.md](A2_RUBRIC_AND_SCHEMAS.md) and
[A2_1_CORRECTION_REPORT.md](A2_1_CORRECTION_REPORT.md) for executed evidence/rules.
The bounded reliability follow-up is in
[A2_2_MODEL_RELIABILITY_REPORT.md](A2_2_MODEL_RELIABILITY_REPORT.md).
No recommendations, DB input implementation, factual-answer generation or
full-dataset model run is included.

### Page, permissions and routes

`/knowledge-coverage` is part of the main FastAPI/Jinja dashboard with local
styles/scripts/fonts, existing sidebar/themes and capability-gated navigation.
It supports explicit CSV mapping, calendar/timezone/order assumptions, dataset
summary/preparation counts, up-to-five explicit pilot row selection, document
scope and 1–300 entry budget, snapshot capture, progress/cancel/retry, result
filters/pagination, numbered evidence/conditions and full-row downloads.
RTL/LTR direction and Persian text rendering are supported; interface labels
remain English. A2.1 includes actual synthetic Chromium visual/keyboard/RTL,
theme, responsive and download checks. Excel application validation remains
unperformed; automated BOM/quoting/formula tests passed.

Existing roles, including admin, acquire no audit privileges by default.
`KNOWLEDGE_COVERAGE_ACCESS_GRANTS={}` denies all new access. Explicit positive
web-user-ID grants use the four agreed capabilities. Authentication, active
user, CSRF, same-origin and owner checks apply; unknown routes remain denied.
The operator namespace 0 does not represent a web account. Identical validated
snapshots can be explicitly registered for multiple owners by trusted operator/
capture code; datasets and runs remain single-owner.

| Method / route (prefix `/api/knowledge-coverage`) | Required access |
|---|---|
| GET `/knowledge-coverage` (page, without API prefix) | results-view |
| POST `/datasets` | run-start |
| GET `/datasets`, GET `/datasets/{dataset_id}/rows` | results-view, owned dataset |
| GET/POST `/snapshots` | run-start + existing `kb_read`; owned catalog / read-only capture |
| POST `/runs` | run-start + `kb_read`, owned input/snapshot, explicit row IDs/scope |
| GET `/runs`, GET `/runs/{run_id}`, GET `/runs/{run_id}/results` | results-view, owned run |
| POST `/runs/{run_id}/cancel`, POST `/runs/{run_id}/retry` | run-start, owned run |
| GET `/runs/{run_id}/rows/{row_id}` | evidence-view + results-view + `kb_read`, owned run/row |
| GET `/runs/{run_id}/export`, GET `/runs/{run_id}/export-manifest` | export-download + results-view, owned run; evidence entitlement controls projection |
| POST `/runs/{run_id}/export-revisions` | export-download + results-view, CSRF, owned run; capture a new immutable permission-specific pair |

Names above abbreviate `coverage_run_start`, `coverage_results_view`,
`coverage_evidence_view`, `coverage_export_download`. Twenty routes are
registered, including the page. Upload transport is bounded streamed JSON with
base64 CSV bytes and explicit mapped column names; accepted bytes stay in memory
until mapped/redacted. There is no multipart spool, raw upload download, arbitrary
server-path read or browser snapshot-grant interface. Operational logs never
contain audit bodies or caller-supplied resource path text. Responses/downloads
use no-store, safe attachment filenames and ordinary owner/permission checks.

### Row preservation and implemented dimensions

The shared A1 exporter supplies UTF-8 BOM, commas, quoted CRLF records,
multiline/Persian round-trip, JSON cells, effective-leading-character formula
protection and exact row/export identity checks. Source query/session references
remain opaque; original arbitrary source columns are not projected.
One row per selected input user record appears in original order, including
duplicates/invalid/excluded/errors/pending. Explicit assistant/system messages
are history-only; unknown roles retain invalid selected records. Filtering and
pagination never reduce the CSV. Full imported pilot exports retain all 918
input queries although only five are selected for model evaluation.

| Field / group | Implemented meaning |
|---|---|
| A1 identity/query/history/preparation columns | Preserved mapped source lineage, distinct original/normalized/resolved/retrieval query forms, timestamps and cutoff provenance; preparation status and actual model-prepared flag. `model_selected` refers to this A2 pilot; immutable A1 selection is retained in its archive. |
| `processing_status` | `pending`, `running`, `completed`, `invalid_input`, `excluded`, `needs_context`, `needs_review`, `failed`, `interrupted`, `cancelled`. Run state also has `queued`, `incompatible`. |
| `scope_status` | `kb_question`, `chitchat`, `out_of_scope`, `private_account`, `needs_context`, `uncertain`; inherited unevaluated preparation may carry `unknown`. First-person procedure is not automatically private-account. |
| `coverage_status` | `full`, `partial`, `unsupported`, `uncertain`; unevaluated `not_evaluated`, excluded coverage unset. Batch model label `none` becomes question-level `unsupported`. |
| `outcome` | `covered_reachable`, `covered_not_reachable`, `possible_partial_gap`, `possible_gap`, `needs_context`, `needs_review`, `excluded`, `pending`, `error`. Missing preceding subject/history uses needs-context; scope uncertainty, conflicts, verification/runtime problems use needs-review. Neither becomes a gap. |
| `support_arrangement` | `single_entry`, `within_batch_combination`, `cross_batch_combination`, `none`, `unknown`. Arrangement describes evidence locations, not proof of compatible conditions. |
| `production_context_sufficiency`, `production_reachability` | Independently evaluated baseline coverage; reachable `sufficient`, `insufficient`, `uncertain`, `unknown`. Equivalent source facts may use other IDs than the audit witness. |
| `requested_aspects`, `supported_aspects`, `unresolved_aspects` | JSON aspect objects with stable IDs, descriptions/conditions; supported objects include structured supports/applicability/dependencies and numbered citations. Evidence is retained for partial results too. |
| `supporting_faq_ids`, `supporting_chunk_ids`, `supporting_sentence_refs` | Snapshot/FAQ/chunk/sentence-number references, resolved against frozen redacted full answers. Aspect-to-source mapping is in supported aspect objects; references are not quote identifiers. |
| `verifications`, `verification_result` | Structured origin/bundle/verdict/explanation records; full requires `accepted`; rejection/uncertainty requires review. No model chain-of-thought. |
| `production_candidate_ids`, `production_context_ids`, `production_baseline_version` | Actual separate baseline selection, version `production-selection-1`; not merely audit-witness reachability. |
| `evaluated_entry_ids`, `evaluated_entry_count`, `retrieved_candidate_count` | Distinct entries actually submitted to evaluation (baseline included, malformed attempts included) versus sum of audit retrieval candidate counts across rounds. Entry status separately distinguishes validated output from failed requests. Repeated retrieval/evaluation recovery never spends the same entry twice. Malformed output cannot establish evidence. |
| `evaluation_scope`, `stopping_reason` | Actual initial/broader depths, distinct-entry budget, snapshot reference, explicit `whole_kb_absence_proven=false`; stops include `verified_full`, `candidate_exhausted`, `evaluation_limit`, `needs_context`, `scope_excluded`, `processing_error`, `snapshot_mismatch`, `pending`, interruption/cancellation. |
| `recommendations`, `recommendation_status` and aligned proposal/taxonomy cells | `[]`, `unassessed`; no suggestions or factual new answers. |
| Snapshot/input/config/code/rubric/model/prompt/tokenizer fields | Safe identities with exact file/template/schema hashes and obtainable serving version/context limit in manifest. Immutable weights/tokenizer revision is explicitly unverified. Unknown scalar aliases/classifier/normalization version projections may be empty; authoritative code/config identities remain in the manifest. |
| `input_scope`, counts | `pilot_subset_full_input_export`; selected-input count is the export denominator, source-input count includes history-only records, model-selection IDs separately list the at-most-five pilot. |
| `run_identity_id`, `export_revision_id` | Immutable pre-evaluation configuration/serving identity and frozen permission-specific CSV/manifest revision. Manifest contains the authoritative identity map and capture time. |
| `review_codes`, `review_codes_by_phase`, `evidence_phases` | Scoped uncertainty and production/initial/broader provenance. Evidence views do not reuse a joint full verdict for subsets. |
| `validation_diagnostics`, `output_recovery_count`, `recovery_policy` | Content-free schema diagnostics and separately counted bounded JSON-syntax recovery. No raw outputs or validation input values. |
| `failure_diagnostics` | JSON array of fixed failure categories, boundary/evaluation phase, attempt, dispatch-attempt flag, safe timings/token counts, obtainable opaque request reference/numeric HTTP status and server-completion state. Also available in restricted exports; no evidence text/exception values. |

Results-only exports keep query/status/lineage but omit evidence arrays, grounded
explanations and protected reasons unless evidence-view + `kb_read` are present.
Manifest matches that projection's export ID and file hash. Unknown fields are
empty/`[]`/`{}`; recommendation fields remain explicitly unassessed. Evidence
detail may show partial supports with full source sentences; incompatible runs
withhold content and mark snapshot mismatch. Export identity includes projection,
so restricted and evidence-visible exports can have different IDs.

“Prepare download” captures one immutable revision under the same short lock used
for row/meta updates. Both download links use its `revision_id`; the CSV header
and manifest agree on revision/export identity and CSV hash. Progress cannot
change those bytes. Prepare again to capture newer progress. Unqualified legacy
GETs reuse their projection's latest explicitly created revision (creating one
only if none exists); clients coordinating concurrent explicit refreshes must
pin `revision_id` from the creation response. A revoked evidence entitlement
cannot access the earlier evidence projection. Incomplete captures report their
actual run state and pilot scope, never completed full-dataset evaluation.

### Protected execution and reproducibility

Durable configured artifact root is outside Git/static and `/tmp`, 0700/0600,
owner-only/no symlink traversal. Archive hashes preserve A1 identities; mapped
redacted datasets, full versioned KB snapshots, run settings/ownership/progress
and one checkpoint per row are persisted. Existing in-process job manager plus
OS run/global leases keeps calls sequential without new infrastructure.
Recovery skips completed/excluded/review/context/invalid rows; unfinished or failed
attempts replace the same source identity. Completed runs with failed rows offer
retry. Stale running workers are detected through lease ownership. Recovery is
explicit and row-level; repeated partial remote inference after interruption is
possible, and a queued-before-crash run may need trusted operator retry.

Preparation reuses A1's cutoff and actual production normalization/rewrite/intent/
eligible-alias path. User-only context can resolve a subject. Genuine missing
subject stays needs-context; conservative A1 ellipsis guards may be reviewed only
when the original explicitly supplies a subject and scope certifies it.

Snapshot content capture is read-only REPEATABLE READ plus verified source/index
bracketing and actual transactional content. Retrieval checks signatures and raw
candidate content hashes against that snapshot. Request-local depths are
150/150/150 (initial top 50) and 300/300/300 (unresolved broader check), with full
pool question/category/subcategory reranking and maximum 300 distinct evaluated
entries including baseline. A2.2 caps full Q/A batches at **two** entries, dynamically
budgeted by the served chat-template tokenizer plus reserved output/margin.
Bounded complementary bundles receive actual source evidence/conditions; every
proposed full proof is verified. Budget/search exhaustion implies only possible
gaps within that scope, not whole-KB absence.

Production, initial and broader phases share validated entry evidence, conditions
and proof identities. Verified production full coverage cannot be weakened by
audit results. Cross-phase evidence can establish KB coverage but cannot make
production context sufficient. An independent audit proof with unresolved
production assessment has full KB coverage and review-needed reachability.
Apparent complete aspect support without a compatible verified proof remains
review-needed; bounded greedy bundle search is explicitly non-exhaustive.

Run configuration/serving identities are captured before selected-row evaluation
and compared on resume and after rows. Effective production/audit settings,
aliases/classifier/preparation identities and observed generation/embedding/
reranking serving identities are included. Changed code/settings/serving prevents
mixing completed checkpoints with new work and marks the run incompatible;
original identity values are never overwritten. Legacy runs with retained work
and no pre-evaluation identity cannot resume through changed code.

A2.2 `audit-failures-1` distinguishes admission, outer deadline, typed model
read/connect/write/pool timeout, unknown timeout, connection/service failure,
HTTP/protocol rejection, output length, schema/citation/semantic validation and
cancellation. Exception causes are inspected only in memory. Diagnostics exclude
messages, bodies, headers, traceback locals and source text. Unreturned completion
attempts retain unknown served usage/completion state; local cancellation does not
prove server cancellation. No network retries are added. The existing single
fresh syntax-response policy remains separate and bounded.

`full-entries-two-1` reduces only the audit batch cap from five to two after bounded
paired output-budget checks. Full Q/A, conditions, sentence references and remaining
entries are retained; this does not promise that every two-entry response fits.
Production clients/timeouts, retrieval defaults and all strict proof checks remain
unchanged. Audit tokenization precedes its existing 50-second admission/completion
deadline; it has its own HTTP timeout. Background run duration is independent of
the dashboard request, which returns before model execution. These are not a
50-second total-run or total-attempt guarantee.

The trusted local `knowledge_coverage_pilot.py review --run-ids ...` command creates
a protected, offline JSON/escaped-HTML review package for the same five selected
rows, with redacted intent, full numbered cited/production evidence, conditions,
verdict provenance and blank reviewer fields. It neither assigns human labels nor
exposes a new web endpoint. All prior CSV/manifest revisions remain byte-identical;
new version-3 revisions add diagnostics without rewriting old revisions.

Qdrant and model weights are not frozen. Observed source/index/serving/code drift
invalidates the run, but bracketing cannot detect every transient/ABA change or
immutable weight revision behind an unchanged alias. Historical pilot manifests
explicitly distinguish post-pilot configuration observations from configuration
captured before execution; saved-evidence export corrections retain original
pilot files and exact inference-code hashes. Later full-run/retention/visual and
human-review acceptance remain separate planner gates.


## A3 controlled calibration additions

`KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES` is an audit-local integer 1–5, default 2.
Served-token budgeting may pack fewer whole entries. `coverage-settings-3` records
the cap and `full-entries-configurable-1`; customer CSV v4 adds `batch_max_entries`.
Changing it rejects resume against pinned identities. Historical export revisions
are immutable and retain their original schemas. Production settings are unchanged.

Calibration artifacts use a separate `calibrations/cal_<opaque>` namespace.
`controlled-calibration-1` explicitly means fictional controlled candidates; it
is neither customer audit output nor a hybrid-retrieval recall measurement.
The operator campaign has a durable 120-dispatch cap including probes/recovery,
12 preselected baseline records and three preselected cap-5 comparisons.

| New GET route under `/api/knowledge-coverage` | Required access |
|---|---|
| `/calibrations`, `/calibrations/{calibration_id}` | results-view, owner |
| `/calibrations/{calibration_id}/export`, `/calibrations/{calibration_id}/export-manifest` | export-download + results-view, owner; evidence additionally requires evidence-view + `kb_read` |

These read-only routes reuse authentication/default-deny capabilities and cannot
start a model run, read arbitrary server paths or grant another account access.
Operator owner 0 is not a browser account. Summary responses expose run identity,
configuration and denominated scores. No dashboard layout or user flow changed.

`calibration-export-1` reuses the A1 CSV encoder: BOM, quoting, JSON cells, formula
protection, row-order/identity checks. One immutable CSV/manifest pair is frozen
per permission projection at campaign termination/interruption. Later checkpoint
changes cannot regenerate that pair. Every selected baseline/comparison record,
including errors/unexecuted cases, has its own stable row ID and CSV row.
Fields include case/comparison identity, batch cap and effective configuration
identity, baseline/variant snapshot and removal IDs, query, processing/coverage/
production state, evidence/verifications, missing aspects, errors, stopping reason,
counts/tokens/duration and explicitly unassessed recommendations. Manifests hold
fixture/hidden-label hashes, prompt/schema/code/model identities, configuration
variants and completed/overall metric denominators. Restricted exports omit
source/aspect evidence. No historical 918-row export is changed.

Human-review import `human-label-import-1` is an offline protected interface,
bound to the original package manifest and row/run/snapshot/citation identities.
Completed reviews require intended question, aspects, applicability/conditions,
coverage, production sufficiency, missing facts/evidence and declared independent
human provenance. Independence is declared, not independently authenticated.
Blank fields remain `not_reviewed`; zero-label metrics are null with denominator
zero. Both A2.1 and A2.2 observations remain distinct, particularly rows 121/518.
Reviewer identity, labels, corrections and notes remain outside Git/public assets.
