# A3 controlled coverage calibration

Status: implemented for planner review; live measurements and publication identity
are recorded below. This stage does not authorize recommendations, a customer
full-dataset audit, deployment or production changes.

Branch: `a3/coverage-calibration`. Verified starting HEAD/base:
`9d73a2e64c4c34392746270ed1c12645e68fac31` (A2.2). The publication commit is the
commit containing this report; its full verified local/remote SHA is returned in
the handoff. The earlier P0–P4, acceptance, A1 and A2 histories remain ancestors.

## What changed

`KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES` replaces the audit's fixed two-entry cap.
Default **2**, integer range **1–5**, strict type/range validation. Whole-entry
served-token packing may choose fewer. Settings are immutable per engine/request;
production retrieval, reranking text, timeouts, output token limits and shared
clients are unchanged. `coverage-settings-3` / `full-entries-configurable-1` pins
the effective cap. Existing run identity checks reject changes on resume without
overwriting pinned provenance or mixing completed rows. Customer CSV/manifest v4
adds the cap; historical immutable export revisions retain their original schemas.

The controlled runner calls the existing CSV adapter, query preparer, scope,
aspects, ledger, batch evaluator, reconciliation, verifier and CSV encoder. It
opens no PG/Qdrant connection and makes no live hybrid-search request. Frozen
candidate adapters supply separate production, initial and broader selections;
production sufficiency still uses production-selected evidence only. Sources
are full fictional Q/A entries with taxonomy and stable sentence identities.
No answer generation or recommendation responsibility was added.

A separate protected `calibrations/` namespace stores immutable fixture snapshots,
run/configuration/prompt/schema/serving identities, per-record checkpoints, safe
model metrics and terminal CSV/manifest pairs. The durable campaign counter limits
**all A3 completion dispatches to 120**, including capability probes, syntax
recovery and comparisons. It reserves before dispatch, counts actual HTTP sends,
requires zero SDK network retries, and refuses to automatically rerun an already
started campaign. Cancellation/interruption preserves explicit unexecuted rows
and a frozen export. This is a bounded operator experiment, not a new worker or
new permanent infrastructure.

Four GET routes expose owned calibration summaries/configuration and immutable
CSV/manifest downloads through existing main-dashboard authentication and
permissions. They reuse default-deny capabilities; downloads require results and
export privileges, with evidence additionally requiring evidence permission and
`kb_read`. No account grant or role privilege changed. Default operator owner 0
is not a browser user; trusted CLI `--owner-id` explicitly assigns ownership and
does not grant access. No page, browser flow or separate evaluation frontend was
changed. API tests use temporary synthetic accounts. No new visual/browser
acceptance is claimed; unchanged frontend behavior has automated regressions.

## Frozen specification and seeded controls

Committed synthetic files:

- `fixtures/knowledge_coverage_calibration/inputs.json`: fictional FableBank
  paper-card facts, twelve live case IDs, four deterministic-only cases,
  baseline/removal sets and fixed candidate order. Version `fablebank-inputs-2`.
- `labels.hidden.json`: separately authored expected scope, aspects, applicable
  conditions, support entry/sentence relationships, missing facts and outcomes.
  Version `fablebank-labels-1`; authority is literal fictional facts, **not** the
  evaluator's own predictions or independent human real-query labels.
- `lock.json`: `fablebank-fixture-lock-2`, containing the frozen SHA-256 values.

Input SHA-256: `c865e497155cd03f79c64fa5d53121c503a8517672557fac0b18e3a85c62b9c3`.
Hidden-label SHA-256: `aad11c63cbbe6b037b67d42e459b519949aa0ad925f294be0e5b545db083388b`.
All hashes were frozen before the live campaign. Labels are read only by the
post-evaluation scorer, after all predictions; scope/aspect prompts and frozen
comparison inputs never receive expected labels.

Initial deterministic checks exposed a fixture layout defect: production had
already evaluated a filler entry, so ledger reuse removed the intended cross-batch
split. Input v1 hash `d23a041bfc7035a77e4009a96702dae52835e44fecca9dc7c24be39d448a10e4`
was superseded before any live call. A different unrelated filler now separates
the complementary entries. Expected labels/hash did not change. A conflicting
mock verifier had also incorrectly accepted deliberately incompatible supports;
the synthetic mock was corrected to reject them. Neither change tuned a rubric
against model outcomes.

