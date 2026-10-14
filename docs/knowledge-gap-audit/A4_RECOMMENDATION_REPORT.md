# A4 structured gap analysis and question/taxonomy recommendations

Status: implemented for planner review, with human confirmation and release
limitations below. No factual-answer generation, KB writes, production calls,
deployment, A5 or full 918-query evaluation was performed.

Branch: `a4/gap-question-recommendations`. Verified base:
`0ea9b14d93c428ad8ea1a8a26bd400274e3f80d2`. The publication commit contains this
report; the handoff supplies the verified full local/remote SHA. Historical
coverage verdicts, snapshots, manifests and exports were not rewritten.

## Eligibility and boundaries

Automatic drafting requires a completed, prepared, in-scope `possible_gap` or
`possible_partial_gap`, identifiable unresolved aspects drawn from the actual
requested aspects, recorded bounded scope/stopping reason and no unresolved
errors, context/redaction uncertainty, compatibility or verification problems.
Recovered JSON syntax is distinguished from an unresolved evaluation failure.
No missing fact is inferred from an empty array on an unfinished/error result.
Covered/unreachable stays retrieval-improvement work; covered/reachable, pending,
errors, exclusions and context/review cases expose specific unavailability codes.
Eligibility is not independent confirmation of a real KB gap.

Comparable full observations are checked using the same input identity/source
row, snapshot and normalized resolved intent, accepted model verification and
valid snapshot references. They block drafting and approval; neither historical
observation is deleted or treated as human ground truth. This was checked against
protected real artifacts, without model calls: the latest five-query customer
pilot has **zero eligible rows** (three covered, one exclusion, one error).
Earlier row **121** has one comparable full observation and is blocked with
`conflicting_full_coverage_observation`. Row 518's older unreachable proof and
later error remain separate. No eligible customer gap was fabricated.

Freshness checks run between model responsibilities and after drafting. Later
contradictions or source incompatibility are projected as review-needed without
changing saved draft bytes. Approval rechecks eligibility. A revision from an
older title-lookup policy requires a new revision before approval. All drafting
and review actions require existing ownership/authentication/CSRF checks.

Two isolated responsibilities reuse `AuditModel` through an instance-local
schema/message registry. Coverage retains **coverage-rubric-4**, its original
five schema shapes and prompt hashes. Shared production clients/settings are
not mutated. Both new schemas forbid extra fields and contain **no answer field**.

- **Gap analyst**, `gap-analysis-1`: resolved intent, requested/missing aspects,
  concise structured partial supports and conditions, source/citation identities,
  scope/stopping/uncertainty and run/export/row hash. No raw chunks, full answers
  or full KB. It returns g1–g3 specifications partitioning actual missing IDs,
  missing-information descriptions, only supplied conditions/references,
  bounded-search/human-label limitations and mandatory knowledge-team/independent
  review requirements. All missing IDs and citation membership are validated.
- **Question/taxonomy recommender**, `question-recommendations-1`: gaps, structured
  partial relationships, existing taxonomy and up to twenty relevant snapshot
  titles/IDs; no answers. q1–q3 proposals have question, missing/gap IDs,
  category/subcategory/path status/ID, related/equivalent FAQ leads, equivalence
  basis, action, concise justification and uncertainty. Existing paths preserve
  exact original display values. Proposed paths require explicit proposal flags.

Strict local validation checks source IDs, membership, gap coverage, conditions,
path/display values, collisions, equivalence basis/action consistency, question
punctuation and new numeric premises. It rejects answer fields, invented IDs and
unsupported paths. Free prose still requires human review: schema and numeric
checks cannot prove complete semantic fidelity or immunity to prompt injection.

## Snapshot titles and taxonomy

`snapshot-titles-taxonomy-2` builds a read-only metadata index from the authorized
frozen snapshot: FAQ/chunk ID, question title and category/subcategory. It examines
metadata locally and selects at most twenty candidates using Persian normalization,
word-token overlap, evaluated partial-support preference and exact normalized-word
matches. Full Q/A content never enters either new model responsibility. All
existing taxonomy paths are supplied when they fit the verified token budget;
overflow becomes an explicit error, without silently truncating conditions.

Version 2 fixes punctuation spacing introduced by production preparation: literal
spacing differences must not hide a lexical title match. Taxonomy normalization
and original display values remain separate. Null subcategory is valid;
category/path normalization collisions retain all displays and require taxonomy
review. Unknown/missing categories are counted rather than fabricated.

