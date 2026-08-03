# Mass-answer pipeline audit

Audit baseline: commit `30385f23b0511a395bc25e0046d471d5461db1f4` (2026-07-30).  
Audit date: 2026-08-01.  
Scope: `POST /api/mass-answer`, `POST /api/query`, `POST /api/mobile/v1/talk`, and their shared retrieval, generation, persistence, timeout, and client paths.  
External interactive deadline: 50 seconds (`AGENTS.md:7`; `utils/performance_config.py:83-87`).

This phase was static and read-only. No endpoint was invoked, no staging service was changed, and no customer fixture was used. The deployed reverse proxy, worker count, service versions, current model revisions, and live staging identity remain **unknown** because repository-owned deployment definitions are absent. The repository documents staging as one RTX 5880 Ada 48 GB GPU and production as two separate L4 24 GB GPUs (`AGENTS.md:7-14`); this audit does not extrapolate capacity between them.

## Executive finding

The immediate timeout defect is exact: `process_mass_answer` puts the **whole file operation** inside `asyncio.wait_for(..., REQUEST_TIMEOUT_SECONDS)` (`main.py:974-990`) and admits that whole operation through the same interactive request semaphore (`main.py:992-996`). `_process_mass_answer` then loops over rows sequentially (`main.py:1050-1095`). A batch therefore receives one 50-second budget, not one budget per row, and occupies one interactive limiter slot until parsing, every model call, output generation, and response construction finish.

The batch path is also not behaviorally equivalent to online answering. It manually performs normalize → no-op rewrite → retrieve → context → answer (`main.py:1050-1090`) and never calls the intent classifier, `AgentService.process_message`, or LangGraph. It consequently cannot use the online chit-chat route and omits graph-produced related questions and feedback state. This is an accidental semantic divergence and a correctness defect.

Pandas parsing and output generation are already submitted to the bounded blocking runner (`main.py:1034-1043`, `1098-1109`), so those calls do not execute on the event-loop thread. The upload is nevertheless fully buffered in memory before parsing (`main.py:1034`), and no upload-size or row-count limit exists.

## Current request trace

| Order | Caller | Operation | Evidence | Mode/resource | Timeout/retry | Finding |
|---:|---|---|---|---|---|---|
| 1 | FastAPI | Parse multipart upload and form | `main.py:974-979` | Starlette `UploadFile` | Upstream unknown | MIME is not checked. |
| 2 | `process_mass_answer` | Acquire shared request admission | `main.py:992-996`; `utils/concurrency.py:99-117` | Async semaphore | Configured admission timeout; no retry | One slot covers the full batch. |
| 3 | `process_mass_answer.operation` | Apply total batch deadline | `main.py:980-990` | `asyncio.wait_for` | 50 s maximum | Incorrect scope: whole file. |
| 4 | `_process_mass_answer` | Parse selected documents | `main.py:1008-1027` | Event-loop JSON/list work | Invalid JSON becomes empty list | At least one document is required. |
| 5 | `_process_mass_answer` | Validate extension, read upload | `main.py:1029-1034` | Async file read into one `bytes` object | None | Full upload buffered; no size limit. |
| 6 | `_process_mass_answer` | Parse CSV/Excel | `main.py:1035-1045` | Bounded worker; pandas | Parser defaults | Full DataFrame materialized. |
| 7 | `_process_mass_answer` | Infer question column | `main.py:1047` | In-process | None | Substring match or silently first column; no required-column validation. |
| 8 | Per row | Normalize | `main.py:1050-1054` | Bounded worker; Parsivar | None | `NaN` becomes text `"nan"`. |
| 9 | Per row | Rewrite with no-history sentinel | `main.py:1060-1064`; `new_architecture/app/services/history/rewriting.py:244-251` | Async | vLLM only if history is not sentinel | Current call returns original query without a model request. |
| 10 | Per row | Hybrid retrieve | `main.py:1066-1070`; `utils/RagSystem.py:159-166` | Async shared service | Dependency timeouts; no retry | Same top-k setting but manual route. |
| 11 | Retrieval | Fetch chunks/BM25, embed, Qdrant | `utils/persian_hybrid_search.py:492-549` | Bounded PostgreSQL/CPU, async TEI, bounded sync Qdrant | TEI/Qdrant/DB limits | Shared clients are reused. |
| 12 | Per row | Construct context | `main.py:1072-1078` | Bounded worker for FAQ | None | Mirrors only part of graph behavior. |
| 13 | Per row | Generate and clean answer | `main.py:1080-1094`; `utils/RagSystem.py:251-367` | Async shared vLLM client | HTTP phase timeouts; no retry | Per-row exceptions become answer text. |
| 14 | Batch | Add answer column | `main.py:1096` | DataFrame mutation | None | Only one result field. |
| 15 | Batch | Create and write output | `main.py:1098-1109` | Bounded worker | None | CSV uses UTF-8 BOM. |
| 16 | Batch | Register deletion and return file | `main.py:1111-1118` | `BackgroundTasks` + `FileResponse` | Client/proxy unknown | Cleanup depends on response lifecycle. |

