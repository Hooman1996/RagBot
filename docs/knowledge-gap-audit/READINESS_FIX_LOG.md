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
