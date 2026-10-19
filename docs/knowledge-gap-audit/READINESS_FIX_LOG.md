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


## [02] Full offline suite runs to completion behind one command

### Hang diagnosis

The step 00 stall was caused by the sandbox environment, not a backend deadlock. The required diagnostic command was run outside the sandbox in conda `faq` with the offline guard:

```text
timeout 900 python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q -o faulthandler_timeout=60 -x
990 passed, 26 deselected, 58 warnings, 291 subtests passed in 245.04s (0:04:05)
Exit: 0
```

The originally suspected tests, `tests/test_background_logging.py::BackgroundLoggingTests::test_concurrent_jobs_and_thread_offloads_keep_distinct_parents` and `tests/test_background_logging.py::BackgroundLoggingTests::test_bounded_blocking_runner_copies_request_and_operation_context`, both passed unchanged. No hang fix or skip was needed.

The diagnostic did print a 60-second stack for the slow but completing `tests/test_knowledge_execution_recovery.py::test_full_918_selection_idempotency_chronology_export_and_mock_run`. Its top frames were `json.encoder.iterencode`, `json.encoder.encode`, `json.dumps`, `utils/read_only_audit.py:canonical_json`, `knowledge_audit/privacy.py:private_json`, `knowledge_audit/store.py:write`, and `knowledge_audit/execution.py:save_row`. This was active progress-index serialization during the 918-row fixture, not the original thread-offloading stall. No test data is included here.

### Changes

- `pytest.ini`: add a 120-second faulthandler timeout only.
- `tests/test_request_admission.py`: resolve the architecture document relative to the checkout.
- `tests/test_p2_concurrency.py`: use the requested overlap bound of 2–20 and elapsed bound of 0.5 seconds; preserve result and heartbeat assertions.
- `requirements.runtime.candidate.txt`: add `lxml==6.0.2`; this exact version was already installed in `faq`, so no installation was needed.
- `scripts/run_offline_tests.sh`: executable root-relative entry point, ordered fail-fast stages, offline-guarded pytest, all three Node suites, frontend audit, optional/required browsers, loopback free ports, bounded readiness checks, artifact paths, per-stage summaries, and fixture cleanup traps.
- `tests/knowledge_coverage.browser.cjs`: wait for input preparation before checking invalid-row counts, use the current imported-row denominator, follow explicit unknown-completion recovery when necessary, select actual aspect citation links rather than the new detail-navigation links, open collapsed source evidence and legacy downloads.
- `tests/knowledge_execution.browser.cjs`: open finite execution limits before checking the acknowledgement; use the common failure screenshot name `failed-synthetic-check.png`.
- `tests/knowledge_recommendations.browser.cjs`: wait for input preparation, freeze the explicitly selected coverage source, open the proposals disclosure, use the renamed draft-specific CSV control, and capture failure screenshots/check progress. All six original checks remain.
- `AGENTS.md`: document the single offline command.
- `docs/knowledge-gap-audit/READINESS_FIX_LOG.md`: record this step.

Both original browser failures were reproduced outside the sandbox. Their failure screenshots were opened and compared with the existing template and JavaScript. The execution baseline wrote `synthetic-failure.png`; the harness now uses the requested `failed-synthetic-check.png`. Subsequent coverage screenshots also exposed the explicit recovery requirement and the new detail navigation/source disclosures. The first single-command run also exposed an outdated recommendation flow: proposals are collapsed, a frozen source must be selected explicitly, and the draft-specific CSV button has a new label. Its failure screenshot was opened and compared with the existing page code; the repaired harness and the unchanged run-export harness both passed individually. All original harness checks were retained; none were removed. No fixture or product code changes were necessary, and no real UI bug was found. `.env` was not changed or committed in this step. No production service was contacted.

### Verification

All test commands ran outside the sandbox. Pytest retained `-p tests.offline_guard`. The 26 integration/artifact exclusions are the requested existing marker selection; no test was newly skipped or deleted.

```text
timeout 900 python -m pytest -p tests.offline_guard -q tests/test_request_admission.py tests/test_p2_concurrency.py tests/test_offline_frontend.py
38 passed in 12.72s
Exit: 0
```

The first single-command attempt exited 1 at `browser knowledge_recommendations.browser.cjs: FAIL` (TimeoutError). Its pytest result was `990 passed, 26 deselected, 58 warnings, 291 subtests passed in 243.09s (0:04:03)`; Node tests, frontend audit, coverage, execution and operations passed before the fail-fast stop. Run export was not reached in that attempt. This incomplete attempt is not reported as a passing single-command run.

Final single-command verification, with the existing Playwright/Chromium installation required:

```text
BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 scripts/run_offline_tests.sh
990 passed, 26 deselected, 58 warnings, 291 subtests passed in 243.31s (0:04:03)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
offline frontend audit: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
Exit: 0
```

The Node stage ran all three requested suites (5 coverage, 6 KB-manager and 5 analytics tests). The frontend audit reported `External runtime dependencies: 0`. All five browser harnesses passed with Chromium 153.0.8010.0, synthetic accounts/data and mocked inference. Coverage retained seven checks, execution three, operations five, recommendations six and run export seven. No harness check was removed. The script cleaned up each fixture app.

```text
git diff --check
(no output)
Exit: 0
```


## [03] Gate the audit to staging and keep production credentials local

The audit is enabled only by the exact normalized flag/environment pair defined in `coverage_enabled`; `require_coverage_enabled` fails closed. Enabling it in production raises `coverage_enabled_in_production`. Both deployment error codes are allowlisted for API detail, pipeline results, operational diagnostics and interrupted-job records.

Gated entry points: `knowledge_audit.api.mount`, `api.runtime`, `CoverageJobs.start`, `RecommendationJobs.start`, `service.build_engine`, and `runtime.confirm_staging`. `main.py` calls `mount(app)`; the other routers and shutdown cleanup are unchanged. Existing confirmation, loopback and root-environment target checks remain.

Gated CLI `main` functions, with dotenv loading before the gate and code-only AuditError output/status 2:

- `scripts/knowledge_audit_p0_baseline.py`
- `scripts/knowledge_audit_prepare.py`
- `scripts/knowledge_coverage_calibrate.py`
- `scripts/knowledge_coverage_diagnose.py`
- `scripts/knowledge_coverage_pilot.py`
- `scripts/knowledge_coverage_resources.py`
- `scripts/knowledge_recommendation_pilot.py`
- `scripts/knowledge_recommendation_revalidate.py`

Exempt: `scripts/knowledge_coverage_cleanup.py` remains available to delete leftover data while disabled; `scripts/diagnose_knowledge_update_production.sh` is not an audit CLI and was not changed or run.

Permissions return existing role grants without loading coverage settings while disabled or misconfigured. Enabled configurations cache access grants by `(KNOWLEDGE_COVERAGE_ACCESS_GRANTS, KNOWLEDGE_COVERAGE_ARTIFACT_DIR)`; AuditError results are not cached. Existing audit tests and the shared synthetic browser app explicitly opt into staging; assertions are unchanged except for replacing the production-file name in the five documentation checks.

`Production_ENV` was untracked and retained locally, byte-for-byte unchanged except for the requested gate comment/key. Its tracked example preserves line order/comments and non-secret configuration, with these key names emptied:

- `QDRANT_API_KEY`
- `POSTGRES_PASSWORD`
- `DEFAULT_DB_PASSWORD`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

The initial tracked-secret scan also found `MINIO_SECRET_KEY` in five application files. The owner explicitly approved expanding this step to remove those hard-coded defaults and commented copies. The affected configuration classes now read credentials only from the environment; document upload accepts explicit credentials or reads the environment when omitted. No credential values were printed or included in this log. The scan passed after the removals.

Restored `.gitignore` with the prescribed edits. Private export-name rules remain only in `.git/info/exclude`. Redundant local blanket exclusions hiding tracked paths were removed from that local file so the requested invariant holds. `git ls-files -ci --exclude-standard` prints exactly:

```text
training/artifacts/intent_guardrail_jina_retrieval_query_v1.pt
```

This Git version rejects `git check-ignore -q .env Production_ENV .env.server_git` because quiet mode accepts only one path. The equivalent per-path quiet checks all exited 0. No private export filenames were emitted or added to `.gitignore`.

The unchanged `docs/architecture/REQUEST_ADMISSION_AND_BACKPRESSURE.md` passed category checks: no known secret-value matches, credential assignments, customer-data patterns, hostnames or IP addresses. It is included as-is.

Files changed (including the explicitly approved extension):

- `.env.example.generated`
- `.gitignore`
- `AGENTS.md`
- `Production_ENV`
- `Production_ENV.example`
- `docs/architecture/REQUEST_ADMISSION_AND_BACKPRESSURE.md`
- `docs/knowledge-gap-audit/READINESS_FIX_LOG.md`
- `env.example`
- `knowledge_audit/api.py`
- `knowledge_audit/jobs.py`
- `knowledge_audit/operations.py`
- `knowledge_audit/pipeline.py`
- `knowledge_audit/recommendation_jobs.py`
- `knowledge_audit/runtime.py`
- `knowledge_audit/service.py`
- `knowledge_audit/settings.py`
- `main.py`
- `new_architecture/app/config.py`
- `new_architecture/app/core/database.py`
- `new_architecture/app/services/document/upload.py`
- `new_architecture/data_insertion_with_api.py`
- `new_architecture/insert_data.py`
- `scripts/check_tracked_secrets.py`
- `scripts/knowledge_audit_p0_baseline.py`
- `scripts/knowledge_audit_prepare.py`
- `scripts/knowledge_coverage_calibrate.py`
- `scripts/knowledge_coverage_cleanup.py`
- `scripts/knowledge_coverage_diagnose.py`
- `scripts/knowledge_coverage_pilot.py`
- `scripts/knowledge_coverage_resources.py`
- `scripts/knowledge_recommendation_pilot.py`
- `scripts/knowledge_recommendation_revalidate.py`
- `scripts/run_offline_tests.sh`
- `scripts/validate_environment.py`
- `tests/knowledge_coverage_browser_app.py`
- `tests/test_coverage_deployment_gate.py`
- `tests/test_knowledge_coverage_access_jobs.py`
- `tests/test_knowledge_coverage_calibration.py`
- `tests/test_knowledge_coverage_corrections.py`
- `tests/test_knowledge_execution_recovery.py`
- `tests/test_knowledge_operations.py`
- `tests/test_knowledge_recommendations.py`
- `tests/test_knowledge_run_export.py`
- `tests/test_reranker_batching.py`
- `tests/test_retrieval_depths.py`
- `tests/test_step5_query_canonicalization.py`
- `tests/test_web_permissions.py`
- `web_permissions.py`

Checks before commit ran outside the sandbox in conda `faq`, retaining the offline pytest guard:

```text
timeout 900 python -m pytest -p tests.offline_guard -q tests/test_coverage_deployment_gate.py tests/test_knowledge_coverage_access_jobs.py tests/test_validate_environment.py tests/test_reranker_batching.py tests/test_retrieval_depths.py tests/test_step5_query_canonicalization.py tests/test_knowledge_coverage_calibration.py tests/test_request_admission.py
158 passed, 4 warnings, 168 subtests passed in 27.66s
Final rerun after the approved credential-default removals:
158 passed, 4 warnings, 168 subtests passed in 27.64s
Exit: 0

python scripts/check_tracked_secrets.py
tracked secrets: 0 matches
Exit: 0

python scripts/validate_environment.py --env-file .env --mode staging | tail -1
Summary: 0 critical, 27 warning, 4 informational
Pipeline exit: 0; validator exit: 0

python scripts/validate_environment.py --env-file Production_ENV --mode production | tail -1
Summary: 6 critical, 24 warning, 4 informational
Pipeline exit: 0; validator exit: 2
```

Validator summaries were captured from full output because the requested tail pipelines emit the last finding rather than the summary. Comparing critical key names against the prior validator found no new critical findings in either mode, including for `KNOWLEDGE_COVERAGE_ENABLED` and `ENVIRONMENT`. Existing production findings remain out of scope.

Open owner item: the five production credentials remain in Git history before this commit. Rotation and removal from historical commits are owner decisions and were not performed. No production target was contacted. `.env` and `.env.server_git` remain local and are not staged.

Clean-checkout verification was performed on the initial unpushed commit; exact results follow below. The final amended commit must repeat this clean check before push.

`git diff --check`: no output, exit 0. The insertion script originally mixed line endings; only the two edited credential lines were normalized to avoid newly introduced trailing-whitespace findings.

The scan after staging the new example initially failed: credential values were reused in non-secret configuration fields. The owner explicitly approved emptying `QDRANT_COLLECTION`, `POSTGRES_USER`, `DEFAULT_DB_USER`, `DEFAULT_DB_NAME`, and `MINIO_BUCKET` in `Production_ENV.example` as well. This is an approved exception to copying non-secret values unchanged. The real local production file remains unchanged. No scan exception or allowlist was added.

Clean-checkout command (conda `faq`, outside the sandbox):

```text
git worktree add /tmp/faq-clean-03 HEAD
cd /tmp/faq-clean-03 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-03; echo "exit $status"
1014 passed, 26 deselected, 58 warnings, 291 subtests passed in 240.21s (0:04:00)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

This clean checkout contained no local environment files. The secret stage's NOT RUN result was expected; the main checkout ran the value scan successfully. All five synthetic browser harnesses passed, including coverage, execution, operations, recommendations and run export. No test was newly skipped or removed; the 26 deselections are the requested existing integration/artifact marker exclusions. The temporary worktree was removed.

Only the approved additional example-field sanitization and this verification log change after that first clean run. Before push, the amended commit must be checked in a new clean worktree with the identical command and the same passing stage summaries. No live service or production access is authorized by this verification.

Focused command rerun after the approved example-field correction:

```text
158 passed, 4 warnings, 168 subtests passed in 28.12s
Exit: 0
```

`git check-ignore .env Production_ENV .env.server_git` also exited 0 and printed only these paths:

```text
.env
Production_ENV
.env.server_git
```

Final main-checkout secret scan: `tracked secrets: 0 matches` (exit 0). `git diff --check` again had no output (exit 0).

## [03a] Audit retrieval depths and entry budget come from the environment

The audit's retrieval depths and per-question entry ceiling are read from the environment. Defaults are unchanged:

| Key | Field | Default | Range |
|---|---|---|---|
| `KNOWLEDGE_COVERAGE_INITIAL_DEPTH` | `initial_depth` | 150 | 1–1000 |
| `KNOWLEDGE_COVERAGE_BROADER_DEPTH` | `broader_depth` | 300 | 2–1000 |
| `KNOWLEDGE_COVERAGE_INITIAL_ENTRIES` | `initial_entries` | 50 | 1–1000 |
| `KNOWLEDGE_COVERAGE_MAX_ENTRY_BUDGET` | `max_entry_budget` | 300 | 1–1000 |

`CoverageSettings` requires `initial_entries <= initial_depth < broader_depth`, or it raises `invalid_coverage_depths`. With the defaults, the settings manifest is identical to the previous one: `initial_depths` `[150]*3`, `expanded_depths` `[300]*3`, `initial_entries` 50 and `maximum_distinct_entries` 300. No key was added and `schema` is unchanged, so existing runs continue. A run started under other depths still fails with `audit_runtime_identity_drift` in `build_engine`.

`build_engine` passes the run's pinned `meta["settings"]` values (`initial_depths[0]`, `expanded_depths[0]`, `initial_entries`, `maximum_distinct_entries`) to `AuditRetrieval` and `CoverageEvaluator`, not the live settings. `ControlledCandidates` compares against its `initial_depth`. The API's `entry_budget` defaults to `settings.max_entry_budget`. A value above it is rejected with `invalid_entry_budget` through `safe_call`, and the code was added to `SAFE_API_CODES` so the rejection is visible. The page renders the budget input from `max_entry_budget`. The pilot, calibration, recommendation-pilot and resource scripts read the settings. `scripts/knowledge_audit_p0_baseline.py` is unchanged.

No existing allow-list contained `invalid_coverage_integer`; it appears only in `knowledge_audit/settings.py`. No allow-list was changed for `invalid_coverage_depths`.

The four keys were added after `KNOWLEDGE_COVERAGE_RETENTION_DAYS` in `.env` and `Production_ENV` (local only), `env.example`, `.env.example.generated` and `Production_ENV.example`, and to `SPECS` with component `Knowledge coverage audit`. `.claude/skills` is a relative symlink to `../.agents/skills`; `test -f .claude/skills/fastapi/SKILL.md && echo ok` printed `ok`. No `CLAUDE.md` was added.

This step changes no behavior with the default values. No retrieval, answer-quality or performance run was required or performed.

Checks before commit ran outside the sandbox in conda `faq`, with the offline pytest guard:

```text
timeout 900 python -m pytest -p tests.offline_guard -q tests/test_coverage_deployment_gate.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_coverage_calibration.py tests/test_validate_environment.py tests/test_retrieval_depths.py tests/test_coverage_depth_settings.py
141 passed, 4 warnings, 44 subtests passed in 17.70s

python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

python scripts/validate_environment.py --env-file .env --mode staging | tail -1
Summary: 0 critical, 27 warning, 4 informational
Validator exit: 0

git diff --check
no output, exit 0
```

The validator summary was taken from the full output, because `tail -1` prints the last finding. The counts match step 03. The four new keys report `set` with no findings.

Clean-checkout command (conda `faq`, outside the sandbox), run on the initial unpushed `[03a]` commit:

```text
git worktree add /tmp/faq-clean-03a HEAD
cd /tmp/faq-clean-03a && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-03a; echo "exit $status"
1020 passed, 26 deselected, 58 warnings, 291 subtests passed in 246.87s (0:04:06)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1014 in step 03 to 1020, from the six new tests in `tests/test_coverage_depth_settings.py`. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's value scan passed. The 26 deselections are the existing integration and artifact marker exclusions. Only this log section changed after that run. The amended commit was checked again in a new clean worktree with the same command before push.

## [04] Accept a coverage proof only after every conflict in its view has an explicit verdict

Fixes F1 (High, false "covered" rows) and F16a (Low, lost `verification_token_overflow`).

### Rule (approved by the owner)

- Every conflict in an evidence view goes to the verifier together with its source entries. The verifier gives each conflict exactly one verdict: `not_applicable`, `compatible`, `contradicts` or `cannot_determine`.
- A proof is accepted only when the model says `accepted`, every conflict has a verdict, and none is `contradicts` or `cannot_determine`. The code enforces this whatever the model's verdict: `contradicts` downgrades to `rejected` (`conflict_contradicts_proof`); `cannot_determine` or a missing assessment downgrades to `uncertain` (`conflict_undetermined`). An unknown or duplicate `conflict_id` raises `invalid_conflict_identity`.
- An `uncertain` support for an aspect the witness relies on, from an entry outside the proof, is a conflict record.
- More than 40 conflict records: no verification call; the proof is unresolved with `conflict_limit_exceeded`.
- Failures not linked to the proof's aspects are residual codes (`residual_review_codes`). They are shown, never block full coverage and are never reported as resolved.

`view` now re-verifies each accepted proof wholly inside the view when the view's conflict records are not a subset of the records that proof's verifier saw (`conflict_ids_seen`). The cache keeps this to one call per distinct payload. Each proof keeps its own `codes`, and `view` adds them, so `verification_token_overflow` is no longer overwritten (F16a).

Code sets in `knowledge_audit/pipeline.py`:

| Set | Codes |
|---|---|
| `BLOCKING_CODES` | `evidence_conflict`, `verification_unresolved`, `incompatible_conditions`, `conflict_contradicts_proof`, `conflict_undetermined`, `conflict_limit_exceeded` |
| `RESIDUAL_CODES` | `entry_too_long`, `evaluation_failed`, `subset_batch_uncertainty`, `batch_support_unresolved`, `batch_uncertain` |
| `SEARCH_CODES` | `compatibility_unverified`, `bounded_bundle_search_unresolved`, `reconciliation_token_overflow`, `verification_token_overflow` |

With a witness, `resolved_review_codes` holds only the blocking codes present. Without one, `review_codes` is unchanged from before (residual codes included) and `resolved_review_codes` is empty.

### Files changed

- `knowledge_audit/schemas.py`: `ConflictAssessment`; `VerificationDecision` is `verification-2` with `conflict_assessments`; `VERSION` is `coverage-rubric-5`.
- `knowledge_audit/prompts.py`: the approved sentence appended to the `verification` task only.
- `knowledge_audit/pipeline.py`: `view_conflicts`, `conflict_key`, the code sets, `MAX_VIEW_CONFLICTS = 40`, conflict records in `proof_payload`, the verdict rule in `verify`, witness selection in `view`, `residual_review_codes` in `apply_result`, `proof_reuse_version` `question-ledger-2`, `invalid_conflict_identity` in `ERROR_CODES`.
- `knowledge_audit/settings.py`: `manifest()` `proof_reuse_version` `question-ledger-2`.
- `knowledge_audit/export.py`: `residual_review_codes` after `review_codes` in `COVERAGE_FIELDS`, in `ARRAY_FIELDS`, and kept in restricted exports.
- `knowledge_audit/jobs.py`: `invalid_conflict_identity` in the interrupt allow-list.
- `knowledge_audit/failures.py`: `invalid_conflict_identity` in `VALIDATION_CODES`, next to `invalid_reconciliation_identity`, so its failure diagnostic is `semantic_validation`.
- `static/js/knowledge_coverage.js`: English labels for the three new review codes, and an "Unexamined evidence notes" line for `residual_review_codes`.
- `tests/test_coverage_conflict_verdicts.py`: new, 14 tests.
- `tests/test_knowledge_coverage_pipeline.py`: the fake verifier returns `verification-2` and one assessment per `observed_conflicts` item, default `not_applicable` (`conflict_assessment=` keyword). No expectation changed.
- `tests/test_knowledge_recommendations.py`: rubric-version pin.

