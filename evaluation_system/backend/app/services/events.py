"""Content-free Redis Stream event transport; PostgreSQL remains authoritative."""

from __future__ import annotations

import json
import re
from typing import Any


ALLOWED_EVENT_FIELDS = frozenset({
    "run_id", "run_session_id", "run_turn_id", "status", "stage_name",
    "completed_sessions", "total_sessions", "completed_turns", "total_turns",
    "duration_ms", "error_code",
})
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


def safe_error_code(value: object, *, fallback: str = "EVALUATION_ERROR") -> str:
    candidate = str(value or "").upper()
    return candidate if _SAFE_CODE.fullmatch(candidate) else fallback


class EvaluationEventBus:
    def __init__(self, redis_client, *, maxlen: int = 5000, ttl_seconds: int = 86400):
        self.redis = redis_client
        self.maxlen = maxlen
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def stream_key(run_id: object) -> str:
        return f"evaluation:run:{run_id}:events"

    async def publish(self, run_id: object, event: str, payload: dict[str, Any]) -> str:
        safe = {key: value for key, value in payload.items() if key in ALLOWED_EVENT_FIELDS}
        if "error_code" in safe and safe["error_code"] is not None:
            safe["error_code"] = safe_error_code(safe["error_code"])
        key = self.stream_key(run_id)
        try:
            event_id = await self.redis.xadd(
                key,
                {"event": event, "data": json.dumps(safe, separators=(",", ":"))},
                maxlen=self.maxlen,
                approximate=True,
            )
            await self.redis.expire(key, self.ttl_seconds)
            return event_id.decode() if isinstance(event_id, bytes) else str(event_id)
        except Exception:
            # Redis transports progress only. PostgreSQL execution must continue.
            return "0-0"


class NoOpEventBus:
    async def publish(self, run_id: object, event: str, payload: dict[str, Any]) -> str:
        del run_id, event, payload
        return "0-0"
