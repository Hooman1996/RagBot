"""HTTP contract for executing evaluations against a running RagBot."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _TransportModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class EvaluationTurnRequest(_TransportModel):
    evaluation_session_key: UUID
    evaluation_turn_id: UUID
    turn_index: int = Field(ge=1)
    query: str = Field(min_length=1)
    documents: list[str]
    agent_state_before: dict[str, Any] | None


class EvaluationStageResponse(_TransportModel):
    stage_name: str
    stage_order: int
    status: str
    input_hash: str | None
    output_hash: str | None
    duration_ms: float | None
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    metrics: dict[str, Any]
    error_code: str | None
    error_data: dict[str, Any] | None


class EvaluationTurnResponse(_TransportModel):
    status: Literal["COMPLETED", "ERROR"]
    evaluation_session_key: UUID
    evaluation_turn_id: UUID
    turn_index: int
    original_query: str
    answer: str | None
    normalized_query: str | None
    rewritten_query: str | None
    canonical_retrieval_query: str | None
    final_retrieval_query: str | None
    intent: str | None
    intent_details: dict[str, Any]
    related_questions: list[dict[str, str]]
    feedback_needed: bool | None
    fallback_reason: str | None
    timings_ms: dict[str, float]
    history_before: list[dict[str, str]]
    history_after: list[dict[str, str]]
    history_before_hash: str | None
    history_after_hash: str | None
    agent_state_after: dict[str, Any] | None
    infrastructure_error: bool
    error_code: str | None
    error_data: dict[str, Any] | None
    stages: list[EvaluationStageResponse]


class RuntimeSnapshotResponse(_TransportModel):
    config_snapshot: dict[str, Any]
    git_commit_sha: str | None


class RagBotDocument(_TransportModel):
    name: str
    category: str


class RagBotDatasourceResponse(_TransportModel):
    documents: list[RagBotDocument]
    count: int
    categories: list[str]


class RagBotClientError(RuntimeError):
    """Safe transport-boundary failure with no response or URL details."""

    def __init__(self, error_code: str, failure_kind: str) -> None:
        self.error_code = error_code
        self.infrastructure_error = error_code != "RAGBOT_REQUEST_REJECTED"
        self.error_data = {"failure_kind": failure_kind}
        super().__init__(f"RagBot evaluation request failed: {error_code}")


class RagBotEvaluationClient:
    TURN_PATH = "/api/internal/evaluation/v1/turn"
    SNAPSHOT_PATH = "/api/internal/evaluation/v1/runtime-snapshot"
    DATASOURCES_PATH = "/api/documents"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 70.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_url = base_url.strip().rstrip("/")
        if not normalized_url:
            raise ValueError("EVAL_RAGBOT_BASE_URL must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("EVAL_RAGBOT_HTTP_TIMEOUT_SECONDS must be positive")
        self._client = httpx.AsyncClient(
            base_url=normalized_url,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    async def __aenter__(self) -> "RagBotEvaluationClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ):
            raise RagBotClientError("RAGBOT_TIMEOUT", "timeout") from None
        except httpx.TransportError:
            raise RagBotClientError("RAGBOT_UNAVAILABLE", "connection") from None
        if response.status_code >= 500:
            raise RagBotClientError("RAGBOT_UNAVAILABLE", "upstream_5xx")
        if response.status_code == 422:
            raise RagBotClientError("RAGBOT_REQUEST_REJECTED", "request_contract")
        if response.is_error:
            raise RagBotClientError("RAGBOT_INVALID_RESPONSE", "unexpected_http_status")
        try:
            return response.json()
        except ValueError:
            raise RagBotClientError("RAGBOT_INVALID_RESPONSE", "malformed_json") from None

    @staticmethod
    def _parse(model: type[_TransportModel], payload: Any) -> Any:
        try:
            return model.model_validate(payload)
        except ValidationError:
            raise RagBotClientError("RAGBOT_INVALID_RESPONSE", "schema_validation") from None

    async def evaluate_turn(
        self,
        *,
        evaluation_session_key: UUID,
        evaluation_turn_id: UUID,
        turn_index: int,
        query: str,
        documents: list[str],
        agent_state_before: dict[str, Any] | None,
    ) -> EvaluationTurnResponse:
        request = EvaluationTurnRequest(
            evaluation_session_key=evaluation_session_key,
            evaluation_turn_id=evaluation_turn_id,
            turn_index=turn_index,
            query=query,
            documents=documents,
            agent_state_before=agent_state_before,
        )
        payload = await self._get_json(
            "POST", self.TURN_PATH, json=request.model_dump(mode="json")
        )
        result = self._parse(EvaluationTurnResponse, payload)
        if (
            result.evaluation_session_key != evaluation_session_key
            or result.evaluation_turn_id != evaluation_turn_id
            or result.turn_index != turn_index
        ):
            raise RagBotClientError("RAGBOT_INVALID_RESPONSE", "identity_mismatch")
        return result

    async def runtime_snapshot(
        self, documents: list[str]
    ) -> RuntimeSnapshotResponse:
        payload = await self._get_json(
            "GET",
            self.SNAPSHOT_PATH,
            params=[("documents", document) for document in documents],
        )
        return self._parse(RuntimeSnapshotResponse, payload)

    async def list_datasources(self) -> RagBotDatasourceResponse:
        payload = await self._get_json("GET", self.DATASOURCES_PATH)
        result = self._parse(RagBotDatasourceResponse, payload)
        if result.count != len(result.documents):
            raise RagBotClientError("RAGBOT_INVALID_RESPONSE", "datasource_count_mismatch")
        return result
