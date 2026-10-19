# A6.2 resource budgets, safe retention and operational readiness

Status: **implemented for planner review**, with separate acceptance decisions
below. Branch `a6.2/operational-readiness`; verified direct base
`cd8989a2531ad1d90bc8b0e311e5a1d2f8e8edc9`. The publication commit contains this
report; the handoff supplies the full verified local/remote SHA. Only this review
branch is pushed, without force/merge/deployment.

No customer full-input execution, production call, KB edit, factual-answer drafting,
shared-service restart, serving reconfiguration or deletion/move/expiry change of
real private artifacts occurred. The reference generation experiment uses unchanged
normal generation on explicitly fictional contexts and does not persist answers,
chat sessions, tickets or KB records. Historical runs/exports remain unchanged.

## Separate readiness decisions

| Decision | Result | Meaning |
|---|---|---|
| Implementation/mechanical validation | PASS (qualified by exact test scopes) | Finite ledgers, pause/recovery, ownership/CSRF, dependency-safe manual retention and immutable row-conserving exports are tested on synthetic workloads. |
| Bounded staging execution | GO with limitations | The fixed experiment returned all 8 generation dispatches; 4 audit batches were schema-valid. Controlled 150/300 candidate reranking returned. No repeat-to-pass or unknown completion occurred. |
| Separately authorized full-input exploratory execution | Conditional GO | Appropriate for an explicitly authorized finite-budget staging observation that may pause with pending rows. Reconfirm identities/headroom/access/ordinary workload and select explicit limits first. This report does not start or authorize that run. Defaults do not promise all 918 evaluations finish. |
| Production release and quality acceptance | NO-GO | Human labels/real-query calibration, production capacity/SLA and release acceptance, native spreadsheet and immutable serving provenance are not established by this stage. |

An exploratory reviewer must distinguish blockers from limitations. Source/serving/
configuration mismatch, exhausted allowance, insufficient disk, unresolved remote
completion without explicit recovery choice and missing required access are
**execution blockers**. Missing human labels, native Excel/LibreOffice acceptance,
immutable weights/tokenizer identity, live-index freezing and a measured production
capacity remain **explicit limitations** for exploratory interpretation and release
acceptance, not manufactured accuracy scores. Production deployment is separately
controlled. A configured maximum is not measured capacity. Disk headroom is a preflight
guard, not a reserved quota; another process can fill the filesystem after a
check, and failed writes require operator inspection.

## Finite allowances and resource boundaries

`audit-operations-1` pins strict integer limits and a protected ledger before work.
Defaults/ranges and all eight new env keys appear in the configuration reference.
Default coverage limits: 200 completions, 1,000,000 tokens, 3,600 execution seconds,
3 consecutive failures, 1 GiB disk headroom, 500 ms local pacing. Recommendation
revisions have their own default 20-completion allowance and ledger. Effective
limits are shown before start; full-input needs acknowledgement. Request limits
can tighten ceilings or increase storage/pacing protection, never weaken them.
The existing batch default 2, distinct-entry ceiling 300 and sequential policy stay.

A task-local observer at the existing RAG completion and TEI dispatch boundaries
is unbound for ordinary production work. It changes no shared client, timeout,
retry, model parameter, prompt, reranking text/default or eligibility rule. Actual
history rewrite completions pass the same dispatch ledger; served chat-template
tokenization supplies rewrite input reservations. Audit calls reuse their already
verified token count. Prompt plus maximum output and one attempt are reserved
before dispatch, including the existing one fresh syntax-only recovery. A reused
structured checkpoint makes no completion reservation. Known returned usage replaces
reservation; unknown completion remains conservatively charged, including a crash
between reservation and the per-row dispatch marker. Row identities and recorded
recovery revisions bind those unknown reservations; skip cannot silently redispatch
such a row.

