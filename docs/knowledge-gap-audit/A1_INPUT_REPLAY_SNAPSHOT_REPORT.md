# A1 — input preparation, chronological replay and snapshot foundations

Status: **READY_FOR_PLANNER_REVIEW_WITH_LIMITATIONS**. A1 implementation and
bounded validation are complete. This does not authorize A2 or resolve the
production-repair release gate. Production answering behavior is unchanged.

## Repository and scope

Repository `/root/projects/faq`; branch `a1/knowledge-coverage-inputs`; actual
base matches `7b4de65c851dd8f83a64c7ad2b426cea7664319b`. The scoped commit
containing this report is identified by `git log -1`; its hash is returned in the
planner handoff. Embedding a commit's own hash in its report would be circular.

Scoped files:

- `knowledge_audit/__init__.py`, `inputs.py`, `calendar.py`, `NOTICE`: explicit
  CSV mapping/validation, stable event identities and future DB adapter protocol.
- `knowledge_audit/history.py`, `preparation.py`: cutoff replay and production
  preparation components, with bounded sequential dataset preparation.
- `knowledge_audit/privacy.py`, `export.py`: protected artifact boundary,
  consistent redaction and reusable preparation CSV/manifest.
- `knowledge_audit/snapshot.py`, `runtime.py`: consistent content capture,
  source/index drift gate, local component wiring and identity manifests.
- `scripts/knowledge_audit_prepare.py`, `tests/test_knowledge_audit_a1.py`:
  local diagnostic and entirely synthetic tests.
- This report, `IMPLEMENTATION_PLAN.md`, `DASHBOARD_AND_CSV_CONTRACT.md`.

Existing `.gitignore` edits, deleted `.env.recommended.rtx5880-staging`, private
`.env_latest`, supplied CSVs and all unrelated untracked files were preserved.
Only the three authorized ignored documents were force-added; the ignore rule
was not changed. Input, artifacts and private env files are excluded. No push,
merge, deployment, restart, infrastructure change, KB edit or production call.
No coverage evaluation, aspect extraction, reconciliation, broader search,
recommendation, page, route, worker or database schema was added.

Read AGENTS, plan, dashboard/CSV contract, repair acceptance and P0–P4 reports
before implementation. Cloud-runtime and Python testing skills were used.
Runtime-status tool/network-policy file remain unavailable; existing reports
establish confirmed local staging targets. Live CLI requires explicit staging
assertion, equality with root `.env` targets and loopback hosts; arbitrary remote
or inherited service targets are rejected. FastAPI lifespan is never started.

## Safe input findings and mapping

Input `/root/projects/faq/Eval_System_Test.csv` was read without modification.
Encoding **UTF-8 without BOM**, delimiter **comma**; **918** records, all eight
fields wide. Columns: `date`, `session_id`, `time`, `customer`, `national_code`,
`query`, `bots_answer`, `دسته بندی`.

Explicit mapping: query=`query`, session=`session_id`, date=`date`, time=`time`.
No source-query-ID or role mapping; all rows are selected user queries. The other
four columns are not copied into events or exports. There is no message-role or
assistant-completion-time field. `bots_answer` has **3 missing cells**; every
other column has zero missing cells. Answer presence does not establish failure,
feedback, coverage or historical availability. This column is excluded from
replay, including its nonempty values. No outcome filtering is performed.

Dates use `YYYY/MM/DD`, year **1405**; times use `HH:MM:SS` without offset.
The user explicitly confirmed **Jalali / Asia/Tehran** during A1. All **918**
timestamps validate and convert to UTC; zero missing/malformed/unresolved times
or invalid-width records. Parser/calendar/timezone basis and original offset are
recorded. There are **560 sessions**, zero same-session equal-time groups and
**68 repeated query occurrences** beyond first occurrences. Every duplicate
retains a separate preparation result.

Remaining source ambiguity is assistant availability/history completeness.
Replay remains user-only; historical factual replies and latest summaries are
never substituted. No database customer history was read or enriched.

## Input and chronological preparation

Row identity combines input-byte SHA-256 and 1-based logical CSV record ordinal,
assigned before validation; quoted newlines do not change record identity.
Source order and chronological processing order are separate. Blank, wrong-width
and unknown-role records retain invalid results; file-level unparseable syntax
is rejected before acceptance because boundaries cannot be established.
Session/optional query references use keyed HMAC scoped to source/run. Absent
sessions are independent; matching text never establishes a session.

