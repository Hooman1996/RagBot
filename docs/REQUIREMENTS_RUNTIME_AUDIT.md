# RagBot Production Runtime Requirements Audit

Audit date: 2026-09-20  
Repository: `/root/projects/faq`  
Status: candidate only; clean-environment validation has not been performed.

# 1. Executive Summary

This was an audit-only review. No package was installed, removed, upgraded, or downgraded, and no existing source, configuration, manifest, lock, Docker, or evaluation-system file was changed.

The audit started at `main.py`, parsed imports with Python's AST, followed local imports recursively (including package `__init__.py` execution), and then manually reviewed startup/shutdown, route-specific imports, imports inside functions, optional imports, service factories, file-backed runtime artifacts, and external client calls. The resulting production graph contains 51 reachable local Python modules. No reachable `importlib`, entry-point, plugin-registry, or string-based dynamic Python module loader was found. Function-local imports in `main.py`, `mobile_api.py`, and `kb_manager.py` were included.

The application boundary is the FastAPI app `main:app`, its lifespan, all routers mounted by `main.py`, and services constructed during lifespan startup. It includes web and mobile chat, history/session/authentication, knowledge-chunk management, mass answer, optional OCR, analytics/health/metrics, and the in-process internal evaluation endpoints. The standalone `evaluation_system/` service, tests, training programs, benchmarks, notebooks, migration utilities, profiling/load-test code, and developer tools are outside this boundary. One generated data artifact under `training/` is nevertheless runtime-reachable: `training/persian_normalization/kb_phrase_lexicon.json` is loaded at import time by `utils/persian_query_normalizer.py`; this is a deployment asset, not a Python dependency.

`requirements.lock.txt` has 466 requirement records from a broad development/model-serving environment. It mixes application libraries with vLLM internals, multiple ML frameworks, training/notebook/UI tooling, evaluation infrastructure, optional accelerators, transitive libraries, and machine-local/editable installs. It is therefore unsuitable as a maintained list of RagBot's direct application dependencies.

Gemma generation is remote through an OpenAI-compatible vLLM endpoint. Jina embedding and BGE reranking are remote TEI HTTP endpoints. RagBot needs `openai` and `httpx` to call those services, not the packages required to host those models. This does not eliminate local ML: `intent_classifier.py` loads a checkpoint and executes a local PyTorch MLP, and production configuration declares the classifier required on `cuda`.

The candidate has 22 entries: 21 required direct dependencies and one feature-specific dependency (`openpyxl`) for the exposed `.xlsx` mass-answer path. `python-magic` is an optional enhancement for a document-upload service that is imported through a package initializer but is not constructed or routed by `main.py`; it is not in the candidate. OCR cannot be resolved statically because the optionally imported `ocr_service` module is absent from both the repository and the audit interpreter.

# 2. Production Entry Points Reviewed

## Application and lifecycle

- `main.py` defines `main:app` and direct execution runs `uvicorn.run("main:app", ...)`.
- Lifespan constructs the Persian processor, PostgreSQL/MinIO/Qdrant connections, shared HTTP clients, OpenAI-compatible vLLM client, RAG system, history rewriting, local intent classifier, LangGraph agent, answering service, and mass-answer services.
- Lifespan shutdown closes mass-answer jobs, RAG/search clients, OpenAI/httpx clients, database/object/vector clients, and the blocking runner.
- Startup eagerly initializes PostgreSQL, verifies/creates the MinIO bucket, verifies/creates the Qdrant collection, loads scenarios, and loads the local classifier checkpoint when configured as required.

## Routes defined in `main.py`

- Authentication and pages: `POST /api/login`, `GET /`, `GET /app`, `GET /analytics`.
- Chat and data sources: `POST /api/initialize`, `GET /api/documents`, `POST /api/query`.
- Sessions/history: all `/api/sessions` create/read/message/delete/pin/download/satisfaction routes.
- Feedback and analytics: query feedback/comment routes, `GET /api/analytics`.
- OCR: `GET /api/ocr/status`, `POST /api/ocr/extract`.
- Mass answer: `POST /api/mass-answer` and the job cleanup/status/result/delete routes.
- Operations: `GET /api/health`, `GET /api/metrics/admission`.

## Mounted routers

- `mobile_api.py`: mobile talk, history, feedback, comment, close-session, and satisfaction routes under `/api/mobile/v1`.
- `kb_manager.py`: knowledge-base UI plus document/chunk list, create, update, delete, versions, and revert routes under `/knowledge-base`.
- `internal_evaluation_api.py`: persistence-free `POST /api/internal/evaluation/v1/turn` and `GET /api/internal/evaluation/v1/runtime-snapshot`. This is part of RagBot; it is distinct from the excluded standalone `evaluation_system/` application.

## Services and runtime paths inspected

