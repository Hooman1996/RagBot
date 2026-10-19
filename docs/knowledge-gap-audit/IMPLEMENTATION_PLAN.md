# Knowledge coverage audit — implementation plan

Contract version: `p0-contract-1`. Baseline: [P0_BASELINE_REPORT.md](P0_BASELINE_REPORT.md).
UI/export contract: [DASHBOARD_AND_CSV_CONTRACT.md](DASHBOARD_AND_CSV_CONTRACT.md).
P0/P0.1 established the baseline; production repairs are recorded in
[P1_RRF_REPORT.md](P1_RRF_REPORT.md) and
[P2_RETRIEVAL_DEPTH_REPORT.md](P2_RETRIEVAL_DEPTH_REPORT.md) and
[P3_RERANKER_BATCHING_REPORT.md](P3_RERANKER_BATCHING_REPORT.md) and
[P4_KB_TAXONOMY_REPORT.md](P4_KB_TAXONOMY_REPORT.md). The combined validation is recorded in
[PRODUCTION_REPAIR_ACCEPTANCE_REPORT.md](PRODUCTION_REPAIR_ACCEPTANCE_REPORT.md).
Each later stage requires planner review
and explicit authorization; Codex returns a scoped report/commit and stops after
each stage. The combined gate is validation only; it does not authorize audit
implementation or deployment.

## Invariants

1. Production repairs precede audit implementation. No production infrastructure
   changes from this repository; preserve unrelated work.
2. One major variable per performance experiment; before/after measurements on
   identical frozen inputs and configurations except that variable. Behavior
   changes require retrieval and answer-quality tests, including prompt/context
   effects. Do not silently relax gates if data/runtime is missing.
3. Process **all rows in the selected input by default**, regardless of outcomes,
   feedback, referrals or whether assistant answers exist. Explicit pilot subsets
   carry their selection rule, selected IDs, input/selected counts and subset label.
4. Source-row identity is immutable. Deduplication shares computation, never
   removes output rows. Invalid, excluded, context-dependent and failed rows all
   have corresponding terminal CSV results. CSV is the primary user deliverable.
5. Broader retrieval follows the repaired production sparse+dense+RRF+title/
   taxonomy reranker. Capture a separate production-default retrieval/context
   baseline. No answer-aware reranker substitution or exhaustive full-KB scoring.
6. A bounded search can identify **possible gaps within its recorded scope**;
   it cannot prove absence throughout the KB. Confidence is not a probability.
7. No raw prompts, responses, customer/banking content, authentication or copied
   source rows in operational logs. Private evidence records use approved access,
   retention and redaction; versioned source references explain results without
   chain-of-thought. Recommendations contain questions and taxonomy, never facts
   presented as newly drafted answers.

## Production stages and acceptance gate

| Stage | Single authorized objective when approved | Required evidence |
|---|---|---|
| **P0 baseline** | Documentation, safe reproducible observations and implementation contract only. | Current source/state, executed offline diagnostics, blocked live checks explicitly separated. Completed for review. |
| **P1 RRF correction** | Missing-list contribution becomes zero; retain k=60 and deterministic secondary ordering. Do not change depths, batching, taxonomy, prompts or defaults. | Single-list rank-1 score 1/61, disjoint/overlap/empty lists, long-list ranks >61, stable ties. Before/after count/ID/rank/context/call-size/latency plus labeled retrieval and answer quality on same frozen fixtures. Rank changes are expected and must be reviewed, not hidden by old rankings. |
| **P2 configurable retrieval depths** | Separate lexical/dense/fused depths with internal request-local overrides; preserve configured context selection and production defaults. `RAG_BM25_CANDIDATE_LIMIT=50` replaces the fixed slice. | Positive integer validation; final count is a maximum over the distinct combined pool, with no single-branch upper bound or padding. Preserve context-versus-final validation. Verify >50, small corpora, ties, deduplication, concurrent isolation, corpus-cache reuse and default parity. Benchmark one depth variable at a time. Propagate permanent env keys. Expanded end-to-end validation depends on P3. |
| **P3 safe reranker batching** | Bound each client request by currently verified server max_client_batch_size and token/input limits. Keep question/category/subcategory scoring. Map local indexes to global IDs and perform one global ordering/selection. | Exact/multiple/remainder batches; out-of-order/duplicate/missing/boolean/out-of-range indexes; nonfinite scores; empty input, ties, partial service failures and cancellation; stable global selection and comparable score mode across batches. Validate context and separate related-question paths. Before/after batching benchmark with other depths fixed. |
| **P4 taxonomy preservation** | Explicitly preserve/create/edit/revert category/subcategory with safe legacy parsing and version provenance. No fabricated taxonomy recovery from missing historical versions. | Structured taxonomy survives PG/version/Qdrant/embedding/cache-revision paths; clean fields and legacy taxonomy-in-answer cases; revert with/without taxonomy, empty/unknown category, compensation/concurrent-edit tests. Retrieval/answer-quality checks and bounded before/after update/retrieval measurements on isolated fixtures. |
| **Production acceptance gate** | Planner reviews P1–P4 evidence before any audit stage. | Correct mechanics, frozen input consistency, real labeled retrieval/answer quality, unchanged intended prompt/rerank policy, 50-second external deadline, paired latency/resource results and owner-approved regression tolerance. Missing live evidence prevents production acceptance, even if code can be reviewed. No deployment is implied. |