## Sync/async boundaries

| Boundary | Evidence | Event-loop status | Risk |
|---|---|---|---|
| Upload read | `main.py:1034` | Awaited, but result is fully buffered | Memory exhaustion; no byte limit. |
| pandas parsing | `main.py:1037-1043` | Bounded worker | Event loop is safe; worker/memory remain bounded only by global worker slots and file size. |
| Persian normalization | `main.py:1052-1054` | Bounded worker | Event loop is safe; one worker submission per row. |
| PostgreSQL/BM25 | `utils/persian_hybrid_search.py:500-510`; `new_architecture/app/services/history/database.py:44-79` | Bounded worker | Per-operation psycopg2 connections; no connection held across vLLM waits. |
| TEI embed | `utils/persian_hybrid_search.py:296-305`; `utils/tei_embedding_client.py:1-132` | Async shared HTTP client | Pool/service queue timing is not instrumented. |
| Qdrant query | `utils/persian_hybrid_search.py:427-457` | Bounded worker plus Qdrant semaphore | Sync client is process-shared and serialized by its wrapper. |
| TEI related-question rerank | `agent_graph.py:168-175`; `utils/persian_hybrid_search.py:560-620` | Async shared HTTP client | Online FAQ only; mass path omits it. |
| vLLM | `utils/RagSystem.py:182-191`, `251-367` | Async shared OpenAI/httpx client | Pool/queue/prefill/decode are not separately observed. |
| pandas output | `main.py:1098-1109` | Bounded worker; cancellation waits for write completion | Event loop is safe; cancellation can wait for a long write. |
| File deletion | `main.py:1111-1112` | Starlette background task | No persistent retention/expiry recovery. |

`BoundedBlockingRunner` uses a semaphore and `asyncio.to_thread` (`utils/concurrency.py:15-89`). Cancellation cannot stop an already-running thread; transactional/file writes may wait for completion. `run_with_limit` has bounded admission and always releases the semaphore (`utils/concurrency.py:99-117`).

## Answers to the required audit questions

