# Knowledge-coverage audit operator runbook

Scope: a separately authorized exploratory audit, using the main dashboard and
protected file-backed workers. This document does not authorize a customer run,
production access, deployment, deletion or a service restart. Independent human
quality acceptance and real-query calibration remain pending.

## Before authorizing execution

1. Check the reviewed branch/commit and clean scoped application deployment through
   the normal operator process. Historical pre-A6 runs must not be resumed through
   changed implementation code. Do not edit pinned manifests, hashes or ledgers.
2. Confirm the configured service endpoints. `confirm_live_run` requires an
   explicit `--confirmed` and non-empty `TEI_EMBED_URL`, `VLLM_URL`,
   `POSTGRES_HOST` and `QDRANT_HOST` (and `TEI_RERANK_URL` for runs), and uses
   them as configured, in every environment.
   Reconfirm generation model/context/version, TEI model/limits, SDK retries zero,
   configured client/admission limits and source/index consistency.
   Weight/tokenizer aliases are not immutable weight provenance.
3. Check available disk headroom, filesystem ownership/permissions, GPU/resource
   telemetry if available, normal-workload conditions and shared admission. Missing
   GPU telemetry is unverified, not evidence of spare capacity. A small interference
   experiment is not a production-capacity or 200-concurrent-user SLA result.
4. Explicitly authorize the operator/account and scope. Access comes from the
   role: `admin` can start, view, export and review; `dashboard_viewer` can view
   and export; other roles have none. Starting needs start and KB-read rights;
   evidence/export/recommendation review require their separate capabilities.
   Do not give an arbitrary account the `admin` or `dashboard_viewer` role.
5. Select an owned validated dataset and frozen content snapshot. CSV imports retain
   all selected user-query identities, including duplicates/invalid records. Confirm
   calendar/timezone/role/column mapping. Inspect incomplete history separately from
   a knowledge gap. Never invent historical assistant replies.

## Choose finite allowances

The default remains a maximum-five-question pilot. Explicit larger subset and
server-resolved full-input modes retain every imported query in exports. Full-input
selection does not mean every record can finish within the chosen allowance.

The page shows effective completion, token, execution-time, consecutive-failure,
minimum-free-storage and pacing limits. Full-input starts require explicit
acknowledgement. Request limits may tighten configured ceilings; they cannot weaken
storage/pacing protections. Defaults and ranges are in
[environment documentation](../configuration/ENVIRONMENT_VARIABLES.md).
Default coverage allowance: 200 completion attempts, 1,000,000 prompt/output tokens,
3,600 execution seconds, 3 consecutive failures, 1 GiB free disk and 500 ms audit-local
pacing. These are conservative stop allowances, not predicted cost or capacity for
918 queries. Keep batch cap 2, distinct-entry maximum 300 and sequential audit work.

All actual completion attempts count, including rewrite, scope, aspects, batches,
reconciliation, verification and the existing single syntax-only recovery. The
served tokenizer reserves prompt plus maximum output before dispatch. Known usage
replaces reservation; unknown completion retains conservative charge. Tokenization,
metadata, embedding/reranking POSTs and source-check invocations are counted
separately. Source-check counts are not individual SQL/Qdrant request counts.
Checkpoint reuse consumes no new completion allowance.

Recommendation revisions have their own explicit completion allowance (default
20), other operational limits and ledger, displayed before drafting. No proposals
are created automatically by full-input coverage. New revisions never erase old
usage. Approval concerns question/taxonomy proposals only, never answers or a
confirmed absence from the KB.

There is **no in-place allowance extension**. Exhausted completion/token/time or
failure allowances require a new explicitly configured run; prior work, usage and
exports remain historical. A new run may repeat inference and is not a free resume.
Do not reset counters or copy checkpoints to bypass identities. A missing published
ledger blocks recovery; never recreate a fresh zero-usage ledger. Restore only
validated operator backups or use a separately authorized new run. If a small full-
selection exploratory allowance is authorized, expect pending rows and report them
honestly rather than presenting a complete full-dataset audit.

## Start and monitor

1. Open `/knowledge-coverage`, select dataset/snapshot/datasources, mode, explicit
   subset if applicable and effective finite allowances. Full-input row identities
   are resolved on the server. Review source/selected counts and acknowledge limits.
2. Start once. Idempotency binds owner and normalized request; repeated submissions
   cannot create another job for the same key. HTTP requests do not wait for the
   entire audit. Busy workers remain queued under local OS leases/global audit gate.
3. Monitor imported, selected, processed, model-evaluated, pending/interrupted,
   excluded, context/review and error counts. A completion dispatch is not validated
   evidence. All-terminal with errors is not a clean quality pass.
4. Inspect remaining completions/tokens, conservative unknown reservations,
   execution seconds, pause/error reason, last measured disk headroom and checkpoint
   reuse. Per-phase model metrics retain safe timings/categories without prompts,
   outputs, exception messages or serving logs. No precise ETA is promised.
5. Protect ordinary chatbot work: audit-local pacing precedes shared admission,
   yields to visible normal waiters and leaves a spare slot when capacity permits.
   This is bounded courtesy, not strict cross-worker priority or an SLA guarantee.
   Pause/cancel if ordinary work degrades; do not change shared serving settings.

## Pause, interruption and recovery

Budgets automatically produce `paused`, not gaps or completed full runs. Use
**Cancel run** for an explicit operator stop. Completed rows and validated structured
boundaries remain. Local cancellation does not prove the server stopped.

The elapsed watchdog covers cooperative worker work, including silent awaits;
service calls also have remaining-run deadlines. Filesystem/CPU work that cannot be
preempted may delay cleanup; failed final ledger closure conservatively retains
its active interval. Abandoned active intervals include downtime until inspected/
closed. A clock jump or uncooperative external process is not a strong monotonic
cross-restart timing guarantee.

