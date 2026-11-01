# RagBot Evaluation System V1 acceptance report

## Final verdict

RagBot Evaluation System V1 satisfies the offline acceptance boundary. Core parity, production-history isolation, evaluation-schema isolation, migration safety, deterministic session replay, repetition isolation, divergence classification, durable infrastructure-error classification, and zero-public-runtime frontend assets are proven by static inspection and automated tests.

No live evaluation, PostgreSQL migration/status probe, Redis job, Qdrant request, TEI request, vLLM request, service restart, `.env` change, or production-data write was performed.

## Acceptance results

1. **Core parity — PASS.** Both entry paths call `AnsweringService.answer`, `AgentService.process_message_detailed`, the graph compiled by `agent_graph.build_graph`, `RAGSystem`, `PersianHybridSearch`, and the canonical rewriting/classification services. See `V1_CORE_PARITY_AUDIT.md`.
2. **History isolation — PASS.** `REAL_LOOKING_SESSION_12345` remains `source_session_id` metadata. Evaluation executes with UUID `EvaluationConversationKey` values and `EvaluationHistoryProvider`; the production-provider spy has zero calls. The evaluation runtime no longer constructs `ChatManager`.
3. **Database isolation — PASS.** `EvaluationBase.metadata` contains exactly seven `evaluation.*` tables. Every FK target starts with `evaluation.`. Dataset/run delete functions operate on evaluation ORM models only; cascades cannot leave the schema.
4. **Migration safety — PASS.** Revision `20260831_0001` uses independent metadata and `evaluation.alembic_version`. Offline SQL generation created only `evaluation.*` objects. No `drop_all`, arbitrary-SQL API, reset endpoint, or frontend drop action exists. The operator-only downgrade is confined to the seven evaluation tables.
5. **Dataset ordering — PASS.** The required CSV and XLSX fixture produces A=`Q1,Q2,Q3`, B=`B1`, then two one-row synthetic sessions. A validation defect was fixed: ISO time-only values such as `10:03` now use a deterministic 1970-01-01 UTC anchor for ordering only.
6. **Blank-session behavior — PASS.** Blank/whitespace/NaN session IDs produce a unique synthetic session per source row and are never grouped.
7. **Multi-turn history — PASS.** Before Q1=`[]`; before Q2=`Q1,A1`; before Q3=`Q1,A1,Q2,A2`. Exact saved graph state is used, so a client-only fallback is not synthesized into later history. Shared production formatting/trimming functions are exercised directly.
8. **Stability isolation — PASS.** `repeat_count=5` creates five unique evaluation-session UUIDs. Each repetition starts empty and processes Q1→Q2→Q3 sequentially. Stability concurrency resolves to one; general dataset concurrency uses a fixed bounded worker count.
9. **Divergence — PASS.** Identical stages produce no divergence. First differences resolve to REWRITE, RETRIEVAL, PROMPT_BUILD, and GENERATION as specified. A semantically similar but exact-string-different answer is DIVERGED, never automatically correct/incorrect.
10. **Infrastructure failures — PASS.** Injected embedding timeout, Qdrant unavailable, reranker timeout, and vLLM unavailable exceptions exercise the worker's actual persistence path. Each writes `status=ERROR`, `infrastructure_error=true`, a safe dependency error code, and an ERROR stage. These remain distinct from `NO_RETRIEVAL_RESULTS` and `LLM_CONTEXT_REFUSAL` semantic fallbacks.
11. **Frontend build — PASS.** TypeScript and Vite production build succeeded. Output: `dist/index.html`, 26.51 kB CSS, and 423.19 kB JavaScript (122.22 kB gzip).
12. **Offline asset audit — PASS.** Source and built output report `external runtime asset requests = 0`. CSS uses local WOFF2 files; icons and JS are bundled. Classified strings are license text, React diagnostic literals, XML/SVG namespace identifiers, and the loopback-only development proxy—not runtime public asset requests.

## Database initialization flow

Automated tests cover `NOT_INITIALIZED`, `READY`, `UPGRADE_REQUIRED`, and safe `ERROR`. They prove:

- `EVAL_ALLOW_DB_INIT=false` rejects initialization before importing Alembic/database execution code;
- wrong confirmation is rejected;
- exact confirmation calls only predefined `upgrade(config, "head")`;
- `pg_try_advisory_lock(hashtext(:name))` prevents concurrent execution;
- the fixed schema statement is `create schema if not exists evaluation`;
- the lock is released in `finally`;
- errors expose safe codes, not DSNs or credentials.

The safe first-time operator flow is:

```bash
cd /root/projects/faq
python main.py
```

Open `/evaluation`, sign in with an existing RagBot username/password, and use **Create Evaluation Tables**. The dialog requires `CREATE_EVALUATION_TABLES`. `EVAL_ALLOW_DB_INIT=true` must already be configured in the root `.env`; if it is false, the UI shows operator instructions instead.

This endpoint runs upgrade-to-head only. It accepts no SQL and has no drop counterpart. The command was **not** executed against the configured database during validation. The deployment role's `CREATE SCHEMA` permission therefore remains an operator preflight, not an unresolved architectural defect.

## Trace security

`utils/request_instrumentation.py` was unchanged and remains content-free. Production's no-op observer does not even materialize content artifacts. Full prompt/query/context/chunk/answer artifacts exist only in `evaluation.stage_results`/`evaluation.run_turns` and evaluation API responses protected by the existing RagBot-login dependency.

A code search found no active `print(prompt)`, `logger.info(query)`, `logger.info(context)`, or `logger.info(answer)` in evaluation/shared tracing paths. Dormant commented prompt/context print snippets were removed from `utils/RagSystem.py`. Evaluation SSE publishes identifiers, status, counts, timings, and safe error codes—not content.

