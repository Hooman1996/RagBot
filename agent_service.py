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

@dataclass
class AgentTurnResult:
    answer: Optional[str]
    state: dict[str, Any]


class AgentService:
    def __init__(self, rag_system, intent_classifier, scenarios_db,
                 db_manager: DatabaseManager, chat_manager: ChatManager,
                 blocking_runner: BoundedBlockingRunner | None = None,
                 category_resolver=None):
        self.rag_system = rag_system
        self.intent_classifier = intent_classifier
        self.scenarios_db = scenarios_db
        self.db_manager = db_manager
        self.chat_manager = chat_manager
        self.blocking_runner = blocking_runner or BoundedBlockingRunner()
        self.category_resolver = category_resolver

        # Build graph without any checkpointer
        self.graph = build_graph(
            intent_classifier=intent_classifier,
            scenarios_db=scenarios_db,
            rag_system=rag_system,
            chat_manager=chat_manager
        )
        self._session_locks: dict[str, asyncio.Lock] = {}

    async def process_message(
        self,
        session_id: str,
        user_message: str,
        selected_docs: List[str] = None,
        retrieval_query: Optional[str] = None,
        preclassified_intent: Optional[dict] = None,
        doc_category: Optional[str] = None,
    ) -> Optional[str]:
        result = await self.process_message_detailed(
            session_id,
            user_message,
            selected_docs=selected_docs,
            retrieval_query=retrieval_query,
            preclassified_intent=preclassified_intent,
            doc_category=doc_category,
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
    ) -> AgentTurnResult:
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            return await self._process_message(
                session_id,
                user_message,
                selected_docs=selected_docs,
                retrieval_query=retrieval_query,
                preclassified_intent=preclassified_intent,
                doc_category=doc_category,
            )

    async def _process_message(
        self,
        session_id: str,
        user_message: str,
        selected_docs: List[str] = None,
        retrieval_query: Optional[str] = None,
        preclassified_intent: Optional[dict] = None,
        doc_category: Optional[str] = None,
    ) -> AgentTurnResult:
        if not user_message.strip():
            return AgentTurnResult(answer=None, state={})

        if selected_docs is None:
            selected_docs = []

        if doc_category is None and selected_docs and self.category_resolver:
            doc_category = self.category_resolver(selected_docs[0])

        session_pk = int(session_id)

        # 1. Get user_id from the session row
        session_row = await self.blocking_runner.run(
            self.db_manager.get_session_by_id, session_pk
        )
        if not session_row:
            return AgentTurnResult(answer=None, state={})
        user_id = session_row["user_id"]

        # 2. Load previous agent state from meta_data
        meta = await self.blocking_runner.run(
            self.db_manager.get_session_metadata, session_pk
        )
        state = meta.get("agent_state", None)

        if state is None:
            # Fresh state
            state = {
                "messages": [],
                "latest_user_input": "",
                "retrieval_query": "",
                "intent": {},
                "current_scenario": None,
                "slots": {},
                "remaining_slots": [],
                "pending_question": None,
                "answer": None,
                "last_answer": None,
                "feedback_needed": False,
                "asked_feedback": False,
                "ticket_submitted": False,
                "user_id": user_id,
                "allowed_docs": [],
                "doc_category": None,
                "preclassified_intent": None,
            }
        else:
            defaults = {
                "messages": [],
                "latest_user_input": "",
                "retrieval_query": "",
                "intent": {},
                "current_scenario": None,
                "slots": {},
                "remaining_slots": [],
                "pending_question": None,
                "answer": None,
                "last_answer": None,
                "feedback_needed": False,
                "asked_feedback": False,
                "ticket_submitted": False,
                "preclassified_intent": None,
            }
            for k, v in defaults.items():
                if k not in state:
                    state[k] = v
            state["user_id"] = user_id

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
        if final_state.get("ticket_submitted"):
            await self.blocking_runner.run(
                self._create_ticket,
                user_id=user_id,
                session_id=session_id,
                wait_for_completion_on_cancel=True,
            )

        # 8. Trim state again (just in case) before storing
        final_state["messages"] = final_state["messages"][-10:]

        # 9. Save into meta_data
        meta["agent_state"] = final_state
        async with trace_span("persistence"):
            await self.blocking_runner.run(
                self.db_manager.update_session_metadata,
                session_pk,
                meta,
                wait_for_completion_on_cancel=True,
            )
        return AgentTurnResult(answer=answer, state=final_state)

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
        state = {
            "messages": [],
            "latest_user_input": user_message,
            "retrieval_query": retrieval_query or user_message,
            "intent": {},
            "preclassified_intent": preclassified_intent,
            "current_scenario": None,
            "slots": {},
            "remaining_slots": [],
            "pending_question": None,
            "answer": None,
            "last_answer": None,
            "feedback_needed": False,
            "asked_feedback": False,
            "ticket_submitted": False,
            "user_id": None,
            "allowed_docs": documents,
            "doc_category": doc_category,
            "related_questions": [],
        }
        final_state = await self.graph.ainvoke(state)
        answer = None
        messages = final_state.get("messages", [])
        if messages and messages[-1].get("role") == "assistant":
            answer = messages[-1].get("content")
        return AgentTurnResult(answer=answer, state=final_state)

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
