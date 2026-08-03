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

### Graph and node files

- `agent_graph.py` defines `AgentState`, constructs the LangGraph `StateGraph`, and contains the node factories and routing functions.
- The registered graph nodes are `add_user_message`, `classify_intent`, `handle_general`, `handle_chitchat`, `handle_personal`, `validate_slot`, and `add_assistant_message`.
- `agent_service.py` builds the graph and invokes it for each user turn. It persists agent state in PostgreSQL chat-session metadata rather than using a LangGraph checkpointer.
- No separate per-node files were found; the verified node implementations are in `agent_graph.py`.

### Model and retrieval clients

- vLLM client: `utils/RagSystem.py` creates an OpenAI-compatible `AsyncOpenAI` client using `VLLM_URL` and calls `chat.completions.create`.
- Embedding client: `utils/persian_hybrid_search.py` implements the async TEI `/embed` request in `PersianHybridSearch._encode_query`, using `TEI_EMBED_URL`.
- Reranking client: `utils/persian_hybrid_search.py` implements a batched async TEI `/rerank` request in `PersianHybridSearch.rerank`, using the TEI reranking URL. `utils/RagSystem.py` also carries `TEI_RERANK_URL`.
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
- `new_architecture/app/config.py`: service configuration loaded from environment variables.
- `main.py`: contains an additional inline Qdrant `Config` class.
- `scenarios.json`: agent intent/scenario definitions.
- `new_architecture/alembic/versions/alembic.ini`: Alembic configuration.
- Root `package.json`: root frontend dependency metadata.
- `qdrant-web-ui-master/package.json` and `static_qdrant/package.json`: bundled Qdrant UI build and test scripts.

No `pyproject.toml`, `requirements*.txt`, `pytest.ini`, `tox.ini`, or Makefile was found. The canonical Python dependency-installation command is therefore unknown.

## Docker

No Dockerfile, Compose file, or other repository-owned Docker definition was found. Docker build and run commands are unknown.

## Tests and benchmarks

- `python3 test_qdrant.py` runs the standalone, read-only Qdrant connectivity and collection inspection script. It contains a placeholder API key and requires access to its configured Qdrant endpoint.
- `cd qdrant-web-ui-master && npm test` runs the bundled Qdrant UI Vitest script.
- `cd static_qdrant && npm test` runs the second bundled Qdrant UI Vitest script.
- No repository-defined backend automated test-suite command was found; it is unknown.
- No retrieval-test or answer-quality-test command was found; both commands are unknown. This does not relax the requirement to run those tests before changing model behavior.
- `benchmarks/` and `docs/performance/` exist, but no benchmark runner or benchmark command was found. The benchmark command is unknown.

Do not claim a test or benchmark passed unless its command was actually run and its result recorded. Do not run connectivity tests against production.