1. **Accepted formats:** extension-only validation accepts `.csv`, `.xlsx`, and `.xls` (`main.py:1029-1032`). The response claims generic CSV/Excel. `.xls` output depends on a pandas Excel writer that is not declared or verified, so practical legacy Excel support is unknown and unreliable.
2. **Required columns:** no named column is actually required. The first header containing Persian `سوال` or case-insensitive English `question` is used; otherwise the first column is silently selected (`main.py:1047`). A zero-column file fails with an uncaught index error. Semantically, the request also requires at least one selected document (`main.py:1021-1025`).
3. **Optional columns:** every other input column is opaque and preserved. No optional session, national-code, history, conversation-group, or per-row document column is recognized.
4. **Column normalization:** none. Matching uses raw column objects and substring tests (`main.py:1047`); whitespace, Arabic/Persian character variants, and Unicode normalization are not handled. Two source columns can match, and the first wins silently.
5. **Empty rows:** rows are not removed. A missing pandas cell normally becomes `NaN`; `str(q).strip()` becomes `"nan"`, so it is treated as a real question (`main.py:1050-1058`). A literal empty string that survives parsing receives `Empty question context row` in the answer column.
6. **Duplicates:** no deduplication occurs. Duplicate rows are processed independently in original order (`main.py:1050-1095`). Duplicate headers are left to pandas' parser behavior rather than explicitly rejected.
7. **Encoding detection:** none. `pd.read_csv` is called without `encoding`, detector, fallback, or delimiter configuration (`main.py:1036-1039`).
8. **Persian CSV:** UTF-8 Persian input works under pandas' default UTF-8 behavior; UTF-8 BOM is normally consumed by pandas. Other common Persian encodings are not detected. Output explicitly uses `utf-8-sig`, which is appropriate for common spreadsheet programs (`main.py:1101-1103`).
9. **Memory:** yes. `await file.read()` creates the complete bytes value and pandas materializes the complete DataFrame (`main.py:1034-1043`).
10. **Row scheduling:** strictly sequential (`main.py:1050-1095`).
11. **Unbounded concurrency:** no row concurrency exists, so there is no unbounded `gather`; throughput is instead unnecessarily serialized.
12. **Pandas on event loop:** no for the actual parse/write calls; both use `blocking_runner.run` (`main.py:1037-1043`, `1107-1109`). Full-byte buffering and ordinary DataFrame indexing/mutation still occur in the async function.
13. **One whole-batch `wait_for`:** yes (`main.py:980-985`).
14. **Separate row timeout:** no.
15. **Interactive limiter wraps full batch:** yes (`main.py:992-996`). It is the same process-level limiter installed at startup (`main.py:202-203`, `341`).
16. **Same pipeline as online:** no. Web and mobile classify, conditionally load/rewrite history, persist messages, then call `AgentService.process_message`/LangGraph (`main.py:572-649`; `mobile_api.py:128-201`). Mass manually calls RAG and omits classification/graph routing (`main.py:1050-1094`).
17. **Client reuse:** yes. Lifespan constructs process-scoped TEI, vLLM, Qdrant, RAG, classifier, and agent objects (`main.py:234-342`) and closes them at shutdown (`main.py:344-399`). Rows do not construct clients.
18. **Session IDs per row:** none. The mass request accepts no session field and calls no session API.
19. **History sharing:** history is intentionally absent: each row passes the no-history sentinel to rewriting and empty history to generation (`main.py:1061-1064`, `1083-1088`). There is no conversation grouping.
20. **Output order:** yes under current sequential execution. `answers.append` aligns positionally with DataFrame iteration (`main.py:1048-1096`).
21. **One-row failure:** most per-row exceptions are caught and written as `ERROR: <exception>` in the answer column (`main.py:1093-1094`). Normalize failures occur outside that `try` and can fail the whole batch (`main.py:1052-1060`). `CancelledError`/whole-batch timeout also terminates the batch.
22. **Partial results:** retained only in memory during a normally completing batch. A whole-batch timeout, disconnect, process crash, or pre-output exception loses them; no job record or checkpoint exists.
23. **Temporary cleanup:** successful response construction registers `os.remove(path)` as a response background task (`main.py:1098-1114`). There is no job retention sweeper. A failure after file creation but before background-task registration can leak the file; process death can also leave it.
24. **Disconnect/cancellation:** there is no detached durable job. Cancellation can abort awaited row work and prevent output creation; already-running blocking work follows `BoundedBlockingRunner` cancellation semantics (`utils/concurrency.py:18-22`, `71-89`). Thus a disconnect can terminate the only in-memory batch, although whether a particular ASGI server cancels the handler on disconnect is deployment-dependent and unverified.
25. **Progress/status/error fields:** no. The synchronous response exposes no progress. Output adds only `Answer (پاسخ)` (`main.py:1096`); failures are mixed into that field, with no stable status, error code, sanitized error field, row timing, intent, or rewritten-query field.