Mixed-role files support user/assistant/system, with ai/model mapped to assistant.
Assistant events require their own availability timestamp. System rows are
history-only and do not enter rewrite formatting. The future `AuditInputAdapter`
interface returns the same immutable event contract. A future DB implementation
must use existing psycopg2 read-only patterns, frozen ordered selection, approved
owner/session filters, user `created_at`, actual assistant `completed_at` and a
confirmed naive-time convention. No new DB query schema or active DB input
adapter was invented. Latest-state DatabaseManager history is unsuitable.

`AuditHistoryProvider.before(current_event)` enforces same-session historical
cutoff, excluding current/future events. Shared production trim/format rules
apply: last 10 state messages, last 6 valid rewrite messages (3 turns). Equal
cutoff timestamps are excluded unless source order is explicitly confirmed.
Earlier equal timestamps have reproducible ordinal fallback but ambiguous
conversational order. Missing/invalid times do not establish precedence; unknown
peer times mark incomplete history. Explicit trusted source sequence can enable
ordinal chronology; it is off for this file. DST folds are ambiguous and
nonexistent local times invalid. Capture completeness is always unverified.

Observed history states: **560 unavailable**, **358 user_only**. These describe
available events, not proof the conversation started in the CSV. No assistant
responses were fabricated, and no current chatbot answer was generated.

`QueryPreparer.from_answering_service` accepts the exact active production
components. CLI uses the same non-stemming PersianTextProcessor, Persian
normalization, HistoryRewritingService, classifier factory/checkpoint and
general-only alias canonicalizer in AnsweringService order. It never invokes
the answering service workflow, graph, retrieval, reranking or answer generation.
No production source was changed. Parity tests compare actual AnsweringService
query forms/intents against audit preparation with real normalization and mocked
model components; actual production rewrite parsing is separately tested.

Original redacted, normalized, history-resolved semantic and alias retrieval
forms remain separate. The active classifier supplies general/actionable versus
chitchat only; general leaves audit scope **unknown**. Additional scope logic is
deferred. Conservative ellipsis detection and lexical rewrite grounding mark
absent, ambiguous or unsupported context `needs_context`/uncertain; they never
produce a knowledge-gap label. They can miss ellipsis or flag self-contained
questions, and shared subject words do not prove complete semantic fidelity.

## Privacy and snapshot guarantees/limitations

Raw bytes/mapped messages are memory-only; the user-owned original is not copied.
New artifacts retain redacted views rather than intentional unsanitized copies
of input/history, prompts or model responses; detector limitations remain below.
Existing log-sanitizer patterns apply before external calls, storage and export.
Additional conservative redaction covers unvalidated long numeric IDs, labeled
PII and explicit currency amounts. Repeated references use consistent per-run
placeholders. Typed opaque IDs are preserved separately from untrusted text.
Only fixed errors survive; inherited content observers and CLI library logging
are suppressed. No raw exception strings or model-filled prompts are logged.

Regex redaction cannot identify every unlabeled name, address, credential or
banking fact, and can remove useful policy numbers/amounts. Redaction effects
are recorded; authorized private review is required before sharing/evaluation.
Text over 32,768 characters fails safely rather than silently truncating evidence.
Artifacts are outside Git/static directories: directory **0700**, files **0600**,
exclusive creation, no symlink traversal/overwrite. Protected privacy keys are
local; fresh runs intentionally have different pseudonyms. `/tmp` storage is
ephemeral, not durable encrypted audit infrastructure.

The versioned snapshot captures **1,526** authoritative chunks in one PostgreSQL
read-only **REPEATABLE READ** transaction: full redacted content, Q/A, available
taxonomy, document/chunk mapping, document revision and latest stored version ID.
Latest version ID is available provenance, not proof of a complete version chain.
Arbitrary metadata and editor identifiers are excluded. Recognized FAQ chunk ID
is the entry ID; no cross-chunk grouping or semantic deduplication is inferred.
**67** records changed under redaction; remaining clauses/text are retained.

`scripts/kb_signature.py` brackets capture. Signatures must FULL_MATCH and both
report cross-store consistency; actual captured content/metadata hashes must
equal the complete signature records. Inconsistent captures fail explicitly.
Snapshot and manifest contain source/redacted content hashes, file/content
identities and capture code hashes. Source PG aggregate remains
`948cae670aaec5faa350d977a0f381d6410a9b48d7853cdfd18bff7c76310750`.

