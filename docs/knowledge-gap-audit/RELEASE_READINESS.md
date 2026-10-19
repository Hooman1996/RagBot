# Release readiness: knowledge-gap-audit

This is the record of which release gates the `knowledge-gap-audit` branch meets and what a person still has to do. Steps 00 to 14 each fixed one finding from the review of `cda143d`. Step 15 checked that the fixes fit together. A gate is marked Done only when every item in it is Done, and an item is Done only when its evidence was actually produced and recorded.

**Owner decision, 2026-10-19.** On 2026-10-19 the owner decided the audit is role-based and enabled in every environment: `admin` and `dashboard_viewer` get audit access from `COVERAGE_ROLE_CAPABILITIES` in `web_permissions.py`, and the audit is on unless `KNOWLEDGE_COVERAGE_ENABLED=false`, whatever `ENVIRONMENT` says (step [17] in `READINESS_FIX_LOG.md`).

## Summary

Status meanings:

- **Fixed**: the code fix and its tests are in the branch.
- **Fixed, operator step pending**: the code fix is in, but the fix only takes effect, or is only confirmed, after a person does something listed below.
- **Open**: not fixed.

All tests named below pass in the step 15 regression run (see "Step 15 validation").

| Finding | Step | Commit | Tests that prove the fix | Status |
|---|---|---|---|---|
| F3: reranker batch size from the server limit, with a verified fallback | 01 | `396f053` | `tests/test_reranker_batching.py::RerankerBatchingTests::test_server_below_contract_uses_server_limit`, `::test_capability_failures_use_contract_but_cancellation_propagates` | Fixed, operator step pending (L6 for production, Gate C) |
| F4: the offline suite runs to completion behind one command | 02 | `33bcc23` | `scripts/run_offline_tests.sh` in a clean checkout; `tests/test_request_admission.py::AdmissionLimiterLifecycleTests::test_fairness_is_documented_without_being_promised`, `tests/test_p2_concurrency.py::ConcurrentRequestTests::test_twenty_mocked_requests_overlap_and_loop_stays_responsive` | Fixed |
| F9 and F10: the audit is gated to staging; production credentials stay local | 03 | `1bb1c7b` | `tests/test_coverage_deployment_gate.py::test_production_runs_enabled_audit`, `::test_mount_follows_flag_in_every_environment` (renamed in [17]), `::test_environment_example_and_ignore_contract`; `scripts/check_tracked_secrets.py` | Staging-only gate withdrawn by the 2026-10-19 owner decision ([17]); credentials: fixed, operator step pending (credential rotation and the Git history decision, Gate C) |
| Depth settings: audit depths and entry budget from the environment | 03a | `f30c2c1` | `tests/test_coverage_depth_settings.py::test_pipeline_uses_configured_depths_and_budget_ceiling`, `::test_run_started_under_other_depths_is_identity_drift` | Fixed |
| F1: a proof is accepted only after every conflict has a verdict | 04 | `e74cbfe` | `tests/test_coverage_conflict_verdicts.py::test_contradicting_conflict_blocks_the_proof`, `::test_unassessed_conflict_is_undetermined` | Fixed |
| F16a: `verification_token_overflow` is kept | 04 | `e74cbfe` | `tests/test_coverage_conflict_verdicts.py::test_verification_overflow_reason_is_kept` | Fixed |
| F2: KB snapshots keep public facts | 05 | `36aa98d` | `tests/test_kb_content_privacy.py::test_kb_text_keeps_public_facts`, `::test_scrubbed_entry_without_support_goes_to_review_not_recommendation` | Fixed, operator step pending (public-contact allow-list and a new snapshot, Gate A) |
| F5: ticket referrals count only for contact questions | 06 | `83f9fc3` | `tests/test_coverage_referral_guard.py::test_referral_does_not_answer_a_fee_question`, `::test_referral_for_an_unclassified_aspect_goes_to_review` | Fixed |
| F7: redacted questions get uncertain production reachability | 07 | `24d2c96` | `tests/test_coverage_redacted_reachability.py::test_covered_reachable_with_redacted_query_goes_to_review`, `::test_redacted_prior_turn_marks_the_rewrite` | Fixed |
| F6: a proof is accepted only when verification agrees in both evidence orders | 08 | `165f354` | `tests/test_coverage_order_verification.py::test_acceptance_that_depends_on_order_goes_to_review`, `tests/test_coverage_stability_report.py::test_runs_differing_only_in_batch_size_in_runtime_versions_are_compared` | Fixed, operator step pending (L2 stability protocol, Gate B) |
| F8a: refused connections and HTTP rejections do not pause runs | 09 | `78832bb` | `tests/test_audit_send_state.py::test_refused_connection_is_refunded_and_does_not_pause`, `::test_server_rejection_keeps_charge_and_does_not_pause` | Fixed |
| F16b: rewrite fallbacks are reusable checkpoints | 09 | `78832bb` | `tests/test_audit_send_state.py::test_rewrite_fallback_is_a_reusable_checkpoint` | Fixed |
| F8b: full and subset runs show a cost estimate | 10 | `f3c7424` | `tests/test_coverage_sizing.py::test_unsized_run_needs_acknowledgement`, `::test_run_over_the_limits_needs_partial_acceptance` | Fixed, operator step pending (reference pilot and raised limits, Gate B) |
| F8c: a paused run can be continued and exported as a chain | 11 | `d551baf` | `tests/test_coverage_continuation.py::test_selection_rule_with_and_without_needs_review`, `::test_chain_of_three_runs_exports_each_row_from_the_run_that_finished_it` | Fixed |
| F15: every run-creating request needs an idempotency key | 11 | `d551baf` | `tests/test_coverage_continuation.py::test_every_run_creating_request_needs_an_idempotency_key` | Fixed |
| F8d: a repeated question is evaluated once per run | 12 | `5dee7e9` | `tests/test_coverage_dedupe.py::test_identical_history_free_rows_are_evaluated_once`, `::test_eligibility_and_key_inputs` | Fixed |
| F11: retrieval and answer-quality evaluation tools | 13 | `3e5ed0d` | `tests/test_release_evaluation_tools.py::test_bootstrap_identical_runs_and_verdicts`, `::test_end_to_end_leaves_no_private_text` | Fixed, operator step pending (both live evaluations, Gate C) |
| F12: the legacy inline category footer is parsed | 14 | `9656be5` | `tests/test_faq_taxonomy.py::FaqTaxonomyParsingTests::test_legacy_inline_footer_is_the_category`, `::test_inline_prose_and_unmarked_text_are_not_a_legacy_footer` | Fixed, operator step pending (new snapshot and L4, Gates A and B) |
| F13: numbers are compared by value | 14 | `9656be5` | `tests/test_knowledge_recommendations.py::test_numbers_are_compared_by_value` | Fixed |
| F14: approvals need a second reviewer | 14 | `9656be5` | `tests/test_recommendation_second_reviewer.py::test_owner_cannot_approve_own_run_but_can_reject_or_request_changes`, `::test_second_reviewer_with_capability_approves_and_is_recorded` | Fixed, operator step pending (grant the review capability to a second user) |

