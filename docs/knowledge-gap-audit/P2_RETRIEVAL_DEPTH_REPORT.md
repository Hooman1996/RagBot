# P2 — configurable retrieval candidate depths

Status: **READY_FOR_REVIEW_WITH_BLOCKED_CHECKS**. P2 implementation and scoped
checks are complete. Expanded live context/answer validation awaits P3 batching;
this report does not authorize deployment or another stage.

## Repository and scope

Project `/root/projects/faq`; branch `p2/retrieval-depths`, based on verified P1
checkpoint `c8338050aa548cfc3f48f0927d4bcd270c2e608f`. No worktree isolation was
needed: initial unrelated changes were disjoint. Preserved `.gitignore` edits,
the deletion of `.env.recommended.rtx5880-staging`, and existing untracked files.
Private `.env_latest` remains untracked with the authorized key insertion.

Read repository guidance, P0/P0.1 and P1 reports, implementation/UI/export
contracts, and debugging-strategies, python-testing-patterns and rag-implementation
skills. Python: **3.12.12**, `/root/miniconda3/envs/faq/bin/python`.
All Python commands below used:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

No prompts, generation settings, reranker text/batching, taxonomy, infrastructure,
routes, permissions or schemas changed. Main-dashboard, all-selected-query,
explainability and one-output-row-per-input CSV contracts remain intact. P3 and
the audit/dashboard feature have not started.

## Retrieval contract and implementation

| Setting | Meaning / units | Source default | Effective project configuration |
|---|---|---:|---:|
| `RAG_BM25_CANDIDATE_LIMIT` | BM25 score-sorted candidate slice, entries/query | 50 | 50 |
| `RAG_SEMANTIC_CANDIDATE_LIMIT` | Qdrant dense limit, entries/query | 50 | 50 |
| `RAG_RETRIEVAL_TOP_K` | Maximum distinct fused results, entries/query | 10 | 50 |
| `RAG_CONTEXT_RERANK_TOP_K` | Existing answer-context selection limit | 10 | 10 |

Context reranking remains enabled. Project configuration is explicitly loaded
through the existing `load_dotenv('/root/projects/faq/.env', override=False)` path
in the comparison helper; exported variables retain normal precedence. The P1
baseline identity matched before edits. Existing settings and values remained
unchanged; the only new permanent key defaults to 50.

`utils/performance_config.py:load_performance_settings` loads the new positive
integer. It retains context-count-versus-final-count validation and removes the
incorrect final-count-versus-dense-count restriction. All three depths must be
positive integers. There is **no theoretical final-count upper bound**: final is
a maximum over the eligible distinct combined pool, which naturally bounds the
returned count. Thus 150/50/150 and 100/100/150 are valid, and even final counts
beyond combined capacity simply yield fewer results. No padding or duplication.

`PersianHybridSearch.search` accepts keyword-only `bm25_candidate_limit` and
`semantic_candidate_limit`, alongside existing `top_k`. None selects configured
values; explicit booleans, strings, floats, zero and negative overrides raise
ValueError. `RAGSystem.retrieve` forwards these overrides without changing
production callers. Explicit zero final depth now rejects rather than silently
falling back to a default.

Effective depths are passed to `_score_bm25`, `_semantic_search`, and final
selection. BM25 nonpositive scores remain excluded after slicing. Corpus cache
keys remain document-scope/revision based, independent of request depths.
Requests never mutate shared settings or environment. Corrected RRF (K=60,
one-based present-branch contributions), deduplication, secondary tie ordering,
six-decimal public rounding, original RRF ranks, filters and full content remain
unchanged.

Request trace `retrieval_depths` and retrieval-stage metrics report effective
`bm25_candidate_limit`, `semantic_candidate_limit`, `retrieval_top_k`, and actual
`bm25_candidate_count`, `semantic_candidate_count`, `candidate_union_count`,
`returned_candidate_count`, including empty outcomes. New diagnostics contain
only counts/settings. The existing internal runtime configuration snapshot also
includes the lexical setting; no endpoint was added.

## Frozen inputs and provenance

The BEFORE baseline ran **before code/env edits**, reusing the actual frozen P1
first-stage lists and source contents. A signature alone was not used as a
snapshot. Complete branch ranks/scores, retrieved ordering/IDs, selected IDs,
private evidence and model responses are stored outside the repository in
`/tmp/ragbot-p2-default-20261013` (directory 0700; files 0600).

- Frozen input canonical SHA-256:
  `9926d2dc6499c99ee14ccfe56306dbfef4b9cda4b262cff634dab999f3a8335f`.
- Input-file byte SHA-256:
  `424b148038666bd9964c97b178d7ce452519539e7bf4eebb9c9c9e2008526dce`.
