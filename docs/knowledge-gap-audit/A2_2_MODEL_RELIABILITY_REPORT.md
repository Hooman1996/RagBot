# A2.2 bounded model-call reliability diagnosis

Status: implemented for planner review, with unresolved model-output/reliability
limitations. No A3, recommendations, full-dataset audit, production calls, KB edits,
shared-service restart, infrastructure change or deployment is included.

Branch `a2.2/audit-model-reliability`; verified base
`68cd16f152ea9e897d92077654120f46712a5b61`. The publication commit contains this
report; the handoff supplies its verified full local/remote SHA. Live work used
this correction worktree with exact code-file hashes, before committing; historical
run identities are never rewritten to the new commit. Applied repository debugging,
Python-testing and cloud-runtime guidance. The managed environment-status tool
and network-policy snapshot were unavailable; staging guards verify actual
loopback targets against the established root dotenv configuration.

## Confirmed finding and limits

Reconstructed row 486 and 320 batches reproduced **typed client read timeouts**:
`httpx.ReadTimeout` through SDK `APITimeoutError` and RAG `ServiceTimeoutError`.
Measured completion waits were 40,240.788 / 40,018.083 ms, admission below 0.3 ms,
tokenization below 55 ms. The 50-second outer deadline did not expire. This
confirms the boundary/cause of the new reproductions, not a retroactive exception
record for the original A2.1 failures. Those historical runs stored only
`not_returned`/`audit_failed`; their exact exception category remains unavailable.
The same configured path and reconstructed inputs strongly support the read-timeout
explanation, but do not prove the historical exception itself.

Read timeout is the transport termination; large structured output is a separate
observed pressure. First-observed five-entry requests generated near the 1,200
output cap while the non-streaming client awaited its response. Warm repeats
returned **length**, also at 1,200 tokens, just below 40 seconds. A request-local
45-second allowance returned the same length failures and was not adopted.
No global or audit-specific timeout increase is implemented.

Two-entry requests reduced output/time for one reconstructed boundary and yielded
two schema-valid outputs across three comparisons, but the other boundary returned
malformed JSON. The narrow implemented correction is a fixed two-entry audit cap,
`full-entries-two-1`, with all remaining entries still evaluated and every Q/A,
condition, citation and strict proof check retained. It does not guarantee a valid
or timely response. Production answering/retrieval/client defaults are unchanged.

Staging metrics showed no waiting requests and at most one running request during
the diagnostic samples. First-token counter deltas were 0.510–0.629 seconds for
first-observed calls and 0.118–0.132 seconds for repeats/comparisons. This does not
support a 40-second queue/schema-start delay in these reproductions. Repeated
requests are warm observations; no service/cache flush established a controlled
cold start. Counters are server-wide observations, not per-request traces or proof
that no other GPU work existed. GPU queries/NVML were unavailable; GPU contention,
weights/tokenizer revision and the serving model's underlying output behavior
remain unverified. No raw serving logs, prompts or outputs were collected.

Preliminary A2.1 JSON-syntax/length failures, original final A2.1 unreturned calls,
new typed read timeouts, and new returned malformed/length outputs remain separate.
No speculative serving root cause or calibrated reliability rate is claimed.

## Complete deadline/translation path

Effective values were loaded via root dotenv without printing credentials.
Installed SDK versions: OpenAI 2.6.1, httpx 0.28.1. Source inspection included the
installed SDK's timeout/retry path and repository lifecycle/admission code.

