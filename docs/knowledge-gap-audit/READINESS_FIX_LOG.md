# Readiness fix log

## [00] Branch consolidation

Date: 2026-10-18 (Asia/Tehran). Repository: Hooman1996/RagBot. Environment: conda `faq`, Python 3.12.12.

### Branch survey

Fetched `origin` and verified `origin/a6.2/operational-readiness` at `cda143d5c92ae07d84b6a215d89f893dfc0b02d2`, 17 commits after `origin/main`. The nine remote branches matched the expected tips. The survey below precedes creation of `knowledge-gap-audit`. `origin/HEAD` is a symbolic alias and is excluded. Ahead/behind counts apply to the listed upstream; remote-tracking branches have no upstream.

| Branch | Tip | Upstream | Ahead / behind | Ancestor of a6.2 | Extra commits | Last commit |
|---|---|---|---|---|---|---|
| `a1/knowledge-coverage-inputs` | `9517714` | `—` | — / — | yes | 0 | 2026-10-13T16:31:04+03:30 |
| `a2.1/coverage-corrections` | `68cd16f` | `origin/a2.1/coverage-corrections` | 0 / 0 | yes | 0 | 2026-10-14T13:41:00+03:30 |
| `a2.2/audit-model-reliability` | `9d73a2e` | `origin/a2.2/audit-model-reliability` | 0 / 0 | yes | 0 | 2026-10-14T15:20:06+03:30 |
| `a2/knowledge-coverage-pilot` | `f94226e` | `origin/a2/knowledge-coverage-pilot` | 0 / 0 | yes | 0 | 2026-10-14T10:00:48+03:30 |
| `a3/coverage-calibration` | `0ea9b14` | `origin/a3/coverage-calibration` | 0 / 0 | yes | 0 | 2026-10-14T16:13:23+03:30 |
| `a4/gap-question-recommendations` | `1cc2965` | `origin/a4/gap-question-recommendations` | 0 / 0 | yes | 0 | 2026-10-14T20:14:05+03:30 |
| `a5/coverage-dashboard-export` | `11daa97` | `origin/a5/coverage-dashboard-export` | 0 / 0 | yes | 0 | 2026-10-17T08:30:54+03:30 |
| `a6.1/full-input-recovery` | `cd8989a` | `origin/a6.1/full-input-recovery` | 0 / 0 | yes | 0 | 2026-10-17T13:18:55+03:30 |
| `a6.2/operational-readiness` | `cda143d` | `origin/a6.2/operational-readiness` | 0 / 0 | yes | 0 | 2026-10-17T14:24:53+03:30 |
| `acceptance/retrieval-kb-repairs` | `7b4de65` | `—` | — / — | yes | 0 | 2026-10-13T15:30:19+03:30 |
| `main` | `681cc95` | `origin/main` | 0 / 0 | yes | 0 | 2026-10-10T19:25:14+03:30 |
| `p0/knowledge-coverage-baseline` | `0663fa0` | `—` | — / — | yes | 0 | 2026-10-12T16:16:15+03:30 |
| `p1/rrf-correction` | `c833805` | `—` | — / — | yes | 0 | 2026-10-13T11:55:55+03:30 |
| `p2/retrieval-depths` | `d45ddf6` | `—` | — / — | yes | 0 | 2026-10-13T12:38:50+03:30 |
| `p3/reranker-batching` | `e15761f` | `—` | — / — | yes | 0 | 2026-10-13T13:28:30+03:30 |
| `p4/kb-taxonomy-preservation` | `670961c` | `—` | — / — | yes | 0 | 2026-10-13T14:32:15+03:30 |
| `origin/a2.1/coverage-corrections` | `68cd16f` | `—` | — / — | yes | 0 | 2026-10-14T13:41:00+03:30 |
| `origin/a2.2/audit-model-reliability` | `9d73a2e` | `—` | — / — | yes | 0 | 2026-10-14T15:20:06+03:30 |
| `origin/a2/knowledge-coverage-pilot` | `f94226e` | `—` | — / — | yes | 0 | 2026-10-14T10:00:48+03:30 |
| `origin/a3/coverage-calibration` | `0ea9b14` | `—` | — / — | yes | 0 | 2026-10-14T16:13:23+03:30 |
| `origin/a4/gap-question-recommendations` | `1cc2965` | `—` | — / — | yes | 0 | 2026-10-14T20:14:05+03:30 |
| `origin/a5/coverage-dashboard-export` | `11daa97` | `—` | — / — | yes | 0 | 2026-10-17T08:30:54+03:30 |
| `origin/a6.1/full-input-recovery` | `cd8989a` | `—` | — / — | yes | 0 | 2026-10-17T13:18:55+03:30 |
| `origin/a6.2/operational-readiness` | `cda143d` | `—` | — / — | yes | 0 | 2026-10-17T14:24:53+03:30 |
| `origin/main` | `681cc95` | `—` | — / — | yes | 0 | 2026-10-10T19:25:14+03:30 |