`evidence_conflict` appeared only in `knowledge_audit/pipeline.py`; no other review-code list exists in `knowledge_audit/` or `static/js/knowledge_coverage.js`.

### Changed test expectations

One expectation changed. It pins the rubric version and does not encode F1:

```text
tests/test_knowledge_recommendations.py:360
old: assert prompt_identity()['rubric_version']=='coverage-rubric-4' and ...
new: assert prompt_identity()['rubric_version']=='coverage-rubric-5' and ...
```

No pipeline, calibration, corrections or export expectation changed. `test_conflicting_conditions_cannot_be_combined_into_full` passes unmodified.

### Versions and resumption

`verification-1` → `verification-2`, `coverage-rubric-4` → `coverage-rubric-5`, `question-ledger-1` → `question-ledger-2` (row `evaluation_scope` and settings manifest). Runs created before this step no longer resume; they stop with `audit_runtime_identity_drift` or `audit_version_drift`. This is intended.

### Implementation decisions not covered by the command

These were not put to the owner; they are recorded for review.

- Persian labels were not added. The coverage UI has a single English `LABELS` map and no Persian text anywhere, so there is no existing style to follow. The English labels and the "Unexamined evidence notes" heading were added. The Persian strings from the command are «شواهد با اثبات در تناقض است», «یک تعارض قابل ارزیابی نبود», «تعارض‌ها برای بررسی بیش از حد است» and «یادداشت‌های شواهد بررسی‌نشده».
- An accepted proof must cover every required aspect, so an uncertain support for an aspect outside the witness cannot occur end to end. Test 6 therefore checks that aspect rule on `view_conflicts` directly, and checks end to end that an uncertain batch about other entries creates no record, does not block, and appears only in `residual_review_codes`.
- A proof record keeps `entry_ids` as all entries in its `source_evidence` (witness plus conflict sources), used for the "wholly inside the view" test, and `witness_entry_ids` for the uncertain-support rule.
- When the model says `accepted` with both `contradicts` and `cannot_determine`, both codes are recorded and the verdict is `rejected`. The downgrade codes are recorded only when the model said `accepted`.
- The batch's own verification in `assess` passes no conflict records, because `validate_batch` forbids conflicts on a full batch; each view then re-verifies against its own records.
- With more than 40 records, reconciliation is still called; only verification is skipped.
- Without a witness, `conflict_assessments` is from the last verification run in that view, or else the last proof wholly inside it.

### AGENTS.md note

This changes the audit's own verification prompt and schema, not the chatbot. Chatbot retrieval and answers are unchanged, so the chatbot's retrieval and answer-quality tests do not apply. The audit's live behaviour is re-checked in the Gate A pilot. No performance change; no benchmark was required.

### Checks

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_coverage_conflict_verdicts.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_calibration.py tests/test_knowledge_coverage_corrections.py tests/test_knowledge_run_export.py tests/test_coverage_depth_settings.py
121 passed, 3 warnings in 39.13s

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

Clean-checkout command (conda `faq`), run on the initial unpushed `[04]` commit:

```text
git worktree add /tmp/faq-clean-04 HEAD
cd /tmp/faq-clean-04 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-04; echo "exit $status"
1034 passed, 26 deselected, 58 warnings, 291 subtests passed in 258.26s (0:04:18)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1020 in step 03a to 1034, from the 14 new tests in `tests/test_coverage_conflict_verdicts.py`. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. The 26 deselections are the existing integration and artifact marker exclusions. Only this log section changed after that run. The amended commit was checked again in a new clean worktree with the same command before push.

## [05] KB snapshots keep public facts and scrub only secrets and validated personal identifiers

Finding F2 (High). `capture_snapshot` ran every KB chunk through the customer-query redactor, so fees, limits, support numbers and procedure sentences became `[PRIVATE_…]`. A fee or limit question then could never be covered. If the model read a masked fact as missing, the row became a clean `possible_gap` that was eligible for recommendations.

### Three policies (approved by the owner)

| Policy | Code | This step |
|---|---|---|
| Customer queries | `Redactor.text` | Unchanged. `preparation.py` and `history.py` untouched. |
| Logging | `utils/log_sanitizer.scrub_text` | Unchanged. KB text is never logged. |
| KB content | new `Redactor.kb_text`, `kb_version = "kb-content-1"` | Scrubs only secrets (`_INLINE_SECRET`, `_BEARER`, `_JWT`), Luhn-valid cards, mod-97-valid IBANs, checksum-valid national IDs, mobiles and emails that are not on the public-contact allow-list, and the value (not the label) after `کد ملی`, `شماره حساب`, `شماره کارت` or `شبا` + `:`/`=` when it has 8 or more digits. Keeps amounts, limits, durations, dates, percentages, landlines, short codes, digit runs that fail their checksum, allow-listed contacts, and `نام:` and `رمز:` text. |

`kb_text` does not call `scrub_text`. It uses the same `[PRIVATE_<12 hex>]` callback and placeholder-skipping loop as `text`, so a value gets the same placeholder under both policies.

Rows that rely on a scrubbed entry go to review and are not eligible for recommendations. `view` adds `kb_redaction_affected` (a residual code) whenever an evaluated entry in the view has `redaction_changed`. With no witness the row is `needs_review`. A witness that uses no scrubbed entry stays `covered_*`, and the code appears only in `residual_review_codes`. A witness that uses a scrubbed entry is still downgraded by `verify`. `eligibility` adds `kb_redaction_unresolved` when the code appears in `review_codes`, `residual_review_codes` or any phase of `review_codes_by_phase`.

### Files changed

- `knowledge_audit/privacy.py`: `Redactor.kb_version`, `Redactor.kb_text`, `_valid_iban` (ISO 13616 mod-97 after Persian and Arabic digit normalisation), `normalize_public_contact`.
- `knowledge_audit/settings.py`: `CoverageSettings.public_contacts`, parsed from `KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS`. Entries can be an exact email, an `@domain` or a phone number. Emails and domains are lower-cased. Phones are converted to ASCII digits, with spaces and hyphens removed and a leading `+98`/`0098` changed to `0`. Any other entry raises `invalid_coverage_public_contacts`. The setting is not in `manifest()`; the snapshot records it.
- `knowledge_audit/snapshot.py`: `content` and `document_title` go through `kb_text`. `schema_version` is `a1-kb-snapshot-2`, with `kb_redaction_policy = {version, public_contacts_sha256}`, and the manifest is `a1-kb-manifest-2`. `load_snapshot` accepts versions 1 and 2. `privacy.py` is still in `capture_code_sha256`.
- `knowledge_audit/execution.py`: `create_run` raises `snapshot_policy_superseded` for any snapshot that is not version 2.
- `knowledge_audit/api.py`: passes `settings.public_contacts` to `capture_snapshot`; `snapshot_policy_superseded` added to `SAFE_API_CODES`.
- `knowledge_audit/failures.py`: new `RUN_ADMISSION_CODES = {"snapshot_policy_superseded"}`.
- `knowledge_audit/pipeline.py`: `kb_redaction_affected` in `view` and `RESIDUAL_CODES`.
- `knowledge_audit/recommendations.py`: `kb_redaction_unresolved`.
- `knowledge_audit/recommendation_fixtures.py`: the fictional A4 fixture snapshot is now `a1-kb-snapshot-2` with `kb_redaction_policy`. It was changed because `scripts/knowledge_recommendation_pilot.py` registers this fixture and calls `store.create_run` with it, which would now raise `snapshot_policy_superseded`.
- `scripts/knowledge_audit_prepare.py`: passes `load_coverage_settings().public_contacts` when `--capture-snapshot` is given.
- `scripts/validate_environment.py`: `KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS` spec (string, default empty, component `Knowledge coverage audit`, restart `FastAPI`, usage `Redactor.kb_text`).
- `static/js/knowledge_coverage.js`: labels for `kb_redaction_affected` and `snapshot_policy_superseded`.
- `env.example`, `.env.example.generated`, `Production_ENV.example`, plus the untracked local `Production_ENV` and `.env`: `KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS=` with an empty value and the agreed comment. No contacts were invented; the owner fills in the list.
- `tests/test_kb_content_privacy.py`: new, covering command tests 1–10.
- `tests/test_knowledge_coverage_access_jobs.py`: shared `seed` fixture (see below).

### Old snapshots

Snapshots captured before this step still load and export, but they can no longer start runs: `create_run` refuses them with `snapshot_policy_superseded`, and the page shows "Snapshot captured under an older privacy policy. Capture a new snapshot." Capture a new snapshot before the next run.

### Changed test expectations

One existing fixture changed; no assertion changed.

- `tests/test_knowledge_coverage_access_jobs.py` `seed`, which the operations, execution-recovery, reliability, run-export and browser tests share. Old: `snap.update(schema_version='a1-kb-snapshot-1',source_signature={},retrieval_frozen=False)`. New: `snap.update(schema_version='a1-kb-snapshot-2',source_signature={},retrieval_frozen=False, kb_redaction_policy={'version':Redactor.kb_version,'public_contacts_sha256':canonical_sha256([])})`. Reason: `seed` creates a run, and a version 1 snapshot can no longer start one.

`tests/test_knowledge_audit_a1.py` and `tests/test_knowledge_sources.py` have no assertion that amounts or digit runs are masked in KB snapshots, so neither changed. `test_snapshot_redacts_sensitive_content_without_truncation` checks that the mobile `09123456789` is scrubbed and `redacted_record_count == 1`, which still holds because that mobile is not allow-listed. No `Redactor.text` customer-query test changed.

### Implementation decisions not covered by the command

These were not put to the owner; they are recorded for review.

- `failures.py` has only the model-failure lists `TRANSPORT_CODES` and `VALIDATION_CODES`. Adding `snapshot_policy_superseded` to either would make `category()` classify it as a row failure, but the code is raised before any run or row exists. It is in a new `RUN_ADMISSION_CODES` set instead, and a test checks that set is a subset of `SAFE_API_CODES`.
- The page showed API error `detail` strings raw. `api()` in `knowledge_coverage.js` now shows `LABELS[detail]` when a label exists, so the new English message is displayed; other details are unchanged.
- The labelled-identifier value is the digit token after the label (an optional `IR`, then digit groups separated by a single space or hyphen), not the rest of the line. "شماره حساب: شماره ۱۳ رقمی خود را وارد کنید." is kept.
- The shared `_MOBILE` pattern also consumes one separator after the last digit. `kb_text` keeps that separator outside the placeholder so surrounding words stay intact.
- `redaction_changed` still compares `content` only, as before; a scrub of `document_title` is not evidence.
- An empty value gives an empty allow-list. A blank entry inside a non-empty list (for example `a@b.example,,c@d.example`) is rejected as `invalid_coverage_public_contacts`.

### AGENTS.md note

This changes only what the audit's KB snapshot keeps. The chatbot's retrieval, answers and logging are unchanged, so the chatbot's retrieval and answer-quality tests do not apply. No performance change; no benchmark was required.

### Checks

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_kb_content_privacy.py tests/test_knowledge_audit_a1.py tests/test_knowledge_sources.py tests/test_coverage_conflict_verdicts.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_recommendations.py tests/test_validate_environment.py
183 passed, 3 warnings in 16.79s

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

The same files gave 142 passed before this step; the 41 new tests are in `tests/test_kb_content_privacy.py`.

Clean-checkout command (conda `faq`), run on the initial unpushed `[05]` commit:

```text
git worktree add /tmp/faq-clean-05 HEAD
cd /tmp/faq-clean-05 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-05; echo "exit $status"
1075 passed, 26 deselected, 58 warnings, 291 subtests passed in 256.39s (0:04:16)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1034 in step 04 to 1075, from the 41 new tests in `tests/test_kb_content_privacy.py`. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. The 26 deselections are the existing integration and artifact marker exclusions. Only this log section changed after that run. The amended commit was checked again in a new clean worktree with the same command before push.

## [06] Ticket referrals count only for contact questions; unclassified aspects go to review

### Problem

The rule that a referral can answer how to submit a ticket, but not a missing fee, duration, eligibility condition or other fact, existed only in the prompt (`knowledge_audit/prompts.py:12-14`). When the batch evaluator and the verifier both accepted "please submit a ticket" as support for "What is the card issuance fee?", the row became `covered_reachable` with verification `accepted`.

### Rule (approved by the owner)

Each aspect is classified from its normalised `description`. A support is referral-only when every sentence it cites is only a referral or the chatbot's fallback text.

| Aspect class | A referral-only support |
|---|---|
| `contact_procedure` | counts as support |
| `substantive_fact` | does not count; the aspect's outcome follows the rest of the evidence |
| `unclassified` | counts, and the row goes to review (`referral_support_unclassified`) |

`substantive_fact` is checked first, so "Fee for submitting a complaint" is substantive.

### Regexes (`knowledge_audit/referrals.py`, `VERSION = "referral-guard-1"`)

All matching runs on `normalize_persian_text(text).lower()`, the normaliser the audit already uses in `preparation.py` and `recommendations.py`.

- `REFERRAL_PATTERNS`, one compiled regex per phrase, with words joined by `[\s‌]+`: the normalised `FAQ_FALLBACK_FRAGMENT`, each of its two sentences, `اقدام به ثبت تیکت`, `ثبت تیکت`, `تیکت ثبت کن`, `با پشتیبانی تماس بگیرید`, `به پشتیبانی پیام دهید`, `از طریق پشتیبانی`, `submit a ticket`, `open a ticket`, `contact customer support`, `contact support`.
- `SUBSTANCE`: `[0-9۰-۹٠-٩]|ریال|تومان|rial|روز|ساعت|دقیقه|هفته|ماه|day|hour|minute|week|month|سقف|حداقل|حداکثر|کارمزد|هزینه|fee|limit|minimum|maximum|شرط|شرایط|مشمول|eligible|condition`
- `SUBSTANTIVE_ASPECT`: `کارمزد|هزینه|مبلغ|سقف|حداقل|حداکثر|مدت|زمان|چقدر|چند|روز|ساعت|شرایط|شرط|مشمول|نرخ|سود|درصد|fee|cost|amount|limit|minimum|maximum|how long|how much|duration|time|days?|hours?|eligib|condition|requirement|rate|interest|percent`
- `CONTACT_ASPECT`: `تیکت|پشتیبانی|تماس|ارتباط|شکایت|اعتراض|ticket|support|contact|complain|reach`

`is_referral_only(sentence)` is true when at least one referral pattern matches and, after every match is deleted, `SUBSTANCE` finds nothing.

### Changes

- `utils/faq_fallback.py` holds `FAQ_FALLBACK_FRAGMENT`, with the string unchanged; `agent_graph.py` imports it from there, so the audit does not import LangGraph.
- `knowledge_audit/pipeline.py`:
  - `evaluate` stores `self.aspect_classes`.
  - `assess` resolves each support's cited sentences. It moves referral-only supports for `substantive_fact` aspects out of the batch's usable `supports` into `excluded_referral_supports` and records their IDs in `self.referral_excluded_ids`. It records referral-only supports for `unclassified` aspects in `self.referral_unclassified_ids`. A batch the model called `full` is verified only if the remaining supports still cover every required aspect; otherwise it is treated like a partial batch. `batch["result"]` is stored as the model returned it.
  - `view` adds the note `referral_only_support` to `residual_review_codes` when a batch in the view has excluded referral supports, with or without a witness. The new `NOTE_CODES` set holds it; it never enters `review_codes`, never blocks and is never resolved.
  - `apply_result` sets `outcome` and `processing_status` to `needs_review` and adds `referral_support_unclassified` (now in `BLOCKING_CODES`) when a full witness uses a referral-only support for an unclassified aspect. `coverage_status` stays `full`.
- `knowledge_audit/settings.py`: the manifest gained `"referral_guard_version": "referral-guard-1"`. Runs created before this step cannot resume, because `service.py` refuses a run whose stored settings differ from the current manifest.
- `static/js/knowledge_coverage.js`: English labels for `referral_only_support` and `referral_support_unclassified`.
- Eligibility is unchanged. `needs_review` rows are ineligible, and a note in `residual_review_codes` leaves a real gap eligible; a test checks that the note does not change the eligibility decision.

### Existing tests and calibration

No calibration case changed outcome; `tests/test_knowledge_coverage_calibration.py` passed unchanged.

One existing test fixture changed; no expected outcome changed.

- `tests/test_knowledge_coverage_pipeline.py::test_referral_instructions_vs_missing_substantive_fact[True-covered_reachable]` failed with `needs_review` after the guard. Its shared `LabeledModel` describes every aspect as "Requested fixture fact a1", which is `unclassified`, and the cited sentence "To submit a ticket, open Support and select New ticket." is referral-only. The question is "How do I submit a ticket?", so the test now gives its aspect the description "How to submit a ticket" (`contact_procedure`), and "Fee amount" for the fee question. The expected outcomes `covered_reachable` and `possible_gap` are unchanged.
- `tests/test_coverage_conflict_verdicts.py::test_every_view_code_belongs_to_exactly_one_set` now checks four disjoint sets, including `NOTE_CODES`, and its source scan also reads `residual.append(...)`.

### Implementation decisions not covered by the command

These were not put to the owner; they are recorded for review.

- `segment_answer` splits the fallback into two sentences, and a citation points at one sentence. The patterns therefore include each fallback sentence as well as the whole fragment, so an entry that repeats the fallback is referral-only whichever sentence is cited. The fallback patterns come first and longer phrases before shorter ones, so deleting matches removes each phrase whole.
- "Remaining supports cover every required aspect" counts only supports whose applicability is not `uncertain`, the same test `validate_batch` uses for a full claim.
- The note is added when any batch in the view has excluded supports, as the command says, even if the excluded support's entry is outside the view; the same batch-level rule already applies to batch conflicts.
- `tests/test_coverage_referral_guard.py` also checks that the note is kept beside a verified witness from another entry, and that the manifest carries the guard version.

### AGENTS.md note

Moving the constant is the only change in `agent_graph.py`, and the string is identical, so the chatbot's behaviour is unchanged. The guard affects only the audit, so the chatbot's retrieval and answer-quality tests do not apply. No performance change; no benchmark was required.

### Checks

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_coverage_referral_guard.py tests/test_coverage_conflict_verdicts.py tests/test_kb_content_privacy.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_calibration.py tests/test_knowledge_recommendations.py
180 passed, 3 warnings in 17.46s

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

The 22 new tests are in `tests/test_coverage_referral_guard.py`; the other files have 158 tests.

Clean-checkout command (conda `faq`), run on the unpushed `[06]` commit:

```text
git worktree add /tmp/faq-clean-06 HEAD
cd /tmp/faq-clean-06 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-06; echo "exit $status"
1097 passed, 26 deselected, 58 warnings, 291 subtests passed in 249.48s (0:04:09)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1075 in step 05 to 1097, from the 22 new tests in `tests/test_coverage_referral_guard.py`. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. The 26 deselections are the existing integration and artifact marker exclusions. Only this log section changed after that run. The amended commit was checked again in a new clean worktree with the same command before push.

## [07] Redacted questions get uncertain production reachability and go to review

### Problem

`QueryPreparer.prepare` redacts the customer query, the rewrite and the prior turns, and `CoverageEvaluator.evaluate` runs the production baseline on `canonical_retrieval_query_redacted`. Production never saw that text. `redaction_changed_query` and `redaction_changed_rewrite` made the row `uncertain_preparation`, but `apply_result` ignored them, so a row could still report `covered_reachable` or `covered_not_reachable`. A rewrite built from redacted prior turns was not marked at all; only `history_provenance["history_redaction_changed"]` recorded it.

### Rule (approved by the owner)

All redaction stays. Running the production baseline on unredacted text in memory would change the privacy boundary and is not part of this step.

A row's production query is redaction-affected when its `uncertainty_codes` contain `redaction_changed_query`, `redaction_changed_rewrite` or `redaction_changed_history`. For such a row:

| Outcome before this step | After this step |
|---|---|
| `covered_reachable` or `covered_not_reachable` | `outcome` and `processing_status` become `needs_review`. `review_codes` gain `production_reachability_unresolved` and `redaction_changed_production_query`. `coverage_status` stays `full`; the witness, supports and `verification_result` are unchanged. |
| `possible_gap` or `possible_partial_gap` | `outcome` and `processing_status` become `needs_review`; `review_codes` gain `redaction_changed_production_query`. |
| `needs_review` | `review_codes` gain `redaction_changed_production_query`. |

In every case `production_reachability` becomes `"uncertain"`. Rows that are not redaction-affected are unchanged.

### Changes

- `knowledge_audit/preparation.py`: inside the branch that calls `rewrite_query`, `redaction_changed_history` is appended when `context.provenance["history_redaction_changed"]` is true. Rows with no prior history never run the rewrite and are not marked. The existing `code.startswith("redaction_changed")` check makes the row `uncertain_preparation`.
- `knowledge_audit/pipeline.py`: new `PRODUCTION_QUERY_REDACTION_CODES`. The table is applied at the end of `apply_result`, after both branches and after the step 06 referral rule. Codes are merged with `list(dict.fromkeys(...))`. `coverage_status`, the witness, the supports, `verification_result` and `stopping_reason` are not touched. The early returns in `evaluate` and the error paths are unchanged. The two review codes are row-level and are not in `BLOCKING_CODES`, `RESIDUAL_CODES`, `SEARCH_CODES` or `NOTE_CODES`.
- `knowledge_audit/recommendations.py`: `redaction_changed_history` also produces `context_or_redaction_unresolved` in `eligibility`.
- `knowledge_audit/settings.py`: the manifest gained `"reachability_policy_version": "redaction-reachability-1"`. Runs created before this step cannot resume (`audit_runtime_identity_drift`), so no run mixes old and new outcomes.
- `static/js/knowledge_coverage.js`: English labels for `redaction_changed_production_query`, `production_reachability_unresolved` and `redaction_changed_history`.

### Known limit: history over-marking

`history_redaction_changed` is true when any prior turn of the session was changed by redaction, while the rewrite sees at most the last three turns. A row whose redacted turn is older than the rewrite window is still marked. Over-marking sends rows to review rather than claiming certainty, which is the safe direction; it is not narrowed in this step.

### Existing tests and calibration

No existing test expectation or calibration outcome changed. `tests/test_knowledge_coverage_calibration.py` and every other existing test in the focused set passed unchanged; none of their queries, rewrites or prior turns is changed by redaction.

One existing test changed, with no change to what it expects; see the next section.

### Decision approved by the person running this step: garbage collection in a health timing test

The first two clean-checkout runs of the `[07]` commit failed with one test, `tests/test_health_checks.py::HealthTests::test_component_and_overall_deadlines` (`0.588… not less than 0.3`, then `0.527… not less than 0.3`). The test asserts that a health report with a stuck vLLM probe returns within 0.3 s of wall-clock time.

- The parent commit `83f9fc3` passed the same pytest stage in a clean worktree (1097 passed). The `[07]` code with `tests/test_coverage_redacted_reachability.py` excluded also passed (1097 passed). The test passed alone, beside the new file, and in shorter subsets.
- With Python's garbage collector disabled, the full suite including the new file passed (1110 passed, 0 failed). A `gc.callbacks` probe measured a full generation-2 collection on the suite's heap at 0.474 s and 0.490 s, with `collected=0` and `uncollectable=0`: a pure heap traversal, with no leak or slow finalizer from the new tests.
- Cause: the 13 new tests shift when the interpreter triggers that collection, and it landed inside the health test's 0.3 s window. The test was already fragile; this step exposed it.

Approved fix: `test_component_and_overall_deadlines` runs `gc.collect()` and disables the collector around the timed `report()` call only, then restores the previous state in `finally`. The 0.3 s limit and every assertion are unchanged. `utils/health_checks.py` is unchanged.

### Implementation decisions not covered by the command

These were not put to the owner; they are recorded for review.

- A `needs_review` row from full coverage with an undetermined production assessment already carries `production_reachability_unresolved`; it gains only `redaction_changed_production_query`, as the table's last row says. The merge keeps each code once.
- For gap rows, `production_reachability` was never set by `apply_result` and stayed `"unknown"`; redaction-affected gap rows now show `"uncertain"`, unaffected ones still `"unknown"`.
- The tests for `redaction_changed_rewrite` and `redaction_changed_history` replace the shared fixture's `QueryPreparer` with a subclass that appends the code to a prepared row and sets `preparation_status` to `uncertain_preparation`, as the real preparer does.
- `tests/test_coverage_redacted_reachability.py` also checks a `needs_review` row (incompatible conditions) with a redacted query, and that the manifest carries the policy version. It reuses the `seed` fixture from `tests/test_knowledge_coverage_access_jobs.py` for the export check.
- The 6 behaviour tests were checked to fail with `pipeline.py` and `preparation.py` reverted (6 failed, 7 passed), and to pass with the change.

### AGENTS.md note

This step changes only how the audit labels its rows. Retrieval, prompts, models and the chatbot are unchanged, so no retrieval or answer-quality test is required. No performance change; no benchmark was required.

### Checks

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_coverage_redacted_reachability.py tests/test_coverage_referral_guard.py tests/test_coverage_conflict_verdicts.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_calibration.py tests/test_knowledge_recommendations.py tests/test_knowledge_audit_a1.py
199 passed, 3 warnings in 18.17s

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

The 13 new tests are in `tests/test_coverage_redacted_reachability.py`; the other files have 186 tests.

Clean-checkout command (conda `faq`), run on the unpushed `[07]` commit:

```text
git worktree add /tmp/faq-clean-07 HEAD
cd /tmp/faq-clean-07 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-07; echo "exit $status"
```

Runs 1 and 2, before the health-test fix (`f76cc6a`):

```text
1 failed, 1109 passed, 26 deselected, 58 warnings, 291 subtests passed in 250.96s (0:04:10)
pytest: FAIL
exit 1

1 failed, 1109 passed, 26 deselected, 58 warnings, 291 subtests passed in 251.78s (0:04:11)
pytest: FAIL
exit 1
```

Run 3, after the approved health-test fix was amended into the `[07]` commit:

```text
1110 passed, 26 deselected, 58 warnings, 291 subtests passed in 249.91s (0:04:09)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
Offline frontend audit: PASS
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1097 in step 06 to 1110, from the 13 new tests. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. The 26 deselections are the existing integration and artifact marker exclusions. Only this log section changed after run 3. The amended commit was checked again in a new clean worktree with the same command before push.

## [08] Accept a proof only when verification agrees in both evidence orders; add a stability report

### Problem

Verification uses the same served model as evaluation, with `temperature=0` and a fixed seed, so it is a self-consistency check, not independent evidence. Row 121 was `possible_partial_gap` in A2 and `covered_reachable` in A2.2; row 518 was `covered_not_reachable` in A2.1 and a schema error in A2.2. Those runs also changed rubric and code, so batch size cannot be shown to be the cause. `CoverageEvaluator.proof_payload` always presents evidence in one canonical order, so a verifier whose answer depends on that order was never detected.

### Rule (approved by the owner)

1. **Second verification pass**, configurable with `KNOWLEDGE_COVERAGE_VERIFICATION_PASSES` (1 or 2, default 2). When the first pass accepts a proof, the same proof is verified again with `supports`, `source_evidence` and `observed_conflicts` in reversed order. Conflict IDs keep their numbers. The proof is accepted only when both passes accept it. The reversed pass runs every check of the first: the conflict-limit and token checks, aspect and conflict identity, the per-conflict verdicts from step 04, and the redaction downgrade.
   - If the reversed pass does not accept, the final verdict is the primary verdict with `verdict: "uncertain"` and the explanation "Verification changed with evidence order; review required." Its proof codes are the union of both passes' codes plus `verification_order_unstable`, and `verification_unresolved` is added once.
   - A primary verdict that is not `accepted` makes no second call.
   - `verifications` holds both passes: `origin` and `origin + ":reversed"`, with the same `bundle_id`. Only the final verdict is cached and stored in the proof, so a cache hit makes no model call.
   - With 1 pass, behaviour is the same as before this step.
2. **Read-only stability report**, `scripts/knowledge_coverage_stability_report.py`, comparing completed runs of the same rows on one snapshot that differ only in batch size. The runbook is `docs/knowledge-gap-audit/STABILITY_PROTOCOL.md`.

### Changes

- `knowledge_audit/settings.py`: `CoverageSettings.verification_passes = 2`, validated as an `int` in `{1, 2}` (`invalid_verification_passes`). Loaded with `integer("KNOWLEDGE_COVERAGE_VERIFICATION_PASSES", 2, 1, 2)` and passed by keyword. The manifest gained `verification_passes` and `verification_policy` (`order-permuted-2` or `single-pass-1`).
- `knowledge_audit/pipeline.py`: `CoverageEvaluator(verification_passes=2)`, validated like `batch_max_entries`. The body of `verify` after the cache check moved unchanged into `_verification_pass(payload, conflicts, entries) -> (verdict, codes)`; `verify` runs the primary pass, the reversed pass when the rule applies, and combines them. `verification_order_unstable` is in `BLOCKING_CODES`.
- `knowledge_audit/service.py`: `build_engine` passes `verification_passes=pinned["verification_passes"]`, the run's pinned value.
- `knowledge_audit/api.py`: `invalid_verification_passes` is in `SAFE_API_CODES`.
- `static/js/knowledge_coverage.js`: label `verification_order_unstable: 'Verification depended on evidence order'`.
- Env: `KNOWLEDGE_COVERAGE_VERIFICATION_PASSES=2` with the agreed comment, after `KNOWLEDGE_COVERAGE_MAX_ENTRY_BUDGET`, in `.env`, `env.example`, `.env.example.generated`, `Production_ENV` and `Production_ENV.example`. `.env` and `Production_ENV` are local and not staged. `scripts/validate_environment.py` has the `VariableSpec` (`int`, default 2, 1–2, Knowledge coverage audit, restart FastAPI, usage `knowledge_audit/pipeline.py CoverageEvaluator.verify`).
- `scripts/knowledge_coverage_stability_report.py`: arguments `--owner-id` (default 0), repeatable `--run-id` (at least 2) and `--row-id` (at least 1), and `--output DIR`, which must pass `private_directory`. It reads runs with `store.owned` and rows with `store.row` only. Refusals exit 2 and print only `snapshot_mismatch`, `code_version_mismatch`, `run_not_completed` or `row_missing`. It writes `stability-report.json` and `stability-report.md`, mode 0600, with batch size, outcome, coverage status, aspect counts and supported aspect IDs, support triples, `chunk_id:sentence_number` refs, verification origins and verdicts, and completion and token counts. Aspect descriptions are compared in memory and only the boolean is written. A row passes when aspect checklists, outcomes and support triples (minimum pairwise Jaccard at least 0.9) all agree. Exit 0 when every row passes, 1 otherwise.

Runs created before this step cannot resume (`audit_runtime_identity_drift`), because the manifest gained `verification_passes` and `verification_policy`. A run pinned at 2 passes also refuses to resume under 1, and the reverse.

### Existing tests and calibration

No outcome, coverage status or calibration result changed. `tests/test_knowledge_coverage_calibration.py` and the other focused files passed with no change to an expected label. Three tests count verification calls and now see exactly one more call per accepted proof, and one test counts the coverage CLIs:

| Test | Before | After | Why |
|---|---|---|---|
| `tests/test_knowledge_coverage_pipeline.py::test_exact_and_paraphrase_verified_and_reachable` (both parameters) | 1 | 2 | One accepted production proof, verified in both orders. |
| `tests/test_coverage_conflict_verdicts.py::test_assessed_conflict_lets_the_proof_stand` (both parameters) | 2 | 4 | Two accepted proofs (`initial:2` and `conflict_reverification`), each verified in both orders. |
| `tests/test_knowledge_execution_recovery.py::test_completed_boundary_survives_process_death_without_repeat` (both parameters) | 1 verification | 2 verification | The process is killed after a validated batch or verification and the run is recovered. The accepted proof is verified in both orders, and neither call is repeated after recovery; `scope`, `aspects` and `batch` stay at 1. |
| `tests/test_coverage_deployment_gate.py::test_cli_gate_coverage` | 9 scripts | 10 scripts | The new `scripts/knowledge_coverage_stability_report.py`. The test's rule that every coverage CLI except cleanup calls `require_coverage_enabled` after `load_dotenv` now covers it too. |

No scripted fake model ran out of responses; the shared `LabeledModel` answers every verification call.

### Cost

- One extra verification completion per accepted proof. Proofs that the first pass does not accept add nothing. A row whose view gains new conflicts can have more than one accepted proof, and each one is verified twice.
- The reversed pass also makes one token-count request (`AuditModel.fits`), which is not a completion.
- The extra prompt is the same size as the first verification prompt, with the same content in a different order. On the staging runs recorded before this step (6 runs, 8 verification calls; token counts only were read), a verification call used 1,270–2,969 prompt tokens (median 2,010.5) and at most 152 completion tokens (median 130). Step 10 uses these numbers for sizing.

### Implementation decisions not covered by the command

These were not put to the owner; they are recorded for review.

- `integer(..., 1, 2)` raises `invalid_coverage_integer` for an out-of-range value, while the test plan requires `KNOWLEDGE_COVERAGE_VERIFICATION_PASSES=3` to raise `invalid_verification_passes`. The loader keeps the specified `integer` call and re-raises its error as `invalid_verification_passes`, so a malformed value (`two`) also gives that code.
- Each pass's record is appended to `verifications` as soon as that pass returns, so if the reversed pass raises a validation error, the row (an error) still shows the primary record.
- When the reversed pass rejects, `verification_result` of a row that is not covered is `rejected`, by the existing rule that any rejected verification sets it.
- Stability report: a missing, foreign or unreadable run gives `run_not_completed`; a row not selected in a run, or still pending, gives `row_missing`. The checklist comparison uses `(aspect_id, description)` pairs. Two empty support sets have Jaccard 1.0. Prompt and completion token sums are reported separately. Repeated IDs are counted once. An existing report file is refused with `stability_report_exists`, and any unexpected error prints only `stability_report_failed`. It is gated like every coverage CLI except cleanup: `main` loads `.env` and calls `require_coverage_enabled` before opening the store, as `test_cli_gate_coverage` requires. The tests pass a temporary store to `main` instead, which skips that loading so the real `.env` never enters the test process. Opening the store takes the shared retention lock file, as every store reader does.
- `tests/test_coverage_order_verification.py` tests `build_engine` by replacing its service collaborators with fakes and stopping at the `CoverageEvaluator` construction, so no network or model is used. It also checks that a run without a pinned pass count (created before this step) cannot resume.
- `scripts/validate_environment.py --env-file Production_ENV --mode production` exits 2 with the same 6 critical placeholder findings as in steps 03a and 07; this step adds none.

### AGENTS.md note

This step changes the audit's judgement and cost: a proof whose acceptance depends on evidence order now goes to review, and each accepted proof costs one more verification call. It does not change retrieval, prompts, models or the chatbot. No performance change to the chatbot; no benchmark was required. The live L2 experiment is out of scope and is run by the operator on staging using the runbook.

### Checks

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_coverage_order_verification.py tests/test_coverage_stability_report.py tests/test_coverage_redacted_reachability.py tests/test_coverage_referral_guard.py tests/test_coverage_conflict_verdicts.py tests/test_coverage_depth_settings.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_calibration.py tests/test_knowledge_recommendations.py tests/test_validate_environment.py
194 passed, 3 warnings in 18.22s

conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file .env --mode staging | tail -1
- [INFORMATIONAL] REQUEST_CONCURRENCY_LIMIT, ... QDRANT_CONCURRENCY: overlap (concurrency and pools): Each limit applies at a different queue or resource boundary.
Summary line: Summary: 0 critical, 27 warning, 4 informational; validator exit 0

conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file Production_ENV --mode production | tail -1
- [INFORMATIONAL] REQUEST_CONCURRENCY_LIMIT, ... QDRANT_CONCURRENCY: overlap (concurrency and pools): Each limit applies at a different queue or resource boundary.
Summary line: Summary: 6 critical, 24 warning, 4 informational; validator exit 2 (pre-existing placeholders)

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

`tail -1` prints the validator's last item, an informational line; the `Summary` line was read from the same output with `grep '^Summary'`. Both reports list `KNOWLEDGE_COVERAGE_VERIFICATION_PASSES` as set, with no finding. The 24 new tests are 14 in `tests/test_coverage_order_verification.py` and 10 in `tests/test_coverage_stability_report.py`.

Clean-checkout command (conda `faq`), run on the unpushed `[08]` commit:

```text
git worktree add /tmp/faq-clean-08 HEAD
cd /tmp/faq-clean-08 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-08; echo "exit $status"
```

Run 1, on the first `[08]` commit:

```text
3 failed, 1131 passed, 26 deselected, 58 warnings, 291 subtests passed in 258.01s (0:04:18)
pytest: FAIL
exit 1
```

The three failures were `tests/test_knowledge_execution_recovery.py::test_completed_boundary_survives_process_death_without_repeat[batch]` and `[verification]` (verification calls counted 2, expected 1) and `tests/test_coverage_deployment_gate.py::test_cli_gate_coverage` (10 coverage scripts, expected 9; the new script was not gated). The fixes are in "Existing tests and calibration" and "Implementation decisions" above; the report script now calls `require_coverage_enabled`. They were amended into the `[08]` commit, and the focused set above was run again after them.

Run 2, on the amended `[08]` commit:

```text
1134 passed, 26 deselected, 58 warnings, 291 subtests passed in 257.04s (0:04:17)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
Offline frontend audit: PASS
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1110 in step 07 to 1134, from the 24 new tests. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. The 26 deselections are the existing integration and artifact marker exclusions. Only this log section changed after run 2. The amended commit was checked again in a new clean worktree with the same command before push.

## [09] Refused connections and HTTP rejections no longer pause audit runs; rewrite fallbacks are reusable

### Part A: fix from verifying step 08

`scripts/knowledge_coverage_stability_report.py` refused the experiment it was built for. `load_runs` required identical `versions`, but a started run's `versions.runtime_configuration.audit_runtime_settings` is `settings.manifest()`, which holds `batch_entries` and `batch_max_entries`. Two real runs differing only in batch size always exited with `code_version_mismatch`; the step 08 tests missed it because their synthetic `versions` had no `runtime_configuration`.

Fix: the new `comparable_versions(meta)` deep-copies `versions` and removes `BATCH_KEYS` from `runtime_configuration.audit_runtime_settings` when that path exists. `load_runs` compares those copies. The stored meta is never changed, and every other field must still match. Two new tests in `tests/test_coverage_stability_report.py` cover it: runs differing only in the two batch keys produce a report (and the stored meta keeps its batch keys), and runs whose `audit_runtime_settings` also differ in `initial_entries` exit 2 with `code_version_mismatch`. The first test fails on `165f354` and passes after the fix.

### Problems

- **F8a (Medium).** `Budget.dispatch` marked an allowance `dispatched` before the call and, on any exception, called `finish` with no usage, which set `state='unknown'` and `pause_reason='unknown_remote_completion'`. `AuditModel._call_once` likewise left `dispatched=True` and `server_completion_state='unknown'`. So a refused TCP connection, which provably sent nothing, and an HTTP 500, where the server answered without a completion, paused the whole run until an operator chose retry or skip.
- **F16b (Low).** `RowJournal.invoke` recorded a preparation whose rewrite fell back as `preparation_unobserved`, which is in `UNKNOWN`. A finished row looked as if it had unknown outstanding work, and its preparation was never reused from the checkpoint. The rewrite's own completion is already in the ledger as `history_rewrite`.

### Rule (approved by the owner)

| What happened | Ledger state | Charge | Failure streak | Pauses the run |
|---|---|---|---|---|
| Connection never made: `httpx.ConnectError`, `httpx.ConnectTimeout` or `httpx.PoolTimeout` anywhere in the cause chain | `not_sent` | refunded | +1 | no |
| Server answered with an error status: `httpx.HTTPStatusError` or `openai.APIStatusError` anywhere in the cause chain | `failed_known` | reservation kept | +1 | no |
| Anything else after sending: read or write timeouts, `ReadError`, `RemoteProtocolError`, cancellation, `OperationalPause` | `unknown` | as today | as today | yes, as today |

The consecutive-failure limit (`KNOWLEDGE_COVERAGE_MAX_CONSECUTIVE_FAILURES`, default 3) still stops a run when the server is down, with `budget_failures`. Rewrite fallbacks become validated results. There are no automatic retries: `network_retries: 0` stays.

### Changes

- `knowledge_audit/failures.py`: `send_state(error)` walks `causes(error)` and returns `not_sent`, `server_rejected` or `unknown` as in the table; `asyncio.CancelledError` or `OperationalPause` at the top is always `unknown`. `VERSION = "audit-failures-2"`.
- `knowledge_audit/operations.py`: `Budget.not_sent(identity, error)` sets `state='not_sent'`, `known_tokens=0`, the safe `error_category` and `duration_ms`, refunds `charged_tokens` from `tokens_charged`, subtracts 1 from `completion_attempts`, adds 1 to the `history_rewrite` or `model` streak and never sets `pause_reason`. `Budget.server_rejected(identity, error)` sets `state='failed_known'`, `known_tokens=None`, keeps the charge, adds 1 to the streak and sets `pause_reason='budget_tokens'` only when `tokens_charged` exceeds the allowance. `dispatch` picks one of them or `finish` by `send_state` and always re-raises. `summary` gained `not_sent_completions` and `server_rejected_completions` (`failed_known` with `known_tokens is None`); `dispatched_completions` excludes `not_sent`. `_reason`, `unknown_row_ids`, `acknowledge_unknown` and the `unknown_*` counts keep using `{'reserved','dispatched','unknown'}`, so `not_sent` is excluded by construction (tested). `VERSION = 'audit-operations-2'`.
- `knowledge_audit/model.py`: in `_call_once`'s `except Exception` branch, `not_sent` sets `dispatched=False` and `server_completion_state='not_dispatched'` (journal: `failed_before_dispatch`); `server_rejected` sets `server_completion_state='rejected_by_server'` and keeps `dispatched=True` (journal: `response_received`). `budget.model_result` still runs only for `response_received`, so one failure adds exactly 1 to the streak (tested with an HTTP 500).
- `knowledge_audit/recovery.py`: `invoke` records `preparation_unobserved` only when `preparation_status == 'failed'`. A fallback rewrite is stored as `validated` with `result` and `result_sha256`; the result keeps `rewrite_status="fallback"` and the row keeps `preparation_status="uncertain_preparation"`. `VERSION = "audit-boundaries-2"`.
- `knowledge_audit/settings.py`: manifest `failure_policy`, `operational_policy` and `checkpoint_policy` set to the three new versions.
- `static/js/knowledge_coverage.js`: the budget panel, which lists ledger counts, shows `not_sent_completions` as "Not sent (connection refused)" and `server_rejected_completions` as "Rejected by server", after the unknown reservations.
- `knowledge_audit/jobs.py`: not changed. The recovery prompt and `unknown_completion_count` count journal records in `UNKNOWN` and ledger requests in `{'reserved','dispatched','unknown'}`; neither includes `not_sent`, `failed_known`, `failed_before_dispatch` or `response_received`. The run's recovery text in `knowledge_coverage.js` uses those same counts.
- New `tests/test_audit_send_state.py`: `send_state` cases; the reproduction (refused connection refunds, does not pause, is not among unknown rows or acknowledged; three refusals then `budget_failures`); server rejection (charge kept, no pause, next dispatch proceeds; over-allowance gives only `budget_tokens`); read timeout still pauses as unknown; model metrics and journal states for `ConnectError` and HTTP 500 through the real `AuditModel` with the mocked OpenAI transport; F16b checkpoint reuse and `failed` still `preparation_unobserved`.

Runs and journals created before this step cannot resume: the ledger refuses a `budget.json` of another version (`budget_identity_mismatch`), the journal binding includes the checkpoint policy, and the manifest's three policy versions changed (`audit_runtime_identity_drift`).

### Existing tests changed

| Test | Old expectation | New expectation | Why |
|---|---|---|---|
| `tests/test_knowledge_coverage_reliability.py::test_translated_sdk_causes_remain_specific_without_network_retries`, parameters `ConnectTimeout`, `PoolTimeout`, `ConnectError` | `metric['dispatched'] is True` and `metric['server_completion_state']=='unknown'` | `metric['dispatched'] is False` and `metric['server_completion_state']=='not_dispatched'` | It encoded F8a: a connection that was never made counted as unknown remote work. The `ReadTimeout`, `WriteTimeout` and `RemoteProtocolError` parameters keep `True` and `unknown`. The failure codes, one send, no retry and limiter release are unchanged for all six. |

No other existing test changed. `tests/test_knowledge_execution_recovery.py` and `tests/test_knowledge_operations.py` passed unchanged.

### Decisions approved by the owner (step 09b)

1. **Token-count errors.** `rejected_by_server` is used only when a completion was actually sent. An error status from the token-count request stays `not_dispatched`, as before.
2. **Old version strings.** The hard-coded copies now use the module constants: `operational_policy` in `knowledge_audit/execution.py` (new run meta) and `knowledge_audit/recommendation_store.py` uses `VERSION` from `knowledge_audit/operations.py`; the export manifest's `checkpoint_policy` in `knowledge_audit/export.py` uses `VERSION` from `knowledge_audit/recovery.py`; the two synthetic `failure_diagnostics` entries in `knowledge_audit/pipeline.py` use `VERSION` from `knowledge_audit/failures.py`. Nothing else changed in those four files. No existing test asserted an old string: `tests/test_knowledge_coverage_reliability.py::test_failure_categories_survive_restricted_immutable_csv_projection` stores `'audit-failures-1'` as synthetic historical row data and checks only that the export carries it through unchanged, so it was left as is.

### Implementation decisions not covered by the command

These were not put to the owner; they are recorded for review.

- `finish`, `not_sent` and `server_rejected` all ignore a request that is already terminal (`returned`, `failed_known`, `unknown`, `not_sent`), so a repeated call never refunds or counts twice.
- `send_state` imports `OperationalPause` inside the function, as `recovery.py` does, because `operations.py` imports `failures.py`.

### AGENTS.md note

This changes only how the audit's ledger classifies failed requests. It does not change retrieval, prompts, models or the chatbot. No performance change to the chatbot; no benchmark was required.

### Checks

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_audit_send_state.py tests/test_coverage_stability_report.py tests/test_knowledge_execution_recovery.py tests/test_knowledge_operations.py tests/test_knowledge_coverage_access_jobs.py tests/test_coverage_order_verification.py tests/test_knowledge_coverage_pipeline.py
166 passed, 9 warnings in 197.22s (0:03:17)

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

The changed existing test file was also run alone: `tests/test_knowledge_coverage_reliability.py`, 33 passed, 3 warnings in 13.69s. The step 09b re-run of the focused set, with the version-string change, is recorded below. The new tests are 20 in `tests/test_audit_send_state.py` and 2 in `tests/test_coverage_stability_report.py`.

Clean-checkout command (conda `faq`), run on the unpushed `[09]` commit. `/tmp/faq-a21-browser-node` exists, so the browser stage ran with `REQUIRE_BROWSER=1`:

```text
git worktree add /tmp/faq-clean-09 HEAD
cd /tmp/faq-clean-09 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-09; echo "exit $status"
```

Run 1, on the first `[09]` commit:

```text
1156 passed, 26 deselected, 58 warnings, 291 subtests passed in 251.06s (0:04:11)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
Offline frontend audit: PASS
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1134 in step 08 to 1156, from the 22 new tests. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. The 26 deselections are the existing integration and artifact marker exclusions.

