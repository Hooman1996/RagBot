# P1 — reciprocal rank fusion correction

Status: **READY_FOR_REVIEW_WITH_BLOCKED_CHECKS**. Recorded 2026-10-13,
Asia/Tehran. P1 only; no P2 work, audit feature, deployment, push, merge or
service restart. Release-validation limitations are listed below.

## Repository and change boundary

Actual checkout `/root/projects/faq`; starting HEAD verified as
`0663fa07acaf2ba9433789e8655643b9e7d6b163`. Created `p1/rrf-correction`
at that checkpoint in the existing worktree. No reset, rebase, stash or merge.
Existing `.gitignore` edits, deleted `.env.recommended.rtx5880-staging` and
untracked user files are preserved and excluded from this stage's commit.

Files in scope:

- `utils/persian_hybrid_search.py`: one formula hunk in `PersianHybridSearch.search`.
- `tests/rrf_fixtures.py`, `tests/test_rrf_scoring.py`: synthetic evidence and
  independent expected relevance/math tests against the actual search method.
- `scripts/rrf_p1_compare.py`: P1-only freeze/replay/downstream/paired-timing
  diagnostic; no application imports/startup, jobs, tables or audit feature.
- `scripts/knowledge_audit_p0_baseline.py`: reports the RRF issue resolved and
  the fixed BM25 cap/unbatched reranker still outstanding; its synthetic server
  boundary now uses the verified 64-item limit rather than historical 50.
- `IMPLEMENTATION_PLAN.md`: links this report and updates stage authorization
  wording; main-dashboard, explainability, all-query processing, early pilot and
  complete-CSV invariants and stage sequence are preserved.
- This report.

The resulting scoped commit is returned in the final report; use `git rev-parse
HEAD` to identify it. Embedding its own hash here would be circular.

## Formula and preserved behavior

Before, missing ranks were replaced with 61:

```text
old(cid) = 1 / (60 + sparse_rank_or_61) + 1 / (60 + dense_rank_or_61)
```

After:

```text
new(cid) = (1 / (60 + sparse_rank) if present else 0)
         + (1 / (60 + dense_rank) if present else 0)
```

Implementation uses `.get(cid)` and tests `rank is not None` for each branch.
No new utility/refactor/dependency is needed. The production source diff adds
six/removes three lines, preserving original mixed line endings outside the hunk.
RRF k=60, one-based ranks, candidate union/deduplication, output depth, six-decimal
rounding, original_rrf_rank numbering and sort keys remain unchanged:
hybrid descending, semantic descending, BM25 descending, then string ID ascending.
Normalization, datasource filtering, full chunk content, title/taxonomy rerank
text, generation settings and prompts are unchanged. An absent branch no longer
adds `1/121`, approximately `0.00826446281`.

| Controlled case | Before public score | After public score / unrounded reference |
|---|---:|---|
| Rank 1, sparse only | 0.024658 | 0.016393 / 1/61 |
| Rank 1, dense only | 0.024658 | 0.016393 / 1/61 |
| Rank 1 in both | 0.032787 | 0.032787 / 2/61 |
| Rank 100, dense only | 0.014514 | 0.006250 / 1/160 |
| Sparse rank 3, dense rank 2 | 0.032002 | 0.032002 / (1/63 + 1/62) |

Tests use at most half a six-decimal rounding unit against unrounded references.
Rank-100 input is injected at the fusion boundary; it does not claim that the
current 50-candidate production dense/BM25 settings can return rank 100.

## Frozen input and configuration identities

All comparison inputs were frozen **before changing the production formula**.
Private directory `/tmp/ragbot-p1-rrf-20261013` has mode **0700**; each file is
created exclusively with mode **0600**. Nothing from that directory is committed.
It contains fixed branch ID/score lists (rank is the one-based list ordinal;
nonpositive sparse rows are omitted by production search), full candidate chunk
content and datasource mapping, expected entries, synthetic reference facts,
capability/configuration identity, before/after measurements and private answers.
It contains no customer conversations or copied model prompts.

- Input identity (canonical JSON excluding its own identity field):
  `9926d2dc6499c99ee14ccfe56306dbfef4b9cda4b262cff634dab999f3a8335f`.
- Frozen `inputs.json` byte SHA-256:
  `424b148038666bd9964c97b178d7ce452519539e7bf4eebb9c9c9e2008526dce`.
- Effective configuration/artifact identity:
  `551d8d885243e451514b8a195abc20b9fb5832968e68b924db5489c7344d5cb9`.
  Includes performance settings and hashes of production prompt/config source,
  aliases, performance loader, rerank formatter and RAG generation code; no prompt
  text or secret values are serialized. Both phases enforce identity equality.