Limits/counters survive restart/resume. There is no allowance-extension API;
exhausted completion/token/time/failure allowance requires a new explicitly
configured run, preserving old usage/results/exports. Unknown acknowledgement never
refunds usage. A new run may repeat work. Low-disk pauses may resume after repair
only with compatible identities and remaining allowance. Budgets pause work and
preserve pending/interrupted records; they cannot produce a gap or complete full run.

A cooperative run-wide elapsed watchdog covers silent awaits and service calls use
remaining-run deadlines. Unpreemptible filesystem/CPU/foreign work is not magically
stopped; durable IO drains short writes before lease release. Abandoned active
intervals conservatively include downtime; wall-clock changes remain a cross-restart
limitation. A failed final ledger closure retains its active charge. Failure
streaks are per model/rewrite/service family, so successful health metadata cannot
mask repeated model errors. A published run with a missing ledger fails closed;
its consumed allowance is never recreated as zero. Review-package input and
export/review identity aliases protect their parent datasets/runs, and unresolved
source strings are omitted from cleanup plans. Failed or unknown inference never proves insufficient
production reachability or a gap.

The ledger records only fixed categories/IDs, known/conservative tokens, request
counts/durations, unknown usage, checkpoint/recovery counts, last disk measurement,
artifact bytes at attempt closure and process peak RSS. It never stores filled
prompts, raw outputs, exception messages, auth values, raw serving logs or arbitrary
source columns. Redaction's existing prose limitations remain; private ownership
and review are still required. Source-check counters count signature-provider
invocations, not all underlying SQL/Qdrant operations. Normal application startup
and archival standalone calibration tools are outside the operational worker
ledger and retain their own bounded campaign policies. No complete accounting of
unobservable server usage or all shared-service traffic is claimed.

Audit-local pacing precedes shared admission, yields to visible normal waiters and
reserves a spare slot when configured capacity allows. It is not a new scheduler,
strict cross-worker priority or a production-latency guarantee. Execution time starts
after worker/global admission; global queued time is not a separate monotonic
counter. Per-model admission spans and safe queue-stage timestamps remain available. Default serving
configuration, production timeouts and SDK network retries zero remain unchanged.

## Safe retention

`manual-dependency-retention-1` is manual-only; automatic deletion is disabled.
The trusted CLI defaults to dry-run and accepts an explicit plan ID/file only for
apply. There is no browser arbitrary-path endpoint. Planning identifies dataset/
privacy-key, snapshot, run/checkpoint/export, recommendation/review and protected
calibration/review/label/archive dependencies by stable references. Retained
artifacts protect their transitive dependencies. Unknown/malformed namespaces,
unsafe permissions/links, holds, shared-owner snapshots and active/preparing/
queued/recoverable/leased units are held. Expiry alone does not revoke access.

Apply hashes/revalidates current inventory, references, ownership and leases under
root coordination. Unknown nested filenames also hold their entire artifact;
queued/running work conservatively holds all cleanup candidates. Root lock acquisition
is nonblocking, so readers receive busy rather than blocking ordinary dashboard work; stale plans fail. It never follows symlink targets or chooses
outside-root paths. Safe-delete support is mandatory. Cleanup outcomes contain
minimal state/counts/identities; partial failure requires operator inspection.
Cooperating creation/export/worker paths share the filesystem lock. Legacy/out-of-
band tools must be quiesced or honor it; local OS locks do not provide distributed
multi-host/NFS coordination or hostile same-UID isolation.

**Real root: dry-run only.** Plan
`c8ecb6d42c9d76392ec56c66ba1f0f84f6b396a22a563a6419917cfb349b6f29`, owner 0,
30-day threshold, **0 candidates / 0 deletions**, unresolved inventory false;
4,755 artifact files / 63,151,251 bytes inspected plus the excluded worker-control lock. The plan is
protected at `/tmp/faq-a62-operator/real-root-handoff-dry-run.json`. No real artifact was
moved, expired, rewritten or removed. Actual deletion tests are exclusively owned
synthetic `/tmp` stores. Final 4,756-file historical hash preservation is reported
below.

## Bounded staging observations