Run 2, on the `[09]` commit amended with run 1's log section only:

```text
Timeout (0:02:00)!
Thread ... (most recent call first):
  File ".../json/decoder.py", line 354 in raw_decode
timeout: the monitored command dumped core
scripts/run_offline_tests.sh: line 20: ... Segmentation fault      timeout 1800 python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q
pytest: FAIL
exit 139
```

Diagnosis: CPU starvation, not a regression. The test running at the crash (number 641 in collection order) was `tests/test_knowledge_execution_recovery.py::test_full_918_selection_idempotency_chronology_export_and_mock_run`, which exceeded `faulthandler_timeout = 120` in `pytest.ini`; the process then crashed while dumping tracebacks. Run alone on `[09]` it took 130.99 s, and on the parent `165f354` it hit the same 120 s limit and crashed the same way. A crypto-mining process on the dev host was using about 16 cores (load average about 17). The dev host's miner was removed in step 09b before the next run.

Step 09b, after the miner was removed and with the two approved decisions, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_audit_send_state.py tests/test_coverage_stability_report.py tests/test_knowledge_execution_recovery.py tests/test_knowledge_operations.py tests/test_knowledge_coverage_access_jobs.py tests/test_coverage_order_verification.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_reliability.py
199 passed, 9 warnings in 181.39s (0:03:01)

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

After this log section was written, the amended commit was checked in a new clean worktree with the same clean-checkout command, at normal load, before push.

## [10] Full and subset runs show a server-computed cost estimate and need explicit acceptance when it exceeds the limits

### Problem (F8b, Medium)

A full run started with no estimate of its cost, and the default limits (200 completions, 1,000,000 tokens, 3,600 seconds in `Limits`) stop it after one or two hard questions. In the A2 pilot, row 121 alone used 64 completions, 175,552 prompt tokens and 259 seconds, and step 08 added a second verification call per accepted proof. `create_run` required only `budget_acknowledged=True` for `full_input`, so the user confirmed "finite limits" without seeing how far they were from what the run needs.

### Rule (approved by the owner)

Before a `full_input` or `subset` run starts, the server computes an estimate from completed reference runs on the same snapshot, code and audit settings, and the page shows it next to the limits.

- **No reference runs:** the user must explicitly acknowledge an unsized run (`sizing_acknowledged`), or the start returns 422 "No reference runs on this snapshot; run a pilot first or acknowledge an unsized run".
- **Expected cost over any limit:** the user must explicitly accept that the run will pause partway (`accept_partial_run`), or the start returns 422 "Estimated cost exceeds run limits; raise limits or accept a partial run".
- **Pilot runs** are unchanged and are not sized.

The estimate is computed on the server at start; a client value is never trusted. What was shown is stored as a top-level `sizing` key in the run meta (`version`, `estimate`, `comparison`, `reference`, `sizing_acknowledged`, `accept_partial_run`), never in `settings`, which the drift check and the stability report compare.

### What counts as the same setup

`knowledge_audit/sizing.py` `comparable(meta_or_config)`:

- **Settings:** the run's `settings` without `operational_limits` (limits only cap a run), `selection_method` (the only setting that legitimately differs between a pilot and a full run) and `sizing`.
- **Versions:** only `prompts`, `code` and `code_id`, the keys `versions()` returns for a new run. A started run also gains `serving` and `runtime_configuration`, which a new run does not have yet; this is the trap fixed in step 09 Part A.

A reference run must also be `completed` and have the same `snapshot_id` and `dataset_id`, and be owned by the same user.

### Changes

- New `knowledge_audit/sizing.py` (`VERSION = "coverage-sizing-1"`). It reads only budget ledgers, row outcomes and row durations, never a text field, and holds one shared artifact lock for the read.
  - `reference_stats(store, owner, snapshot_id, dataset_id, settings, versions)`: for each finished selected row of each reference run, the outcome class (`covered`: `covered_reachable`, `covered_not_reachable`; `non_covered`: `possible_gap`, `possible_partial_gap`, `needs_review`; `other`: everything else), completions (ledger requests with that `source_row_id` whose state is not `not_sent`), tokens (their `charged_tokens`) and seconds (`duration_ms / 1000`). Pending rows are skipped. Per class it returns `rows`, `share`, and the total, mean and nearest-rank 90th percentile (position `ceil(0.9 * n)`) of each measure, plus `reference_run_ids` and `reference_row_count`. Fewer than 5 rows gives `None`.
  - `estimate(row_count, stats, *, non_covered_share=None)`: `expected = row_count * sum(share_c * mean_c)` and `high = row_count * sum(share_c * p90_c)`, both rounded up. An override replaces the non-covered share and rescales the other classes in their ratio.
  - `compare(estimate, limits)`: limit, expected, high, `fits_expected` and `fits_high` for completions, tokens and seconds, and `fits` when every `fits_expected` holds.
- `knowledge_audit/api.py`: `RunScope` holds the fields shared by the estimate and the start; `RunPayload` adds `sizing_acknowledged` and `accept_partial_run`, `EstimatePayload` adds `non_covered_share` (0 to 1). `run_config` builds the config and effective limits for both routes, so they cannot drift apart. `sizing_view` counts the rows (for `full_input`, `execution.available_row_ids`, the helper `execution.create_run` now uses) and computes the estimate. New `POST /api/knowledge-coverage/runs/estimate` (`coverage_run_start` and `kb_read`) returns `{"row_count", "estimate", "comparison", "reference": {"run_ids", "row_count"}, "sizing_version"}`. `create_run` keeps the `budget_acknowledged` check, then applies the rule above for `full_input` and `subset`.
- `knowledge_audit/execution.py`, `knowledge_audit/store.py`: `create_run(..., sizing=None)` stores `meta["sizing"]` when given.
- `web_permissions.py`: `("POST", r"/api/knowledge-coverage/runs/estimate", "coverage_run_start")` next to the run-creation route. The patterns are matched with `re.fullmatch`, so `/api/knowledge-coverage/runs` never matched `/runs/estimate` and no anchoring was needed.
- `templates/knowledge_coverage.html`, `static/js/knowledge_coverage.js`: for `full_input` and `subset`, the page requests the estimate whenever the dataset, snapshot, datasources, questions, mode, entry budget or limits change, and shows a table (completions, tokens, hours; limit, expected, high) after the limits section. Cells over the limit carry "over limit" in the existing error badge. With no estimate it shows "No reference runs on this snapshot. Run a pilot first, or confirm an unsized run." and the checkbox "I confirm an unsized run."; over the limits it shows "I accept that this run will pause before finishing". Start stays disabled until the estimate for the current selection has loaded and the required checkbox is ticked.
- New `docs/knowledge-gap-audit/FULL_RUN_SIZING.md`: pilot first (with `--owner-id` set to the web user ID, because references are per owner), reading the estimate, raising the limits within the validated maxima, and very large inputs needing the step 11 continuation.

Runs created before this step have no `sizing` key; nothing reads it except the record itself, so they are unaffected.

### Existing tests changed

| Test | Old | New | Why |
|---|---|---|---|
| `tests/test_knowledge_execution_recovery.py::test_full_mode_api_idempotency_csrf_owner_and_revoked_grant` | `full_input` payload with `budget_acknowledged: True` gives 202 | the same payload with `sizing_acknowledged: True` gives 202 | The test store has no completed reference run, so an unsized run must now be acknowledged. Every assertion is unchanged. |
| `tests/test_web_permissions.py` route inventory `EXPECTED` | no estimate route | `('POST', '/api/knowledge-coverage/runs/estimate'): 'coverage_run_start'` | The inventory lists every browser route; the role matrix now also covers the new route. |
| `tests/knowledge_operations.browser.cjs` | ticks the full-input limit confirmation, then starts | also waits for and ticks "I confirm an unsized run" before starting | No completed reference run exists in that fixture. Every check is unchanged. |
| `tests/knowledge_execution.browser.cjs` | full-input and subset starts | both tick "I confirm an unsized run" (the full-input step first checks Start is disabled); one new step, below | No completed reference run exists before the subset finishes. |
| `tests/knowledge_execution_browser_app.py` | the mocked model made no ledger entry | each mocked call is charged in the ledger (`audit_dispatch`, 10 prompt and 10 output tokens), as `tests/knowledge_operations_browser_app.py` already does | So the completed 9-row subset is a sizing reference with nonzero completions. |

New browser check, after the 9-row subset finishes: switching to full input shows "from 9 reference rows in 1 completed runs", a three-row table with at least one cell over the limit, and Start stays disabled after the limit confirmation until "I accept that this run will pause before finishing" is ticked. It does not start the run.

New tests: 11 in `tests/test_coverage_sizing.py` and 1 in `tests/knowledge_coverage.frontend.test.cjs`.

### Implementation decisions not covered by the command

These were not put to the owner; they are recorded for review.

- `VERSION_KEYS` is a constant (`prompts`, `code`, `code_id`); a test checks it equals the keys of `versions()`, so a new version key cannot be silently ignored.
- Only a reference run's `selected_row_ids` are read: rows it did not select were never evaluated.
- Arithmetic uses exact fractions, so rounding up never adds one because of float error. Means and shares are returned as numbers; a row without `duration_ms` counts 0 seconds.
- An override that gives a positive share to a class with no reference rows (for example `non_covered_share=0.5` when every reference row is non-covered) is refused with `sizing_class_without_reference` (409 through `safe_call`, as other audit codes), rather than estimating that class at zero.
- `run_config` keeps the old order of checks: datasource, then the full-input limit confirmation, then the limit ceiling.
- The run's idempotency identity does not include `sizing`, so a retried start with the same key returns the original run with the sizing recorded when it was created.
- The page re-requests the estimate 250 ms after the last change, and a new estimate clears both sizing checkboxes, because the user confirmed a different estimate. Datasource checkboxes now refresh the selection summary and the estimate; before, they had no listener. The sizing block sits after the limits `<details>`, so a subset run, which needs no limit confirmation, shows it without opening that section. No CSS changed: the block reuses `coverage-settings`, `coverage-check` and the error `coverage-badge`.

### AGENTS.md note

This adds a pre-start estimate and a confirmation. It does not change how rows are evaluated, retrieval, prompts, models or the chatbot. The benchmark below shows that per-row work is unchanged: the estimate is one API call before a run starts.

### Checks

`scripts/benchmark_coverage_budgets.py` (mocked 918-row input, 12 boundaries per iteration, file I/O only):

```text
before, on 78832bb:
{"boundaries_per_iteration": 12, "checkpoint_only": {"measurements_ms": [498.484, 480.258, 445.846], "median_ms": 480.258}, "checkpoint_with_allowance": {"measurements_ms": [683.969, 703.945, 740.557], "median_ms": 703.945}, "input_rows": 918, "iterations": 3, "live_dispatches": 0, "scope": "mocked_file_io_no_service_throughput", "version": "a62-file-io-1"}
after:
{"boundaries_per_iteration": 12, "checkpoint_only": {"measurements_ms": [503.639, 418.203, 421.93], "median_ms": 421.93}, "checkpoint_with_allowance": {"measurements_ms": [698.978, 753.576, 602.01], "median_ms": 698.978}, "input_rows": 918, "iterations": 3, "live_dispatches": 0, "scope": "mocked_file_io_no_service_throughput", "version": "a62-file-io-1"}
```

Medians: checkpoint only 480.258 ms before, 421.930 ms after; checkpoint with allowance 703.945 ms before, 698.978 ms after. The timed section (ledger reservations, row saves and progress reads) is not changed by this step; only the untimed `create_run` setup is. The difference is run-to-run noise, and there is no per-row cost.

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_coverage_sizing.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_execution_recovery.py tests/test_knowledge_operations.py tests/test_coverage_deployment_gate.py tests/test_coverage_stability_report.py
145 passed, 9 warnings in 189.31s (0:03:09)

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

`tests/test_web_permissions.py` (24 passed), the three node frontend harnesses (6, 6 and 5 passed), the offline frontend audit (PASS) and the execution and operations browser harnesses were also run before commit.

The full offline pytest suite was also run in the main checkout before commit: 1167 passed, 26 deselected, 58 warnings, 291 subtests passed in 250.18s (0:04:10).

Clean-checkout command (conda `faq`), run on the unpushed `[10]` commit. `/tmp/faq-a21-browser-node` exists, so the browser stage ran with `REQUIRE_BROWSER=1`. `uptime` before the run showed a load average of 1.20, the host's normal level:

```text
uptime
git worktree add /tmp/faq-clean-10 HEAD
cd /tmp/faq-clean-10 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-10; echo "exit $status"
```

Run 1, on the first `[10]` commit:

```text
1167 passed, 26 deselected, 58 warnings, 291 subtests passed in 245.71s (0:04:05)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
Offline frontend audit: PASS
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1156 in step 09 to 1167, from the 11 new tests in `tests/test_coverage_sizing.py`. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. Only this log section changed after run 1. The amended commit was checked again in a new clean worktree with the same command before push.

## [11] Continue a paused run's unfinished rows, export the whole chain, and require idempotency keys

### Problem

- **F8c (Medium):** a paused run could not practically be finished. `RowJournal.binding` (`knowledge_audit/recovery.py`) includes the run ID, so a new run cannot reuse another run's checkpoints; nothing created a run from the rows a previous run did not finish (continuing a 918-row run paused at row 40 meant ticking about 880 boxes in a subset run); each run exported on its own, with no single CSV for the whole input; and `failed` is in `TERMINAL` although it is retryable.
- **F15 (Low):** `create_run` used `payload.idempotency_key or canonical_sha256(payload.model_dump())`. A script resending the same payload after a run was exhausted got the old run back, and after a code or settings change the same payload failed with `idempotency_request_conflict`. The page always sent a random key and was not affected.

### Rule (approved by the owner)

- **Continue:** a "continue" action creates a new `subset` run from the unfinished rows of a source run, on the same dataset, snapshot and documents.
- **Chains:** runs linked this way form a chain, and one immutable, hash-bound export covers the whole input of the chain.
- **Idempotency:** every run-creating request carries an explicit idempotency key.
- **No cross-run checkpoint reuse:** `RowJournal.binding` is unchanged. A continuation selects only unfinished rows, so it needs no checkpoint reuse.

### Which rows a continuation selects

`knowledge_audit/execution.py` `continuation_rows(store, owner, source_run_id, *, include_needs_review=False)` returns the source's `selected_row_ids`, in that order, whose progress-index summary is unfinished (`unfinished(row, include_needs_review)`):

- `processing_status` is not in `TERMINAL` (`pending`, `running`, `interrupted`, `cancelled`); or
- `processing_status == "failed"`; or
- `unknown_completion_count > 0` and the status is not `completed`; or
- `include_needs_review` is set and the status is `needs_review`.

`completed`, `excluded`, `invalid_input` and `needs_context` (the new `FINAL` set) are never selected, whatever their unknown-completion count. In practice the unknown-completion clause therefore adds only `needs_review` rows with an unknown remote completion.

- **`needs_context` is final:** `CoverageEvaluator.evaluate` already retries such a row once with `context_reviewed=True`, so running it again gives the same result.
- **`needs_review` only on request:** running these again is only useful after something has changed, such as the KB or the limits.

`continuation_counts` gives the preview: `unfinished` (the default selection), `needs_review` (rows the checkbox would add), and `failed` and `unknown` within the default selection. Both read the progress index under the run's metadata lock, never row text.

### What "same setup" and `merge_identity` compare

New `knowledge_audit/chain_export.py`:

- **`same_setup(source, config, versions)`**, for a new continuation: `sizing.comparable(source) == sizing.comparable({"settings": config, "versions": versions()})`, else `AuditError("continuation_identity_drift")` (409). That is the source's settings without `operational_limits`, `selection_method` and `sizing`, and only the `prompts`, `code` and `code_id` versions, against the config the server builds now. `versions` are not compared directly: a started run also holds `serving` and `runtime_configuration`, which a new run does not have yet (the step 09 Part A trap).
- **`merge_identity(meta)`**, for the chain export: `sizing.comparable(meta)`, plus `versions["serving"]`, plus `versions["runtime_configuration"]` without `model_limit` (the row count), `model_sample_rule` (see decisions) and `audit_runtime_settings.operational_limits`. A run that never started has neither key and contributes `None` for both. Every run of a chain must have an equal `merge_identity`, `dataset_id`, `snapshot_id` and `row_ids`, else `chain_identity_drift`. So runs that differ only in row count or limits merge, and runs that differ in code, settings or serving model do not.

### Changes

- **F15, `knowledge_audit/api.py`:** `RunPayload.idempotency_key` is required (same pattern, `IDEMPOTENCY_KEY`) and `create_run` passes it directly; the unused `canonical_sha256` import is removed. The new `ContinuationPayload` also requires a key. A search of `knowledge_audit/` found no other endpoint with the payload-hash fallback: recommendation drafts (`recommendation_api.create`) take a fresh random ID per request and have no idempotency key, and calibrations have no HTTP creation endpoint. Both are unchanged.
- **`knowledge_audit/execution.py`, `knowledge_audit/store.py`:** `create_run(..., chain=None)`. With `chain`, `continues_run_id` and `chain_root_run_id` go into the top-level meta (never `settings`), the chain is part of the creation request identity, and a second continuation of the same source is refused with `run_already_continued` inside the per-owner creation lock (see decisions). Without `chain`, run creation is unchanged.
- **`knowledge_audit/jobs.py`:** `CoverageJobs.idle(rid, owner)` settles a stale state with `inspect_state`, then holds the run's lease, as `recover` (the retry endpoint) does, and refuses with `run_active` when the lease is held, the task is active or the state is `queued`/`running`. The continuation is created while this lease is held, so the source cannot be resumed meanwhile.
- **`knowledge_audit/api.py`, routes:**
  - `POST /api/knowledge-coverage/runs/{run_id}/continuations` (`coverage_run_start`): body `{"idempotency_key", "include_needs_review": false, "operational_limits": null, "sizing_acknowledged": false, "accept_partial_run": false}`. Source owned by the user (else 404) and idle (else 409 `run_active`); rows from `continuation_rows`; none gives 422 "No unfinished rows"; more than `max_run_rows` takes the first `max_run_rows` and returns `"truncated": true` with `remaining_rows`. The run is built with the step 10 `run_config` from the source's `dataset_id`, `snapshot_id`, `settings["documents"]` and `settings["entry_budget"]`, `execution_mode="subset"`, then `same_setup`, then the step 10 sizing rules through a new shared `sized(...)` helper (the old `create_run` block, moved unchanged) with `sizing` recorded as in step 10.
  - `GET .../continuation-preview` (`coverage_results_view`): `{"unfinished", "needs_review", "failed", "unknown"}`, counts only.
  - `POST .../continuation-estimate` (`coverage_run_start`, see decisions): the `runs/estimate` shape for the continuation's selection and limits, plus `truncated` and `remaining_rows`.
  - `POST .../chain-export-revisions`, `GET .../chain-export`, `GET .../chain-export-manifest` (`coverage_export_download`, as the run export), for any run of the chain.
  - `safe_meta` adds `continues_run_id` and `chain_root_run_id`. New allowlisted codes: `run_active`, `run_already_continued`, `continuation_identity_drift`, `ambiguous_run_chain`, `chain_identity_drift`, `run_chain_changed`.
- **Chain export, `knowledge_audit/chain_export.py`:**
  - `chain(store, owner, run_id)`: follows `continues_run_id` to the root, collects the root and every run with that `chain_root_run_id`, root first then creation order. Two runs continuing one source, a cycle or a link outside the chain give `ambiguous_run_chain`.
  - `merged_rows(store, owner, runs)`: the root's `row_ids`; each row from the latest run that finished it (status in `TERMINAL` and not `failed`), else its latest copy; plus a `provenance` map. Only runs that selected the row are considered when any did (see decisions).
  - `export_revision(...)`: holds every chain run's metadata lock (sorted, so no lock-order cycle), re-reads the chain (a run that joined meanwhile gives `run_chain_changed`), captures each run's rows and budget summary, and writes `runs/<root>/chain-exports/{evidence|restricted}/rev_<32 hex>/{coverage.csv,manifest.json}` plus `latest.json`. Reads verify the CSV hash, projection and version, exactly like run export revisions.
  - The CSV is `coverage_export(...)` over the merged rows, so the BOM, quoting, formula protection and restricted fields are the run export's. The meta is the latest run's, with the root's `run_id`, `execution_mode` and `row_ids` and the union of selected rows. One column is added, `source_run_id`; each row's `operational_budget` and `pause_reason` come from its source run.
  - The manifest adds `chain_export_version: "coverage-chain-export-1"`, `chain_root_run_id`, `chain_run_ids`, `chain_results_sha256` (each run's `canonical_sha256` of its row copies), `chain_runs` (state, mode, selected count, identities and budget per run), `merge_identity_sha256` and `source_run_row_counts`.
- **`knowledge_audit/export.py`:** `coverage_export(..., sources=None)`. With `sources` (row ID → source run meta) it adds `source_run_id` and takes the budget columns per row; without it the output is byte-for-byte unchanged. `source_run_id` joins the opaque reference keys that redaction leaves alone.
- **Retention, `knowledge_audit/retention.py`:** `chain-exports/` is a known run layout. The export lives with the root run and its manifest names every chain run, so a retained root keeps every run its chain export references. Every continuation's meta names the root, so a retained continuation keeps the root.
- **`web_permissions.py`:** the six routes above. `tests/test_web_permissions.py` route inventory: the same six entries.
- **Page (`templates/knowledge_coverage.html`, `static/js/knowledge_coverage.js`), English text and existing styles only:**
  - On a stopped run that has not already been continued, the preview drives "Continue unfinished rows (N)" and the "Also re-run rows that need review" checkbox. The continuation estimate fills the step 10 sizing table and the same two checkboxes ("I confirm an unsized run.", "I accept that this run will pause before finishing"), using the finite execution limits on the page. Continue is disabled until the estimate for the current choice has loaded and the required checkbox is ticked. Each click sends a new random idempotency key. On success the page opens the new run.
  - A run in a chain shows "Download whole input (all runs)" in the existing download actions. It freezes a revision, downloads the CSV and shows "Whole-input CSV" and "Whole-input manifest" links.

### Decisions not covered by the command

Approved by the person running this step:

- **`merge_identity` also removes `runtime_configuration.model_sample_rule`.** It is the run's selection method (`server_all_user_query_rows` for a full run, `explicit_source_row_ids` for a subset), which `sizing.comparable` already ignores. Without this, a paused full run and its subset continuation, the main use case, could never merge.
- **New route `POST /runs/{run_id}/continuation-estimate`.** The page needs the step 10 sizing table before a continuation starts, the preview is counts only, and the page never sees the unfinished row IDs. It takes the continuation body without the key or acknowledgements, runs the same selection, config and setup checks as the continuation, and creates nothing.

Not put to the owner; recorded for review:

- **A source can be continued once (`run_already_continued`, 409).** A second continuation of one source would branch the chain and make `chain` refuse the whole chain with `ambiguous_run_chain`. A replay with the same key still returns the first continuation. The page hides Continue on a run that already has a continuation; the latest run of a chain can be continued.
- **Merge provenance prefers runs that selected the row.** A continuation's unselected copy of an `invalid_input` row is terminal and identical to the root's, so the literal rule would credit a run that never processed the row.
- **Chain revisions are named by their inputs:** `rev_` plus the first 32 hex digits of `canonical_sha256` of the version, projection, each run's meta with its budget summary, and each run's results hash. Exporting an unchanged chain returns the same revision, its stored bytes and its first capture time; any change gives a new revision. Run exports keep random revision IDs.
- **A never-started run in a chain** contributes `None` serving and runtime identity, so a chain with one started and one never-started run gives `chain_identity_drift` until that run starts (literal rule).
- **Truncation is effectively unreachable with today's settings.** `max_run_rows` is in the compared settings, and `create_run` caps every run at its own `max_run_rows`, so a source with the same setup never has more rows than the maximum. The code path exists and is tested by capping only the selection maximum.
- **New tests skip `os.fsync`** (module fixture in `tests/test_coverage_continuation.py`). They check selection, chains and exports on 918-row runs, not crash durability; this cut the file from about 234 s to about 90 s. No product code is patched.
- **`knowledge_audit/jobs.py` changed** (`idle`), which the command's staging list did not name.
- **`pytest.ini` changed** (`faulthandler_timeout` 120 → 300), approved by the owner after clean-checkout run 2; see below.

### Existing tests changed

| Test | Old | New | Why |
|---|---|---|---|
| `tests/test_coverage_sizing.py` `body()` and `estimate_body()` | run payloads had no key | `body()` adds a fresh `idempotency_key`; `estimate_body()` drops it (the estimate takes none) | F15: a run POST without a key is now 422. Every assertion is unchanged. |
| `tests/test_coverage_depth_settings.py::test_api_entry_budget_defaults_to_and_is_bounded_by_configured_maximum` | both run POSTs had no key | each POST sends its own key | F15. Assertions unchanged. |
| `tests/test_knowledge_coverage_access_jobs.py::test_upload_mapping_no_arbitrary_paths_and_full_input_pilot_export` | run POST had no key | the body carries a key | F15. Assertions unchanged. |
| `tests/test_web_permissions.py` `EXPECTED` | no continuation or chain-export routes | the six new routes and capabilities | The inventory lists every browser route. |
| `tests/knowledge_operations.browser.cjs` | ended the paused-run flow after the export hash check | new step, below; every earlier check unchanged | Browser coverage for the continue action and the chain export. |

`tests/test_knowledge_execution_recovery.py::test_full_mode_api_idempotency_csrf_owner_and_revoked_grant` already sent a key and is unchanged. The page already sent a key, so `tests/knowledge_coverage.frontend.test.cjs` is unchanged.

New browser step in `tests/knowledge_operations.browser.cjs`, from the paused synthetic 918-row run: "Continue unfinished rows (918)" is shown and disabled until "I confirm an unsized run." is ticked; the click opens a new paused run whose `continues_run_id` and `chain_root_run_id` are the source and which selects 918 rows; "Download whole input (all runs)" downloads a CSV whose SHA-256 equals the manifest's `csv_sha256`, and the manifest lists both runs and 918 rows. The fixture app needed no change.

New tests (`tests/test_coverage_continuation.py`, 10): the selection rule with and without `needs_review`; creation (linked `subset` run with top-level links, same key gives the same run, unsized and over-limit sizing rules, second continuation refused, continuation of a continuation keeps the root); refusals (lease held and queued give `run_active`, changed `batch_max_entries` gives `continuation_identity_drift`, no unfinished rows gives 422, a started source with an otherwise equal setup is accepted, unknown run 404); truncation; a chain of 3 runs (provenance per row, 918 rows, 3 runs and hashes in the manifest, the same revision and bytes on repeat and on a fresh build, restricted projection, different `model_limit` and limits still merge); chain export routes; bad chains (branch, different snapshot, different serving); retention; and F15 (missing key 422 for runs and continuations, two keys with identical payloads give two runs).

### AGENTS.md note

This adds run orchestration and an export. It does not change how a row is evaluated, retrieval, prompts, models or the chatbot, so no retrieval or answer-quality test applies. Both benchmarks below show per-row execution overhead is unchanged: the read counts are identical and the medians move within run-to-run noise.

### Checks

Benchmarks, before on `f3c7424` and after, in conda `faq`:

```text
conda run --no-capture-output -n faq python scripts/benchmark_coverage_progress.py
before: {"baseline_full_rows_checkpoint_and_progress": {"median_ms": 855.3, "reads": {"index": 0, "metadata": 4600, "row": 4595}}, "baseline_full_rows_poll": {"median_ms": 856.622, "reads": {"index": 0, "metadata": 4595, "row": 4590}}, "indexed_checkpoint_and_progress": {"median_ms": 58.218, "reads": {"index": 10, "metadata": 20, "row": 5}}, "indexed_poll": {"median_ms": 8.151, "reads": {"index": 5, "metadata": 10, "row": 0}}, "iterations": 5, "model_dispatches": 0, "rows": 918, "scope": "synthetic_file_io_only"}
after:  {"baseline_full_rows_checkpoint_and_progress": {"median_ms": 815.61, "reads": {"index": 0, "metadata": 4600, "row": 4595}}, "baseline_full_rows_poll": {"median_ms": 809.6, "reads": {"index": 0, "metadata": 4595, "row": 4590}}, "indexed_checkpoint_and_progress": {"median_ms": 36.935, "reads": {"index": 10, "metadata": 20, "row": 5}}, "indexed_poll": {"median_ms": 7.974, "reads": {"index": 5, "metadata": 10, "row": 0}}, "iterations": 5, "model_dispatches": 0, "rows": 918, "scope": "synthetic_file_io_only"}

conda run --no-capture-output -n faq python scripts/benchmark_coverage_budgets.py
before: {"boundaries_per_iteration": 12, "checkpoint_only": {"measurements_ms": [490.728, 435.463, 444.574], "median_ms": 444.574}, "checkpoint_with_allowance": {"measurements_ms": [753.954, 834.973, 986.053], "median_ms": 834.973}, "input_rows": 918, "iterations": 3, "live_dispatches": 0, "scope": "mocked_file_io_no_service_throughput", "version": "a62-file-io-1"}
after:  {"boundaries_per_iteration": 12, "checkpoint_only": {"measurements_ms": [491.568, 444.757, 437.785], "median_ms": 444.757}, "checkpoint_with_allowance": {"measurements_ms": [807.223, 747.743, 715.192], "median_ms": 747.743}, "input_rows": 918, "iterations": 3, "live_dispatches": 0, "scope": "mocked_file_io_no_service_throughput", "version": "a62-file-io-1"}
```

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_coverage_continuation.py tests/test_coverage_sizing.py tests/test_knowledge_execution_recovery.py tests/test_knowledge_operations.py tests/test_knowledge_coverage_access_jobs.py tests/test_web_permissions.py tests/test_knowledge_recommendations.py
182 passed, 29 warnings in 275.60s (0:04:35)

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

The first run of the focused command, before the fsync fixture and the export rebuild change in the new test file, ended in a segmentation fault reported by the shell; a second, identical run passed (182 passed in 410.89s), as did the final run above. In both completed runs the only diagnostic is the `faulthandler_timeout = 120` traceback dump from the existing `tests/test_knowledge_execution_recovery.py::test_full_918_selection_idempotency_chronology_export_and_mock_run`, which takes about 145 s on `f3c7424` too (143.91 s there, 145.65 s with this change, run alone). No kernel log entry was found. The same crash recurred in clean-checkout run 2; see "Clean-checkout run 2 and the faulthandler timeout" below.

Also run before commit: the node harness `tests/knowledge_coverage.frontend.test.cjs` (6 passed), the offline frontend audit (PASS) and the operations browser harness on its fixture app (all 6 checks, including the new one).

Clean-checkout command (conda `faq`), run on the unpushed `[11]` commit. `/tmp/faq-a21-browser-node` exists, so the browser stage ran with `REQUIRE_BROWSER=1`. `uptime` before the run showed a load average of 0.53, the host's normal level:

```text
uptime
git worktree add /tmp/faq-clean-11 HEAD
cd /tmp/faq-clean-11 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-11; echo "exit $status"
```

Run 1, on the first `[11]` commit (`94ab38e`):

```text
1177 passed, 26 deselected, 58 warnings, 291 subtests passed in 327.75s (0:05:27)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
Offline frontend audit: PASS
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1167 in step 10 to 1177, from the 10 new tests in `tests/test_coverage_continuation.py`. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. Only this log section changed after run 1.

### Clean-checkout run 2 and the faulthandler timeout (approved by the owner)

Run 2, on the amended commit `7ff0645` (only the run 1 summary above added), with the same command. `uptime` showed a load average of 1.54. The suite itself exited 139 (segmentation fault) during pytest, so the later stages did not run:

```text
....Timeout (0:02:00)!
Thread 0x00007e0fe3a65600 (most recent call first):
  File "/root/miniconda3/envs/faq/lib/python3.12/pathlib.py"timeout: the monitored command dumped core
scripts/run_offline_tests.sh: line 20: 1212093 Segmentation fault      timeout 1800 python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q
pytest: FAIL
exit 139
```

- **Where it crashed:** `pytest.ini` set `faulthandler_timeout = 120`, so for any test running longer than 120 s faulthandler's watchdog thread prints the traceback of every thread. The existing `tests/test_knowledge_execution_recovery.py::test_full_918_selection_idempotency_chronology_export_and_mock_run` runs longer than that, and both crashes (the first focused run before commit and clean-checkout run 2) happened while that dump was being printed: the output stops in the middle of a traceback line, then the core dump.
- **Not this change:** run alone, that test took 143.91 s on `f3c7424` and 145.65 s with this change, so it triggers the dump on both, and none of the new code runs in it. Of the five runs that reached the dump, two crashed and three passed. The cause is the faulthandler dump thread, not this change.
- **Decision (owner, option 1 of 3):** `pytest.ini` `faulthandler_timeout = 300`. No test changes; a real hang still gets a traceback, after 5 minutes instead of 2. The alternatives were skipping disk flushes in that test, which would weaken a crash-recovery test, or re-running unchanged and accepting the flake.

The commit amended with `pytest.ini` and this section was checked again in a new clean worktree with the same command before push.

## [12] Evaluate a repeated question once per run, keyed on its texts, intent and prior turns

### Problem

- **F8d (Medium, cost):** `CoverageEvaluator.evaluate` (`knowledge_audit/pipeline.py`) ran scope, aspects, the production assessment, audit batches and verification for every row. A non-covered row costs about 64 completions, so every repeat of a question cost that again.
- **A key on the query alone is wrong.** Scope and aspects read `standalone_query_redacted`, the scope call also reads `input_query_redacted` and the prior turns, and retrieval reads `canonical_retrieval_query_redacted`. Two rows that share only the canonical query can still be different questions.

### Rule (approved by the owner in plan v2)

1. **Same run only.** A row copies only from a row of the same run that ended `completed`. Nothing is copied across runs, including continuations.
2. **The key covers everything row-specific the evaluation reads.**
3. **Uncertain rows never copy and are never copied.**
4. **Copies are marked.** A copy names its source, is not counted as model-evaluated and is not drafted for recommendations on its own.
5. **Preparation still runs.** The key needs the prepared texts and the intent, so a copy still pays for its preparation calls; it saves everything after preparation.

### The key and eligibility (`knowledge_audit/dedupe.py`, `VERSION = "repeated-question-1"`)

