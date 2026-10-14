# A2.1 correction and bounded revalidation report

Readiness: implemented for planner code review, with the model/reproducibility
limitations below. A3, recommendations, deployment and a full-dataset model audit
remain unauthorized. Production answering and retrieval defaults are unchanged.

Branch: `a2.1/coverage-corrections`. Verified base:
`f94226e2119e57ff5b511ad86e4425bf28eabb8e`, following the published A2 implementation
and sanitized example-env documentation. The review commit is the commit containing
this report; the handoff supplies the verified full local/remote SHA. No prior
commits or historical pilot manifests were rewritten.

## Reproduced findings and corrections

Before implementation, seven synthetic cases against the base returned **6 failed,
1 passed** (`12.46s`, three warnings). All five planner findings reproduced;
unchanged-identity resume already passed. The final regression file contains 20
cases, all passing within the final suite.

| Counterexample | Base observation | Corrected result |
|---|---|---|
| Verified production full; audit lacks that entry | Weaker audit assessment could overwrite KB full | Covered and reachable; production proof retained, no redundant verification |
| Uncertain initial batch; identical broader entries | Empty expansion could become unsupported | Uncertain/review-needed, original batch uncertainty retained |
| Production a1 plus compatible audit a2 | Phases assessed separately | Reconciled/verified full KB evidence; production context remains partial |
| Resume with completed rows after runtime/serving changes | Identities could be overwritten | Incompatible run; original identity values retained, no new row calls |
| Apparent support for all aspects, no compatible verified proof | Partial gap with zero missing aspects possible | Review-needed with compatibility and bounded-search reasons |

`question-ledger-1` holds per-entry validated evidence, phase provenance, evaluated
entry status and proof identities. Production, initial audit, broader audit and
the question union have independently scoped views. Per-entry support may be reused;
a joint batch verdict cannot be copied to a different subset. Accepted and rejected
identical proofs share their verification result. Reconciliation receives full
source evidence with conditions, dependencies and citations. Eight greedy seed
bundles per view are a bounded search, explicitly non-exhaustive.

Verified production full always establishes KB coverage and reachability. Compatible
cross-phase evidence can establish KB coverage; audit evidence cannot establish
production sufficiency. A production-only failure leaves production reachability
uncertain without destroying an independent audit proof. Uncertain batches,
oversized/failed entries, conflicts and failed verification remain scoped review
codes until explicitly resolved. Apparent all-aspect support without a verified
combination is review-needed. Possible gaps require identifiable unsupported
aspects and no unresolved uncertainty that invalidates that conclusion.

The 300-entry budget counts distinct entries actually submitted, including a failed
structured response; validated evidence is separate. Repeated phase retrieval or
the one allowed response recovery never counts the same entry twice. Initial
150/150/150 and broader 300/300/300 retrieval, full-pool question/category/subcategory
reranking, top-50 initial evaluation and five-entry maximum batches are unchanged.
No answer-aware reranking, factual-answer generation or recommendations were added.

## Identities, export revisions and privacy

`run-identity-1` pins settings and obtainable serving identities **before selected
query evaluation**. It includes effective production performance/retrieval settings,
audit settings, alias hash, classifier configuration/checkpoint hash, preparation
behavior, generation context/version/model identity, and embedding/reranking `/info`
identities/limits. Endpoint/model names are opaque where appropriate. Missing immutable
weights/tokenizer provenance is explicitly unverified; a reported TEI `model_sha`
is an observation, not a guaranteed weight digest.

Resume compares current values with the original pinned map and hashes; it does
not overwrite them. Code/template/schema changes are also checked. Incompatible
retained work requires a new run. Legacy runs with retained work and no original
pin cannot resume through changed code. Post-row checks also detect observed drift.
Snapshot/Qdrant bracketing and candidate content checks continue unchanged; they
cannot freeze live retrieval or detect every transient/ABA change or replacement
of weights behind an unchanged alias.

