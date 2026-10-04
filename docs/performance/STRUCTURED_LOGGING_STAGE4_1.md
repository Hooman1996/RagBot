# Structured logging Stage 4.1 controlled DEV attribution

Measured 2026-10-04. These results describe the current DEV stack, not production capacity. No serving/model/retrieval configuration was changed.

## Source and method

- Baseline: `661c12e01b5fe0719334f1c8582315b873bc287f`, detached temporary worktree.
- Feature committed HEAD: `37a8a9fdbbf62073ec58df59499bd04064de3142`, plus the retained Stage 4 safe startup logging and routine httpx INFO suppression corrections.
- Runtime source SHA-256 fingerprint: `60cade8ccefa11d932982ceb3805e1d2083b30832666b5efdc80d01c70644fda`.
- Ordered 200-payload corpus SHA-256: `640f955aad28b8c55203a8e78f817cfc26c53b64d6413510734d6fc093473d4c`.
- Persistence-free endpoint: `POST /api/internal/evaluation/v1/turn`; HTTP 200 is classified by the Eval result, not mistaken for successful RAG completion.
- Three fixed sequential warmups per process, excluded; two-second settle. No retries, cache clearing, or overlapping baseline/feature processes.
- Both experiments use the balanced order B1, F1, F2, B2, B3, F3. Fixed concurrency 2 for attribution and 200 for operational evidence.
- Short preflights at concurrency 32, 16, and 8 produced 16/32, 12/16, and 5/8 completions. Concurrency 2 produced 16/16; chosen without changing services. Dependency health passed twice beforehand.
- The internal Eval endpoint bypasses the admission wrapper used by browser/mobile talk. Admission/pipeline/rewrite/response-build timing headers absent here are not assigned zero values. Existing limits remain unchanged.
- Latency starts after the client concurrency semaphore is acquired and ends on full response receipt. Percentiles use linear interpolation. Throughput is completed count divided by measured run wall time.
- Process CPU/RSS sampled every two seconds; logging snapshots every ten seconds. This test-only launcher added no production endpoint or authentication bypass. `/api/metrics/admission` retained HTTP 401; runtime snapshots were authorized by the user.
- Raw requests, answers, prompts, logs, and the temporary corpus are not committed. The benchmark records outcome metadata, identifiers, timing headers, and semantic hashes.

## Clean attribution

All latency columns are seconds. COMPLETED turns and dependency failures are separate populations. Other failures are explicitly counted.

| Run | Completed | Dependency errors | Other | Completed mean | Median | p95 | p99 | Completed/s | All/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 200 | 0 | 0 | 3.900 | 3.525 | 5.367 | 5.403 | 0.512 | 0.512 |
| F1 | 200 | 0 | 0 | 3.938 | 3.558 | 5.411 | 5.457 | 0.507 | 0.507 |
| F2 | 200 | 0 | 0 | 3.901 | 3.528 | 5.354 | 5.390 | 0.511 | 0.511 |
| B2 | 200 | 0 | 0 | 3.896 | 3.520 | 5.355 | 5.384 | 0.512 | 0.512 |
| B3 | 200 | 0 | 0 | 3.900 | 3.525 | 5.358 | 5.400 | 0.511 | 0.511 |
| F3 | 200 | 0 | 0 | 3.896 | 3.523 | 5.367 | 5.398 | 0.512 | 0.512 |

### Dependency errors and mixed-outcome operational metrics

Mixed outcomes are operational context; they are not the primary logging-attribution comparison. Empty error populations have no invented latency.

| Run | Dependency count | Dependency mean | Median | p95 | Mixed mean | Mixed median | Mixed p95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 0 | — | — | — | 3.900 | 3.525 | 5.367 |
| F1 | 0 | — | — | — | 3.938 | 3.558 | 5.411 |
| F2 | 0 | — | — | — | 3.901 | 3.528 | 5.354 |
| B2 | 0 | — | — | — | 3.896 | 3.520 | 5.355 |
| B3 | 0 | — | — | — | 3.900 | 3.525 | 5.358 |
| F3 | 0 | — | — | — | 3.896 | 3.523 | 5.367 |

