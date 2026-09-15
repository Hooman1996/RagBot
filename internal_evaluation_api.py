"""Internal, persistence-free HTTP execution seam for RagBot evaluation."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, field_validator

from answering_service import AnswerRequestContext, AnswerResult
from conversation_history import (
    EVALUATION_EXECUTION_POLICY,
    ConversationSnapshot,
    canonical_history_messages,
    hydrate_agent_state,
    trim_agent_messages,
)
from new_architecture.app.config import Config
from pipeline_observer import (
    STAGE_ORDER,
    PipelineStage,
    PipelineStageResult,
    json_safe,
)
from utils.performance_config import PERFORMANCE_SETTINGS
from utils.retrieval_query_canonicalizer import (
    RETRIEVAL_QUERY_ALIASES_PATH,
    RETRIEVAL_QUERY_ALIASES_SCHEMA_VERSION,
    RETRIEVAL_QUERY_ALIASES_SHA256,
)
from utils.service_errors import InvalidRequestError, ServiceError


router = APIRouter(prefix="/api/internal/evaluation/v1", tags=["internal-evaluation"])

_SAFE_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_CANONICAL_STAGES = tuple(sorted(STAGE_ORDER, key=STAGE_ORDER.__getitem__))


class EvaluationTurnRequest(BaseModel):
    evaluation_session_key: UUID
    evaluation_turn_id: UUID
    turn_index: int = Field(ge=1)
    query: str
    documents: list[str] = Field(default_factory=list)
    agent_state_before: dict[str, Any] | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        return stripped


class EvaluationStageResponse(BaseModel):
    stage_name: str
    stage_order: int
    status: str
    input_hash: str | None = None
    output_hash: str | None = None
    duration_ms: float | None = None
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_data: dict[str, Any] | None = None


class EvaluationTurnResponse(BaseModel):
    status: Literal["COMPLETED", "ERROR"]
    evaluation_session_key: UUID
    evaluation_turn_id: UUID
    turn_index: int
    original_query: str
    answer: str | None = None
    normalized_query: str | None = None
    rewritten_query: str | None = None
    canonical_retrieval_query: str | None = None
    final_retrieval_query: str | None = None
    intent: str | None = None
    intent_details: dict[str, Any] = Field(default_factory=dict)
    related_questions: list[dict[str, str]] = Field(default_factory=list)
    feedback_needed: bool | None = None
    fallback_reason: str | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
    history_before: list[dict[str, str]] = Field(default_factory=list)
    history_after: list[dict[str, str]] = Field(default_factory=list)
    history_before_hash: str | None = None
    history_after_hash: str | None = None
    agent_state_after: dict[str, Any] | None = None
    infrastructure_error: bool
    error_code: str | None = None
    error_data: dict[str, Any] | None = None
    stages: list[EvaluationStageResponse]


class RuntimeSnapshotResponse(BaseModel):
    config_snapshot: dict[str, Any]
    git_commit_sha: str | None = None


class RequestLocalEvaluationHistory:
    """Conversation state held only for one internal evaluation request."""

    namespace = "evaluation"

    def __init__(
        self,
        *,
        evaluation_session_key: UUID,
        evaluation_turn_id: UUID,
        turn_index: int,
        agent_state_before: dict[str, Any] | None,
    ) -> None:
        self._session_key = evaluation_session_key
        self._turn_id = evaluation_turn_id
        self._turn_index = turn_index
        self._state_before = (
            json_safe(agent_state_before) if agent_state_before is not None else None
        )
        self._state_after: dict[str, Any] | None = None

    def _validate_key(self, conversation_key: object) -> None:
        if conversation_key != self._session_key:
            raise ValueError("evaluation conversation key mismatch")

    def _hydrated_state(self) -> dict[str, Any]:
        state = hydrate_agent_state(self._state_before, None)
        state["messages"] = canonical_history_messages(
            trim_agent_messages(list(state.get("messages") or []))
        )
        return state

    def lock_key(self, conversation_key: object) -> UUID:
        self._validate_key(conversation_key)
        return self._session_key

    async def load_rewrite_messages(
        self, conversation_key: object
    ) -> list[dict[str, str]]:
        self._validate_key(conversation_key)
        state = self._hydrated_state()
        return canonical_history_messages(
            trim_agent_messages(list(state.get("messages") or []))
        )

    async def load_snapshot(
        self, conversation_key: object
    ) -> ConversationSnapshot:
        self._validate_key(conversation_key)
        return ConversationSnapshot(
            conversation_key=self._session_key,
            actor_id=None,
            agent_state=self._hydrated_state(),
            metadata={
                "evaluation_turn_id": str(self._turn_id),
                "turn_index": self._turn_index,
            },
            version=self._turn_index - 1,
        )

    async def save_snapshot(
        self,
        snapshot: ConversationSnapshot,
        final_state: dict[str, Any],
    ) -> None:
        self._validate_key(snapshot.conversation_key)
        self._state_after = json_safe(final_state)

    @property
    def agent_state_after(self) -> dict[str, Any] | None:
        if self._state_after is None:
            return None
        return json_safe(self._state_after)


def _merge_dicts(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if left is None:
        return deepcopy(right)
    if right is None:
        return deepcopy(left)
    merged = deepcopy(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def safe_error_code(
    value: object, *, fallback: str = "EVALUATION_ERROR"
) -> str:
    candidate = str(value or "").upper()
    return candidate if _SAFE_ERROR_CODE.fullmatch(candidate) else fallback


class EvaluationTraceCollector:
    """Request-local trace collector matching the embedded evaluator's merge rules."""

    pipeline_hashes_enabled = True

    def __init__(self) -> None:
        self._records: dict[PipelineStage, PipelineStageResult] = {}

    def record(self, result: PipelineStageResult) -> None:
        detached = PipelineStageResult(
            stage=result.stage,
            status=result.status,
            input_data=(
                json_safe(result.input_data)
                if result.input_data is not None
                else None
            ),
            output_data=(
                json_safe(result.output_data)
                if result.output_data is not None
                else None
            ),
            metrics=json_safe(result.metrics),
            duration_ms=result.duration_ms,
            error_code=(
                safe_error_code(result.error_code)
                if result.error_code is not None
                else None
            ),
            error_data=(
                json_safe(result.error_data)
                if result.error_data is not None
                else None
            ),
        )
        previous = self._records.get(detached.stage)
        if previous is None:
            self._records[detached.stage] = detached
            return

        status = (
            "ERROR"
            if "ERROR" in {previous.status, detached.status}
            else (
                detached.status
                if detached.status != "COMPLETED"
                else previous.status
            )
        )
        durations = [
            value
            for value in (previous.duration_ms, detached.duration_ms)
            if value is not None
        ]
        self._records[detached.stage] = PipelineStageResult(
            stage=detached.stage,
            status=status,
            input_data=_merge_dicts(previous.input_data, detached.input_data),
            output_data=_merge_dicts(previous.output_data, detached.output_data),
            metrics=_merge_dicts(previous.metrics, detached.metrics) or {},
            duration_ms=max(durations) if durations else None,
            error_code=detached.error_code or previous.error_code,
            error_data=_merge_dicts(previous.error_data, detached.error_data),
        )

    @property
    def records(self) -> list[PipelineStageResult]:
        return sorted(self._records.values(), key=lambda item: item.stage_order)

    def get(self, stage: PipelineStage) -> PipelineStageResult | None:
        return self._records.get(stage)