Step 15 (this commit) adds `tests/test_coverage_code_registry.py` and `tests/test_coverage_manifest_versions.py`, which check that the fixes fit together. They are not tied to one finding.

## Gates

No gate is met. Every gate below has at least one Owed item.

### Gate A: staging pilot — Owed

| Item | Status | How |
|---|---|---|
| Steps 01 to 07 committed | Done | Commits `396f053` to `24d2c96`. |
| Green suite | Done | Step 15 clean-checkout run, exit 0 (see "Step 15 validation"). |
| A new staging snapshot captured after step 14 | Owed | Checklist step 4. |
| The public-contact allow-list filled in from the KB owner's official numbers and addresses | Owed | Checklist step 3. On 2026-10-19, `KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS` was empty in the staging `.env` and in `Production_ENV`. |
| A pilot of 5 rows or fewer, compared with the A2.2 rows | Owed | Checklist step 7. |

### Gate B: full 918-row run — Owed

| Item | Status | How |
|---|---|---|
| Gate A | Owed | See above. |
| Steps 08 to 12 committed | Done | Commits `165f354` to `5dee7e9`. |
| L2 stability protocol for rows 121 and 518 passing under `STABILITY_PROTOCOL.md`, with the cited sentences read by a person | Owed | Checklist step 8. |
| L1 recorded | Owed | Checklist step 9. L1 is not defined in this repository. |
| L3 recorded | Owed | Checklist step 9. L3 is not defined in this repository. |
| L4 recorded: 0 snapshot answers containing `question category` | Owed | Checklist step 5. |
| A 5-row reference pilot and a sizing estimate | Owed | Checklist step 10. |
| Staging limits raised deliberately | Owed | Checklist step 11. |
| The full-input confirmation accepted | Owed | Checklist step 12. |