### Median of three run-level completed metrics

| Metric | Baseline seconds | Feature seconds | Delta ms | Delta % |
| --- | --- | --- | --- | --- |
| mean_ms | 3.900 | 3.901 | 1.383 | 0.04 |
| median_ms | 3.525 | 3.528 | 3.058 | 0.09 |
| p95_ms | 5.358 | 5.367 | 8.842 | 0.17 |
| p99_ms | 5.400 | 5.398 | -1.645 | -0.03 |

### Paired common-success subsets

| Pair | Count | Metric | Baseline seconds | Feature seconds | Delta ms | Delta % |
| --- | --- | --- | --- | --- | --- | --- |
| B1/F1 | 200 | mean_ms | 3.900 | 3.938 | 38.336 | 0.98 |
| B1/F1 | 200 | median_ms | 3.525 | 3.558 | 33.171 | 0.94 |
| B1/F1 | 200 | p95_ms | 5.367 | 5.411 | 44.178 | 0.82 |
| B2/F2 | 200 | mean_ms | 3.896 | 3.901 | 4.907 | 0.13 |
| B2/F2 | 200 | median_ms | 3.520 | 3.528 | 8.158 | 0.23 |
| B2/F2 | 200 | p95_ms | 5.355 | 5.354 | -1.133 | -0.02 |
| B3/F3 | 200 | mean_ms | 3.900 | 3.896 | -3.983 | -0.10 |
| B3/F3 | 200 | median_ms | 3.525 | 3.523 | -2.190 | -0.06 |
| B3/F3 | 200 | p95_ms | 5.358 | 5.367 | 8.842 | 0.17 |

### Existing timing headers: median of three run distributions

Units milliseconds. Spans may overlap; they are not summed. `client_minus_endpoint_ms` is an observed transport/endpoint gap, not an isolated logger timer.

| Stage | Baseline median | Feature median | Median delta | Delta % | Baseline p95 | Feature p95 | p95 delta | Delta % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| client_minus_endpoint_ms | 5.383 | 4.823 | -0.561 | -10.42 | 8.215 | 8.137 | -0.078 | -0.95 |
| x-blocking-wait-ms | 0.100 | 0.103 | 0.003 | 3.52 | 0.135 | 0.134 | -0.001 | -0.74 |
| x-embedding-duration-ms | 36.359 | 37.078 | 0.719 | 1.98 | 44.105 | 45.487 | 1.383 | 3.13 |
| x-endpoint-processing-ms | 3520.248 | 3523.061 | 2.813 | 0.08 | 5353.144 | 5362.567 | 9.423 | 0.18 |
| x-history-duration-ms | 0.029 | 0.030 | 0.001 | 3.45 | 0.047 | 0.042 | -0.005 | -10.64 |
| x-intent-duration-ms | 23.524 | 23.754 | 0.230 | 0.98 | 30.000 | 31.426 | 1.426 | 4.75 |
| x-persistence-duration-ms | 0.070 | 0.073 | 0.003 | 4.29 | 0.134 | 0.142 | 0.008 | 5.93 |
| x-qdrant-duration-ms | 12.150 | 12.280 | 0.129 | 1.06 | 16.583 | 16.960 | 0.377 | 2.27 |
| x-qdrant-wait-ms | 0.009 | 0.009 | 0.000 | 0.00 | 0.012 | 0.013 | 0.001 | 8.33 |
| x-reranker-duration-ms | 53.482 | 52.942 | -0.540 | -1.01 | 65.628 | 66.187 | 0.559 | 0.85 |
| x-vllm-duration-ms | 3281.828 | 3284.684 | 2.856 | 0.09 | 5106.722 | 5106.006 | -0.716 | -0.01 |

### Process resources

