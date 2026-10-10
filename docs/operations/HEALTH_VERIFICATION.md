# Health verification and failure dispositions

## Baseline and comparison conditions

Initial checkout: `feature/structured-logging` at
`9875bb5c78f3fbbcf95f61a236366a6b4c14501f`; main at
`b306395d814af84598fa61e87b14550ddadca5ae`. The feature commit already
contained health code; health tests and handoff were untracked. Both histories
are preserved by the normal main merge. Python 3.12.12, existing `faq` environment.

The recovered earlier health report was **498 passed, 14 failed, 14 setup errors,
10 skipped, 1 deselected** (109 subtests); it excluded stalled suites. The saved
baseline overlay had the same 28 failed/error causes, plus one independently
non-reproducible logging event-count failure (41 versus 40 due to an asyncio slow
callback warning). It was not a complete passing regression run.

Fresh isolated unchanged baseline at b306395, with the same interpreter and
tracked offline guard, used:

```bash
python -m pytest -p tests.offline_guard tests --ignore=tests/test_analytics.py -q --tb=short -o faulthandler_timeout=60
```

Result: **463 passed, 14 failed, 14 setup errors, 3 skipped, 102 subtests passed**,
34.08 seconds. All security/logging tests ran; the seven known PostgreSQL SQL
integration cases were not executed. The served analytics integration test's
existing development-configuration skip applied in this baseline. No services
were contacted. Temporary guard/config copies contained no credentials.

All 28 IDs reproduced. Causes and traceback locations agree with the recovered
health run, with one explicit configuration difference: the isolated baseline
has no private `.env`, so the policy test raised `KeyError` for canonicalization,
where the original baseline/health copies raised the five-key assertion below.
Both are an invalid dependency on private local configuration; this is not claimed
as an identical traceback. No private configuration was copied to the worktree.

## The 28-case matrix

Each baseline entry below failed/errored before the health work, and each
“original health” entry had the same stated cause unless noted above. No row is
classified as a new health product regression. “Artifact unavailable” means a
retained, explicitly selected audit outside the offline unit suite, not an xfail
or a claimed pass. Temporary checkpoints verify protocol/validation behavior,
not quality or identity of absent historical production weights.

