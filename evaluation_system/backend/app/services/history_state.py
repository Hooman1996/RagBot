"""Restore the exact opaque RagBot state persisted by completed eval turns."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def exact_agent_state_from_turns(turns: list[Any]) -> dict[str, Any] | None:
    """Return a detached copy of the latest exact state, without interpreting it."""

    if not turns:
        return None
    for turn in reversed(turns):
        metadata = (
            turn.get("metadata")
            if isinstance(turn, dict)
            else turn.metadata_json
        )
        candidate = (metadata or {}).get("agent_state_after")
        if isinstance(candidate, dict):
            return deepcopy(candidate)
    raise RuntimeError("EVALUATION_HISTORY_STATE_MISSING")