- `answering_service.py`, `agent_service.py`, `agent_graph.py`, `conversation_history.py`.
- `new_architecture/app/services/history/database.py` and `rewriting.py`.
- `utils/RagSystem.py`, `utils/persian_hybrid_search.py`, `utils/tei_embedding_client.py`, normalization/canonicalization, concurrency, instrumentation, and error helpers.
- `intent_classifier.py` and `intent_classifier_factory.py`.
- PostgreSQL, MinIO, and Qdrant startup clients and knowledge-update coordination.
- Mass-answer parsing/serialization/processing/jobs.
- Authentication, package-initializer-loaded document/chunking/feedback services, templates/static paths, and optional OCR import.

# 3. Required Direct Runtime Dependencies

Versions below come from `requirements.lock.txt` unless explicitly noted. A pinned version records the current known-good environment; it is not proof that the candidate can be installed from the production package index.

| PyPI package | Imported as | Evidence/file(s) | Runtime purpose | Required/Optional | Version source |
|---|---|---|---|---|---|
| `bcrypt` | `bcrypt` | `new_architecture/app/services/authentication/authentication.py:18`; `db_connection/connection.py:17` | Password hash verification; eager startup import | Required | lock `5.0.0` |
| `fastapi` | `fastapi` | `main.py:24-29`; all three routers | ASGI application, routes, requests/responses, templates, uploads | Required | lock `0.124.0` |
| `httpx` | `httpx` | `main.py:8,253-298`; `utils/RagSystem.py:20`; `utils/persian_hybrid_search.py:27`; `utils/tei_embedding_client.py:9` | Shared HTTP transports for vLLM and TEI | Required | lock `0.28.1` |
| `Jinja2` | via `Jinja2Templates` | `main.py:26,503`; `kb_manager.py:8,25` | Render shipped HTML routes/templates | Required | lock `3.1.6` |
| `langchain-classic` | `langchain_classic` | `utils/RagSystem.py:13` | Eager import of `RetrievalQA`; symbol is unused but currently required for `import main` | Required by current source | lock `1.0.0` |
| `langgraph` | `langgraph` | `agent_graph.py:19,435-485` | Builds and executes the production agent state graph | Required | lock `1.2.0` |
| `minio` | `minio` | `db_connection/connection.py:9-10,60-82`; document upload module | Required startup MinIO connection and object-store client | Required | lock `7.2.20` |
| `numpy` | `numpy` / `np` | `intent_classifier.py:16,93,151,165`; `utils/persian_hybrid_search.py:1`; `utils/RagSystem.py:4` | Classifier embedding arrays and hybrid retrieval scoring | Required | lock `2.2.6` |
| `openai` | `openai` | `main.py:31,299-310`; `utils/RagSystem.py:19,191-219` | OpenAI-compatible client for external vLLM | Required | lock `2.6.1` |
| `openpyxl` | pandas engine `openpyxl` | `mass_answer_files.py:135-148,182-202` | `.xlsx` mass-answer read/write | Optional production feature, included for shipped `.xlsx` support | lock `3.1.5` |
| `pandas` | `pandas` / `pd` | `main.py:19,1198-1217`; `mass_answer_files.py:13` | CSV/XLSX mass-answer dataframes and serialization | Required | lock `2.3.3` |
| `parsivar` | `parsivar` | `utils/persian_hybrid_search.py:12`; `kb_manager.py:14` | Persian normalization/tokenization/stemming and KB normalization | Required | lock `0.2.3.1` |
| `psycopg2-binary` | `psycopg2` | `main.py:32`; history/auth/mobile/KB/database modules | PostgreSQL connections, cursors, transactions, sessions/history | Required | lock `2.9.11` |
| `pydantic` | `pydantic` | `main.py:30`; `mobile_api.py:2`; `kb_manager.py:9`; `internal_evaluation_api.py:17` | Request/response models and validation | Required | lock `2.12.5` |
| `python-dotenv` | `dotenv` | `main.py:14`; configuration/database/RAG/search modules | Loads local environment configuration | Required by current source | lock `1.2.1` |
| `python-multipart` | FastAPI form parser | `main.py:24,27,1030,1080-1084` | Required by FastAPI's `File(...)`, `Form(...)`, and OAuth2 form route construction | Required | lock `0.0.20` |
| `qdrant-client` | `qdrant_client` | `utils/RagSystem.py:1`; `utils/persian_hybrid_search.py:18-19`; startup/KB modules | Qdrant connection, filtered vector query, and KB vector writes | Required | lock `1.16.2` |
| `rank-bm25` | `rank_bm25` | `utils/persian_hybrid_search.py:15,454-474` | Local lexical BM25 side of hybrid retrieval | Required | lock `0.2.2` |
| `torch` | `torch`, `torch.nn` | `intent_classifier.py:17-18,33-55,85,107-121,243-267` | Local intent-checkpoint load and no-grad MLP inference | Required | lock `2.9.1+cu130`; wheel/index needs verification |
| `tqdm` | `tqdm` | `utils/persian_hybrid_search.py:8`; package-initializer-loaded chunker | Eager import and optional progress iteration | Required by current import graph | lock `4.67.1` |
| `transformers` | `transformers` | `new_architecture/app/services/history/rewriting.py:6` | Eager `AutoModelForCausalLM`/`AutoTokenizer` import; local history model code is commented out and remote vLLM performs rewriting | Required by current source; cleanup candidate | lock identifies `5.10.1` through a machine-local wheel |
| `uvicorn` | `uvicorn` | `main.py:1839-1843` | Direct `python main.py` ASGI server path | Required for repository-defined launch path | lock `0.38.0` |

