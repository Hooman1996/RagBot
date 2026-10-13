# Combined P1–P4 production-repair acceptance gate

Status: **READY_FOR_REVIEW_WITH_BLOCKED_CHECKS**.
Technical mechanics passed. **Release readiness is blocked; no release approval
or deployment is granted.** No knowledge-coverage audit work began.

## Scope, repository and commands

Repository `/root/projects/faq`; branch `acceptance/retrieval-kb-repairs`, based on
actual expected HEAD `670961c75d5d8fea286674badccda6d143d69a7d`.
The worktree already contained a changed `.gitignore`, deleted
`.env.recommended.rtx5880-staging`, private `.env_latest`, the user's
`General_FAQ.csv`, and unrelated untracked files. All remain untouched and
outside the scoped commit. No reset, rebase, stash, merge or checkout replacement
occurred. The resulting commit contains this report, the plan update and one
diagnostic script; identify it with `git log -1`.

Root AGENTS.md, implementation plan and P0–P4 reports were inspected. Applicable
debugging, Python testing, RAG, LLM evaluation and performance-audit guidance was
used within the explicitly authorized validation scope. Only already-confirmed
development/staging inference/data services were accessed. No production service,
persisting chat endpoint or live KB write endpoint was called.

All Python commands used:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Interpreter `/root/miniconda3/envs/faq/bin/python`, Python **3.12.12**.
The diagnostic imports the established explicit root `load_dotenv` path
(`scripts/rrf_p1_compare.py`, `override=False`). Effective service targets match
the root file for all five confirmed service keys; only equality flags were
printed, never URLs or credentials.

Exact regression commands and results:

```bash
python -m pytest tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py -q
python -m pytest tests/test_p2_concurrency.py tests/test_request_admission.py -q
python -m pytest tests/test_offline_frontend.py tests/test_tei_embedding_policy.py -q
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python scripts/knowledge_audit_p0_baseline.py
python -m py_compile scripts/production_repair_acceptance.py
git diff --check
```

| Check | Exit | Result |
|---|---:|---|
| Combined backend selection | 0 | **248 passed / 203 subtests**, 18.62 s |
| Lifecycle/admission | 0 | **18 passed**, 10.72 s |
| Offline assets / embedding policy | 0 | **36 passed / 10 subtests**, 1.28 s |
| KB editor JavaScript VM | 0 | **6 passed**, 4.06 s |
| Analytics JavaScript VM | 0 | **5 passed**, 0.07 s |
| Offline dependency audit | 0 | PASS; **0 external runtime dependencies** |
| P0 synthetic diagnostic | 0 | Correct RRF; configurable lexical depth; 150 rerank requests 50/50/50; taxonomy retained; literal revert |
| Diagnostic compilation / diff checks | 0 | Passed |

One preliminary supplemental command mistakenly included nonexistent
`tests/test_request_instrumentation.py`; pytest exited **4**, no tests ran.
The corrected existing-file selection above passed. No assertion was weakened.
Existing warnings concern SWIG, local NVML, datetime.utcnow and template calling
conventions. No substantive P1–P4 implementation defect was confirmed.

The existing environment validator also ran (exit 0):

```bash
umask 077
python scripts/validate_environment.py --env-file /root/projects/faq/.env --mode staging --format json > /tmp/ragbot-repair-acceptance-20261013/env-validation.json
```

It reports **0 critical / 27 warnings / 4 informational** findings. These existing
configuration findings were not suppressed or changed; the private key-only
report remains available for review. No secret values were printed or committed.

## Configuration and serving identity

Effective unchanged settings: lexical/dense/final **50/50/50**, context **10**,
context reranking enabled, client rerank batch **50**, application deadline
**50 seconds**, TEI read timeout **15 seconds**, vLLM read timeout **40 seconds**.
Source-default final depth remains 10; the P0 helper deliberately reports source
defaults, whereas all gate comparisons load the effective project configuration.

Live capability discovery matched P3: TEI **1.9.3**; embedding served path
`/app/models/models--jinaai--jina-embeddings-v5-text-small-retrieval`, input limit
32768; reranking served path `/app/models/BAAI--bge-reranker-v2-m3`, input limit
8192; both server client limits **64**, automatic truncation **false**; vLLM
served alias `/app/model`, context **8192**. These are actual responses, not older
documentation limits. Immutable weight/tokenizer revisions were not independently
verified from these serving paths/aliases.

Both `RAG_BM25_CANDIDATE_LIMIT` and `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` are present
and consistent in `env.example`, `Production_ENV`, `.env.example.generated`,
`.env` and `.env_latest`. `.env.server_git` is absent. The generated-named template
is source-authored; no generator exists according to source inspection and the
configuration documentation. The user-deleted staging template was not recreated.
Separate evaluation-system configurations do not configure this retrieval client.
**New runtime variables: none. Env-file changes: none.**

