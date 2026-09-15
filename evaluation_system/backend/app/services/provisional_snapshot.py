"""Minimal run-creation snapshot pending an authoritative RagBot snapshot."""

from __future__ import annotations


def build_provisional_snapshot(documents: list[str]) -> dict[str, object]:
    """Preserve requested source order without inspecting the RagBot runtime."""

    return {
        "schema_version": "evaluation-pending-v1",
        "retrieval": {"knowledge_sources": list(documents)},
        "runtime_snapshot_pending": True,
    }