The candidate does not list standard-library modules, local modules, or dependencies owned transitively by the packages above.

# 4. External Model Serving Dependencies

## vLLM

RagBot creates `openai.AsyncOpenAI` with `VLLM_URL` as `base_url` and a shared `httpx.AsyncClient` (`main.py:276-310`). Generation calls `self.client.chat.completions.create(...)` (`utils/RagSystem.py:191-219,322-337`). No reachable code imports `vllm` or loads Gemma weights locally.

Therefore `vllm` itself and its server stack are not RagBot application dependencies: Ray, FlashAttention/FlashInfer, compressed-tensors, outlines/outlines-core, xgrammar, llguidance, lm-format-enforcer, gguf, openai-harmony, model-hosting-container-standards, sgl-kernel, and server-specific CUDA/CuPy tooling are excluded as direct dependencies. The local intent classifier may still cause Torch's own CUDA runtime components to be installed transitively; that is a separate requirement from vLLM serving.

## TEI embedding

`PersianHybridSearch._encode_query` delegates to `TeiEmbeddingClient`, which POSTs JSON to `{TEI_EMBED_URL}/embed` with `httpx` and validates the numeric response (`utils/tei_embedding_client.py`; `utils/persian_hybrid_search.py:303-328`). KB writes use the same remote service through the synchronous client (`utils/persian_hybrid_search.py:348-381`). Jina model weights are not loaded in-process.

TEI's embedding server, `sentence-transformers`, local Jina model code, model-download tooling, and serving CUDA stack are not direct RagBot dependencies.

## TEI reranker

Answer-context and related-question reranking POST JSON to `{TEI_RERANK_URL}/rerank` with the shared `httpx.AsyncClient` (`utils/persian_hybrid_search.py:682-788,868-963`). BGE weights/tokenizers are not loaded by the application.

TEI's reranker model-serving stack is not a direct RagBot dependency. `transformers`, `tokenizers`, and `huggingface_hub` may still appear after candidate installation only because current RagBot source has an unrelated eager `transformers` import; they are not needed to call TEI.

# 5. Local ML Dependencies

`intent_classifier.py` defines `_GuardrailNet`, a fixed `1024 -> 512 -> 128 -> 32 -> 2` PyTorch network. Construction:

- selects the configured `torch.device`;
- hashes and loads `INTENT_CLASSIFIER_MODEL_PATH` with `torch.load(..., weights_only=True)`;
- validates checkpoint architecture, labels, embedding role/dimension, normalizer, and threshold metadata;
- loads `model_state_dict`, moves the model to the configured device, and enters evaluation mode;
- converts the remote 1024-dimensional TEI embedding to a tensor and performs a locked `torch.no_grad()` forward pass followed by `torch.softmax`.

Both `.env` and `Production_ENV` declare `INTENT_CLASSIFIER_REQUIRED=true` and `INTENT_CLASSIFIER_DEVICE=cuda`. The checkpoint referenced by `.env` exists in this worktree; the path written in `Production_ENV` does not exist on the audit host and must be supplied correctly in the production image/mount. Values other than the non-secret flags, device, basename, and existence check were not printed during the audit.

PyTorch therefore remains a direct application dependency even though Gemma, Jina, and BGE are remote. NumPy also remains direct. Torch-selected CUDA libraries are transitive to the chosen CUDA Torch build and should not be maintained as independent top-level requirements. The `2.9.1+cu130` production wheel source and NVIDIA L4 driver compatibility require validation.

# 6. Optional Production Features