| Case | Frozen expected behavior / isolated manipulation |
|---|---|
| c01 | Exact question: production f01 is sufficient even when audit selects noise. |
| c02 | Paraphrase: equivalent f02 production evidence establishes full coverage. |
| c03 | f03 duration + f04 cutoff, separated across cap-2 batches; full KB coverage, production noise insufficient. |
| c04 | c03 baseline with f04 removed: duration remains; missing cutoff a2 gives partial coverage. |
| c05 | Same baseline with f03/f04 removed: both requested facts missing; complete controlled gap. |
| c06 | Remove f01 but retain equivalent f02: full coverage survives removal. |
| c07 | Duration for Silver only and cutoff for Gold only: no compatible full proof for the same account type; review/uncertain. |
| c08 | Actual ticket-submission steps answer a procedural ticket question. |
| c09 | Generic referrals without fee/duration cannot supply either requested substantive fact. |
| c10 | Full f01 audit evidence, absent from the production context: covered but not reachable. |
| c11 | Subject-free follow-up without history: needs context. |
| c12 | Unrelated creative request: excluded. |
| c13–c16 | Deterministic-only malformed output, invalid citation, private-account request and chit-chat. |

Each removal records the unmodified baseline and variant identities. All unrelated
records, order and taxonomy survive exactly. c03/c04/c05 share a baseline; c06
explicitly preserves equivalent support. No shared database/vector record is
hidden, deleted or edited. These **controlled candidate** results validate evidence
reasoning under specified candidates; they do not validate live hybrid-search
recall, reranker quality or naturally occurring gap prevalence.

## Model policy and paired experiment

Baseline `coverage-rubric-4` and all prompt/schema hashes are captured in run
identities. Responsibility versions remain `scope-1`, `aspects-2`, `batch-1`,
`reconciliation-1`, `verification-1`; segmenter `answer-sentences-1`. There was
**no rubric candidate, tuning or majority vote**. Strict schema/citation/membership,
compatibility and every-full-proof verification remain mandatory. A malformed
response cannot become covered or a gap. Error taxonomy `audit-failures-1` and
bounded syntax recovery `json-invalid-stop-one-fresh-response-1` are unchanged.

The current served `/tokenize` counts complete messages, schema/rubric/evidence
with chat template and generation prompt; 1,200 output tokens plus 128 margin
must fit the actual served context. No character-count proxy or truncation is
used. SDK network retries remain zero; inherited production-client deadline
policy is unchanged. Weight/tokenizer immutable revisions remain unverified.

Twelve preselected baseline cases run sequentially at cap 2, followed by c03,
c07 and c09 at cap 5. Comparisons freeze the **baseline model-derived** scope and
aspects (not the expected labels); query forms, source contents/order, rubric,
model settings, serving identity and entry budget remain fixed. Effective cap-2
and cap-5 configuration variants are separately hashed in rows/manifests. A
comparison cannot execute if its baseline has no extracted scope/aspects. These
one-pair observations cannot isolate sampling/runtime variation statistically.

## Live campaign and metrics

One campaign, `cal_27dd08c46b1d04f693a40ab8424be20c`, ran on confirmed root-dotenv
loopback staging, sequentially, from 2026-10-14 12:24:57 UTC to 12:29:21 UTC.
Protected directory:
`/root/projects/faq-private/knowledge-coverage/calibrations/cal_27dd08c46b1d04f693a40ab8424be20c/`.
Run identity:
`743aac00f5e51e1da28b4a1c34c7ac411d10aaeedff24f351f5be917e5cf035f`.
Base configuration identity:
`8c38b91221b19232e34fa48a0c4b7c32851ad0971b214261db241507af1a5032`.
Code was frozen before execution; all captured source/operator file hashes match
the final implementation. The run records base Git HEAD plus exact file hashes
because implementation files had not yet been committed during the experiment.

