from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class DatabaseInitializeRequest(BaseModel):
    confirmation: str


class ManualStabilityRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=1000)
    repeat_count: int = Field(default=2, ge=2)
    documents: list[str] = Field(min_length=1)

    @field_validator("queries")
    @classmethod
    def validate_queries(cls, value: list[str]) -> list[str]:
        if not any(str(item).strip() for item in value):
            raise ValueError("at least one non-empty query is required")
        return value

    @field_validator("repeat_count")
    @classmethod
    def validate_repeat_max(cls, value: int) -> int:
        from ..config import get_settings

        if value > get_settings().repeat_max:
            raise ValueError("repeat count exceeds EVAL_REPEAT_MAX")
        return value


class RunCreateRequest(BaseModel):
    dataset_id: uuid.UUID
    run_type: Literal[
        "DATASET_INSPECTION", "STABILITY_QUERY", "STABILITY_SESSION", "STABILITY_DATASET"
    ]
    repeat_count: int = Field(default=1, ge=1)
    documents: list[str] = Field(min_length=1)

    @field_validator("repeat_count")
    @classmethod
    def validate_repeat_count(cls, value: int, info):
        from ..config import get_settings

        if value > get_settings().repeat_max:
            raise ValueError("repeat count exceeds EVAL_REPEAT_MAX")
        run_type = info.data.get("run_type", "")
        if str(run_type).startswith("STABILITY") and value < 2:
            raise ValueError("stability runs require at least two repetitions")
        if run_type == "DATASET_INSPECTION" and value != 1:
            raise ValueError("dataset inspection uses exactly one repetition")
        return value


class IdResponse(BaseModel):
    id: uuid.UUID
    status: str


class DeleteResponse(BaseModel):
    deleted: bool


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
