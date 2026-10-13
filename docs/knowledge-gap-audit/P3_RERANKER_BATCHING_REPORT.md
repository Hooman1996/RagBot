# P3 — safe sequential reranker batching

Status: **READY_FOR_REVIEW**. The requested isolated implementation, protocol
tests, bounded staging comparisons and expanded checks are complete. This does
not approve production release, the production acceptance gate or P4.

## Repository and preserved scope

Checkout `/root/projects/faq`; branch `p3/reranker-batching`; verified base
`d45ddf6684a15b8a376fb8277ce68e0df04f7d7e`. No isolated worktree was needed.
The existing `.gitignore` modification, deleted
`.env.recommended.rtx5880-staging` and pre-existing untracked files were preserved.
Private `.env`/`.env_latest` edits stay local and outside the commit.

Read AGENTS.md, the implementation, baseline/P1/P2 and dashboard/CSV contracts,
and debugging-strategies, python-testing-patterns, rag-implementation and
llm-evaluation skills. No ancestor/nested AGENTS.md files were found.

Only reranker batching/validation/global merging and their configuration,
diagnostics, tests and documentation changed. Retrieval methods are AST-identical
to P2. RRF, candidate depths, datasource filtering, generation prompts/settings,
taxonomy, infrastructure, routes, permissions and schemas are unchanged. Main
dashboard integration, explainability, all-selected-query processing and complete
per-input-row CSV requirements remain intact. P4/audit implementation has not begun.

## Implementation contract

`utils/persian_hybrid_search.py:PersianHybridSearch._rerank_scores_batched`
is shared by `rerank_search_results` (answer context) and `rerank` (related
questions). It partitions the unchanged scoring texts by original input position,
sends requests **sequentially**, and validates every batch before merging:

- List shape and exact response count; dict items; complete unique integer,
  nonboolean, in-range local indexes.
- Numeric, nonboolean, finite scores, including rejection of nonrepresentable
  huge integers. Malformed JSON and incomplete responses fail the operation.
- Local index → original global position via `offset + index`, never by text.
  Repeated scoring texts keep distinct candidate/content associations.
- No per-batch top-k, thresholds, score rescaling, epsilon policy or rounding
  changes. All candidates are scored before one global sort/selection.

Answer context retains normalized query, `build_faq_rerank_text` question/category/
subcategory scoring and `raw_scores=False`. Full chunks and metadata survive.
Global ordering is score descending, original RRF rank, string chunk ID; final
top-k and global reranker ranks retain their previous semantics.

Related questions retain normalized query and question-only normalization;
`raw_scores` stays **omitted**, preserving server-default behavior. A stable
descending-score merge retains legacy TEI response encounter order for exact
ties, followed by the unchanged threshold and five-result cap. Within a batch,
tie order comes from TEI; across batches, sequential original batch order applies.
The old path had no independent client tie key and relied on server response order.
This policy preserves single-request behavior; related exact-tie order can depend
on partition boundaries. It does not merge local rank positions as global scores.

On HTTP pool/read/connect errors, existing ServiceTimeoutError/
ServiceUnavailableError translations are kept; invalid protocol results use
ServiceProtocolError. Any intermediate failure stops subsequent batches and
returns no partial successful ranking. Cancellation propagates, including an
external deadline's cancellation. No retries or parallel batch execution added.
The active counter is held once per logical rerank and released in `finally`;
pool-timeout accounting stays balanced.

Observers receive **one logical rerank result**: completed, ERROR or CANCELLED.
Existing content/evidence payload shapes are retained. Added metadata contains
only client/server limits, attempted/completed batch counts, request sizes,
per-request durations and capability-GET count/duration. A failed operation has
no successful partial output. Existing trace spans accumulate sequential request
times; metadata distinguishes HTTP work from total logical operation duration.

## Configuration and target limits

One new permanent key: **`TEI_RERANK_MAX_CLIENT_BATCH_SIZE`**, positive integer,
default and initial value **50**, units **texts per HTTP rerank request**.
It is independent of embedding settings and never changes TEI server flags.
Loader/default/validation: `utils/performance_config.py`; environment validator
manifest: `scripts/validate_environment.py:_specs`.

`_rerank_server_limit` reads target `/info` on the first nonempty operation,
validates `max_client_batch_size` and caches the successful limit per target URL
for that search client's lifetime. Concurrent lookups are coalesced with an async
lock. Client settings above the target's limit fail **before sending texts**;
unavailable/malformed capabilities fail closed with existing translated errors.
There is no hardcoded universal 64 ceiling. Tests include target limits 20/64/200.
Recreate clients after server-limit changes; cached values are not live monitoring.
Production gateway access to reranker `/info` is a release prerequisite; no
production target was probed or infrastructure changed here.

