"""
Thin service layer that runs the LangGraph agent for each user turn.
State is persisted in chat_sessions.meta_data (JSON), so no external
checkpointer is needed. The message list is kept small.
"""
from typing import List
import asyncio
import json
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass

from agent_graph import build_graph, AgentState
from new_architecture.app.services.history.database import DatabaseManager, ChatManager
from utils.concurrency import BoundedBlockingRunner
from utils.request_instrumentation import trace_span
from conversation_history import (
    PRODUCTION_EXECUTION_POLICY,
    ConversationHistoryProvider,
    ProductionHistoryProvider,
    TurnExecutionPolicy,
    enforce_history_policy,
    hydrate_agent_state,
    new_agent_state,
    trim_agent_messages,
)

@dataclass
class AgentTurnResult:
    answer: Optional[str]
    state: dict[str, Any]
    history_before: list[dict[str, str]] | None = None


class AgentService:
    def __init__(self, rag_system, intent_classifier, scenarios_db,
                 db_manager: DatabaseManager, chat_manager: ChatManager,
                 blocking_runner: BoundedBlockingRunner | None = None,
                 category_resolver=None,
                 history_provider: ConversationHistoryProvider | None = None):
        self.rag_system = rag_system
        self.intent_classifier = intent_classifier
        self.scenarios_db = scenarios_db
        self.db_manager = db_manager
        self.chat_manager = chat_manager
        self.blocking_runner = blocking_runner or BoundedBlockingRunner()
        self.category_resolver = category_resolver
        self.history_provider = history_provider or ProductionHistoryProvider(
            db_manager, self.blocking_runner
        )

        # Build graph without any checkpointer
        self.graph = build_graph(
            intent_classifier=intent_classifier,
            scenarios_db=scenarios_db,
            rag_system=rag_system,
            chat_manager=chat_manager
        )
        self._session_locks: dict[tuple[str, object], asyncio.Lock] = {}

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        selected_docs: List[str] = None,
        retrieval_query: Optional[str] = None,
        preclassified_intent: Optional[dict] = None,
        doc_category: Optional[str] = None,
        history_provider: ConversationHistoryProvider | None = None,
        execution_policy: TurnExecutionPolicy = PRODUCTION_EXECUTION_POLICY,
    ) -> Optional[str]:
        result = await self.process_message_detailed(
            session_id,
            user_message,
            selected_docs=selected_docs,
            retrieval_query=retrieval_query,
            preclassified_intent=preclassified_intent,
            doc_category=doc_category,
            history_provider=history_provider,
            execution_policy=execution_policy,
        )
        return result.answer

    async def process_message_detailed(
        self,
        session_id: str,
        user_message: str,
        selected_docs: List[str] = None,
        retrieval_query: Optional[str] = None,
        preclassified_intent: Optional[dict] = None,
        doc_category: Optional[str] = None,
        history_provider: ConversationHistoryProvider | None = None,
        execution_policy: TurnExecutionPolicy = PRODUCTION_EXECUTION_POLICY,
    ) -> AgentTurnResult:
        provider = history_provider or self.history_provider
        enforce_history_policy(provider, execution_policy)
        provider_lock_key = getattr(provider, "lock_key", None)
        conversation_lock_key = (
            provider_lock_key(session_id)
            if callable(provider_lock_key)
            else session_id
        )
        lock_key = (provider.namespace, conversation_lock_key)
        lock = self._session_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            return await self._process_message(
                session_id,
                user_message,
                selected_docs=selected_docs,
                retrieval_query=retrieval_query,
                preclassified_intent=preclassified_intent,
                doc_category=doc_category,
                history_provider=provider,
                execution_policy=execution_policy,
            )

    async def _process_message(
        self,
        session_id: str,
        user_message: str,
        selected_docs: List[str] = None,
        retrieval_query: Optional[str] = None,
        preclassified_intent: Optional[dict] = None,
        doc_category: Optional[str] = None,
        history_provider: ConversationHistoryProvider | None = None,
        execution_policy: TurnExecutionPolicy = PRODUCTION_EXECUTION_POLICY,
    ) -> AgentTurnResult:
        if not user_message.strip():
            return AgentTurnResult(answer=None, state={})

        if selected_docs is None:
            selected_docs = []

        if doc_category is None and selected_docs and self.category_resolver:
            doc_category = self.category_resolver(selected_docs[0])

        provider = history_provider or self.history_provider
        enforce_history_policy(provider, execution_policy)
        snapshot = await provider.load_snapshot(session_id)
        if snapshot is None:
            return AgentTurnResult(answer=None, state={})
        user_id = snapshot.actor_id
        state = hydrate_agent_state(snapshot.agent_state, user_id)
        history_before = [dict(message) for message in state["messages"]]

        state["allowed_docs"] = selected_docs
        state["doc_category"] = doc_category

        # 3. Cancel any pending satisfaction prompt when a new message arrives
        if state.get("feedback_needed"):
            state["feedback_needed"] = False
            state["asked_feedback"] = False

        # 4. Inject the new user message
        state["latest_user_input"] = user_message
        state["retrieval_query"] = retrieval_query or user_message
        state["preclassified_intent"] = preclassified_intent
        state["fallback_reason"] = None

        # 5. Run the graph (modifies the state dict)
        final_state = await self.graph.ainvoke(state)   # was: self.graph.invoke(state)

        # 6. Extract assistant reply
        answer = None
        messages = final_state.get("messages", [])
        if messages:
            last = messages[-1]
            if last.get("role") == "assistant":
                answer = last["content"]

        # 7. If a ticket was requested
        if (
            final_state.get("ticket_submitted")
            and execution_policy.allow_ticket_writes
        ):
            await self.blocking_runner.run(
                self._create_ticket,
                user_id=user_id,
                session_id=session_id,
                wait_for_completion_on_cancel=True,
            )

        # 8. Trim state again (just in case) before storing
        final_state["messages"] = trim_agent_messages(
            final_state["messages"]
        )

        # 9. Save through the selected provider. Evaluation providers never
        # receive a production DatabaseManager/ChatManager write dependency.
        if execution_policy.persist_conversation_state:
            async with trace_span("persistence"):
                await provider.save_snapshot(snapshot, final_state)
        return AgentTurnResult(
            answer=answer, state=final_state, history_before=history_before
        )

    async def process_stateless_message(
        self,
        *,
        user_message: str,
        selected_docs: List[str] = None,
        retrieval_query: Optional[str] = None,
        preclassified_intent: Optional[dict] = None,
        doc_category: Optional[str] = None,
    ) -> AgentTurnResult:
        """Run one isolated turn without reading or writing chat records."""
        if not user_message.strip():
            return AgentTurnResult(answer=None, state={})
        documents = list(selected_docs or [])
        if doc_category is None and documents and self.category_resolver:
            doc_category = self.category_resolver(documents[0])
        state = new_agent_state(None)
        state.update({
            "latest_user_input": user_message,
            "retrieval_query": retrieval_query or user_message,
            "preclassified_intent": preclassified_intent,
            "allowed_docs": documents,
            "doc_category": doc_category,
        })
        final_state = await self.graph.ainvoke(state)
        answer = None
        messages = final_state.get("messages", [])
        if messages and messages[-1].get("role") == "assistant":
            answer = messages[-1].get("content")
        return AgentTurnResult(
            answer=answer, state=final_state, history_before=[]
        )

    def _create_ticket(self, user_id: int, session_id: str):
        """Insert a new support ticket into the database."""
        try:
            now = datetime.utcnow()
            self.db_manager._execute(
                """
                INSERT INTO tickets (user_id, session_id, status, created_at, updated_at)
                VALUES (%s, %s, 'open', %s, %s)
                """,
                (user_id, int(session_id), now, now)
            )
        except Exception:
            raise