Cached reranker limits are per client/target. Client recreation after serving-limit
changes is documented in `docs/configuration/ENVIRONMENT_VARIABLES.md` and P3.
No server/client configuration was changed to measure drift or improve outcomes.

## Consistent evaluation material

Private artifacts are in `/tmp/ragbot-repair-acceptance-20261013` (0700; files
0600), including full frozen content, branch ranks, scored indexes and answers.
No dataset, KB content, source queries, copied prompt, model answer or env file
is tracked. The diagnostic prints allowlisted identifiers, counts and timing.

| Identity | SHA-256 |
|---|---|
| Existing P1/P3 frozen ranks and content | `9926d2dc6499c99ee14ccfe56306dbfef4b9cda4b262cff634dab999f3a8335f` |
| Effective configuration/artifacts | `c8af233fbe4b854dd5beedd18a3b2efeee5278a0a3f566c02db3681798ea2d65` |
| New private full-content snapshot | `7c43a32d68d79ec4fe4a61bfa3981061ef979351843f217a5e7a1983f948fa14` |
| Existing banking relevance fixture | `08e94e0126854c0fa58f3f6452acdd587dcd849406bc874d61afb1ff228cac70` |
| User's unmodified General_FAQ.csv | `d337c38df38b524c16534dc9c5f445d0e4f194c588df5c5bff3eacc2fb5bf629` |

`General_FAQ.csv` has **1526 data records**. It is a KB source, as confirmed by
the user, not an independent labeled answer-evaluation file. Equal counts alone
do not prove CSV-to-chunk content equivalence.

The actual new snapshot captures full PG chunk content in a read-only repeatable
read and matches the earlier frozen P3 content. New banking query captures retain
both actual first-stage rank lists before evaluation. `kb_signature.create_signature`
bracketed the initial live run, follow-up and token-budget check: **FULL_MATCH**, **1526 PG chunks /
1526 Qdrant points**, cross-store consistent each time. PG fingerprint remained
`948cae670aaec5faa350d977a0f381d6410a9b48d7853cdfd18bff7c76310750`.
A signature is a fingerprint; the private content/rank captures supply frozen
evidence. This is not an atomic immutable PG/Qdrant deployment snapshot.
The final identity check repeated `/info` and `/models` after all bounded live
checks; serving identities, effective configuration and KB signatures still match.

Exact diagnostic commands (all exit 0, meaning execution completed rather than
release approved):

```bash
python scripts/production_repair_acceptance.py offline --directory /tmp/ragbot-repair-acceptance-20261013
python scripts/production_repair_acceptance.py live --directory /tmp/ragbot-repair-acceptance-20261013 --confirmed-staging
python scripts/production_repair_acceptance.py followup --directory /tmp/ragbot-repair-acceptance-20261013 --confirmed-staging
python scripts/production_repair_acceptance.py budgets --directory /tmp/ragbot-repair-acceptance-20261013 --confirmed-staging
python scripts/production_repair_acceptance.py finalize --directory /tmp/ragbot-repair-acceptance-20261013 --confirmed-staging
```

## Cumulative repair comparison

The diagnostic AST-extracts only checkpoint methods, without loading old startup
modules or changing the working branch. P0.1 checkpoint `0663fa07...` and final P4
receive identical frozen ranks/content and effective default depths. P1 and P2
checkpoint methods are replayed on those same inputs as default-parity controls.

P1 changes absent-list contributions from 1/121 to zero, retaining k=60, one-based
ranks and six-decimal public scores. Single-list rank 1 becomes 0.016393; rank 100
becomes 0.006250. Both-list rank 1 remains 0.032787. Meaningful ranking changes are
expected; they are not hidden behind an equality requirement against defective P0.

| Cases | Relevant retrieved/selected P0 → P4 | Required context facts | Real model checks on synthetic facts |
|---|---|---|---|
| Three synthetic paraphrase/multipart/condition cases | 0/6 → 6/6 | 0/9 → 9/9 | 0/9 → 9/9 |
| Two short KB title controls | 2/2 → 2/2 | No fact labels | Not generated/scored |

P1, P2 and final P4 default ordered IDs, scores, original RRF ranks and full chunk
content are identical on all five cases. Each version ran 10 warmups and 100
timed alternating replay iterations per case. **Fixture-only** median ranges:
P0 0.214–0.223 ms; P4 0.215–0.223 ms. This excludes embedding/database/Qdrant costs.

Live default scoring used the original/current client methods: five logical
reranks per side, each one POST of 50. Native capability GETs are 0 → 5 because
the original client had no discovery and each final replay used a cold engine.
Median rerank latency, n=5 per side, **51.360 → 49.750 ms**; sample sizes are too
small to establish a performance improvement. Original synthetic outputs lacked
the needed evidence and appropriately did not supply the reference facts.
Final output checks cover only the predetermined working-day/cutoff/late-start
patterns; no comprehensive factual error rate is inferred.

