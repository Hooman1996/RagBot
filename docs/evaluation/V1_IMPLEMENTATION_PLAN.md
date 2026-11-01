# RagBot Evaluation System V1 - implementation plan

Audit date: 2026-08-31  
Repository: `/root/projects/faq`  
Pass type: audit and design only

## Audit outcome

V1 can be implemented without duplicating the production RAG pipeline. The existing `AnsweringService` is already the closest thing to a shared pipeline executor. It must remain the single executor and gain two narrow, per-execution dependencies:

1. an injectable conversation history/state provider; and
2. an optional, evaluation-only pipeline observer whose production default is a no-op.

Evaluation must call `AnsweringService` directly. It must never call `POST /api/mobile/v1/talk`, construct a mobile request, resolve a mobile session, provision a production user, or call production chat-message persistence.

Important conflicts found in the current code:

- The production conversation is stored twice for different purposes. `queries` is the transaction/message ledger, while `chat_sessions.meta_data.agent_state` is the history and LangGraph checkpoint actually consumed by rewriting and the graph.
- Query rewriting and graph execution independently reload `agent_state`; a history seam that only returns message rows is insufficient.
- Primary retrieved chunks are not reranked. TEI reranking currently applies only to the five related-question candidates for FAQ documents. V1 must record primary `RERANK` as `SKIPPED`, not introduce a new primary rerank.
- There are currently three distinct history rules: rewrite history, final-answer prompt history, and persisted-state trimming. They must be extracted without changing their byte-for-byte behavior and then shared by both providers.
- The chitchat prompt in `utils/RagSystem.py` currently contains no interpolation placeholders. Consequently the `format(...)` call does not include the current query or recent history. This is current behavior and must be characterized and preserved in V1 unless a separate, quality-tested product change is approved.
- `RAG_RELATED_QUESTIONS_RERANK_THRESHOLD` is active and defaults to `0.1`; `MOBILE_RELATED_QUESTIONS_RERANK_THRESHOLD` defaults to `0.5` but is not used by the verified mobile path.
- The repository has an in-process `MassAnswerJobManager`, but it is not durable across API restarts or multiple API workers. It is not a suitable evaluation job mechanism.
- Redis client code and the `redis` Python package exist, but Redis is not on the verified application runtime path. Celery is not present in `requirements.lock.txt`.
- The existing application login is process-global state, not a reusable request authentication boundary. The evaluation API must have its own explicit administrator authentication dependency.
- The existing Alembic environment has stale/nonexistent imports and targets application objects. It must not be reused for evaluation migrations.
- `requirements.lock.txt` now exists even though `AGENTS.md` says no requirements file was found. It is a full environment snapshot with local file references, not a proven portable/canonical installation manifest.

No application code, services, database objects, production records, Qdrant data, MinIO data, prompts, thresholds, model configuration, or environment files were changed during this audit.

## 1. Exact `/v1/talk` execution path

The real route is `POST /api/mobile/v1/talk`, registered under the `/api/mobile` router prefix.

1. `mobile_api.py:83-107`, `gateway_talk`:
   - creates the `operation` wrapper and `pipeline` timing span;
   - enters the process-local request admission limiter through `run_with_limit`;
   - wraps the whole admitted operation in `asyncio.wait_for` using `APPLICATION_REQUEST_TIMEOUT_SECONDS`, validated not to exceed 50 seconds;
   - translates an overall timeout to `ServiceTimeoutError`.
2. `mobile_api.py:109-127`, `_gateway_talk`:
   - validates non-empty `query`, `session_id`, and `national_code`;
   - obtains services from `request.app.state`;
   - calls `chat_manager.db.get_or_create_user_by_national_code` in the bounded blocking runner. This can write a row to production `users`.
3. `mobile_api.py:130-152`:
   - calls `chat_manager.resolve_mobile_session(user_id, req.session_id)`;
   - `ChatManager.resolve_mobile_session` calls `DatabaseManager.get_or_create_mobile_session`, resolving or creating a production `chat_sessions` row;
   - calls `chat_manager.add_message(..., role="user")`, which inserts a pending production `queries` row and increments the production session query count.
4. `mobile_api.py:154-165`:
   - invokes `request.app.state.answering_service.answer(...)` with:
     - `original_query=req.query`;
     - the resolved internal production session integer converted to string;
     - selected documents from `req.documents`;
     - `channel="mobile"`;
     - history enabled;
     - agent-state persistence enabled;
     - related questions enabled.
5. `answering_service.py:70-103`:
   - strips the raw query;
   - calls `PersianTextProcessor.normalize` through `BoundedBlockingRunner`;
   - calls `normalize_persian_text`;
   - calls `IntentClassifier.classify(normalized_query)` exactly once.
6. `answering_service.py:106-127`, for non-chitchat:
   - calls `HistoryRewritingService.get_formatted_history_string(session_id, max_turns=3)` in a blocking worker;
   - calls `HistoryRewritingService.rewrite_query(normalized_query, formatted_history)`;
   - normalizes the returned rewrite again with `normalize_persian_text`.
7. `answering_service.py:138-160`:
   - validates selected document names through `DatabaseManager.filter_available_document_titles`;
   - rejects a `general` request with no current datasource;
   - resolves the prompt category using `main.get_document_category`.
8. `answering_service.py:161-183`:
   - calls `AgentService.process_message_detailed`, passing the raw stripped query, rewritten retrieval query, preclassified intent, selected documents, and category.
9. `agent_service.py:65-210`:
   - takes a process-local lock keyed by internal production session ID;
   - loads the production session row and its `user_id`;
   - loads `chat_sessions.meta_data.agent_state` or builds fresh state;
   - cancels a pending satisfaction prompt;
   - sets the current raw user message, rewritten retrieval query, documents, category, and preclassified intent;
   - invokes the compiled LangGraph;
   - optionally creates a production support ticket if graph state requests it;
   - trims state messages to the last 10;
   - overwrites `chat_sessions.meta_data.agent_state`.
10. `agent_graph.py:360-410`, graph path:
    - `add_user_message` appends the raw query and trims to 10 messages;
    - `classify_intent` consumes the preclassified result, so the normal path does not classify twice;
    - `general` and currently any `personal` label route to `handle_general`;
    - `chitchat` routes to `handle_chitchat`;
    - the selected handler sets an answer;
    - `add_assistant_message` appends it and trims to 10 messages.
11. `agent_graph.py:127-238`, general RAG path:
    - calls `RAGSystem.retrieve(rewritten_query, top_k, allowed_docs)`;
    - derives related questions from the first five search results;
    - builds final context;
    - for FAQ only, reranks related questions with TEI;
    - calls `RAGSystem.answer` for final vLLM generation;
    - records semantic fallback state;
    - returns through the graph and agent-state persistence.
12. `agent_graph.py:241-268`, chitchat path:
    - skips retrieval and rewriting history was already skipped by `AnsweringService`;
    - calls `RAGSystem.answer` with empty context and category `chitchat`;
    - sets no helpfulness feedback request.
13. `mobile_api.py:166-181`:
    - substitutes `متاسفانه پاسخی دریافت نشد.` if the core returns an empty answer;
    - calls `chat_manager.add_message(..., role="assistant", query_id=user_msg.id)`;
    - that updates the same pending production `queries` row with the answer and marks it completed.
14. `mobile_api.py:183-214`:
    - returns related questions only for FAQ category;
    - builds `TalkResponse` using the original external mobile session ID;
    - returns the production query row ID as `query_id`.

The evaluation worker must enter at step 4 by calling the shared executor with an evaluation provider. It must not execute steps 2, 3, or 13 against production storage.

## 2. Exact history lookup and persistence path

### Production transaction/message ledger

- User append: `mobile_api.py:143-150` -> `ChatManager.add_message` at `database.py:849-872` -> `DatabaseManager.add_message` at `database.py:547-598` -> `DatabaseManager.add_query`.
- Assistant append: `mobile_api.py:173-181` -> the same `ChatManager.add_message` -> `DatabaseManager.update_query_response` on the pending query row.
- History API rendering: `ChatManager.get_messages` -> `DatabaseManager.get_session_messages`, which reconstructs user/assistant messages from `queries` in ascending creation order.

This ledger is not what query rewriting reads.

### Rewrite history

`AnsweringService` calls `HistoryRewritingService.get_formatted_history_string` at `rewriting.py:82-143`.

