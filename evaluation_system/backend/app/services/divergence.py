"""Deterministic stability comparison; divergence is not correctness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pipeline_observer import PipelineStage, STAGE_ORDER


ORDERED_STAGES = tuple(sorted(PipelineStage, key=STAGE_ORDER.get))


@dataclass(frozen=True)
class ComparableTurn:
    run_session_id: object
    logical_session_id: object
    repeat_index: int
    turn_index: int
    stage_outputs: dict[str, str | None]
    normalized_query: str | None
    intent: str | None
    rewritten_query: str | None
    context_hash: str | None
    answer_hash: str | None
    fallback_used: bool
    completed: bool = True
    prompt_hash: str | None = None


@dataclass
class StabilitySummary:
    first_divergent_turn: int | None = None
    first_divergent_stage: str | None = None
    fallback_count: int = 0
    total_turns: int = 0
    incomparable_turn_count: int = 0
    variants: dict[str, set[str]] = field(default_factory=lambda: {
        "normalization": set(), "intent": set(), "rewrite": set(),
        "retrieval": set(), "rerank": set(), "context": set(),
        "prompt": set(), "answer": set(),
    })

    def as_dict(self) -> dict[str, Any]:
        return {
            "first_divergent_turn": self.first_divergent_turn,
            "first_divergent_stage": self.first_divergent_stage,
            "fallback_count": self.fallback_count,
            "fallback_rate": self.fallback_count / self.total_turns if self.total_turns else 0.0,
            "incomparable_turn_count": self.incomparable_turn_count,
            "unique_variants": {key: sorted(values) for key, values in self.variants.items()},
            "variant_counts": {key: len(values) for key, values in self.variants.items()},
        }


def analyze_stability(turns: list[ComparableTurn]) -> dict[object, StabilitySummary]:
    logical_groups: dict[object, list[ComparableTurn]] = {}
    for turn in turns:
        logical_groups.setdefault(turn.logical_session_id, []).append(turn)
    summaries: dict[object, StabilitySummary] = {}
    for logical_id, group in logical_groups.items():
        summary = StabilitySummary()
        summary.total_turns = len(group)
        summary.fallback_count = sum(turn.fallback_used for turn in group)
        completed_group = [turn for turn in group if turn.completed]
        summary.incomparable_turn_count = len(group) - len(completed_group)
        for turn in completed_group:
            value_map = {
                "normalization": turn.normalized_query,
                "intent": turn.intent,
                "rewrite": turn.rewritten_query,
                "retrieval": turn.stage_outputs.get("RETRIEVAL"),
                "rerank": turn.stage_outputs.get("RERANK"),
                "context": turn.context_hash,
                "prompt": turn.prompt_hash or turn.stage_outputs.get("PROMPT_BUILD"),
                "answer": turn.answer_hash,
            }
            for key, value in value_map.items():
                summary.variants[key].add(value if value is not None else "<null>")

        by_turn: dict[int, list[ComparableTurn]] = {}
        for turn in completed_group:
            by_turn.setdefault(turn.turn_index, []).append(turn)
        for turn_index in sorted(by_turn):
            repetitions = by_turn[turn_index]
            if len(repetitions) < 2:
                continue
            for stage in ORDERED_STAGES:
                values = {item.stage_outputs.get(stage.value) for item in repetitions}
                if len(values) > 1:
                    summary.first_divergent_turn = turn_index
                    summary.first_divergent_stage = stage.value
                    break
            if summary.first_divergent_stage is not None:
                break
        summaries[logical_id] = summary
    return summaries