On recovery, check original query/history, snapshot/source/index, code, schema,
rubric, model/serving and configuration identities. A drifted run is incompatible.
Retained structured outputs pass membership/citation/semantic verification again.
Never relabel a dispatched/incomplete request as complete evidence.

Unknown work offers three explicit choices: stop (default), leave unknown rows
interrupted and continue others, or explicitly retry accepting duplicate work/cost.
The recorded recovery revision acknowledges uncertainty but **does not refund its
token or completion reservations**. Check available serving metrics/operator state
before retrying; a local gate cannot prove abandoned remote work is gone. SDK network
retries remain zero. If allowance is exhausted, choose a new authorized run instead.
Storage pauses may resume only after storage is repaired and identities/remaining
allowance still pass. Failure-threshold pauses need operator diagnosis and a new
run; no automatic retry-until-success policy exists.

Abrupt worker death releases kernel leases. Inspect stale work; no startup routine
automatically replays unknown inference. Durable rows are authoritative and dirty
progress indexes reconcile. Attempt/recovery history is separate from effective
results. Disk-write failure can leave an interrupted operation requiring inspection;
fix storage first. Never overwrite historical exports to hide an error.

## Final CSV and review handoff

Prepare one immutable coverage revision from the desired progress state. The full
export includes every imported source query in source order; filtering/pagination
never changes the denominator. Pending/error/context/excluded rows remain explicit.
A budget-paused 918-row export is not 918 model-evaluated rows.

For recommendations, deliberately use a common frozen coverage source when drafting
multiple rows. In **Run download**, choose at most one compatible recommendation
revision per row and an explicit review revision. Multiple proposals stay in JSON
cells. Inspect the count/review-state/unselected/incompatible summary, then prepare
the immutable combined CSV and matching manifest. Later coverage/review changes do
not change old bytes. Restricted permissions withhold evidence/draft text/notes.

Check row IDs/order, CSV hash/export identity, selected-source map and frozen
operational allowance in the matching manifest. BOM, JSON, quoting and formula
protection are mechanical safeguards; native Excel/LibreOffice acceptance remains
unverified when the application is unavailable. Recommendation approval never
approves factual answers. Possible gaps are bounded-search findings; confidence
is not calibrated probability. Human labels remain `not_reviewed` unless genuinely
supplied through the validated independent-review interface.

## Retention: dry-run first

Automatic deletion is disabled; no scheduled cleanup or browser filesystem-path
endpoint exists. Age threshold defaults to 30 days. Passing the age threshold does
not revoke access or change bytes. Manual deletion makes removed resources
unavailable; old URLs then return not found. Keep needed exports/review packages
held according to operator policy before authorizing deletion. For a separately
authorized future hold, an owner-only `.hold` or `HOLD` marker in the artifact
directory protects it without editing pinned manifests; metadata `retention_hold`
and `protected` flags are also honored.

Use the configured protected root only, with the normal conda environment:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
# Save a protected plan outside Git/static; the parent must exist with mode 0700.
python scripts/knowledge_coverage_cleanup.py --owner-id OWNER_ID \
  --plan-file /protected/operator-directory/cleanup-plan.json
# Only after reviewing the exact plan ID, dependency graph, holds and candidates:
python scripts/knowledge_coverage_cleanup.py --owner-id OWNER_ID \
  --plan-file /protected/operator-directory/cleanup-plan.json \
  --apply-plan-id EXACT_PLAN_ID
```

These example commands are future operator actions, not authorization to delete
current customer artifacts. **A6.2 applies deletion only to exclusively owned
synthetic temporary fixtures; existing real artifacts receive dry-run inspection.**

Planning is read-only, scans stable identities/references, and preserves unknown
artifact types, malformed inventories, symlinks, held/protected nodes, shared-owner
snapshots, active/recoverable/preparing/leased work and dependencies referenced by
retained datasets, runs, exports, recommendations/reviews, calibration or protected
review packages. Input/export identity aliases also resolve to parent artifacts. Same-owner runs
sharing input and snapshot are retained together when any is retained, preserving
historical counterproofs used by recommendation eligibility.
Dataset deletion includes its privacy key only when the complete
unit is proven unreferenced and eligible. Unknown package types are held, never
silently expired.

Queued/running work conservatively holds all cleanup candidates. Unknown nested
files hold their entire artifact. Root coordination is nonblocking: readers or
new submissions receive a busy response during apply and should retry after it
finishes; they do not block the dashboard event loop.

Apply requires the exact hashed plan, re-inventories references/ownership/content,
checks root coordination plus global/run leases, rejects stale plans, and uses the
platform's symlink-resistant deletion. Cleanup and cooperating creation/export/
worker paths share filesystem coordination. Minimal outcomes persist separately;
inspect partial/interrupted deletion before any new plan. No symlink target or
outside-root path is a deletion candidate. Do not run old standalone tools or
out-of-band filesystem writers concurrently; they must honor the same artifact
coordination or be quiesced. Local OS locks are not distributed multi-host/NFS
queue or hostile same-UID process isolation.

## Acceptance boundaries

Implementation/mechanical acceptance, small bounded staging execution, a separately
authorized full-input exploratory run and production release/quality acceptance are
separate decisions. Consult the current
[A6.2 readiness report](A6_2_OPERATIONAL_READINESS_REPORT.md). No operator action in
this runbook fills missing human labels, freezes live Qdrant, proves immutable
weights/tokenizer provenance or establishes production capacity. Historical
credential exposure remains the external owners' rotation/history-handling action;
never print credentials, rotate automatically or rewrite history as audit cleanup.
