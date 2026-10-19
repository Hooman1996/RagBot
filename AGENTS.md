# Repository Guidance

## Scope and system facts

This repository contains a production-oriented Agentic RAG chatbot for a neo-banking application.

- The external maximum request timeout is 50 seconds.
- Staging currently has one NVIDIA RTX 5880 Ada Generation GPU with 48 GB VRAM.
- Production has two NVIDIA L4 GPUs with 24 GB VRAM each.
- The generative model is served through vLLM.
- Embedding and reranking are served through Hugging Face Text Embeddings Inference (TEI).
- PostgreSQL stores relational data and chat-session data.
- Qdrant stores vectors.
- MinIO stores objects.
- The current staging TEI endpoints use port `7997` for embedding and port `7998` for reranking.

## Non-negotiable constraints

- Never change production infrastructure from this staging repository.
- Every performance change requires before-and-after benchmarks.
- Optimize one major variable per experiment.
- Never log prompts, customer data, authentication values, or banking data.
- Do not change model behavior without running retrieval tests and answer-quality tests.

## Verified application map

### Application entry point

- `main.py` defines the FastAPI application as `main:app`.
- Direct execution starts Uvicorn with `uvicorn.run("main:app", ...)`.
- `main.py` mounts static files at `/static` and includes the routers from `mobile_api.py` and `kb_manager.py`.

### FastAPI endpoint paths

Endpoints defined directly in `main.py`:

- `POST /api/login`
- `GET /`
- `GET /app`
- `GET /analytics`
- `POST /api/initialize`
- `GET /api/documents`
- `POST /api/query`
- `GET /api/sessions`
- `POST /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/message`
- `GET /api/sessions/{session_id}/messages`
- `DELETE /api/sessions/{session_id}`
- `PATCH /api/sessions/{session_id}/pin`
- `GET /api/sessions/{session_id}/download`
- `PATCH /api/queries/{query_id}/feedback`
- `PATCH /api/queries/{query_id}/comment`
- `POST /api/sessions/{session_id}/satisfaction`
- `GET /api/ocr/status`
- `POST /api/ocr/extract`
- `POST /api/mass-answer`
- `GET /api/analytics`
- `GET /api/health`

Endpoints from `mobile_api.py`, whose router prefix is `/api/mobile`:

- `POST /api/mobile/v1/talk`
- `GET /api/mobile/v1/history`
- `POST /api/mobile/v1/queries/{query_id}/feedback`
- `POST /api/mobile/v1/queries/{query_id}/comment`
- `POST /api/mobile/v1/sessions/{session_id}/satisfaction`

Endpoints from `kb_manager.py`, whose router prefix is `/knowledge-base`:

- `GET /knowledge-base/`
- `GET /knowledge-base/api/documents`
- `GET /knowledge-base/api/chunks/{document_id}`
- `POST /knowledge-base/api/chunks/create`
- `PUT /knowledge-base/api/chunks/update`
- `DELETE /knowledge-base/api/chunks/delete/{chunk_id}`
- `GET /knowledge-base/api/chunks/{chunk_id}/versions`
- `POST /knowledge-base/api/chunks/revert`

#### Knowledge-coverage check routes

`coverage_check.api.mount` includes these routes when `KNOWLEDGE_COVERAGE_ENABLED` is not `false`, whatever `ENVIRONMENT` says; `main.py` calls it. With the flag `false`, the `coverage_check_gate` middleware in `main.py` returns 404 for every coverage path. Access comes from `COVERAGE_ROLE_CAPABILITIES` in `web_permissions.py` (`admin`: `coverage_run_start`, `coverage_results_view`; `dashboard_viewer`: `coverage_results_view`). The old audit in `knowledge_audit/` stays on disk but is no longer mounted; step 25 deletes it. Suggestions draft FAQ text only, into the run's private folder, and never change the knowledge base.

- `GET /knowledge-coverage`
- `GET /api/knowledge-coverage/documents`
- `POST /api/knowledge-coverage/checks`
- `GET /api/knowledge-coverage/checks`
- `GET /api/knowledge-coverage/checks/{run_id}`
- `GET /api/knowledge-coverage/checks/{run_id}/rows`
- `GET /api/knowledge-coverage/checks/{run_id}/rows/{row}`
- `POST /api/knowledge-coverage/checks/{run_id}/cancel`
- `POST /api/knowledge-coverage/checks/{run_id}/resume`
- `GET /api/knowledge-coverage/checks/{run_id}/export`
- `POST /api/knowledge-coverage/checks/{run_id}/suggestions`
- `GET /api/knowledge-coverage/checks/{run_id}/suggestions`
- `POST /api/knowledge-coverage/checks/{run_id}/suggestions/cancel`

#### Routes from `internal_evaluation_api.py`

The router prefix is `/api/internal/evaluation/v1`. `main.py` includes it unconditionally.

- `GET /api/internal/evaluation/v1/datasources`
- `GET /api/internal/evaluation/v1/runtime-snapshot`
- `POST /api/internal/evaluation/v1/turn`

### Graph and node files

- `agent_graph.py` defines `AgentState`, constructs the LangGraph `StateGraph`, and contains the node factories and routing functions.
- The registered graph nodes are `add_user_message`, `classify_intent`, `handle_general`, `handle_chitchat`, `handle_personal`, `validate_slot`, and `add_assistant_message`.
- `agent_service.py` builds the graph and invokes it for each user turn. It persists agent state in PostgreSQL chat-session metadata rather than using a LangGraph checkpointer.
- No separate per-node files were found; the verified node implementations are in `agent_graph.py`.