- P1 configuration identity:
  `551d8d885243e451514b8a195abc20b9fb5832968e68b924db5489c7344d5cb9`.
- P2 configuration identity:
  `e976a7fa3768cea327734864b3b81cc842ad9f65dbdd56049f5c346a40e7f333`.
  This intentionally differs because of the added setting/loader and retrieval
  forwarding code. The helper verifies equality of all previous performance
  values and unchanged prompt/model configuration, aliases and reranker parser.
- PG aggregate SHA-256 before/after:
  `948cae670aaec5faa350d977a0f381d6410a9b48d7853cdfd18bff7c76310750`.
  Both signatures: **1,526 chunks, 1,526 points**, cross-store consistency and
  signature FULL_MATCH true. This is a fingerprint; frozen inputs provide actual
  comparison evidence. No KB writes or customer conversations were used.
- Separate expanded synthetic input identity:
  `62b4a0b323be5d8b286daacda0f66da30eea4a8a21105d6ffb7dd086f6e2c86b`,
  archived in `/tmp/ragbot-p2-depths-20261013`, with the same restricted modes.

The default set contains three synthetic multipart/paraphrase cases with
predetermined duration, cutoff and late-start conditions, plus two existing
short FAQ-title retrieval cases (expected IDs 2 and 3). No customer queries.
Expanded fixtures have 300 frozen lexical scores and 300 dense scores, with two
independently labeled fictional source facts. Lexical/dense ranks are 120/50 and
50/120 for those entries. These are controlled mechanics/relevance fixtures,
not a labeled natural-query gap dataset.

## Paired default correctness and quality

All five cases have 50 positive lexical and 50 dense candidates, return 50, and
select 10 contexts. Candidate union sizes are 98/98/98/64/65. AFTER IDs, scores,
original ranks and full content match BEFORE exactly; 200 alternating checkpoint
and current replays per case were deterministic and equal.

| Evidence | BEFORE | AFTER |
|---|---:|---:|
| Expected relevant entries retrieved | 8/8 | 8/8 |
| Expected relevant entries selected | 8/8 | 8/8 |
| Synthetic required facts present in context | 9/9 | 9/9 |
| Actual model answers passing predetermined fact/condition checks | 9/9 | 9/9 |
| Forbidden synthetic calendar-day assertion detected | 0/3 answers | 0/3 answers |
| Reranker calls / request sizes | 10 / all 50 texts | 10 / all 50 texts |
| Actual generation calls | 3 | 3 |

All selected-context **sets** match. Four orders match; synthetic-info-3 swaps
two irrelevant entries: sparse-07 and sparse-20 were tied at 0.00003883111
BEFORE, while AFTER sparse-07 scored 0.000038528935. The relevant first two
entries remain fact-time/fact-cutoff. TEI scores differed on all five cases,
consistent with prior score drift. Identical first-stage evidence rules out a
depth change as the reason for this near-tie ordering effect. No observed fact
or selected-set regression; no compensating threshold/prompt/top-k changes.

Real KB cases check retrieval/context inclusion only. Their factual answers
were not generated or scored. Live answer checks use synthetic supplied facts
and narrow predefined regexes, not a comprehensive semantic-quality assessment
or measured error rate on naturally occurring unlabeled questions.

## Expanded retrieval and timings

Actual counts below use production lexical selection/fusion with frozen score
providers. Two labeled complementary facts are the reference. Increasing only
lexical depth retrieves lex-relevant; increasing only dense depth retrieves
dense-relevant; increasing only final depth exposes both singleton entries.

| Lexical / dense / final | Actual union | Returned | Reference facts | Median total ms | p95 total ms |
|---|---:|---:|---:|---:|---:|
| 50 / 50 / 50 | 100 | 50 | 0/2 | 0.250 | 0.272 |
| 150 / 50 / 50 | 199 | 50 | 1/2 | 0.342 | 0.365 |
| 50 / 150 / 50 | 199 | 50 | 1/2 | 0.340 | 0.360 |
| 50 / 50 / 150 | 100 | 100 | 2/2 | 0.359 | 0.379 |
| 150 / 50 / 150 | 199 | 150 | 2/2 | 0.567 | 0.598 |
| 100 / 100 / 150 | 200 | 150 | 2/2 | 0.567 | 0.710 |
| 150 / 150 / 150 | 298 | 150 | 2/2 | 0.665 | 0.744 |
| 300 / 300 / 300 | 598 | 300 | 2/2 | 1.323 | 1.418 |