Confirmed `.env` loading uses the existing explicit project `load_dotenv` path
with `override=False`. Effective normal lexical/dense/final/context depths remain
**50/50/50/10**, context reranking enabled, generation unchanged. The new setting
is **50**. Before/after configuration comparison checks that all previous
performance values and non-performance artifacts are unchanged.

User-confirmed development/staging capability reads were repeated before every
live phase and matched frozen values:

| Serving fact | Observed value |
|---|---|
| TEI reranker version/model identity | 1.9.3; `/app/models/BAAI--bge-reranker-v2-m3` |
| TEI client request limit | 64 texts |
| Reranker input limit / automatic truncation | 8,192 / disabled |
| TEI max batch tokens / requests | 32,768 / 32 |
| vLLM served ID / context | `/app/model` / 8,192 |

These values are current read-only runtime evidence, not historical defaults or
immutable weight/tokenizer revision verification. No live rerank request exceeded50.
Token-size rejection is still server-enforced; count batching does not remove
per-input limits, and no chunk/prompt was silently truncated for tests.

## Frozen comparison evidence

BEFORE measurements completed **before editing reranking/configuration/env files**.
Inputs, source snapshot, scores, ordering, selected IDs and answers are retained
in `/tmp/ragbot-p3-batching-20261013`, outside Git; directory0700/files0600.
No customer conversations, chat endpoints, KB writes, schema changes or vector
rebuilds were used. Operational output is allowlisted metadata only.

- P1/P2 frozen input identity:
  `9926d2dc6499c99ee14ccfe56306dbfef4b9cda4b262cff634dab999f3a8335f`.
  Five cases: three synthetic multipart/paraphrase questions with predetermined
  duration/cutoff/late-start conditions and two existing short FAQ-title queries
  (expected IDs2/3). Complete source/rank lists were reused, not merely signatures.
- Expanded frozen input identity:
  `c736c12d972a900cc02fa70e0f302b0c4528a535590dd3856f22124a63663242`.
  A read-only repeatable-read PG snapshot stores full chunks privately. BEFORE
  captured actual lexical/dense lists and final150/300 ordering for each FAQ
  query. AFTER performs actual embedding/Qdrant retrieval against that frozen
  corpus, verifies identical IDs/order, then reranks all results.
- Configuration identity BEFORE:
  `e976a7fa3768cea327734864b3b81cc842ad9f65dbdd56049f5c346a40e7f333`;
  AFTER:
  `c8af233fbe4b854dd5beedd18a3b2efeee5278a0a3f566c02db3681798ea2d65`.
  The difference is the new reranker setting/loader; other values and prompt,
  alias, reranker-text parser and generation artifacts are unchanged.
- Bracketed KB signatures: **1,526 chunks / 1,526 points**, cross-store consistency
  and FULL_MATCH true. PG aggregate:
  `948cae670aaec5faa350d977a0f381d6410a9b48d7853cdfd18bff7c76310750`.
  Fingerprints detect drift; the private snapshot supplies actual source content.

## Normal50 parity and bounded quality

Five cases, two answer-context repetitions and one related-question operation
each, at client concurrency **1**:

| Check | BEFORE | AFTER |
|---|---:|---:|
| Rerank POSTs, all50 texts | 15 | 15 |
| Answer-context / related logical operations | 10 / 5 | 10 / 5 |
| Native capability GETs | 0 | 5 |
| Expected relevant entries selected, first context repetition | 8/8 | 8/8 |
| Synthetic context facts | 9/9 | 9/9 |
| Actual synthetic generation checks | 9/9 | 9/9 |
| Forbidden synthetic calendar-day assertion | 0/3 | 0/3 |

All five cases match in retrieved IDs, scoring-text identities, exact POST
payload identities, selected context sets/order and related-question selection
order. Scores are not asserted equal: maximum observed normal BEFORE/AFTER
absolute score drift across the two paths was **0.00118597**. No selection/fact
regression was observed. Model checks are narrow predetermined lexical fact and
condition checks; no comprehensive banking or natural-query error rate claimed.