### Combined P1–P4 gate outcome

Technical checks passed: 248 backend tests / 203 subtests, 18 lifecycle/admission
tests, 36 asset/embedding tests / 10 subtests, 11 frontend tests and the offline
dependency audit. Frozen P1/P2/P4 default results match; original/final comparisons
reproduce the intended RRF correction and synthetic taxonomy preservation.
Sequential staging 150/300 retrieval accounts for all candidates using 3/6
requests of 50, with full content retained. Snapshot/signature/configuration
checks and cold/cached discovery behavior passed. No substantive repair-code
defect was confirmed and no implementation behavior changed in this gate.

Development readiness: repairs are technically reviewable; these results support
development planning. Release readiness: **blocked**, with no deployment approval.
The 10 repository banking queries have relevance-only labels whose current
validity needs review: original/final frozen retrieval both include only 3/19
expected IDs; final context includes 1/19. Required-answer facts, unsupported-claim
labels and human review are absent; the supplied `General_FAQ.csv` is the KB,
not an independent evaluation set. Source-derived referral checks and nine
synthetic lexical checks do not close that gap. Obtain current-snapshot labels,
conditions/referral expectations and human-reviewed outputs before quality acceptance.

Other blocked checks require exclusively owned isolated PG/Qdrant write fixtures
for transactional create/edit/revert/cleanup; a local browser or an approved
reachable isolated editor for actual visual/keyboard/RTL checks; and suitable
staging GPU telemetry plus a defined load/deadline budget and regression tolerance.
Serving-limit changes require client recreation because discovery is cached.
Production gateway `/info` access and immutable weight/tokenizer provenance also
remain release prerequisites. No production service was contacted.

The user explicitly authorized **A1 input/replay/snapshot foundations**. A1 is
implemented for planner review in
[A1_INPUT_REPLAY_SNAPSHOT_REPORT.md](A1_INPUT_REPLAY_SNAPSHOT_REPORT.md).
This authorization does not resolve the repair gate's release blockers.
The user subsequently authorized **A2**. The functional main-dashboard page,
bounded end-to-end pilot and complete per-input-row CSV are implemented for
review in [A2_END_TO_END_PILOT_REPORT.md](A2_END_TO_END_PILOT_REPORT.md).
All 918 rows remain represented; five distinct queries were live-piloted.
Strict model-output errors and pending/context rows are retained. Browser,
human-label/calibration and full-run/release acceptance remain outstanding.

The user subsequently authorized **A2.1 planner corrections and bounded paired
revalidation**. Shared question-level evidence, immutable run identities and
export revisions, safe structured-output diagnostics and bounded syntax recovery
are implemented in [A2_1_CORRECTION_REPORT.md](A2_1_CORRECTION_REPORT.md).
Actual synthetic authenticated Chromium checks now cover the main-dashboard
flow, evidence, downloads, keyboard, RTL and themes. The live revalidation uses
only the same five query IDs in new protected runs; all 918 export rows remain.
Historical pilot artifacts are preserved. This stage does not authorize A3,
recommendations, a full-dataset audit, deployment or production changes.