| Package/module | Importing file | Feature | Behavior when absent | Configuration/use assessment |
|---|---|---|---|---|
| `openpyxl` | `mass_answer_files.py` through pandas | `.xlsx` mass-answer upload/export | CSV mass answer still works; `.xlsx` parsing/writing fails and is converted to an endpoint error | The endpoint explicitly advertises and implements `.xlsx`; included in the candidate |
| `python-magic` (`magic`) | `new_architecture/app/services/document/validation.py:15-20` | Content-based MIME validation in `DocumentValidator` | `HAS_MAGIC=False`; validator falls back to extension/`mimetypes` behavior | The module is eagerly reached through `services/__init__.py`, but `DocumentUploadService` is not constructed or exposed by a `main.py` route; omitted from candidate |
| unresolved provider for `ocr_service.OCRService` | `main.py:88-91` | `/api/ocr/extract` | Import failure is caught; status reports unavailable and extract returns HTTP 503 | No `ocr_service.py`, installed module, or OCR-specific production flag was found. Two machine-local editable OCR distributions in the lock need manual identification |

The KB manager supports chunk-level create/update/delete/revert and remote embedding, but no production document-file upload endpoint constructs `DocumentUploadService`. MinIO remains required because lifespan startup treats it as a mandatory service.

# 7. Packages Safe to Remove from RagBot Runtime

“Safe to remove” here means “do not maintain as a direct RagBot application requirement.” A transitive package may still be installed by its owning direct dependency. No packages were actually removed.

| Package/family | Why it exists currently | Why RagBot runtime does not need it as a direct dependency | Evidence |
|---|---|---|---|
| vLLM server stack: `vllm`, Ray, FlashAttention/FlashInfer, compressed-tensors, outlines, xgrammar, llguidance, server kernels | Shared model-serving/development environment | RagBot calls an external OpenAI-compatible endpoint | `main.py:276-310`; `utils/RagSystem.py:191-219` |
| TEI/local embedding/reranker stack: `sentence-transformers`, model-serving utilities, local model loaders | Shared ML environment | Embedding and reranking are HTTP calls to TEI | `utils/tei_embedding_client.py`; `utils/persian_hybrid_search.py` |
| JAX/Flax ecosystem: `jax`, `jaxlib`, `flax`, `optax`, `orbax-checkpoint`, `chex`, `clu`, `kauldron`, `grain`, `tensorstore`, `treescope` | Model/training experimentation | No reachable production import or execution | 51-module reachable import graph |
| TensorFlow/Keras ecosystem | Training/model environment | No reachable production import | Reachable import graph |
| Extra model runtimes: `llama_cpp_python`, `bitsandbytes`, CuPy, FAISS, `gemma` | Local serving/experimentation | No reachable production use; external services own Gemma/Jina/BGE | Reachable import graph and HTTP client paths |
| Training/data libraries: `datasets`, tensorboard, scikit-learn, pyarrow, timm | Training/evaluation environment | Production classifier only performs Torch inference on a provided checkpoint | `intent_classifier.py` |
| Notebook/UI tooling: IPython, ipywidgets, Jupyter widget packages, Gradio, Streamlit, Altair, Plotly | Interactive development | No production import or route dependency | Reachable import graph |
| Standalone evaluation stack: Redis, SSE, Celery-related packages in the alternate manifest | `evaluation_system/` service | `main.py` only mounts `internal_evaluation_api.py`; it does not import standalone evaluation packages | Router imports and application graph |
| Database/migration alternatives: asyncpg, psycopg 3, Alembic, standalone SQLAlchemy usage | Setup/migrations/evaluation environment | Running app uses synchronous `psycopg2`; SQLAlchemy is only a transitive dependency of retained `langchain-classic` | Production DB modules |
| Profiling/load/dev tooling: `py-spy`, Docker SDK, Git tooling, build/uv/pip/wheel, supervisor, formatting/testing-related packages | Development and operations environments | No production import path | Reachable graph and excluded-area policy |
| Image/OCR candidates such as duplicate OpenCV packages, PDF/image utilities | Broad OCR/dev environment | Current OCR provider module is absent and failure is optional; not justified in core candidate | `main.py:88-91,1020-1071` |

The exhaustive `REMOVE_FROM_RAGBOT_RUNTIME` package list and counts are in “Appendix B — Existing Lock Classification.”

# 8. Transitive Dependencies

The lock contains many libraries that may legitimately be installed, but should be owned by a direct dependency rather than independently maintained. Examples:

- FastAPI/Pydantic/httpx: Starlette, AnyIO, `pydantic_core`, annotated/typing helpers, httpcore, h11, certifi, idna, sniffio.
- OpenAI: jiter plus its HTTP/Pydantic dependencies.
- LangGraph/LangChain Classic: `langchain-core`, text splitters, LangGraph checkpoint/prebuilt/SDK packages, LangSmith, SQLAlchemy, jsonpatch, tenacity, ormsgpack, orjson, xxhash.
- Transformers: Hugging Face Hub, tokenizers, safetensors, regex, requests, packaging, `hf-xet` as selected by that distribution.
- Torch CUDA build: SymPy, NetworkX, filelock, FSSpec, Triton, and the CUDA/NVIDIA runtime packages selected by the actual Torch wheel.
- MinIO: urllib3, certifi, argon2/cffi, and crypto dependencies.
- pandas/openpyxl/Parsivar: date/time packages, `et_xmlfile`, NLTK/joblib/six as selected by their distributions.
- Qdrant client: gRPC/protobuf, portalocker, HTTP/URL dependencies.