That method:

1. converts the internal session key to `int` and calls `DatabaseManager.get_session_by_id`;
2. reads `chat_sessions.meta_data.agent_state.messages`;
3. filters to user/assistant-like roles and non-empty content;
4. globally deduplicates by exact content, regardless of role;
5. reverses the whole result if the first unique item has an AI role;
6. selects the final `max_turns * 2` messages, currently six;
7. formats with English `User:` and `AI:` prefixes.

If no usable history exists, it returns `[بدون مکالمه قبلی]`.

### Graph and final-prompt history

`AgentService._process_message` independently reloads the session row and `meta_data.agent_state` at `agent_service.py:103-117`. After the new raw user message is appended, `handle_general` and `handle_chitchat` select `state["messages"][-7:-1]`, which is at most six prior messages and excludes the current user message. `recent_history_to_text` at `agent_graph.py:345-357` formats them with Persian `کاربر:` and `دستیار:` prefixes and keeps only the most recent 3,000 characters, prefixed with `... ` when truncated.

### Agent-state persistence

The graph trims messages after both the user and assistant append. `AgentService` trims once more to the last 10 and then calls `DatabaseManager.update_session_metadata`, overwriting the production session metadata JSON.

### Evaluation persistence rule

For an imported source value such as `458923`:

- store only `source_session_id="458923"` on evaluation dataset/run rows;
- generate an opaque UUID `evaluation_session_key` from `(run_id, dataset_session_id, repeat_index)` using deterministic UUIDv5 or store a generated UUID once;
- pass only that UUID-typed key to `EvaluationHistoryProvider`;
- never convert the source value to an integer for core execution;
- never instantiate `ProductionHistoryProvider` in an evaluation worker task;
- never give `EvaluationHistoryProvider` a `ChatManager` or production `DatabaseManager` write dependency.

The evaluation turn ledger is `evaluation.run_turns`. The exact LangGraph checkpoint is stored in `evaluation.run_sessions.agent_state`; both are updated in one evaluation transaction after a turn. This explicit checkpoint is necessary because the current state contains more than user/assistant text, including pending questions, slots, feedback flags, and fallback state.

## 3. Minimal refactor to inject the history provider

Add `conversation_history.py` at repository root with the following narrow contract:

```python
@dataclass(frozen=True)
class ConversationSnapshot:
    conversation_key: object
    actor_id: int | None
    agent_state: dict[str, Any] | None
    metadata: dict[str, Any]
    version: int | None = None

class ConversationHistoryProvider(Protocol):
    namespace: str

    async def load_rewrite_messages(self, conversation_key: object) -> list[dict[str, str]]: ...
    async def load_snapshot(self, conversation_key: object) -> ConversationSnapshot: ...
    async def save_snapshot(
        self,
        snapshot: ConversationSnapshot,
        final_state: dict[str, Any],
    ) -> None: ...
```

Implementations:

- `ProductionHistoryProvider`
  - is constructed from existing `DatabaseManager`/`ChatManager` and `BoundedBlockingRunner`;
  - accepts only the existing internal production session key;
  - calls the same `get_session_by_id`, `get_session_metadata`, and `update_session_metadata` methods used today;
  - remains the default injected into `AnsweringService` and `AgentService` in `main.py`.
- `EvaluationHistoryProvider`
  - lives under `evaluation/execution/history_provider.py`;
  - accepts only an `EvaluationConversationKey` containing evaluation UUIDs;
  - reads/writes only `evaluation.run_sessions`, `evaluation.run_turns`, and their state/version columns;
  - uses compare-and-swap on `state_version` as a defensive concurrency check;
  - has no imports from `mobile_api.py` and no production persistence dependency.

Extract, without semantic cleanup, these shared functions into `conversation_history.py`:

- `new_agent_state(actor_id)` and `hydrate_agent_state(existing, actor_id)` from `AgentService`;
- `trim_agent_messages(messages, limit=10)` from `agent_graph.py` and the final `AgentService` trim;
- `format_rewrite_history(messages, max_turns=3)` from `HistoryRewritingService.get_formatted_history_string`;
- `select_answer_prompt_history(messages)` implementing the exact `[-7:-1]` selection;
- `format_answer_prompt_history(messages, max_chars=3000)` implementing the exact Persian prefixes and tail truncation.

Backward compatibility requirements:

- `AnsweringService.answer(request)` with no provider argument uses `ProductionHistoryProvider`.
- Existing web/mobile callers keep their current `AnswerRequestContext` fields and response shape.
- Existing stateless mass-answer behavior keeps `use_history=False` and `persist_agent_state=False` and does not require a provider.
- Keep the current ordering: rewrite-history load remains before `AgentService`'s per-session lock, while graph-state load/save remains inside that lock. Moving the lock around rewriting would alter current behavior for concurrent requests to the same production session and is not part of V1.
- Lock keys become `(provider.namespace, opaque_conversation_key)` so an evaluation UUID can never collide with a production integer session.
- Add an explicit `allow_production_side_effects` execution option. It defaults to `True` for production and is always `False` for evaluation, preventing ticket creation or future production-only graph effects.

`HistoryRewritingService` remains the one rewrite implementation. Its DB-reading wrapper delegates to the shared formatter for backward compatibility; the shared executor uses the provider plus that same formatter.

## 4. Exact shared pipeline executor

Do not create a second evaluation executor. Evolve the existing `AnsweringService` into the shared executor and keep its public name to minimize import churn.

Proposed call:

```python
result = await answering_service.answer(
    AnswerRequestContext(...),
    conversation_provider=evaluation_history_provider,
    observer=evaluation_trace_collector,
    allow_production_side_effects=False,
)
```

The single sequence remains:

1. validate and strip raw query;
2. production Persian normalization;
3. production intent classification;
4. load and format provider history for non-chitchat;
5. production rewrite prompt and generation;
6. normalize rewrite;
7. validate selected current documents from the same production knowledge tables;
8. load provider agent state;
9. run the same `AgentService` and compiled LangGraph;
10. run the same retrieval, context, prompt, and generation code;
11. save provider agent state when enabled;
12. apply the shared mobile empty-answer fallback helper when execution mode is `mobile_compatible`;
13. return `AnswerResult` plus trace collection to the caller.

The mobile route continues to own production-only user provisioning, mobile-session resolution, and the `queries` user/assistant ledger. The evaluation runner owns creation/finalization of `run_turns` and stage rows. These are adapters around one core executor, not alternate RAG implementations.

Evaluation must set the same per-turn 50-second deadline as mobile. The run itself has no HTTP request deadline. Production admission remains an HTTP adapter concern; evaluation uses explicit worker concurrency and records that difference in `config_snapshot`.

## 5. Observer and trace hook points

Add `pipeline_observer.py` with:

- `PipelineObserver` protocol;
- immutable stage artifact dataclasses or JSON-safe dictionaries;
- `NoOpPipelineObserver`, the production default;
- a task-local `ContextVar` binding so deep calls can emit without changing every public signature;
- a safe emission wrapper that never logs content and never changes a pipeline decision.

`EvaluationTraceCollector` lives only in the evaluation package. It accumulates artifacts in memory for one turn and flushes them to evaluation tables after the turn. Hook methods must not perform database/network I/O inside production stage decisions. Collector failures mark the evaluation trace incomplete but must not change the generated answer.

Do not add raw content to `RequestTrace`. Keep `utils/request_instrumentation.py` content-free. Its existing fingerprints, candidate IDs/scores, fallback code, and timings may remain.