The user subsequently authorized **A2.2 bounded model-call reliability diagnosis**.
[A2_2_MODEL_RELIABILITY_REPORT.md](A2_2_MODEL_RELIABILITY_REPORT.md) records the
12-dispatch transport/output-policy diagnosis, safe failure taxonomy, a two-entry
audit batch cap, one new same-five-query pilot and a protected blank human-review
package. Production client settings, serving flags and infrastructure remain
unchanged. This stage does not authorize A3 or full-dataset evaluation; model
observations still require independent human review and reliability acceptance.

The user subsequently authorized **A3 controlled calibration and independent-review integration**.
See [A3_CALIBRATION_REPORT.md](A3_CALIBRATION_REPORT.md). Fictional seeded variants
use fixed candidate manifests; they do not measure live hybrid-search recall.
The audit-local batch cap is validated 1–5, default 2, and remains pinned to run
identities. Independent real-query labels are unavailable and calibration remains
pending. This scope does not authorize recommendations or full-dataset evaluation.

The user authorized **A4 structured gap analysis and question/taxonomy proposals**.
[A4_RECOMMENDATION_REPORT.md](A4_RECOMMENDATION_REPORT.md) records eligibility,
separate versioned model inputs, snapshot metadata-only lookup, immutable drafts/
reviews/combined CSVs, default-deny review capability, actual synthetic Chromium
checks and bounded fictional staging work. Historical coverage/exports remain
unchanged. Independent human confirmation and release acceptance remain pending.
No factual answers, KB writes, recommendations for covered/unreachable results,
A5 or full-dataset evaluation are authorized by this implementation.

The user authorized **A5 dashboard refinement and complete export validation**.
[A5_DASHBOARD_EXPORT_REPORT.md](A5_DASHBOARD_EXPORT_REPORT.md) records an explicit
run-level frozen-source/draft/review selection map, immutable permission-specific
CSV/manifest pairs, 918-row synthetic conservation, protected customer accounting
and actual synthetic browser checks at 390/768/1280/1440 pixels. Query details and
pilot/input denominators are clearer; model prompts/settings, retrieval and
recommendation eligibility are unchanged. A5 makes zero model or external data/inference service calls.
Native spreadsheet validation remains unavailable and independent human labels
remain pending. A6 scaling, retention, worker/load hardening and any full-input
model execution require separate authorization.

No naturally occurring unlabeled queries can supply a measured answer-quality error rate.
Choose tolerances and label sets before experiments, rather than after results.

## Audit stages after production acceptance

| Stage | Scope and delivered acceptance boundary |
|---|---|
| **A1 input/replay/snapshot foundations — implemented for review** | Explicit CSV mapping and future DB adapter interface; stable row IDs; private versioned redacted full-content PG snapshot verified against bracketing source/index signatures; confirmed calendar/timezone policy; strict cutoff history provider; production preparation components and parity tests; reusable preparation-only CSV/manifest and sequential CLI sample capped at 10 query rows. No DB input query implementation, scope extension, coverage evaluation, durable worker or page. No production history writes/tickets/feedback. See A1 report for executed evidence and limitations. |
| **A2 early end-to-end pilot — implemented for review** | A1 CSV/replay/preparation reused; strict scope/aspects/batch/reconciliation/verification; frozen numbered evidence; independent production-context sufficiency; request-local 150/150/150 full-pool question/taxonomy rerank and initial top 50, followed by 300/300/300 for unresolved eligible questions within 300 total distinct evaluated entries; served-template token counting and up to five full Q/A entries per batch. Main `/knowledge-coverage` upload/explicit mapping, knowledge-document scope, up-to-five pilot selection/budget, progress/cancel/retry, filters/evidence and complete 918-row CSV/manifest. Default-deny per-user capabilities, protected durable artifacts and row checkpoints/leases; recommendations unassessed. Database input remains the A1 interface, not a fabricated query schema or UI. Actual five-query pilot and limitations are in the A2 report. |
| **A3 controlled calibration — implemented for review** | Measure A2's existing engine against frozen fictional facts and isolated seeded removals; separately compare batch caps 2/5 with model-derived aspects held fixed. Import declared independent human labels only when supplied. Preserve the 300 total distinct-entry cap, unrepeated expansion evidence, chronology, question/taxonomy scoring, token budgets, CSV accounting and independent baseline sufficiency. Review schema failures, compatibility-call costs, breadth, stopping reasons/conflicts and verifier rejection rates. Any answer-aware diagnostic requires separate approval and named experiment. |
| **A4 gap and taxonomy recommendations — implemented for review** | Gap analyst consumes structured findings; recommender consumes gap specifications, existing category/subcategory paths and relevant FAQ titles. Suggest question/category/subcategory, flag proposed new paths, cite equivalent/related entries; reviewer approves/rejects recommendations without writing KB automatically. UI details and CSV include multiple recommendations without multiplying rows. No factual-answer generation. |
| **A5 refinement and full export validation — implemented for review** | Polish enterprise dashboard, RTL/LTR/accessibility/responsiveness, protected evidence/versions, search/filter/pagination and state transitions. Validate full schema, redaction, Persian/Excel/quoting/formula safety; manifest-versus-export check and zero dropped rows. Real visual screenshots and keyboard checks against both existing themes. |
| **A6 operational hardening and full-run readiness** | Durable interruption/resume, scoped retries, idempotency, checkpoints, leases/ownership, cancellation/deadlines, cleanup/retention, per-service caps and safe metadata telemetry. Confirm bounded CPU/RAM/GPU/service use under approved staging traffic, interference with normal chat and complete large-run row accounting. Planner accepts full-run readiness before an explicitly selected full dataset run. |