Titles are review leads, never proof of coverage or answer incompleteness. An
`evaluated_partial_support` basis must really have validated partial evidence.
An exact normalized title or declared equivalent FAQ requires review-existing/
taxonomy action, preventing a duplicate new question. Similar titles without
that evidence do not establish incompleteness. Failed bounded lookup does not
establish absence of an equivalent FAQ across the KB. This is metadata lookup,
not production retrieval or answer-aware reranking.

## Revisions, review and CSV

`recommendation-revision-1` lives under the protected `recommendations/rec_<id>`
namespace. It pins an explicitly selected evidence-visible immutable coverage
export/revision and CSV/manifest hash, every source-row hash, snapshot/index,
recommendation code/prompts and obtainable serving identity. The source projection
and final draft results are immutable; checkpoints are separate. New attempts
create new revisions, retaining previous errors and interrupted work.

`recommendation-review-1` uses immutable rvw revisions with previous revision,
result hash, reviewer ID and redacted note. States are unreviewed/approved/rejected/
needs_changes. **Approval approves a question/taxonomy proposal only**, never a
factual answer, coverage truth or KB write. Independent gap-review and real-query
calibration status remain explicit and pending. There were no genuine human
labels or real-user review decisions; Chromium's votes were synthetic test actions.

`coverage-recommendations-csv-1` / `coverage-recommendations-manifest-1` bind one
immutable rex export to frozen coverage and pinned recommendation/review data.
The reusable A1 encoder preserves BOM, Persian/multiline quoting, JSON cells,
formula protection, original order and duplicate IDs. Multiple questions stay in
one JSON cell. Every source record remains, including pending/excluded/errors.
Permission-restricted projections omit draft/evidence text, blank phase maps and
mark evidence restricted. Approval scope is explicit. CSV and manifest GETs use
the same rex identity even if later review/progress changes. Old coverage prompt/
model/version projections remain original; new recommendation provenance is separate.

Nine new routes integrate the existing main dashboard: row availability; draft
creation; revision detail/cancel/review; frozen FAQ metadata links; combined-export
creation, CSV and manifest. Unknown routes remain denied. New capability
`coverage_recommendation_review` is default denied, including admins; existing
roles and real grants are unchanged. Drafting requires existing start/export/
results/evidence/kb-read capabilities. Review additionally requires the new grant.
Jobs reuse tracked tasks, the coverage serial gate/global lease, existing service
admission and sequential calls; no Redis/Celery/infrastructure was introduced.

## Controlled staging evidence

Fixture specifications were frozen before model work in
`fixtures/knowledge_question_recommendations/inputs.json`, separate evaluator-hidden
`labels.hidden.json`, and hashed `lock.json`. Facts are explicitly fictional
FableBank policies, not real assertions or customer-derived fixtures. Three
model-selected questions plus one unselected duplicate produce four source rows.
Controlled candidate manifests are explicit; there was no live hybrid-retrieval
recall test or shared index mutation. The hidden labels are loaded only after
initial model work. Fixture SHA-256: inputs
`27f01fa47b0c965f8c7c439a1493ff80be6a9b45bfe11bb5b44232c2155c2c06`;
evaluator-hidden labels
`a1550d1dfd8f1c3011e5236c3a4440a9379a5bb572ecf0980f2e233e08596321`.

Initial pilot ran 14 October 2026, **19:15:16–19:17:05 Asia/Tehran**. Private root:
`/root/projects/faq-private/knowledge-coverage/recommendation-pilots/`.
Coverage run `r_1a543dbe4e2880f5e5c9b90d4b08d613`, snapshot
`e820ce63af5ac751dacc5ee78a78fadf8e4fe46ad90e8dbede49d21030876559`.

| Case | Actual result | Entries / completion attempts | Prompt/output tokens | Row ms |
|---|---|---|---|---:|
| Compatible-set question with incompatible weekday/weekend evidence | needs_review, uncertain; zero recommendations | 4 / 7 | 9480 / 1306 | 45080 |
| Standard-card duration plus missing submission cutoff | possible_partial_gap, missing a2 | 2 / 4 | 3857 / 489 | 16695 |
| Missing replacement fee | possible_gap, missing a1 | 2 / 4 | 3732 / 254 | 8939 |
| Duplicate of fee question, unselected | pending/not evaluated | 0 / 0 | 0 / 0 | — |