| Run | Mean CPU % of one core | Peak CPU % | Peak RSS MiB | Samples |
| --- | --- | --- | --- | --- |
| B1 | 7.21 | 16.49 | 1258.2 | 195 |
| B2 | 7.41 | 15.99 | 1260.0 | 195 |
| B3 | 7.45 | 16.98 | 1260.7 | 195 |
| F1 | 7.71 | 18.48 | 1260.8 | 197 |
| F2 | 7.70 | 17.43 | 1263.4 | 195 |
| F3 | 7.43 | 15.98 | 1263.0 | 195 |

### Semantic hash comparisons

Differences compare identical successful workload indexes. Rerank differences include service scores and sometimes ordering; baseline repeats establish that variation also occurs without structured logging. They do not by themselves prove its precise numerical cause.

| Comparison | Common successes | Answer | Intent | Context | Generation | Routing | Rerank | Rerank without scores |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1/F1 | 200 | 0 | 0 | 0 | 0 | 0 | 200 | 87 |
| B2/F2 | 200 | 0 | 0 | 0 | 0 | 0 | 198 | 89 |
| B3/F3 | 200 | 0 | 0 | 0 | 0 | 0 | 200 | 105 |
| B1/B2 | 200 | 0 | 0 | 0 | 0 | 0 | 199 | 99 |
| B2/B3 | 200 | 0 | 0 | 0 | 0 | 0 | 199 | 98 |

## 200-concurrent operational evidence

All latency columns are seconds. COMPLETED turns and dependency failures are separate populations. Other failures are explicitly counted.

| Run | Completed | Dependency errors | Other | Completed mean | Median | p95 | p99 | Completed/s | All/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 140 | 60 | 0 | 24.109 | 24.484 | 29.016 | 30.071 | 4.528 | 6.469 |
| F1 | 145 | 55 | 0 | 25.033 | 25.450 | 30.632 | 31.724 | 4.527 | 6.244 |
| F2 | 149 | 51 | 0 | 25.069 | 24.935 | 31.084 | 31.933 | 4.627 | 6.210 |
| B2 | 147 | 53 | 0 | 23.956 | 24.122 | 29.293 | 30.333 | 4.784 | 6.509 |
| B3 | 159 | 41 | 0 | 24.095 | 24.302 | 30.391 | 31.149 | 5.074 | 6.382 |
| F3 | 137 | 63 | 0 | 22.960 | 22.863 | 28.019 | 28.502 | 4.735 | 6.913 |

### Dependency errors and mixed-outcome operational metrics

Mixed outcomes are operational context; they are not the primary logging-attribution comparison. Empty error populations have no invented latency.

| Run | Dependency count | Dependency mean | Median | p95 | Mixed mean | Mixed median | Mixed p95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 60 | 16.744 | 17.177 | 18.819 | 21.900 | 21.774 | 28.840 |
| F1 | 55 | 16.990 | 18.225 | 19.610 | 22.822 | 23.115 | 30.240 |
| F2 | 51 | 17.267 | 18.646 | 20.693 | 23.079 | 22.923 | 30.349 |
| B2 | 53 | 16.137 | 17.322 | 19.036 | 21.884 | 21.761 | 28.899 |
| B3 | 41 | 16.401 | 17.496 | 18.332 | 22.518 | 22.520 | 29.935 |
| F3 | 63 | 15.534 | 16.529 | 18.220 | 20.621 | 20.998 | 27.754 |

### Median of three run-level completed metrics

| Metric | Baseline seconds | Feature seconds | Delta ms | Delta % |
| --- | --- | --- | --- | --- |
| mean_ms | 24.095 | 25.033 | 938.300 | 3.89 |
| median_ms | 24.302 | 24.935 | 633.090 | 2.61 |
| p95_ms | 29.293 | 30.632 | 1339.114 | 4.57 |
| p99_ms | 30.333 | 31.724 | 1391.566 | 4.59 |

### Paired common-success subsets