This is frozen content plus consistency evidence, not a signature-only export.
It does **not freeze live Qdrant**, establish atomic cross-store transactions or
detect every transient/ABA change between observations. Later runners must call
`enforce_run_compatibility` before/after each live retrieval/evidence unit, reject
source/vector/collection/configuration drift and invalidate incompatible results.
Current KB text must never replace mismatched frozen evidence. An immutable
matching index/checkpoint is the stronger A2 prerequisite. Sentence segmentation
and citations are deferred.

## Final accounting, artifacts and model calls

Final directory: `/tmp/ragbot-a1-final-20261013`.
Files: `preparation.csv`, `preparation-manifest.json`, `privacy.key`,
`kb-snapshot.json`, `kb-snapshot-manifest.json`. Independent parse/hash checks
confirmed all 918 IDs exactly once in source order, matching run/export/snapshot
identities, empty coverage fields, unchanged input hash and private permissions.
Five queries changed under redaction. No original customer, national-code,
session-ID, answer or category columns are projected.

| Preparation status | Rows |
|---|---:|
| prepared | 10 |
| pending_model | 857 |
| needs_context | 51 |
| failed / invalid_input / uncertain_preparation | 0 |
| total | 918 |

All rows were parsed, validated and production-normalized. Only **10** were
successfully model-prepared: deterministic first 10 chronological user rows,
with necessary preceding supplied history. Five had prior history; event counts
in source export order: `0,1,2,3,0,1,0,1,0,0`. Successful final live pass:
**10 TEI embedding POSTs** for classification and **5 vLLM rewrite completions**,
sequential concurrency one, no retries. Metadata: embedding `/info`, vLLM
`/models` and `/version` before/after (six GETs), matching serving identity.
Immutable weights/tokenizer revisions remain unverified. There were no rerank,
retrieval, answer-generation, coverage or production calls.

Two preliminary live exports reached export validation but failed when text
redaction altered opaque row hashes. They used the **same** first-10 query
selection/histories; per-service call counts were not retained, so cumulative
call totals must not be inferred from the final manifest. The final pass's exact
counts above are recorded. No more than 10 distinct user queries were selected
for live preparation across these attempts. Two sandbox offline attempts stalled
and were terminated; the successful full offline/live commands used escalation,
as prior local asyncio/ASGI checks required. A risky nested redaction regex was
also replaced and covered by synthetic adversarial input; no production
performance change or speed claim is made.

| Final identity | Value |
|---|---|
| Run | `a1_f9dc536c1ebc9ba52dd00069c9cefdc9` |
| Input SHA-256 | `f2e963046de586df6e187a33cac12ba3900c60d5a408066b50bc5fe2f896f3fe` |
| Export | `f39381b7360193d259abdf3f5e40d583142c9069b41935eedb1f11b692889aa0` |
| CSV SHA-256 | `70f3b8600973497f12e0eb4fc744c0731f1bc9fb780250d0b54d1c842979b46e` |
| KB snapshot | `41bffc05e91c02e288c81f23a45606de54746ead33e11e9ddb24b7d2402e16ef` |
| Configuration | `f6d72c445c818a0bd54e95ae8b1729955d8d4aa77b17e91cfaf98b308c85f75a` |
| Preparation code | `2208d0267858ee1b5f231ec865f33a7b458513deb8795db635cfd3ef8370ba00` |

Code identity records base plus exact implemented source hashes, captured before
commit; it does not falsely attribute modified code to the base alone.
Configuration includes existing effective settings, classifier expected/actual
hashes, alias hash, time/sample policy, history limits, privacy version and keyed
target identities. No secrets, endpoint credentials, filled prompts or env
contents are copied. Cross-run keyed identities require the same protected key
or an authorized equivalence check; raw-byte row identity remains stable.

## Configuration and executed validation

All Python commands ran after:

```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda activate faq
```