**A3 compatibility blind spot is closed for this controlled case:** the new
question explicitly identifies Silver cards; scope is self-contained, extracted
aspects are three with **zero ambiguities**, and the sources were evaluated across
batches. All aspects have apparent support but weekday duration and weekend cutoff
cannot supply one compatible proof. The result carries
`compatibility_unverified` / `bounded_bundle_search_unresolved`, no accepted full
verification and no inferred missing aspects. Gap analysis/drafting calls: **zero**.
No actual ambiguity was overridden and no expected label entered the model.

Initial recommendation revision:
`rec_9c8f90faba1d457d9f01d435f100b274`, rubric 1 / lookup 1.
Source coverage export `9096ffb7903a83c79585c4e05b111efbad903f0b0d5bf4f5cded7f0eafa77342`,
revision `rev_6bd47f8297e075b8f2f222c71e36248d`.

The analyst produced valid missing specifications for cutoff a2 and fee a1.
The fee draft was valid, action `new_question`, existing Fictional banking / Paper
cards path. The partial draft was rejected as `equivalent_title_requires_review`:
it marked an evaluated FAQ equivalent while asking to create a new question.
This was **semantic validation**, not JSON/schema syntax or transport failure.
The rejected attempt and original results/exports remain intact.

Two individually bounded paired checks followed, without rerunning coverage or
analysis, then one final control on the separate fee case:

| Check | Only changed input/policy | Attempts | Tokens prompt/output | Request ms | Observation |
|---|---|---:|---|---:|---|
| Initial partial question boundary | rubric 1 / lookup 1 | 1 | 2240 / 216 | 8722 | rejected equivalent-title/new-question combination |
| Prompt candidate | rubric 2 clarifies the existing cross-field rule; exactly same structured payload | 1 | 2342 / 189 | 7030 | passed then-current guards but still chose new_question by dropping equivalence flag |
| Metadata-only check | rubric 2 fixed; lookup 2 recognizes normalized-word title equality | 1 | 2344 / 216 | 7742 | valid review_existing_faq, supplied f201; existing path |
| Final fee control | final rubric 2 / lookup 2; not a single-variable comparison | 1 | 2130 / 182 | 6627 | valid new_question; existing path |

The prompt-only candidate is **not counted as a successful duplicate-prevention
repair**. Inspection found the client exact-title flag was false because production
normalization changed punctuation spacing. Word-token matching corrected that
independently; no schema/citation/action guard was weakened, field coerced or
semantic output repaired. Older lookup revisions now require fresh revision review.

Prompt-only payload SHA verified identical:
`157902960e6f16ea44cb24b58eacd7fd429f27e628cb157c7de71db79f3c44b3`.
Metadata-only payload SHA after the explicitly changed lookup:
`3f6ac23360652aa82cb0a6cd667a126086bc31b42a0829d64d690ee19bd9e354`.
The baseline reconstruction was hash verified; gap/aspect/source/question and
serving identities were held fixed. There is no statistical attribution of
latency or guaranteed reliability from these single observations.

Final partial revision: `rec_1f75f3be05c6437cd3cbb02bfdeff705`.
Final fee revision: `rec_e91878f122898be63a37e54936690ab9`.
Final partial CSV export:
`3b980cd5f22ae722dabea7d4ecba8b78957c3fc735448008f55430bdc4b3cf20`.
Final fee CSV export:
`ef5220521ad08318b54088b903c60a7292c45bf8b38eebbcef9a35c76704d2fc`.
All five saved evidence/restricted export pairs passed SHA/identity/BOM/four-row
source-order validation after the final checks.

Both are unreviewed. Intermediate candidate `rec_c078e5bf55825f71ebae20f753e15663`
is preserved and current-policy approval is blocked. Every export contains four
rows; intermediate/candidate exports do not overwrite the original.

**Total A4 staging dispatches: 22 / hard 40**, all sequential:
15 coverage, 2 gap analysis, 5 question recommendation; probes 0, recovery 0,
network retries 0. Returned: 22. JSON/schema-valid responses: 22. Initial strict
semantic rejection: 1; the title-matching false-negative is reported separately.
Transport/output-length failures: 0; unknown server usage: 0. Total returned tokens:
**31,101 prompt + 3,323 output = 34,424**. Initial pilot wall time 108,393 ms;
paired/check operator times 7,321 / 8,045 / 6,870 ms. No further dispatch or full
pilot rerun was performed. Actual bounded operator commands (not instructions
to rerun the completed experiments):

