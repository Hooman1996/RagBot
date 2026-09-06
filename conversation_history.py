"""Shared conversation state/history contracts for production and evaluation.

This module intentionally contains the *only* formatting and trimming rules used
by the answer pipeline.  Storage providers supply messages and snapshots; they
must not reimplement these rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


NO_CONVERSATION_HISTORY = "[بدون مکالمه قبلی]"
MAX_STATE_MESSAGES = 10


@dataclass(frozen=True)
class ConversationSnapshot:
    conversation_key: object
    actor_id: int | None
    agent_state: dict[str, Any] | None
    metadata: dict[str, Any]
    version: int | None = None


@runtime_checkable
class ConversationHistoryProvider(Protocol):
    """Narrow storage seam consumed by the shared answering pipeline."""

    namespace: str

    def lock_key(self, conversation_key: object) -> object: ...

    async def load_rewrite_messages(
        self, conversation_key: object
    ) -> list[dict[str, str]]: ...

    async def load_snapshot(
        self, conversation_key: object
    ) -> ConversationSnapshot | None: ...

    async def save_snapshot(
        self,
        snapshot: ConversationSnapshot,
        final_state: dict[str, Any],
    ) -> None: ...


@dataclass(frozen=True)
class TurnExecutionPolicy:
    """Explicitly separates conversational computation from external effects."""

    persist_conversation_state: bool = True
    persist_real_chat_history: bool = True
    allow_feedback_writes: bool = True
    allow_ticket_writes: bool = True
    allow_satisfaction_writes: bool = True
    allow_knowledge_modifications: bool = True
    allow_user_state_modifications: bool = True


PRODUCTION_EXECUTION_POLICY = TurnExecutionPolicy()
EVALUATION_EXECUTION_POLICY = TurnExecutionPolicy(
    persist_conversation_state=True,
    persist_real_chat_history=False,
    allow_feedback_writes=False,
    allow_ticket_writes=False,
    allow_satisfaction_writes=False,
    allow_knowledge_modifications=False,
    allow_user_state_modifications=False,
)


def enforce_history_policy(
    provider: ConversationHistoryProvider | None,
    policy: TurnExecutionPolicy,
) -> None:
    if provider is None and not policy.persist_real_chat_history:
        raise RuntimeError("EVALUATION_HISTORY_PROVIDER_REQUIRED")
    if (
        provider is not None
        and getattr(provider, "namespace", None) == "production"
        and not policy.persist_real_chat_history
    ):
        raise RuntimeError("EVALUATION_PRODUCTION_HISTORY_FORBIDDEN")


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def trim_agent_messages(
    messages: list[dict[str, Any]], limit: int = MAX_STATE_MESSAGES
) -> list[dict[str, Any]]:
    """Preserve the production last-N state rule exactly."""

    if len(messages) > limit:
        return messages[-limit:]
    return messages


def canonical_history_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return the deterministic message representation consumed by the graph."""

    canonical: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", ""))
        content = str(message.get("content", ""))
        canonical.append({"role": role, "content": content})
    return canonical


def messages_from_turn_records(turns: list[Any]) -> list[dict[str, str]]:
    """Reconstruct the production message shape from completed turn records."""

    messages: list[dict[str, str]] = []
    for turn in turns:
        raw_query = turn["raw_query"] if isinstance(turn, dict) else turn.raw_query
        actual_answer = (
            turn.get("actual_answer")
            if isinstance(turn, dict)
            else turn.actual_answer
        )
        messages.append({"role": "user", "content": str(raw_query)})
        if actual_answer is not None:
            messages.append({"role": "assistant", "content": str(actual_answer)})
    return canonical_history_messages(trim_agent_messages(messages))


def format_rewrite_history(
    messages: list[dict[str, Any]], max_turns: int = 3
) -> str:
    """Format the most recent valid messages in authoritative chronology."""

    formatted_messages: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).lower()
        text = str(message.get("content", "")).strip()
        if not text or role not in {"user", "assistant", "ai", "model"}:
            continue
        speaker = "AI" if role in {"assistant", "ai", "model"} else "User"
        formatted_messages.append(f"{speaker}: {text}")

    if not formatted_messages:
        return NO_CONVERSATION_HISTORY
    recent_messages = (
        formatted_messages[-(max_turns * 2) :]
        if max_turns
        else formatted_messages
    )
    return "\n".join(recent_messages)


def select_answer_prompt_history(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select the exact prior-message slice used by production prompts."""

    return messages[-7:-1]


def format_answer_prompt_history(
    messages: list[dict[str, Any]], max_chars: int = 3000
) -> str:
    """Format prompt history with the exact Persian prefixes/tail truncation."""

    lines: list[str] = []
    for message in messages:
        prefix = "کاربر" if message["role"] == "user" else "دستیار"
        lines.append(f"{prefix}: {message['content']}")
    full_text = "\n".join(lines)
    if len(full_text) > max_chars:
        return "... " + full_text[-max_chars:]
    return full_text


def new_agent_state(actor_id: int | None) -> dict[str, Any]:
    return {
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
        "user_id": actor_id,
        "allowed_docs": [],
        "doc_category": None,
        "preclassified_intent": None,
        "related_questions": [],
        "fallback_reason": None,
    }


def hydrate_agent_state(
    existing: dict[str, Any] | None, actor_id: int | None
) -> dict[str, Any]:
    state = new_agent_state(actor_id)
    if isinstance(existing, dict):
        state.update(existing)
    state["messages"] = canonical_history_messages(
        list(state.get("messages") or [])
    )
    state["user_id"] = actor_id
    return state


class ProductionHistoryProvider:
    """Adapter preserving the current production session metadata behavior."""

    namespace = "production"

    def __init__(self, db_manager: Any, blocking_runner: Any):
        self._db_manager = db_manager
        self._blocking_runner = blocking_runner

    @staticmethod
    def _session_pk(conversation_key: object) -> int:
        if isinstance(conversation_key, bool):
            raise ValueError("invalid production conversation key")
        return int(str(conversation_key))

    def lock_key(self, conversation_key: object) -> int:
        return self._session_pk(conversation_key)

    async def load_rewrite_messages(
        self, conversation_key: object
    ) -> list[dict[str, str]]:
        session_pk = self._session_pk(conversation_key)
        row = await self._blocking_runner.run(
            self._db_manager.get_session_by_id, session_pk
        )
        if not row:
            return []
        metadata = _metadata_dict(row.get("meta_data", {}))
        state = metadata.get("agent_state", {})
        return canonical_history_messages(list(state.get("messages") or []))

    async def load_snapshot(
        self, conversation_key: object
    ) -> ConversationSnapshot | None:
        session_pk = self._session_pk(conversation_key)
        row = await self._blocking_runner.run(
            self._db_manager.get_session_by_id, session_pk
        )
        if not row:
            return None
        metadata = await self._blocking_runner.run(
            self._db_manager.get_session_metadata, session_pk
        )
        metadata = _metadata_dict(metadata)
        actor_id = int(row["user_id"])
        return ConversationSnapshot(
            conversation_key=conversation_key,
            actor_id=actor_id,
            agent_state=metadata.get("agent_state"),
            metadata=metadata,
        )

    async def save_snapshot(
        self,
        snapshot: ConversationSnapshot,
        final_state: dict[str, Any],
    ) -> None:
        session_pk = self._session_pk(snapshot.conversation_key)
        metadata = dict(snapshot.metadata)
        metadata["agent_state"] = final_state
        await self._blocking_runner.run(
            self._db_manager.update_session_metadata,
            session_pk,
            metadata,
            wait_for_completion_on_cancel=True,
        )