The related50 operations are controlled component scaling comparisons; the
production graph normally supplies three related-question titles. A supplemental
alternating P2-checkpoint/current comparison used **three question-only** titles
for one synthetic and two KB cases, three repetitions/side:18 POSTs of3 texts,
exact payload/selection parity throughout. Synthetic retained fact-time/fact-cutoff;
KB1 selected `[2,138,874]`, KB2 `[7,3,4]`. This executes extracted P2 code against
current code on identical evidence, without normal chat/session writes.

The five capability GETs reflect five fresh diagnostic search engines; each is
cached across its second context call and related call. A real reused engine
normally probes once, not once per query. Initial GET latency is included in the
first AFTER logical call and separately counted.

## Cross-batch score comparability

Same50 query/text pairs for one synthetic case and one real FAQ-title case, both
paths. Each variant ran twice: single50,25/25,17/17/16,25/25 after rotation13,
and single50 with reversed input. Reordered responses are mapped back to original
items. Diagnostics use isolated client instances; no shared settings/env mutation.
Forty logical observations,72 rerank POSTs; all are sequential and permissible.

| Case/path | Max absolute drift | Full-order changes vs first observation (of9) | Selected-set changes | Relevant entries retained |
|---|---:|---:|---:|---:|
| Synthetic / context | 0.00089101 | 9 | 0 | 2/2 throughout |
| Synthetic / related | 0.00076520 | 9 | 0 | 2/2 throughout |
| KB1 / context | 0.00029188 | 1 | 0 | 1/1 throughout |
| KB1 / related | 0.00049236 | 8 | 0 | 1/1 throughout |

All synthetic selections retain three required facts. Order changes include
irrelevant exact/near ties; they are reported, not hidden by altered rounding,
thresholds, score modes or epsilon sorting. The synthetic context cutoff is an
exact tie (gap0), resolved by existing RRF/ID policy; its measured cutoff-item
drift is0. KB1 context's baseline rank10–11 gap is **0.0001059244**, with maximum
near-cutoff-item drift **0.0000119997**. Related threshold remains0.1; nearest
baseline score margin is **0.099974928407** synthetic and **0.0301748** KB1,
with near-threshold drift **0.000000195103** and **0.00044165**, respectively.

Measured scales and useful selections are comparable on this small sample.
There is no evidence here of per-request score renormalization changing useful
selection. This is broader evidence than index validity alone, but does not prove
exact equality, universal partition invariance or comparability for every KB
query. Related exact-tie encounter order remains boundary-dependent by design.
Scores are not calibrated probabilities.

## Expanded staging and downstream checks

Two actual FAQ queries ×150/300, each with two context operations and one related
operation: **54 rerank POSTs**, all50 texts. Every operation accounts for all
candidate positions, globally merges scores and preserves selected source content
and metadata. Actual retrieval ordering matches the frozen BEFORE lists.

| Query/depth | Context request sizes per operation | Selected context IDs (both repetitions) | Relevant selected |
|---|---|---|---:|
| KB1/150 | 50,50,50 | 2,138,874,11,882,809,905,23,1437,906 | 1/1 |
| KB1/300 | 50 ×6 | 2,138,874,11,882,809,905,23,1437,906 | 1/1 |
| KB2/150 | 50,50,50 | 3,7,4,25,159,156,16,24,6,21 | 1/1 |
| KB2/300 | 50 ×6 | 3,7,4,25,159,156,16,24,6,21 | 1/1 |

Related150/300 operations also use three/six requests respectively, then apply
the unchanged global threshold/cap. Selected IDs: KB1 `[2,138,874]`; KB2
`[7,3,4,156,25]` at both depths. Real banking answer quality was not scored.

A separate **synthetic** retrieval fixture places complementary fact entries at
lexical positions80/130 among300 entries. Its first-stage scores are controlled;
reranking and generation use actual staging models. At150 and300, paired client
sizes50/25 select the same ten contexts, retain2/2 reference entries and3/3 facts,
and all four answers pass3/3 checks (**12/12 total**) with no forbidden assertion.
Request sizes:150 →3×50 or6×25;300 →6×50 or12×25.

Generation receives only ten selected **full** chunks, never150/300 entries.
The actual production messages/chat template were checked with served vLLM
`/tokenize`: **2,522 prompt tokens +500 reserved output**, below verified8,192.
No prompt/source truncation or prompt/generation change. Synthetic answers are
private; no banking factual-answer completeness claim follows from these tests.

## Timing and investigated variation

All live experiments use client concurrency1 and sequential requests; no stress
test or server concurrency tuning. Shared-service external workload/GPU headroom
was not controlled or profiled. HTTP durations differ from logical times, which
include formatting/validation/global merging and initial capability work.

