# RagBot Evaluation V1 core parity audit

## Verdict

**PASS.** Production `POST /api/mobile/v1/talk` and evaluation worker turns enter the same `AnsweringService.answer()` implementation. From normalization through fallback handling, both paths call the same object types, functions, LangGraph, RAG system, TEI clients, Qdrant client, prompt builder, and vLLM completion method. Evaluation changes only the conversation storage provider, execution policy, and optional trace collector.

No evaluation-specific normalizer, classifier, rewriter, retriever, reranker, context builder, prompt builder, generator, or fallback implementation exists.

## End-to-end paths

Production:

```text
POST /api/mobile/v1/talk
  mobile_api.gateway_talk
  mobile_api._gateway_talk
  ChatManager.get_or_create_user_by_national_code
  ChatManager.resolve_mobile_session
  ChatManager.add_message(user)
  AnsweringService.answer(default production policy/provider, NoOp observer)
  AgentService.process_message_detailed
  canonical LangGraph from agent_graph.build_graph
  ProductionHistoryProvider.save_snapshot
  ChatManager.add_message(assistant)
  unchanged TalkResponse
```

Evaluation:

```text
Celery task evaluation.execute_run
  worker.tasks._execute
  core_adapter.runtime.canonical_turn_runtime
  worker.runner.EvaluationRunExecutor.execute
  EvaluationRunExecutor._execute_session (turn_index loop, sequential)
  AnsweringService.answer(EvaluationHistoryProvider,
                          EVALUATION_EXECUTION_POLICY,
                          EvaluationTraceCollector)
  AgentService.process_message_detailed
  the same canonical LangGraph from agent_graph.build_graph
  EvaluationHistoryProvider.save_snapshot
  evaluation.run_turns + evaluation.stage_results persistence
```

The evaluation runtime constructs the existing core classes directly: `PersianTextProcessor`, `RAGSystem`, `IntentClassifier`, `HistoryRewritingService`, `AgentService`, and `AnsweringService`. It does not instantiate `ChatManager` and does not call the mobile endpoint.

## Stage parity

| Stage | Production implementation | Evaluation implementation |
|---|---|---|
| History source | `conversation_history.ProductionHistoryProvider`, backed by existing `DatabaseManager` session metadata | `core_adapter.history.EvaluationHistoryProvider`, backed only by completed `evaluation.run_turns` for an opaque `EvaluationConversationKey` |
| Normalizer | `AnsweringService._answer` → `PersianTextProcessor.normalize` → `normalize_persian_text` | Same `AnsweringService._answer` and same functions |
| Classifier | `AnsweringService._answer` → `IntentClassifier.classify_detailed` | Same call on the same classifier class/configuration |
| History formatting | `canonical_history_messages`, `format_rewrite_history`, `trim_agent_messages`, `select_answer_prompt_history`, `format_answer_prompt_history` in `conversation_history.py` | The same functions; provider supplies storage only |
| Rewrite | `HistoryRewritingService.rewrite_query` → canonical `RAGSystem.generate_text` | Same service and method |
| Embedding | `PersianHybridSearch._encode_query` → shared TEI embedding client | Same method/client and effective settings |
| Retrieval | `agent_graph.make_handle_general` → `RAGSystem.retrieve` → `PersianHybridSearch.search` → Qdrant/BM25 | Same graph node and methods |
| Reranker | FAQ related-question path in `agent_graph.make_handle_general` → `PersianHybridSearch.rerank` | Same conditional scope, method, threshold, and TEI endpoint |
| Context builder | `agent_graph.make_handle_general.prepare_context` → `RAGSystem.generate_context`; non-FAQ selection remains `search_results[:3]` | Same closure and method |
| Prompt builder | `agent_graph.recent_history_to_text` → shared history formatter; `RAGSystem.answer` builds the final category prompt | Same functions and prompt branches |
| Generator | `RAGSystem.answer` → `RAGSystem._completion` using the existing OpenAI-compatible vLLM client | Same method/client and generation arguments |
| Fallback handling | `NO_RETRIEVAL_RESULTS`, `LLM_CONTEXT_REFUSAL`, graph fallback state, and `answering_service.mobile_empty_answer_fallback` | Same graph state/reasons and same mobile-compatible fallback function |

## Permitted differences

Production resolves an external mobile session to an internal production session, records user/assistant query rows, and persists graph state through `ProductionHistoryProvider`. These surrounding mobile effects remain outside the shared semantic executor.

Evaluation supplies an `EvaluationConversationKey` containing `run_session_id`, `run_turn_id`, `turn_index`, and a random `evaluation_session_key`. It persists the exact graph state after a turn in that turn's evaluation metadata, then reconstructs the next turn from earlier completed turns in the same `run_session_id`. The imported `source_session_id` is never part of this key.

`EVALUATION_EXECUTION_POLICY` keeps evaluation state persistence enabled but disables real-chat, feedback, ticket, satisfaction, knowledge, and user-state writes. `enforce_history_policy` rejects a production provider before any lookup when that policy is active.

Production uses the observer default, for which `emit_pipeline_stage_lazy` does not materialize content. Evaluation binds `EvaluationTraceCollector`, so exact artifacts are materialized only for evaluation persistence. `RequestTrace` remains content-free.

## Proof tests

The acceptance tests use the exact sentinel `REAL_LOOKING_SESSION_12345`. They prove it remains importer/source metadata, evaluation rejects a production provider before its spy can execute, the evaluation adapter imports neither `ChatManager` nor `DatabaseManager`, and evaluation execution identity is a UUID key.

The shared-executor parity spy calls one `AnsweringService` instance once with a production provider and once with an evaluation provider, then verifies the same classifier, rewriter, agent, retrieval query, history representation, and result semantics were used. The core regression suites additionally characterize normalization/rewrite flow, one classifier call, graph invocation, TEI payload/index mapping, and one canonical reranker call.

## Deployment consequence

The current V1 includes shared-core changes loaded by the existing chat process. Deploying these shared files requires one normal chatbot process restart/redeploy to load them; no restart was performed during validation. Evaluation API/worker and static frontend deployment remain independent. Future frontend-only changes never require a chatbot restart. Future evaluation-only API/worker changes require restarting only the affected evaluation process, unless they also modify shared core files.