```bash
python scripts/knowledge_recommendation_pilot.py --confirmed-staging
python scripts/knowledge_recommendation_revalidate.py --confirmed-staging --recommendation-revision-id rec_9c8f90faba1d457d9f01d435f100b274 --source-row-id row_38048a74eb30c71ac0f40e6f5fa5ca29
python scripts/knowledge_recommendation_revalidate.py --confirmed-staging --metadata-normalization-check --recommendation-revision-id rec_c078e5bf55825f71ebae20f753e15663 --source-row-id row_38048a74eb30c71ac0f40e6f5fa5ca29
python scripts/knowledge_recommendation_revalidate.py --confirmed-staging --final-heldout-check --recommendation-revision-id rec_9c8f90faba1d457d9f01d435f100b274 --source-row-id row_90d98b595fe04bf507b2bdd807516e82
``` These related controlled cases are not real-query
accuracy, calibrated confidence or independent human ground truth.

All requests retain actual served-token chat-template counting, 1,200 output
reserve, 128 margin, served context 8,192 and vLLM 0.26.0. Original admission/
50-second outer and effective 40-second read policy remain unchanged; SDK network
retries are zero. Background operations consist of separate bounded calls, not
one external HTTP deadline. Immutable weight/tokenizer revisions remain unverified.

Initial unfilled prompt/schema source hashes were verified and archived privately
at `archive/a4_initial_roles_1/`; the code exercised before final source-freshness
projection guards is archived at `archive/a4_live_guard_sources_1/`. Live runs
record the base Git HEAD plus exact per-file worktree/operator hashes. Later
freshness/approval/projection safeguards were validated deterministically and in
the final synthetic browser, without rewriting those hashes or replaying coverage.
Source-consistent model observations do not validate the negative freshness branch.

## Tests and actual browser acceptance

Initial focused tests: 26 passed / one invalid-citation test mistakenly supplied
a valid reference; corrected to a genuinely unprovided sentence. Subsequent focused
backend/permission/reliability checks: 88 passed. The first broad suite found eight
failures from a missing first-party asset whitelist entry; registering the new
script fixed the integration. Then 525 tests / 203 subtests passed. Final source-
freshness, restricted projection, title-spacing and stale-policy assertions are
included in the final full run recorded below.

All Python commands used the activated `faq` conda environment. Final commands:

```bash
timeout 240 python -m pytest tests/test_knowledge_recommendations.py tests/test_knowledge_coverage_calibration.py tests/test_knowledge_coverage_reliability.py tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py tests/test_structured_logging.py tests/test_offline_frontend.py -q
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit scripts/knowledge_recommendation_pilot.py scripts/knowledge_recommendation_revalidate.py tests/test_knowledge_recommendations.py tests/knowledge_recommendation_browser_app.py
node --check static/js/knowledge_recommendations.js
node --check static/js/knowledge_coverage.js
git diff --check
python -m tests.knowledge_recommendation_browser_app --port 18764
node tests/knowledge_recommendations.browser.cjs /tmp/faq-a21-browser-node http://127.0.0.1:18764 /tmp/faq-a4-browser-evidence-final
```

Results: **529 tests and 203 subtests passed**, 39 warnings, 26.16 s.
New A4 module: 39 tests. Frontend DOM contracts: **3 / 6 / 5 passed**.
Offline audit passed with zero external runtime dependencies; compilation, JS
syntax and Git whitespace checks passed. Actual Chromium acceptance: six groups
passed. A mistakenly named offline-audit command initially returned file-not-found;
the correct existing `audit_offline_frontend.py` command above passed.

New tests cover total/partial gaps, real partial references, existing/new paths,
null subcategories/category/path collisions, evaluated partial versus title-only
leads, multiple questions in one CSV row, all ineligible dimensions, contradictory
historical full observations, between-stage freshness, hallucinated IDs/paths/
conditions, answer fields, numeric premises, injection, overflow/malformed output,
shared 40-dispatch exhaustion, default schema parity, owner/auth/CSRF/new review
capability, cancellation/lease release, immutable source/draft/review/CSV pairs,
restricted evidence and stale-policy approval rejection. Retained P1–P4/A1–A3
retrieval/answering/history/configuration/permissions/consistency regressions pass.