Actual HTTP completion dispatches **55/120**: **5** capability probes, **45**
baseline attempts and **5** comparison attempts. There were **54 validated
responses**, **1 invalid-JSON response**, and **1 explicitly counted recovery
request** (included in those 55 and validated responses). All 55 requests returned;
transport failures **0**, output-length failures **0**, unknown server usage **0**,
blocked dispatches **0**. First attempts: 53 validated + 1 invalid; recovery: 1
validated. The invalid response was c04's production batch, `batch-1`, before
redaction, `json_invalid`, root field path, finish `stop`, 1,160 prompt/80 output
tokens, 2,772 ms. Its permitted fresh attempt used 1,160/159 tokens, 5,310 ms.
The failed attempt remains in safe metrics; no text/JSON contents are retained in
this report and no semantic content was repaired. Final row errors are zero;
that does not erase the attempt-level schema failure.

Five schema-constrained capability probes validated all five responsibilities.
Served vLLM version **0.26.0**, context **8,192**; immutable model/tokenizer weights
remain unverified. Returned usage: **55,710 prompt + 7,448 output = 63,158 tokens**.
Probe usage: 4,175/549; baseline: 44,463/6,051; comparisons: 7,072/848.
Campaign wall time **264,312 ms**; summed request boundary times **251,296 ms**,
minimum **1,795 ms**, maximum **16,472 ms**. Calls by responsibility (including
probes/recovery): scope 13, aspects 11, batch 21, reconciliation 2, verification 8.
No extra staging probe, pilot rerun or rubric candidate was executed.

| Case | Outcome | Production | Entries | Calls | Prompt/output tokens | Row ms |
|---|---|---|---:|---:|---|---:|
| c01 | covered_reachable | full | 1 | 4 | 3884/746 | 25436 |
| c02 | covered_reachable | full | 1 | 4 | 3891/679 | 22925 |
| c03 | covered_not_reachable | unsupported | 4 | 7 | 8062/907 | 31192 |
| c04 | possible_partial_gap | unsupported | 2 | 5 | 4952/638 | 21522 |
| c05 | possible_gap | unsupported | 1 | 3 | 2627/199 | 6831 |
| c06 | covered_reachable | full | 1 | 4 | 3845/686 | 22903 |
| c07 | needs_review | not_evaluated | 0 | 2 | 1492/218 | 7365 |
| c08 | covered_reachable | full | 1 | 4 | 3821/709 | 23959 |
| c09 | possible_gap | unsupported | 4 | 5 | 5254/362 | 12720 |
| c10 | covered_not_reachable | unsupported | 2 | 5 | 5040/782 | 26101 |
| c11 | needs_context | not_evaluated | 0 | 1 | 794/74 | 2538 |
| c12 | excluded | not_evaluated | 0 | 1 | 801/51 | 1828 |

All six baseline full outcomes have accepted verification and authored required
fact citations: c01 f01 sentences 1/2; c02 and c06 f02 1/2; c03 f03 1 + f04 1;
c08 f07 1; c10 f01 1/2. c03 is a verified cross-batch combination; c01's production
proof wins despite different audit selection. c04 retains duration evidence f03 1
and missing cutoff **a2**; c05 has missing **a1/a2** after the seeded removals; c09
has missing fee/duration **a1/a2** despite referrals. Their stop is
`candidate_exhausted`, within these fixture variants. c07 stops at
`aspect_ambiguity`, c11 at `needs_context`, c12 at `scope_excluded`. No gap result
is inferred from missing history, uncertainty or an error.

Baseline metrics (twelve selected records; comparisons excluded):

| Metric | Numerator / denominator |
|---|---|
| Completed decisions, including explicit abstentions/exclusion | 12 / 12 |
| Final errors / unexecuted | 0 / 12; 0 / 12 |
| Coverage correct, all selected KB cases | 10 / 10 |
| Coverage correct, completed KB cases | 10 / 10 |
| False full, expected partial/unsupported/uncertain cases | 0 / 4 |
| False full, among full predictions | 0 / 6 |
| False gap, known sufficient cases | 0 / 6 |
| Partial coverage and missing-aspect IDs correct | 1 / 1 |
| Production sufficiency, known covered cases | 6 / 6 |
| Authored required-fact citations present, known covered cases | 6 / 6 |
| Context/exclusion decisions correct | 2 / 2 |
| Abstention/review/context | 2 / 12 |