### Gate C: production release of the shared retrieval path (P1 to P3 and step 01) — Owed

**Owner decision, 2026-10-19.** The audit is role-based and enabled in every environment, production included (step [17]). Gate C covers only the shared chatbot retrieval changes (RRF, retrieval depths and reranker batching).

| Item | Status | How |
|---|---|---|
| Step 13's retrieval report passing (`docs/performance/release-retrieval-evaluation.md`) | Owed | Checklist step 14. No live report exists yet. |
| Step 13's answer-quality report passing (`docs/performance/release-answer-quality.md`) | Owed | Checklist step 14. No live report exists yet. |
| L6: the production reranker's `--max-client-batch-size`, read from its deployment configuration, with `TEI_RERANK_VERIFIED_MAX_BATCH_SIZE` set to it | Owed | Checklist step 15. |
| Production credentials rotated | Owed | Checklist step 16. |
| Removal of the old credentials from Git history decided by the owner | Owed | Checklist step 16. |
| `KNOWLEDGE_COVERAGE_ENABLED=false` in `Production_ENV` and `Production_ENV.example` | Withdrawn | Withdrawn by the 2026-10-19 owner decision: the audit is enabled in every environment ([17]). |
| `KNOWLEDGE_COVERAGE_ENABLED=false` (or unset) in the running production deployment | Withdrawn | Withdrawn by the 2026-10-19 owner decision: the audit is enabled in every environment ([17]). A withdrawn item does not count toward the gate. |

### Gate D: quality acceptance of the audit — Owed

| Item | Status | How |
|---|---|---|
| A human-labelled sample of at least 50 rows, stratified by outcome, at an agreement threshold the owner sets | Owed | Checklist step 13. The owner has not set the threshold. |

## Operator checklist

Run every command from `/root/projects/faq` on `knowledge-gap-audit`, on the staging host, through `conda run --no-capture-output -n faq`. None of these commands contacts production. Don't print `.env`, `Production_ENV` or any private file. Record IDs, counts and verdicts in the release log, never question, answer or KB text.

`OWNER` below is the web user ID of the person who will review the runs on the coverage page. Runs under the operator namespace `0` don't appear on the page and aren't sizing references for runs started there.

1. **Secure the staging host first.** Do every item in "Staging host" below.

2. **Give a second web user the `admin` role.** Recommendation approval needs a second admin, who must not be the run owner. Access comes from the role ([17]); no environment change grants it. Then check the staging `.env`, which [17] changed, and restart FastAPI:

   ```bash
   conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file .env --mode staging | grep '^Summary'
   ```

   The summary must show `0 critical`.

3. **Fill in the public-contact allow-list.** Get the official support numbers, email addresses and `@domain` entries from the KB owner. Set them, comma-separated, as `KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS` in the staging `.env`. Don't invent entries. Run the check from step 2 and restart FastAPI.

4. **Capture a new staging snapshot.** On `/knowledge-coverage`, press "Capture current knowledge" and record the new snapshot ID. Snapshots captured before step 14 still start runs, but they predate the legacy footer parser.

5. **Record L4.** Count the snapshot answers that still contain `question category`. The command prints one number only:

   ```bash
   conda run --no-capture-output -n faq python -c 'import sys; sys.path.insert(0, "."); from dotenv import load_dotenv; load_dotenv(".env"); from knowledge_audit.settings import load_coverage_settings; from knowledge_audit.store import CoverageStore; s = CoverageStore(load_coverage_settings().artifact_dir).snapshot(sys.argv[1], int(sys.argv[2])); print(sum("question category" in (r.get("answer") or "").lower() for r in s["records"]))' SNAPSHOT_ID OWNER
   ```

   L4 passes at `0`.

6. **Import the dataset**, if it isn't already imported under `OWNER`, from the coverage page. Record its dataset ID.

