# Mass-answer repair report

Date: 2026-08-01. Baseline: `30385f23b0511a395bc25e0046d471d5461db1f4`.

## Outcome

The whole-file 50-second timeout, sequential manual RAG loop, unsanitized failure cells, and unbounded input size were repaired. Web, mobile, and batch now enter `AnsweringService`; online wrappers retain authentication/session/persistence/response responsibilities, while batch uses fresh stateless graph state.

| Change | Evidence |
|---|---|
| Shared semantic service | `answering_service.py`; `agent_service.py`; `agent_graph.py` |
| Fixed-size row workers and bounded queue | `mass_answer_service.py` |
| Per-row 50 s default, no whole-file deadline | `mass_answer_service.py`; `main.py` |
| Direct threshold and tracked job API | `main.py`; `mass_answer_jobs.py` |
| PostgreSQL job metadata | `new_architecture/app/services/history/database.py` |
| Strict CSV/XLSX validation and safe output | `mass_answer_files.py` |
| Browser job polling | `templates/index.html` |
| Focused tests and fixtures | `tests/test_mass_answer*.py`; `tests/fixtures/mass_answer/` |

## Timeout and concurrency model

Before: one interactive limiter slot and one `asyncio.wait_for(..., 50)` covered parse, every sequential row, serialization, and response construction. After: the whole-file wrapper and interactive limiter are absent. Each row is guarded by `MASS_ANSWER_ROW_TIMEOUT_SECONDS`; exactly `MASS_ANSWER_ROW_CONCURRENCY` worker tasks plus one producer exist regardless of file size. The queue capacity is twice the worker count. Results are written by original list index.

Default 4 is intentionally below HTTP pool sizes (32), keep-alive pools (16), global blocking work (16), and interactive admission (32). This is a conservative starting point, not a measured optimum.

## Parity

`AnsweringService` now owns validation/normalization, one intent classification, history/rewrite policy, graph invocation, and structured results. `AgentService.process_stateless_message` runs exactly the same graph with a new in-memory state and no DB calls. The graph accepts the preclassified intent, eliminating the prior second TEI embedding/classifier pass.

Prompts, retrieval top-k 10, semantic candidates 50, hybrid fusion, FAQ context construction, related-question TEI reranking threshold 0.1, non-FAQ first-three context, tone, response type, and generation caps are unchanged. Mobile/web schemas remain unchanged. Mobile national-code/session resolution and online message/agent-state persistence remain channel-specific. The unused mobile threshold setting remains a documented pre-existing issue; changing it requires retrieval/answer-quality evidence.

## Failure and cleanup policy

One row cannot cancel unrelated rows. Empty cells are `invalid_input`; row deadlines are `timeout`; overload is `busy`; dependency unavailability is `retrieval_error`; unexpected errors are `internal_error`. The file remains valid with mixed outcomes. Query text is not logged. Unexpected row exceptions are logged with batch ID and row index.

Direct artifacts are response-background deleted. Job artifacts are deleted by job DELETE or expiry cleanup. Failed serialization removes the partial output immediately. An external durable worker queue does not exist, so restart recovery remains unsupported.

## Observability

Status exposes total, valid, queued, active, completed, successful, failed, and timed-out rows. Completion persists total duration, average row time, and interpolated p50/p95/p99 row times. Shared semantic results record normalization, classification, history, rewrite, graph, and total timings; lower-level TEI/Qdrant/vLLM spans are not yet instrumented. No Prometheus metrics were added because the active repository has no verified Prometheus instrumentation pattern.

## Verification and benchmark status

The focused suite was run in `/root/miniconda3/envs/faq/bin/python3.12`; exact final counts are recorded in the completion response. The default `/root/miniconda3/bin/python3` is Python 3.14 and lacks pandas/FastAPI/openpyxl, so it is not the correct project interpreter. `pytest` is not installed in the project environment; the repository has no declared dependency installation command. Use `python -m unittest`, shown below.

The synthetic scheduler benchmark does not contact vLLM, TEI, Qdrant, PostgreSQL, GPU, or the API. It validates bounded scheduling only. No live 1/10/50/100/500-row or mixed mobile workload was run automatically. Live results and before/after service metrics remain unknown.

A full synthetic scheduler comparison used 10 ms fake I/O per row and the required 1/10/50/100/500 row sizes at bounded concurrency 1/2/4/8. All 25 cases had zero errors and zero timeouts. Selected 500-row results:

| Scheduler | Concurrency | Total | Rows/s | p95 row | Max row |
|---|---:|---:|---:|---:|---:|
| Audited sequential baseline | 1 | 5.153 s | 97.02 | 10.40 ms | 11.94 ms |
| Bounded | 1 | 5.248 s | 95.27 | 10.59 ms | 26.32 ms |
| Bounded | 2 | 2.627 s | 190.31 | 10.70 ms | 10.82 ms |
| Bounded | 4 | 1.327 s | 376.89 | 10.87 ms | 11.05 ms |
| Bounded | 8 | 0.681 s | 734.51 | 11.15 ms | 11.39 ms |

This demonstrates scheduler overlap and its fixed overhead only; it is not an inference-capacity result and cannot select live concurrency. The concurrency-8 synthetic result must not be interpreted as safe for shared vLLM/TEI/GPU services.

Run focused tests:

```bash
/root/miniconda3/envs/faq/bin/python3.12 -m unittest tests.test_mass_answer_files tests.test_mass_answer_jobs tests.test_mass_answer_regressions tests.test_mass_answer_service tests.test_answering_service
```

Run all discovered backend tests:

```bash
/root/miniconda3/envs/faq/bin/python3.12 -m unittest discover -s tests -p 'test_*.py'
```

Run the safe synthetic 1/10/50/100/500 × 1/2/4/8 scheduler matrix:

```bash
/root/miniconda3/envs/faq/bin/python3.12 benchmarks/mass_answer_benchmark.py
```

## Reviewed live experiment plan (not executed)

Freeze a synthetic input set and test one row-concurrency value at a time: 1, then 2, then 4, then 8. For each configuration, restart only the staging application with one changed environment variable, warm up, run at least three equivalent batches, and collect job totals plus TEI/vLLM/Qdrant/PostgreSQL/GPU metrics. Run file sizes 1, 10, 50, 100, and 500; do not start 500 until the smaller stages are stable.

Mixed-workload acceptance criteria must be frozen before traffic:

- mass job: 100% rows reach a terminal per-row status; no lost/reordered rows; zero batch-level failures;
- interactive: 50 simultaneous attempts, all successful, p95 at most 20 s, zero limiter/deadline/client timeouts, zero 5xx;
- no sustained vLLM/TEI queue growth, Qdrant/DB pool exhaustion, GPU OOM, or interactive starvation.

Use the existing mobile load generator in a second terminal only after confirming staging route, synthetic identities, write footprint, and cleanup:

```bash
# Terminal 1: submit the reviewed synthetic mass file and poll its job.
# Terminal 2: exact flags must follow benchmarks/load/README.md and the confirmed staging URL.
/root/miniconda3/envs/faq/bin/python3.12 benchmarks/load/mobile_talk_load_test.py --help
```

The mandatory inference isolated/pairwise/all-service layers require staging identity proof, reviewed service isolation/restore commands, installed-version flag verification, and synchronized GPU/service metrics. They were not executed as part of this source repair.