### Consolidation and owner decisions

Merges: none needed. All 16 original local branches and all nine original remote branches are ancestors of `knowledge-gap-audit`; none had extra commits. Needs owner decision: none.

The user subsequently authorized removing the listed local-only files from tracking and deleting all superseded branches. `.gitignore` and `.env.recommended.rtx5880-staging` were removed from tracking. Existing local files were preserved; the already absent environment recommendation file was not restored. Existing ignore rules and the listed local-only paths were retained in `.git/info/exclude`, which is not committed. Application code was not changed.

Environment recommendation key names only (no values):

- `APPLICATION_REQUEST_TIMEOUT_SECONDS`
- `BLOCKING_CONCURRENCY_LIMIT`
- `QDRANT_CONCURRENCY`
- `RAG_CHITCHAT_MAX_NEW_TOKENS`
- `RAG_MAX_NEW_TOKENS`
- `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD`
- `RAG_RETRIEVAL_TOP_K`
- `RAG_REWRITE_MAX_TOKENS`
- `RAG_SEMANTIC_CANDIDATE_LIMIT`
- `REQUEST_ADMISSION_TIMEOUT_SECONDS`
- `REQUEST_CONCURRENCY_LIMIT`
- `TEI_EMBED_INSERT_BATCH_SIZE`
- `TEI_EMBED_MAX_CLIENT_BATCH_SIZE`
- `TEI_HTTP_CONNECT_TIMEOUT_SECONDS`
- `TEI_HTTP_KEEPALIVE_EXPIRY_SECONDS`
- `TEI_HTTP_MAX_CONNECTIONS`
- `TEI_HTTP_MAX_KEEPALIVE_CONNECTIONS`
- `TEI_HTTP_POOL_TIMEOUT_SECONDS`
- `TEI_HTTP_READ_TIMEOUT_SECONDS`
- `TEI_HTTP_WRITE_TIMEOUT_SECONDS`
- `VLLM_HTTP_CONNECT_TIMEOUT_SECONDS`
- `VLLM_HTTP_KEEPALIVE_EXPIRY_SECONDS`
- `VLLM_HTTP_MAX_CONNECTIONS`
- `VLLM_HTTP_MAX_KEEPALIVE_CONNECTIONS`
- `VLLM_HTTP_POOL_TIMEOUT_SECONDS`
- `VLLM_HTTP_READ_TIMEOUT_SECONDS`
- `VLLM_HTTP_WRITE_TIMEOUT_SECONDS`

### Verification and baseline

All 25 surveyed branches passed `git merge-base --is-ancestor <branch> knowledge-gap-audit`. Before this documentation commit, `git diff --stat origin/a6.2/operational-readiness knowledge-gap-audit` was empty; only the two authorized tracking removals were staged.