| Pair | Count | Metric | Baseline seconds | Feature seconds | Delta ms | Delta % |
| --- | --- | --- | --- | --- | --- | --- |
| B1/F1 | 98 | mean_ms | 24.138 | 24.852 | 714.665 | 2.96 |
| B1/F1 | 98 | median_ms | 24.484 | 25.082 | 597.542 | 2.44 |
| B1/F1 | 98 | p95_ms | 29.024 | 30.736 | 1711.742 | 5.90 |
| B2/F2 | 115 | mean_ms | 24.033 | 24.866 | 832.753 | 3.47 |
| B2/F2 | 115 | median_ms | 24.234 | 24.908 | 673.939 | 2.78 |
| B2/F2 | 115 | p95_ms | 29.375 | 31.080 | 1705.357 | 5.81 |
| B3/F3 | 108 | mean_ms | 23.791 | 22.788 | -1003.385 | -4.22 |
| B3/F3 | 108 | median_ms | 24.024 | 22.256 | -1768.377 | -7.36 |
| B3/F3 | 108 | p95_ms | 29.964 | 28.037 | -1927.535 | -6.43 |

### Existing timing headers: median of three run distributions

Units milliseconds. Spans may overlap; they are not summed. `client_minus_endpoint_ms` is an observed transport/endpoint gap, not an isolated logger timer.

| Stage | Baseline median | Feature median | Median delta | Delta % | Baseline p95 | Feature p95 | p95 delta | Delta % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| client_minus_endpoint_ms | 168.988 | 172.515 | 3.527 | 2.09 | 200.637 | 235.504 | 34.866 | 17.38 |
| x-blocking-wait-ms | 6539.909 | 6927.023 | 387.114 | 5.92 | 6860.025 | 7454.150 | 594.125 | 8.66 |
| x-embedding-duration-ms | 1117.576 | 1320.705 | 203.129 | 18.18 | 3994.759 | 5103.393 | 1108.634 | 27.75 |
| x-endpoint-processing-ms | 24153.832 | 24723.309 | 569.477 | 2.36 | 29126.026 | 30419.672 | 1293.647 | 4.44 |
| x-history-duration-ms | 0.013 | 0.010 | -0.003 | -23.08 | 0.027 | 0.024 | -0.003 | -12.59 |
| x-intent-duration-ms | 1585.517 | 1711.254 | 125.736 | 7.93 | 1972.458 | 2122.382 | 149.925 | 7.60 |
| x-persistence-duration-ms | 0.076 | 0.071 | -0.005 | -6.58 | 0.137 | 0.151 | 0.013 | 9.61 |
| x-qdrant-duration-ms | 281.073 | 296.421 | 15.348 | 5.46 | 905.920 | 971.831 | 65.911 | 7.28 |
| x-qdrant-wait-ms | 3040.905 | 3401.567 | 360.662 | 11.86 | 4794.911 | 4086.975 | -707.935 | -14.76 |
| x-reranker-duration-ms | 2863.262 | 3214.052 | 350.790 | 12.25 | 6628.284 | 6713.558 | 85.273 | 1.29 |
| x-vllm-duration-ms | 8062.705 | 7522.450 | -540.255 | -6.70 | 10695.336 | 10516.855 | -178.481 | -1.67 |

### Process resources

| Run | Mean CPU % of one core | Peak CPU % | Peak RSS MiB | Samples |
| --- | --- | --- | --- | --- |
| B1 | 101.03 | 303.56 | 1372.0 | 15 |
| B2 | 101.17 | 287.62 | 1365.6 | 15 |
| B3 | 103.11 | 312.59 | 1369.3 | 15 |
| F1 | 99.05 | 332.66 | 1369.8 | 16 |
| F2 | 102.37 | 356.50 | 1367.1 | 16 |
| F3 | 110.98 | 355.56 | 1369.8 | 14 |

### Semantic hash comparisons

Differences compare identical successful workload indexes. Rerank differences include service scores and sometimes ordering; baseline repeats establish that variation also occurs without structured logging. They do not by themselves prove its precise numerical cause.