| Boundary | Effective policy | What the limit includes |
|---|---|---|
| Dashboard start/progress | Existing background job/persistence path | Start returns before long-running evaluation; a run is not one external 50-second HTTP request |
| Preparation | `AdmittedPreparer`, outer 50s, admission 12s | Preparation operation including permit wait/rewrite/classification; underlying rewrite uses the existing RAG client |
| Audit tokenization/discovery | Separate httpx metadata client, 40s per connect/read/write/pool operation | `/tokenize`, models/version metadata; no completion SDK retry. Tokenization precedes the audit completion outer deadline; fits checks also tokenize |
| Audit admission | Existing limiter, 12s | Permit wait; inside completion's 50s outer deadline |
| Audit completion operation | Outer asyncio deadline 50s | Admission plus completion, excluding earlier tokenization/progress; not a total-attempt/run deadline |
| SDK/httpx model request | Connect 3s, read 40s, write 5s, pool 5s; SDK retries 0 | Phase/inactivity waits; read includes waiting for response bytes while serving queues/generates. Non-streaming completion supplies no token stream to reset the client read wait |
| Staging serving | Observed vLLM version/context and numeric `/metrics` | Queue/prefill/first-token/decode counters; no serving flags or limits changed |
| RAG translation | `_completion` catches SDK timeout/status/connection errors | Raises content-free service errors **with original causes**, balances active counters in `finally`; production implementation unchanged |
| A2.2 audit translation | Bounded cause-chain inspection, `audit-failures-1` | Retains specific typed failure categories only; no exception values, body, headers or traceback locals |

The repository default read value is 45s; the effective staging env value is 40s.
The separate audit metadata client uses the read value for all its HTTP phases.
Count/fits calls are outside completion admission/deadline. Consequently 50s is
not a promise for total audit-attempt elapsed time. This existing background behavior
is documented, not silently converted into a production deadline change.

`asyncio.timeout` distinguishes its own expiration from a nested timeout; admission
overload and an outer deadline expiring while waiting remain distinct. Cancellation
propagates as cancellation and releases permits/counters. Local cancellation or a
read timeout does not prove that server inference stopped. Unknown completion/usage
is retained; there is no new network retry or exactly-once remote inference claim.
Existing explicit row retry still may duplicate unknown remote work and must not
be used to rerun a pilot until it passes.

## Safe diagnostics and export

`audit-failures-1` categories include:

- `admission_timeout`, `outer_operation_deadline`.
- `model_read_timeout`, `model_connect_timeout`, `model_write_timeout`,
  `model_pool_timeout`, `model_timeout_unknown`.
- `model_connection_failure`, `model_service_failure`, `model_http_rejection`,
  `model_protocol_rejection`.
- `output_length`, `schema_validation`, `citation_validation`,
  `semantic_validation`, existing fixed evidence/token validation codes.
- `cancellation`; unknown exceptions remain `audit_failed` without copied text.

Metrics include role/schema, purpose, call/attempt IDs, safe UTC start time,
progress/tokenization/admission/completion/validation durations, preflight/reported
tokens, safe finish reason, input/message hashes, numeric output/reasoning shape
where obtainable, and server-completion state. SDK request IDs are keyed opaque
references; only numeric HTTP status is retained. No authorization headers, URL
credentials, exception messages, raw outputs, filled prompts, source text or
traceback locals are serialized. Unknown field names in schema errors become `*`.

`dispatched` is the audit completion-entry/attempt flag, not proof of a wire
request; CLI transport hooks count actual completion POSTs. Correlation IDs are
recorded only when exposed by the SDK; missing IDs are not invented. Unknown
served usage is not replaced with planned input token counts. Output-length and
schema failures with returned responses retain their known usage.

CSV/manifest version 3 adds `failure_diagnostics`, also retained in restricted
exports because it contains allowlisted metadata only. Row details render failure
category, boundary, evaluation phase, attempt and duration. Fixed `error_code`
values survive rather than collapsing every failure into `audit_failed`. A failed
production model assessment remains uncertain; it cannot prove insufficient
reachability or a gap. Independent valid audit evidence may still establish KB
coverage with reachability review. Every A2.1 evidence/identity/immutable-export
regression is retained.

All 918 source rows, duplicates/order, pending/context/excluded/error states,
redaction, BOM, JSON cells and formula protection remain in export. Frozen CSV/
manifest revisions remain immutable; no historical revision is regenerated.
Rubric `coverage-rubric-4`, responsibility schemas and segmenter remain unchanged.
`json-invalid-stop-one-fresh-response-1` remains the only recovery: at most one
fresh identical request for a before-redaction JSON-syntax error with `stop`.
It never repairs content or retries network/length/semantic/citation errors.

## Bounded diagnosis: twelve dispatches

