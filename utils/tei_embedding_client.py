"""Shared, policy-explicit client for the TEI embedding service."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import httpx

from utils.service_errors import ServiceProtocolError
from utils.persian_normalization import normalize_persian_text


EMBEDDING_DIMENSION = 1024
QUERY_PROMPT_NAME = "query"


def build_query_payload(query: str) -> dict[str, Any]:
    """Build the measured query-role request without a manual text prefix."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    normalized_query = normalize_persian_text(query)
    if not normalized_query:
        raise ValueError("query must be non-empty after normalization")
    return {
        "inputs": normalized_query,
        "prompt_name": QUERY_PROMPT_NAME,
        "normalize": True,
    }


def build_document_payload(documents: Sequence[str]) -> dict[str, Any]:
    """Build a raw-document request compatible with the existing collection."""
    if isinstance(documents, (str, bytes)) or not isinstance(
        documents, Sequence
    ):
        raise TypeError("documents must be a sequence of strings")
    document_list = list(documents)
    for index, document in enumerate(document_list):
        if not isinstance(document, str) or not document.strip():
            raise ValueError(
                f"document at index {index} must be a non-empty string"
            )
    return {"inputs": document_list, "normalize": True}


def validate_embedding_response(
    payload: Any,
    *,
    expected_count: int,
    expected_dimension: int = EMBEDDING_DIMENSION,
) -> list[list[float]]:
    """Validate TEI's list-of-vectors response without renormalizing it."""
    if (
        not isinstance(payload, list)
        or len(payload) != expected_count
        or any(not isinstance(vector, list) for vector in payload)
    ):
        raise ServiceProtocolError(
            "Embedding service returned an invalid response shape"
        )

    validated: list[list[float]] = []
    for vector_index, vector in enumerate(payload):
        if len(vector) != expected_dimension:
            raise ServiceProtocolError(
                "Embedding service returned vector "
                f"{vector_index} with dimension {len(vector)}; "
                f"expected {expected_dimension}"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in vector
        ):
            raise ServiceProtocolError(
                "Embedding service returned a non-finite or non-numeric value"
            )
        validated.append([float(value) for value in vector])
    return validated


class TeiEmbeddingClient:
    """Async TEI client with separate query and stored-document policies.

    Query text uses ``prompt_name="query"``. Stored documents intentionally
    use raw text with no prompt so new vectors remain compatible with the
    existing Qdrant collection.
    """

    def __init__(
        self,
        base_url: str,
        http_client: httpx.AsyncClient,
        *,
        expected_dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("TEI embedding URL must be present")
        if expected_dimension < 1:
            raise ValueError("expected embedding dimension must be positive")
        self.base_url = base_url.rstrip("/")
        self._http = http_client
        self.expected_dimension = expected_dimension

    async def embed_query(self, query: str) -> list[float]:
        response = await self._http.post(
            f"{self.base_url}/embed",
            json=build_query_payload(query),
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceProtocolError(
                "Embedding service returned invalid JSON"
            ) from exc
        return validate_embedding_response(
            payload,
            expected_count=1,
            expected_dimension=self.expected_dimension,
        )[0]

    async def embed_documents(
        self, documents: Sequence[str]
    ) -> list[list[float]]:
        request_payload = build_document_payload(documents)
        document_list = request_payload["inputs"]
        if not document_list:
            return []
        response = await self._http.post(
            f"{self.base_url}/embed",
            json=request_payload,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceProtocolError(
                "Embedding service returned invalid JSON"
            ) from exc
        return validate_embedding_response(
            payload,
            expected_count=len(document_list),
            expected_dimension=self.expected_dimension,
        )