| Stage order | Stage | Exact hook | Captured evaluation-only artifacts |
| ---: | --- | --- | --- |
| 10 | `NORMALIZATION` | `AnsweringService._answer`, around `PersianTextProcessor.normalize` plus `normalize_persian_text` | raw query, final normalized query, exact input/output SHA256, duration |
| 20 | `INTENT` | `IntentClassifier` immediately after the shared `_classify_embedding` result | normalized classifier input, label/class ID, confidence, `p_actionable`, `p_chitchat`, effective threshold, embedding policy name/dimension, duration |
| 30 | `REWRITE` | `AnsweringService` plus `HistoryRewritingService.rewrite_query` | exact shared-formatted history, original normalized query, rewrite prompt, raw extracted rewrite if available, final normalized rewrite, system message, model, max tokens, temperature, top-p, fallback-to-original flag/reason, duration |
| 40 | `RETRIEVAL` | `RAGSystem.retrieve` / `PersianHybridSearch.search` after final hybrid ordering | exact retrieval query, expanded/normalized semantic query, selected datasource names, top-k/candidate limits, ordered chunk IDs, ranks, hybrid/BM25/semantic scores, document name, candidate content, embedding request policy metadata, duration |
| 50 | `RERANK` | `PersianHybridSearch.rerank` and the graph branch deciding whether it runs | FAQ related-question input candidates, output order, TEI scores, threshold, accepted flag; otherwise explicit `SKIPPED` with reason. Primary-context reranking is recorded as absent, not simulated |
| 60 | `CONTEXT_SELECTION` | `agent_graph.make_handle_general` immediately after `generate_context`/slice selection | selected chunk IDs and order, exact context object/string passed toward prompt construction, context SHA256, category, recent-history selection and hash, duration |
| 70 | `PROMPT_BUILD` | `RAGSystem.answer` immediately after the active category branch builds local `prompt` and before `_completion` | source prompt symbol/category, prompt version if one is later defined, exact final prompt, prompt SHA256, system message, duration |
| 80 | `GENERATION` | `RAGSystem._completion`/`answer`, then graph fallback detection | model ID, effective max tokens/temperature/top-p, cleaned final answer, answer SHA256, fallback used/reason, dependency error code if any, duration |

Hash rules:

- text hashes are full lowercase SHA256 of the exact UTF-8 string passed to the next stage;
- structured hashes use UTF-8 JSON with `ensure_ascii=False`, sorted keys, and compact separators;
- retrieval/rerank comparison hashes include ordered IDs and scores plus candidate content hashes, not database row order;
- hashes are comparison aids, never substitutes for the evaluation-only administrator artifacts.

Stage exceptions are captured as `ERROR` with a stable `error_code` and safe structured details. `ServiceTimeoutError`, `ServiceUnavailableError`, `ServiceProtocolError`, and `ServiceOverloadedError` are infrastructure errors. `InvalidRequestError` and importer validation errors are validation failures. A semantic fallback remains a successful stage with `fallback_used=true`.

## 6. Current normalizer location

The mobile answer path normalizes in two layers:

- `utils/persian_hybrid_search.py:55-106`, `PersianTextProcessor.normalize`, using Parsivar plus Arabic/Persian character and whitespace replacements. `main.py:234-236` constructs it with `use_stemming=False` for the answering path.
- `utils/persian_normalization.py:147-154`, `normalize_persian_text`, which calls `normalize_persian_orthography` and the generated KB phrase lexicon in `utils/persian_query_normalizer.py`.

`AnsweringService` calls both at `answering_service.py:77-87`. Intent embedding, semantic retrieval, and TEI payload construction normalize again through the same `normalize_persian_text`; V1 records these calls but does not remove them.

## 7. Current intent classifier call

`answering_service.py:99-104` calls:

```python
intent_data = await self.intent_classifier.classify(normalized_query)
```

`intent_classifier.py:207-245` normalizes again, embeds through the same TEI query embedding callable, and runs `_GuardrailNet`. The active threshold is `IntentClassifier.threshold`, default `0.875`. Chitchat is selected only when `p_chitchat >= threshold`; ambiguous cases route to `general`.

For tracing, consolidate the duplicate `classify`/`classify_detailed` code into one private classification implementation. `classify` must project the exact existing two-field result; the executor may consume the detailed result without running a second embedding/classification. Characterization tests must prove identical labels and graph inputs.

## 8. Current rewrite call

For non-chitchat and history-enabled requests, `answering_service.py:110-127` calls:

```python
history_rewriting_service.get_formatted_history_string(
    current_chat_id=session_id,
    max_turns=3,
)
await history_rewriting_service.rewrite_query(
    current_query=normalized_query,
    current_summary=history,
)
```

`rewriting.py:245-255` builds `Config.QUERY_REWRITE_PROMPT`, then calls `RAGSystem.generate_text`. `utils/RagSystem.py:452-460` uses the same vLLM model with `RAG_REWRITE_MAX_TOKENS`, temperature `0.0`, the `_completion` default `top_p=0.95`, and the same system message used by `_completion`. `extract_rewritten_query` uses `<rewrite>` tags, then content after `</thought_process>`, then the original query as ultimate fallback. The result is normalized again.

## 9. Current retrieval call

`agent_graph.py:164-169` calls:

```python
await rag_system.retrieve(
    rewritten_query,
    top_k=PERFORMANCE_SETTINGS.rag_retrieval_top_k,
    allowed_docs=allowed,
)
```

`RAGSystem.retrieve` delegates to `PersianHybridSearch.search`.

`search` currently:

1. requires non-empty allowed documents;
2. applies `_expand_query_intent` and `normalize_persian_text`;
3. loads/builds a revision-aware BM25 corpus from production PostgreSQL chunks;
4. tokenizes/stems the query for BM25;
5. calls TEI `/embed` using `prompt_name="query"`, normalized output, and expected dimension 1,024;
6. calls synchronous Qdrant `query_points` through the bounded blocking runner with a document filter, semantic candidate limit, `with_payload=["chunk_id"]`, and no vectors;
7. unions BM25 and semantic candidates;
8. scores using reciprocal-rank fusion with `RRF_K=60`;
9. sorts only by hybrid score and returns top-k `SearchResult` values.

The union uses a Python `set`, and equal hybrid scores therefore have no explicit deterministic tie breaker. This is a legitimate potential source of stability divergence. V1 must observe it, not change it. A deterministic tie-break change would be a separate retrieval behavior change requiring retrieval and answer-quality tests.

## 10. Current reranking call

There is no primary chunk rerank in the verified path.

For FAQ documents only, `agent_graph.py:193-208` calls:

```python
await rag_system.search_engine.rerank(
    rewritten_query,
    related_question_candidates,
    threshold=PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold,
)
```

`PersianHybridSearch.rerank` at `persian_hybrid_search.py:650-740` posts normalized query and normalized candidate question texts to TEI `/rerank`, validates the returned index/score list, filters by the active threshold, preserves TEI output order, and keeps at most five candidates.

## 11. Current context-building call

`agent_graph.py:128-152` defines `prepare_context`.

- It calls `rag_system.generate_context(search_results)` for the FAQ aggregated XML string.
- It derives related questions from the first five search results.
- It calls `recent_history_to_text` for final-answer history.

At final generation (`agent_graph.py:218-224`):

- FAQ passes the aggregated context built from all returned top-k results, sorted again by `SearchResult.score` inside `generate_context`.
- Non-FAQ categories pass `search_results[:3]` directly. Python string interpolation in `RAGSystem.answer` therefore uses the list/dataclass representation currently produced by those objects.

Both forms must be captured exactly before prompt formatting.

## 12. Current final prompt call

`agent_graph.py:218-224` calls `RAGSystem.answer(...)` with the rewritten query, selected context, formatted recent history, empty summary, friendly tone, normal response type, history disabled, and resolved category.

`utils/RagSystem.py:268-449` contains three prompt branches:

- `chitchat`: fixed conversational policy prompt; current query/history are not actually interpolated because the template has no placeholders;
- `ابلاغیه ها` or `قرارداد ها`: formal document-bounded analyst prompt using context, recent history, and question;
- all other categories, including FAQ: Hibot FAQ/default prompt using formatted context and rewritten question, without recent history.

There is no explicit prompt version field. V1 stores `prompt_source` such as `RAGSystem.answer:default`, the Git commit SHA, and `prompt_version=null`. It must not invent a version number. A later explicit prompt constant/version can populate the field.

## 13. Current generation call

Final generation calls `RAGSystem._completion` with:

- model: `self.model_id`, default `/app/model` unless constructed otherwise;
- messages: system `You are a helpful assistant.` and user exact final prompt;
- `max_tokens`: `RAG_MAX_NEW_TOKENS`, or `RAG_CHITCHAT_MAX_NEW_TOKENS` for chitchat;
- `temperature=1` from the `answer` default;
- `top_p=0.95`;
- OpenAI-compatible async client pointed at `VLLM_URL`;
- no client retry.

`clean_llm_answer` removes `<thought_process>` and `<think>` blocks and strips the answer. Rewrite generation is a separate call to the same `_completion` path with rewrite max tokens and temperature zero.

## 14. Existing fallback paths