These are review boundaries, not commands to begin feature work. A1 job/schema
decisions and A2 artifacts require separate authorization. No new libraries,
runtime variables, routes, schema or workers are created in P0.

## Query preparation and chronology contract

Reuse the actual order from `AnsweringService._answer`, not an independently
invented rewrite/classification chain:

```text
original meaning → Parsivar normalization → Persian phrase normalization
  → preceding session history → production rewrite (only when history exists)
  → normalized standalone wording → current classifier → general-only aliases
  → datasource validation → recorded retrieval wording and baseline
```

Keep original, normalized, standalone/effective and canonical retrieval wording
separate, with redacted views. Aspect extraction evaluates intended standalone
meaning, not aliases that introduce expanded retrieval vocabulary. Record rewrite
use, history completeness, alias artifact hash and classifier artifact hash.
In A2, additional audit routing will distinguish KB questions, chitchat, personal requests,
out-of-scope queries, missing-context questions and routing errors. The active
classifier supplies only actionable/general versus chitchat: general is not proof
of KB scope. Ambiguous scope must be reviewed, not silently excluded or called a gap.

Use a separate, non-production history provider. `TurnExecutionPolicy` and
`enforce_history_policy` are useful existing safety boundaries; a metadata-backed
`ProductionHistoryProvider` is incompatible with historical cutoffs and can write.
Do not use latest session summaries or regenerate factual assistant replies to
fill missing historical answers. Reuse formatting/normalization without calling
the full answering graph merely to prepare a query.

A1 records only the classifier's existing intent and `chitchat`/`unknown`
scope. It retains original redacted, normalized, history-resolved and canonical
retrieval forms separately. All 918 supplied query rows were parsed/normalized/
exported; the successful live pass prepared only the first 10 chronological
query rows. Other rows are explicitly `pending_model` or `needs_context`;
coverage fields are empty. Its distinct preparation schema is documented in the
dashboard/CSV contract, and is not a final coverage result or full model replay.

For DB inputs, read query ID/session/user message creation time and actual
assistant completion time from approved source records. `get_session_queries`
currently orders only by created_at and `get_session_messages` interleaves each
row's answer immediately after its question; neither is an adequate cutoff-aware
event replay. Reconstruct an event timeline: every eligible event must precede
the current turn, be in the same authorized session, and use the assistant's
availability/completion time. A preceding user turn whose answer completed after
the current question contributes no assistant answer. No sessions are joined by
similar text or guessed identities.