The final pilot was executed on the correction worktree before its publication
commit. Its recorded Git HEAD is the base, with exact per-file correction hashes;
those inference files were held unchanged during evaluation. A final review after
completion corrected one additional drift-only outcome label in `pipeline.py`
from needs-context to needs-review, with a deterministic source-drift regression.
That branch was not exercised by the source-consistent live run; its original code
hash remains recorded, and it must not resume through the final file change.
The exact pilot pipeline is durably preserved at
`archive/a21_pilot_code_1/pipeline.py` under the protected artifact root
(SHA-256 `e359eca561a161765c1927897105e6f46e473164a3e91e92db99d613102702ff`).
The publication commit includes the corrected drift label without rewriting pilot
metadata or repeating the live five-query evaluation for a non-exercised branch.

CSV/manifest version 2 adds `run_identity_id`, `export_revision_id`, phase-specific
review/provenance, safe validation diagnostics and recovery accounting. “Prepare
download” captures an immutable pair under the row/meta lock; both URLs pin its
revision. Progress cannot regenerate those bytes. Repeated downloads are stable;
a new explicit revision captures newer progress. Legacy unqualified GETs retain
the latest explicitly created projection; callers coordinating concurrent refreshes
must use the returned revision ID. Tests mutate a checkpoint between CSV and
manifest requests and check old/new hashes and repeated downloads.

UTF-8 BOM, quoting/newlines, JSON cells, formula protection, duplicates, source
ordering, all pending/excluded/error rows, redacted query forms and recommendation
`unassessed` fields remain intact. Capture state and pilot scope prevent labeling
incomplete runs as full-dataset evaluation. Evidence-visible and restricted
projections have separate protected revisions; revoked evidence permission cannot
read the old privileged projection.

Default deny remains `KNOWLEDGE_COVERAGE_ACCESS_GRANTS={}`. No real account was
granted access. All 16 page/API routes retain authentication, ownership, capability
and CSRF enforcement where applicable; the new export-revision POST requires
export/results capabilities and CSRF. Query details show explicit verified/apparent
support, missing/unresolved aspects, compatibility/verification reasons, review/error
codes and stopping reasons. Missing preceding history uses `needs_context`;
other uncertainty uses `needs_review`.

Root dotenv is loaded through the existing mechanism without displaying secrets.
No new permanent env variables were introduced. Fixed schema/recovery/identity
policy versions are included in the runtime manifest. Existing five audit settings,
their defaults, validation and template/local-env propagation remain unchanged.
Private env edits and the user-deleted staging template are preserved.

Artifact root remains `/root/projects/faq-private/knowledge-coverage`, outside Git
and public static roots, directories 0700/files 0600. Customer queries, snapshots,
run outputs and filled prompts are not included in this report or committed
fixtures. Only synthetic browser screenshots are committed. Existing redaction
limitations remain: pattern matching is not comprehensive PII detection; consistent
placeholders preserve references, but redaction can alter text and needs review.

Input SHA-256 remains
`f2e963046de586df6e187a33cac12ba3900c60d5a408066b50bc5fe2f896f3fe`.
Dataset `d_62ca6afb6cb231e3105f8aa4746ac3b0` retains 918 user records, including
duplicates, and the unchanged A1 accounting: 10 model-prepared, 857 pending,
51 needs-context. Absence of assistant messages is not a veto. The same legitimate
preceding user-only history is replayed with confirmed Jalali/Asia–Tehran cutoffs;
subject-free ellipsis remains needs-context, never a KB gap.

Original A2 artifacts were fingerprinted before this work: 1,862 files across both
historical runs. All hashes remained unchanged. The preliminary A2.1 run's 929
files were separately fingerprinted before final revalidation and preserved.
Private hash inventories remain in `/tmp/faq-a21-*-artifact-hashes.json`; they are
not Git artifacts or a retention substitute for the durable run files.

## Structured-output diagnosis

Rubric `coverage-rubric-4`; scope `scope-1`, aspects `aspects-2`, batch `batch-1`,
reconciliation `reconciliation-1`, verification `verification-1`, segmenter
`answer-sentences-1`. Schema shapes remain strict and unchanged. Rubric 3 introduced
shared evidence rules; rubric 4 records the bounded recovery policy.