| Condition | Current result | V1 classification |
| --- | --- | --- |
| No search results | Graph still calls final generation with empty context and sets `fallback_reason="NO_RETRIEVAL_RESULTS"` | semantic fallback, not infrastructure error |
| Default/FAQ LLM emits exact ticket fallback fragment | Graph sets `LLM_CONTEXT_REFUSAL` | semantic fallback |
| Contract/notice LLM emits its exact missing-document refusal | Answer is returned, but current graph does not set a fallback reason | preserve `fallback_used=false` and `fallback_reason=null`; an observer may record `recognized_refusal_text=true` as a diagnostic metric, but it must not increment fallback counts |
| Rewrite lacks `<rewrite>` but has text after `</thought_process>` | Uses that text | rewrite fallback mode, not final-answer fallback |
| Rewrite has neither parseable form | Uses original normalized query | rewrite fallback mode `REWRITE_PARSE_FALLBACK`, not infrastructure error |
| Core returns empty answer | Mobile substitutes `متاسفانه پاسخی دریافت نشد.` | shared mobile-compatible fallback `NO_ANSWER`; evaluator uses the same helper |
| Chitchat non-banking refusal | Fixed-policy answer, no current `fallback_reason` | do not count as fallback in V1 |
| Missing/stale selected datasource for general intent | `InvalidRequestError` | validation error, not fallback/infrastructure |
| TEI/vLLM/Qdrant timeout/unavailable/invalid response | typed `ServiceError` | infrastructure error, never fallback |
| Unexpected exception | mobile returns generic HTTP 500 | internal execution error, never fallback |

Observer-only pattern recognition may add a diagnostic metric, but it must not enrich production fallback state, alter fallback counts, returned text, routing, selected context, or persistence. `fallback_used` and `fallback_reason` always reflect the effective production decision.

## 15. Proposed directory tree

```text
conversation_history.py                 # shared provider protocol and exact history rules
pipeline_observer.py                    # shared protocol, no-op, context binding, hashes
answering_service.py                    # existing shared executor, extended in place
agent_service.py                        # provider-backed state load/save
agent_graph.py                          # exact shared history helpers and stage hooks

evaluation/
  __init__.py
  config.py                             # EVAL_* settings only
  security.py                           # evaluation admin dependency
  db/
    __init__.py
    base.py                             # EvaluationBase only
    engine.py                           # same POSTGRES_* source, separate engine/session
    models.py
    repositories.py
  migrations/
    env.py
    script.py.mako
    versions/
      0001_evaluation_v1.py
  alembic.ini
  importer.py                           # one CSV/XLSX importer for both panels
  api/
    __init__.py
    main.py                             # separate evaluation-api FastAPI app
    dependencies.py
    schemas.py
    system.py
    datasets.py
    runs.py
    events.py
  execution/
    __init__.py
    celery_app.py
    tasks.py
    runtime.py                          # side-effect-free construction of existing core clients
    runner.py                           # bounded session workers, sequential turns
    history_provider.py
    trace_collector.py
    comparison.py
    event_bus.py
  tests/
    ...

evaluation_frontend/
  package.json
  package-lock.json
  vite.config.ts
  tsconfig*.json
  index.html
  public/
    fonts/                              # locally bundled Persian-capable font files/licenses
  src/
    app/
      App.tsx
      router.tsx
      providers.tsx
    api/
      client.ts
      schemas.ts
      sse.ts
    components/
      database-gate/
      dataset-import/
      session-table/
      turn-inspector/
      stage-inspector/
      stability/
      ui/                               # owned/customized shadcn components
    features/
      dataset-inspector/
      stability-inspector/
    styles/
      tokens.css
      index.css
    test/
      ...
```

The frontend has an independent build and deployment artifact. It is not inserted into the current Jinja templates. The evaluation API can serve it in a dedicated deployment, but the preferred production topology is a static frontend server/reverse proxy plus the separate `evaluation.api.main:app` backend.

## 16. Final database schema

All identifiers use lowercase snake_case. All tables, indexes, constraints, enums/checks, and foreign keys below are in schema `evaluation`. There are no cross-schema foreign keys. Use a dedicated `EvaluationBase = DeclarativeBase()` with `MetaData(schema="evaluation")`; never import the application `Base`.

Use PostgreSQL `uuid`, `text`, `boolean`, `integer`, `double precision`, `jsonb`, and timezone-aware `timestamptz`. Use text plus check constraints for statuses/types to avoid global PostgreSQL enum lifecycle coupling. JSONB metadata fields are non-null with server default `{}` unless explicitly nullable.

### `evaluation.datasets`

- `id uuid primary key`
- `filename text null`
- `source_type text not null check (source_type in ('FILE','MANUAL'))`
- `file_sha256 text null check (file_sha256 is null or length(file_sha256)=64)`
- `dataset_type text not null check (dataset_type in ('PIPELINE_INSPECTION','STABILITY'))`
- `row_count integer not null check (row_count >= 0)`
- `session_count integer not null check (session_count >= 0)`
- `valid_row_count integer not null check (valid_row_count >= 0)`
- `invalid_row_count integer not null check (invalid_row_count >= 0)`
- `created_at timestamptz not null default now()`
- `metadata jsonb not null default '{}'::jsonb`
- check `row_count = valid_row_count + invalid_row_count`
- index `(created_at desc, id)` for listing
- index `(dataset_type, created_at desc)`

### `evaluation.dataset_issues` (required refinement)

The proposed model needs normalized, queryable validation warnings/errors rather than an unbounded opaque array in dataset metadata.

- `id uuid primary key`
- `dataset_id uuid not null references evaluation.datasets(id) on delete cascade`
- `source_row_number integer null`
- `severity text not null check (severity in ('WARNING','ERROR'))`
- `code text not null`
- `field_name text null`
- `message text not null`
- `details jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- index `(dataset_id, severity, source_row_number)`

### `evaluation.dataset_sessions`

- columns from the approved model, with `source_session_id text null` to preserve leading zeroes and nonnumeric IDs;
- `dataset_id` is `on delete cascade`;
- `first_source_row integer not null check (first_source_row >= 2)`;
- timestamps are `timestamptz`;
- counts are nonnegative;
- unique partial index `(dataset_id, source_session_id) where source_session_id is not null`;
- unique `(dataset_id, first_source_row)`;
- index `(dataset_id, first_source_row)`.

### `evaluation.dataset_turns`

- columns from the approved model;
- `dataset_session_id` is `on delete cascade`;
- `turn_index integer not null check (turn_index >= 1)`;
- `source_row_number integer null check (source_row_number is null or source_row_number >= 2)`;
- `query text not null check (btrim(query) <> '')`;
- unique `(dataset_session_id, turn_index)`;
- index `(dataset_session_id, source_timestamp, source_row_number)`.

### `evaluation.runs`

Keep the approved columns and add:

- `infrastructure_error_count integer not null default 0`;
- `cancel_requested_at timestamptz null`;
- `worker_task_id text null`;
- `heartbeat_at timestamptz null`;
- `failure_code text null`;
- `failure_data jsonb null`.

Constraints:

- `dataset_id references evaluation.datasets(id) on delete cascade`;
- approved run type and status checks;
- all counters nonnegative and completed counters not greater than totals;
- `finished_at >= started_at` when both exist;
- index `(status, created_at)` for worker/status scans;
- index `(dataset_id, created_at desc)`;
- partial index `(heartbeat_at) where status='RUNNING'` for stale-run recovery.

`COMPLETED` means orchestration finished even if individual turns have errors; counters expose those errors. `FAILED` is reserved for fatal run-level failure that prevents orchestration from completing.

### `evaluation.run_sessions`

Keep the approved columns except move first-divergence fields to the comparison table below. Add:

- `infrastructure_error_count integer not null default 0`;
- `agent_state jsonb not null default '{}'::jsonb`;
- `state_version integer not null default 0 check (state_version >= 0)`;
- `metadata jsonb not null default '{}'::jsonb`.

Use:

- `run_id ... on delete cascade`;
- `dataset_session_id ... on delete set null`;
- `evaluation_session_key uuid not null unique`;
- `repeat_index integer not null default 1 check (repeat_index >= 1)`;
- unique `(run_id, dataset_session_id, repeat_index)` when `dataset_session_id is not null`;
- index `(run_id, status, repeat_index)`;
- index `(run_id, dataset_session_id, repeat_index)`.

Every repetition gets a new row, empty `agent_state`, and distinct evaluation session key.

### `evaluation.run_turns`

Keep the approved columns and add:

- `infrastructure_error boolean not null default false`;
- `error_code text null`;
- `error_data jsonb null`;
- `attempt_count integer not null default 1`;
- `metadata jsonb not null default '{}'::jsonb`.

Use:

- `run_session_id ... on delete cascade`;
- `dataset_turn_id ... on delete set null`;
- `request_id uuid not null unique`;
- full SHA256 fields as `text` with length checks;
- unique `(run_session_id, turn_index)`;
- index `(run_session_id, status, turn_index)`;
- index `(status, started_at)`.

The query and answer columns are evaluation content and are never copied into logs. State/checkpoint and completed turn update occur in one transaction.

### `evaluation.stage_results`

Keep the approved columns with:

- `run_turn_id ... on delete cascade`;
- `stage_name` check limited to `NORMALIZATION`, `INTENT`, `REWRITE`, `RETRIEVAL`, `RERANK`, `CONTEXT_SELECTION`, `PROMPT_BUILD`, `GENERATION`;
- `status` check limited to `PENDING`, `RUNNING`, `COMPLETED`, `SKIPPED`, `ERROR`;
- SHA256 length checks;
- nonnegative `stage_order` and `duration_ms`;
- unique `(run_turn_id, stage_name)`;
- unique `(run_turn_id, stage_order)`;
- index `(run_turn_id, stage_order)`.

No GIN index is added to JSONB in V1 because the defined UI reads stages by turn/order, not arbitrary JSON containment. Add a targeted expression/GIN index only after a measured query requires it.

### `evaluation.stability_comparisons` (required refinement)

First divergence belongs to a logical source session across repetitions, not to one repeated `run_session` row.

- `id uuid primary key`
- `run_id uuid not null references evaluation.runs(id) on delete cascade`
- `dataset_session_id uuid null references evaluation.dataset_sessions(id) on delete set null`
- `first_divergent_turn integer null`
- `first_divergent_stage text null`
- `comparable_repeat_count integer not null`
- `fallback_rate double precision not null default 0`
- `variant_summary jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- unique `(run_id, dataset_session_id)` when dataset session is non-null
- index `(run_id, first_divergent_turn)`