Protected directory:
`/root/projects/faq-private/knowledge-coverage/diagnostics/diag_9d947a0c43bc4431b42bbd6b4b765968`.
Source run `r_4b85230ac9db94edc715055d1e0d6cf9`; same saved A1 snapshot
`41bffc05e91c02e288c81f23a45606de54746ead33e11e9ddb24b7d2402e16ef`.
No query preparation/retrieval/new customer queries ran in diagnosis.

| Boundary | Original ordered membership | Tokens | Reconstructed payload SHA-256 |
|---|---|---:|---|
| 486 / `row_7a55dfd6fb2e3bf750d99fa30e975d30` | 583,577,627,581,818 | 2,953 | `9adad2ea70df3dd1b1725289eaa2436a174487c7345f907c8bba96deeb0aa232` |
| 320 / `row_85acf8adf43bd6feb04d01f90927b68e` | 942,161,295,297,142 | 2,986 | `bc2b088c2c41d1259debb94fa79968e278d2bbba2f483fce8d396c92f08af73f` |

Membership came from persisted production selection and `model_requested` status;
saved resolved intent/aspects and full snapshot records supplied inputs. Original
prompt/schema file hashes matched; exact served token counts matched the recorded
failed requests. The old run had no input/message hash, so original byte identity
cannot be independently proven beyond those checks. New protected hashes enable
future exact comparisons. No reconstructed filled prompt/input was saved.

| Comparison, in dispatch order | Synthetic ms / outcome | 486 ms / outcome | 320 ms / outcome |
|---|---|---|---|
| First observed, five entries/read 40s (486,320,synthetic) | 40,061.020 / read timeout | 40,288.419 / read timeout | 40,071.354 / read timeout |
| Repeated same boundaries, five/read 40s (486,320,synthetic) | 39,652.148 / length | 39,968.501 / length | 39,637.520 / length |
| Change only request-local read to 45s (synthetic,486,320) | 39,670.117 / length | 39,742.150 / length | 39,980.325 / length |
| Restore read 40s, change only batch cap to two (synthetic,486,320) | 39,775.986 / schema-valid | 21,660.004 / schema-valid | 19,598.090 / malformed JSON |

The synthetic full batch was 2,674 input tokens, versus 2,953/2,986 source-boundary
tokens; two-entry inputs were 1,617 / 1,585 / 1,726. Full Q/A text was not truncated.
Smaller requests evaluated subsets of the original batch; they do not by themselves
establish whole-question coverage. The six returned full-batch failures each used
1,200 output tokens. Two-entry outputs used 1,199 / 652 / 588 tokens. The synthetic
success is nearly at both limits and is not a robust-margin claim.

Exactly **12 completion POSTs** occurred: two schema-valid, six length-terminated,
three read-timeout and one malformed-JSON response. There were 13 audit attempt
records because the final syntax recovery was **blocked before the SDK request**
by the global dispatch budget. No recovery completion was dispatched, and no
network retry occurred. That earlier instrumented metric conservatively marked
completion-entry as dispatched; the guarded operator counter proves twelve wire
dispatches. Final instrumentation explicitly marks such blocked budget attempts
not-dispatched; the original diagnostic journal is preserved.

Returned usage: **22,154 prompt / 9,639 output tokens**, nine responses. Three read
timeouts have unknown server usage; generation-counter deltas are not substituted
for response usage. Summed experiment elapsed time: 440,105.634 ms, including
telemetry/validation and the blocked recovery. The final follow-up process's RAG
active counter was zero; each process closed its own clients. Its timeout counter
is process-local and does not include the first diagnostic process's timeouts.

The temporary 45s override affected only those three requests via SDK request
options; shared client configuration, services and env values were never changed.
It did not fix output-length failure. The adopted batch-only correction keeps
read 40s, outer 50s, output reserve 1,200, max 300 distinct entries and sequential
calls. More/smaller calls can increase total run cost; this is a bounded reliability
experiment, not a throughput optimization or a new reliability-rate estimate.

Exact commands, with the root conda environment activated:

```bash
python scripts/knowledge_coverage_diagnose.py --run-id r_4b85230ac9db94edc715055d1e0d6cf9 --confirmed-staging
python scripts/knowledge_coverage_diagnose.py --run-id r_4b85230ac9db94edc715055d1e0d6cf9 --confirmed-staging --followup-id diag_9d947a0c43bc4431b42bbd6b4b765968
```

The follow-up can start only once after the six initial dispatches; both phases
share the hard limit of twelve, including syntax recoveries. Numeric telemetry
comes only from existing staging `/metrics` and bounded `nvidia-smi` queries;
there is no new monitoring infrastructure or raw log collection.

## Single end-to-end revalidation

One new run uses the same five original IDs, legitimate preceding history and
unchanged 300-entry budget. No repeat-to-pass run is authorized or performed.

```bash
python scripts/knowledge_coverage_pilot.py pilot --dataset-id d_62ca6afb6cb231e3105f8aa4746ac3b0 --snapshot-id 41bffc05e91c02e288c81f23a45606de54746ead33e11e9ddb24b7d2402e16ef --entry-budget 300 --row-ids row_bd526b97ad9940b1d6a15871aac7b0ab row_db3be7cdd0b505a4def0a73355236a6f row_7a55dfd6fb2e3bf750d99fa30e975d30 row_85acf8adf43bd6feb04d01f90927b68e row_dedce881f722f95251e3f326f002f465 --confirmed-staging
```

Run `r_bcc2b95676b8184e3bb4e6f7d25d8b84`; source/index preflight matched the
existing snapshot. Identities captured before selected-row evaluation at
`2026-10-14T11:37:22.523829+00:00`, identity
`80d137647e76d6311d2c31f2b445c00bd88ea7b7248733c1c6ac3a6d2c67ab33`.
The run completed in **299.646 seconds**. All inference-file hashes matched the
worktree after completion; no later code correction was replayed into that run.
Generation serving identity was unchanged from A2.1; observed runtime identity
changed only in the explicit audit-policy settings. Source/index checks matched;
no new snapshot or KB edits were needed. Immutable weights remain unverified.

Actual calls: **41 completion POSTs**, all returned (five synthetic capability,
35 audit attempts, one legitimate history rewrite), 13 embedding and 16 reranking
requests. Of 40 structured attempts, 38 validated and two failed schema validation;
the latter are the initial and one fresh recovery for the same row 518 batch.
There were **no transport/outer/admission/length failures in this run**, and no
network retries. All response usage is known: **58,147 prompt / 6,547 output tokens**.
Measured structured-call duration totals 225,550.771 ms; server correlation headers
were not exposed (zero server request references). No reasoning text was exposed;
numeric shape observations do not establish internal reasoning behavior.

| Ordinal / original ID suffix | A2.1 final → A2.2 | Distinct submitted entries | Audit attempts | Prompt / output tokens | Row duration ms |
|---|---|---:|---:|---:|---:|
| 387 / `...aac7b0ab` | Excluded → excluded | 0 | 1 | 907 / 64 | 3,314.768 |
| 518 / `...55236a6f` | Covered but not reachable → schema error/uncertain | 30 | 18 | 29,813 / 1,876 | 80,515.039 |
| 486 / `...0e975d30` | Unreturned-call error → covered/reachable | 4 | 7 | 10,553 / 2,213 | 88,276.537 |
| 320 / `...0927b68e` | Unreturned-call error → covered/reachable | 2 | 4 | 5,143 / 902 | 44,323.456 |
| 121 / `...002f465` | Possible partial gap → covered/reachable | 4 | 5 | 5,948 / 941 | 45,226.840 |

The full IDs are in the exact command above and private manifests. Row audit totals
exclude capability/rewrite usage, included in the overall total. The row 518 schema
failures are `json_invalid`, root field path `[]`, before redaction, normal `stop`;
both use 1,747 prompt tokens, then 94/98 output tokens, 3,401.997/3,327.637 ms.
The fresh syntax recovery failed; this row remains an error, not a gap or a
negative production-reachability finding. No repeat pilot was performed.

Each covered result has one accepted full proof over production-selected evidence:

| Row | Snapshot-qualified FAQ/chunk sentences | Accepted bundle |
|---|---|---|
| 486 | 627:5 and 581:1–4 | `f4370dbf37ed31513a8d00a4f695b5002384c0ab0fc18818be8bc6cfb2900009` |
| 320 | 942:1–2 and 161:1 | `0f735076f9dff83b16f62618934433fecf5caee4b85b5c696f8a0bf95801ee8a` |
| 121 | 116:3 for a1 and a2 | `2b46585e59161a5a29a842be23af1e35d12c1713545c3e5c5499064da6e18420` |

These are accepted **model** proofs, not independent human labels. Row 121's
original/resolved wording, requested aspects and production-selected IDs were
identical to A2.1, yet its result changed from missing a1 at 300 entries to verified
full at four. This grouping/model judgment sensitivity needs human review,
especially substantive-fact versus generic-referral applicability. It is not
evidence that the KB changed or that the earlier possible gap was definitively
repaired. Rows 486/320/518 have different aspect text from A2.1; row 518's production
selection also differed despite equal query forms/intent. Source/serving signatures
matched, but no deterministic whole-system replay or calibrated accuracy is claimed.

Full export **918 = 3 covered/reachable + 1 error + 1 excluded + 51 needs-context + 862 pending**.
Preparation counts remain 15 prepared, 852 pending-model,
51 needs-context; ten prepared rows are inherited A1 work, not ten extra evaluated
queries. Recommendations remain unassessed. Every export row/order/duplicate,
export/run/revision identity and CSV hash matched the manifest on independent parse.

| Final export identity | Value |
|---|---|
| Configuration | `07e9f053df1d5e5bb4331965d0cd3551b40487bbe97ad8a9aac1b65784396968` |
| Revision | `rev_6ce1f2f3d126bd9f9c03daebc8d8927f` |
| Export ID | `1b24fcad075dc4ffb33d968b29f5125a2d25312a64e483e022cee081e41245af` |
| CSV SHA-256 | `a7cac6ebc6b6dde54aee0832e9eef3a226274b3b7aa1dd874e935c151bea29c0` |

Private files remain under `runs/r_bcc2b95676b8184e3bb4e6f7d25d8b84/`, including
row checkpoints, content-free metrics/usage, summary, run-level CSV/manifest and
`exports/evidence/rev_6ce1f2f3d126bd9f9c03daebc8d8927f/` frozen pair.
Across the entire A2.2 task: **53 wire completion dispatches**, 50 returned,
**80,301 reported prompt / 16,186 output tokens**, three diagnostic read-timeout
requests with unknown additional usage. One pilot syntax recovery was dispatched
and failed; one diagnostic recovery was blocked. Only the same five distinct
customer-query IDs were used. The 12-dispatch diagnosis had no preparation,
retrieval or additional input-query run.

## Deterministic and frontend validation

Environment:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Final full regression command:

```bash
python -m pytest tests/test_knowledge_coverage_reliability.py tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py tests/test_structured_logging.py tests/test_offline_frontend.py -q
```

**444 passed, 203 subtests passed, 39 warnings, 22.54 seconds.** Existing warnings
are NVML availability and deprecations. Tests exercise the actual SDK/RAG translation
chain under mocked transports, each typed timeout, status/protocol/connection/service
failure, tokenization versus completion, admission versus outer expiration, nested
timeouts, cancellation at three boundaries and balanced counters. They verify no
network retries, output-shape-only length diagnostics, budget-blocked dispatch,
blank human labels, HTML escaping, full evidence, the two-entry cap with no lost
facts/rows/entries, and failure-category preservation in restricted frozen CSVs.
All A2.1 question-evidence/uncertainty/resume/export counterexamples pass.

Earlier focused checks passed 42, then 23 reliability, then 81 and 83 combined
tests as assertions were added; the final full suite includes all 30 new reliability
tests. All fixtures/model responses are fictional. No customer-derived fixture or
filled prompt/output was committed.

After adding three explicit nested-timeout and citation/semantic diagnostic
assertions, `python -m pytest tests/test_knowledge_coverage_reliability.py -q`
passed **33 tests / three warnings in 12.79s**. Only tests changed after the
444-test suite; inference files stayed identical throughout the live pilot.

