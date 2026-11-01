# RagBot Evaluation V1 session execution

## Identity isolation

`source_session_id` is import metadata only. For every `(run, logical dataset session, repeat_index)`, the backend creates a fresh UUID `evaluation_session_key`. Every turn receives an `EvaluationConversationKey` containing only:

- evaluation `run_session_id` UUID;
- evaluation `run_turn_id` UUID;
- turn index;
- evaluation session key UUID.

The object has no source-session field. `EvaluationHistoryProvider` rejects any other key type and queries only `evaluation.run_turns` for that run session. The evaluation worker installs a rejecting default provider, so accidentally omitting the explicit evaluation provider fails closed instead of invoking production history.

## History reconstruction

Before turn N, the provider selects completed evaluation turns with `turn_index < N`, ordered ascending. It reconstructs:

```text
Q1 -> {role:user, content:Q1}
A1 -> {role:assistant, content:A1}
Q2 -> {role:user, content:Q2}
A2 -> {role:assistant, content:A2}
```

The last completed turn's `agent_state_after` value, stored inside that evaluation `run_turns` row, is the exact history authority. This matters for the mobile empty-answer fallback: production returns that fallback to the client but does not add it to graph history, so evaluation must not synthesize it into the next turn either. Missing persisted state after a completed turn fails as an evaluation infrastructure consistency error; it never falls back to production history.

The shared functions in `conversation_history.py` then apply the exact production rules:

- state retains the final ten messages;
- rewrite history globally deduplicates exact text regardless of role, applies the existing reversal heuristic, and keeps six messages;
- final prompt history uses `messages[-7:-1]`;
- final prompt history uses the existing Persian role prefixes and 3,000-character tail.

The same functions are called by production and evaluation. `run_turns.raw_query/actual_answer` remain the result ledger shown by the UI, while `run_turns.metadata.agent_state_after` is the exact conversation-state source for later turns. The evaluation provider stages the current state in process memory and the runner commits that state, answer, hashes, and stage artifacts in one `run_turns` transaction before advancing to the next turn.

`history_before_hash` hashes the canonical graph pre-turn message list. `history_after_hash` hashes the canonical graph post-turn list. Both use compact, sorted-key UTF-8 JSON and full SHA256.

## Shared execution sequence

Evaluation calls the existing `AnsweringService.answer` with the evaluation provider, observer, and policy. That same object performs production normalization, classifier inference, rewrite, datasource validation, AgentService/LangGraph invocation, retrieval, FAQ related-question reranking, context construction, prompt construction, vLLM generation, fallback, and state persistence.

Evaluation does not call `/api/mobile/v1/talk`, resolve a mobile session, provision a production user, or insert/update a production query.

`EVALUATION_EXECUTION_POLICY` disables production chat persistence, feedback writes, ticket writes, satisfaction writes, knowledge modification, and user-state modification. Evaluation conversation-state persistence remains enabled through its provider. Model/retrieval decisions are unchanged.

## Trace stages

The task-local `EvaluationTraceCollector` records:

1. `NORMALIZATION`
2. `INTENT`
3. `REWRITE`
4. `RETRIEVAL`
5. `RERANK`
6. `CONTEXT_SELECTION`
7. `PROMPT_BUILD`
8. `GENERATION`

Primary chunk reranking remains absent; the active rerank is the existing FAQ related-question rerank. Inapplicable stages are persisted as `SKIPPED`. Artifact capture is synchronous/in-memory and best-effort while decisions run; database writes occur afterward. Collector failure cannot change an answer. Full artifacts are never written to INFO logs or Redis.

## Bounded execution and repetitions

One Celery task orchestrates one run. A fixed worker set processes logical sessions up to `EVAL_SESSION_CONCURRENCY` (default 1). It never creates one task per dataset session; fatal worker errors cancel peers cleanly. Each session handler loops its turns sequentially.

All stability run types force concurrency 1. Every repetition has a fresh run-session row and evaluation key; no previous repetition rows match its provider query.

PostgreSQL stores durable run/session/turn/stage state. Redis carries only Celery delivery and content-free progress events. Redis event publication fails open and cannot fail a run.

The Celery task ID is stored in `runs.worker_task_id`. A duplicate/redelivered task may resume only when its task ID matches the durable claim; a different task cannot steal a live run. Already terminal sessions/turns are skipped, a stale in-progress turn increments `attempt_count` before regeneration, and unique `(run_session_id, turn_index)` constraints prevent duplicate turn rows. An operator-driven stale-run requeue can be added later using the heartbeat index; V1 does not expose an automatic or frontend recovery/reset action.

## Divergence

After a stability run, completed repetitions are grouped by logical dataset session and turn index. Stage output hashes are compared in pipeline order. The first unequal hash sets `first_divergent_turn` and `first_divergent_stage`. Variant sets/counts and fallback rate are stored in run-session metadata. A difference is called divergence; it is never automatically labeled incorrect or error.