The comparison algorithm groups by logical dataset session and `turn_index`, orders stages by fixed stage order, and compares canonical stage outcome tuples. Text/output differences are `DIVERGENCE`, never automatically `ERROR`. Failed/missing repetitions are reported as not comparable and in error counts; they do not get mislabeled as semantic text divergence.

### Delete behavior

- Deleting a run cascades only through evaluation run sessions, turns, stages, and comparisons.
- Deleting a dataset cascades through its evaluation sessions/turns and associated evaluation runs, then their evaluation descendants.
- There is no FK, trigger, cascade, or ORM relationship to `users`, `chat_sessions`, `queries`, knowledge tables, or any public/application table.
- No frontend operation drops tables or schema.

## 17. Migration strategy

Create a completely independent Alembic environment at `evaluation/migrations` with `evaluation/alembic.ini`.

Configuration requirements:

- build the SQLAlchemy URL from the same `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` values using `sqlalchemy.engine.URL.create`, never string interpolation or logging;
- `target_metadata = EvaluationBase.metadata` only;
- `include_schemas=True`;
- `version_table="alembic_version"`;
- `version_table_schema="evaluation"`;
- include-object/name filters reject every schema except `evaluation`;
- the initial revision creates only the evaluation schema objects listed above;
- downgrade, available only to operators through CLI, drops only evaluation-owned objects in dependency order;
- never call application `Base.metadata.create_all`, any `drop_all`, the existing `DatabaseManager.init_db`, or the existing Alembic environment.

Because `evaluation.alembic_version` cannot be created before the schema exists, the fixed migration runner performs only this predefined bootstrap before `alembic upgrade head`:

```sql
create schema if not exists evaluation;
```

It is not user-supplied SQL. The same SQLAlchemy connection is placed in `AlembicConfig.attributes["connection"]` so schema bootstrap, advisory lock ownership, and migration execution use one database session.

Migration endpoint algorithm:

1. require evaluation administrator authentication;
2. require `EVAL_ALLOW_DB_INIT=true`;
3. require exact confirmation `CREATE_EVALUATION_TABLES`;
4. acquire `pg_try_advisory_lock(hashtext('ragbot:evaluation:migrations:v1'))`;
5. return HTTP 409 if another initializer owns the lock;
6. create the evaluation schema if absent;
7. run only `alembic upgrade head` from the fixed evaluation script directory;
8. inspect required objects/revision;
9. always release the session advisory lock in `finally`;
10. return the new safe status.

`GET /api/v1/evaluation/system/database-status` is read-only and must not create the schema/version table. It compares:

- whether schema `evaluation` exists;
- current revision from `evaluation.alembic_version` if readable;
- head revision from local `ScriptDirectory`;
- a constant allowlist of expected evaluation tables/indexes.

Response state:

- `NOT_INITIALIZED`: schema/version table or initial objects absent;
- `READY`: current revision equals head and required objects exist;
- `UPGRADE_REQUIRED`: a known older evaluation revision or missing object while schema is initialized;
- `ERROR`: safe connection/inspection/migration error.

The response exposes only state, current/head revision strings, `allow_initialize`, migration-in-progress status, and missing expected evaluation object names. It never exposes host, database/user name, SQLAlchemy URL, SQL text, or exception details containing secrets.

Required deployment permission check is `has_database_privilege(current_user, current_database(), 'CREATE')` when the schema is absent, followed by schema `USAGE/CREATE` and DML privileges after provisioning. This audit did not connect to the configured database because the repository cannot prove that target is non-production. If the deployment role lacks database `CREATE` and the schema has not been operator-provisioned, initialization is a blocking deployment issue. There is no fallback to public/application tables.

## 18. API endpoints

Use a separate FastAPI application `evaluation.api.main:app`, with router prefix `/api/v1/evaluation`. All endpoints use typed Pydantic request/response models and one evaluation-admin dependency.

V1 authentication (updated by the focused operational simplification):

- reuse `POST /api/login`, `AuthenticationService`, and the existing RagBot `users` table;
- do not create an evaluation token or evaluation users/admins table;
- keep the existing password storage and authentication semantics unchanged;
- require authenticated RagBot process state on evaluation endpoints;
- use same-origin `fetch` for REST and SSE from `/evaluation`.

System/data source:

- `GET /api/v1/evaluation/system/database-status`
- `POST /api/v1/evaluation/system/database-initialize`
- `GET /api/v1/evaluation/system/capabilities` - safe limits, enabled state, queue availability
- `GET /api/v1/evaluation/datasources` - current selectable document titles, read from existing knowledge tables with no evaluation FK

Datasets:

- `POST /api/v1/evaluation/datasets/import` - multipart CSV/XLSX plus dataset type
- `POST /api/v1/evaluation/datasets/manual` - one query or ordered query list; creates the same normalized dataset/session/turn model
- `GET /api/v1/evaluation/datasets`
- `GET /api/v1/evaluation/datasets/{dataset_id}`
- `GET /api/v1/evaluation/datasets/{dataset_id}/sessions`
- `GET /api/v1/evaluation/dataset-sessions/{session_id}/turns`
- `DELETE /api/v1/evaluation/datasets/{dataset_id}` - explicit confirmation and evaluation-only cascade

Runs/results:

- `POST /api/v1/evaluation/runs` - dataset/run type, selected documents, repeat count, and bounded concurrency
- `GET /api/v1/evaluation/runs`
- `GET /api/v1/evaluation/runs/{run_id}`
- `GET /api/v1/evaluation/runs/{run_id}/sessions`
- `GET /api/v1/evaluation/run-sessions/{run_session_id}/turns`
- `GET /api/v1/evaluation/run-turns/{run_turn_id}/stages`
- `GET /api/v1/evaluation/runs/{run_id}/stability`
- `POST /api/v1/evaluation/runs/{run_id}/cancel`
- `DELETE /api/v1/evaluation/runs/{run_id}` - terminal runs only, explicit confirmation
- `GET /api/v1/evaluation/runs/{run_id}/events`