One experiment, protected directory `/tmp/faq-a62-live-resource/`, campaign
`a62-resources-1`. Task-wide durable one-start guard:
`/tmp/faq-a62-task-control/task-budget-cd8989a2.json`. No rerun occurred.
Hard caps: 24 completion dispatches / 80 embedding-reranking POSTs; measured
**8 / 11**. Completion probes 0, syntax recovery 0, network retries 0, unknown
completion/usage 0. Four non-persisting reference generations and four audit batch
calls ran; the two interference pairs each contain at most one reference plus one
audit generation. No customer questions, chat-session or KB write path ran.

Staging guards matched established root dotenv loopback targets; model alias/context
and metadata reconfirmed. vLLM **0.26.0**, context **8,192**; embedding/reranker TEI
**1.9.3**, declared batch max **64**, input maxima **32,768 / 8,192**, auto-truncate
false. Model names are hashed/opaque. Observed serving identity remained unchanged;
immutable weights/tokenizer provenance remains unverified. Existing generation
client: connect 3 / read 40 / write 5 / pool 5 seconds, SDK retries 0. Audit output
reserve 1,200 and margin 128 are unchanged. Startup opens no PG/Qdrant resources;
controlled candidates use unchanged question/category/subcategory scoring.

| Fixed observation | Duration ms | Result |
|---|---:|---|
| Reference alone 1 | 1723.271 | Returned, 1745 input / 38 output tokens |
| Reference alone 2 | 1344.058 | Returned, 1745 / 38 |
| Audit alone 1 | 12393.672 | Schema-valid, 1404 / 349 |
| Audit alone 2 | 12047.928 | Schema-valid, 1404 / 341 |
| Reference with audit 1 | 1356.961 | Returned, 1745 / 38 |
| Audit with reference 1 | 11929.620 | Schema-valid, 1404 / 341 |
| Reference with audit 2 | 1368.016 | Returned, 1745 / 38 |
| Audit with reference 2 | 11984.408 | Schema-valid, 1404 / 341 |

This reference is the normal generation component on fixed synthetic context,
not an end-to-end authenticated chatbot/retrieval/session-latency measurement.

Medians/ranges: reference-alone **1533.6645 [1344.058,1723.271] ms**; reference
with audit **1362.4885 [1356.961,1368.016] ms**; audit-alone **12220.800
[12047.928,12393.672] ms**; audit with reference **11957.014
[11929.620,11984.408] ms**. These two-observation groups show this workload only;
the smaller paired numbers are not proof of improvement or zero interference.
The first observation is not a controlled cold start; no cache/service flush ran.
Reference inputs/settings stayed identical; generated audit output varied slightly.

Total known generation usage: **12,596 prompt + 1,524 output = 14,120 tokens**.
The separate audit allowance records 4 attempts / 6,988 known tokens; task-wide
counts also include reference work. All eight responses ended `stop`; no errors,
length/schema failures or unexecuted generation cases. Audit admission spans
501.042–501.257 ms include the configured 500 ms local pacing; tokenization spans
28.797–48.339 ms. Completion spans were separately retained. HTTP tokenization/
metadata requests: 13, separate from the 11 TEI POST guard.

Controlled depth-150 / depth-300 reranking returned **150 / 300 entries**, boundary
elapsed **254.172 / 325.423 ms**. Two explicit query embeddings and the remaining
reranking batches account for the 11 TEI POSTs (request-kind split inferred from
fixed control flow and unchanged no-retry client, not a separate endpoint journal).
The configured unchanged client batch cap is 50: 3 + 6 reranking POSTs plus
2 embeddings. TEI token usage and per-TEI-batch timing samples were not retained; measured boundary durations include
embedding and full-pool reranking. This is controlled-candidate processing, not
live hybrid-search recall or whole-KB evaluation. No shared records/indexes changed.