- **`eligible(prepared)`** is true only when `preparation_status == "prepared"`, `uncertainty_codes == []`, `rewrite_status` is `no_prior_history` or `rewritten`, `existing_intent` is not empty, and the history is known and unambiguous: `history_provenance.history_status` is `unavailable` (no prior turns) or `user_only` (prior turns all the user's own), `prior_order_ambiguous` and `unresolved_peer_times` are false and `equal_timestamp_event_count == 0`. `incomplete` (an assistant turn, or unresolved peer times) and `ambiguous` (equal timestamps) history are never eligible.
- **`key(identity, prepared)`** is `None` unless eligible, else `canonical_sha256` of `VERSION`, the run identity, `input_query_redacted`, `normalized_query_redacted`, `standalone_query_redacted`, `canonical_retrieval_query_redacted`, `existing_intent`, `scope_status` (the preparation's), `rewrite_status`, `history_status` and `history_provenance.history_digest` (the digest of the redacted prior turns, not of row IDs).
- **`run_identity(meta)`** hashes `run_id`, `dataset_id`, `snapshot_id`, `run_identity_id`, `configuration_id`, `settings.documents`, `settings.entry_budget` and `versions`. It is computed after the run identity is pinned and is constant within a run. See decision 1 for `run_id`.
- **Accepted provenance difference.** The scope prompt also carries `history_provenance`, which holds the row's own `cutoff_row_id`, `cutoff_timestamp` and `history_row_ids`. That metadata is not part of the key, so a copy's source saw different row IDs and times in its scope prompt. The prior-turn texts themselves are covered by `history_digest`, and eligible rows have no equal-timestamp exclusions.

### Changes

- **`knowledge_audit/dedupe.py`** (new): `eligible`, `key`, `run_identity`, `candidate_key`, `preview`, `copy_result`, plus `enabled(settings)` (`settings["dedupe_policy"] == VERSION`), `is_source`/`register` (first completed, non-copy row with a key, per key; row IDs only) and `source_map(store, meta)`, which walks `processing_row_ids` and reads the stored row files.
  - **`copy_result(source, own)`** deep-copies the source and puts back the copy's own fields (`OWN_KEYS`): the `QueryPreparer.prepare` keys for identity, timestamps, preparation and `history_provenance`, plus `processing_ordinal`, `model_selected` and the attempt accounting (`attempt_count`, `run_identity_id`, `duration_ms`, `model_metrics`, `retrieval_metrics`, `validation_diagnostics`, `output_recovery_count`, `failure_diagnostics`, `request_journal`, `validated_checkpoint_count`, `checkpoint_reuse_count`, `unknown_completion_count`). An own key not yet present is removed rather than left as the source's; the evaluator's `finally` block and the job loop then set it. It sets `deduplicated_from_row_id`, `dedupe_key_sha256`, `model_evaluated = False` and `entry_model_dispatched = False`. See decision 3.
  - **Why a copy keeps the source's `stopping_reason`:** the copy carries the source's `evaluation_scope`, which describes the search the source ran, and `stopping_reason` is why that search stopped. Recommendation eligibility reads both together (`evaluation_scope_not_established` unless `stopping_reason` is `candidate_exhausted` or `evaluation_limit`). The copy's own value would be the job loop's seed (`preparation`), which describes no evaluation.
- **`knowledge_audit/settings.py`:** `CoverageSettings.dedupe: bool = True` from `KNOWLEDGE_COVERAGE_DEDUPE` (`true`/`false`, stripped, case-insensitive; anything else, including empty, raises `invalid_coverage_dedupe`, now in `SAFE_API_CODES`). The manifest gained `"dedupe_policy": "repeated-question-1"` or `"disabled"`, pinned per run like `verification_passes`.
- **`knowledge_audit/pipeline.py`:** `CoverageEvaluator(..., dedupe=False)` with `dedupe_identity` and `dedupe_lookup`. Fresh rows default `deduplicated_from_row_id` to `""`. Right after the first preparation succeeds, when dedupe and a lookup are set and the key is not `None`, the key is stored in `dedupe_key_sha256` and looked up; a found source becomes the result through `copy_result` and no further model or retrieval call is made. The `finally` block leaves a copy's `question_evidence`, `batch_results`, `evaluated_entry_ids`, `evaluated_entry_count`, `verifications` and `review_codes` alone and still sets its own metrics, diagnostics and `duration_ms`. A row with a key but no source evaluates normally and keeps its key.
- **`knowledge_audit/jobs.py`:** after the identity is pinned and before the row loop, when the engine has `dedupe` set and the run's pinned settings name the policy, the map is rebuilt with `dedupe.source_map` from the store, `engine.dedupe_identity = dedupe.run_identity(meta)` and `engine.dedupe_lookup` reads the source row from the store. After each saved row, `dedupe.register` adds it if it qualifies. For a copy the loop keeps `model_evaluated` and `entry_model_dispatched` false, keeps the source's `evaluated_entry_ids`, and skips the `retained_evaluation_unresolved` check. Engines without the attribute (test fakes) are unchanged.
- **`knowledge_audit/service.py`:** `dedupe=dedupe.enabled(pinned)`.
- **`knowledge_audit/export.py`:** `deduplicated_from_row_id` in `COVERAGE_FIELDS` (not `FIELDS`, so `attempt_seed` drops it) and in the `_redact` reference keys, so the restricted export keeps the row ID. Older rows export `""`. `dedupe_key_sha256` is not exported.
- **`knowledge_audit/recommendations.py`:** `eligibility` adds `deduplicated_row_uses_source` for a copy; drafting happens once, on the source.
- **`knowledge_audit/sizing.py`:** `_observe` skips copies, so reference per-row costs stay costs of real evaluations. The estimate still multiplies by every row, so it stays an upper bound.
- **`knowledge_audit/api.py`:** `sizing_view` adds `"dedupe": dedupe.preview(store.preparations(...), row_ids)` over the run's row IDs (`None` when the config's policy is `disabled`), returned by `/runs/estimate` and `continuation-estimate`. `candidate_key` runs on the stored preparation rows (`pending_model` or `prepared`, no uncertainty codes, history passing the history checks) and hashes `input_query_redacted`, `normalized_query_redacted`, `history_status` and `history_digest`. The preview returns `policy`, `candidate_rows`, `distinct_questions` and `possible_copies` only, never text or keys.
- **`static/js/knowledge_coverage.js`:** under the sizing table in the start and the continue panels, when `dedupe` is present: `Repeated questions: N rows may reuse an earlier row's result`.
- **Environment:** `KNOWLEDGE_COVERAGE_DEDUPE=true` with the approved comment after `KNOWLEDGE_COVERAGE_VERIFICATION_PASSES` in `.env`, `env.example`, `.env.example.generated`, `Production_ENV` and `Production_ENV.example` (`.env` and `Production_ENV` are local only and not staged). `scripts/validate_environment.py` has the `VariableSpec` (`kind="bool"`, `default="true"`, component `Knowledge coverage audit`, restart `FastAPI`, usage naming `knowledge_audit/dedupe.py` and `CoverageEvaluator.evaluate`). `tests/test_validate_environment.py` lists no coverage keys, so it is unchanged.

### Decisions

1. **`run_id` in `run_identity` (beyond the listed fields; please confirm).** The listed fields are identical for two runs on the same dataset, snapshot, settings and serving, so without `run_id` the key of a second run would equal the first run's. Copying across runs was already impossible (the map is rebuilt from this run's rows only), but "the key can never match across runs" would not hold. `test_runs_never_share_sources` asserts both.
2. **Two gates.** The job loop sets the lookup only when the engine has `dedupe` set *and* the run's pinned settings name `repeated-question-1`. The factory already follows the pinned policy; the second gate makes the run's settings the authority even for an engine built another way. A run whose settings lack `dedupe_policy` is evaluated without copying (tested with an engine that has `dedupe=True`).
3. **`processing_status`, `coverage_status` and `scope_status` are the source's.** `QueryPreparer.prepare` returns them too, but evaluation overwrites them, and the copy's are the source's evaluation results (`completed`, the coverage, the scope decision). `processing_ordinal` and `model_selected`, which the job loop seeds, stay the copy's own.
4. **A copy's dispatch accounting.** If an earlier, interrupted attempt of a row dispatched batches before a later attempt copied it, the copy still reports `entry_model_dispatched = False` and the source's `evaluated_entry_ids`; the row's `request_journal` keeps the earlier dispatches.
5. **Older runs.** The manifest gained `dedupe_policy`, so runs created before this step cannot resume (`audit_runtime_identity_drift` in `build_engine`), as in steps 07 and 08; `dedupe.enabled` would keep them off in any case. Completed runs from before this step are not comparable reference runs for sizing, and their continuations give `continuation_identity_drift`, until a new pilot runs.
6. **The preview line shows with or without an estimate,** whenever `dedupe` is present.

### AGENTS.md note

This changes audit cost, not the chatbot. A copy carries the verdict its source reached on identical inputs. Retrieval, prompts, models and the chatbot's answers are unchanged, so the chatbot's retrieval and answer-quality tests do not apply. The live L2 stability protocol measures how often a fresh evaluation would differ.

### Tests

New `tests/test_coverage_dedupe.py` (9 tests), driving runs through `CoverageJobs` with a real `CoverageEvaluator`, `LabeledModel` and the mocked `Retrieval`:

1. eligibility (`uncertain_preparation`, `needs_context`, an uncertainty code, `incomplete` history from an assistant turn, `ambiguous` history from equal timestamps, `fallback` rewrite, empty intent give `None`); equal inputs give equal keys; the cutoff row ID does not change the key; each of the four texts, the intent, the history digest and the run identity does;
2. three identical history-free rows and one different row: the model is called after preparation only for row 1 and the different row (by role: 2 scope, 2 aspects, 2 batch, 4 verification); rows 2 and 3 name row 1, are not model-evaluated, equal row 1 on every key outside `OWN_KEYS`, and keep their own row ID, ordinals, timestamp and session;
3. prior turns: the same text after identical user-only prior turns in two sessions is copied; after different prior turns it is evaluated again;
4. a first row sent to review is not a source; the second is evaluated and the third copies from it;
5. a child process dies (`os._exit`) right after row 1's completed row is written; a new worker recovers the run, rebuilds the map from the store and copies row 2 with no model call;
6. a second run over the same rows evaluates its first occurrence again and has different keys;
7. `KNOWLEDGE_COVERAGE_DEDUPE=false` gives `"disabled"` and evaluates every row; a run whose settings lack `dedupe_policy` evaluates every row; `yes`, `1` and `""` raise `invalid_coverage_dedupe`;
8. the column is in the evidence and the restricted export, `dedupe_key_sha256` is not; eligibility gives `deduplicated_row_uses_source` for the copy only; `_observe` skips the copy; the estimate response has the exact preview counts on a synthetic 6-row dataset (3 repeats, 1 other, 2 rows with equal-time history: 4 candidates, 2 distinct, 2 possible copies; a 3-row subset gives 1), no question text, and `None` with the setting off.

Changed existing tests:

- `tests/test_coverage_sizing.py::test_estimate_endpoint_shape_and_permissions` asserts the exact estimate response, which now has the `dedupe` key (7 distinct questions in one session: 7 candidates, 0 possible copies).
- `tests/knowledge_coverage.frontend.test.cjs` (full-input estimate table test): the fixture view gains `dedupe` and one assertion checks the new line under the table.

A mutation check (the `finally` guard disabled) made test 2 fail; the guard was restored.

### Benchmark

`scripts/benchmark_coverage_dedupe.py`: a synthetic 50-row input (40 distinct history-free questions plus 10 exact repeats, each row in its own session) through `CoverageJobs` with a real `CoverageEvaluator`, `LabeledModel` and the mocked retrieval, with the setting off and then on, 3 iterations each; then the map rebuild on the 918-row `synthetic_918` store with 40 keys. The setting is the only variable. "Off" is the before measurement, because with the setting off no key is computed and nothing is copied.

```text
conda run --no-capture-output -n faq python scripts/benchmark_coverage_dedupe.py
{"calls_by_role": {"aspects": 50, "batch": 50, "scope": 50, "verification": 100}, "copied_rows": 0, "distinct_questions": 40, "iterations": 3, "median_wall_ms": 14956.348, "model_calls": 250, "retrieval_fetches": 100, "rows": 50, "scope": "mocked_model_and_retrieval", "variant": "dedupe_off", "wall_ms": [14956.348, 14844.733, 15246.236]}
{"calls_by_role": {"aspects": 40, "batch": 40, "scope": 40, "verification": 80}, "copied_rows": 10, "distinct_questions": 40, "iterations": 3, "median_wall_ms": 13421.604, "model_calls": 200, "retrieval_fetches": 80, "rows": 50, "scope": "mocked_model_and_retrieval", "variant": "dedupe_on", "wall_ms": [13559.23, 13304.386, 13421.604]}
{"iterations": 3, "measurements_ms": [211.958, 189.378, 187.476], "median_ms": 189.378, "rows": 918, "sources": 40, "variant": "map_rebuild_918"}
```

Model calls fall from 250 to 200 and retrieval fetches from 100 to 80, exactly the 10 repeats' share. The mocked model answers instantly, so wall time (−10%) is dominated by the journal and row file writes and by preparation, which copies still pay; on live serving the saving follows the call counts. Rebuilding the map once per attempt costs about 0.19 s on 918 rows.

### Checks

Before commit, in conda `faq` with the offline pytest guard:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_coverage_dedupe.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_execution_recovery.py tests/test_knowledge_operations.py tests/test_knowledge_coverage_access_jobs.py tests/test_coverage_sizing.py tests/test_coverage_continuation.py tests/test_knowledge_recommendations.py tests/test_coverage_depth_settings.py tests/test_validate_environment.py
207 passed, 10 warnings in 282.06s (0:04:42)

conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file .env --mode staging | grep -i "summary"
Summary: 0 critical, 27 warning, 4 informational

conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file Production_ENV --mode production | grep -i "summary"
Summary: 6 critical, 24 warning, 4 informational
(validator exit 2; the same six pre-existing empty credential placeholders as in earlier steps)

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0
```

Also run before commit: `node --test tests/knowledge_coverage.frontend.test.cjs` (6 passed).

Clean-checkout command (conda `faq`), on the unpushed `[12]` commit:

```text
uptime
git worktree add /tmp/faq-clean-12 HEAD
cd /tmp/faq-clean-12 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-12; echo "exit $status"
```

`/tmp/faq-a21-browser-node` exists, so the browser stage ran with `REQUIRE_BROWSER=1`. `uptime` before the run showed a load average of 0.63, the host's normal level.

Run 1, on the first `[12]` commit (`f808a67`):

```text
1186 passed, 26 deselected, 59 warnings, 291 subtests passed in 329.88s (0:05:29)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
Offline frontend audit: PASS
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count rose from 1177 in step 11 to 1186, from the 9 new tests in `tests/test_coverage_dedupe.py`. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. Only this log section changed after run 1, and the amended commit was checked again in a new clean worktree with the same command before push.

## [13] Add staging-only retrieval and answer-quality evaluation tools and the release runbook

### Problem

- **F11 (Medium, blocks production release):** the branch changes production ranking, and the only evidence is a few frozen cases per change (`scripts/rrf_p1_compare.py`, `retrieval_depth_p2_compare.py`, `reranker_p3_compare.py`). `AGENTS.md` listed the retrieval-test and answer-quality-test commands as unknown.

### Configurations and the frozen-query rule

| Label | Commit | Change |
|---|---|---|
| `baseline` | `681cc95` | `main` |
| `p1` | `c833805` | An absent retrieval branch adds 0 to RRF scoring. |
| `p2` | `d45ddf6` | Lexical and dense depths are request-local and configurable. |
| `p3` | `e15761f` | Batched TEI reranking with merged global scores. |
| `rc` | tip of `knowledge-gap-audit` | Release candidate. |

`freeze` computes each case's retrieval query once, on this checkout, as `answering_service.py` builds it for a first-turn `general` question: `PersianTextProcessor(use_stemming=False).normalize`, `normalize_persian_text`, then `canonicalize_retrieval_query`. It records `query_rule: "general_canonical"`, the alias SHA-256, the canonicalization flag and the commit. Every configuration gets the identical query string, so the ranking code is the only variable.

### Changes

- **`scripts/_staging_guard.py`.** It has three functions:
  - `require_staging(keys)` requires `ENVIRONMENT=staging`, and requires each key to equal this checkout's `.env` value and resolve to `127.0.0.1`, `localhost` or `::1`. For a key ending in `URL` the URL host is checked, else the value itself. This is the same comparison as `confirm_staging`. On failure it prints `staging guard: refused (KEY)` and exits 3.
  - `require_loopback_url` applies the loopback rule to `--base-url`.
  - `load_env()` fills unset variables from `.env`, as the other staging scripts do.
- **`scripts/retrieval_eval.py`.**
  - `freeze` reads the questions and writes `cases.json`.
  - `run` calls the guard first and checks the worktree. It then runs `scripts/_retrieval_child.py` with `cwd` and `PYTHONPATH` set to the worktree, and writes `run.json`.
  - `label-sheet` writes the union of each question's retrieved and context IDs across runs, without duplicates and with a blank row between questions.
  - `compare` computes the paired metrics, the bootstrap intervals, the latency deltas and the verdict, and writes the report.
- **`scripts/_retrieval_child.py`.** The child builds `RAGSystem` as `main.py` `lifespan` does, but without `init_db`, authentication, OCR, the classifier or the agent services. It runs each case sequentially under `bind_pipeline_observer(None)`, and its `select_context` mirrors `agent_graph.make_handle_general`. It writes these private files:
  - `per_question.json`: the retrieved, reranked and context IDs, `empty`, `latency_ms`, and the exception class name for a case that raises;
  - `titles.json`: the FAQ `question:` field per chunk ID, parsed as `prepare_context` does;
  - `child.json`: the `rag_*` and `tei_rerank_*` settings and the counts.
- **`scripts/answer_quality_eval.py`.**
  - `collect` sends sequential `POST /api/mobile/v1/talk` requests, each with a new UUID session ID, the original question, the datasource and a 50 s timeout. It writes `answers.json` and `collect.json`.
  - `blind` writes `grading-sheet.csv` (no configuration names) and `grading-key.json`, randomizing the answer order per item from the seed.
  - `score` un-blinds the sheet, computes the rates, the preference counts and a two-sided exact sign test excluding `same`, and writes the report.
- **Identity loader reuse.** `collect` takes national codes only from the operator-reserved fixture, through `load_fixture` in `benchmarks/load/mobile_talk_load_test.py`. The module is loaded by path, and the identities are assigned round-robin.
- **Privacy.**
  - Every private input and output directory must pass `knowledge_audit.privacy.private_directory`, and files are written by `private_write` (mode `0600`, never overwriting). The child writes with the same `O_EXCL` and `0600` semantics using the standard library.
  - Reports must be `.md` files under `docs/performance/`.
  - The terminal prints counts and fixed lines only, and the child's stdout and stderr are discarded.
  - Sheet text cells go through `formula_safe`.
- **`docs/performance/RELEASE_EVALUATION_RUNBOOK.md`** covers the worktrees (including the `e15761f` fail-closed fallback to comparing `p2` with `rc`), the 150 to 300 question retrieval set, sequential runs on an idle host, labeling, compare, the 50 to 100 question blind answer evaluation on two loopback app instances, and Gate C with L6.
- **`AGENTS.md`.** Under "Tests and benchmarks", the "unknown" sentence is replaced by the two commands, the runbook pointer and the staging-only, human-label note.

### Verdict thresholds (flags; defaults)

- **Retrieval, each configuration against `baseline`.** It passes when all four hold:
  - the lower 95% bound of the `hit_context` difference is at least `-0.02` (`--min-hit-diff`);
  - the lower 95% bound of the `recall_context` difference is at least `-0.02` (`--min-recall-diff`);
  - p95 is at most 45,000 ms (`--max-p95-ms`);
  - p95 is at most 1.2 × the baseline's p95 (`--max-p95-ratio`).

  The bootstrap draws 10,000 paired resamples with `random.Random(1234)`, using one index draw per resample for all three metrics. `compare` exits 0 only if every configuration passes.
- **Answers.** The release candidate fails if the sign test favors the baseline at p < 0.05 (`--alpha`), or if its `incorrect` count exceeds the baseline's by more than 2 (`--max-extra-incorrect`). `score` exits 0 on pass, else 1.

### Decisions not covered by the command

1. **Normalization before canonicalization.** See "Facts corrected" below. The production retrieval query is canonicalized from the normalized query. `PersianTextProcessor`, `normalize_persian_text`, the canonicalizer and `config/retrieval_query_aliases.json` are unchanged between `681cc95` and the tip, so applying them on this checkout matches every configuration.
2. **Imports in the child.** Besides the standard library and the worktree's modules, the child imports `httpx` and `openai`. These are the client libraries the worktree's `main.py` uses to build the same clients, from the shared conda environment. It never imports this checkout's code. It is started with `python -P` so this checkout's `scripts/` directory can't shadow worktree modules.
3. **Clean worktree required.** `run` also exits 2 when the worktree has uncommitted tracked changes, so the recorded commit is the code that ran.
4. **Failed cases.** A case that raised, or is missing from a run, counts as an empty context in the rates and is left out of the latencies. Error counts are reported per configuration.
5. **Latency population.** Latency percentiles use every completed case, not only the labeled ones, because latency doesn't depend on labels.
6. **Verdict scope.** Only non-baseline configurations get a verdict. When the previous configuration is the baseline, the duplicate pair is skipped.
7. **Where `blind` reads questions.** `blind` has no `--cases` flag, so it reads the questions from the cases file that `collect` recorded. It checks that both collections and the file share one SHA-256. `--a` is the baseline and `--b` the release candidate. A missing answer shows as `[no answer]`.
8. **Incomplete grading.** `score` exits 2, printing a count only, when any item has a missing or invalid grade.
9. **Private inputs.** The questions CSV, the grading sheet and the key must also be in private directories.

### Facts corrected

- **Query canonicalization.** `answering_service.py` canonicalizes `classification_query`, the Parsivar-plus-`normalize_persian_text` normalized query, not the raw question. `freeze` therefore normalizes first; see decision 1.
- **"Only three files change."** Between `681cc95` and `e15761f`, the only files that affect ranking are `utils/RagSystem.py`, `utils/performance_config.py` and `utils/persian_hybrid_search.py`. Outside tests, docs and scripts, these also changed:
  - `env.example`, `.env.example.generated` and `Production_ENV` (tracked at those commits; untracked at the tip), which added two configuration keys;
  - `internal_evaluation_api.py`, which added two runtime-snapshot fields.

  None of these affects ranking.

Everything else held:

- The `RAGSystem(` call and the `lifespan` construction are identical in all five commits. `check_worktree` accepted temporary worktrees of `681cc95` and `e15761f` and the tip.
- The child's imports resolve to each worktree's own modules at `681cc95` and `e15761f`. This was checked with imports only and no service connection; the worktrees were then removed.
- `agent_graph.py` differs only by moving the `FAQ_FALLBACK_FRAGMENT` import.
- The `/v1/talk` schema is unchanged.

### AGENTS.md note

This adds evaluation tools only. Retrieval, prompts, models and the chatbot are unchanged. No performance change, so no benchmark is required.

### Live evaluation

No live evaluation was run in this step. Running the tools on staging is an operator step from `docs/performance/RELEASE_EVALUATION_RUNBOOK.md`. Gate C stays open until both reports pass and L6 is confirmed.

### Tests

New `tests/test_release_evaluation_tools.py` (6 tests, offline, synthetic data):

1. exact `hit_context`, `recall_context`, `mrr_context` and `recall_retrieved`, including no relevant hit and an empty result;
2. the selection mirror with a recording fake: `FAQ` takes the whole reranked list, other categories the first 3, and reranking is skipped when disabled. A raising case records only `ValueError`;
3. the bootstrap is deterministic. Identical runs give 0 differences with intervals containing 0. Constructed data passes, fails on `hit_context`, and fails on the p95 ratio. Comparison pairs are checked;
4. a blind and score round trip recovers the per-configuration counts, the grounded count and the sign test (p = 2/256). The sheet holds no configuration names. The report holds no question or answer text;
5. guards: `require_staging` exits 3 without `ENVIRONMENT=staging`, with a non-loopback host and with a value that differs from `.env`. A non-loopback `--base-url` exits 3. `freeze`, `label-sheet` and `collect` refuse an output directory inside the repository and don't create it. The `RAGSystem(` touch detection is checked;
6. an end-to-end pass with a unique marker seeded in the questions, the titles and the answers. It covers the real `freeze`, `run` with one fake child (which prints the marker), `label-sheet`, `compare`, `collect` with a fake poster, `blind` and `score`. Both reports are written under `docs/performance/` and removed afterwards. The marker is absent from every repository file modified during the test and from captured stdout and stderr, and the private files are `0600`.

Mutation checks:

- not discarding the child's output failed test 6;
- selecting the first 2 instead of 3 failed test 2.

Both were restored.

### Checks

In conda `faq`:

```text
timeout 600 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_release_evaluation_tools.py
6 passed in 3.81s

conda run --no-capture-output -n faq python scripts/audit_offline_frontend.py
Offline frontend audit: PASS
External runtime dependencies: 0

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

git diff --check
no output, exit 0

git diff --name-only HEAD -- knowledge_audit/ main.py agent_graph.py utils/ mobile_api.py
no output
```