```bash
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit scripts/knowledge_coverage_pilot.py scripts/knowledge_coverage_diagnose.py tests/test_knowledge_coverage_reliability.py
node --check static/js/knowledge_coverage.js
git diff --check
git diff --cached --check
```

Frontend: 3 audit / 6 KB / 5 analytics checks passed; the updated audit check also
renders safe model-failure details. Offline audit PASS, zero external runtime
dependencies. Compilation, syntax and whitespace checks passed. A2.2 did not rerun
actual browser acceptance; A2.1's synthetic Chromium evidence is retained, and
Node/DOM assertions are not presented as new visual acceptance.

## Human review, privacy and publication

The reusable offline review component creates five protected row JSON files plus
an escaped, network-disabled HTML index and hashed manifest. Each observation
preserves its run/input/snapshot identity, redacted original/resolved intent,
aspects/conditions, numbered cited evidence with full surrounding answers,
production-selected evidence/assessment, outcome/missing aspects/uncertainty and
stopping/error reasons. Reviewer agreement/correction/applicability/coverage/missing-
fact fields are blank. Status remains `not_reviewed`; no independent human label
or new factual answer is invented. Rows 518 and 121 are explicitly prioritized.

Actual package:
`/root/projects/faq-private/knowledge-coverage/reviews/review_5ba744159f6b388080c0903648f72c06/`.
Open `index.html` locally under authorized operator access; five `row_*.json`
files hold blank reviewer fields. Manifest SHA-256:
`a0b68ea1d5f00c627a8288a9815d4f3b2169d7fdd831d4d3d635e329d535d566`.
It contains both original final A2.1 and A2.2 observations without changing either
run. In particular it preserves row 518's older accepted unreachable proof and
new error, and row 121's earlier missing a1 plus new accepted full proof. Original
aspects, conditions, complete numbered source answers and production contexts are
available for agreement/correction, without any auto-assigned human judgment.

```bash
python scripts/knowledge_coverage_pilot.py review --run-ids r_4b85230ac9db94edc715055d1e0d6cf9 r_bcc2b95676b8184e3bb4e6f7d25d8b84
```

Artifact root `/root/projects/faq-private/knowledge-coverage`, directories 0700,
files 0600; outside Git and public static roots. No real account access grant or
new endpoint was added. Existing authentication/CSRF/default-deny/ownership rules
are unchanged. Existing regex redaction is not comprehensive PII recognition;
private protection remains required even for redacted review material.

No new permanent env variable was introduced. Existing values/defaults/templates
and private `.env`/`.env_latest` were not changed. The fixed batch cap and failure,
deadline, recovery and unknown-server-completion policies are in the runtime
manifest. Template-generation sources remain source-authored as documented;
no deleted staging template was recreated.

At start, 3,727 historical run/dataset/snapshot files were fingerprinted. All
checked hashes remained unchanged; input CSV SHA-256 remains
`f2e963046de586df6e187a33cac12ba3900c60d5a408066b50bc5fe2f896f3fe`.
Private snapshots, exports, diagnostic/review packages, raw datasets and env files
are excluded from the commit. Unrelated `.gitignore`, deleted staging template
and untracked files remain untouched. Authorized ignored docs are explicitly added
without changing the ignore rule.

Scoped files: audit model/failure taxonomy/telemetry/pipeline/settings/export/review
components; trusted diagnostic/pilot CLI; three-line dashboard detail rendering;
new synthetic reliability tests and adjusted batch-cap assertion/frontend checks;
this report, plan, rubric/schema, CSV contract and configuration-policy docs.
No production `RAGSystem`, shared client, retrieval default or serving flag changes.

Historical credential exposure in old `env.example` commits remains an operator
responsibility: assess/rotate affected PostgreSQL credentials through the owner
process and decide coordinated history handling. Values are not reproduced;
credentials were not rotated and Git history was not rewritten.

Release limitations remain model-output validity/transport margin, unavailable
GPU/immutable model provenance, independent evidence/aspect labels and production
repair acceptance gates. Bounded manual review of the five-question package is
appropriate. Numerical accuracy/reliability calibration is not established by
these model observations; no broader calibration or dataset run is started.