Allowlisted existing `/metrics` was available before/after: both brackets showed
0 running/waiting requests, but these are not continuous queue maxima. Server-wide
success count increased by **11**, exceeding our 8 completions: other staging
traffic existed, so counter deltas cannot be attributed solely to this experiment.
GPU/NVML telemetry was unavailable. The local Python process peak RSS was
1,027,156 KiB (imports included); this is not generation/TEI server or GPU memory.
The audit-allowance directory held 1,555 bytes at its recorded checkpoint and last
filesystem headroom was 907,291,463,680 bytes. Run-directory byte samples exclude
external shared dataset/snapshot dependencies and precede the final ledger write. No raw serving logs or monitoring installation
were used. These observations do not establish production throughput, headroom or
the 200-concurrent-user SLA.

Live code identities were captured before the experiment; the operator script and
exact source hashes remain with protected evidence. Subsequent narrow reservation-
row mapping, per-family failure accounting and metadata/layout/override, ledger-loss and dependency/comparison-group guards are
mechanically validated without rerunning the experiment. The measured default
500 ms path and prompts/client settings did not change. No historical pilot is
resumed through these changes or retroactively assigned new identities.

## Deterministic and browser validation

All Python commands used the established environment:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Complete pre-final-guard regression command:

```bash
timeout 390 python -m pytest \
  tests/test_knowledge_operations.py tests/test_knowledge_execution_recovery.py \
  tests/test_knowledge_run_export.py tests/test_knowledge_recommendations.py \
  tests/test_knowledge_coverage_calibration.py tests/test_knowledge_coverage_reliability.py \
  tests/test_knowledge_coverage_corrections.py tests/test_knowledge_coverage_pipeline.py \
  tests/test_knowledge_coverage_access_jobs.py tests/test_knowledge_audit_a1.py \
  tests/test_faq_taxonomy.py tests/test_faq_taxonomy_api.py \
  tests/test_kb_manager_chunk_create.py tests/test_kb_manager_database_config.py \
  tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py \
  tests/test_kb_phrase_normalization.py tests/test_web_permissions.py tests/test_web_auth.py \
  tests/test_rrf_scoring.py tests/test_retrieval_depths.py tests/test_reranker_batching.py \
  tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py \
  tests/test_answer_context_reranking.py tests/test_rag_answer_prompt_roles.py \
  tests/test_performance_config.py tests/test_validate_environment.py \
  tests/test_answering_service.py tests/test_history_aware_query_routing.py \
  tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_api.py \
  tests/test_internal_evaluation_parity.py tests/test_kb_audit_tools.py \
  tests/test_mass_answer_jobs.py tests/test_http_logging_middleware.py \
  tests/test_structured_logging.py tests/test_offline_frontend.py -q
```

Result: **622 passed, 44 warnings, 203 subtests passed, 216.80 s**. This includes
the complete synthetic 918-row interruption/recovery replay. Following the final
three ledger/alias guard regressions, the same complete file list was run with
`timeout 170` and
`-k 'not full_918_selection_idempotency_chronology_export_and_mock_run'`.
Result: **624 passed, 1 deselected, 44 warnings, 203 subtests passed, 85.83 s**. Only that previously passing slow replay is excluded;
the new 918-row budget-pause/conservation cases remain included. Focused final
guard/recovery/access/export/frontend checks passed **167 tests, 1 deselected,
9 warnings, 77.89 s** with this command:

```bash
timeout 160 python -m pytest tests/test_knowledge_operations.py \
  tests/test_knowledge_execution_recovery.py tests/test_knowledge_coverage_access_jobs.py \
  tests/test_knowledge_run_export.py tests/test_knowledge_recommendations.py \
  tests/test_offline_frontend.py -q \
  -k 'not full_918_selection_idempotency_chronology_export_and_mock_run'
```

Other exact executed commands:

```bash
# Initial absence: collection error; first core fixtures: 2 failed / 1 passed;
# corrected core: 3 passed. Expanded operations: 22 passed.
timeout 40 python -m pytest tests/test_knowledge_operations.py -q
# Nested-file hold regression before fix: 1 failed / 1 passed / 37 deselected.
timeout 40 python -m pytest tests/test_knowledge_operations.py -q \
  -k 'unknown_nested or spare_normal_slot'
# Nonblocking reader before fix: 1 failed / 39 deselected.
timeout 35 python -m pytest tests/test_knowledge_operations.py -q -k never_blocks_new
# Final ledger/alias counterexamples before fix: 3 failed / 40 deselected.
timeout 40 python -m pytest tests/test_knowledge_operations.py -q \
  -k 'missing_published or identity_aliases'
node tests/knowledge_coverage.frontend.test.cjs
node tests/kb_manager.frontend.test.cjs
node tests/analytics.frontend.test.cjs
python scripts/audit_offline_frontend.py
python -m compileall -q knowledge_audit utils/audit_dispatch.py utils/RagSystem.py \
  utils/persian_hybrid_search.py utils/tei_embedding_client.py \
  scripts/knowledge_coverage_cleanup.py scripts/knowledge_coverage_resources.py \
  scripts/benchmark_coverage_budgets.py tests/test_knowledge_operations.py \
  tests/knowledge_operations_browser_app.py
node --check static/js/knowledge_coverage.js
node --check static/js/knowledge_recommendations.js
git diff --check
# Single authorized bounded live experiment; do not rerun this completed campaign.
python scripts/knowledge_coverage_resources.py --confirmed-staging \
  --output /tmp/faq-a62-live-resource
# Read-only real-root inspection only; earlier dry-run plans are also preserved.
python scripts/knowledge_coverage_cleanup.py --owner-id 0 \
  --plan-file /tmp/faq-a62-operator/real-root-handoff-dry-run.json
python scripts/benchmark_coverage_budgets.py
python -m tests.knowledge_operations_browser_app --port 18767
node tests/knowledge_operations.browser.cjs /tmp/faq-a21-browser-node \
  http://127.0.0.1:18767 /tmp/faq-a62-browser-publish
```

Node suites passed **5 + 6 + 5 tests**; offline audit passed with **zero external
runtime dependencies**. Compilation, JS syntax and whitespace checks passed.
Warnings are existing deprecations, unavailable NVML and Linux fork warnings;
no warning is represented as GPU validation. Browser servers were isolated and
stopped afterward. No skipped native-spreadsheet or model-quality check is claimed.

Synthetic workload: 918 rows, duplicate identities retained, invalid/pending/
excluded/context/error conservation. New tests cover all responsibility dispatch
boundaries including rewrite/recommendation, pre/during-question exhaustion,
checkpoint reuse, unknown reservations before dispatch markers, restart/no-reset,
explicit extension refusal, failure thresholds, low disk/checkpoint writes,
concurrent reservations/workers, cancellation, elapsed deadline/lease release,
reference/hold/shared snapshot/symlink/path attacks, stale cleanup plans and partial
cleanup outcomes. Existing A6.1/P1–P4/A1–A5 regressions remain included.

Initial tests first failed collection because the requested operations module was
absent. Early core fixture checks then found two fixture setup identity mismatches:
limits must be chosen when creating a new run, not changed on an existing ledger.
Fixed fixtures retained strict identity checks. Expanded 918-row expectations were
corrected to count preparation and retrieval checkpoints as well as model calls;
no validation or row-count requirement was relaxed. A broad sweep found 7 offline
rendering-fixture failures (612 tests / 203 subtests passed); adding the actual new
budget context fixed the fixture without adding silent runtime defaults. A further
621-test / 203-subtest sweep passed. Nested unknown-artifact eligibility reproduced
1 failed / 1 passed before its recursive allowlist fix; final targeted export/
operations/offline checks passed 75 cases. The nonblocking reader regression
separately reproduced a cleanup lock wait before the final nonblocking correction.
The corrected full sweep then passed 622 tests / 203 subtests. Final fault review
reproduced 3 failures for missing published ledger and review-package input/export
aliases; fail-closed guards and alias-to-parent dependency resolution correct them.
Their post-correction results are recorded below. A final implicit-dependency
case also reproduced: A4 compares historical runs sharing owner/input/snapshot.
Cleanup now retains that comparison group while any member is retained, preventing
removal of an old full counterproof from making a possible-gap draft eligible.
Its before check failed (1 failed / 43 deselected, 12.68s); focused final results
are **99 passed, 3 warnings, 59.74 s**:

```bash
timeout 120 python -m pytest tests/test_knowledge_operations.py \
  tests/test_knowledge_recommendations.py tests/test_knowledge_run_export.py -q
```

The cross-stage post-guard sweep above and this final retention/recommendation/
export sweep are distinct scopes; the report does not label them as a new complete
full-replay run. One restricted-sandbox mock
SDK run stalled; the same isolated tests using the required local IPC permission
passed. No live request was used to debug deterministic tests.

Actual isolated Chromium **153.0.8010.0** passed five groups: explicit full-budget
acknowledgement/keyboard start; a two-completion pause with 918 pending rows and no
invented gap; exhausted recovery refusal without counter reset; immutable 918-row
BOM CSV and matching manifest/hash; light/dark and 390px RTL without page-wide
overflow. Final screenshots were actually opened and visually inspected, including
the corrected no-extension recovery wording. The temporary synthetic account has
process-only grants; services/inference are mocked and all browser traffic stays
on its loopback fixture. Its server was stopped afterward. An early final harness
attempt reached the fixture before startup completed; it passed after the explicit
readiness check. No shared service or real account was changed.

- [Light paused state](assets/a6_2_synthetic/a62-paused-light.png)
- [Dark/RTL paused state](assets/a6_2_synthetic/a62-paused-dark-rtl.png)
- [Actual browser inventory](assets/a6_2_synthetic/checks.json)
- [Numeric-only staging observations](assets/a6_2_synthetic/staging-measurements.json)

No new 768/1280 visual matrix, screen-reader, real-account/live-service browser or
native Excel/LibreOffice import is claimed. Spreadsheet executables were unavailable;
parser/BOM/JSON/formula checks are mechanical, not native application acceptance.

## Filesystem measurements

Final benchmark (with no overlapping regression/browser workload) used the same
918-row fictional source and current checkpoint writer for both variants. Twelve
mock completed boundaries per iteration, three iterations:

| Variant | Measurements ms per 12 boundaries | Median ms |
|---|---|---:|
| Checkpoint/index only | 500.220, 513.810, 556.253 | 513.810 |
| Same writer plus durable allowance reservation/dispatch/settlement | 803.584, 795.736, 707.821 | 795.736 |

The added median bookkeeping cost was 281.926 ms per twelve mocked boundaries
(about 23.494 ms per boundary in this small sample). The baseline uses the same
current writer; this isolates incremental reservation bookkeeping, not the total
cost of every A6.2 change versus a historical deployment. Raw numeric evidence is
[budget-overhead.json](assets/a6_2_synthetic/budget-overhead.json).

These compare the same 918-row fictional input and writer policy with/without
reservation bookkeeping. They are mocked local filesystem overhead, not service
latency, production capacity or a full 918-question model throughput estimate.
An initial benchmark launch was stopped before measurement so final measurements
would not overlap regression disk activity.

## Operator handoff, configuration and preservation

[OPERATIONAL_RUNBOOK.md](OPERATIONAL_RUNBOOK.md) covers identity/access checks,
dataset/snapshot choice, finite budgets, start/monitor/pause/recovery, unknown work,
explicit retries, pinned run-level CSV/recommendation/review selection and manual
retention dry-run/apply safeguards. No actual customer run is started.