Timezone-aware timestamps normalize to UTC while retaining original offset
metadata. DB timestamps are naive (`TIMESTAMP`/datetime.utcnow usage); confirm
source convention rather than assume UTC or Asia/Tehran. CSV naive timestamps
require an explicit run-level source timezone (recorded with parser version);
without it mark time unresolved and disable chronology-dependent conclusions.
Missing timestamps may use a user-confirmed authoritative session row sequence,
labeling that policy; otherwise history is incomplete. Equal user timestamps use
trusted source event sequence, then numeric DB query ID or CSV record ordinal
as a deterministic tie-break. An ordinal makes ordering reproducible but does
not prove true chronology: ambiguous same-time assistant events are excluded
unless trustworthy sequence establishes precedence. Record tie ambiguity.

CSV user-only history may be enriched with preceding database assistant messages
**only** when authorized stable source/session mapping and timestamps are
available. Existing `queries.response_text`/`completed_at` demonstrate source
columns, not proof of complete data. If unavailable, use preceding user messages
where safe, set `history_status=user_only`/`incomplete`, and mark unresolved
elliptical questions `needs_context` rather than possible gaps. Import still works
with query text alone; session/time/feedback/referral/answers remain optional.

## Frozen input, candidate and evidence contracts

Approximate KB size is not an evaluation budget. Freeze full Q/A content, taxonomy,
source/version mappings and sentence offsets in private authorized storage;
retain a matching vector/config checkpoint or approved read-only frozen retrieval
adapter. The evidence snapshot is immutable per run. `kb_signature.py` provides
hashes and cross-store consistency checks, not frozen content or an atomic
PG/Qdrant snapshot. Before/after signatures and revision manifests detect drift;
they cannot alone recover the content that was evaluated. Refuse to combine live
mutable retrieval with mismatched evidence. No DB/schema/vector mutation in P0.

Define `faq_entry_id` from authoritative identity; chunk ID is the known stable
identifier in current code. Verify whether each FAQ is exactly one chunk, whether
multiple chunks compose one FAQ, and how duplicates/versions map before selecting
50 distinct entries. Never use generation XML ordinal IDs as persistent FAQ IDs.
Persist original full Q/A, immutable content hash, version and deterministic
sentence-number/character-offset map per snapshot privately. Preserve conditions,
exceptions, bullet/numbered clauses, Persian punctuation and mixed-language
content in segmentation. Citations reference `(snapshot_id, faq_entry_id,
chunk_id, sentence_number)` and validated offsets; they are checked structurally
and for support, not accepted merely because the model supplied an ID.

Initial pilot settings: about 150 fused candidates, 50 distinct reranked entries,
up to five full Q/A entries per evaluation batch. Source defaults baseline is a
separate recorded retrieval/context run on the same query/snapshot; it does not
generate a production answer or write a chat. Rerank question/category/subcategory,
then give **full answers** to the coverage evaluator. Deterministic entry selection
must preserve scores and rank-to-ID mappings, including duplicates and scope.

Batch count alone is not a token budget: tokenize with served tokenizer/chat
template, include rubric/question/aspects/Q/A/IDs, reserve output tokens and a
context margin; reject over-budget packing before sending. One oversized entry
requires explicit `entry_too_long`/review or a separately validated segmentation
policy with stable references; do not silently truncate an answer and claim full
coverage. Rerank pair truncation is also recorded and limits certainty.

Reconcile across all evaluated batches. Coverage may come from one entry,
multiple entries within one batch or complementary entries across batches.
Support requires requested conditions/exceptions to hold, not just topical match;
contradictions and mutually exclusive evidence need review. Proposed full coverage
goes through a short independent verifier; rejection restores unresolved status.
Expansion adds new distinct entries only; initial maximum 300 total evaluated,
subject to pilot settings and current server/token limits. Stop on verified full
coverage, exhausted candidates, evaluation budget, time budget, missing context,
conflict, cancellation or error, recording actual depth and reason per row.

## Six separate model responsibilities