- Before retrieval source SHA-256:
  `f77e018046c4e7a14a37b5c7a57818648f01958c7bbb9880a32ec0ef9f3df123`.
- After retrieval source SHA-256:
  `c708ff9d18b0024e62d321e051eca01fe46019d7e1f55cc41944a8ac377f4567`.
- Before results canonical fingerprint:
  `6876246d428fce6066a2fbf615a84bc8d9c478a3237010aa7bf0a897fa538d48`.
- After results canonical fingerprint:
  `bfcb595fdbd5b1b32a895ddad32fe211011003ed7e49811514eb85b0dcec6254`.

`scripts.kb_signature.create_signature` ran before and after freeze. Both returned
**1,526 PG chunks / 1,526 Qdrant points**, cross-store consistent, with comparator
**FULL_MATCH**. PostgreSQL content/metadata aggregate stayed
`948cae670aaec5faa350d977a0f381d6410a9b48d7853cdfd18bff7c76310750`,
matching P0.1. PG content capture used a read-only repeatable-read transaction;
Qdrant operations were read-only. A signature is not an immutable snapshot or a
cross-store atomicity guarantee: the actual branch lists and candidate content
are separately frozen and replayed, with no PG/Qdrant/embedding calls in either
fusion comparison phase. Signatures bracketed the live capture and detected no
drift; the report does not claim global database immutability.

### Effective settings verified before and after

Python `/root/miniconda3/envs/faq/bin/python`, **3.12.12**. The diagnostic explicitly
loads `/root/projects/faq/.env` with dotenv `override=False` before settings imports,
including when invoked from another worktree/CWD. No private env file is copied.

| Non-secret setting / capability | Observed value |
|---|---|
| Retrieval / dense depth | `RAG_RETRIEVAL_TOP_K=50`, `RAG_SEMANTIC_CANDIDATE_LIMIT=50` |
| Context rerank | enabled, top_k=10 |
| Query aliases | enabled |
| FAQ generation | max new tokens 500, temperature 0, top_p 1, seed 42 |
| TEI embedding | 1.9.3, Jina v5 small retrieval; client batch 64, input length 32,768, auto_truncate false |
| TEI reranker | 1.9.3, BAAI bge-reranker-v2-m3; client batch 64, input length 8,192, auto_truncate false |
| Both TEI services | max batch tokens 32,768, max batch requests 32 |
| vLLM model metadata | served `/app/model`, max_model_len 8,192 |

HTTP `/info` and `/models` checks were repeated before each downstream phase and
matched the frozen capability identity. No historical 50-item TEI serving limit
or automatic truncation was substituted. The P0 diagnostic's 10-retrieval default
fixture is explicitly separate from the effective 50-retrieval live comparison.

## Fixture provenance and predetermined references

**Mathematical/offline tests are synthetic.** Cover sparse-only, dense-only,
overlap, different ranks, rank 100, empty branches/corpus, deduplication, dense
secondary tie score, exact string-ID ties, top-k/rank tracking and full chunk
preservation. They assert the desired contract, not defective historical output.

**Three synthetic information cases** share a frozen 98-entry candidate union:
50 sparse + 50 dense, two overlaps. Relevant entries `fact-time` and `fact-cutoff`
have ranks 45/45 and 46/46. Their fictional banking answers specify duration,
working-day interpretation, cutoff and delayed-start condition. Queries are
paraphrases/multipart information needs. Relevance and required fact labels were
defined in `tests/rrf_fixtures.py` before baseline execution; they do not derive
from RRF scores. No facts describe an actual bank/product.

**Two real KB cases**, `kb-1`/`kb-2`, use existing FAQ titles as controlled queries,
with expected stable chunk IDs **2** and **3**. Selection was deterministic from
short existing FAQ entries ordered by source ID, independent of feedback/outcome
flags. Positive sparse/dense counts are 50/50; unions are 64/65. Both references
are rank 1 in both branches. Queries/chunks remain private. This is a narrow
self-title retrieval sample, not representative natural-query evaluation.
Initial live capture times were **2,164.801 / 2,083.656 ms**; these include actual
BM25/embedding/Qdrant capture and are not paired before/after performance data.
History rewrite and classification are outside this direct component comparison.

## Paired correctness, relevance and quality results

