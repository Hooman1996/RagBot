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
