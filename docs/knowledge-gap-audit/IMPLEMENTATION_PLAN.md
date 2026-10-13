# Knowledge coverage audit — implementation plan

Contract version: `p0-contract-1`. Baseline: [P0_BASELINE_REPORT.md](P0_BASELINE_REPORT.md).
UI/export contract: [DASHBOARD_AND_CSV_CONTRACT.md](DASHBOARD_AND_CSV_CONTRACT.md).
P0/P0.1 established the baseline; production repairs are recorded in
[P1_RRF_REPORT.md](P1_RRF_REPORT.md) and
[P2_RETRIEVAL_DEPTH_REPORT.md](P2_RETRIEVAL_DEPTH_REPORT.md) and
[P3_RERANKER_BATCHING_REPORT.md](P3_RERANKER_BATCHING_REPORT.md) and
[P4_KB_TAXONOMY_REPORT.md](P4_KB_TAXONOMY_REPORT.md). Each later stage requires planner review
and explicit authorization; Codex returns a scoped report/commit and stops after
each stage. P4 implementation does not authorize the production acceptance gate,
audit implementation, or deployment.

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

P3 review readiness is not an authorization to deploy or start P4. No naturally
occurring unlabeled queries can supply a measured answer-quality error rate.
Choose tolerances and label sets before experiments, rather than after results.

## Audit stages after production acceptance

| Stage | Scope and delivered acceptance boundary |
|---|---|
| **A1 frozen-input and replay foundation** | Input-row manifest, CSV mapping and supported read-only DB query source; private consistent KB snapshot and stable IDs; timestamp/session policy; chronological replay provider; production preparation parity; early scope routing; persisted run/row contract and bounded worker design. No invocation of production history writes/tickets/feedback. Tests prove row conservation and no future leakage. |
| **A2 early end-to-end pilot — page + CSV required** | Minimal complete coverage pipeline: aspect extraction, production-default baseline, broader candidates (~150), title/taxonomy rerank (~50 distinct entries), tokenizer-budgeted up-to-five full Q/A entries per batch, sentence citations, reconciliation, short full-coverage verification. **Functional new main-dashboard page**, authorized navigation, upload/mapping, DB/scope/session selection, validated settings, start/progress/retry, paginated/filterable results and evidence panel, **initial complete CSV download**. All selected rows exported including error/exclusion/context/invalid rows. Initial pilot may stop after the initial evaluated set and must record that scope; recommendation fields remain empty with explicit not-yet-run state. This stage is before expansion tuning and backend completion. |
| **A3 bounded expansion and calibration** | Use pilot evidence to tune one variable at a time; expand unresolved cases with unrepeated evidence, initially up to 300 **total evaluated distinct entries**, not 300 additional entries. Preserve chronological prep, title-only production rerank policy, token budgets, CSV accounting and baseline reachability. Evaluate retrieval breadth, stopping reasons, conflicts and verifier rejection rates on controlled labeled tests. Any answer-aware diagnostic requires separate approval and named experiment. |
| **A4 gap and taxonomy recommendations** | Gap analyst consumes structured findings; recommender consumes gap specifications, existing category/subcategory paths and relevant FAQ titles. Suggest question/category/subcategory, flag proposed new paths, cite equivalent/related entries; reviewer approves/rejects recommendations without writing KB automatically. UI details and CSV include multiple recommendations without multiplying rows. No factual-answer generation. |
| **A5 refinement and full export validation** | Polish enterprise dashboard, RTL/LTR/accessibility/responsiveness, protected evidence/versions, search/filter/pagination and state transitions. Validate full schema, redaction, Persian/Excel/quoting/formula safety; manifest-versus-export check and zero dropped rows. Real visual screenshots and keyboard checks against both existing themes. |
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
Early audit routing distinguishes KB questions, chitchat, personal requests,
out-of-scope queries, missing-context questions and routing errors. The active
classifier supplies only actionable/general versus chitchat: general is not proof
of KB scope. Ambiguous scope must be reviewed, not silently excluded or called a gap.

Use a separate, non-production history provider. `TurnExecutionPolicy` and
`enforce_history_policy` are useful existing safety boundaries; a metadata-backed
`ProductionHistoryProvider` is incompatible with historical cutoffs and can write.
Do not use latest session summaries or regenerate factual assistant replies to
fill missing historical answers. Reuse formatting/normalization without calling
the full answering graph merely to prepare a query.

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