### Model and retrieval clients

- vLLM client: `utils/RagSystem.py` creates an OpenAI-compatible `AsyncOpenAI` client using `VLLM_URL` and calls `chat.completions.create`.
- Embedding client: `utils/persian_hybrid_search.py` implements the async TEI `/embed` request in `PersianHybridSearch._encode_query`, using `TEI_EMBED_URL`.
- Reranking client: `utils/persian_hybrid_search.py` implements a batched async TEI `/rerank` request in `PersianHybridSearch.rerank`, using the TEI reranking URL. `utils/RagSystem.py` also carries `TEI_RERANK_URL`.
- Reranking uses `min(TEI_RERANK_MAX_CLIENT_BATCH_SIZE, server /info limit)`, falls back to `TEI_RERANK_VERIFIED_MAX_BATCH_SIZE` when `/info` is unavailable, and otherwise fails closed.
- The staging `.env` currently assigns `TEI_EMBED_URL` to port `7997` and `TEI_RERANK_URL` to port `7998`.

### Data-service clients

- PostgreSQL client used by the application startup: `new_architecture/app/services/db_connection/connection.py` creates a `psycopg2` connection in `DatabaseConnections`.
- PostgreSQL relational and chat operations: `new_architecture/app/services/history/database.py` defines `DatabaseManager` and `ChatManager`; `DatabaseManager` opens `psycopg2` connections per operation.
- PostgreSQL pool implementation: `new_architecture/app/core/database.py` defines a SQLAlchemy engine with `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, and `pool_pre_ping`, plus `SessionLocal`. This module is not imported by the verified `main.py` startup path, so use of that pool by the running application is unknown.
- Qdrant client: `main.py` creates the client passed into `RAGSystem`; `new_architecture/app/services/db_connection/connection.py` also creates a Qdrant client during application startup.
- MinIO client: `new_architecture/app/services/db_connection/connection.py` creates the MinIO client during application startup and ensures the configured bucket exists.

## Configuration

Verified configuration files and sources:

- `.env`: local runtime configuration; treat it as sensitive and never print, log, or commit its secret values.
- `env.example`: environment-variable example.
- `.env.server_git`: server-oriented environment configuration present in the worktree; treat it as sensitive.
- `Production_ENV.example`: tracked copy of the production keys, with secret values empty.
- `Production_ENV`: local only, untracked.
- `new_architecture/app/config.py`: service configuration loaded from environment variables.
- `main.py`: contains an additional inline Qdrant `Config` class.
- `scenarios.json`: agent intent/scenario definitions.
- `new_architecture/alembic/versions/alembic.ini`: Alembic configuration.
- Root `package.json`: root frontend dependency metadata.
- `qdrant-web-ui-master/package.json` and `static_qdrant/package.json`: bundled Qdrant UI build and test scripts.
- Knowledge-coverage check gate: the check routes and background task run when `KNOWLEDGE_COVERAGE_ENABLED` is not `false`, whatever `ENVIRONMENT` says (`coverage_check/settings.py` `coverage_enabled`); `load_settings` validates every `KNOWLEDGE_COVERAGE_*` key at startup. Access comes from `COVERAGE_ROLE_CAPABILITIES` in `web_permissions.py`.

`pytest.ini` now exists. No `pyproject.toml`, `requirements*.txt`, `tox.ini`, or Makefile was found. The canonical Python dependency-installation command is therefore unknown.

## Docker

No Dockerfile, Compose file, or other repository-owned Docker definition was found. Docker build and run commands are unknown.

## Tests and benchmarks

- `python3 test_qdrant.py` runs the standalone, read-only Qdrant connectivity and collection inspection script. It contains a placeholder API key and requires access to its configured Qdrant endpoint.
- `cd qdrant-web-ui-master && npm test` runs the bundled Qdrant UI Vitest script.
- `cd static_qdrant && npm test` runs the second bundled Qdrant UI Vitest script.
- `scripts/run_offline_tests.sh` runs the offline pytest suite, the Node frontend tests, the offline frontend audit and, when `BROWSER_NODE_DIR` is set, all browser harnesses. Set `REQUIRE_BROWSER=1` to fail when browsers are unavailable.
- Retrieval test: `scripts/retrieval_eval.py` (`freeze`, `run`, `label-sheet`, `compare`). Answer-quality test: `scripts/answer_quality_eval.py` (`collect`, `blind`, `score`). Both are staging-only, need human labels (relevance labels and blind grades), and follow `docs/performance/RELEASE_EVALUATION_RUNBOOK.md`.
- Coverage-audit benchmarks, run with `conda run --no-capture-output -n faq python <script>`; each prints its results as JSON lines and contacts no service:
  - `scripts/benchmark_coverage_budgets.py`: checkpoint and budget-allowance file-I/O overhead on a mocked 918-row input.
  - `scripts/benchmark_coverage_progress.py`: progress-index versus full-row reads for checkpoints and polling on a synthetic 918-row run.
  - `scripts/benchmark_coverage_dedupe.py`: model calls, retrieval fetches and wall time of a mocked 50-row run with repeated-question copying off and on, plus the 918-row source-map rebuild.
- `scripts/coverage_compare.py` compares two coverage checks and, with `--expected`, a labelled CSV. It prints counts and row numbers only and contacts no service.

Do not claim a test or benchmark passed unless its command was actually run and its result recorded. Do not run connectivity tests against production.