`python -m compileall -q knowledge_audit utils scripts`: passed (exit 0).

Python baseline command:

```text
python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q
```

The run was interrupted with SIGINT after ten minutes while waiting in the event loop with no additional observed CPU activity. Exit code: 2. Partial result:

```text
80 passed, 26 deselected, 4 warnings, 9 subtests passed in 601.83s (0:10:01)
```

This is an incomplete baseline, not a passing run. The expected review result was 975 passed and 5 failed. No failed test identifiers were reported before interruption; the incomplete run cannot establish whether the five known failures or any additional failures remain. No test or code fixes were made. The user authorized proceeding with the push and branch cleanup after being informed of the incomplete baseline.

Frontend results:

`node tests/knowledge_coverage.frontend.test.cjs`: exit 0.

```text
# tests 5
# suites 0
# pass 5
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 34.596596
```

`node tests/kb_manager.frontend.test.cjs`: exit 0.

```text
# tests 6
# suites 0
# pass 6
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 4060.178251
```

`node tests/analytics.frontend.test.cjs`: exit 0.

```text
# tests 5
# suites 0
# pass 5
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 88.072714
```

### Branch cleanup authorization

After publishing this commit, delete the eight original remote feature branches and 15 original local branches other than `main`. Every branch scheduled for deletion has been verified as contained in `knowledge-gap-audit`. Preserve local and remote `main` at `681cc95`; retain only `main` and `knowledge-gap-audit`. No rebase, history rewrite, or forced push is required. Final remote cleanup is verified after this commit is pushed.


## [01] Rerank uses server batch limit with verified fallback contract

Reranking now slices both context and related-question requests at the smaller of the configured size and the server capability. Valid capabilities expire after the configured TTL; failed lookups use only the verified contract and are suppressed for the retry window. Cancellation propagates, failure without a contract still fails closed, and POST response validation/global merging are unchanged. The audit checks for an effective capability before building the engine and preserves `reranker_capability_unavailable` in its error allowlists.

Files changed:

- `utils/performance_config.py`
- `utils/persian_hybrid_search.py`
- `knowledge_audit/service.py`
- `knowledge_audit/pipeline.py`
- `knowledge_audit/jobs.py`
- `scripts/validate_environment.py`
- `env.example`
- `.env.example.generated`
- `Production_ENV`
- `AGENTS.md`
- `tests/test_reranker_batching.py`
- `tests/test_p0_p1_repairs.py`
- `tests/test_knowledge_coverage_access_jobs.py`
- `docs/knowledge-gap-audit/READINESS_FIX_LOG.md`

`.env` was updated locally with the three new keys and their contract comment; it is not staged or committed. No production contact, live services, benchmarks, or full-suite run was performed. All Python checks used conda environment `faq`.

Checks and exact result lines:

```text
timeout 600 python -m pytest -p tests.offline_guard -q tests/test_reranker_batching.py tests/test_p0_p1_repairs.py tests/test_validate_environment.py tests/test_retrieval_depths.py
66 passed, 4 warnings, 159 subtests passed in 12.53s
Exit: 0

timeout 600 python -m pytest -p tests.offline_guard -q tests/test_knowledge_coverage_access_jobs.py
17 passed, 4 warnings in 14.87s
Exit: 0

python scripts/validate_environment.py --env-file .env --mode staging
Summary: 0 critical, 27 warning, 4 informational
Exit: 0

python scripts/validate_environment.py --env-file Production_ENV --mode production
Summary: 6 critical, 24 warning, 4 informational
Exit: 2

git diff --check
(no output)
Exit: 0
```

The production validator's six critical findings concern existing configuration; neither mode reported findings for any of the three new keys. No unrelated configuration was changed. The audit test command initially stalled after four tests inside the sandbox; the identical command passed outside the sandbox with the offline guard still enabled. The stalled duplicate was then terminated (exit 143); that incomplete run is not reported as passing.