These small related fixture families are not a statistically representative sample.
The missing-aspect score checks ordered aspect IDs plus aspect-count agreement;
it does not supply independent semantic alignment. Required-fact citation presence
checks the authored source/sentence relationships, not independent human entailment.
Error/unexecuted records would remain in overall denominators; completed-case
metrics are separately labeled. The attempt-level schema failure rate is 1/55;
its recovery does not support a guaranteed reliability rate.

Paired comparison results, excluding reused scope/aspect calls from **both** sides:

| Case | Caps 2 / 5: outcome | Evaluation calls | Prompt/output tokens | Request ms | Distinct entries |
|---|---|---|---|---|---|
| c03 | covered_not_reachable / same | 5 / 3 | 6600/789 → 4203/612 | 26849 → 20460 | 4 / 4 |
| c07 | needs_review / same | 0 / 0 | 0/0 → 0/0 | 0 → 0 | 0 / 0 |
| c09 | possible_gap / same | 3 / 2 | 3792/244 → 2869/236 | 8493 → 7987 | 4 / 4 |

c03 changes from initial audit batches 2+1 and reconciliation to a single batch
of 3; the same f03/f04 evidence is independently verified in both rows. c09's
referrals remain unsupported with batches 2+1 versus 3. Total row calls 7→3 for
c03 and 5→2 for c09 additionally include two saved scope/aspect calls, so those
larger differences must not be attributed solely to batching. All four recorded
query/aspect/scope equality checks are true for all three pairs. No claim is made
that a nominal cap of 5 actually packed five entries: these pools need at most 3.

**Live compatibility sensitivity limitation:** c07's baseline aspect ambiguity
was frozen for its paired row; both abstained before inspecting f05/f06. This
validates conservative early review, not model compatibility reasoning across
these batches. Deterministic source-evidence tests exercise actual incompatible
combinations and generic-referral hazards under both caps; actual live combination
sensitivity for the incompatible case remains unmeasured. No override cleared
ambiguity just to obtain a favorable comparison. No further live experiment ran.

All **15/15** selected baseline/comparison records are preserved in original
selection order, including both abstentions and the exclusion. The permission-
specific frozen CSV/manifest pairs pass hash/row/export-identity checks:

- Evidence export: `5f30b5d718601391bd79774a3fac08404c4f4b5cd7f2482e31f6dc78a0a0c1c0`,
  CSV SHA `5306b532bffca2f11266777c616fd4e55897eb7d8fd83825074f1601f75c0e86`.
- Restricted export: `05d7e57d11c7c317c7d4ce0990283bf73a9e45b45600e83dfcc2e779c32a745a`,
  CSV SHA `08cf1d2e1769dc4306ce02d2df5823dfa51f6d99771d58c1616a6fb7c4a5ce74`.

Historical customer exports still contain their original 918 rows and bytes;
A3's fifteen fictional records do not replace or extend them.


## Independent human review

The user confirmed that no independent labels are available. Real-query accuracy
and calibration therefore remain **pending**. The original protected package is
unchanged:

`/root/projects/faq-private/knowledge-coverage/reviews/review_5ba744159f6b388080c0903648f72c06/`

Manifest SHA-256:
`a0b68ea1d5f00c627a8288a9815d4f3b2169d7fdd831d4d3d635e329d535d566`.
It preserves five row identities with two observations each (A2.1 and A2.2).
For row 121 the earlier possible partial gap and later full proof remain different
observations; a reviewer must check every substantive requested fact rather than
accept a generic referral. For row 518 the earlier accepted unreachable proof and
later schema failure remain distinct; neither is automatically ground truth.

New reusable protected template:
`/root/projects/faq-private/knowledge-coverage/human-label-templates/review_5ba744159f6b388080c0903648f72c06.json`.
The actual blank-template import validated ten observation identities and produced
`/root/projects/faq-private/knowledge-coverage/human-labels/labels_89201b46124508474254e8333fe3f467/`.
All ten remain `not_reviewed`, completed labels **0**, agreement denominators **0**
and values **null**. This is interface validation, not supplied human review.

