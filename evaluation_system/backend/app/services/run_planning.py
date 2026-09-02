"""Pure run-session planning shared by persistence and tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class RunSessionSpec:
    dataset_session_id: uuid.UUID
    repeat_index: int
    evaluation_session_key: uuid.UUID


class RunPlanError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_run_shape(
    run_type: str,
    repeat_count: int,
    session_turn_counts: list[int],
) -> None:
    if not session_turn_counts:
        raise RunPlanError("DATASET_HAS_NO_VALID_SESSIONS")
    if run_type == "DATASET_INSPECTION":
        if repeat_count != 1:
            raise RunPlanError("DATASET_INSPECTION_REQUIRES_ONE_REPEAT")
        return
    if not run_type.startswith("STABILITY") or repeat_count < 2:
        raise RunPlanError("STABILITY_REQUIRES_MULTIPLE_REPEATS")
    if run_type == "STABILITY_QUERY" and (
        len(session_turn_counts) != 1 or session_turn_counts[0] != 1
    ):
        raise RunPlanError("STABILITY_QUERY_REQUIRES_ONE_QUERY_SESSION")
    if run_type == "STABILITY_SESSION" and len(session_turn_counts) != 1:
        raise RunPlanError("STABILITY_SESSION_REQUIRES_ONE_SESSION")


def build_run_session_specs(
    dataset_session_ids: list[uuid.UUID], repeat_count: int
) -> list[RunSessionSpec]:
    if repeat_count < 1:
        raise ValueError("repeat_count must be positive")
    return [
        RunSessionSpec(
            dataset_session_id=dataset_session_id,
            repeat_index=repeat_index,
            evaluation_session_key=uuid.uuid4(),
        )
        for repeat_index in range(1, repeat_count + 1)
        for dataset_session_id in dataset_session_ids
    ]