Actual isolated Playwright/Chromium **153.0.8010.0** used synthetic account 990001,
process-only grants, temporary artifacts and deterministic mock models. No real
user account/table or persistent grant changed; the fixture replaced application
startup/auth/data services. All browser requests were confined to its loopback
origin. Six actual check groups passed: upload/mapping/Persian multiline/duplicate/
error preservation; eligible drafting/progress/cancel/new revision; readonly FAQ
metadata and keyboard approval/focus; four-row BOM CSV/manifest hashes with old
review-export immutability; dark/light/RTL/mobile/visible focus; covered-row drafting
blocked with no page errors or KB write requests. Review actions approved/requested
changes/rejected are automated synthetic UI checks, not human validation.

Screenshots (synthetic data only):
[dark desktop](assets/a4-dark-desktop.png),
[light desktop](assets/a4-light-desktop.png),
[RTL mobile](assets/a4-rtl-mobile.png).
Detailed browser checks/downloads stay in `/tmp/faq-a4-browser-evidence-final/`.
Only sanitized fictional screenshots are committed. No unperformed Excel-native,
real-account, human-quality or production browser acceptance is claimed.

## Configuration, privacy and remaining limits

**No new permanent env variables.** Existing grants JSON accepts the explicitly
named default-denied review capability; all four tracked templates document it.
Other defaults/type/ranges/manifest settings are reused. `.env` / `.env_latest`
bytes are unchanged, not committed; their original hashes, the raw CSV and user's
ignore rule were checked. No generator exists for the source-authored generated
example, and the deleted staging template remains deleted.

Protected root `/root/projects/faq-private/knowledge-coverage`: directories 0700,
files 0600, outside Git/static, no symlink traversal. Raw input may be in memory;
new source artifacts contain validated redacted coverage projections and permitted
metadata only. Model metrics retain fixed categories/counts/timings/hashes, never
prompts, raw responses, exception strings, auth or banking/customer text. Existing
regex redaction is incomplete for arbitrary prose; private permissions/review
remain necessary. All 4,686 pre-A4 artifact hashes were checked unchanged. Of 4,718 files captured
before the candidate checks, only the authorized A4 dispatch-budget counter changed
(from 19 to 22); every historical/intermediate result and export stayed unchanged. The original customer input and unrelated
worktree/private env/ignore/deleted/untracked files are excluded from the commit.

Historical pre-P0 credential exposure remains an operator responsibility: assess/
rotate through owners and decide coordinated history handling. Values are not
printed; no automatic external rotation or Git-history rewriting occurred.

Planner readiness: backend/UI/revisions and bounded controlled evidence are
reviewable. Independent real-query gap labels, taxonomy/question quality,
immutable model provenance, whole-KB equivalent-title recall and production repair
release gates remain unresolved. Approval does not establish any factual answer.
No A5, full-dataset model run, deployment or production default change is included.

## Scoped publication files

Only the following 38 files are included in the A4 commit:

```text
.env.example.generated
Production_ENV
docs/configuration/ENVIRONMENT_VARIABLES.md
docs/knowledge-gap-audit/A2_RUBRIC_AND_SCHEMAS.md
docs/knowledge-gap-audit/A4_RECOMMENDATION_REPORT.md
docs/knowledge-gap-audit/DASHBOARD_AND_CSV_CONTRACT.md
docs/knowledge-gap-audit/IMPLEMENTATION_PLAN.md
docs/knowledge-gap-audit/assets/a4-dark-desktop.png
docs/knowledge-gap-audit/assets/a4-light-desktop.png
docs/knowledge-gap-audit/assets/a4-rtl-mobile.png
env.example
env.review.example
fixtures/knowledge_question_recommendations/inputs.json
fixtures/knowledge_question_recommendations/labels.hidden.json
fixtures/knowledge_question_recommendations/lock.json
knowledge_audit/api.py
knowledge_audit/export.py
knowledge_audit/model.py
knowledge_audit/recommendation_api.py
knowledge_audit/recommendation_fixtures.py
knowledge_audit/recommendation_jobs.py
knowledge_audit/recommendation_prompts.py
knowledge_audit/recommendation_schemas.py
knowledge_audit/recommendation_store.py
knowledge_audit/recommendations.py
knowledge_audit/settings.py
scripts/knowledge_recommendation_pilot.py
scripts/knowledge_recommendation_revalidate.py
static/css/knowledge_coverage.css
static/js/knowledge_coverage.js
static/js/knowledge_recommendations.js
templates/knowledge_coverage.html
tests/knowledge_recommendation_browser_app.py
tests/knowledge_recommendations.browser.cjs
tests/test_knowledge_recommendations.py
tests/test_web_permissions.py
versioned_assets.py
web_permissions.py
```