Interpreter `/root/miniconda3/envs/faq/bin/python`, Python **3.12.12**. Root `.env`
loads through established `load_dotenv(ROOT / '.env', override=False)` before
settings/services. **New permanent env variables: none. Env changes: none.**
Per-run defaults/validation: UTF-8-sig decoder/comma (explicit supported choices),
Gregorian/ISO calendar, timezone unset (validated IANA name), source order
untrusted (boolean), model limit zero (integer 0–10), existing deadline ≤50s,
shared 10/6-message history rules. Actual mapping, encoding, chronology, sample
and runtime settings are recorded in manifests. Main templates/generator
references were inspected; `.env.example.generated` is source-authored, with no
repository generator found. No unused future settings or deleted template added.

Final successful commands, each exit **0**:

```bash
python scripts/knowledge_audit_prepare.py Eval_System_Test.csv --directory /tmp/ragbot-a1-validated-offline-20261013 --query-column query --session-column session_id --date-column date --time-column time --calendar jalali --source-timezone Asia/Tehran --snapshot /tmp/ragbot-a1-preparation-20261013/kb-snapshot.json
python scripts/knowledge_audit_prepare.py Eval_System_Test.csv --directory /tmp/ragbot-a1-final-20261013 --query-column query --session-column session_id --date-column date --time-column time --calendar jalali --source-timezone Asia/Tehran --model-limit 10 --confirmed-staging --capture-snapshot
python -m pytest tests/test_knowledge_audit_a1.py tests/test_answering_service.py tests/test_history_aware_query_routing.py tests/test_step5_query_canonicalization.py tests/test_internal_evaluation_parity.py tests/test_web_permissions.py tests/test_web_auth.py tests/test_kb_audit_tools.py tests/test_knowledge_update_consistency.py tests/test_revision_aware_cache.py tests/test_faq_taxonomy.py tests/test_performance_config.py tests/test_validate_environment.py tests/test_retrieval_normalization_consistency.py tests/test_persian_normalization.py tests/test_structured_logging.py -q
python -m compileall -q knowledge_audit scripts/knowledge_audit_prepare.py tests/test_knowledge_audit_a1.py
git diff --check
git diff --cached --check
```

Final suite: **209 passed / 46 subtests**, **16.40s**, including **47 A1 tests**.
Earlier focused runs: first 1 failed/40 passed (rewrite output reached classifier
before redaction), then 41 passed; expanded focused run 46 passed before the
timeout-row test. Earlier broad run 203 passed/46 subtests. Counts overlap.
Issues were corrected with regressions, not suppressed. Existing warnings:
SWIG, NVML, datetime.utcnow and Starlette templates; live Qdrant's generic
insecure-connection API-key warning contained no key value.

Comprehensive deterministic tests are synthetic/mocked: real production rewrite
parsing/normalization parity, follow-up/insufficient/invented context, mixed roles,
duplicates/invalid rows, session isolation/cutoffs, timestamps/DST/ties, redaction
and errors, formula/JSON/multiline/manifest conservation, snapshot consistency,
integrity and source/index/config drift. Timeout tests preserve rows without
inference retry. Independent activated Python stdin checks also parsed the full
input and verified final file/manifest identities, counts/order and permissions;
only counts/hashes/booleans were printed. Actual Excel import was unavailable,
and no browser page exists in A1.

Calendar calculation adapts MIT-licensed
[jalaali-js](https://github.com/jalaali/jalaali-js/blob/master/src/index.ts);
notice retained, no dependency installed. Supported Jalali years 1200–1600 stay
within its documented Gregorian/Intl agreement range; Nowruz/leap boundaries
and all supplied dates were validated. No calendar inference occurs without
explicit configuration.

## Remaining boundaries and recommended next pilot

No A1 implementation blocker remains. Planner should privately review the 51
conservative needs-context cases and redaction effects. Full model replay and
coverage remain unperformed. User-only history cannot recover missing assistant
facts; lexical grounding cannot certify semantic fidelity. Durable ownership,
authorization, retention/encryption, interruption/resume, model-token budgeting,
frozen-index guarantees and DB input authorization remain later-stage work.
Repair-gate release-quality/write/browser/GPU/load/tokenizer limitations remain.

After separate A2 authorization, select at most 10 reviewed rows across
standalone, user-only follow-up, duplicate/history-dependent and needs-context
cases. Establish current-snapshot fact/condition labels and compatible immutable
index or strict drift invalidation before coverage. Preserve every selected row
and uncertainty. A2 must include the agreed main-dashboard page and initial
coverage CSV. A1 stops here for planner review.
