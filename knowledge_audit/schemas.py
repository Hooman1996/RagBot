"""Strict, versioned audit responsibilities. No answer or recommendation schema."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION = "coverage-rubric-2"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ScopeDecision(StrictModel):
    version: Literal["scope-1"]
    decision: Literal["kb_question", "chitchat", "out_of_scope", "private_account", "needs_context", "uncertain"]
    self_contained: bool
    context_sufficient: bool
    explanation: str = Field(max_length=600)


class Aspect(StrictModel):
    aspect_id: str = Field(pattern=r"^a[1-9][0-9]?$", max_length=3)
    description: str = Field(min_length=1, max_length=300)
    conditions: list[str] = Field(max_length=8)


class AspectChecklist(StrictModel):
    version: Literal["aspects-2"]
    aspects: list[Aspect] = Field(min_length=1, max_length=12)
    ambiguities: list[str] = Field(max_length=8)

    @field_validator("aspects")
    @classmethod
    def stable_ids(cls, aspects):
        if [a.aspect_id for a in aspects] != [f"a{i}" for i in range(1, len(aspects) + 1)]:
            raise ValueError("aspect_ids_must_be_sequential")
        return aspects


class SentenceReference(StrictModel):
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    faq_entry_id: str = Field(min_length=1, max_length=128)
    chunk_id: str = Field(min_length=1, max_length=128)
    sentence_number: int = Field(ge=1)


class Support(StrictModel):
    aspect_id: str
    entry_id: str
    citations: list[SentenceReference] = Field(min_length=1, max_length=12)
    applicability: Literal["applicable", "conditional", "uncertain"]
    conditions: list[str] = Field(max_length=8)
    dependencies: list[str] = Field(max_length=8)
    explanation: str = Field(max_length=500)


class BatchCoverage(StrictModel):
    version: Literal["batch-1"]
    coverage: Literal["full", "partial", "none", "uncertain"]
    supports: list[Support] = Field(max_length=60)
    unresolved_aspect_ids: list[str] = Field(max_length=12)
    conflicts: list[str] = Field(max_length=8)
    explanation: str = Field(max_length=700)


class CompatibilityDecision(StrictModel):
    version: Literal["reconciliation-1"]
    coverage: Literal["full", "partial", "none", "uncertain"]
    support_ids: list[str] = Field(max_length=60)
    supported_aspect_ids: list[str] = Field(max_length=12)
    unresolved_aspect_ids: list[str] = Field(max_length=12)
    compatible: bool
    conflicts: list[str] = Field(max_length=8)
    explanation: str = Field(max_length=700)


class VerificationDecision(StrictModel):
    version: Literal["verification-1"]
    verdict: Literal["accepted", "rejected", "uncertain"]
    supported_aspect_ids: list[str] = Field(max_length=12)
    unresolved_aspect_ids: list[str] = Field(max_length=12)
    explanation: str = Field(max_length=700)


SCHEMAS = {"scope": ScopeDecision, "aspects": AspectChecklist, "batch": BatchCoverage,
           "reconciliation": CompatibilityDecision, "verification": VerificationDecision}
