"""Evaluation history provider backed only by evaluation.run_turns."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from conversation_history import (
    ConversationSnapshot,
    hydrate_agent_state,
)
from pipeline_observer import json_safe
from ..db.models import RunTurn
from .history_state import exact_agent_state_from_turns, exact_messages_from_turns

@dataclass(frozen=True)
class EvaluationConversationKey:
    run_session_id: uuid.UUID
    run_turn_id: uuid.UUID
    turn_index: int
    evaluation_session_key: uuid.UUID

    def __post_init__(self):
        if not isinstance(self.run_session_id, uuid.UUID):
            raise TypeError("run_session_id must be a UUID")
        if not isinstance(self.run_turn_id, uuid.UUID):
            raise TypeError("run_turn_id must be a UUID")
        if not isinstance(self.evaluation_session_key, uuid.UUID):
            raise TypeError("evaluation_session_key must be a UUID")
        if self.turn_index < 1:
            raise ValueError("turn_index must be positive")


class EvaluationHistoryProvider:
    namespace = "evaluation"

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._pending_states: dict[uuid.UUID, dict[str, Any]] = {}
        self._pending_lock = asyncio.Lock()

    @staticmethod
    def _key(value: object) -> EvaluationConversationKey:
        if not isinstance(value, EvaluationConversationKey):
            raise TypeError("evaluation execution requires EvaluationConversationKey")
        return value

    def lock_key(self, conversation_key: object) -> uuid.UUID:
        return self._key(conversation_key).run_session_id

    async def _previous_turns(self, key: EvaluationConversationKey) -> list[RunTurn]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(RunTurn)
                .where(
                    RunTurn.run_session_id == key.run_session_id,
                    RunTurn.turn_index < key.turn_index,
                    RunTurn.status == "COMPLETED",
                )
                .order_by(RunTurn.turn_index)
            )
            return list(rows)

    async def load_rewrite_messages(self, conversation_key: object) -> list[dict[str, str]]:
        key = self._key(conversation_key)
        return exact_messages_from_turns(await self._previous_turns(key))

    async def load_snapshot(self, conversation_key: object) -> ConversationSnapshot:
        key = self._key(conversation_key)
        previous = await self._previous_turns(key)
        last_state = exact_agent_state_from_turns(previous)
        state = hydrate_agent_state(last_state, None)
        return ConversationSnapshot(
            conversation_key=key,
            actor_id=None,
            agent_state=state,
            metadata={"run_turn_id": str(key.run_turn_id)},
            version=key.turn_index - 1,
        )

    async def save_snapshot(
        self, snapshot: ConversationSnapshot, final_state: dict[str, Any]
    ) -> None:
        key = self._key(snapshot.conversation_key)
        state = json_safe(final_state)
        async with self._pending_lock:
            self._pending_states[key.run_turn_id] = state

    async def pending_state(self, run_turn_id: uuid.UUID) -> dict[str, Any]:
        async with self._pending_lock:
            state = self._pending_states.get(run_turn_id)
            if state is None:
                raise RuntimeError("EVALUATION_PENDING_STATE_MISSING")
            return dict(state)

    async def discard_pending_state(self, run_turn_id: uuid.UUID) -> None:
        async with self._pending_lock:
            self._pending_states.pop(run_turn_id, None)