P4's synthetic write comparison alternates checkpoint/current on the same complete
store fixture, n=100 per side/case. P0 and P3 KB/coordinator source bytes match,
so this isolates the cumulative P4 content change without real writes:

| Mocked operation | P0 median → P4 median ms | Embedding/vector/version/cache calls before → after |
|---|---:|---|
| Answer edit | 0.605 → 1.128 | 1/1/1/1 → 1/1/1/1 |
| Taxonomy edit | 0.570 → 1.078 | 1/1/1/1 → 1/1/1/1 |
| Clean unchanged submission | 0.563 → 0.906 | 1/1/1/1 → 0/0/0/0 |
| Matching legacy unchanged submission | 0.630 → 0.923 | 0/1/1/1 → 0/0/0/0 |

Current content preserves taxonomy and all synthetic answer facts; store/vector
association is consistent. No-op savings concern calls, not measured live latency.
Concurrency, locked re-resolution, versions, revisions, cache invalidation,
rollback/compensation, categorized/uncategorized revert and auth/CSRF remain
covered by the combined synthetic/HTTP regression selection.

## Banking-quality review table and unresolved result

The existing fixture describes synthetic banking queries with manually reviewed
relevance IDs. IDs were resolved through current Qdrant point-to-chunk mappings.
It has **no independent required-fact, restrictive-condition or unsupported-claim
labels**. Real vLLM responses were retained privately; they are not rated correct.
The table deliberately reports misses instead of inventing current labels.

| Fixture case | Expected evidence IDs; required facts unavailable | Retrieved expected IDs | Selected expected evidence | Answer / failure |
|---|---|---|---|---|
| balance | 744,87 | — | — | Generated; labels/facts need review |
| card-replacement | 596 | — | — | Generated; labels/facts need review |
| transfer-limit | 203,561 | — | — | Generated; labels/facts need review |
| joint-account | 148 | 148 | — | Generated; expected context missed |
| password-reset | 657,754,814 | — | — | Generated; labels/facts need review |
| cheque-status | 817,954,29 | 29 | 29 | Generated; completeness unassessed |
| mobile-banking | 765,662 | — | — | Generated; labels/facts need review |
| deposit-profit | 74 | — | — | Generated; labels/facts need review |
| iban | 100,354 | 100 | — | Generated; expected context missed |
| transaction-history | 682,90 | — | — | Generated; labels/facts need review |
| Source-derived referral 3 | Source answer/conditions; equivalents 3,4,7 | Relevant source available | 3,4,7 | Referral wording present; conditions need human review |
| Source-derived referral 57 | Source referral instruction | Relevant source available | 57 | Referral wording present; factual sufficiency unassessed |

Banking-fixture relevant inclusion is **3/19** in retrieval and **1/19** in final
context. Replaying the *original* formula on the newly frozen branch lists also
retrieves **3/19**: this is not an observed repair-induced retrieval regression.
Weak expected-title token/topic overlap suggests current labels need verification;
that heuristic does not prove the labels wrong. Neither labels nor settings were
changed. No naturally occurring labeled customer evaluation sample or human
review was supplied. Obtain current-snapshot evidence/fact/condition labels and
expert review to distinguish retrieval deficiencies, out-of-scope questions and
stale fixture references. **This is an unresolved release-quality blocker.**

The referral cases are source-derived controls selected from authorized KB content,
including one conditional source and equivalent sources under different titles.
They are not independent human-labeled quality evidence. No answer facts were
added to the KB. For the ten unlabeled generated answers, unsupported/contradictory
claims are **unassessed**, not zero. The first private run's empty-pattern forbidden
flag must not be interpreted as a quality check; the diagnostic was corrected to
emit null when no forbidden patterns exist. Synthetic zero-claim counts refer
only to their specific predetermined affirmative-calendar-day regex.

## Sequential runtime and score comparability

All live requests were sequential at logical concurrency one. No stress/load
traffic, server tuning or infrastructure changes occurred. Runtime cold means a
fresh HTTP pool, embedding client and rerank capability cache, not cold model/GPU
startup. Default followed by warm/default and joint 150/300 configurations uses
one frozen corpus/query, with explicit request-local depths:

| Operation (n=1 each) | Candidates | Rerank POST sizes | /info GETs | Retrieval / rerank / total ms | TEI reported compute tokens |
|---|---:|---|---:|---|---:|
| Cold default | 50 | 50 | 1 | 2140.972 / 60.607 / 2201.716 | 2515 |
| Warm default | 50 | 50 | 0 | 2204.832 / 49.434 / 2254.397 | 2515 |
| Expanded 150 | 150 | 50,50,50 | 0 | 2178.713 / 128.093 / 2307.009 | 7433 |
| Expanded 300 | 300 | six × 50 | 0 | 2075.722 / 228.356 / 2304.412 | 14605 |