| Case | Relevant in retrieved pool before → after | Relevant in first selected context before → after | Synthetic required facts in context before → after |
|---|---:|---:|---:|
| synthetic-info-1 | 0/2 → 2/2 | 0/2 → 2/2 | 0/3 → 3/3 |
| synthetic-info-2 | 0/2 → 2/2 | 0/2 → 2/2 | 0/3 → 3/3 |
| synthetic-info-3 | 0/2 → 2/2 | 0/2 → 2/2 | 0/3 → 3/3 |
| kb-1 | 1/1 → 1/1 | 1/1 → 1/1 | Not evaluated |
| kb-2 | 1/1 → 1/1 | 1/1 → 1/1 | Not evaluated |

Aggregate relevant entry appearances **2/8 → 8/8** in both retrieval and selected
context. Treat synthetic and KB subsets separately; this is not a natural-query
recall estimate. All selected contexts retained the full frozen chunks.

Actual vLLM FAQ generation ran once per synthetic case per phase, using unchanged
`RAGSystem.answer`, context formatter, production prompts and generation parameters.
Nine predetermined lexical checks (duration in working days, cutoff marker and
next-working-day start across three answers) improved **0/9 → 9/9**. The configured
affirmative-calendar-day forbidden-claim regex fired **0 → 0**. This is actual
model output evaluated against synthetic references, not a mocked answer or a
candidate-count check. Before outputs lacked the required evidence; short
refusal/incompleteness is appropriate there and is not characterized as model
misbehavior.

These lexical checks are deliberately narrow: they do not prove complete semantic
condition handling, absence of every unsupported claim, or expert-reviewed
banking correctness. No actual model answer was generated/scored for the two
private KB questions. No statistical error rate or deployment quality gate is
claimed. Private responses are retained only for authorized review, never copied
into tracked reports/logs.

### Ranking changes and drift investigation

- Synthetic `fact-time`/`fact-cutoff` enter ranks **1/2** and the selected context.
  Their own two-branch scores do not change (2/105 and 2/106); the correction
  removes the false boosts from singleton distractors. `dense-25`/`sparse-25`
  leave each 50-entry pool. All 50 rank positions shift, as intended.
- kb-1 retains the same candidate set but 23 positions change. kb-2 has 24 position
  changes; IDs 10/427 enter and 2/313 leave its candidate pool. Both expected
  reference entries remain rank 1, and both real cases' selected context sets
  and order remain unchanged.
- Reranking repeats used exactly the same candidate order/content within each
  phase. One **before** synthetic repeat reordered the same selected set at
  equal/near-zero scores; there was no set change. All after repeat orders matched.
  Across repeats, maximum shared selected score drift was **0.00118597**.
  Both before KB margins (approximately 0.0000575 and 0.0018112 minimum adjacent
  selected-score gaps) and score drift were recorded privately. Cross-phase
  numerical score changes are not attributed exclusively to RRF: input order/
  pool and observed serving numerical drift both matter.
- No unexpected loss of a labeled relevant entry/context occurred. This does not
  label every unlabeled gained/lost FAQ relevant or irrelevant.

## Timing and request accounting

Each phase: five cases × 200 deterministic fusion replays (1,000 total), then
two live reranker calls per case (**10 calls**, each **50 texts**), and **3 actual
generation calls**. No retries, batching change or branch recapture. All fusion
replays had identical ordered results/scores within a version. Live inference
was sequential; no unattended stress or concurrency test.

Initial separated-phase fusion medians varied with execution conditions. One
KB case increased from 0.232 to 0.297 ms while others decreased or stayed close.
To investigate, a second **offline-only** diagnostic loaded the checkpoint's
unchanged search method and alternated before/current execution on the same
frozen inputs, with 50 warmups and **1,000 measured iterations per case/version**:

| Case | Paired fusion-replay median before / after (ms) | Paired p95 before / after (ms) |
|---|---:|---:|
| synthetic-info-1 | 0.202436 / 0.199411 | 0.218664 / 0.213367 |
| synthetic-info-2 | 0.201755 / 0.198565 | 0.215641 / 0.211089 |
| synthetic-info-3 | 0.202514 / 0.199848 | 0.239811 / 0.228144 |
| kb-1 | 0.190747 / 0.190550 | 0.202107 / 0.201374 |
| kb-2 | 0.193841 / 0.193069 | 0.207747 / 0.205953 |

These are search-fusion replay timings with stubbed upstream methods, including
object construction/sorting; **not pure arithmetic timings or actual retrieval
service latency**. The alternating check found no persistent local slowdown;
small differences do not establish a throughput benefit.

