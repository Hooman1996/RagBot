"""Pure helpers for restoring the exact graph state persisted per eval turn."""

from __future__ import annotations

from typing import Any

from conversation_history import canonical_history_messages, trim_agent_messages


def exact_agent_state_from_turns(turns: list[Any]) -> dict[str, Any] | None:
    """Return the last exact state; never synthesize client-only fallbacks."""

    if not turns:
        return None
    for turn in reversed(turns):
        metadata = turn.get("metadata") if isinstance(turn, dict) else turn.metadata_json
        candidate = (metadata or {}).get("agent_state_after")
        if isinstance(candidate, dict):
            state = dict(candidate)
            state["messages"] = canonical_history_messages(
                trim_agent_messages(list(state.get("messages") or []))
            )
            return state
    raise RuntimeError("EVALUATION_HISTORY_STATE_MISSING")


def exact_messages_from_turns(turns: list[Any]) -> list[dict[str, str]]:
    state = exact_agent_state_from_turns(turns)
    return list(state.get("messages") or []) if state is not None else []