The clean-checkout full run was skipped by agreement with the owner. This step adds standalone scripts, a runbook and an `AGENTS.md` paragraph; no application or audit module imports the new scripts, so the existing suite can't change. Step 14's clean run covers this commit, and the owner runs the full suite after the push.

## [14] Parse the legacy inline category footer, compare numbers by value, and require a second reviewer for approvals

F12, F13 and F14 in one commit. They touch separate modules with independent tests.

### Part A (F12): legacy inline category footer

`grep -rn faq_content --include=*.py .` shows the parser is used by `kb_manager.py`, `new_architecture/knowledge_update.py` (error type only), `knowledge_audit/snapshot.py`, offline scripts and tests. `main.py`, `agent_graph.py`, `agent_service.py` and `utils/RagSystem.py` don't use it, so the chat answer path is unaffected.

- `hihelp_chunker.py`: the two `data = f"..."` lines moved into `format_chunk(user_question_and_answer, category, sub_category=None)`. Both branches now start the footer on its own line. The file reading and loop are under `if __name__ == "__main__":`. The sub-category branch is chosen by `sub_category is not None`, which keeps the old `type(...) == str` behavior for an empty string.
- `utils/faq_content.py`: `FOOTER_VERSION = "faq-footer-2"`, and a legacy fallback in `split_taxonomy_suffix` that runs only when no line-start metadata was found. `compose_faq` still writes only the line-start form.
- `knowledge_audit/snapshot.py`: `utils/faq_content.py` is now hashed into `capture_code_sha256`.

**Accepted form:** last non-empty line, last `question category` token, written as the old chunker wrote it (`question category :`, whitespace before the colon). Text precedes it on that line, an `answer` marker occurs before it, and the rest is one label of 1 to 120 characters with an optional final `.`, no `:`, no other metadata token and no newline. Example: `question: How do I X?\nanswer: Do Y.question category : Cards.` gives category `Cards`, no subcategory and answer `Do Y.`. The label is cleaned with `_clean_category_field`, as line-start footers are.

**Rejected forms (content unchanged, no category):**

- prose with a later colon: `answer: The question category : field in the form is optional, see section 2: details.`;
- the inline form with no `answer` marker;
- `question category:` without whitespace before the colon, as in prose (`Explain question category: examples in prose.`) or a quoted line (`> question category: example`);
- a token with no text before it on the line, which is the existing line-start path.

### Part B (F13): numbers compared by value

`knowledge_audit/recommendations.py`: `NUMERIC_GUARD_VERSION = "numeric-premise-2"`, `_DIGITS` (Persian and Arabic-Indic to ASCII), and `_numbers(text)`. It translates digits, removes `,` `،` `٬` between digits, extracts `\d+(?:[.:/]\d+)*`, strips leading zeros from each integer part, and adds single number words. `_no_new_numbers` keeps the aspect, gap and question ID stripping and raises `invented_numeric_premise` on `_numbers(value) - _numbers(provided)`. `recommendation_versions()` records `"numeric_guard"`.

**Number words** (whole tokens after `normalize_persian_text`, ZWNJ to space and case folding; no compound parsing):

- Persian: یک 1, دو 2, سه 3, چهار 4, پنج 5, شش and شیش 6, هفت 7, هشت 8, نه 9, ده 10, یازده 11, دوازده 12, پانزده 15, بیست 20, سی 30, چهل 40, پنجاه 50, صد 100, دویست 200, پانصد 500, هزار 1000, میلیون 1000000, میلیارد 1000000000.
- English: one to ten, twenty, thirty, fifty, hundred, thousand, million, billion.

**Unit rule:** `یک`, `دو`, `نه`, `سی` and `one` count only when the next token is روز, ساعت, ماه, سال, هفته, دقیقه, درصد, ریال, تومان, day(s), hour(s), month(s), year(s), week(s), minute(s) or percent.

No existing test relied on `۵` and `5` being different.

### Part C (F14): a second reviewer for approvals

- **Setting.** `CoverageSettings.require_second_reviewer` (default `True`) from `KNOWLEDGE_COVERAGE_REQUIRE_SECOND_REVIEWER`, parsed like `KNOWLEDGE_COVERAGE_DEDUPE`; the error code is `invalid_coverage_second_reviewer`. `manifest()` adds `recommendation_review_policy`: `second-reviewer-1`, or `owner-review-1` when off. The key and comment are in `.env`, `env.example`, `.env.example.generated`, `Production_ENV` and `Production_ENV.example` after `KNOWLEDGE_COVERAGE_DEDUPE`, with a `VariableSpec` in `scripts/validate_environment.py`. `.env` and `Production_ENV` were edited but not staged.
- **Store.** `reviewable`, `list_reviewable` and `reviewer_view` were added. `decide(rid, actor_id, capabilities, row_id, question_id, decision, note)` authorizes with `reviewable` and does every internal read as `meta['owner_id']`. It records `reviewer_user_id` and `run_owner_id` on the review revision and on each decision. It raises `second_reviewer_required` when the policy is on and the owner approves.
- **Exports.** The recommendation export manifest carries `reviewer_user_id` (of the pinned review revision; `null` when unreviewed) and `run_owner_id`. Each decision embedded in a CSV row's `recommendations[].review` carries both. CSV columns are unchanged.
- **API.** `GET /api/knowledge-coverage/recommendations/reviewable` (metadata only) and `GET /api/knowledge-coverage/recommendations/{revision_id}/review-view` (the projection) are registered in `web_permissions.py` under `coverage_recommendation_review`, ahead of the `/recommendations/[^/]+` pattern. Neither requires `coverage_evidence_view`. Both codes are in `SAFE_API_CODES` in `knowledge_audit/api.py`. The dashboard shows "Approval needs a reviewer other than the run owner." for `second_reviewer_required`.
- **Dashboard.** A "Waiting for my review" section, rendered only with `coverage_recommendation_review`, lists other owners' completed revisions. Opening one shows the projection with Approve, Request changes and Reject. On the owner's own draft, when the policy is `second-reviewer-1`, Approve has `aria-disabled="true"` and the title "Another reviewer must approve". The page's labels are English only (the language toggle changes reading direction), so no Persian strings were added.

**Reviewer projection fields (`reviewer_view`):**

- `revision`: `public_meta` (`recommendation_revision_id`, `source_run_id`, `source_export_id`, `source_export_revision_id`, `snapshot_id`, `created_at`, `finished_at`, `state`, `phase`, `error_code`, `selected_row_ids`, `versions`, `serving_identity`, `human_gap_review_status`, `calibration_status`, `operational_settings`, `pause_reason`);
- `is_run_owner`, `review_policy`, `review_revision_id`;
- `rows[row_id]`:
  - `source_row_id`, `recommendation_status` (the effective status);
  - `recommendations[]`: `recommendation_id`, `recommended_question`, `category`, `subcategory`, `taxonomy_status`;
  - `gap_specifications[]`: `gap_id`, `missing_aspect_ids`, `missing_information`, `conditions`, `search_scope_limitations`, `review_requirements`;
  - `decisions[recommendation_id]`: that row's current decision (`source_row_id`, `recommendation_id`, `status`, redacted `note`, `reviewer_user_id`, `run_owner_id`), or `{status: unreviewed}`.

It never includes the customer, normalized, standalone or retrieval queries, evidence sentences, supports, eligibility details, title lookups or other rows' notes. `list_reviewable` returns `public_meta` only.

### Decisions not covered by the command

1. **Footer colon spacing.** The command's acceptance rule also matched `answer: Explain question category: examples in prose.` and `> question category: example`. Those break the existing `test_inline_quoted_and_fenced_prose_is_not_taxonomy`, which had to stay green unchanged. The fallback therefore also requires whitespace before the colon, which the chunker always wrote.
2. **Snapshot version.** Admission (`snapshot_policy_superseded`) is gated on `SNAPSHOT_VERSION`, not on the code hash. `SNAPSHOT_VERSION` was left unchanged, so only new snapshot IDs change. Snapshots captured before this step stay admissible, and a fresh staging snapshot remains an owner task.
3. **Decimals.** In a decimal (one `.` and no `:` or `/`), the fractional part keeps its leading zeros, so `1.05` and `1.5` stay different.
4. **Check order in `decide`.** `second_reviewer_required` is checked after every existing check, so an owner's approval of an ineligible draft still reports the existing reason.
5. **Policy timing.** `decide` reads the current setting, not the setting captured when the draft was made. The detail and review-view responses carry `review_policy` for the dashboard.
6. **Decision route permissions.** `POST .../reviews` now requires only `coverage_recommendation_review`; previously it also required `coverage_results_view`, `coverage_evidence_view` and `kb_read`. A non-owner reviewer works from the projection. The store still allows only the owner, or a review-capable user on a completed revision.
7. **Support references.** `partial_support_references` (pointers into KB evidence) are left out of the reviewer's gap specifications, because the reviewer may lack evidence access.
8. **`aria-disabled` and one extra file.** The owner's Approve uses `aria-disabled` instead of `disabled`, so the button and its tooltip stay reachable by keyboard; the server refuses the action regardless. `static/css/knowledge_coverage.css` gives `[aria-disabled="true"]` the existing disabled look; this file is outside the command's stage list.
9. **`public_meta`** moved to `knowledge_audit/recommendation_store.py`; `recommendation_api.py` imports it.
10. **Revalidation drift.** `scripts/knowledge_recommendation_revalidate.py` compares a source run's settings with the current `manifest()`. Coverage runs created before this step lack `recommendation_review_policy` and will report `audit_runtime_identity_drift` there, as happened when `dedupe_policy` was added.
11. **Browser contexts.** In this Chromium build, two contexts of one browser shared the session cookie (the reviewer page resolved to the owner). The harness therefore signs in as the reviewer on a second page of the same context, approves, closes the page and signs back in as the owner.

### Changed existing tests

- `tests/test_knowledge_recommendations.py`: new `REVIEWER` constant. `test_immutable_coverage_recommendation_review_export_revisions_and_duplicate_rows` now approves as user 2 with `REVIEWER`, because the owner can no longer approve by default. `test_late_conflict_blocks_approval_...` and `test_legacy_metadata_policy_...`: signature only. `test_owned_csrf_review_capability_and_pinned_downloads` sets `KNOWLEDGE_COVERAGE_REQUIRE_SECOND_REVIEWER=false`, because the owner approves through the API there.
- `tests/test_knowledge_run_export.py`: the one approval is made by user 2 with `REVIEWER`; the rejections and the later `needs_changes` are signature only.
- `tests/test_web_permissions.py`: the two new routes added to the route inventory.
- `tests/knowledge_run_export_browser_app.py`: sets `KNOWLEDGE_COVERAGE_REQUIRE_SECOND_REVIEWER=false`, because that harness checks run-level export selection and the owner approves there.
- `tests/knowledge_recommendations.browser.cjs` and `tests/knowledge_recommendation_browser_app.py`: the owner's Approve is asserted disabled. A second synthetic user (`coverage_results_view` and `coverage_recommendation_review` only) approves by keyboard from "Waiting for my review". New check `owner_approve_disabled_second_reviewer_approves_from_waiting_list`.

### Tests added

- `tests/test_faq_taxonomy.py`: the legacy inline footer parses; prose and unmarked text stay unparsed; `format_chunk` puts the footer on its own line in both branches and both parse back.
- `tests/test_knowledge_recommendations.py`: `test_numbers_are_compared_by_value` (11 cases).
- `tests/test_recommendation_second_reviewer.py` (4 tests): the owner's own decisions and the setting off; a second user with the capability; a second user without it; no leaks. Markers are seeded in the customer query (present in the source rows) and in the KB evidence (present in the snapshot), and neither appears in `reviewer_view` or `list_reviewable`.

### AGENTS.md note

- **Footer parsing.** It changes what the KB editor and the audit snapshot read from legacy chunks. The chat answer path doesn't use this parser, so retrieval and answers are unchanged. A chunk's stored text changes only when a person saves it in the editor; it is then written in the line-start form.
- **Numeric guard and second reviewer.** These change only recommendation checks and permissions.
- **Tests and benchmarks.** No retrieval or answer-quality test applies. No performance change, so no benchmark is required.

### Checks

In conda `faq`:

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_knowledge_recommendations.py tests/test_recommendation_second_reviewer.py tests/test_web_permissions.py tests/test_validate_environment.py
129 passed, 30 warnings, 24 subtests passed in 20.01s

conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file .env --mode staging | grep -i "summary"
Summary: 0 critical, 27 warning, 4 informational

conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file Production_ENV --mode production | grep -i "summary"
Summary: 6 critical, 24 warning, 4 informational

conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches

conda run --no-capture-output -n faq python scripts/audit_offline_frontend.py
Offline frontend audit: PASS

git diff --check
no output, exit 0
```

Both env summaries equal those of the same files without the new key, so the 6 production critical findings pre-date this step. For the new key, the validator prints only `set (optional; restart: FastAPI)`.

Before the commit, the two affected browser harnesses passed on their own: `knowledge_recommendations.browser.cjs` (7 checks) and `knowledge_run_export.browser.cjs`.

Clean-checkout full run of `faeedae` (load average 0.45 before the run; `BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 scripts/run_offline_tests.sh` in a temporary worktree, then removed). This run also covers step 13:

```text
1210 passed, 26 deselected, 59 warnings, 295 subtests passed in 338.57s (0:05:38)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

These results were then added to this log and the commit was amended; the amendment changes only this file.

## [15] Integration check, AGENTS.md sync and release-readiness record

This step checks that steps 00 to 14 fit together, makes the docs match the code, and writes `docs/knowledge-gap-audit/RELEASE_READINESS.md`.

### Integration fixes

**a. Codes.** An AST scan of `knowledge_audit/` found 187 distinct codes in `AuditError("…")` literals, counting both branches of a conditional code. A code counts as surfaced when its own string is stored on a row, run or recommendation record, written to an export or sent as an API detail. Every boundary masks other codes (generic 409/500 text, `audit_failed`, `failures.category`) or translates them into a fixed sentence.

- 12 surfaced codes were in no allow-list, and 3 review refusals were added for consistency. Added to `SAFE_API_CODES` in `knowledge_audit/api.py`:
  - kept on run records by `CoverageJobs.work` (`invalidate`/`interrupt` sets): `audit_serving_drift`, `audit_identity_unpinned`, `snapshot_identity_mismatch`, `candidate_snapshot_mismatch`, `audit_access_revoked`, `checkpoint_identity_mismatch`, `checkpoint_content_mismatch`. `candidate_snapshot_mismatch` is also stored on rows by `CoverageEvaluator.evaluate`;
  - kept on recommendation records by `RecommendationJobs.work`: `recommendation_source_drift` and `run_already_owned` (`audit_serving_drift` too);
  - written into `review_unavailable_reasons` and run-export projection reasons: `recommendation_metadata_policy_changed`;
  - the other `decide` refusals, so they are reported like `second_reviewer_required`: `recommendation_not_reviewable`, `recommendation_source_requires_review`, `invalid_review_decision`.
- Added to `ERROR_CODES` in `knowledge_audit/pipeline.py`: `empty_normalized_query` and `preparation_components_missing`, which `QueryPreparer.prepare` stores in a row's `preparation_errors`. Neither can be raised inside `assess` or escape `prepare`, so `evaluate`'s handling is unchanged.
- After these additions, 95 raised codes are allow-listed and the other 92 are in `INTERNAL_ONLY` in the new test, each with a one-line reason.
- `static/js/knowledge_coverage.js` had no label for 12 review codes that predate the review: `evidence_conflict`, `verification_unresolved`, `incompatible_conditions`, `entry_too_long`, `evaluation_failed`, `subset_batch_uncertainty`, `batch_support_unresolved`, `batch_uncertain`, `compatibility_unverified`, `bounded_bundle_search_unresolved`, `reconciliation_token_overflow`, `verification_token_overflow`. English labels were added. The file has one English `LABELS` map and no Persian text, so English is the only language it uses.

**b. Manifest.** `CoverageSettings.manifest()` `"schema"` is `coverage-settings-6`. Runs created under `coverage-settings-5` stop with `audit_runtime_identity_drift`, as after steps 07, 08 and 12.

**c. Env keys.** No change needed. The 28 `KNOWLEDGE_COVERAGE_*` and `TEI_RERANK_*` keys in `SPECS` are exactly the keys the non-test code reads, and all 28 are in `env.example`, `.env.example.generated`, `Production_ENV.example`, `.env` and `Production_ENV`. The local files were checked by a script that printed key names and booleans only. `KNOWLEDGE_COVERAGE_ENABLED` is `false` in `Production_ENV` and `Production_ENV.example`.

**d. CSV contract.** `docs/knowledge-gap-audit/DASHBOARD_AND_CSV_CONTRACT.md` gained "Readiness fixes: current column lists", generated from `knowledge_audit/export.py`: the column groups in order (34 + 55, then the 9 A6.1 execution, 3 A6.2 operations and 1 chain columns with their conditions), `residual_review_codes`, `deduplicated_from_row_id`, chain-only `source_run_id`, the chain export manifest keys, `reviewer_user_id` and `run_owner_id` in the review data, and `coverage-settings-6`.

### AGENTS.md changes

- Under "FastAPI endpoint paths": "Knowledge-coverage and recommendation routes" (43 routes, generated as the difference between `main.app.routes` imported in-process with `KNOWLEDGE_COVERAGE_ENABLED=true`/`ENVIRONMENT=staging` and with the flag `false`, with sockets and `psycopg2.connect` blocked as in `tests/offline_guard.py`), noting that `knowledge_audit.api.mount` includes the router only when both hold; and "Routes from `internal_evaluation_api.py`" (3 routes).
- Under "Configuration": the coverage gate line, and "`pytest.ini` now exists." in front of the rest of the old sentence.
- Under "Tests and benchmarks": the three `scripts/benchmark_coverage_*.py` scripts with one line each, replacing "no benchmark runner or benchmark command was found".

### Changed existing tests

| Test | Old | New | Why |
|---|---|---|---|
| `tests/test_coverage_depth_settings.py::test_defaults_keep_the_settings_manifest_unchanged` | `manifest['schema'] == 'coverage-settings-5'` | `manifest['schema'] == 'coverage-settings-6'` | The schema string moved in 1b. Every other assertion is unchanged. |

No other existing test changed. The full offline suite in the main checkout passed with the new allow-list entries (below).

### Tests added