List endpoints use cursor/keyset pagination by `(created_at, id)` or `(turn_index, id)`, not unbounded responses. Responses containing prompts, contexts, candidate content, queries, or answers are administrator-only and set `Cache-Control: no-store`.

### One shared importer

Both React panels call the same dataset endpoints and backend `evaluation.importer`. The browser does not implement independent CSV/XLSX semantics.

Importer rules:

- read uploads with a byte limit, compute SHA256, parse in a bounded worker thread, persist normalized rows transactionally, then release/discard bytes;
- support UTF-8/UTF-8-BOM CSV with deterministic delimiter sniffing and `.xlsx` through pandas/openpyxl;
- require exactly one normalized `query` column; support exact optional `session_id` and `time` names for V1;
- source row numbering is 2-based, including the header as row 1;
- blank/whitespace query is an invalid row and creates a dataset issue, not a turn;
- preserve `source_session_id` as text. Numeric spreadsheet values with integral value are canonicalized without a trailing `.0`; text retains leading zeroes;
- every blank session ID gets a distinct synthetic dataset session keyed by its source row. Blank rows are never grouped together;
- a nonblank session ID groups valid rows exactly by canonical text value;
- if every valid turn in a session has a valid timestamp, order by `(source_timestamp ASC, source_row_number ASC)`;
- if none has a valid timestamp, preserve source row order and issue `NO_VALID_SESSION_TIMESTAMPS`;
- for mixed valid/missing/invalid timestamps, preserve source row order for the entire session and issue `INCOMPLETE_SESSION_TIMESTAMPS`; do not guess where invalid timestamps belong;
- imported timestamps affect ordering only. The worker never sleeps to reproduce elapsed wall time;
- accepted timestamp formats must be versioned and deterministic: native XLSX datetime, ISO-8601 with timezone, and a short documented allowlist. Do not use locale-guessing parsing;
- store parser version, detected columns, warnings, filename, SHA256, sessions, and normalized turns only; never store the original binary and never use MinIO.

## 19. Worker architecture

Use Celery with Redis because no durable, already-supported alternative exists in the repository.

```text
React -> evaluation-api -> PostgreSQL run row -> Redis/Celery queue
                                               -> evaluation-worker
evaluation-worker -> existing AnsweringService/AgentService/LangGraph/RAGSystem
evaluation-worker -> evaluation PostgreSQL results -> Redis metadata event
```

PostgreSQL is authoritative. Redis holds only Celery delivery state, cooperative cancellation notification, and content-free progress events.

Execution model:

- one Celery task orchestrates one run;
- the worker starts a dedicated async runtime for the task and closes all HTTP/Qdrant/blocking resources deterministically;
- it constructs the existing `DatabaseManager` only for read-only knowledge chunk/document access and the existing RAG classes; it does not call `DatabaseConnections.connect_all`, because that method can create a MinIO bucket and Qdrant collection;
- it constructs Qdrant in read-only-use mode and fails if the configured collection is absent;
- it never calls `DatabaseManager.init_db`;
- `acks_late` and task identity are used with DB claim/heartbeat state; duplicate delivery sees the existing run claim and does not create duplicate run sessions/turns;
- use one Celery evaluation queue and a conservative worker process concurrency. On staging, start with one run task at a time because evaluation shares the single GPU services with normal traffic;
- inside a run, use an `asyncio.Queue` with exactly `EVAL_SESSION_CONCURRENCY` fixed workers. Do not create one task per session and do not use unbounded `gather`;
- each queue item is a complete run session. Its turns execute in strict `turn_index` order and commit generated Q/A to evaluation history before the next turn;
- dataset inspection defaults to a conservative bounded session concurrency, initially 1 until a staging benchmark justifies more;
- all stability run types default to and initially enforce concurrency 1 unless an explicit future diagnostic override is approved;
- every repetition creates fresh `run_session.agent_state={}` and a distinct evaluation session key;
- every turn uses the mobile-compatible 50-second timeout and the same effective model/retrieval configuration;
- update run/session/turn counters and publish progress only after the corresponding PostgreSQL transaction commits.

Cancellation is cooperative:

- API sets `cancel_requested_at` and publishes a content-free cancellation notification;
- queued Celery work may be revoked without process termination;
- a running worker checks cancellation before claiming a session and before every turn;
- an in-flight model/retrieval call is allowed to finish or hit its timeout so resource cleanup and result classification remain deterministic;
- remaining rows are marked cancelled and the run reaches `CANCELLED`.

Run retry/recovery:

- maintain `heartbeat_at` while running;
- claim rows transactionally;
- unique constraints make session/turn creation idempotent;
- if a worker dies after external generation but before commit, the turn may be regenerated on retry. Increment `attempt_count`; never pretend exactly-once external generation;
- a recovery command/task may requeue stale `RUNNING` runs after an operator-defined heartbeat threshold.

The evaluation workload adds contention outside the process-local production admission limiter. `EVAL_SESSION_CONCURRENCY`, Celery worker concurrency, TEI/vLLM pools, and Qdrant concurrency must therefore be benchmarked together on staging. Do not change vLLM/TEI/Qdrant configuration in this feature.

## 20. SSE architecture

Use FastAPI's SSE response support available in the installed FastAPI version, with an async generator and disconnect handling.

Worker event flow:

1. commit durable run/session/turn/stage state in PostgreSQL;
2. append a small event to Redis Stream `evaluation:run:{run_id}:events` with bounded length/TTL;
3. include only event ID, entity UUIDs, status, stage name, counters, and durations;
4. never put query, prompt, context, candidate content, answer, auth, or banking data in Redis events.

SSE endpoint behavior:

- require evaluation admin authorization;
- use browser `fetch` streaming, not native `EventSource`, so the bearer header is not put in a URL;
- accept `Last-Event-ID` and use Redis `XREAD` for resume;
- emit an initial `snapshot` assembled from PostgreSQL, then stream new events;
- send a heartbeat comment approximately every 15 seconds;
- stop promptly on client disconnect;
- after Redis loss/expiry, send a fresh PostgreSQL snapshot and continue from current stream head;
- use `Cache-Control: no-cache, no-store`, `Content-Type: text/event-stream`, and disable proxy buffering.

Events:

- `run_started`
- `session_started`
- `turn_started`
- `stage_completed`
- `turn_completed`
- `session_completed`
- `progress`
- `run_completed`
- `run_failed`
- add `run_cancelled` for the required cancellation path.

TanStack Query treats SSE as an invalidation/progress signal. On terminal or reconnect events it refetches PostgreSQL-backed REST resources. Redis is never the only copy of a result.

## 21. React architecture

Design read: a regulated internal diagnostic cockpit for RagBot administrators, with high information density, restrained motion, Persian-first content inspection, and a locally bundled shadcn/Radix foundation.

Design settings for implementation:

- `DESIGN_VARIANCE: 3`
- `MOTION_INTENSITY: 2`
- `VISUAL_DENSITY: 8`

This is a dashboard/data-table product, which `design-taste-frontend` explicitly says is outside its primary scope. Use TanStack Table and accessible shadcn/Radix primitives for the dense product UI, while applying that skill only where relevant: consistent tokens, explicit responsive collapse, complete loading/empty/error states, local assets, contrast, reduced motion, and avoidance of decorative dashboard clutter.

Application structure:

- top-level database gate calls `database-status` before enabling uploads or runs;
- `NOT_INITIALIZED` shows `Evaluation database is not initialized` and, only when allowed, `[ Create Evaluation Tables ]`;
- `UPGRADE_REQUIRED` shows `[ Upgrade Evaluation Tables ]`;
- when `EVAL_ALLOW_DB_INIT=false`, show operator instructions and no active migration control;
- primary navigation has two routes/tabs: Dataset Session Inspector and Stability / Reproducibility Inspector;
- one shared `DatasetImport` component calls the one backend importer for both panels;
- a required run-configuration area selects current datasources because production general intent rejects an empty/stale selection;
- server-side pagination keeps large datasets/runs bounded.

Panel 1:

- one TanStack row per logical dataset session;
- summary columns: source/synthetic label, turn count, first query, fallback count, infrastructure error count, duration, status;
- first expansion level fetches ordered turns;
- second expansion level fetches the fixed stage rail and stage details;
- stage detail provides structured tabs for input, output, metrics, timing, and error, with Persian content rendered `dir="auto"` and technical metadata LTR;
- no original upload download because the binary is discarded.