## Frontend functional validation

Twelve Vitest/Testing Library tests passed across three files. Covered behavior includes:

- database setup gate, fixed typed confirmation, automatic unlock, and API recovery state;
- dataset upload summary and parser warnings;
- one session row expanding to ordered turns and the shared trace inspector;
- semantic fallback versus infrastructure-error rendering;
- user-only manual conversation add/reorder/remove behavior;
- repeat-count validation;
- backend-canonical first-divergence display and side-by-side attempts;
- SSE named-event parsing, streamed progress, and UI hook updates.

Static inspection confirms the implemented single-query and upload stability modes, recent persisted runs, URL `run` state for refresh/reopen, search/filter/pagination, retrieval/content expansion, rerank movements, context/prompt/generation artifacts, loading/empty/error states, and no frontend schema-drop control. Playwright/Chromium was not locally installed, so no browser smoke test was run and no browser package was downloaded.

## Commands executed and results

Backend evaluation suite, using a disposable `/tmp` environment containing validation-only SQLAlchemy/Alembic/openpyxl/psycopg2 packages:

```bash
/tmp/ragbot-eval-validation/bin/python -m unittest discover -s evaluation_system/backend/tests -v
```

Result: **54 passed, 0 failed, 0 skipped** in the final suite (53 before the strengthened infrastructure persistence case; the additional focused case also passed).

Production/core characterization:

```bash
python3 -m unittest tests.test_answering_service tests.test_p0_p1_repairs -v
```

Result: **20 passed, 0 failed**. One pre-existing `datetime.utcnow()` deprecation warning was emitted.

Offline migration SQL, with command-scoped dummy connection values and `--sql` (no connection):

```bash
env POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 \
  POSTGRES_DB=offline_only POSTGRES_USER=offline_only POSTGRES_PASSWORD=offline_only \
  /tmp/ragbot-eval-validation/bin/alembic \
  -c evaluation_system/backend/alembic.ini upgrade head --sql
```

Result: **passed**; only `evaluation.*` DDL and `evaluation.alembic_version` were generated.

Frontend:

```bash
cd /root/projects/faq/evaluation_system/frontend
npm run validate
```

Result: **12 tests passed; TypeScript/Vite build passed; offline audit passed with zero runtime public requests**.

`git diff --check` also passed. No live integration test was run, by explicit safety requirement.

## Start, build, and deploy commands

Integrated RagBot API and evaluation frontend:

```bash
cd /root/projects/faq
evaluation_system/backend/scripts/check_dependencies.sh
python main.py
```

Evaluation worker:

```bash
cd /root/projects/faq
evaluation_system/backend/scripts/start_worker.sh
```

Equivalent direct command:

```bash
python3 -m celery -A evaluation_system.backend.app.worker.celery_app:celery_app \
  worker --loglevel=INFO --queues=ragbot-evaluation --pool=solo --concurrency=1
```

Frontend connected build environment:

```bash
cd /root/projects/faq/evaluation_system/frontend
npm ci
npm run build
```

Normal development serves the built artifact at `/evaluation` from `python main.py`; it does not start a second evaluation API. No Node/npm install is required at runtime.

## Safe one-query development smoke test — prepared, not executed

This enqueues one logical query with the minimum two isolated stability repetitions. It writes only evaluation records but performs real development inference/retrieval against the services configured for the evaluation worker. Run it only after explicit approval, database initialization, and confirmation that the selected datasource is non-production-safe:

Use `/evaluation`, sign in with an existing RagBot account, choose **Stability Inspector → Single Query**, enter the query, set repetitions to 2, select the approved development datasource, and start the run. This avoids putting a password in shell history.

## Files changed during final validation

- `evaluation_system/backend/app/services/importer.py` — deterministic parsing/sorting of required time-only timestamps.
- `evaluation_system/backend/app/core_adapter/runtime.py` — removed unused evaluation `ChatManager` construction.
- `evaluation_system/backend/tests/test_history_and_parity.py` — exact real-looking source-session sentinel.
- `evaluation_system/backend/tests/test_v1_acceptance.py` — acceptance fixtures and safety/parity/isolation/divergence/error persistence tests.
- `utils/RagSystem.py` — removed dormant content-print snippets; semantic behavior unchanged.
- `docs/evaluation/V1_CORE_PARITY_AUDIT.md` — final side-by-side trace.
- `docs/evaluation/V1_ACCEPTANCE_REPORT.md` — this report.

The production templates, static frontend, `.env` files, knowledge data, Qdrant, MinIO, and live services were not modified.

## Restart/deployment answers

- **Must an existing RagBot service restart because shared-core code changed?** Yes, once when these shared-core V1 files are deployed, the chatbot API process must undergo its normal controlled restart/redeploy to load Python changes. No service was restarted in this validation pass.
- **Do future frontend-only changes require chatbot restart?** No. Rebuild `evaluation_system/frontend/dist`; the chatbot inference source is untouched.
- **Do future evaluation-only changes require chatbot restart?** Worker-only changes require only a worker restart. Python control-plane changes now load inside `main.py` and therefore take effect on the next normal RagBot app restart/redeploy; there is no second evaluation API process.
- **Can the evaluation UI be developed/deployed without restarting live chat?** Yes. Frontend source/build work is isolated. The integrated control-plane API follows the normal RagBot process lifecycle by design.

## Unresolved issues

No core-parity, history-isolation, database-isolation, migration-safety, ordering, repetition-isolation, or offline-frontend issue remains. Live service connectivity and the deployment role's schema-creation permission were intentionally not tested; these are deployment validation steps and were not used to claim live integration success.

V1_ACCEPTED=true