7. **Gate A pilot (5 rows or fewer), compared with A2.2.** Use the five A2.2 rows (`docs/knowledge-gap-audit/A2_2_MODEL_RELIABILITY_REPORT.md`, "Single end-to-end revalidation") and the same entry budget, 300:

   ```bash
   conda run --no-capture-output -n faq python scripts/knowledge_coverage_pilot.py --owner-id OWNER pilot \
     --dataset-id DATASET_ID --snapshot-id SNAPSHOT_ID --entry-budget 300 \
     --row-ids row_bd526b97ad9940b1d6a15871aac7b0ab row_db3be7cdd0b505a4def0a73355236a6f row_7a55dfd6fb2e3bf750d99fa30e975d30 row_85acf8adf43bd6feb04d01f90927b68e row_dedce881f722f95251e3f326f002f465 \
     --confirmed-staging
   ```

   The run must end `completed`. On the coverage page, compare each row's outcome with A2.2 run `r_bcc2b95676b8184e3bb4e6f7d25d8b84`, and record every row whose outcome changed, with the review code that explains it. The stability report can't make this comparison, because the code versions differ.

8. **L2 stability protocol.** Follow `docs/knowledge-gap-audit/STABILITY_PROTOCOL.md`: 12 pilot runs of rows 121 and 518 (three each at batch sizes 1, 2, 3 and 5), the read-only `scripts/knowledge_coverage_stability_report.py` over all 12 and per batch size, and a person reading row 121's cited sentences on the coverage page. Gate B needs a pass, or a pinned batch size and a passing repeat.

9. **Record L1 and L3** as defined in the review plan. Their definitions aren't in this repository; write them into the release log with the results.

10. **Reference pilot and sizing estimate.** Run a 5-row pilot under `OWNER`, with the datasources and entry budget planned for the full run, as in `docs/knowledge-gap-audit/FULL_RUN_SIZING.md` section 1. When it has completed, select "Full input" on the coverage page and record the estimate table (completions, tokens and hours: limit, expected and high).

11. **Raise the staging limits deliberately.** Using the High column, set `KNOWLEDGE_COVERAGE_MAX_COMPLETIONS`, `KNOWLEDGE_COVERAGE_MAX_TOKENS` and `KNOWLEDGE_COVERAGE_MAX_EXECUTION_SECONDS` in the staging `.env`, within the maxima in `FULL_RUN_SIZING.md` section 3. Run the check from step 2 and restart FastAPI. An estimate over 168 hours needs continuation runs (step 11 of the fix log).

12. **Full 918-row run.** Only after Gates A and B's other items are Done: on the coverage page, choose "Full input", tick the finite-limits confirmation (and "I accept that this run will pause before finishing" only if the estimate is still over a limit), and start. If it pauses, use "Continue unfinished rows" and download "Download whole input (all runs)".

13. **Gate D human labels (at least 50 rows, stratified by outcome).** The owner first sets the agreement threshold. The human-label tooling works on review packages of exactly 5 rows (1 to 3 runs of the same 5 rows), so 50 rows need at least 10 packages. Choose 5-row pilots that together cover each outcome. For each package:

    ```bash
    conda run --no-capture-output -n faq python scripts/knowledge_coverage_pilot.py --owner-id OWNER review --run-ids RUN_ID
    conda run --no-capture-output -n faq python scripts/knowledge_coverage_calibrate.py human-template --package-id REVIEW_PACKAGE_ID
    # A person who knows the FAQ fills in the template, privately.
    conda run --no-capture-output -n faq python scripts/knowledge_coverage_calibrate.py human-import --package-id REVIEW_PACKAGE_ID --labels FILLED_TEMPLATE_PATH
    ```

    `human-import` prints `coverage_agreement`, `production_sufficiency_agreement` and `aspect_agreement` for that package. No tool combines packages yet, so add the counts across packages by hand and compare the totals with the threshold.

14. **Gate C evaluations.** Follow `docs/performance/RELEASE_EVALUATION_RUNBOOK.md` sections 1 to 4 on an otherwise idle host. The verdicts come from:

    ```bash
    $PY scripts/retrieval_eval.py compare --cases "$E/cases" --sheet "$E/labels/label-sheet-labeled.csv" \
      --runs "$E/runs/baseline" "$E/runs/p1" "$E/runs/p2" "$E/runs/p3" "$E/runs/rc" \
      --baseline baseline --report docs/performance/release-retrieval-evaluation.md
    $PY scripts/answer_quality_eval.py score --sheet "$E/blind/grading-sheet-graded.csv" --key "$E/blind/grading-key.json" \
      --report docs/performance/release-answer-quality.md
    ```

    Both must exit 0 and report PASS.