| Responsibility | Input/output boundary |
|---|---|
| Aspect extraction | Intended standalone question and safe preceding context → enumerated requested aspects, conditions, exclusions, ambiguities. No KB-driven omission of difficult requested aspects. |
| Batch coverage | Question/aspects + up-to-five token-budgeted full Q/A entries with sentence IDs → structured support/unresolved/conflict per aspect and evidence references. Answers are included. |
| Question reconciliation | Structured batch findings + cited evidence as needed → question-level support arrangement, remaining aspects/conflicts and concise evidence-grounded explanation. No hidden reasoning trace. |
| Short full-coverage verification | Proposed full coverage, all requested aspects, selected cited answer sentences and necessary conditions → `accepted`/`rejected`/`error` with short reason. Failure cannot result in verified full coverage. |
| Gap analysis | Structured reconciled/verified findings and unresolved aspects → scoped gap specifications, uncertainty and relation to existing support. Does not receive entire KB. |
| Recommendation | Gap specifications + existing taxonomy paths + relevant FAQ titles/IDs → proposed question(s), category/subcategory, new-path flags and equivalent/related IDs. No drafted factual answers. |

Version prompts/rubric/parser/normalizer/aliases/classifier/models/tokenizers/code/
snapshot/settings. No prompt text in operational logs or CSV. Fine-grained secure
prompt artifacts can exist as version-controlled templates in later authorized
code, not copied customer-filled prompts. Report schema validation failures as
errors/review, not confident guesses.

## Pilot selection without outcome flags

Process the entire selected file/source unless an explicit pilot subset is
requested. For a bounded pilot, select deterministically by stable record ID
across lexical length bands, topic/taxonomy hints where available, duplicate
groups and session/history availability. Include Persian orthographic variants,
single/multi-aspect, context-dependent and invalid records. Feedback or referral
flags may stratify when available but must not gate selection. No assistant
answers in CSV is a valid input. Store seed, selection rule and exact row IDs
privately; publish counts and subset label, never imply it is a full-input audit.

## Future test and acceptance matrix (proposed, not executed in P0)

| Area | Required checks |
|---|---|
| Retrieval | Zero missing RRF contribution; sparse/dense/fused independent depths; >50/150/300, empty/short corpora; deterministic ties/string vs numeric IDs; duplicates, stale vectors, snapshot/scoped title membership. Production baseline reachability and source-default parity. |
| Reranker | Batch boundaries, global index mapping, complete outputs, shuffled indexes, ties, global sorting, finite scores, partial failures/retries/cancellation; compatible tokenizer pair budget and score modes; separate related-question path. |
| History | Same-session cutoff; future questions/answers/summaries never supplied; assistant completion after current question; timestamp offsets/naive config/missing/ties; user-only CSV and safe DB enrichment; no production writes. |
| Routing/aspects | Chitchat/personal/out-of-scope/missing-context vs banking KB; false exclusions/route errors; rewrite meaning preserved and aliases distinguished; multi-aspect conditions/exceptions and ambiguity; aspect omission detection. |
| Evidence/coverage | Invalid/hallucinated sentence IDs, bad offsets and snapshot versions rejected; one-entry, within-batch and cross-batch complementary coverage; conflicting conditions, exceptions and stale answers; short verifier rejects false full coverage, schema/protocol errors cannot upgrade coverage. |
| Seeded gaps | Remove answer-bearing sources from isolated immutable snapshots, including cases where equivalent remaining sources still cover the query; no writes to real KB. Measure controlled-test false gap/full-coverage errors against seeded labels. These do **not** establish error rates on naturally occurring unlabeled queries. |
| Row conservation | Every accepted input record maps to exactly one output row; duplicate computation retains separate identities; blank/missing/invalid/excluded/error/context rows; absent optional CSV columns; source_query_id collisions; explicit subset accounting vs full run; no progress denominator excludes invalid rows. |
| Recommendations | Equivalent FAQ prevents duplicate proposal; multiple gap recommendations align taxonomy/new-path flags/related IDs; question-only output; no factual answers; user review cannot mutate KB or privileges automatically. |
| Export | UTF-8 Persian/ZWNJ round trip, UTF-8 BOM/Excel, CSV commas/quotes/multiline quoting, JSON cell structure, formula prefixes including leading whitespace/control/bidi characters, safe sanitized columns only; unchanged input hash; manifest/export count+ID equality, interrupted and partial exports. |
| Dashboard security | Page/API authorization per action, unknown roles deny, CSRF on start/retry/cancel/review/upload, session/row/run ownership, guessing IDs cannot read evidence/exports, pagination/search scope, DB source selection authorization, retention expiry and snapshot-version mismatch. |
| UI | Table/details evidence visible and numbered references usable, hidden evidence clearly labeled; empty/loading/error/partial/completed states, real counts only; keyboard focus/tab/escape/return, screen reader status, contrast, Persian RTL with LTR IDs, 360/768/1280/wide layouts, both themes, offline asset check and actual screenshots. |
| Operations | Crash/cancel/deadline resumes without dropped/duplicated rows; cache includes history/snapshot/version/settings; idempotent checkpoint/retry, bounded resource use and service contention, retention cleanup, progress+CSV error rows; content-safe log regression. |