`human-label-import-1` accepts intended question, aspect agreement/correction,
applicability/conditions, coverage, production sufficiency, missing facts and
snapshot-qualified evidence. Completed reviews require declared independent human
provenance. Package hash, row/run/snapshot identities, duplicates, membership and
citations are validated. Missing fields or model provenance fail closed; blank
labels stay unreviewed. Independence is declared, not independently authenticated.
Model errors do not count as agreement with a human uncertainty label. Private
reviewer identities, notes and labels are redacted before private persistence and
are never committed or served in public assets.

## Configuration, privacy and preservation

Only new permanent key: `KNOWLEDGE_COVERAGE_BATCH_MAX_ENTRIES=2`.
Defaults/type/range validation, runtime manifest, environment validator,
configuration documentation and all applicable tracked templates agree:
`env.example`, `env.review.example`, `Production_ENV`, `.env.example.generated`.
The generated-named template is source-authored; no generator was found. Existing
`.env` and `.env_latest` received only the missing key; byte-hash checks after
removing the addition confirm every prior byte/value is preserved. Neither private
file is committed, and the user-deleted staging template is not recreated.

Artifacts remain outside Git/static at the configured durable private root;
directories 0700/files 0600, no symlink traversal. Only fictional fixture inputs
and mocked outputs are committed. Live model outputs and reviewer material stay
private. Metrics contain allowlisted categories, times, counts and hashes, not
prompts, raw responses, exception text or banking/customer data. Existing regex
redaction cannot identify all sensitive prose and is not a substitute for those
private permissions. Source input stays untouched; no customer query was evaluated
in A3, and historical 918-row exports are not regenerated.

All 4,674 pre-existing private artifact hashes were checked unchanged. The original
CSV SHA-256 remains `f2e963046de586df6e187a33cac12ba3900c60d5a408066b50bc5fe2f896f3fe`.
Unrelated `.gitignore`, deleted staging template, private env edits and untracked
files stay excluded. The authorized ignored reports are added explicitly without
changing the ignore rule.

Outgoing inspection also found `POSTGRES_USER`/`DEFAULT_DB_USER` template account
names matching private runtime values in `env.example` and `env.review.example`.
Those public fields were replaced with `CHANGE_ME_POSTGRES_USER`; private values
were preserved. No credential values are printed here. Older commits are unchanged.

Historical pre-P0 PostgreSQL credential exposure remains an operator action:
assess/rotate affected credentials through their owner process and decide any
coordinated history handling. Values are not reproduced; no external credential
rotation or Git-history rewriting was performed.

## Validation

All model-backed work followed deterministic synthetic tests. Initial focused
checks reproduced the two fixture/mock construction failures (**33 passed,
2 failed**); correction passed **56** combined calibration/correction tests.
The first comprehensive run exposed the independent route-inventory expectation
missing the four new routes (**482 passed, 1 failed**); adding those explicit
permission expectations passed 93 focused tests and then **483 passed / 203
subtests before the live campaign**. No production behavior was changed to make
those tests pass. After adding final drift, validator, fact-citation and both-cap
hazard assertions, the final calibration suite passed **42** and full suite
passed **490 tests / 203 subtests, 39 warnings, 23.31 seconds**.