| Live measurement | Before | After |
|---|---:|---:|
| Reranker calls / sizes | 10 / [50] each | 10 / [50] each |
| Reranker median (n=10) | 38.421 ms | 40.115 ms |
| Reranker observed range | 33.066–66.350 ms | 33.955–58.086 ms |
| Generation calls | 3 | 3 |
| Generation median (n=3) | 987.546 ms | 2,358.131 ms |
| Generation observed range | 986.180–1,367.956 ms | 2,290.303–2,828.987 ms |
| Answer character counts | 71 / 71 / 71 | 232 / 203 / 217 |

After outputs were substantially longer and contained the requested information;
this supports interpreting increased generation work separately from fusion
cost, but does not prove a causal latency model. These runs have no fixed-load
control or production concurrency coverage; do not claim a latency/throughput
improvement or a production deadline guarantee. No thresholds, prompts, depths,
model flags or temperature were adjusted to offset timing differences.

## Exact executed commands and outcomes

All Python commands ran from the project after:

```sh
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

| Command | Exit and outcome |
|---|---|
| `python scripts/rrf_p1_compare.py freeze --directory /tmp/ragbot-p1-rrf-20261013 --confirmed-staging` | **0**; five frozen cases, consistent bracketed KB signatures and current capability/configuration identity. |
| `python -m pytest tests/test_rrf_scoring.py -q` before correction | **1**; reported **7 failed, 9 passed**, including three failed controlled-case subtests. Correct desired assertions reproduced the defect. |
| `python scripts/rrf_p1_compare.py before --directory /tmp/ragbot-p1-rrf-20261013 --confirmed-staging` | **0**; before measurements and private answers saved before formula edit. |
| `python -m pytest tests/test_rrf_scoring.py -q` after correction | **0**; **13 passed, 3 subtests passed**, 2.54 s. |
| `python scripts/rrf_p1_compare.py after --directory /tmp/ragbot-p1-rrf-20261013 --confirmed-staging` | **0**; identical frozen/configuration identities, after measurements and private answers. |
| `python -m pytest tests/test_rrf_scoring.py tests/test_answer_context_reranking.py tests/test_retrieval_normalization_consistency.py tests/test_performance_config.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_rag_answer_prompt_roles.py tests/test_kb_audit_tools.py -q` | **0**; **79 passed, 30 subtests passed**, 10.59 s; two SWIG deprecation warnings. Covers applicable reranking, normalization, configuration, answering, routing, canonicalization, prompt-role and signature regressions. Counts overlap the focused test command; do not add them as independent tests. |
| `python scripts/knowledge_audit_p0_baseline.py` | **0**; missing_branch_defect_resolved=true, BM25 fixed_50_cap_still_outstanding=true, one_request_batching_still_outstanding=true; fixture-local time 0.470 ms. |
| `python scripts/rrf_p1_compare.py timing --directory /tmp/ragbot-p1-rrf-20261013` | **0**; alternating checkpoint/current offline timings, zero network calls. |
| `python -m py_compile scripts/rrf_p1_compare.py tests/rrf_fixtures.py tests/test_rrf_scoring.py scripts/knowledge_audit_p0_baseline.py` | **0**. |
| `git diff --check` | **0**. |
| `git diff --cached --check` | **0**; scoped staged files have no whitespace errors. |

Live diagnostics and applicable regression execution used sandbox escalation
because P0.1 established local socket restrictions. The user-confirmed
development/staging targets and authorization persist from P0.1; no production
target was contacted. No unrelated frontend suite was rerun.

## Remaining boundaries and release limitations

Environment variables introduced: **none**. No env loaders/defaults/settings
changed and no env template/runtime file edited or committed. `.gitignore` stays
untouched by P1; only this authorized report is force-added if necessary.

- **P2 remains outstanding:** fixed BM25 50-item cap and coupled/global candidate
  depth controls. Rank-100 fusion testing is not a P2 implementation.
- **P3 remains outstanding:** one-request reranking. Current production 50 fits
  the verified 64 client limit; 150 audit candidates still require later batching.
- **P4 remains outstanding:** structured taxonomy preservation and historical
  missing-taxonomy handling. No KB mutation was performed.
- The real KB sample is only two title queries; representative human-reviewed
  retrieval and banking answer-quality acceptance remains unverified. Synthetic
  lexical checks do not establish natural-query error rates or complete semantics.
- No production load/concurrency/deadline validation, GPU headroom observation,
  immutable weight revision or exact serving tokenizer-object verification was
  added. P0.1 GPU telemetry limitations remain. Reranker near-tie numerical drift
  is observed and needs consideration in later batching/quality work.

The isolated correction and executable tests are complete for review. This
report does not approve deployment, the production acceptance gate, or P2.