## Input/output correctness and security findings

- Extension is the sole file-type gate; MIME and magic/content validation are absent (`main.py:1029-1045`).
- There is no file-size, row-count, or direct-mode threshold.
- Empty, header-only, malformed, and duplicate-header files do not receive deliberate stable validation errors.
- CSV delimiter/sniffing is not configured. Quoted commas and multiline values work when the file uses pandas' default CSV dialect; semicolon/tab promises do not exist.
- `read_excel` uses pandas' default first sheet; sheet selection is not exposed (`main.py:1040-1043`).
- Numeric query cells are converted with `str`, but missing values are incorrectly converted to `"nan"` (`main.py:1050-1054`).
- Original columns and row order are preserved on normal completion (`main.py:1096-1104`).
- CSV output uses a BOM; Excel output does not escape input cells beginning with `=`, `+`, `-`, or `@`, so spreadsheet formula injection is possible.
- Raw exception text is returned inside the spreadsheet (`main.py:1093-1094`), which can leak internal dependency details. Tracebacks are not explicitly placed there, but exception messages are unsanitized.
- The filename is passed to `FileResponse` as a download name (`main.py:1114-1117`); Starlette handles header construction, but output naming/extension fidelity has no dedicated test.

## Resource and persistence findings

- Batch rows create no users, sessions, query records, chat messages, tickets, or metadata. This avoids polluting chat history but is an undocumented behavior difference.
- Web/mobile call `AgentService`, which reads session/user and agent metadata, invokes LangGraph, and writes metadata (`agent_service.py:70-169`). Wrappers also write the user and assistant message (`main.py:589-621`; `mobile_api.py:142-177`).
- `DatabaseManager` opens and closes a new psycopg2 connection per operation (`new_architecture/app/services/history/database.py:44-79`); the SQLAlchemy pool elsewhere in the repository is not proven to serve these paths.
- No DB connection or lock is held while awaiting vLLM: each database operation closes before control returns.
- TEI and vLLM HTTP clients are shared for the lifespan (`main.py:234-299`). TEI limits default to 32 connections/16 keep-alive and vLLM to 32/16 (`utils/performance_config.py:97-143`); mass concurrency must be smaller and separately bounded.
- Qdrant sync calls are offloaded and limited by `QDRANT_CONCURRENCY`, default 4 (`utils/persian_hybrid_search.py:280-282`, `427-457`).
- MinIO is initialized at application startup but is not on the mass/web/mobile answer critical path.

## Timeout and deployment conclusion

The repository has no Docker, Compose, Nginx, Caddy, gateway, or other owned proxy definition. Therefore proxy request/body/download timeouts and client-disconnect behavior are **unknown**. The browser uses one ordinary `fetch` and waits for a blob (`templates/index.html:272-313`), providing neither progress nor recovery. A synchronous response is consequently unsuitable for large batches even after removing the erroneous 50-second wrapper.

Recommended architecture for repair:

- Keep a compatibility direct-download mode only for a small, validated row threshold.
- Add a persistent PostgreSQL job record and explicit create/status/result/delete endpoints for larger files.
- Do not claim restart recovery unless queued/running work is actually rediscovered and resumed; persisted status/artifacts alone are not a worker queue.
- Run rows through a shared answer service with `use_history=false` and `persist_messages=false` for independent FAQ rows.
- Use a fixed-size worker pool/queue (default 4), not one task per row and not unbounded `asyncio.gather`.
- Apply the 50-second-compatible timeout to each row, not the file.
- Offload parsing and serialization through the existing bounded blocking runner and enforce upload/row limits before expensive work.

No benchmark was run in this phase. Baseline mass throughput, GPU contention, proxy survival, and mixed-workload impact are therefore **unknown**.