Every candidate is accounted for by strict per-batch response/index validation;
returned candidates and selected contexts retain full snapshot content. Per-POST
timings and allowlisted service headers are retained privately. Expanded runs vary
all three depths jointly for correctness; their timing is not attributed to one
specific depth parameter. These n=1 observations do not estimate cold/warm p95,
throughput, tail latency or GPU capacity.

Cold discovery succeeds against staging; subsequent operations reuse cached limits.
A diagnostic-only 503 proxy verifies a reused client can use its cached capability,
while a fresh client returns translated `ServiceUnavailableError`, sends no rerank
POST, leaves no cached limit, and balances active counters. This is a controlled
simulation, not an induced service outage. Unit tests also cover malformed/missing
capabilities, strict response failures, cancellation,
timeouts and failure without partial success. No unbounded retry is introduced.

Partition comparability reran two frozen cases through both paths: 40 logical
operations, **72 bounded POSTs**, limits 50/25/17, rotation and reversal, two repeats
per variant. Maximum score drift: answer context **0.00089101** / real KB control
**0.00019445**; related questions **0.00057380** / **0.00068932**. Internal ordering
changed in 9/10 and 8/10 synthetic observations, 0/10 and 5/10 KB observations,
respectively; **zero selected-set changes**, labeled sources/facts retained.
Raw score modes, global tie rules, precision and thresholds were unchanged.

Actual tokenization of unchanged production messages preceded generation. Six
paired synthetic prompts used **2472–2522** tokens plus **500** output reservation,
with 23–73 actual output tokens. Ten banking-fixture prompts used **2756–3214**
tokens plus **500**, outputs 23–183. Referral prompts used **3392/3073 + 500**,
outputs 97/42. Server prompt counts matched tokenizer counts; all fit context
8192 and ended with `stop`. No full 150/300 candidate set was placed into a
generation prompt, and no source was truncated. Expanded runtime checks retain
the ordinary selected-context count of 10. An additional tokenize-only check of
the actual 150/300 selections measured **3070 + 500** tokens for each, retained
full content, and made **zero additional generation calls**. Both fit 8192;
expanded real-answer factual quality remains unassessed.

Runtime retrieval/rerank operations ran inside the configured 50-second component
wrapper; other measured components also completed in less than 50 seconds.
TEI/vLLM phase timeouts remained 15/40 seconds. Deliberate
timeout/cancellation propagation is tested with synthetic transports. The real
50-second external HTTP gateway under production-like load, server-side abort
completion and GPU headroom remain unverified. `nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader`
exited **9**: the local NVIDIA driver is unavailable. This is not a measurement
of the remote serving GPU. No approved additional concurrency/load budget or
suitable GPU telemetry source was established.

## P4 write/visual verification and readiness decision

Inspection found mocked write fixtures, but no established isolated PostgreSQL
database/Qdrant collection with exclusive run-owned cleanup. Live transactional
create → answer edit → taxonomy edit → revert → cleanup is **blocked**. No shared
FAQ was edited, no infrastructure created, no historical version rewritten, and
no bulk repair performed. Existing mocked SQL/vector/version/cache evidence is
retained; it cannot prove live distributed rollback behavior.

Python Playwright/Selenium/Pyppeteer modules, Node Playwright/Puppeteer and local
Chromium/Chrome executables/caches are unavailable. Remote browsing tools do not
establish access to a local synthetic editor. Actual rendered Persian/RTL layout,
keyboard traversal, validation/error visuals and version-history visual inspection
are **blocked/unperformed**. Existing VM tests and rendered HTML checks cover
payloads, prefilling, clearing, escaping, permissions and accessible labels; they
are not claimed as browser visual verification.

Development readiness: combined repair mechanics and scoped code are reviewable.
Release readiness: blocked by quality-label/human-review gaps, the weak fixture
result, live isolated write checks, actual editor visuals, GPU/load/deadline
evidence, production gateway `/info` compatibility, and immutable model/tokenizer
provenance. Define representative labels and regression tolerances before accepting
release quality; do not claim error rates from these small synthetic controls.

Recommended next audit stage, only after explicit planner authorization and gate
review, is **A1 frozen-input and chronological replay foundation**. A2 still must
deliver the functional main-dashboard page and initial complete per-input-row CSV.
All-query processing, optional enrichment, explainability and row conservation
contracts are unchanged. No audit routes, jobs, schemas, CSV processing or new
dashboard page were implemented. No push, merge, deployment or restart occurred.