| Comparison | Common successes | Answer | Intent | Context | Generation | Routing | Rerank | Rerank without scores |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1/F1 | 98 | 2 | 0 | 0 | 2 | 0 | 98 | 44 |
| B2/F2 | 115 | 0 | 0 | 0 | 0 | 0 | 114 | 53 |
| B3/F3 | 108 | 3 | 0 | 0 | 3 | 0 | 107 | 48 |
| B1/B2 | 105 | 0 | 0 | 0 | 0 | 0 | 104 | 45 |
| B2/B3 | 118 | 1 | 0 | 0 | 1 | 0 | 117 | 59 |

## Feature body-off diagnostic

The only child-process changes were `LOG_REQUEST_BODY=false` and `LOG_RESPONSE_BODY=false`; persistent DEV/production settings were untouched. Same 200 requests, concurrency 2, corpus, warmups, and services. One control is diagnostic evidence rather than a replicated experiment.

| Metric | Normal feature (median run metric), seconds | Body-off seconds | Delta ms | Delta % |
| --- | --- | --- | --- | --- |
| mean_ms | 3.901 | 3.899 | -2.091 | -0.05 |
| median_ms | 3.528 | 3.522 | -5.454 | -0.15 |
| p95_ms | 5.367 | 5.367 | -0.480 | -0.01 |

Body-off outcomes: {"COMPLETED": 200}.

## Queue and stdout audit

| Run | Capacity | Final depth | Overflow | Write errors | Listener alive | Non-JSON | Received | Completed | Unique IDs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| clean_F1 | 4096 | 0 | 0 | 0 | True | 0 | 200 | 200 | 200 |
| clean_F2 | 4096 | 0 | 0 | 0 | True | 0 | 200 | 200 | 200 |
| clean_F3 | 4096 | 0 | 0 | 0 | True | 0 | 200 | 200 | 200 |
| operational_F1 | 4096 | 0 | 0 | 0 | True | 0 | 200 | 200 | 200 |
| operational_F2 | 4096 | 0 | 0 | 0 | True | 0 | 200 | 200 | 200 |
| operational_F3 | 4096 | 0 | 0 | 0 | True | 0 | 200 | 200 | 200 |

Each normal feature run emitted 420 JSON objects overall: 10 safe startup events and 205 HTTP event pairs (200 measured, three warmups, one health, one unauthenticated metrics check). Admission events were absent because this Eval path does not acquire admission permits. No `logging_error`, routine per-stage events, or httpx INFO flood appeared. Synchronous overflow fallback was not used.

## Isolated overhead recheck

- Sanitizer/enqueue, 5,000 samples: median/p95 328.8/888.7 µs; old JSON preparation 5.0/10.9 µs.
- In-process HTTP, 1,000 samples: disabled median/p95 5.6/5.8 µs; enabled 305.0/437.5 µs; **added 299.4/431.7 µs**.
- Fifty concurrent requests had 50 unique IDs and zero queue overflow. Added HTTP p95 remained below 1 ms. These measurements exclude inference and do not imply zero overhead.

## Decision and limits

**Logging feature: merge ready for manual review.** No reproducible >3% logging-attributable regression was reproduced in the clean completed-only or common-success comparisons. All six clean runs completed 200/200. Median run-level mean/p95 differences were +0.04%/+0.17%; every clean pair remained below 1%. The body-off result was essentially unchanged, and isolated added HTTP p95 was 0.432 ms. The clean client-minus-endpoint gap did not increase.

The saturated operational result remains a limitation: median run-level completed mean/p95 was +3.89%/+4.57% for the feature. Paired common-success deltas changed direction rather than consistently exceeding 3%. Much larger fluctuations were already present in endpoint blocking waits, intent, embedding, Qdrant, and reranker spans; vLLM spans sometimes decreased. These spans overlap and cannot be summed to assign a precise cause. This is evidence of contention/runtime variation, not proof of a particular dependency's causal contribution. No additional WARNING-only run or logger optimization was justified after the stable clean and body-control results.

