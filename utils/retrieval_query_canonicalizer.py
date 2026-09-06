"""Deterministic, query-only canonicalization for approved retrieval aliases."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Pattern

from utils.performance_config import PERFORMANCE_SETTINGS


RETRIEVAL_QUERY_ALIASES_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "config" / "retrieval_query_aliases.json"
)


@dataclass(frozen=True)
class _AliasRule:
    pattern: Pattern[str]
    replacement: str


def _load_alias_policy(path: Path) -> tuple[int, str, tuple[_AliasRule, ...]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid retrieval query alias artifact: {path}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("Retrieval query alias schema_version must be 1")
    aliases = payload.get("aliases")
    if not isinstance(aliases, list):
        raise RuntimeError("Retrieval query alias artifact must contain an aliases list")

    compiled: list[_AliasRule] = []
    for index, item in enumerate(aliases):
        if not isinstance(item, dict) or set(item) != {"pattern", "replacement"}:
            raise RuntimeError(f"Retrieval query alias {index} is malformed")
        pattern = item.get("pattern")
        replacement = item.get("replacement")
        if not isinstance(pattern, str) or not pattern:
            raise RuntimeError(f"Retrieval query alias {index} has an invalid pattern")
        if not isinstance(replacement, str) or not replacement:
            raise RuntimeError(
                f"Retrieval query alias {index} has an invalid replacement"
            )
        try:
            compiled_pattern = re.compile(pattern)
        except re.error as exc:
            raise RuntimeError(
                f"Retrieval query alias {index} has an invalid regex"
            ) from exc
        compiled.append(_AliasRule(compiled_pattern, replacement))

    return (
        int(payload["schema_version"]),
        hashlib.sha256(raw).hexdigest(),
        tuple(compiled),
    )


(
    RETRIEVAL_QUERY_ALIASES_SCHEMA_VERSION,
    RETRIEVAL_QUERY_ALIASES_SHA256,
    _APPROVED_ALIAS_RULES,
) = _load_alias_policy(RETRIEVAL_QUERY_ALIASES_PATH)


def canonicalize_retrieval_query(
    query: str, *, enabled: bool | None = None
) -> str:
    """Apply only version-controlled approved aliases to a normalized query."""

    if not isinstance(query, str):
        raise TypeError("retrieval query must be a string")
    if enabled is None:
        enabled = PERFORMANCE_SETTINGS.rag_query_canonicalization_enabled
    if not enabled:
        return query

    canonical = query
    for rule in _APPROVED_ALIAS_RULES:
        canonical = rule.pattern.sub(rule.replacement, canonical)
    return canonical