- `tests/test_coverage_code_registry.py` (4 tests): every raised literal is allow-listed or internal-only; `INTERNAL_ONLY` is disjoint from the allow-lists and has no stale entries; an internal-only code never appears as a string outside `AuditError(...)` except at the two translation sites (`safe_call`'s 404 and `run_export_api.MESSAGES`); every code in `BLOCKING_CODES`, `RESIDUAL_CODES`, `SEARCH_CODES` and `NOTE_CODES` has a label in each `LABELS*` map. A mutation check (removing `audit_access_revoked` from `SAFE_API_CODES` and the `evidence_conflict` label) failed two tests; both were restored.
- `tests/test_coverage_manifest_versions.py` (1 test): `schema == "coverage-settings-6"` and the nine policy keys with their values. The test also ties the hard-coded `failure_policy`, `operational_policy` and `checkpoint_policy` strings, and `referral_guard_version` and `dedupe_policy`, to the `VERSION` constants of their modules.

### Decisions not covered by the command

No decision was put to the person running this step. Recorded for review:

1. **What "reaches the API" means.** A code translated into a fixed sentence (`artifact_not_found`/`invalid_artifact_id` as 404 "Audit resource not found", the six `run_export_api.MESSAGES` codes, the two cancel refusals) is internal-only, because its string never leaves the process. The test pins those translation sites.
2. **Review refusals allow-listed.** `recommendation_not_reviewable`, `recommendation_source_requires_review` and `invalid_review_decision` were masked while `second_reviewer_required` and now `recommendation_metadata_policy_changed` were shown. All five are fixed codes from `RecommendationStore.decide`.
3. **Settings codes stay internal-only.** `runtime()` loads the settings outside `safe_call`, so a settings error is a generic 500 whatever the allow-list says. Adding the codes would change nothing.
4. **Predating AGENTS.md drift not fixed.** Twelve routes on `main` (`681cc95`) are missing from the AGENTS.md lists, and `requirements.lock.txt` and `requirements.runtime.candidate.txt` exist although AGENTS.md says no `requirements*.txt` was found. Both predate this branch; the command allows only the listed changes. Both are open items in `RELEASE_READINESS.md`.
5. **`coverage-csv-6` not bumped.** Steps 04 and 12 added columns under the same CSV schema string. Bumping it changes the export contract, so it is an open item.

### AGENTS.md note

This step changes documentation, labels, allow-lists and the manifest schema string. Retrieval, prompts, models and the chatbot are unchanged, so no retrieval or answer-quality test applies. No performance change; the benchmarks below are recorded as the final baseline.

### Checks

In conda `faq`, before commit:

```text
timeout 1800 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q
1215 passed, 26 deselected, 59 warnings, 295 subtests passed in 341.41s (0:05:41)

node --test tests/knowledge_coverage.frontend.test.cjs
# tests 6, # pass 6, # fail 0
```

The suite grew from 1210 in step 14 to 1215: the 4 + 1 new tests.

Section 3 step 1, fast checks (before commit, so `git diff --check cda143d..HEAD` covered steps 00 to 14; repeated after commit below):

```text
conda run --no-capture-output -n faq python -m compileall -q knowledge_audit utils scripts
exit 0
for f in $(git diff --name-only cda143d..HEAD -- 'static/js/*.js'); do node --check "$f" || echo "FAIL $f"; done
no output (static/js/knowledge_coverage.js, static/js/knowledge_recommendations.js)
git diff --check cda143d..HEAD
no output, exit 0
conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches
```

Section 3 step 2, benchmarks (load average 1.33 at the start, right after the suite):

```text
conda run --no-capture-output -n faq python scripts/benchmark_coverage_budgets.py
{"boundaries_per_iteration": 12, "checkpoint_only": {"measurements_ms": [477.924, 427.012, 423.857], "median_ms": 427.012}, "checkpoint_with_allowance": {"measurements_ms": [716.815, 722.887, 724.625], "median_ms": 722.887}, "input_rows": 918, "iterations": 3, "live_dispatches": 0, "scope": "mocked_file_io_no_service_throughput", "version": "a62-file-io-1"}

conda run --no-capture-output -n faq python scripts/benchmark_coverage_progress.py
{"baseline_full_rows_checkpoint_and_progress": {"median_ms": 826.223, "reads": {"index": 0, "metadata": 4600, "row": 4595}}, "baseline_full_rows_poll": {"median_ms": 868.995, "reads": {"index": 0, "metadata": 4595, "row": 4590}}, "indexed_checkpoint_and_progress": {"median_ms": 35.202, "reads": {"index": 10, "metadata": 20, "row": 5}}, "indexed_poll": {"median_ms": 7.95, "reads": {"index": 5, "metadata": 10, "row": 0}}, "iterations": 5, "model_dispatches": 0, "rows": 918, "scope": "synthetic_file_io_only"}

conda run --no-capture-output -n faq python scripts/benchmark_coverage_dedupe.py
{"calls_by_role": {"aspects": 50, "batch": 50, "scope": 50, "verification": 100}, "copied_rows": 0, "distinct_questions": 40, "iterations": 3, "median_wall_ms": 15101.372, "model_calls": 250, "retrieval_fetches": 100, "rows": 50, "scope": "mocked_model_and_retrieval", "variant": "dedupe_off", "wall_ms": [15125.198, 15101.372, 15073.512]}
{"calls_by_role": {"aspects": 40, "batch": 40, "scope": 40, "verification": 80}, "copied_rows": 10, "distinct_questions": 40, "iterations": 3, "median_wall_ms": 13201.804, "model_calls": 200, "retrieval_fetches": 80, "rows": 50, "scope": "mocked_model_and_retrieval", "variant": "dedupe_on", "wall_ms": [13201.804, 13025.809, 13273.244]}
{"iterations": 3, "measurements_ms": [231.224, 184.675, 183.0], "median_ms": 184.675, "rows": 918, "sources": 40, "variant": "map_rebuild_918"}
```

Read counts and call counts equal the step 11 and step 12 records; medians are within the run-to-run spread recorded there.

Section 3 step 3, regression tests for the findings (37 node IDs, listed per finding in `RELEASE_READINESS.md`; parametrized cases expand to 57):

```text
timeout 900 conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -q <the 37 node IDs>
57 passed, 3 warnings, 10 subtests passed in 50.26s
```

After commit, the fast checks were repeated so that `git diff --check cda143d..HEAD` covers this commit:

```text
python -m compileall -q knowledge_audit utils scripts: exit 0
node --check: no failures (static/js/knowledge_coverage.js, static/js/knowledge_recommendations.js)
git diff --check cda143d..HEAD: no output, exit 0
scripts/check_tracked_secrets.py: tracked secrets: 0 matches
```

Section 3 step 4, clean-checkout full run. `/tmp/faq-a21-browser-node` exists, so the browser stage ran with `REQUIRE_BROWSER=1`. A first attempt on the initial commit was stopped by hand before it finished, to correct one AGENTS.md phrase (the dedupe benchmark prints three JSON lines, not one); it produced no result and is not reported. The run below is on the amended commit `1c0a7d1`. `uptime` before it showed a load average of 0.73, the host's normal level.

```text
uptime
git worktree add /tmp/faq-clean-15 HEAD
cd /tmp/faq-clean-15 && BROWSER_NODE_DIR=/tmp/faq-a21-browser-node REQUIRE_BROWSER=1 timeout 3600 conda run --no-capture-output -n faq scripts/run_offline_tests.sh; status=$?
cd /root/projects/faq && git worktree remove --force /tmp/faq-clean-15; echo "exit $status"
1215 passed, 26 deselected, 59 warnings, 295 subtests passed in 341.35s (0:05:41)
pytest: PASS (0 failed)
node frontend tests: PASS (3 harnesses)
Offline frontend audit: PASS
offline frontend audit: PASS
tracked secrets: NOT RUN (no local env files)
tracked-secret check: PASS
browser knowledge_coverage.browser.cjs: PASS
browser knowledge_execution.browser.cjs: PASS
browser knowledge_operations.browser.cjs: PASS
browser knowledge_recommendations.browser.cjs: PASS
browser knowledge_run_export.browser.cjs: PASS
browser harnesses: PASS (5 harnesses)
exit 0
```

The pytest count equals the main-checkout run. The clean checkout has no local env files, so the secret stage's NOT RUN result is expected; the main checkout's scan passed. These results were then added to this log and to `RELEASE_READINESS.md`, and the commit was amended; the amendment changes only those two files.

## [17] Role-based knowledge-coverage access, same in every environment

### Owner decision

On 2026-10-19 the owner decided that the audit is role-based and behaves the same in development, staging and production. Access comes from roles that already exist, not from per-user grants, and no audit code reads `ENVIRONMENT`. The audit is on unless `KNOWLEDGE_COVERAGE_ENABLED=false`.

### Role table

`COVERAGE_ROLE_CAPABILITIES` in `web_permissions.py`, next to `ROLE_PERMISSIONS`. `permissions_for_user(role, user_id)` returns `permissions_for(role) | COVERAGE_ROLE_CAPABILITIES.get(role, ∅)` while `coverage_enabled()`, and `permissions_for(role)` when it is off or the flag is invalid. The signature is unchanged; `user_id` is no longer used.

| Role | Capabilities |
|---|---|
| `admin` | `coverage_run_start`, `coverage_results_view`, `coverage_evidence_view`, `coverage_export_download`, `coverage_recommendation_review` |
| `dashboard_viewer` | `coverage_results_view`, `coverage_evidence_view`, `coverage_export_download` |
| every other role | none |

Unchanged: the second-reviewer rule (an owner cannot approve their own run's recommendations, so approval now needs a second admin), the `audit_access_revoked` check, and every `require(...)` capability check in the API.

### Changes

- **Gate.** `knowledge_audit.settings.coverage_enabled` returns true when `KNOWLEDGE_COVERAGE_ENABLED` is unset, `true`/`false` (stripped, case-insensitive) as given, and raises `invalid_coverage_flag` for any other value, the empty string included. `require_coverage_enabled` still raises `coverage_disabled` when it is off. `mount(app)` includes the router whenever `coverage_enabled()` is true.
- **Live-run guard.** `knowledge_audit.runtime.confirm_staging` is now `confirm_live_run(*, confirmed, model=False, snapshot=False)`. It keeps `require_coverage_enabled()` and the explicit confirmation, and replaces the loopback and `.env` comparison with a non-empty check of `TEI_EMBED_URL`/`VLLM_URL` (model) and `POSTGRES_HOST`/`QDRANT_HOST` (snapshot) through a new `require_configured(*keys)`. `build_engine` in `knowledge_audit/service.py` checks `TEI_RERANK_URL` the same way. Callers updated: `knowledge_audit/api.py` (snapshot capture), `knowledge_audit/recommendation_jobs.py`, `knowledge_audit/service.py` and the seven audit CLIs.
- **CLIs.** `scripts/knowledge_audit_prepare.py`, `knowledge_coverage_calibrate.py`, `knowledge_coverage_diagnose.py`, `knowledge_coverage_pilot.py`, `knowledge_coverage_resources.py`, `knowledge_recommendation_pilot.py` and `knowledge_recommendation_revalidate.py` document `--confirmed`; `--confirmed-staging` stays as a hidden alias (`help=argparse.SUPPRESS`, same `dest="confirmed"`). `knowledge_audit_p0_baseline.py`, `knowledge_coverage_cleanup.py` and `knowledge_coverage_stability_report.py` had no confirmation flag.
- **Manifest.** `CoverageSettings.manifest()` replaces `access_grants_sha256` with `"access_policy": {"version": "coverage-roles-1", "roles_sha256": canonical_sha256(<COVERAGE_ROLE_CAPABILITIES with sorted lists>)}`, and `"schema"` is `coverage-settings-7`. Runs created before this change report `audit_runtime_identity_drift` on resume. The owner accepted that.
- **Validator.** `scripts/validate_environment.py`: the grants spec and the production relationship check are removed; `KNOWLEDGE_COVERAGE_ENABLED` is `kind="bool", default="true", allowed=("true", "false")`; the `ENVIRONMENT` spec no longer names the coverage gate.
- **Env files.** `.env`, `env.example`, `Production_ENV.example` and `.env.example.generated`: the grants line and its comment are removed, `KNOWLEDGE_COVERAGE_ENABLED=true` has the new comment, and the second-reviewer comment names admins. In `.env` only these lines changed: `KNOWLEDGE_COVERAGE_ENABLED` (comment; the value was already `true`), `KNOWLEDGE_COVERAGE_ACCESS_GRANTS` (removed) and `KNOWLEDGE_COVERAGE_REQUIRE_SECOND_REVIEWER` (comment). `ENVIRONMENT` is unchanged. `Production_ENV` was skipped, because the owner is recreating it. `env.review.example` also lost its grants line, because the required `git grep` covers it.
- **Docs.** `AGENTS.md` (the two coverage-gate sentences only), `docs/configuration/PRODUCTION_ENV_REFERENCE.md` (the flag row leaves "must be exactly these"; the `ENVIRONMENT` row and bullets no longer mention the audit; the audit section is "every environment", with the role list and the production note on `KNOWLEDGE_COVERAGE_ARTIFACT_DIR`, the production vLLM and TEI, `KNOWLEDGE_COVERAGE_PACE_MS` and the shared request limiter), `docs/configuration/ENVIRONMENT_VARIABLES.md`, and under `docs/knowledge-gap-audit/`: `RELEASE_READINESS.md` (dated note; both Gate C flag items and checklist step 17 withdrawn; step 2 now asks for a second admin), `DASHBOARD_AND_CSV_CONTRACT.md`, `OPERATIONAL_RUNBOOK.md` and `A2_1_CORRECTION_REPORT.md`. Older reports that describe how past runs were guarded are left as history.
- **Release-evaluation tools.** `scripts/_staging_guard.py`, `scripts/retrieval_eval.py` and `scripts/answer_quality_eval.py` stay staging-only. They are release-test tools, and `AGENTS.md` forbids connectivity tests against production. The one approved exception is below.

### Removed keys and codes

- Env key `KNOWLEDGE_COVERAGE_ACCESS_GRANTS`: `_coverage_grants` in `web_permissions.py`, `CoverageSettings.access_grants` and `grants_for` in `settings.py`, its `SPECS` entry, and all env-file lines.
- `coverage_enabled_in_production`: the raise, and its entries in `SAFE_API_CODES`, `ERROR_CODES`, `SAFE_ERRORS`, the `jobs.py` interrupt list and the validator relationship check. `static/js/*.js` had no label for it.
- `invalid_coverage_access_grants`, from `INTERNAL_ONLY` in `tests/test_coverage_code_registry.py`.
- `unconfirmed_service_target`: nothing raises it any more, so it is gone from `INTERNAL_ONLY`.
- `staging_confirmation_required`, renamed to `live_run_confirmation_required`. Other scripts that raise a `RuntimeError` with the same text (`kb_taxonomy_p4_compare.py`, `production_repair_acceptance.py`) are not audit code and are unchanged.

### New codes

- `invalid_coverage_flag`: `SAFE_API_CODES`.
- `audit_service_unconfigured`: `SAFE_API_CODES`, `ERROR_CODES`, `SAFE_ERRORS` and the `jobs.py` interrupt list, where `coverage_enabled_in_production` was, so a run that fails for a missing endpoint records the reason.
- `live_run_confirmation_required`: `INTERNAL_ONLY`. Only a CLI run without `--confirmed` raises it, and the CLI prints it.

### Decisions not covered by the command

The person running this step approved these:

1. **`scripts/_staging_guard.py` docstring.** The required `git grep` matched its docstring "Same comparison as knowledge_audit.runtime.confirm_staging, plus ENVIRONMENT." Only that docstring changed; it now describes the check itself. The guard's behavior is unchanged.
2. **`scripts/knowledge_coverage_resources.py`.** It had its own `TEI_RERANK_URL` loopback and `.env` check. It now uses the same non-empty `require_configured` check, so `unconfirmed_service_target` could be deleted.

Also recorded, with no question asked:

3. **Partial capability sets in tests.** No real role has results view and export without evidence view. Four tests checked that restricted projection through grants, so they now narrow `COVERAGE_ROLE_CAPABILITIES['admin']` with `monkeypatch.setitem`. With the real roles, the restricted-export path is not reachable today.
4. **Empty flag value.** `KNOWLEDGE_COVERAGE_ENABLED=` (empty) raises `invalid_coverage_flag`, as the command says for any value other than `true` or `false`. Only an unset key means on.

### Changed existing tests

| Test | Change |
|---|---|
| `tests/test_coverage_deployment_gate.py::test_coverage_enabled_truth_table` | New table: unset and `true` are on in every environment; `false` is off; `1` and `""` raise `invalid_coverage_flag`. |
| `::test_production_refuses_enabled_audit` → `::test_production_runs_enabled_audit` | Renamed; with `ENVIRONMENT=production` the flag is on and `require_coverage_enabled` passes. |
| `::test_mount_only_on_staging` → `::test_mount_follows_flag_in_every_environment` | Renamed; mounts in staging, production and development when the flag is unset or `true`, and not when it is `false`. |
| `::test_entry_points_fail_before_work` | Parameter `confirm_staging` → `confirm_live_run`. |
| `::test_permissions_cached_and_deny_by_default` → `::test_permissions_from_role_without_loading_settings` | The grant cache is gone. Asserts the admin's role capabilities, with none for `false` or an invalid flag, and that settings are never loaded. |
| `::test_validator_rejects_enabled_production` → `::test_validator_accepts_enabled_production` | The validator accepts `true`/`false` under production and flags `1`/`maybe` as critical. |
| `tests/test_coverage_order_verification.py` helper `patched_engine_inputs` (used by `::test_build_engine_uses_the_pinned_pass_count`) | Patches `confirm_live_run`; the `.env` reranker-target patch is gone. This is the loopback and `.env` target test. |
| `tests/test_coverage_code_registry.py` `INTERNAL_ONLY` | `live_run_confirmation_required` replaces `staging_confirmation_required`; `unconfirmed_service_target` and `invalid_coverage_access_grants` removed. |
| `tests/test_coverage_manifest_versions.py::test_manifest_schema_and_policy_keys` | `coverage-settings-7`; `access_policy` expected; `access_grants_sha256` absent. |
| `tests/test_coverage_depth_settings.py::test_defaults_keep_the_settings_manifest_unchanged` | `coverage-settings-7`. |
| `tests/test_coverage_depth_settings.py::test_api_entry_budget_defaults_to_and_is_bounded_by_configured_maximum` | Grants removed; the admin role grants access. |
| `tests/test_coverage_continuation.py` fixture `client_runtime`, `tests/test_coverage_dedupe.py` fixture `client_store`, `tests/test_coverage_sizing.py` fixture `client_runtime` | Grants removed; the admin role grants access. |
| `tests/test_coverage_sizing.py::test_estimate_endpoint_shape_and_permissions` | No run-start is now `dashboard_viewer`; the test takes the `setup` fixture. |
| `tests/test_knowledge_coverage_access_jobs.py::test_default_deny_real_auth_owner_csrf_and_restricted_export` | Alice is `user` (403), then `admin` (200); bob is `admin`; restricted export via the narrowed role map. |
| `tests/test_knowledge_coverage_access_jobs.py::test_upload_mapping_no_arbitrary_paths_and_full_input_pilot_export` | Grants removed. |
| `tests/test_knowledge_coverage_access_jobs.py::test_configuration_validation_and_propagation` | The `KNOWLEDGE_COVERAGE_ACCESS_GRANTS` parameter case is removed, because the key no longer exists; the other five cases are unchanged. |
| `tests/test_knowledge_coverage_calibration.py::test_calibration_api_default_deny_ownership_export_projection` | `user` then `admin`; partial sets via the narrowed role map; bob is `admin`. |
| `tests/test_knowledge_coverage_corrections.py::test_immutable_export_pair_survives_row_mutation_and_repeated_downloads` | Grants removed; restricted case via the narrowed role map. |
| `tests/test_knowledge_execution_recovery.py::test_full_mode_api_idempotency_csrf_owner_and_revoked_grant` | Two admins; revocation is now a role change to `user`. |
| `tests/test_knowledge_recommendations.py::test_owned_csrf_review_capability_and_pinned_downloads` | Two admins; the no-review check is the owner as `dashboard_viewer`. |
| `tests/test_knowledge_run_export.py::test_run_export_api_owner_csrf_explicit_review_and_permission_revocation` | Two admins; partial sets via the narrowed role map, restored before bob. |
| `tests/test_web_permissions.py::test_role_by_api_route_matrix`, `::test_login_landing_pages_and_forged_links`, `::test_dashboard_viewer_exact_grants_navigation_and_read_only_template` | Expected permissions are now `ROLE_PERMISSIONS | COVERAGE_ROLE_CAPABILITIES` for the role, because the audit is on by default. These failed in the first full run (below). `ROLE_PERMISSIONS` itself is unchanged and still asserted. |
| `tests/knowledge_coverage_browser_app.py`, `tests/knowledge_recommendation_browser_app.py` | Grants env removed; both synthetic accounts are admins, so the reviewer is a second admin. The browser harnesses were not run (not required). |

No existing test was deleted.

### Tests added

`tests/test_coverage_role_access.py`, 4 tests (11 cases):

1. `test_gate_is_the_flag_alone`, for `ENVIRONMENT` development, staging, production and unset: with the flag unset, `coverage_enabled()` is true and `mount()` includes `/knowledge-coverage`; with `false` both are off; `maybe` raises `invalid_coverage_flag`.
2. `test_roles_grant_coverage_capabilities`, for the same four environments: `admin` gets all five capabilities; `dashboard_viewer` gets exactly the three read capabilities; `user`, `moderator`, `analytics_viewer`, `knowledge_editor` and an unknown role get none; with the flag `false`, nobody gets any.
3. `test_page_and_sidebar_follow_role` (web-auth fixtures, TestClient): `dashboard_viewer` gets 200 on `GET /knowledge-coverage` and the "Knowledge coverage" link on `/app`; `user` gets 403 and no link.
4. `test_live_run_guard_uses_configured_endpoints`: with `ENVIRONMENT=production` and non-loopback values (`http://10.0.0.5:8000/v1` and others), `confirm_live_run(confirmed=True, model=True, snapshot=True)` passes; each key emptied in turn raises `audit_service_unconfigured`; not confirmed raises `live_run_confirmation_required`.

### AGENTS.md note

Retrieval, prompts, models and the chatbot are unchanged, so no retrieval or answer-quality test applies. This is no performance change, so no benchmark was run.

### Checks

In conda `faq`, before commit:

```text
conda run --no-capture-output -n faq python -m compileall -q knowledge_audit scripts web_permissions.py
exit 0
git diff --check
no output, exit 0
conda run --no-capture-output -n faq python scripts/check_tracked_secrets.py
tracked secrets: 0 matches
git grep -n "KNOWLEDGE_COVERAGE_ACCESS_GRANTS\|coverage_enabled_in_production\|grants_for\|confirm_staging" -- . ':!docs/knowledge-gap-audit/READINESS_FIX_LOG.md'
no output, exit 1
```

Full suite, first run after all changes:

```text
conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q
5 failed, 1227 passed, 26 deselected, 55 warnings, 295 subtests passed in 337.80s (0:05:37)
FAILED tests/test_web_permissions.py::test_role_by_api_route_matrix[admin]
FAILED tests/test_web_permissions.py::test_role_by_api_route_matrix[dashboard_viewer]
FAILED tests/test_web_permissions.py::test_login_landing_pages_and_forged_links[admin-/app-/app-None]
FAILED tests/test_web_permissions.py::test_login_landing_pages_and_forged_links[dashboard_viewer-/app-/app-None]
FAILED tests/test_web_permissions.py::test_dashboard_viewer_exact_grants_navigation_and_read_only_template
```

All five pinned "no role has coverage capabilities". After the change in the table above, the failing file, then the full suite once more:

```text
conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q tests/test_web_permissions.py
24 passed, 23 warnings in 14.94s
conda run --no-capture-output -n faq python -m pytest -p tests.offline_guard -m "not integration and not artifact" -q
1232 passed, 26 deselected, 61 warnings, 295 subtests passed in 335.67s (0:05:35)
```

No clean-worktree run and no browser harnesses (not required).

### Manual check

Not done by eye. The agent running this step cannot view a browser and has no staging web credentials, so it did not start the app on staging and log in. As an automated substitute, not committed, the web-auth fixtures rendered both pages for synthetic users through TestClient:

```text
role=admin            /app 200, link present; /analytics 200, link present
role=dashboard_viewer /app 200, link present; /analytics 200, link present
role=user             /app 200, link absent;  /analytics 403 (no analytics permission), link absent
```

The by-eye check on staging with an admin, a dashboard viewer and a plain user is still owed, after FastAPI is restarted on this commit.