| Normal measurement | BEFORE | AFTER |
|---|---:|---:|
| Context logical median/p95 (n10) ms | 47.180 /56.351 | 47.370 /60.857 |
| First context call median (n5) ms | 51.811 | 47.526, includes capability GET |
| Warm context call median (n5) ms | 45.479 | 46.444 |
| Related logical median (n5) ms | 57.268 | 55.105 |
| Rerank HTTP POST median/p95 (n15) ms | 32.445 /37.140 | 30.666 /37.215 |
| Actual synthetic generation median (n3) ms | 2,521.886 | 2,472.367 |
| Generation range ms | 2,478.359–2,779.992 | 2,261.210–2,734.310 |

The supplemental alternating normal related3 component check (n9/side) measured
logical median/p95 **23.275/24.431 ms** P2 and **18.837/25.470 ms** P3; three
initial P3 capability GETs are included. It verifies parity at normal graph
candidate count; the small sample does not establish a latency improvement.

No claim of a capacity gain or causal service-latency improvement from these
small paired samples. Expanded operation timings measure actual150/300 work:

| Query/depth | Context logical ms, two repetitions | Related logical ms |
|---|---|---:|
| KB1/150 | 113.191,106.510 | 82.352 |
| KB1/300 | 201.941,218.914 | 210.876 |
| KB2/150 | 131.953,133.781 | 111.303 |
| KB2/300 | 271.374,248.676 | 213.814 |

Context medians across four measurements/depth: **122.572 ms** at150 and
**233.795 ms** at300. Per-POST median/p95 across both paths: **27.193/32.828 ms**
(n18) at150; **25.102/38.988 ms** (n36) at300. There is no successful oversized
P2 live rerank to compare: its failure was reproduced only with a mocked64 server.

Actual retrieval BEFORE/AFTER ms: KB1/150 **2,146.396/3,798.495**;
KB1/300 **2,105.298/3,108.292**; KB2/150 **2,043.308/3,703.516**;
KB2/300 **2,091.534/3,918.397**. This increase was investigated rather than
attributed to batching. Eight retrieval methods are AST-identical to P2; a
separate read-only trace rerun returned **2,189.569 ms** (150) and **2,072.819 ms**
(300), near BEFORE. Embedding spans were18.116/14.035 ms and Qdrant17.962/18.506;
roughly2,153.413/2,040.200 ms remained outside those service spans, including NLP
and blocking work. Exact cause of run-to-run variation is not established; no
retrieval tuning, configuration compensation or sustained regression claim.

Expanded synthetic50→25 comparisons (one observation per cell, no causal
performance claim): rerank150 **123.786→126.923 ms**;300 **265.823→257.719 ms**.
Generation150 **3,125.110→2,551.631 ms**;300 **2,522.448→2,599.545 ms**. These
are identical selected contexts and unchanged generation settings; small counts
do not establish a preferred batch size. Default remains50.

## Executed commands and results

All commands used Python3.12.12 at `/root/miniconda3/envs/faq/bin/python`, after:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Live commands ran sequentially on established staging resources using approved
sandbox elevation; no production traffic or persisted test conversations.

