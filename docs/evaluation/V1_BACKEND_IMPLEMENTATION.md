# RagBot Evaluation V1 backend implementation

## Outcome

The backend foundation is integrated into the existing RagBot FastAPI process as a thin control plane, while the Celery worker remains separately startable. `python main.py` exposes `/api/v1/evaluation/*` and the built frontend at `/evaluation` when `EVAL_ENABLED=true`. The existing `AnsweringService` remains the single turn executor for production and evaluation.

The implementation did not modify `.env`, `.env.server_git`, live PostgreSQL data, Qdrant, MinIO, vLLM, TEI, prompts, thresholds, or model settings. No migration was run.

## Existing core files modified

- `answering_service.py`: accepts an optional history provider, evaluation observer, and execution policy while retaining production defaults; captures actual before/after history hashes; owns the shared mobile-compatible empty-answer fallback.
- `agent_service.py`: loads/saves graph state through the provider and gates ticket creation through the explicit policy. Production constructs `ProductionHistoryProvider` by default.
- `agent_graph.py`: delegates trimming and final-prompt history formatting to shared functions and emits evaluation observer stages without changing graph decisions.
- `intent_classifier.py`: consolidates detailed/basic classification through one inference call and emits probabilities to the optional observer.
- `new_architecture/app/services/history/rewriting.py`: delegates exact history formatting to the shared helper, records the existing rewrite prompt/output/settings, and removes two pre-existing customer-content `print` calls without changing rewrite decisions.
- `utils/RagSystem.py`: observes the exact prompt and effective final-generation arguments at their canonical construction/call sites.
- `utils/persian_hybrid_search.py`: observes ordered retrieval candidates/content/scores and the existing FAQ-related-question reranker.
- `mobile_api.py`: requests the shared empty-answer fallback and imports the shared category resolver; its path, request/response schemas, session resolution, query persistence, and feedback behavior are unchanged.
- `main.py`: injects the production provider and shared category resolver, reuses successful `/api/login` state, mounts the evaluation control plane, and serves the built UI at `/evaluation` when enabled.

New shared core files:

- `conversation_history.py`: provider protocol, production provider, policies, exact message trimming/formatting/selection, deterministic message reconstruction.
- `pipeline_observer.py`: task-local observer protocol, no-op production default, stage records, canonical JSON and SHA256.
- `document_category.py`: extracted unchanged datasource category resolver used by both startup paths.

`utils/request_instrumentation.py` was not changed and remains content-free.

## Evaluation backend layout

The isolated package is `evaluation_system/backend`:

- `app/api`: versioned FastAPI routers.
- `app/core_adapter`: evaluation history and side-effect-free canonical core runtime construction.
- `app/db`: dedicated `EvaluationBase`, models, async engine/session.
- `app/services`: importer, repository, migrations, config snapshot, event bus, bounded execution, run planning, divergence.
- `app/tracing`: evaluation-only in-memory collector.
- `app/worker`: Celery app, task, bounded run executor.
- `alembic`: evaluation-only migration environment.
- `tests`: offline/unit and dependency-gated integration safety tests.
- `scripts`: dependency check, status, API start, and worker start.

## Production-default proof

- `AnsweringService.answer(request)` still works without new keyword arguments.
- `PRODUCTION_EXECUTION_POLICY` is the default and allows the same existing effects.
- `AgentService` creates/uses `ProductionHistoryProvider` when none is supplied.
- `main.py` explicitly provides that same production provider.
- Mobile still provisions the production user, resolves the external mobile session, inserts/updates the same `queries` row, and returns the same `TalkResponse`.
- Evaluation never calls the mobile route and explicitly supplies `EvaluationHistoryProvider` plus `EVALUATION_EXECUTION_POLICY`.
- Existing production service/graph contracts and new parity spies exercise the same canonical dependency objects, not two implementations.

## Runtime configuration snapshot

Each run stores effective normalizer identity, intent threshold, rewrite prompt hash/settings, embedding model/dimension, retrieval limits, Qdrant collection, selected datasource identifiers, reranker model/threshold/scope, LLM model/settings, and Git SHA. The worker refreshes the snapshot from the actual constructed canonical runtime when claiming the run. Secret URLs, passwords, tokens, prompts, and document content are not placed in the configuration snapshot.

## Start commands

From repository root, after installing the normal RagBot runtime and `evaluation_system/backend/requirements.txt`:

```bash
cd evaluation_system/frontend && npm ci && npm run build && cd ../..
python main.py
evaluation_system/backend/scripts/start_worker.sh
```

The worker script reads the root `.env`. Its direct equivalent is:

```bash
python3 -m celery -A evaluation_system.backend.app.worker.celery_app:celery_app worker --loglevel=INFO --queues=ragbot-evaluation --pool=solo --concurrency=1
```

There is no second evaluation API process in the normal V1 flow. Open `/evaluation` on the existing RagBot host and sign in with an existing RagBot username/password. The worker remains separate because long-running evaluations never execute in HTTP handlers.

The worker deliberately imports the canonical RagBot runtime, so it also requires the repository's existing runtime modules (`numpy`, the deployment-compatible `torch`, `transformers`, `parsivar`, `rank_bm25`, `tqdm`, `langgraph`, `langchain-classic`, `openai`, and `qdrant-client`). The dependency-check script verifies both these inherited core dependencies and the evaluation-specific packages. The evaluation requirements file does not replace the deployment's GPU-specific RagBot/Torch installation.

For the CUDA-backed classifier, V1 uses Celery `solo` with concurrency one by default. The worker owns one process-local event loop and lazily enters `canonical_turn_runtime()` once, after the worker process has started. The resulting production-equivalent `AnsweringService`, classifier, Parsivar processor, RAG system, and clients are reused across tasks and all rows in those tasks. Worker shutdown closes the canonical runtime. A prefork pool is not supported for this CUDA-dependent runtime.

An uncaught worker-task or runtime-initialization exception durably marks a nonterminal run `FAILED`, stores a safe failure code, and emits `run_failed`. The known CUDA-after-fork signature maps to `CUDA_WORKER_INIT_FAILED`; exception messages and customer content are not persisted or emitted.

## Verification performed

Commands used:

```bash
python3 -m unittest discover -s evaluation_system/backend/tests -v
python3 -m unittest tests.test_answering_service tests.test_p0_p1_repairs
python3 -m compileall -q conversation_history.py pipeline_observer.py document_category.py answering_service.py agent_service.py agent_graph.py intent_classifier.py utils evaluation_system
```

Results in the current shell:

- production characterization suites: 20 passed;
- evaluation backend suite: 35 discovered, 33 passed and 2 dependency-gated skips;
- compile and `git diff --check`: passed;
- the additional repository normalization suites could not import because `numpy` is absent from this shell;
- the dependency checker correctly reports the remaining absent API/worker/core runtime packages.

The two skipped evaluation tests are the SQLAlchemy metadata/FK introspection test and the real XLSX parse test (`openpyxl` absent). No live integration, migration, Qdrant, TEI, vLLM, Redis, or PostgreSQL command was run.