Each row has 10 warmups + 200 measured stable repetitions, zero live reranker
or generation calls. Only the first three changes from 50/50/50 are single-depth
experiments; joint configurations establish combined correctness. These timings
exclude NLP, real BM25 score computation, PostgreSQL, embedding and Qdrant network
latency. Lexical timing measures sorting/slicing already frozen scores. Median
lexical-selection / frozen-dense-provider / fusion-and-overhead ms:

| Depths | Lexical | Dense provider | Fusion and overhead |
|---|---:|---:|---:|
| 50/50/50 | 0.044 | 0.012 | 0.194 |
| 150/50/50 | 0.044 | 0.013 | 0.283 |
| 50/150/50 | 0.045 | 0.021 | 0.274 |
| 50/50/150 | 0.044 | 0.012 | 0.302 |
| 150/50/150 | 0.045 | 0.014 | 0.507 |
| 100/100/150 | 0.045 | 0.019 | 0.503 |
| 150/150/150 | 0.045 | 0.024 | 0.595 |
| 300/300/300 | 0.046 | 0.040 | 1.235 |

Paired default timing alternates extracted **P1 checkpoint search and BM25
selection** with current methods, using identical corpus/score providers, 10
warmups and 200 measurements per side/case:

| Case | BEFORE median / p95 ms | AFTER median / p95 ms |
|---|---:|---:|
| synthetic-info-1 | 0.229 / 0.489 | 0.231 / 0.513 |
| synthetic-info-2 | 0.215 / 0.227 | 0.218 / 0.230 |
| synthetic-info-3 | 0.216 / 0.228 | 0.218 / 0.234 |
| kb-1 | 0.207 / 0.217 | 0.209 / 0.221 |
| kb-2 | 0.205 / 0.220 | 0.207 / 0.222 |

Observed median overhead is roughly 0.002–0.003 ms per replay. This is an offline
mechanics observation, not application latency/capacity or GPU profiling.

Actual staging reranker timings (10 calls each): BEFORE median/p95
**43.854/58.059 ms**, AFTER **49.673/65.127 ms**. Generation (3 synthetic
calls each): BEFORE median **2,555.925 ms**, range **2,486.045–2,894.828**;
AFTER median **2,581.579 ms**, range **2,531.637–2,814.750**. Request bodies and
counts are identical. The reranker median increase is recorded; small service
samples and execution variation do not establish a P2 causal latency regression.
No end-to-end request deadline or production capacity conclusion is drawn.

## Executed commands and outcomes

BEFORE command, after activation, executed at unchanged P1 configuration:

```bash
python - <<'PY'
import asyncio, json
from pathlib import Path
from scripts.rrf_p1_compare import run, write_private
from scripts.kb_signature import create_signature
p = Path('/tmp/ragbot-p2-default-20261013')
p.mkdir(mode=0o700)
inputs = json.loads(Path('/tmp/ragbot-p1-rrf-20261013/inputs.json').read_text())
write_private(p/'inputs.json', inputs)
signature = create_signature('p2-before')
write_private(p/'signature-before.json', signature)
asyncio.run(run(p, 'before', True))
PY
```

Exit **0**: five cases, 8/8 retrieved reference entries, 10 reranker and three
generation calls. Read-only target environment was already user-confirmed as
development/staging. Restricted network/local test socket actions ran through
approved sandbox elevation. No chat endpoint/persistence was used.

| Command | Exit and result |
|---|---|
| `python scripts/retrieval_depth_p2_compare.py after --directory /tmp/ragbot-p2-default-20261013 --confirmed-staging` | **0**; five exact-parity retrieval cases, 10 reranker calls, three generation calls; checks above. |
| `python scripts/retrieval_depth_p2_compare.py timing --directory /tmp/ragbot-p2-default-20261013` | **0**; 200 paired measurements per case and side; exact ordering/content equality. |
| `python scripts/retrieval_depth_p2_compare.py depths --directory /tmp/ragbot-p2-depths-20261013` | **0**; eight configurations, 200 measurements each, actual counts above. A prior mechanical run used the same ranks/labels with a generic synthetic query; the final frozen fixture explicitly names its multipart information need. |
| `python -m pytest tests/test_retrieval_depths.py tests/test_rrf_scoring.py tests/test_performance_config.py tests/test_retrieval_normalization_consistency.py tests/test_answer_context_reranking.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_validate_environment.py tests/test_revision_aware_cache.py tests/test_rag_answer_prompt_roles.py tests/test_kb_audit_tools.py -q` | **0**; **112 passed, 74 subtests passed**, 13.56 s; two SWIG deprecations and unavailable NVML warning. No frontend suites. |
| `python -m pytest tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py -q` | **0**; **15 passed, 8 subtests passed**, 0.46 s; verifies the existing internal diagnostic API and answering-path parity after lexical setting propagation. |
| `python scripts/knowledge_audit_p0_baseline.py` | **0**; zero network calls/env loads; RRF resolved, default BM25 50, requested 150 returns all 120 positive fixture entries; unbatched synthetic 150-text rerank still exceeds synthetic 64-item limit. Source-default final depth is 10; this helper deliberately measures source defaults, not project runtime. |
| `git diff --check` (final) | **0**; earlier check caught a CRLF on a newly added line, corrected without converting unrelated lines. |