The candidate intentionally does not pin these. The resolver for the chosen direct versions should select them, and the later `pip check` must prove consistency.

# 9. Manual Verification Required

1. **OCR provider identity and dependency closure.** Determine whether production is expected to supply a package exporting `ocr_service.OCRService`. The repository has no such module, and the audit interpreter cannot resolve it. The two lock records are editable paths to `dots.ocr` and `dotsocr` on `/home/hooman/...`, but static evidence does not prove that either exports `ocr_service`. In a production-like image, run `python -c "import ocr_service; print(ocr_service.__file__)"`, inspect that distribution's metadata, and exercise both image and PDF routes. Until then, OCR is intentionally absent from the candidate.
2. **Portable Transformers artifact.** The lock pins Transformers through `/storage/models/Engines/transformers-5.10.1-py3-none-any.whl`. The candidate records `transformers==5.10.1`, derived from that wheel filename. Confirm that this exact artifact/version exists in the production package source and that its hash/provenance is approved. It is currently needed only because of an eager unused import.
3. **Production Torch build.** Confirm where `torch==2.9.1+cu130` will be obtained, that its CUDA dependencies resolve without separately pinning the frozen `nvidia-*` list, and that it is compatible with the production L4 driver. Validate actual checkpoint load and inference on the configured device.
4. **Clean-environment proof.** The audit interpreter lacks most project dependencies, so `import main` and lifespan execution were not attempted. Static analysis cannot replace the validation plan in section 12.

Additional deployment checks: package the classifier checkpoint, `scenarios.json`, `config/retrieval_query_aliases.json`, templates/static assets, and the runtime-loaded `training/persian_normalization/kb_phrase_lexicon.json`. The last file is in a nominally training-only directory but is a production runtime asset.

# 10. Suspicious / Machine-Specific Dependencies

The current lock contains non-portable entries:

- `addict @ file:///nvme/wheels/...`
- `cymem`, `finglish`, `murmurhash`, `preshed`, `spacy-legacy`, and `spacy-loggers` from `/home/hooman/Downloads/...`
- `flash_attn @ file:///home/hooman/Downloads/...`
- `pip @ file:///home/hooman/pycharm/plugins/...`
- `transformers @ file:///storage/models/Engines/...`
- editable `/home/hooman/PycharmProjects/RegAssist/new_architecture/dots.ocr` and `dotsocr`
- `dialog` from a pinned GitHub commit.

Of these, only Transformers corresponds to a current unconditional RagBot import; it is normalized to the discovered version in the candidate but still needs artifact verification. The two editable OCR entries are manual-verification items. The others have no reachable production import and are excluded. The newer untracked root snapshot `requirements_sep_8_2026.txt` adds more development/evaluation packages and a Git editable `snappbox_decision_support`; it does not change the production import graph and was not edited.

No `pyproject.toml`, Pipfile, Poetry lock, setup metadata, or repository Dockerfile exists at the root. Root `package.json` contains only a browser Chart.js dependency and is not a Python runtime manifest.

# 11. Candidate Requirements Summary

`requirements.runtime.candidate.txt` contains:

- 21 required direct application dependencies;
- 1 included optional-feature dependency (`openpyxl`) for the shipped `.xlsx` mass-answer path;
- 22 total candidate requirement lines;
- 2 identified optional production dependencies overall (`openpyxl`, included; `python-magic`, omitted);
- 362 current lock records classified `REMOVE_FROM_RAGBOT_RUNTIME`;
- 79 current lock records classified `TRANSITIVE` and deliberately not copied;
- 2 current lock records classified `MANUAL_VERIFICATION` (the editable OCR distributions);
- 444 of the lock's 466 records not carried into the direct candidate.

No version was invented. Twenty-one candidate versions are direct lock pins. The Transformers version is extracted from the lock's machine-local wheel filename and clearly marked for verification.

# 12. Clean-Environment Validation Plan

Do not replace any production dependency file until every step passes in a disposable production-like staging environment. Do not run these steps against production services.