15. **L6.** The owner of the production reranker deployment reads its `--max-client-batch-size` from that deployment's configuration. Don't query production from staging to find it. Then set `TEI_RERANK_VERIFIED_MAX_BATCH_SIZE` to that value in the local `Production_ENV`, and confirm that the production `TEI_RERANK_MAX_CLIENT_BATCH_SIZE` is no larger. Check the file:

    ```bash
    conda run --no-capture-output -n faq python scripts/validate_environment.py --env-file Production_ENV --mode production | grep '^Summary'
    ```

    The 6 critical findings recorded since step 03 are pre-existing empty credential placeholders. Record the L6 value in the release log.

16. **Production credentials.** The owner rotates the five production credentials that were in Git history before step 03 (`QDRANT_API_KEY`, `POSTGRES_PASSWORD`, `DEFAULT_DB_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`) and decides whether to remove them from the Git history. Rewriting history is the owner's decision; it needs a force-push and every clone to be re-cloned.

17. **Production audit flag.** Withdrawn by the 2026-10-19 owner decision: the audit is enabled in every environment ([17]). `KNOWLEDGE_COVERAGE_ARTIFACT_DIR` must point to a persistent directory on the production host.

18. **Production `ENVIRONMENT` label.** `Production_ENV.example` carries `ENVIRONMENT="development"`, copied from the production file. The owner decides whether production should say `production`, and records the decision in the release log. Since [17] the audit does not read `ENVIRONMENT`; the label still guards the reset tools. Changing it is a production configuration change and is not made from this repository.

## Staging host

The dev and staging host was compromised by a cryptominer, which was removed in step 09b. The owner must:

- [ ] change the `ubuntu` password, install the owner's SSH key and turn SSH password login off;
- [ ] rotate the GitHub credential used on the host;
- [ ] log Codex and Claude Code out and back in;
- [ ] treat the host as untrusted until it is rebuilt or reviewed.

Until then, results produced on this host, including every result in this document, came from an untrusted machine.

## Evidence log

Fix log entries, in `docs/knowledge-gap-audit/READINESS_FIX_LOG.md`:

- [00] Branch consolidation
- [01] Rerank uses server batch limit with verified fallback contract
- [02] Full offline suite runs to completion behind one command
- [03] Gate the audit to staging and keep production credentials local
- [03a] Audit retrieval depths and entry budget come from the environment
- [04] Accept a coverage proof only after every conflict in its view has an explicit verdict
- [05] KB snapshots keep public facts and scrub only secrets and validated personal identifiers
- [06] Ticket referrals count only for contact questions; unclassified aspects go to review
- [07] Redacted questions get uncertain production reachability and go to review
- [08] Accept a proof only when verification agrees in both evidence orders; add a stability report
- [09] Refused connections and HTTP rejections no longer pause audit runs; rewrite fallbacks are reusable
- [10] Full and subset runs show a server-computed cost estimate and need explicit acceptance when it exceeds the limits
- [11] Continue a paused run's unfinished rows, export the whole chain, and require idempotency keys
- [12] Evaluate a repeated question once per run, keyed on its texts, intent and prior turns
- [13] Add staging-only retrieval and answer-quality evaluation tools and the release runbook
- [14] Parse the legacy inline category footer, compare numbers by value, and require a second reviewer for approvals
- [15] Integration check, AGENTS.md sync and release-readiness record

Runbooks:

- [Release evaluation runbook (Gate C)](../performance/RELEASE_EVALUATION_RUNBOOK.md)
- [Stability protocol (L2)](STABILITY_PROTOCOL.md)
- [Full-run sizing](FULL_RUN_SIZING.md)

Live reports: none exist yet. `docs/performance/release-retrieval-evaluation.md` and `docs/performance/release-answer-quality.md` are written by Checklist step 14.

## Step 15 validation

All results below were produced on 2026-10-19 in conda `faq` with the offline pytest guard, on the staging host. The full command lines are in the `[15]` fix log entry.