Panel 2:

- modes: one query, manually ordered Q1/Q2/Q3 session, or file import;
- assistant messages are never manually entered;
- repeat count is a validated positive bounded integer;
- comparison grid groups by logical source session plus turn index;
- columns/sections report variants for normalization, intent, rewrite, retrieval, rerank, context, prompt, answer, and fallback rate;
- the first divergent turn/stage is visually anchored to the stage rail;
- UI copy says `Divergence`, never `Error`, for differing successful text/artifacts;
- failed repetitions remain separately marked as error/not-comparable.

Distinctive but functional visual signature: an eight-stage provenance rail whose segments show stable/divergent/skipped/error state and open the exact artifact comparison. It encodes actual pipeline structure and is not decorative numbering.

Frontend safety and quality:

- all JavaScript, CSS, icons, fonts, and shadcn component code are built into the artifact;
- no CDN, remote font, telemetry, public module import, public image, or runtime package fetch;
- reuse the already vendored Vazirmatn font files/licenses by copying them into the independently deployable frontend artifact, with system Persian-capable fallback;
- use one bundled icon family, preferably Phosphor, rather than hand-written SVGs or remote icons;
- use semantic color plus text/icon labels, not color alone;
- keyboard-operable nested expansion, visible focus, WCAG AA contrast, reduced-motion support, skeletons matching table layout, and explicit empty/error states;
- no arbitrary raw HTML rendering of prompts/context; display as text to prevent stored XSS;
- no auth token in localStorage, URL, logs, or built environment variables;
- extend the repository offline frontend scanner or add an evaluation-specific equivalent that scans built HTML/CSS/JS and fails on public runtime targets.

## 22. Installed frontend skills and application

Requested exact skills:

| Skill | Path | Available | Application |
| --- | --- | --- | --- |
| `design-taste-frontend` | `/root/projects/faq/.agents/skills/design-taste-frontend/SKILL.md` | Yes, read in full | Apply relevant accessibility, local-asset, responsive, state, contrast, and consistency guardrails. Do not force its landing-page patterns onto this dashboard; the skill explicitly excludes dashboards/data tables |
| `frontend-design` | `/root/projects/faq/.agents/skills/frontend-design/SKILL.md` | Yes, read in full | Ground the UI in the actual evaluation workflow, use deliberate type/color/layout tokens, make the trace rail the one justified signature element, keep copy functional, and critique the design against generic dashboard defaults |

Other locally installed and used audit guidance:

- FastAPI: `.agents/skills/fastapi/SKILL.md`
- FastAPI project structure: `.agents/skills/fastapi-templates/SKILL.md`
- async Python: `.agents/skills/async-python-patterns/SKILL.md`
- Python testing: `.agents/skills/python-testing-patterns/SKILL.md`
- PostgreSQL: `.agents/skills/supabase-postgres-best-practices/SKILL.md`
- LLM evaluation: `.agents/skills/llm-evaluation/SKILL.md`
- Python observability: `.agents/skills/python-observability/SKILL.md`
- RAG implementation: `.agents/skills/rag-implementation/SKILL.md`

No locally installed skill named exactly `architecture` was found. `fastapi-templates` is the closest installed project-architecture skill. The two requested frontend skills were found locally even though they were not included in the session's abbreviated available-skills catalog.

## 23. Required dependencies

### Already present in `requirements.lock.txt`