1. Create a clean Python environment or clean application container matching the production Python version, OS, architecture, CUDA driver, and approved indexes/wheelhouse.
2. Install only `requirements.runtime.candidate.txt`. For Torch, use the approved source capable of providing the exact CUDA build. Do not add packages ad hoc; record any missing import as an audit finding.
3. Run `python -m pip check` and save the output/package-resolution report.
4. Run `python -c "import main; print(main.app.title)"` from the repository root.
5. Start FastAPI through the intended production command and, separately if supported, verify the repository-defined `python main.py`/Uvicorn path.
6. Confirm lifespan startup completes and readiness becomes true; then inspect logs for safe error types only, without prompts, auth values, customer data, or banking data.
7. Confirm the local intent classifier finds the expected checkpoint, validates SHA/metadata, loads on the configured device, and performs representative actionable/chitchat inference.
8. Verify PostgreSQL connection, schema-dependent initialization, authentication, session/history reads/writes, feedback, and ticket path against disposable staging data.
9. Verify Qdrant connection, filtered query, collection/vector dimensions, and KB create/update/delete/revert against a disposable staging collection.
10. Verify MinIO bucket access and object path against a disposable staging bucket. Note that current startup creates a missing bucket.
11. Send a TEI embedding request and verify response count and 1024 dimensions.
12. Send TEI reranking requests for both answer-context and related-question shapes and verify index/score validation.
13. Send a vLLM chat-completions request through the `openai` client and verify timeout/error translation.
14. Exercise a regular document-backed RAG query, including BM25, Qdrant, embedding, reranking, prompt construction, and generation.
15. Exercise a chitchat query and prove retrieval/reranking are skipped while generation succeeds.
16. Exercise a multi-turn history/rewrite query and verify rewriting uses the remote vLLM client rather than a local Transformers model.
17. Exercise mobile talk, history, feedback/comment, close-session, and satisfaction paths.
18. Exercise knowledge-base pages and chunk create/update/delete/version/revert. If document-file upload is considered production-supported, separately decide whether `python-magic` is required and add a routed validation.
19. Exercise mass-answer CSV and XLSX direct and queued-job paths, including output download and cleanup.
20. Exercise internal evaluation `/turn` and `/runtime-snapshot`, verifying persistence isolation and all pipeline stages.
21. Verify graceful shutdown closes HTTP, PostgreSQL, Qdrant, MinIO, job, and executor resources without cleanup errors.

After functional validation, run retrieval regression tests and answer-quality tests before any source cleanup that removes eager `transformers` or `langchain-classic` imports. Only after the complete clean-environment validation passes should this candidate replace an existing production requirements file.

# Appendix A — Reachable Import Classification

## A. Python standard library

`__future__`, `asyncio`, `collections`, `collections.abc`, `contextlib`, `contextvars`, `copy`, `csv`, `dataclasses`, `datetime`, `enum`, `functools`, `glob`, `hashlib`, `html`, `inspect`, `io`, `json`, `logging`, `math`, `mimetypes`, `operator`, `os`, `pathlib`, `re`, `shutil`, `subprocess`, `sys`, `tempfile`, `textwrap`, `threading`, `time`, `typing`, `unicodedata`, `uuid`.

## B. Local project modules

The 51 reachable local modules are:

- Root services: `main`, `mobile_api`, `kb_manager`, `internal_evaluation_api`, `answering_service`, `agent_service`, `agent_graph`, `conversation_history`, `intent_classifier`, `intent_classifier_factory`, `mass_answer_service`, `mass_answer_files`, `mass_answer_jobs`, `pipeline_observer`, `document_category`, `frontend_paths`.
- Runtime utilities: `utils` package plus `RagSystem`, `client_lifecycle`, `concurrency`, `performance_config`, `persian_hybrid_search`, `persian_normalization`, `persian_query_normalizer`, `rag_utils`, `request_instrumentation`, `retrieval_query_canonicalizer`, `revision_cache`, `service_errors`, `tei_embedding_client`.
- Architecture modules: `new_architecture`, `new_architecture.app`, configuration, `new_architecture.knowledge_sources`, `new_architecture.knowledge_update`, and the reachable `services` package modules for authentication, chunking, DB connection, document validation/upload, feedback/analytics, and history database/rewriting.

## C/D/G. Third-party and unresolved imports

Required direct third-party imports are enumerated in section 3. Optional imports are in section 6. The missing `ocr_service` module and its two possible editable distributions are manual-verification items. No reachable source imports the standalone evaluation, benchmark, test, training-program, notebook, or migration modules.

# Appendix B — Existing Lock Classification

This classification covers all 466 non-comment records in `requirements.lock.txt`. Names are shown without versions for readability; the source lock was not changed.

## KEEP — 21

`bcrypt`, `fastapi`, `httpx`, `Jinja2`, `langchain-classic`, `langgraph`, `minio`, `numpy`, `openai`, `pandas`, `parsivar`, `psycopg2-binary`, `pydantic`, `python-dotenv`, `python-multipart`, `qdrant-client`, `rank-bm25`, `torch`, `tqdm`, `transformers`, `uvicorn`.

## OPTIONAL_PRODUCTION_FEATURE — 2

`openpyxl`, `python-magic`.

## MANUAL_VERIFICATION — 2

Editable `dots_ocr` (`/home/hooman/PycharmProjects/RegAssist/new_architecture/dots.ocr`) and editable `dotsocr` (`/home/hooman/PycharmProjects/RegAssist/new_architecture/dotsocr`).