Fast checks:

```text
python -m compileall -q knowledge_audit utils scripts: exit 0
node --check on static/js/*.js changed since cda143d: no failures (knowledge_coverage.js, knowledge_recommendations.js)
git diff --check cda143d..HEAD: no output
scripts/check_tracked_secrets.py: tracked secrets: 0 matches
```

Benchmarks (the final baseline; no performance change in step 15):

| Script | Result |
|---|---|
| `scripts/benchmark_coverage_budgets.py` | checkpoint only, median 427.012 ms; checkpoint with allowance, median 722.887 ms (918 rows, 12 boundaries, 3 iterations) |
| `scripts/benchmark_coverage_progress.py` | indexed checkpoint and progress, median 35.202 ms (10 index, 20 metadata, 5 row reads) against 826.223 ms for full rows; indexed poll, median 7.95 ms against 868.995 ms |
| `scripts/benchmark_coverage_dedupe.py` | 50 rows: 250 model calls and 100 retrieval fetches with copying off, 200 and 80 with it on (10 copied rows); median wall 15,101.372 ms off, 13,201.804 ms on; 918-row map rebuild, median 184.675 ms |

Regression tests for the findings (the tests named in the summary table, in one command):

```text
57 passed, 3 warnings, 10 subtests passed in 50.26s
```

Full offline suite in the main checkout, before commit:

```text
1215 passed, 26 deselected, 59 warnings, 295 subtests passed in 341.41s (0:05:41)
```

Clean-checkout full run (`scripts/run_offline_tests.sh` in a new worktree of the step 15 commit, with the browser harnesses required):

```text
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

The clean checkout has no local env files, so the secret stage's NOT RUN is expected; the main checkout's scan passed. The 26 deselections are the existing integration and artifact marker exclusions.

## Open items

| Item | Reason |
|---|---|
| Every Owed gate item above | Needs a person, live staging services or the production owner. |
| L1 and L3 definitions | They aren't written anywhere in this repository, so this document can't say what passes. The owner should record them. |
| Gate D agreement threshold | The owner hasn't set it. |
| No tool combines human-label agreement across review packages | A review package holds exactly 5 rows, so a 50-row sample is at least 10 packages, and `human-import` reports agreement per package. Combining them is manual until a tool exists. |
| The coverage CSV `schema_version` is still `coverage-csv-6` | Steps 04 and 12 added `residual_review_codes` and `deduplicated_from_row_id` without changing the string, so two `coverage-csv-6` files can have different headers. Consumers must read columns by name. Whether to move to `coverage-csv-7` is an owner decision; it changes the export contract, so it wasn't done in step 15. |
| Some request-path refusals still show a generic message | Codes in the step 15 internal-only set (for example `recommendation_source_evidence_required` and the settings-validation codes) are masked as "Audit operation could not complete" or a generic 500. Step 15 allow-listed only codes that records already keep, plus the review refusals. Others can be allow-listed if operators need the reason. |
| AGENTS.md lists 12 fewer routes than the app has | `GET /access-denied`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET /api/health/details`, `GET /api/health/live`, `GET /api/health/ready`, `POST /api/mass-answer/jobs/cleanup`, `DELETE /api/mass-answer/jobs/{job_id}`, `GET /api/mass-answer/jobs/{job_id}`, `GET /api/mass-answer/jobs/{job_id}/result`, `GET /api/metrics/admission` and `POST /api/mobile/v1/sessions/{session_id}/close` all exist on `main` (`681cc95`) and aren't listed. They predate this branch, and step 15 changed only facts this branch changed. |
| AGENTS.md says no `requirements*.txt` was found | `requirements.lock.txt` and `requirements.runtime.candidate.txt` are tracked, and predate this branch. Step 15 kept that part of the sentence as instructed. |
| Snapshots captured before step 14 are still admissible | Step 14 left `SNAPSHOT_VERSION` unchanged (decision 2 of that step). A fresh snapshot is Checklist step 4. |
| Coverage runs from before step 15 can't resume | The settings manifest moved to `coverage-settings-6`, so older runs stop with `audit_runtime_identity_drift`, as after steps 07, 08 and 12. Completed runs from before it aren't sizing references. |
| The staging host is untrusted | See "Staging host". |
