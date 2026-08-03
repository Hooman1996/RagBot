# README source map

This maintainer map ties important root README claims to repository evidence.
It deliberately excludes environment values, credentials, customer data, and
benchmark request bodies. Line numbers refer to the source revision audited
when the README was written and may drift as code changes.

| README claim | Source |
|---|---|
| FastAPI application title/version and lifespan | `main.py:455-459` |
| Application mounts web, mobile, and knowledge-base routes | `main.py:461-468` |
| Mobile talk route and request/response schema | `mobile_api.py:26-39`, `mobile_api.py:81-101` |
| Mobile route has no FastAPI auth dependency | `mobile_api.py:77-82` |
| Mobile total deadline includes admission | `mobile_api.py:81-101` |
| Web query route and schema | `main.py:132-138`, `main.py:589-606` |
| Web query shared answer path and response | `main.py:609-680` |
| Per-process request and blocking limiters | `main.py:80-87`, `main.py:215-216` |
| Limiter overload behavior | `utils/concurrency.py:99-117`; `utils/service_errors.py:28-30` |
| Shared web/mobile/batch answering semantics | `answering_service.py:1-20`, `answering_service.py:55-153` |
| Normalization, classification, and rewrite order | `answering_service.py:62-107` |
| History rewrite uses up to three turns | `answering_service.py:91-107`; `new_architecture/app/services/history/rewriting.py:81-142` |
| Query rewrite uses the vLLM-backed RAG client | `new_architecture/app/services/history/rewriting.py:244-251`; `utils/RagSystem.py:370-378` |
| LangGraph state and registered nodes | `agent_graph.py:23-42`, `agent_graph.py:313-362` |
| Active intent routes are general and chit-chat | `intent_classifier.py:202-237`; `agent_graph.py:338-347` |
| Agent state persists in PostgreSQL session metadata | `agent_service.py:1-5`, `agent_service.py:112-116`, `agent_service.py:194-204` |
| Per-session turns are serialized | `agent_service.py:43-44`, `agent_service.py:64-82` |
| Stateless batch graph path | `agent_service.py:207-247` |
| Hybrid retrieval uses PostgreSQL chunks, BM25, TEI, and Qdrant | `utils/persian_hybrid_search.py:211-215`, `utils/persian_hybrid_search.py:395-457`, `utils/persian_hybrid_search.py:492-549` |
| Hybrid fusion is reciprocal-rank fusion | `utils/persian_hybrid_search.py:524-539` |
| Retrieval defaults: top 10 and 50 semantic candidates | `utils/performance_config.py:151-158` |
| Query embedding calls TEI `/embed` | `utils/tei_embedding_client.py:104-120` |
| Query embedding uses `prompt_name="query"` | `utils/tei_embedding_client.py:14-26` |
| Stored-document embedding has no prompt name | `utils/tei_embedding_client.py:29-41`, `utils/tei_embedding_client.py:122-144` |
| Active vector dimension is 1,024 | `utils/tei_embedding_client.py:14`, `main.py:67` |
| Qdrant collection uses cosine distance | `new_architecture/app/services/db_connection/connection.py:92-103` |
| FAQ related questions—not main context—are reranked | `agent_graph.py:119-185` |
| Reranker calls TEI `/rerank` | `utils/persian_hybrid_search.py:560-620` |
| vLLM uses an OpenAI-compatible persistent client | `main.py:268-302`; `utils/RagSystem.py:182-191` |
| Application sends served model name `/app/model` | `utils/RagSystem.py:44-52`, `utils/RagSystem.py:360-378` |
| Underlying vLLM model is not controlled by `LLM_MODEL` | `docs/configuration/ENVIRONMENT_VARIABLES.md:352-410`; `docs/configuration/RTX5880_MODEL_SERVER_BASELINE.md:201-270` |
| Jina TEI model identifier and server settings | `docs/configuration/RTX5880_MODEL_SERVER_BASELINE.md:43-72` |
| BGE reranker identifier and server settings | `docs/configuration/RTX5880_MODEL_SERVER_BASELINE.md:43-72` |
| Intent MLP architecture and labels | `intent_classifier.py:37-79` |
| Intent artifact path and safe load | `intent_classifier.py:109-173` |
| Intent runtime uses the TEI embedding callable | `main.py:330-336`; `intent_classifier.py:186-196` |
| No classifier training script exists | Repository file audit; `intent_classifier.py:10`, `intent_classifier.py:34-45` reference absent `chitchat_guardrail.py` |
| MinIO is initialized and bucket existence is checked | `new_architecture/app/services/db_connection/connection.py:57-76` |
| MinIO/PostgreSQL/Qdrant insertion roles | `new_architecture/insert_data.py:1358-1405` |
| Mass-answer accepted file types and query aliases | `mass_answer_files.py:16-27`, `mass_answer_files.py:69-97`, `mass_answer_files.py:151-179` |
| Mass-answer output columns and spreadsheet hardening | `mass_answer_files.py:18-28`, `mass_answer_files.py:182-212` |
| Direct/job mode threshold | `main.py:1004-1028`; `utils/performance_config.py:169-184` |
| Bounded mass-answer workers and per-row deadline | `mass_answer_service.py:48-64`, `mass_answer_service.py:66-170`, `mass_answer_service.py:172-236` |
| Batch rows are stateless/no-history | `mass_answer_service.py:190-202`; `agent_service.py:207-247` |
| Mass-answer output fields | `main.py:1117-1149` |
| Job creation response and URLs | `main.py:1154-1214` |
| Job progress schema and timing fields | `main.py:1303-1344` |
| Job poll/download/delete/cleanup routes | `main.py:1357-1420` |
| Job process-restart durability limitation | `mass_answer_jobs.py:9-60`; `docs/architecture/MASS_ANSWER.md:70-82` |
| Application health route | `main.py:1724-1731` |
| Direct application startup command | `main.py:1734-1738` |
| No repo-owned service/container definitions | `docs/configuration/ENVIRONMENT_QUICK_START.md:137-145`; repository file audit |
| No canonical Python dependency installation command | `docs/performance/17-mass-answer-repair-report.md:42-46`; repository file audit |
| Environment variable groups and status | `docs/configuration/ENVIRONMENT_VARIABLES.md` |
| Environment changes require restart | `docs/configuration/ENVIRONMENT_QUICK_START.md:194-216` |
| Environment validator does not reveal values | `scripts/validate_environment.py:1-8` |
| Staging hardware and production hardware differ | `AGENTS.md:5-10` |
| Accepted benchmark: 250/250, five waves, concurrency 50 | `docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md:9-21`; `benchmarks/results/mobile-talk/rtx5880_request50_pool64_c50_20260729T125100Z/report.md` |
| Accepted benchmark p50/p95/p99/max/throughput | `benchmarks/results/mobile-talk/rtx5880_request50_pool64_c50_20260729T125100Z/report.md:21-51` |
| Zero limiter rejections, timeouts, and HTTP 5xx | `benchmarks/results/mobile-talk/rtx5880_request50_pool64_c50_20260729T125100Z/report.md:45-58` |
| Winning application configuration | `docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md:23-63` |
| Fixed vLLM and TEI benchmark configuration | `docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md:39-63` |
| Synthetic benchmark traffic and answer-quality limitation | `docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md:102-104`, `docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md:160-175` |
| RTX 5880 result does not transfer automatically to dual L4 | `docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md:22-24`, `docs/configuration/RTX5880_FINAL_RECOMMENDATIONS.md:233-234` |
| Load runner modes, no retries, and persistent client | `benchmarks/load/mobile_talk_load_test.py:1-7`; `benchmarks/load/README.md:1-8` |
| Load artifact content warning | `benchmarks/load/mobile_talk_load_test.py:61-108`; `benchmarks/load/README.md:44-50` |
| Load CLI options | `benchmarks/load/mobile_talk_load_test.py:1758-1815` |
| Unit-test command and missing pytest note | `docs/performance/17-mass-answer-repair-report.md:42-75`; `docs/performance/09-tei-embedding-policy-implementation.md:176-213` |
| No project-level license/CI/contributing/security files | Repository file audit; bundled UI licenses exist only at `qdrant-web-ui-master/LICENSE` and `static_qdrant/LICENSE` |