## TRANSITIVE — 79

`annotated-doc`, `annotated-types`, `anyio`, `argon2-cffi`, `argon2-cffi-bindings`, `certifi`, `cffi`, `charset-normalizer`, `click`, `distro`, `et_xmlfile`, `filelock`, `fsspec`, `greenlet`, `grpcio`, `h11`, `hf-xet`, `httpcore`, `huggingface_hub`, `idna`, `jiter`, `joblib`, `jsonpatch`, `jsonpointer`, `langchain-core`, `langchain-text-splitters`, `langgraph-checkpoint`, `langgraph-prebuilt`, `langgraph-sdk`, `langsmith`, `MarkupSafe`, `mpmath`, `networkx`, `nltk`, `nvidia-cublas`, `nvidia-cuda-cupti`, `nvidia-cuda-nvrtc`, `nvidia-cuda-runtime`, `nvidia-cudnn-cu13`, `nvidia-cufft`, `nvidia-cufile`, `nvidia-curand`, `nvidia-cusolver`, `nvidia-cusparse`, `nvidia-cusparselt-cu13`, `nvidia-nccl-cu13`, `nvidia-nvjitlink`, `nvidia-nvshmem-cu13`, `nvidia-nvtx`, `orjson`, `ormsgpack`, `packaging`, `portalocker`, `protobuf`, `pycparser`, `pycryptodome`, `pydantic_core`, `python-dateutil`, `pytz`, `PyYAML`, `regex`, `requests`, `requests-toolbelt`, `safetensors`, `six`, `sniffio`, `SQLAlchemy`, `starlette`, `sympy`, `tenacity`, `tokenizers`, `triton`, `typing-inspection`, `typing_extensions`, `tzdata`, `urllib3`, `uuid_utils`, `xxhash`, `zstandard`.

These may be installed by their direct owners. Their presence in this section is not an instruction to remove them from an installed environment manually.

## REMOVE_FROM_RAGBOT_RUNTIME — 362