| Test ID | Phase | Actual cause (baseline / original health) | Classification | Resolution / final disposition |
| --- | --- | --- | --- | --- |
| `tests/intent_classifier/test_finetuning_pipeline.py::CheckpointCompatibilityTests::test_application_default_selects_finetuned_checkpoint` | test | AssertionError: constructor default is inspect.empty, not the former checkpoint filename. Same baseline/health cause. | Stale test | Assert explicit factory configuration; PASS. |
| `tests/intent_classifier/test_finetuning_pipeline.py::CheckpointCompatibilityTests::test_current_architecture_loads_old_checkpoint_strictly` | test | FileNotFoundError: historical checkpoint absent. Same baseline/health cause. | Missing artifact / fixture | Exercise strict legacy-format loading using a temporary synthetic checkpoint; PASS. Historical weights remain unaudited. |
| `tests/intent_classifier/test_finetuning_pipeline.py::CheckpointCompatibilityTests::test_old_checkpoint_runs_same_public_preprocessing_path` | test | TypeError: missing similarity_threshold, required, expected_sha256; historical weights also absent. Same baseline/health cause. | Stale fixture / missing artifact | Use validated temporary checkpoint and explicit parameters; PASS. Historical weight behavior not claimed. |
| `tests/intent_classifier/test_finetuning_pipeline.py::CheckpointCompatibilityTests::test_original_checkpoint_checksum_is_unchanged` | test | FileNotFoundError: historical checkpoint absent. Same baseline/health cause. | Missing artifact | Preserved as explicit artifact audit; unavailable, no fabricated checksum or passing claim. |
| `tests/intent_classifier/test_finetuning_pipeline.py::CheckpointCompatibilityTests::test_probability_above_threshold_routes_to_chitchat` | test | TypeError: missing required and expected_sha256. Same baseline/health cause. | Stale fixture | Supply explicit parameters and mark supplied deterministic test network initialized; PASS. |
| `tests/intent_classifier/test_finetuning_pipeline.py::CheckpointCompatibilityTests::test_probability_between_half_and_threshold_routes_to_banking` | test | TypeError: missing required and expected_sha256. Same baseline/health cause. | Stale fixture | Same fixture repair; threshold assertions unchanged; PASS. |
| `tests/test_kb_phrase_normalization.py::KBPhraseLexiconTests::test_current_kb_artifact_has_expected_gate_counts` | test | AssertionError: valid FAQ count 1526 versus stale 1426; regenerated phrase count 104 versus historical 100. Same baseline/health cause. | Stale assertion | Compare parser-derived counts and entry/count accounting; retain published lexicon checks; PASS. |
| `tests/test_kb_phrase_normalization.py::IntentRoutingOrthographyTests::test_travel_spacing_variants_have_identical_classifier_input_and_route` | test | TypeError: missing similarity_threshold, required, expected_sha256. Same baseline/health cause. | Stale fixture | Explicit constructor parameters; normalization/routing assertions retained; PASS. |
| `tests/test_p2_concurrency.py::StaticLifecycleAndBoundaryTests::test_database_connections_are_created_inside_worker_operations` | test | AssertionError: metadata worker call moved from AgentService to ProductionHistoryProvider; classifier worker call formatting changed. Same baseline/health cause. | Stale source assertion | Check current provider and classifier worker boundaries; real concurrency tests retained; PASS. |
| `tests/test_retrieval_normalization_consistency.py::RetrievalNormalizationConsistencyTests::test_classifier_receives_same_text_and_keeps_same_route` | test | TypeError: missing similarity_threshold, required, expected_sha256. Same baseline/health cause. | Stale fixture | Explicit constructor parameters; fixed actionable network and text assertions retained; PASS. |
| `tests/test_retrieval_normalization_consistency.py::RetrievalNormalizationConsistencyTests::test_empty_retrieval_has_stable_fallback_reason` | test | AttributeError: fake SearchEngine lacks rerank_search_results. Same baseline/health cause. | Stale fixture | Mock the enabled context reranking method without changing the application flag; PASS. |
| `tests/test_step5_query_canonicalization.py::SharedPathAndEnvironmentTests::test_chat_interfaces_share_service_while_eval_uses_http_boundary` | test | FileNotFoundError: obsolete evaluation worker/process_runtime.py source path. Same baseline/health cause. | Stale source assertion | Inspect current postgres_worker.py HTTP client boundary; PASS. Evaluation code unchanged. |
| `tests/test_step5_query_canonicalization.py::SharedPathAndEnvironmentTests::test_dev_production_and_example_enable_same_policy` | test | AssertionError: private local configuration contains five web-auth keys absent from production template. Fresh baseline: KeyError without private env; saved baseline/health: this assertion. | Environment-dependent stale test | Compare tracked canonicalization templates, not private configuration or unrelated auth-key equality; PASS. |
| `tests/test_validate_environment.py::EnvironmentValidatorTests::test_exit_codes` | test | AssertionError: expected exit 0, received 2; synthetic valid environment omitted five now-required classifier settings. Same baseline/health cause. | Stale fixture | Add synthetic classifier path/threshold/device/required/hash settings; validator unchanged; PASS. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_adversarial_set_is_not_in_master_or_training` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_class_balance_is_within_five_percentage_points` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_every_example_type_is_represented_in_each_ordinary_split` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_every_label_zero_row_references_real_faq` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_labels_are_binary_and_mapping_is_fixed` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_master_has_no_grouped_train_test_leakage` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_no_exact_duplicate_has_conflicting_labels` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_no_exact_duplicate_rows` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_reader_ignores_gitkeep_hidden_empty_and_temporary_files` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Fixture isolation / missing artifact | Reader test also runs in independent FAQReaderTests without dataset setup; PASS. Original artifact audit retained. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_reported_banking_regressions_have_kb_answer_sources` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_review_required_is_excluded_and_captures_meta_conflict` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_source_and_family_groups_do_not_cross_splits` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_split_files_exactly_partition_master` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |
| `tests/intent_classifier/test_finetuning_pipeline.py::DatasetIntegrityTests::test_text_is_never_null_or_empty` | setup | FileNotFoundError in DatasetIntegrityTests.setUpClass → read_csv: private intent_classifier_finetune.csv absent; same baseline/health traceback. | Missing training artifact | Retained artifact audit; unavailable in clean checkout. |

## Other issues found during complete verification

- Permissions inventory lacked the three new exact GET routes. Added them to the
  expected public inventory; role/CSRF/protected-route checks remain intact.
- The served analytics API/assets test imports a real PostgreSQL fixture. The
  guard correctly blocked it and the API returned 500. This is a genuine SQL
  integration test, now explicitly marked alongside the seven SQL cases rather
  than implicitly skipped by a plugin. It remains available with an authorized
  development database; its integration result is not claimed here.
- Removed the concurrency suite's global asyncio.to_thread replacement. Native
  thread context, cancellation, and bounds now run in the actual implementation.
- Determinism/hash/threshold unit tests formerly depended on private weights and
  skipped in clean checkouts. They now use temporary validated synthetic weights;
  the real published-weight metadata audit remains a separate artifact test.
- Qdrant readiness rejected the documented success string and treated grey as
  unhealthy. Fixed service-specific readiness validation and queryability policy,
  with plain-text/JSON-string, failed/malformed/unsupported, grey/red, collection
  configuration, and installed-client credential/prefix protocol coverage.

No application code beyond health reporting was changed for regression repairs.
No security test is deselected. The 26 explicitly deselected cases are eight
analytics integration cases and eighteen artifact audits (fourteen dataset,
historical checksum, two new-weight checks, one published-weight metadata audit).
No skips or xfails were introduced to conceal unit failures.

## Verification results

Commands below run from the repository root after `conda activate faq`, with
`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` recommended. No hidden PYTHONPATH or
external plugin is needed. The managed sandbox blocks cross-thread wakeups;
guarded offline runs used its authorized external execution path.

| Command | Result |
| --- | --- |
| `python -m pytest -p tests.offline_guard tests/test_health_checks.py -q` | 93 passed; 7 subtests; 15.14 s |
| `python -m pytest -p tests.offline_guard tests/test_web_auth.py tests/test_web_permissions.py -q` | 28 passed; 14.86 s |
| `python -m pytest -p tests.offline_guard tests/test_http_logging_middleware.py tests/test_background_logging.py tests/test_structured_logging.py -q` | 51 passed; 14.11 s |
| `python -m pytest -p tests.offline_guard tests/test_answering_service.py tests/test_request_admission.py tests/test_p2_concurrency.py tests/test_vllm_error_translation.py tests/test_tei_embedding_policy.py tests/test_answer_context_reranking.py -q` | 64 passed; 10 subtests; 22.18 s |
| `python -m pytest -p tests.offline_guard tests -m 'not integration and not artifact' -q -o faulthandler_timeout=60` | 570 passed; 109 subtests; 26 explicit integration/artifact deselections; 35.23 s; no failures/errors/hangs |
| `python -m compileall -q main.py web_auth.py utils/health_checks.py utils/http_logging_middleware.py tests` | Passed |
| `git diff --check` | Passed |

Installed versions reviewed: httpx 0.28.1, qdrant-client 1.16.2, MinIO 7.2.20,
psycopg2-binary 2.9.11, FastAPI 0.124.0, Starlette 0.50.0, AnyIO 4.12.0,
pytest 9.1.1. Warnings are installed SWIG and existing datetime/template API
deprecations; no health test warning contains dependency addresses or errors.
The deployed service versions and live health responses were not inspected.
Qdrant API support must be confirmed by operators; unsupported readiness fails
closed as a report and never falls back silently.

## Publication boundary

GitHub inspection found main already the default, no Actions workflows, no
repository webhooks, and no branch protection/rulesets. No deployment automation
was added or triggered. Both original branch tips must remain ancestors of the
final main merge before any branch deletion. Unrelated local ignore-rule changes,
private/generated/untracked files, and the pre-existing environment-file deletion
are excluded from commits and preserved in the primary checkout.