Eight permanent integer variables: `KNOWLEDGE_COVERAGE_MAX_COMPLETIONS`,
`KNOWLEDGE_COVERAGE_MAX_TOKENS`, `KNOWLEDGE_COVERAGE_MAX_EXECUTION_SECONDS`,
`KNOWLEDGE_COVERAGE_MAX_CONSECUTIVE_FAILURES`, `KNOWLEDGE_COVERAGE_MIN_FREE_BYTES`,
`KNOWLEDGE_COVERAGE_PACE_MS`, `KNOWLEDGE_RECOMMENDATION_MAX_COMPLETIONS`,
`KNOWLEDGE_COVERAGE_RETENTION_DAYS`. Defaults/validation/manifests/docs and all four
tracked root templates are updated; existing private `.env`/`.env_latest` receive
only missing keys, preserving their preceding bytes. No production serving values
were changed. No separate template generator exists. The user-deleted staging
example and ignore-rule edit remain preserved.

**4,756 historical private files verified unchanged, zero added files in the real
private root.** Raw input, original private env prefixes, ignore rule and the
user-deleted template state are preserved. The real-root retention inspections
were read-only with zero candidates/deletions; plans live outside that root.
Only scoped implementation, synthetic tests, sanitized documentation/screenshots
and numeric observations are published. Authorized ignored documentation is added
explicitly; the user's ignore rule is unchanged.

No real account grants or role privileges changed. New files/fixtures/screenshots
are synthetic; private datasets/envs/runs/exports/model outputs/review labels are
excluded from Git/public assets. Regex redaction remains incomplete for arbitrary
prose; protected storage and human review are necessary. Human labels remain
unavailable/pending. Native Excel/LibreOffice and immutable serving provenance are
unverified where unavailable. Historical credential exposure remains the external
owners' assessment/rotation/coordinated-history action; no values are printed,
credentials rotated or Git history rewritten.

The implicit comparison-dependency regression used:

```bash
timeout 35 python -m pytest tests/test_knowledge_operations.py -q -k comparable_historical
```

It failed before the conservative comparison-group fix. The final 99-test sweep
above passed after that correction. No further live request was dispatched.

## Scoped publication files

Exactly these 48 scoped files are included:

```text
.env.example.generated
Production_ENV
docs/configuration/ENVIRONMENT_VARIABLES.md
docs/knowledge-gap-audit/A6_2_OPERATIONAL_READINESS_REPORT.md
docs/knowledge-gap-audit/DASHBOARD_AND_CSV_CONTRACT.md
docs/knowledge-gap-audit/IMPLEMENTATION_PLAN.md
docs/knowledge-gap-audit/OPERATIONAL_RUNBOOK.md
docs/knowledge-gap-audit/assets/a6_2_synthetic/a62-paused-dark-rtl.png
docs/knowledge-gap-audit/assets/a6_2_synthetic/a62-paused-light.png
docs/knowledge-gap-audit/assets/a6_2_synthetic/budget-overhead.json
docs/knowledge-gap-audit/assets/a6_2_synthetic/checks.json
docs/knowledge-gap-audit/assets/a6_2_synthetic/staging-measurements.json
env.example
env.review.example
knowledge_audit/api.py
knowledge_audit/execution.py
knowledge_audit/export.py
knowledge_audit/jobs.py
knowledge_audit/model.py
knowledge_audit/operations.py
knowledge_audit/recommendation_api.py
knowledge_audit/recommendation_jobs.py
knowledge_audit/recommendation_store.py
knowledge_audit/recovery.py
knowledge_audit/retention.py
knowledge_audit/retrieval.py
knowledge_audit/run_export.py
knowledge_audit/service.py
knowledge_audit/settings.py
knowledge_audit/store.py
scripts/benchmark_coverage_budgets.py
scripts/knowledge_coverage_cleanup.py
scripts/knowledge_coverage_resources.py
scripts/validate_environment.py
static/js/knowledge_coverage.js
static/js/knowledge_recommendations.js
templates/knowledge_coverage.html
tests/knowledge_execution.browser.cjs
tests/knowledge_operations.browser.cjs
tests/knowledge_operations_browser_app.py
tests/test_knowledge_coverage_reliability.py
tests/test_knowledge_execution_recovery.py
tests/test_knowledge_operations.py
tests/test_offline_frontend.py
utils/RagSystem.py
utils/audit_dispatch.py
utils/persian_hybrid_search.py
utils/tei_embedding_client.py
```