Generation now requests the actual schema via strict `response_format.json_schema`,
the mechanism described by [vLLM's official structured-output documentation](https://docs.vllm.ai/en/latest/features/structured_outputs/).
Five sequential synthetic responsibility probes precede each new live run. Observed
schema support does not replace local schema/redaction/citation/membership/semantic
validation, or guarantee every response will be complete and valid.

Diagnostics save only responsibility/schema version, before/after-redaction stage,
allowlisted field path/error type, prompt/output tokens and finish reason. Unknown
field names become `*`; values, exception messages, raw outputs and filled prompts
are never stored. JSON syntax summaries use static categories/numeric offsets and
object/end flags only.

The preliminary rubric-3 run observed two `json_invalid` failures at the root,
before redaction, with normal `stop`, plus one production batch `length` failure.
Eight bounded diagnostic completions were conducted: two simple synthetic strict
schema probes; two full-schema synthetic probes comparing normal and disabled
thinking; and four identical-input replays of the two failed batches comparing
`response_format` with the direct structured-output carrier. Simple probes passed.
Both full-schema synthetic probes reached their 512-output cap. All four failed-
batch replays passed strict schema checks (518: 156 output tokens; 121: 103).
Thus the live syntax failures did not reproduce; no serving root cause is proven,
and disabled thinking/direct carrier was not introduced as a claimed fix.

The diagnostic calls used 11,166 prompt / 1,574 completion tokens in total. The four
batch replay durations were 5,479.485 / 5,220.788 / 3,456.386 / 3,457.247 ms. Raw
outputs were inspected only in memory and discarded. A protected metadata summary
is archived under `archive/a21_schema_diagnosis_1/summary.json`. No extra CSV query
IDs, production services or factual customer-answer workflow were used.

`json-invalid-stop-one-fresh-response-1` allows one fresh identical request only
for before-redaction JSON syntax failure with `stop`; there is no parser repair,
semantic coercion or fallback. Both attempts are counted and the first diagnostic
is retained. Length, schema-field/type, redaction, citation, semantic, network and
token-budget failures have no recovery. A second syntax failure remains an error.
Synthetic tests verify the limit and each non-recoverable category.

## Actual paired revalidation

The exact same five original IDs are selected explicitly, in the original order:

| Ordinal | Source row ID | Original A2 result |
|---|---|---|
| 387 | `row_bd526b97ad9940b1d6a15871aac7b0ab` | Private-account exclusion |
| 518 | `row_db3be7cdd0b505a4def0a73355236a6f` | Structured-output error |
| 486 | `row_7a55dfd6fb2e3bf750d99fa30e975d30` | Covered and reachable |
| 320 | `row_85acf8adf43bd6feb04d01f90927b68e` | Structured-output error |
| 121 | `row_dedce881f722f95251e3f326f002f465` | Possible partial gap, 300 entries |

Original selection was outcome-independent fixed hash/history/length strata
`a2-pilot-strata-1`; revalidation uses these exact IDs, not new outcome-driven
sampling. Original final A2 run `r_d67252eb2cfc6c33d849dc6c030964e5` is unchanged.
All calls are sequential, guarded confirmed staging, at most five distinct CSV
queries. The protected snapshot remains
`41bffc05e91c02e288c81f23a45606de54746ead33e11e9ddb24b7d2402e16ef` (1,526 entries);
the source/index signature preflight matched. No source-content drift/new snapshot
was required. Entry budget/documents/retrieval/model output cap remain the same;
audit rubric, constrained mode, proof handling and recovery policy differ.

Preliminary new A2.1 run `r_adc731654567c5e01f0b436d0ac190ed` (rubric 3):
32 completions (five capability, 26 audit, one history rewrite), 13 embedding and
16 reranking requests; 60,328 prompt / 5,942 completion tokens, 283.636 seconds
run wall time. It retained two
syntax-error rows, one private exclusion, one covered/reachable row, and one
full-KB/review-needed row with production output-length failure. Evaluated entries
by ordinal were 0 / 15 / 10 / 5 / 45; two full proofs were accepted. Rows 518 and
121 failed before broader conclusions; they were not gaps. This run is preserved,
not silently repaired or resumed after policy changes.

Final rubric-4 run `r_4b85230ac9db94edc715055d1e0d6cf9` completed the five-row pilot,
not full-dataset evaluation. Identities were captured at
`2026-10-14T09:52:22.755804+00:00`, before selected-row evaluation. Run wall time
was 826.869 seconds. Recorded audit/capability call duration totals 723,110.496 ms;
row durations include preparation/retrieval/evaluation. Actual dispatches: **134
completions** (five capability, 128 audit attempts, one legitimate history rewrite),
15 embedding and 28 reranking requests. There were 132 returned completions with
reported usage **343,638 prompt / 17,334 output tokens**; two unreturned attempts
have unknown served usage. No JSON-syntax recovery occurred and no schema validation
failure was observed in this final run. Zero observed syntax failures cannot be
attributed to the unused recovery policy or presented as guaranteed correctness.

| Ordinal | Final outcome / change from original A2 | Entries submitted | Audit calls | Prompt preflight / observed output tokens | Duration ms |
|---|---|---:|---:|---:|---:|
| 387 | Excluded, unchanged private-account scope | 0 | 1 | 907 / 65 | 3,104.471 |
| 518 | Covered but not reachable; previous schema error | 225 | 59 | 160,848 / 10,321 | 408,880.071 |
| 486 | Error/uncertain; previously covered and reachable | 5 | 3 | 4,460 / 136 | 55,899.729 |
| 320 | Error/uncertain; previous schema error | 5 | 3 | 4,520 / 200 | 57,725.931 |
| 121 | Possible partial gap, same outcome class | 300 | 62 | 173,059 / 6,045 | 261,753.372 |

Per-row prompt columns include tokenized planned input for unreturned calls,
not verified usage for those two attempts; output columns are returned usage only.
The capability and history-rewrite usage is included in the overall server-reported
total, not those row audit columns. Two batch calls ended without a response after
40,038.319 / 40,041.151 ms; their content-free metrics are `error`, finish reason
`not_returned`, public row code `audit_failed`. No validation values/output exist
for those attempts. The request failure root cause is unverified; neither row
receives a KB-gap or reachability conclusion. No retry/resume of this run was
performed to replace those errors.

Row 518 has required IDs `a1`,`a2`. Its accepted cross-batch proof cites this
snapshot's FAQ/chunk **231 sentence 1** for a1 and a2 (conditional; two conditions),
plus **143 sentence 1** for a2. Reconciliation supplied full source/condition text;
verification bundle
`017ac2a5048d1e4ef8454590b128db297bb1f876e005bd97126aec6d9e3be171`
accepted both aspects with none unresolved. Production context was independently
assessed unsupported; initial audit was uncertain, and broader evidence established
verified full. This is one verified compatible model proof, not human ground truth.

Row 121 supports a2 with FAQ/chunk **77 sentences 1 and 4**, under one recorded
condition per support. **a1 remains unsupported** after the 300-entry broader pool;
there are no unresolved evaluation review codes invalidating this possible-partial
conclusion. It stops at `candidate_exhausted` with the 300 distinct-entry budget
also fully consumed. No whole-KB absence is established. Rows 486/320 have requested
aspect checklists but no completed assessment; their empty exported missing-aspect
arrays mean unknown assessment, not evidence that nothing is missing.

Proof reuse is deterministic in synthetic counterexamples and row 121 uses 62
audit calls versus original A2's 64; original separate full-proof verification is
also eliminated. These live differences are not isolated speed/quality effects:
rubric/constrained generation changed, model responses varied, row 518 evaluated
more entries than its original failed attempt, and rows 486/320 failed remotely.
Comparisons are observations, not calibrated accuracy or a performance benchmark.

Full 918-row export: one covered-but-not-reachable, one possible partial gap,
one excluded, two errors, **51 needs-context and 862 pending**. Preparation counts
are 15 prepared (including A1's ten), 852 pending-model and 51 needs-context.
Coverage-pending is separate from preparation-pending. All row IDs/order, duplicates,
BOM, shared export/revision IDs and CSV hash were verified against the manifest.

| Final identity | Value |
|---|---|
| Run identity | `2cc1f136606d081ce709013b6145531a142f5c0a46cab42ec34c9732e2030748` |
| Configuration | `612ae07b95c73e769d8b2e487a668e480efb08f6204365a8b9b90cd1161f5edb` |
| Export revision | `rev_1654b7fc470873d73a70341369513661` |
| Export content identity | `013880ae444e352ecccde48055ee271a45639098723ef3803b90d8511b26f457` |
| CSV SHA-256 | `e121fedf0c998fe13f599d5784a68bffddd9221c096b80af6070fd65d181e8a4` |

Protected files are `runs/<run_id>/meta.json`, per-row checkpoints,
`model-metrics.jsonl`, `completion-usage.jsonl`, `pilot-summary.json`, and
`exports/evidence/<revision_id>/{coverage.csv,manifest.json}`. The CLI also saves
the matching run-level `coverage.csv` / `export-manifest.json`. Served generation
version was 0.26.0, context limit 8,192, chat-template tokenizer counting plus
1,200 reserved output and 128 margin. Immutable model/tokenizer revisions remain
unverified. This does not freeze the serving stack.

Across A2.1 preliminary/final runs and eight diagnostic probes, there were **174
completion dispatches**, 172 returned responses, **415,132 reported prompt /
24,850 output tokens**, and only the original five distinct CSV query IDs.
Two unreturned requests have unknown additional server usage. There were 28
embedding / 44 reranking requests across the two pilots; diagnostic probes did
not retrieve. No generation of new factual customer answers was invoked.

## Executed validation

All Python commands used:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Before: `python -m pytest tests/test_knowledge_coverage_corrections.py -q`
returned 6 failed, 1 passed. Final comprehensive command:

```bash
python -m pytest tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py tests/test_structured_logging.py tests/test_offline_frontend.py -q
```

Result: **414 passed, 203 subtests passed, 39 warnings, 20.34 seconds**. Warnings
are existing deprecations/NVML unavailability. Earlier focused final-core command
(`corrections`, `pipeline`, `access_jobs`) passed 50 tests / four warnings in 14.64s
before the five additional recovery/settings cases. A restricted-sandbox invocation
stalled at the TestClient case and was interrupted; the successful comprehensive
execution had local socket access. No live service is used by these regressions.

After adding explicit manifest/provenance assertions to each resume case,
`python -m pytest tests/test_knowledge_coverage_corrections.py -q` passed all
20 cases / three warnings in 12.25s. Original serving/runtime/audit identity values
remain in the export after incompatibility; unchanged resume skips completed rows.

After the final drift-only label correction,
`python -m pytest tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py -q`
passed **55 tests / four warnings in 13.53s**; source drift explicitly asserts
needs-review rather than missing history. Compilation and whitespace checks were
repeated successfully. The broader 414-test suite predates only that label change
and the extra provenance assertions; unchanged subsystems were not retested again.

```bash
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit scripts/knowledge_coverage_pilot.py tests/knowledge_coverage_browser_app.py tests/test_knowledge_coverage_corrections.py
node --check static/js/knowledge_coverage.js
node --check tests/knowledge_coverage.browser.cjs
git diff --check
```

Results: 3 audit / 6 KB / 5 analytics frontend checks passed. Offline audit PASS,
zero external runtime dependencies. Compilation, JavaScript syntax and whitespace
checks passed. Model coverage tests use deterministic fictional Q/A and mocked
responses, including exact/paraphrase, cross-batch support, incompatibility,
production equivalents, referrals, false-full/citation/injection failures,
overflow, drift, cancellation, owner/CSRF and CSV safety.

The final live command (also used for the preserved preliminary run):

```bash
python scripts/knowledge_coverage_pilot.py pilot --dataset-id d_62ca6afb6cb231e3105f8aa4746ac3b0 --snapshot-id 41bffc05e91c02e288c81f23a45606de54746ead33e11e9ddb24b7d2402e16ef --entry-budget 300 --row-ids row_bd526b97ad9940b1d6a15871aac7b0ab row_db3be7cdd0b505a4def0a73355236a6f row_7a55dfd6fb2e3bf750d99fa30e975d30 row_85acf8adf43bd6feb04d01f90927b68e row_dedce881f722f95251e3f326f002f465 --confirmed-staging
```

## Actual browser acceptance

The isolated fixture replaces startup/service dependencies and authentication with
synthetic account 990001; grants exist only in that process. Its artifacts are
isolated temporary synthetic data, never the customer dataset or operator runs.
Shared services and persistent real-account privileges are unchanged.

```bash
python -m tests.knowledge_coverage_browser_app --port 18761
node tests/knowledge_coverage.browser.cjs /tmp/faq-a21-browser-node http://127.0.0.1:18761 /tmp/faq-a21-browser-evidence-final-rubric4
```

Actual Playwright/Chromium **153.0.8010.0** passed seven check groups: synthetic
authenticated upload/BOM/Persian/multiline/mapping/invalid preservation; pilot
selection/background progress; cancellation/pinned retry; supported/missing
aspects and evidence links; error/stopping details; actual matching immutable
CSV/manifest downloads; keyboard focus/return, light/dark, RTL and 390/1024px layouts
without page overflow. Six export rows include duplicate, invalid and missing-
context records. Browser network requests were restricted to the fixture origin.

Browser setup initially encountered PyPI timeouts and a blocked official Chromium
download; isolated npm Playwright plus packaged Chromium provided the working
browser without changing project dependencies. DOM checks are reported separately
from this actual rendered acceptance. No real-account/live-inference browser flow,
Excel desktop, screen-reader acceptance or production browser was tested.

Synthetic screenshots and machine check inventory:
[desktop light](assets/a2_1_synthetic/desktop-light.png),
[desktop dark](assets/a2_1_synthetic/desktop-dark.png),
[error detail](assets/a2_1_synthetic/error-detail-light.png),
[mobile RTL light](assets/a2_1_synthetic/mobile-rtl-light.png),
[mobile RTL dark](assets/a2_1_synthetic/mobile-rtl-dark.png),
[check inventory](assets/a2_1_synthetic/browser-checks.json).
Desktop/mobile screenshots were visually inspected; they are fictional evidence,
not screenshots of the customer pilot.

## Scoped files and remaining review

Scoped code: `knowledge_audit/{api,export,jobs,model,pipeline,prompts,runtime,schemas,
service,settings,store}.py`, `scripts/knowledge_coverage_pilot.py`,
`web_permissions.py`, dashboard template/CSS/JS. Tests: new correction regressions,
isolated browser fixture/driver, updated pipeline/frontend/permission regressions.
Documentation: this report, implementation plan, CSV contract, rubric/schema doc
and six synthetic browser assets. Ignored authorized docs are explicitly added;
the user's ignore rule, deleted staging template and unrelated work stay untouched.

The historical credential exposure discovered during A2 publication is separate:
older `env.example` history contained PostgreSQL credential values, predating P0
and already reachable from origin/main. Current examples are sanitized. Outstanding
operator action is to assess exposure and rotate the affected external credentials
through the owner's process, and decide any coordinated repository-history cleanup.
No values are reproduced, no credential rotation occurred, and Git history was not
rewritten. Private `.env`/`.env_latest` are excluded from publication.

Remaining gates: human review of evidence/aspects, calibration, immutable serving
weight/tokenizer provenance, full-run/retention acceptance and the production
repair release blockers. The original A2 two schema errors remain in immutable
historical results; A2.1 diagnoses and boundedly revalidates them rather than
rewriting those results. Historical missing browser validation is now addressed
by synthetic rendered checks; real-account/live-inference browser acceptance
remains unperformed. No whole-KB absence or production release is claimed.

Final revalidation still has two unreturned model-call errors (486/320), while
the preliminary run retains its two syntax errors and production output-length
failure. Investigating those serving failures and human-reviewing the accepted
proof/partial aspect are the recommended next bounded review scope. No broader
dataset evaluation or A3 work should follow without planner authorization.