Exact final commands, from the repository root:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
timeout 240 python -m pytest tests/test_knowledge_coverage_calibration.py tests/test_knowledge_coverage_reliability.py tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py tests/test_structured_logging.py tests/test_offline_frontend.py -q
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit scripts/knowledge_coverage_calibrate.py scripts/knowledge_coverage_pilot.py scripts/knowledge_coverage_diagnose.py tests/test_knowledge_coverage_calibration.py
node --check static/js/knowledge_coverage.js
git diff --check
git diff --cached --check
python scripts/knowledge_coverage_calibrate.py run --confirmed-staging
python scripts/knowledge_coverage_calibrate.py human-template --package-id review_5ba744159f6b388080c0903648f72c06
python scripts/knowledge_coverage_calibrate.py human-import --package-id review_5ba744159f6b388080c0903648f72c06 --labels /root/projects/faq-private/knowledge-coverage/human-label-templates/review_5ba744159f6b388080c0903648f72c06.json
```

Frontend results: **3 audit, 6 KB and 5 analytics checks passed**; offline audit
PASS with zero external runtime dependencies. Compilation, JS syntax and Git
whitespace checks passed. Warnings are the existing NVML availability and library/
datetime deprecations. Initial sandbox TestClient IPC was blocked; the isolated
synthetic tests were rerun with authorized local IPC, without production services.
No dependency installation or shared-service restart occurred.
After the final public-template account-name cleanup, this exact focused command
passed **54 tests / three warnings in 13.00 seconds**; only templates, the matching
synthetic assertion and this documentation changed after the 490-test run:

```bash
timeout 120 python -m pytest tests/test_knowledge_coverage_calibration.py tests/test_validate_environment.py -q
```

The 27 outgoing files were inspected in full for private runtime secret values,
credential patterns, raw input cells and unauthorized paths. Findings after
public-template cleanup: zero. All four templates contain placeholders for secret
fields and the validated cap default. Git whitespace checks were rerun after
staging. Origin was checked without printing authenticated URLs and targets
`Hooman1996/RagBot`; the A3 review branch was absent before publication.


New tests cover every authored fixture family, exact/paraphrase/full/cross-batch/
seeded partial/gap/equivalence, context/exclusion, malformed output and invalid
citation, both-cap referral and incompatible-condition hazards, default parity,
type/range/template/validator propagation, per-engine concurrency isolation,
smaller token-driven packing, cap-change resume rejection, fixed source mutation,
durable 120-call exhaustion, owner/default-deny export projections, immutable
CSV/manifest pairs and incompatible-run projection, completed/overall metric
denominators, missing required-fact citations, blank human labels, declared
provenance, hash/identity/citation/membership rejection and protected persistence.
The retained A2.1/A2.2 cases verify production proof precedence, uncertainty through
expansion, cross-phase supports, pinned resume, compatibility review, immutable
customer exports, typed failures/deadlines and cancellation. The existing P1–P4
retrieval/reranking/taxonomy/configuration and answering/history/canonicalization
regressions passed. All comprehensive mocked outputs are fictional.

No actual browser check was run in A3: no browser-facing user flow/layout changed.
Protected API acceptance uses actual TestClient middleware/authentication, not
visual acceptance. Historical A2.1 screenshots remain unchanged and are not
presented as new A3 browser evidence.

## Remaining limits and readiness

Controlled facts are not real banking policies. Controlled-candidate success is
not a real-query accuracy estimate or a live retrieval-recall result. Error,
abstention and unexecuted cases stay visible; model confidence is not a calibrated
probability. Independent human labels, natural-query evidence/aspect correctness,
immutable model/tokenizer provenance and prior production-repair release gates
remain outstanding. No recommendation-stage or full-run readiness is claimed.
The next decision belongs to planner review; no later stage was started.

Scoped changes: audit settings/engine/service/export and environment validator;
controlled adapters/artifacts/scoring; protected human-label ingestion; bounded
CLI; four protected read-only API routes/permission inventory; fictional fixtures;
synthetic tests; four sanitized env templates; plan/rubric/CSV/configuration docs
and this report. No production answering, retrieval defaults, model prompts,
shared client or infrastructure code was changed.


Exact scoped files (27):

```text
.env.example.generated
Production_ENV
env.example
env.review.example
knowledge_audit/settings.py
knowledge_audit/pipeline.py
knowledge_audit/service.py
knowledge_audit/export.py
knowledge_audit/calibration.py
knowledge_audit/calibration_scores.py
knowledge_audit/human_labels.py
knowledge_audit/api.py
web_permissions.py
scripts/validate_environment.py
scripts/knowledge_coverage_calibrate.py
fixtures/knowledge_coverage_calibration/inputs.json
fixtures/knowledge_coverage_calibration/labels.hidden.json
fixtures/knowledge_coverage_calibration/lock.json
tests/test_knowledge_coverage_calibration.py
tests/test_knowledge_coverage_corrections.py
tests/test_knowledge_coverage_reliability.py
tests/test_web_permissions.py
docs/configuration/ENVIRONMENT_VARIABLES.md
docs/knowledge-gap-audit/IMPLEMENTATION_PLAN.md
docs/knowledge-gap-audit/DASHBOARD_AND_CSV_CONTRACT.md
docs/knowledge-gap-audit/A2_RUBRIC_AND_SCHEMAS.md
docs/knowledge-gap-audit/A3_CALIBRATION_REPORT.md
```