Dependency errors totaled 154/600 baseline and 169/600 feature in the operational experiment, with varying pair directions (60→55, 53→51, 41→63). No client timeout or other failure occurred, and neither implementation had errors in the clean experiment. The experiment does not establish a reproducible logging-caused error increase; it also does not certify reliable 200-concurrent DEV operation. Both mixed and completed means were below 35 seconds in every run. Production-like validation on deployment hardware remains separate.

The three deterministic parity cases and all 600 clean paired successful cases had equal answer, intent, routing, context, and generation hashes. Reranker variation occurs on repeated baseline code, including after score fields are removed. Saturated answer/generation hash differences also occurred in one repeated baseline comparison; contexts and routing stayed equal in all comparisons. The test does not identify the precise model-service nondeterminism, and no RAG/model/serving semantics were changed.

The six normal feature runs and body-off control reported capacity 4096, empty final queue, zero overflow/write errors, and a live listener. Sampled queue depth peaked at zero, which is a sampled observation rather than a continuous guarantee. Synthetic failed-login credentials and the four configured secret values checked were absent from feature stdout; values were never printed. All 1,200 measured normal feature IDs were unique globally and each matched its event pair and response header. Startup events were JSON; admission and per-stage event counts were zero on this Eval path; no httpx INFO flood occurred. Existing background, sanitizer, failure, streaming, body-limit, and auth contracts passed focused offline tests.

No production infrastructure, database schema, serving configuration, prompt, model parameter, or retrieval policy was changed. Only temporary localhost RagBot processes were started and stopped; inference/data services stayed running. Normal body flags were never changed persistently. The existing feature branch is to be reviewed and merged manually.

## Validation

Conda environment: `faq`.

- Focused command: `python -m pytest -q -o faulthandler_timeout=60 tests/test_structured_logging.py tests/test_http_logging_middleware.py tests/test_background_logging.py tests/test_logging_startup_stdout.py tests/test_logging_attribution.py tests/test_request_admission.py tests/test_web_auth.py tests/test_web_permissions.py tests/test_mobile_history_content.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_mass_answer_files.py tests/test_mass_answer_service.py tests/test_mass_answer_jobs.py tests/test_mass_answer_regressions.py tests/test_pipeline_terminal_debug.py tests/test_retrieval_normalization_consistency.py::RetrievalNormalizationConsistencyTests::test_request_trace_keeps_content_free_diagnostics`.
- Result: **185 passed, 38 warnings, 32 subtests passed in 27.85 seconds**. Covers logging, request instrumentation/admission, background/mass-answer, auth/permissions, mobile, Eval, and pipeline observer.
- Full backend: `python -m pytest -q -o faulthandler_timeout=60 tests`: **14 failed, 471 passed, 2 skipped, 47 warnings, 14 errors, 102 subtests passed in 36.87 seconds**.
- Known unchanged failures: 14 dataset setup errors from absent intent-training CSVs; six checkpoint compatibility failures from missing checkpoint artifacts; two KB lexicon/classifier artifact failures; one stale concurrency database-construction assertion; two retrieval consistency interface failures; two Step 5 static/environment expectation failures; one environment-validator exit-code failure. No retrieval/model code was changed to address them.
- Initial sandboxed test commands stalled during ASGI application tests and were stopped. A focused exception-handler probe outside the restricted sandbox passed (1 test, 16.62 seconds); both complete reruns above finished outside that sandbox. These are offline in-process/mocked tests, not real service connectivity tests.
- `python -m compileall` passed for structured logging, sanitizer, request instrumentation, HTTP middleware, main, dependency connection, new benchmark/helper tests, startup tests, and structured logging tests.
- `git diff --check` passed. Runtime file hashes remained equal to the premeasurement fingerprint throughout.

No raw logs, synthetic workload file, request/answer bodies, or private environment values are included in this report.
