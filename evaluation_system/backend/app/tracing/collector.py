"""In-memory per-turn collector; persistence happens after pipeline decisions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pipeline_observer import PipelineStage, PipelineStageResult, json_safe
from ..services.events import safe_error_code


def _merge(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any] | None:
    if left is None:
        return deepcopy(right)
    if right is None:
        return deepcopy(left)
    merged = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


class EvaluationTraceCollector:
    def __init__(self):
        self._records: dict[PipelineStage, PipelineStageResult] = {}
        self.capture_failed = False

    def record(self, result: PipelineStageResult) -> None:
        result = PipelineStageResult(
            stage=result.stage,
            status=result.status,
            input_data=json_safe(result.input_data) if result.input_data is not None else None,
            output_data=json_safe(result.output_data) if result.output_data is not None else None,
            metrics=json_safe(result.metrics),
            duration_ms=result.duration_ms,
            error_code=(
                safe_error_code(result.error_code)
                if result.error_code is not None
                else None
            ),
            error_data=json_safe(result.error_data) if result.error_data is not None else None,
        )
        previous = self._records.get(result.stage)
        if previous is None:
            self._records[result.stage] = result
            return
        status = "ERROR" if "ERROR" in {previous.status, result.status} else (
            result.status if result.status != "COMPLETED" else previous.status
        )
        durations = [value for value in (previous.duration_ms, result.duration_ms) if value is not None]
        self._records[result.stage] = PipelineStageResult(
            stage=result.stage,
            status=status,
            input_data=_merge(previous.input_data, result.input_data),
            output_data=_merge(previous.output_data, result.output_data),
            metrics=_merge(previous.metrics, result.metrics) or {},
            duration_ms=max(durations) if durations else None,
            error_code=result.error_code or previous.error_code,
            error_data=_merge(previous.error_data, result.error_data),
        )

    @property
    def records(self) -> list[PipelineStageResult]:
        return sorted(self._records.values(), key=lambda item: item.stage_order)

    def get(self, stage: PipelineStage) -> PipelineStageResult | None:
        return self._records.get(stage)