- FastAPI, Uvicorn, Pydantic, `python-multipart`
- SQLAlchemy 2.0, asyncpg, psycopg2-binary
- Alembic (present but currently very old at 1.4.3; evaluation compatibility must be tested or upgraded deliberately)
- redis
- pandas and openpyxl
- httpx, OpenAI client, Qdrant client, LangGraph, Torch, Parsivar, rank-bm25
- `sse-starlette` (FastAPI's native SSE API is preferred if verified against the pinned FastAPI)

### Backend additions

- Celery with Redis transport support
- a portable evaluation/backend dependency manifest and lock procedure, because the current full environment snapshot contains machine-local wheel/editable paths
- optional test-only PostgreSQL container orchestration, not a runtime package

Use the standard library for SHA256, UUID, constant-time token comparison, CSV primitives, and canonical JSON. No MinIO package use is needed by evaluation code.

### Backend test additions

- The repository's primary runnable tests use `unittest`, including `IsolatedAsyncioTestCase`; pytest is not in the lock even though one benchmark test imports it.
- Either keep new backend tests in `unittest` to avoid another dependency, or deliberately add pytest, pytest-asyncio, and pytest-cov with a canonical test command. Do not claim pytest support until installed and run.

### Frontend runtime/build

- React and React DOM
- TypeScript
- Vite and React plugin
- Tailwind CSS v4 with the Vite plugin
- TanStack Query
- TanStack Table
- shadcn/ui-owned components and their Radix dependencies
- `class-variance-authority`, `clsx`, and `tailwind-merge`
- `@phosphor-icons/react`
- Zod for client response/form validation

The frontend does not need a spreadsheet parser because file semantics live in the shared backend importer.

### Frontend tests

- Vitest
- Testing Library React, user-event, jest-dom
- jsdom
- Playwright for real-browser nested-table, upload, SSE, and offline network tests when a browser binary is provisioned locally

Pin and commit the frontend lockfile. Installation/build may access the package registry only during an approved build step; the deployed browser artifact performs zero public runtime requests.

## 24. Existing RagBot core files that need modification

| File | Required change |
| --- | --- |
| `answering_service.py` | Accept provider/observer/side-effect options; use shared history formatter; remain the one executor; return detailed intent/fallback trace data without changing response semantics |
| `agent_service.py` | Replace hardcoded production state load/save with the provider default/override; use provider namespaced locks; disable ticket side effect for evaluation; keep stateless path |
| `agent_graph.py` | Delegate all history selection/formatting/trimming to shared exact functions; add no-op observer hook calls at retrieval/context/fallback boundaries |
| `new_architecture/app/services/history/rewriting.py` | Separate DB lookup from exact shared formatting; emit rewrite artifacts; retain the same prompt, generation call, extraction, and fallback behavior |
| `intent_classifier.py` | Consolidate classify/detailed execution so scores and threshold can be observed without a second classification and without changing the existing label contract |
| `utils/RagSystem.py` | Emit exact prompt/generation artifacts and settings through the optional observer; do not change prompt text or generation parameters |
| `utils/persian_hybrid_search.py` | Emit retrieval candidates/content and related-question rerank inputs/outputs; keep search/rank logic unchanged |
| `mobile_api.py` | Use the shared mobile empty-answer fallback helper; continue to own all production user/session/query writes; pass no explicit provider so production remains default |
| `main.py` | Construct/register `ProductionHistoryProvider` and inject it into the shared services; include no evaluation router because evaluation API is a separate app |
| `utils/request_instrumentation.py` | No content capture. At most add stage-duration names if needed; preserve sanitized summaries and headers |
| `scripts/audit_offline_frontend.py` | Extend roots or add an evaluation build scanner so the new artifact is checked for public runtime resources |

New shared files `conversation_history.py` and `pipeline_observer.py` are production-core infrastructure, not evaluation copies of RAG behavior.

## 25. Why each production-core modification is required

- `AnsweringService`: it is already shared by web/mobile/mass answer and owns normalization, intent, history, rewrite, document validation, and graph invocation. A second evaluation service would violate the one-implementation requirement.
- `AgentService`: this is where production session IDs are converted to integers and production metadata is hardcoded. It is the critical unsafe seam for imported source IDs.
- `agent_graph.py`: retrieval, context selection, prompt-history selection, and fallback decisions occur here. Observer hooks elsewhere cannot reconstruct exact decisions after the fact.
- `HistoryRewritingService`: it combines storage lookup and formatting today. Separating only the lookup enables evaluation state while preserving one formatter/rewriter.
- `IntentClassifier`: the normal call discards score/probabilities. A common internal implementation is required to expose them without a second potentially divergent classification.
- `RAGSystem`: it is the only place where the exact final prompt and effective vLLM parameters coexist.
- `PersianHybridSearch`: it is the only place with expanded query, BM25/semantic candidate scores, Qdrant order, candidate content, and TEI rerank scores.
- `mobile_api.py`: sharing the final empty-answer fallback prevents the evaluator from creating a copied mobile fallback.
- `main.py`: production must explicitly receive the default provider so backward compatibility is obvious and testable.
- `RequestTrace`: explicitly keeping it content-free prevents the evaluation feature from turning normal request logging into a banking-data leak.

No prompt, threshold, retrieval formula, context limit, model setting, or service URL is modified by these changes.

## 26. Tests and benchmarks proving production behavior is unchanged

### Phase 0: before-refactor characterization

Add deterministic tests against the current code before changing it, recording exact fixtures for:

- raw -> Parsivar -> canonical normalization;
- intent input, call count, label, and threshold boundary;
- rewrite history global deduplication, reversal heuristic, six-message limit, exact prefixes, rewrite prompt, generation parameters, extraction, and fallback;
- state initialization/hydration and 10-message trimming;
- prompt recent-history `[-7:-1]`, Persian prefixes, and 3,000-character tail behavior;
- exact retrieval query and selected documents;
- candidate ordering/scores from fixed BM25, embedding, and Qdrant fakes;
- explicit absence of primary reranking;
- FAQ related-question reranking threshold/order;
- exact selected context and exact prompt string for all three category branches;
- exact final vLLM messages/settings and cleaned answer;
- all fallback answers/reasons and typed infrastructure errors;
- current chitchat fixed-prompt behavior.

### Provider and isolation tests

- Production provider calls the same production DB methods and produces the same state/history as the pre-refactor path.
- Default `AnsweringService.answer` output, call order, and production persistence calls match characterization fixtures.
- Evaluation provider accepts only evaluation UUID keys and has no `ChatManager` dependency.
- Imported `source_session_id=458923` is stored as source metadata but never appears in a production lookup/persistence spy call.
- A test production `ChatManager` that raises on any call remains completely untouched during evaluation execution.
- Evaluation turn/checkpoint transaction writes only schema `evaluation`.
- Evaluation history Q1/A1 is present for Q2 rewrite; turns are strictly sequential.
- Repeat 2 starts from empty state and never sees Repeat 1 answers.
- production side effects such as ticket creation are disabled in evaluation.

### Observer tests

- `NoOpPipelineObserver` produces byte-identical output and identical fake dependency calls compared with no explicit observer.
- `EvaluationTraceCollector` receives all required stages and exact artifacts.
- collector failure cannot change answer/routing/context; it marks trace capture failure separately.
- `RequestTrace.trace_summary` remains content-free: no raw query, history, prompt, chunk content, answer, auth, national code, or banking data.
- hash fixtures are stable across processes and JSON key order.

### Importer tests

- CSV/XLSX produce identical normalized dataset structures.
- required/missing/duplicate columns, encoding, malformed workbook, size and row limits.
- source row numbering and file SHA256.
- timestamp ascending order and source-row tie break.
- no timestamps and mixed invalid timestamps preserve row order with correct warnings.
- blank session IDs on adjacent rows create distinct synthetic sessions.
- numeric/text session IDs preserve required canonical form and leading zeroes.
- uploaded byte buffer is not retained or sent to MinIO after persistence.

### PostgreSQL/migration tests

Use a disposable PostgreSQL instance only. SQLite cannot prove schema, JSONB, FK, advisory lock, or Alembic-version behavior.

- empty DB -> `NOT_INITIALIZED` -> initialize -> `READY`;
- initialized old revision -> `UPGRADE_REQUIRED` -> upgrade -> `READY`;
- `EVAL_ALLOW_DB_INIT=false` refuses POST without mutation;
- wrong confirmation refuses POST;
- concurrent initializer advisory lock returns one migration and one 409/no duplicate work;
- migration inspection proves every created relation is in `evaluation`;
- query `pg_constraint` proves every evaluation FK target is also in `evaluation`;
- dataset/run delete cascades remain inside evaluation;
- no application table row counts change;
- downgrade invoked only by operator test affects only evaluation objects;
- missing CREATE SCHEMA privilege reports a safe blocking error and does not fall back.

### Worker/SSE/API tests

- fixed worker count bounds concurrent sessions; no unbounded task creation;
- per-session turns never overlap; different sessions may overlap only to configured bound;
- stability forces/defaults concurrency 1;
- cancellation between turns and timeout classification;
- worker retry/duplicate delivery respects unique constraints and attempt count;
- PostgreSQL commit occurs before event publication;
- Redis loss leaves complete results in PostgreSQL;
- SSE event names, IDs, heartbeat, reconnect, PostgreSQL snapshot fallback, disconnect cleanup, and content-free payloads;
- all endpoints require admin auth and return `Cache-Control: no-store` for content-bearing data;
- system status never exposes connection secrets.

### Frontend tests

- database gate for all four states and disabled-init instructions;
- shared importer used by both panels;
- nested session -> turn -> stage expansion and keyboard operation;
- manual single/session/file stability modes;
- first divergent turn/stage and `Divergence` vs `Error` copy;
- fresh repeat state rendering;
- loading, empty, validation, infrastructure error, cancellation, and reconnect states;
- Persian `dir=auto`, text escaping, no raw HTML injection;
- built artifact offline scanner finds zero public runtime requests;
- browser network test blocks public network and still completes the UI workflow.

### Production parity and quality gates

- Run the existing answering, normalization, embedding policy, retrieval consistency, admission, concurrency, mass-answer, and mobile load-test unit suites with the correct project interpreter.
- Create a golden mobile-vs-evaluation test using identical prior agent state, query, documents, fixed dependency responses, and model output. Assert identical normalized query, intent, rewrite, retrieval order/scores, context, prompt, generation settings, answer, and fallback.
- Run retrieval tests and answer-quality tests before merge. The repository currently has no canonical commands for either; defining those commands and fixtures is a release gate even though V1 intends no model behavior change.
- Capture a before/after mobile benchmark on staging with `NoOpPipelineObserver`, changing only the seam/observer code. Compare latency/throughput/error counts under the same configuration and record evidence. Do not benchmark production.
- Respect the 50-second external deadline and do not claim a benchmark/test passed unless its command was actually run and result recorded.

Implementation order:

1. add characterization tests and baseline benchmark;
2. extract exact history helpers and provider seam;
3. prove production parity with no-op observer;
4. add observer hooks and prove parity again;
5. add evaluation metadata/migrations and disposable-Postgres tests;
6. add importer/API/auth/database gate;
7. add Celery worker, cancellation, comparison, and SSE;
8. build the separate React frontend and offline checks;
9. run full parity, retrieval, answer-quality, integration, browser, and before/after benchmark gates.

Only one major behavior/performance variable is changed per experiment.

## 27. Blocking ambiguities and deployment gates

Resolved design choices:

- Imported session IDs are text metadata only; opaque evaluation UUID keys drive execution.
- Evaluation calls the shared core directly and never calls the mobile HTTP endpoint.
- The state checkpoint is an explicit evaluation column because messages alone cannot reproduce LangGraph state.
- Primary reranking remains absent and is reported as skipped.
- Mixed timestamp validity preserves source order rather than guessing.
- Stability comparison belongs to a logical-session comparison table.
- Celery + Redis is selected over the existing in-process job manager.
- The evaluation API is separate from the current chat API.
- V1 admin protection uses an evaluation-only bearer token hash, not the current process-global login state.

Deployment/release gates that do not block implementation of the architecture:

1. Database privilege is unverified. The configured target cannot be proven non-production from repository metadata, so this audit intentionally made no connection. If the role cannot create schema and an operator does not pre-provision `evaluation`, deployment is blocked.
2. Redis endpoint/topology and service definitions are not present in the repository. Operators must provide a staging Redis instance and worker/API service units or containers.
3. Celery is not installed in the current lock and the repository lacks a canonical portable backend dependency installation workflow. This must be corrected as part of implementation.
4. Retention/access policy for content-full evaluation traces must be approved operationally. V1 deletion endpoints exist, but the organization must choose retention duration and database grants before production use.
5. Retrieval and answer-quality test commands are currently unknown. They are a merge/release gate for any accidental behavior change.
6. The evaluation workload shares vLLM, TEI, Qdrant, and GPU capacity with normal traffic. Safe initial concurrency is 1; raising it requires staging before/after evidence.
7. Exact accepted non-ISO timestamp formats should be documented with product owners before importer fixtures are frozen. The architecture does not rely on locale guessing.

None of these requires a second RAG implementation or a change to the proposed seam. There is no unresolved architectural blocker.

READY_TO_IMPLEMENT=true