| Exact command | Exit/result |
|---|---|
| `python scripts/reranker_p3_compare.py before --directory /tmp/ragbot-p3-batching-20261013 --confirmed-staging` | 0; BEFORE normal measurements, current capabilities and frozen actual150/300 inputs captured before edits. |
| `python scripts/knowledge_audit_p0_baseline.py` BEFORE | 0; synthetic64 server rejects a single150-text request, RRF fixed and BM25 configurable. |
| `python scripts/reranker_p3_compare.py after --directory /tmp/ragbot-p3-batching-20261013 --confirmed-staging` | 0; exact normal payload/selection parity and9/9 answer checks. |
| `python scripts/reranker_p3_compare.py comparability --directory /tmp/ragbot-p3-batching-20261013 --confirmed-staging` | 0;40 observations with full per-item scores; results above. Initial generic stdout summary did not aggregate nested observations; CLI summary was subsequently corrected. Private measurements were complete and analyzed directly. |
| `python scripts/reranker_p3_compare.py expanded --directory /tmp/ragbot-p3-batching-20261013 --confirmed-staging` | 0; actual150/300 retrieval parity,54 bounded POSTs and bracketed signature FULL_MATCH. |
| `python scripts/reranker_p3_compare.py synthetic --directory /tmp/ragbot-p3-batching-20261013 --confirmed-staging` | 0; four expanded model checks,12/12 required facts, served-tokenizer budget verification. |
| `python scripts/reranker_p3_compare.py retrieval-timing --directory /tmp/ragbot-p3-batching-20261013 --confirmed-staging` | 0; two bounded retrieval observations, unchanged-method AST check and span measurements. |
| `python scripts/reranker_p3_compare.py related-normal --directory /tmp/ragbot-p3-batching-20261013 --confirmed-staging` | 0; alternating P2/current three-title component check,18 POSTs of3, exact payload/selection parity. |
| `python -m pytest tests/test_reranker_batching.py tests/test_answer_context_reranking.py tests/test_retrieval_depths.py tests/test_rrf_scoring.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_retrieval_normalization_consistency.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_rag_answer_prompt_roles.py tests/test_kb_audit_tools.py tests/test_revision_aware_cache.py -q` | 0; **144 passed,167 subtests passed**,14.08 s; SWIG deprecations and unavailable NVML warning. No frontend suites. |
| `python scripts/knowledge_audit_p0_baseline.py` AFTER | 0; RRF resolved, BM25 configurable; safely_batched true,150 →50/50/50, unbatched outstanding false; zero network/env loads. |
| `python -m pytest tests/test_reranker_batching.py -q` final | 0; **17 passed,85 subtests passed**,3.10 s; additionally checks full content/metadata association for every observer ranking. |
| `python -m py_compile scripts/reranker_p3_compare.py scripts/knowledge_audit_p0_baseline.py tests/test_reranker_batching.py utils/persian_hybrid_search.py utils/performance_config.py` | 0. |
| `git diff --check` | 0. |

Initial focused command
`python -m pytest tests/test_reranker_batching.py tests/test_answer_context_reranking.py tests/test_retrieval_normalization_consistency.py -q`
exited1 with6 failed subtests,29 passed/79 passed subtests: httpx's mock JSON
encoder refused NaN/Infinity before exercising client validation. Raw response
bytes fixed the fixture; rerun exited0 with29 passed/85 subtests in5.55 s.
Final broader suite above includes subsequent cancellation/capability/deadline
and duplicate-text cases. Do not sum overlapping runs as distinct tests.

## Protocol, isolation and environment evidence

Tests cover0/1/49/50/51/64/65/150/300 inputs and client limits50/64; final short
batches, shuffled local indexes, global top-k beyond batch boundaries, exact
ties, related thresholds, content/metadata and duplicate scoring texts. With50,
150 →50/50/50 and300 →six50; with64,65 →64/1 and correct global ordering.
Malformed shapes/JSON, missing/duplicate/boolean/out-of-range indexes, missing/
boolean/nonfinite scores, intermediate failures, timeout/cancellation and no
partial-success paths pass. One coherent observer result has accurate counts.

Concurrent independent150/65 operations on one engine remain sequential per
operation and return their correct global top10, with one coalesced capability
GET and final active count0. Pool-timeout, capability-failure and cancellation
paths balance counters; external deadline cancellation stops remaining batches.

| File updated | Key | Handling |
|---|---|---|
| `env.example` | `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` | Tracked main template |
| `Production_ENV` | `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` | Tracked main template |
| `.env.example.generated` | `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` | Tracked source-authored template |
| `.env` | `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` | Private/local only |
| `.env_latest` | `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` | Existing private main runtime/local only |

Each has exactly one new key. Removing each insertion reproduces original bytes;
existing/custom values and unrelated entries were preserved. `.env.server_git`
is absent; the user-deleted staging template was not recreated. Separate
evaluation-system envs configure HTTP consumers, not this retrieval client, and
were unchanged. No automatic generated-template writer was found; its validator
manifest and loader/template tests were updated to guard against drift. No other
new permanent setting, private env, dataset, source snapshot or response committed.

## Remaining release boundaries

No required bounded P3 staging check remains blocked. Release still requires
representative human-reviewed retrieval/banking answer quality, agreed regression
tolerances, load/concurrency/external50-second deadline validation, GPU headroom
and production `/info` gateway compatibility. Exact serving weight/tokenizer
revisions and universal cross-batch score invariance remain unverified. Related
tie dependence and observed numerical drift must stay visible in later reviews.
Cached target limits need client recreation when serving limits change. Large
or over-token inputs fail rather than silently dropping/truncating evidence.

P4 taxonomy preservation remains outstanding. No P4 work, audit/dashboard
implementation, push, merge, deployment, service restart or server tuning occurred.