For every stage report, distinguish executed commands/exit statuses from proposed
checks and controlled mechanics from live quality/performance. Stop after report.

## A6.1 execution and recovery — implemented for planner review

User-authorized A6.1 adds `pilot` (default, maximum five), explicit `subset`, and
server-resolved `full_input` execution against an owned redacted dataset. Source
order is conserved in every export; A1 chronological replay order and strict
history cutoffs remain separate. A configurable maximum rejects oversized runs.
No customer execution or live model/embedding/reranker request is authorized or
performed in this stage.

`coverage-execution-1` persists selection/settings/ownership before processing,
owner/request-bound creation idempotency, file-backed progress indexes and run/
global OS leases. Busy workers remain queued. Persistent cancellation cannot be
reverted by stale progress; a cancellation watcher also stops another process's
local task. Interrupted work is discovered, never automatically replayed at boot.

`audit-boundaries-1` journals dispatch/completion uncertainty and stores only
redacted structured preparation/model results and frozen retrieval ID manifests.
Resume checks identities, schema, hashes, membership/citations and semantic proof
rules again. Completed rows are retained; identical completed boundaries avoid
redispatch. Unknown remote work requires explicit skip or duplicate-work retry
acknowledgement. Attempts, recovery decisions and old immutable exports remain
separate. These controls do not promise exactly-once inference or cancellation
of a remote server request.

Coverage CSV/manifest v5 adds execution/recovery provenance for new A6.1 runs;
historical schemas/bytes remain unchanged. A5 pinned coverage/draft/review exports
remain explicit. See [A6_1_EXECUTION_RECOVERY_REPORT.md](A6_1_EXECUTION_RECOVERY_REPORT.md)
for exact synthetic/browser checks and measured file-I/O comparison.
A6.2 retention, service-load/resource validation and operational acceptance remain
separate gates. No retention deletion, deployment, KB editing, live inference or
actual full customer dataset evaluation is included.

## A6.2 finite operations and retention — planner review

A6.2 adds `audit-operations-1`: immutable finite allowances, durable pre-dispatch
completion/token reservations, cumulative execution time, failure streaks, disk
headroom and audit-local pacing before shared admission. Unknown completion keeps
its conservative charge; restored checkpoints require no new reservation. New
runs expose `paused` and explicit remaining allowance; no in-place extension or
counter reset is supported. Existing scope/aspect/coverage/recommendation prompts,
retrieval defaults, eligibility, model/production timeouts and serving settings
remain unchanged. Five-query pilot remains the default.

`manual-dependency-retention-1` is trusted-operator dry-run/explicit-plan apply;
automatic deletion is disabled. References, ownership, holds, protected/unknown
packages, source privacy keys, shared snapshots and active/recoverable/leased work
are conservatively protected. Real historical artifacts receive dry-run inspection
only. Deletion tests use exclusively owned synthetic temporary stores.

New coverage captures use CSV/manifest v6 for frozen operational counters/policy;
old immutable revisions remain byte-identical. A5's frozen source and explicit
recommendation/review selection remain intact. Full-selection acknowledgement and
budget/recovery/retention status extend the existing protected dashboard. No new
capability, infrastructure or real-user access grant is added.

[A6_2_OPERATIONAL_READINESS_REPORT.md](A6_2_OPERATIONAL_READINESS_REPORT.md) records
mechanical tests, controlled staging interference observations, limits and separate
readiness decisions. [OPERATIONAL_RUNBOOK.md](OPERATIONAL_RUNBOOK.md) provides the
operator handoff. A small staging experiment does not establish production
capacity, an accuracy rate or the 200-concurrent-user SLA. A separately authorized
full-input exploratory run remains distinct from production/quality acceptance.
No actual 918-query customer run, production access, deployment, KB edit or deletion
of real private artifacts is performed in A6.2.