Initial development runs found a validator-manifest import typo (1 failed,
32 passed, 57 subtests) and later a new test runner discarding keyword arguments
(1 failed, 111 passed, 74 subtests). Both were fixture mistakes, corrected;
an intermediate run passed 103 tests/74 subtests before the final added checks.
Counts overlap, so do not sum runs. No production retrieval workaround was made.

Post-measurement read-only signature command:

```bash
python - <<'PY'
import json
from pathlib import Path
from scripts.kb_signature import create_signature, compare_signatures
from scripts.rrf_p1_compare import write_private
p = Path('/tmp/ragbot-p2-default-20261013')
a = json.loads((p/'signature-before.json').read_text())
b = create_signature('p2-after')
write_private(p/'signature-after.json', b)
c = compare_signatures(a, b)
print(json.dumps({'record_count': b['postgres']['record_count'],
    'point_count': b['qdrant']['point_count'],
    'postgres_aggregate_sha256': b['postgres']['aggregate_sha256'],
    'cross_store_consistent': b['cross_store']['consistent'],
    'full_match': c['status']['FULL_MATCH']}))
PY
```

Exit **0**, unchanged counts/fingerprint above; only allowlisted counts/hash/match
metadata printed. Temporary directory creation and summary reads likewise used Python
stdin; they printed no source content, env values, URLs or credentials.

## Environment propagation

One new permanent key: **`RAG_BM25_CANDIDATE_LIMIT`**, positive integer/default50.

| File | Key inserted | Handling |
|---|---|---|
| `env.example` | `RAG_BM25_CANDIDATE_LIMIT` | Tracked main template |
| `Production_ENV` | `RAG_BM25_CANDIDATE_LIMIT` | Tracked main template |
| `.env.example.generated` | `RAG_BM25_CANDIDATE_LIMIT` | Tracked source-authored template |
| `.env` | `RAG_BM25_CANDIDATE_LIMIT` | Private runtime; local only |
| `.env_latest` | `RAG_BM25_CANDIDATE_LIMIT` | Existing private main runtime; local only |

Each received exactly one key. Byte-preservation checks confirmed that removing
the insertion reproduces each original file. Existing values/entries preserved.
`.env.server_git` is absent; user-deleted staging template was not recreated.
Separate evaluation-system envs were inspected as HTTP clients to the main
chatbot, not configuration sources for this Python retrieval layer; no key was
added there. No repository generator for `.env.example.generated` was found;
the existing configuration audit describes source-default authorship. Updated
validator `_specs` and a template/loader guard test prevent future omission.
Private runtime files, source evidence, answers and inputs are not committed.

## Isolation, blockers and remaining stages

Executable tests verify different concurrent depths on one engine
(150/50/150 → 150 results; 5/100/150 → 105), override-then-default requests,
unchanged process environment/settings, and one reused corpus-cache build.
Other checks cover positive lexical candidates beyond50, empty/nonpositive
branches, fewer distinct entries, overlap, invalid depths, actual Qdrant filter
and limit forwarding, effective trace/observer metrics, preserved content,
P1 scoring/ties/ranks, service routing/history/canonicalization and validation.

Live capability reads before/after matched frozen serving identities:
TEI client batch **64**, reranker max input **8,192**, automatic truncation
**disabled**, vLLM served ID `/app/model`, context **8,192**. These are observed
serving values, not older documentation. No service flags or infrastructure
changed, and no live rerank request exceeded50 texts.

**P3 dependency:** returned pools above64 cannot safely use the current one-call
real reranker. Expanded selected-context and answer completeness, cross-batch
score/index behavior and expanded end-to-end latency are unverified, deliberately
not exercised. Batching is still outstanding. P4 taxonomy preservation is still
outstanding. No workaround changed defaults, prompts or server limits.

Release acceptance still needs planner-reviewed representative fact-labeled
queries, approved regression tolerances, full read-only pipeline measurements
including actual embedding/Qdrant/corpus costs, resource/concurrency and external
50-second deadline evidence. The small frozen fixture sample cannot establish
natural-query gap/answer error rates or production deployment readiness.