def _ensure_all_stages(collector: EvaluationTraceCollector) -> None:
    present = {record.stage for record in collector.records}
    for stage in _CANONICAL_STAGES:
        if stage not in present:
            collector.record(
                PipelineStageResult(
                    stage=stage,
                    status="SKIPPED",
                    metrics={"reason": "NOT_APPLICABLE"},
                    duration_ms=0.0,
                )
            )


def _record_execution_error(
    collector: EvaluationTraceCollector, exc: Exception
) -> tuple[str, dict[str, str]]:
    code = safe_error_code(
        getattr(exc, "error_code", None),
        fallback="EVALUATION_TURN_ERROR",
    )
    present = {record.stage for record in collector.records}
    failed_stage = next(
        (stage for stage in _CANONICAL_STAGES if stage not in present),
        PipelineStage.GENERATION,
    )
    error_data = {"error_type": type(exc).__name__}
    collector.record(
        PipelineStageResult(
            stage=failed_stage,
            status="ERROR",
            error_code=code,
            error_data=error_data,
        )
    )
    _ensure_all_stages(collector)
    return code, error_data


def _is_infrastructure_error(exc: Exception) -> bool:
    if isinstance(exc, InvalidRequestError):
        return False
    return isinstance(
        exc,
        (
            ServiceError,
            asyncio.TimeoutError,
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    )


def _serialize_stages(
    collector: EvaluationTraceCollector,
) -> list[EvaluationStageResponse]:
    return [
        EvaluationStageResponse(
            stage_name=record.stage.value,
            stage_order=record.stage_order,
            status=record.status,
            input_hash=record.input_hash,
            output_hash=record.output_hash,
            duration_ms=record.duration_ms,
            input_data=record.input_data,
            output_data=record.output_data,
            metrics=record.metrics,
            error_code=record.error_code,
            error_data=record.error_data,
        )
        for record in collector.records
    ]


def _success_response(
    request: EvaluationTurnRequest,
    result: AnswerResult,
    provider: RequestLocalEvaluationHistory,
    collector: EvaluationTraceCollector,
) -> EvaluationTurnResponse:
    return EvaluationTurnResponse(
        status="COMPLETED",
        evaluation_session_key=request.evaluation_session_key,
        evaluation_turn_id=request.evaluation_turn_id,
        turn_index=request.turn_index,
        original_query=result.original_query,
        answer=result.answer,
        normalized_query=result.normalized_query,
        rewritten_query=result.rewritten_query,
        canonical_retrieval_query=result.canonical_retrieval_query,
        final_retrieval_query=result.final_retrieval_query,
        intent=result.intent,
        intent_details=json_safe(result.intent_details),
        related_questions=json_safe(result.related_questions),
        feedback_needed=result.feedback_needed,
        fallback_reason=result.fallback_reason,
        timings_ms=json_safe(result.timings_ms),
        history_before=json_safe(result.history_before),
        history_after=json_safe(result.history_after),
        history_before_hash=result.history_before_hash,
        history_after_hash=result.history_after_hash,
        agent_state_after=provider.agent_state_after,
        infrastructure_error=False,
        stages=_serialize_stages(collector),
    )


@router.post("/turn", response_model=EvaluationTurnResponse)
async def execute_evaluation_turn(
    payload: EvaluationTurnRequest, request: Request
) -> EvaluationTurnResponse:
    provider = RequestLocalEvaluationHistory(
        evaluation_session_key=payload.evaluation_session_key,
        evaluation_turn_id=payload.evaluation_turn_id,
        turn_index=payload.turn_index,
        agent_state_before=payload.agent_state_before,
    )
    collector = EvaluationTraceCollector()
    try:
        result = await request.app.state.answering_service.answer(
            AnswerRequestContext(
                original_query=payload.query,
                selected_documents=tuple(payload.documents),
                session_id=None,
                conversation_key=payload.evaluation_session_key,
                channel="evaluation",
                use_history=True,
                persist_agent_state=True,
                include_related_questions=True,
                timeout_seconds=(
                    PERFORMANCE_SETTINGS.application_request_timeout_seconds
                ),
                apply_mobile_empty_answer_fallback=True,
            ),
            history_provider=provider,
            observer=collector,
            execution_policy=EVALUATION_EXECUTION_POLICY,
        )
        if provider.agent_state_after is None:
            raise RuntimeError("evaluation state capture missing")
    except Exception as exc:
        error_code, error_data = _record_execution_error(collector, exc)
        return EvaluationTurnResponse(
            status="ERROR",
            evaluation_session_key=payload.evaluation_session_key,
            evaluation_turn_id=payload.evaluation_turn_id,
            turn_index=payload.turn_index,
            original_query=payload.query,
            infrastructure_error=_is_infrastructure_error(exc),
            error_code=error_code,
            error_data=error_data,
            stages=_serialize_stages(collector),
        )

    _ensure_all_stages(collector)
    return _success_response(payload, result, provider, collector)


def _sha(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _git_commit_sha(repository_root: Path | None = None) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except Exception:
        return None


def build_runtime_snapshot(
    *,
    answering_service: Any | None = None,
    selected_documents: list[str] | None = None,
) -> dict[str, Any]:
    """Capture effective, non-secret settings for the active RagBot runtime."""

    rag = getattr(getattr(answering_service, "agent_service", None), "rag_system", None)
    search_engine = getattr(rag, "search_engine", None)
    classifier = getattr(answering_service, "intent_classifier", None)
    rewriter = getattr(answering_service, "history_rewriting_service", None)
    rewrite_prompt = getattr(
        getattr(rewriter, "config", None), "QUERY_REWRITE_PROMPT", None
    )
    try:
        answer_method_source = (
            inspect.getsource(type(rag).answer) if rag is not None else None
        )
    except (AttributeError, OSError, TypeError):
        answer_method_source = None
    answer_prompt_source = "\n".join(
        filter(
            None,
            (
                answer_method_source,
                Config.CHITCHAT_SYSTEM_PROMPT,
                Config.CHITCHAT_USER_PROMPT,
                Config.DOCUMENT_RAG_SYSTEM_PROMPT,
                Config.DOCUMENT_RAG_USER_PROMPT,
                Config.GENERAL_RAG_SYSTEM_PROMPT,
                Config.GENERAL_RAG_USER_PROMPT,
            ),
        )
    )
    commit_sha = _git_commit_sha(Path(__file__).resolve().parent)
    return {
        "schema_version": "evaluation-config-v1",
        "intent": {
            "model_path_basename": getattr(classifier, "model_path_basename", None),
            "checkpoint_sha256": getattr(classifier, "checkpoint_sha256", None),
            "threshold": getattr(classifier, "threshold", None),
            "device": str(getattr(classifier, "device", "")) or None,
            "embedding_dimension": getattr(classifier, "embedding_dimension", None),
            "embedding_role": getattr(classifier, "embedding_role", None),
            "embedding_prompt_name": getattr(
                classifier, "embedding_prompt_name", None
            ),
        },
        "normalizer": {
            "identity": "PersianTextProcessor.normalize+normalize_persian_text",
            "version": None,
        },
        "query_canonicalization": {
            "RAG_QUERY_CANONICALIZATION_ENABLED": (
                PERFORMANCE_SETTINGS.rag_query_canonicalization_enabled
            ),
            "artifact_basename": RETRIEVAL_QUERY_ALIASES_PATH.name,
            "schema_version": RETRIEVAL_QUERY_ALIASES_SCHEMA_VERSION,
            "artifact_sha256": RETRIEVAL_QUERY_ALIASES_SHA256,
        },
        "rewrite": {
            "prompt_hash": _sha(rewrite_prompt),
            "prompt_version": None,
            "temperature": PERFORMANCE_SETTINGS.rag_rewrite_temperature,
            "top_p": PERFORMANCE_SETTINGS.rag_rewrite_top_p,
            "seed": PERFORMANCE_SETTINGS.rag_rewrite_seed,
            "max_tokens": PERFORMANCE_SETTINGS.rag_rewrite_max_tokens,
        },
        "embedding": {
            "model": os.getenv("EMBEDDING_MODEL"),
            "dimension": getattr(
                search_engine, "_expected_embedding_dimensions", 1024
            ),
        },
        "retrieval": {
            "top_k": PERFORMANCE_SETTINGS.rag_retrieval_top_k,
            "candidate_limit": PERFORMANCE_SETTINGS.rag_semantic_candidate_limit,
            "qdrant_collection": getattr(
                search_engine,
                "collection_name",
                os.getenv("QDRANT_COLLECTION", "hihelp_embeddings"),
            ),
            "knowledge_sources": list(selected_documents or []),
        },
        "rerank": {
            "model": os.getenv("RERANKER_MODEL"),
            "enabled": PERFORMANCE_SETTINGS.rag_context_rerank_enabled,
            "top_k": PERFORMANCE_SETTINGS.rag_context_rerank_top_k,
            "scope": "answer_context",
            "raw_scores": False,
            "related_questions": {
                "threshold": (
                    PERFORMANCE_SETTINGS.rag_related_questions_rerank_threshold
                ),
                "scope": "faq_related_questions",
            },
        },
        "generation": {
            "model": getattr(rag, "model_id", os.getenv("LLM_MODEL")),
            "temperature": PERFORMANCE_SETTINGS.rag_answer_temperature,
            "top_p": PERFORMANCE_SETTINGS.rag_answer_top_p,
            "seed": PERFORMANCE_SETTINGS.rag_answer_seed,
            "max_tokens": PERFORMANCE_SETTINGS.rag_max_new_tokens,
            "chitchat_temperature": PERFORMANCE_SETTINGS.rag_chitchat_temperature,
            "chitchat_top_p": PERFORMANCE_SETTINGS.rag_chitchat_top_p,
            "chitchat_seed": PERFORMANCE_SETTINGS.rag_chitchat_seed,
            "chitchat_max_tokens": (
                PERFORMANCE_SETTINGS.rag_chitchat_max_new_tokens
            ),
            "prompt_version": None,
            "answer_prompt_source_hash": _sha(answer_prompt_source),
            "per_turn_prompt_hash_stage": "PROMPT_BUILD",
        },
        "git_commit_sha": commit_sha,
    }


@router.get("/runtime-snapshot", response_model=RuntimeSnapshotResponse)
async def runtime_snapshot(
    request: Request,
    documents: Annotated[list[str] | None, Query()] = None,
) -> RuntimeSnapshotResponse:
    snapshot = build_runtime_snapshot(
        answering_service=request.app.state.answering_service,
        selected_documents=documents,
    )
    return RuntimeSnapshotResponse(
        config_snapshot=snapshot,
        git_commit_sha=snapshot.get("git_commit_sha"),
    )