`absl-py`, `accelerate`, `addict`, `aiofile`, `aiofiles`, `aiohappyeyeballs`, `aiohttp`, `aiosignal`, `aiosqlite`, `airportsdata`, `alembic`, `altair`, `anthropic`, `anywidget`, `apache-tvm-ffi`, `arabic-reshaper`, `array_record`, `astor`, `asttokens`, `astunparse`, `async-generator`, `asyncpg`, `attrs`, `Authlib`, `av`, `beartype`, `beautifulsoup4`, `bitsandbytes`, `blake3`, `blinker`, `blis`, `blobfile`, `boto3`, `botocore`, `brotli`, `build`, `cachetools`, `caio`, `cairocffi`, `CairoSVG`, `catalogue`, `cbor2`, `chex`, `cloud-sql-python-connector`, `cloudpathlib`, `cloudpickle`, `clu`, `comm`, `compressed-tensors`, `confection`, `contourpy`, `cryptography`, `cssselect2`, `cuda-bindings`, `cuda-pathfinder`, `cuda-python`, `cupy-cuda12x`, `cycler`, `cyclopts`, `cymem`, `dataclasses-json`, `datasets`, `decorator`, `decord2`, `defusedxml`, `depyf`, `dialog`, `dill`, `diskcache`, `dm-tree`, `dnspython`, `docker`, `docstring_parser`, `docutils`, `durationpy`, `einops`, `email-validator`, `etils`, `exceptiongroup`, `executing`, `faiss-cpu`, `fastapi-cli`, `fastapi-cloud-cli`, `fastar`, `fastmcp`, `fastrlock`, `ffmpy`, `filetype`, `Fingilish`, `finglish`, `flash_attn`, `flashinfer-cubin`, `flashinfer-python`, `flatbuffers`, `flax`, `fonttools`, `frozenlist`, `gast`, `gemma`, `gguf`, `gitdb`, `GitPython`, `google`, `google-api-core`, `google-api-python-client`, `google-auth`, `google-auth-httplib2`, `google-cloud-aiplatform`, `google-cloud-bigquery`, `google-cloud-core`, `google-cloud-resource-manager`, `google-cloud-storage`, `google-crc32c`, `google-genai`, `google-pasta`, `google-resumable-media`, `googleapis-common-protos`, `gradio`, `gradio_client`, `gradio_image_annotation`, `grain`, `graphviz`, `griffelib`, `groovy`, `grpc-google-iam-v1`, `grpcio-health-checking`, `grpcio-reflection`, `grpcio-status`, `grpcio-tools`, `h2`, `h5py`, `hf_transfer`, `hpack`, `httplib2`, `httptools`, `httpx-sse`, `humanize`, `hyperframe`, `ijson`, `ImageIO`, `immutabledict`, `importlib_metadata`, `interegular`, `ipython`, `ipython_pygments_lexers`, `ipywidgets`, `jaraco.classes`, `jaraco.context`, `jaraco.functools`, `jax`, `jaxlib`, `jaxtyping`, `jedi`, `jeepney`, `jmespath`, `joserfc`, `jsonref`, `jsonschema`, `jsonschema-path`, `jsonschema-specifications`, `jupyterlab_widgets`, `kauldron`, `keras`, `keyring`, `kiwisolver`, `kubernetes`, `langchain`, `langchain-community`, `langchain-protocol`, `langgraph-checkpoint-postgres`, `langgraph-checkpoint-sqlite`, `lark`, `lazy-loader`, `libclang`, `llama_cpp_python`, `llguidance`, `llvmlite`, `lm-format-enforcer`, `loguru`, `lxml`, `Mako`, `Markdown`, `markdown-it-py`, `marshmallow`, `matplotlib`, `matplotlib-inline`, `mcp`, `mdurl`, `mediapy`, `ml_collections`, `ml_dtypes`, `model-hosting-container-standards`, `modelscope`, `more-itertools`, `msgpack`, `msgspec`, `multidict`, `multiprocess`, `murmurhash`, `mypy_extensions`, `namex`, `narwhals`, `natsort`, `nest-asyncio`, `ninja`, `numba`, `nvidia-cudnn-frontend`, `nvidia-cutlass-dsl`, `nvidia-cutlass-dsl-libs-base`, `nvidia-ml-py`, `oauthlib`, `openai-harmony`, `openapi-pydantic`, `opencv-python`, `opencv-python-headless`, `opentelemetry-api`, `opt_einsum`, `optax`, `optree`, `orbax-checkpoint`, `outlines`, `outlines_core`, `parso`, `partial-json-parser`, `pathable`, `pdf2image`, `pexpect`, `pillow`, `pip`, `platformdirs`, `plotly`, `preshed`, `prometheus-fastapi-instrumentator`, `prometheus_client`, `promise`, `prompt_toolkit`, `propcache`, `proto-plus`, `psutil`, `psycopg`, `psycopg-binary`, `psycopg-pool`, `psygnal`, `ptyprocess`, `pure_eval`, `py-cpuinfo`, `py-key-value-aio`, `py-spy`, `pyarrow`, `pyasn1`, `pyasn1_modules`, `pybase64`, `pycountry`, `pycryptodomex`, `pydantic-extra-types`, `pydantic-settings`, `pydeck`, `pydub`, `Pygments`, `PyJWT`, `PyMuPDF`, `pyparsing`, `pyperclip`, `pyphen`, `pyproject_hooks`, `pyspellchecker`, `python-bidi`, `python-editor`, `python-json-logger`, `pyzmq`, `qwen-vl-utils`, `RapidFuzz`, `ray`, `redis`, `referencing`, `requests-oauthlib`, `rich`, `rich-rst`, `rich-toolkit`, `rignore`, `rpds-py`, `rsa`, `s3transfer`, `safehttpx`, `scikit-image`, `scikit-learn`, `scipy`, `SecretStorage`, `semantic-version`, `sentence-transformers`, `sentencepiece`, `sentry-sdk`, `setproctitle`, `setuptools`, `sgl-kernel`, `shellingham`, `simple-parsing`, `simplejson`, `smart_open`, `smmap`, `soundfile`, `soupsieve`, `spacy`, `spacy-legacy`, `spacy-loggers`, `sqlite-vec`, `sqlparse`, `srsly`, `sse-starlette`, `stack-data`, `streamlit`, `structlog`, `supervisor`, `tabulate`, `tensorboard`, `tensorboard-data-server`, `tensorflow`, `tensorflow-datasets`, `tensorflow-metadata`, `tensorstore`, `termcolor`, `textstat`, `thinc`, `threadpoolctl`, `tifffile`, `tiktoken`, `timm`, `tinycss2`, `toml`, `tomlkit`, `toolz`, `torchaudio`, `torchvision`, `tornado`, `traitlets`, `treescope`, `typeguard`, `typer`, `typer-slim`, `typing-inspect`, `uncalled-for`, `uritemplate`, `uv`, `uvloop`, `vllm`, `wadler_lindig`, `wasabi`, `watchdog`, `watchfiles`, `wcwidth`, `weasel`, `webencodings`, `websocket-client`, `websockets`, `Werkzeug`, `wheel`, `widgetsnbextension`, `wrapt`, `xgrammar`, `xmanager`, `yarl`, `zipp`.

The alternate root snapshot `requirements_sep_8_2026.txt` adds packages such as Celery/AMQP/Kombu/Vine, pytest/coverage, Ruff/Mypy, and an editable Git application package. They remain outside the RagBot production boundary for the same reasons and are not candidate requirements.
