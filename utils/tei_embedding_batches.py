"""Batch orchestration for raw-document TEI embedding."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import asyncio
import httpx

from utils.tei_embedding_client import TeiEmbeddingClient


class DocumentEmbeddingBatchError(RuntimeError):
    """A document batch failed before it was safe to write to Qdrant."""

    def __init__(
        self,
        *,
        batch_number: int,
        batch_size: int,
        source_record_ids: Sequence[Any],
    ) -> None:
        self.batch_number = batch_number
        self.batch_size = batch_size
        self.source_record_ids = list(source_record_ids)
        super().__init__(
            "TEI document embedding failed for "
            f"batch={batch_number}, size={batch_size}, "
            f"source_record_ids={self.source_record_ids!r}"
        )


async def embed_documents_in_batches(
    client: TeiEmbeddingClient,
    documents: Sequence[str],
    source_record_ids: Sequence[Any],
    *,
    batch_size: int,
) -> list[list[float]]:
    """Embed raw documents in order, adding record context to failures."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if len(documents) != len(source_record_ids):
        raise ValueError("documents and source_record_ids must have equal length")
    if not documents:
        return []

    vectors: list[list[float]] = []
    for offset in range(0, len(documents), batch_size):
        batch_number = offset // batch_size + 1
        batch_texts = documents[offset : offset + batch_size]
        batch_ids = source_record_ids[offset : offset + batch_size]
        try:
            batch_vectors = await client.embed_documents(batch_texts)
        except Exception as exc:
            raise DocumentEmbeddingBatchError(
                batch_number=batch_number,
                batch_size=len(batch_texts),
                source_record_ids=batch_ids,
            ) from exc
        vectors.extend(batch_vectors)
    return vectors


class TeiInsertionSession:
    """Own one async HTTP client and event loop for a synchronous loader."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout: httpx.Timeout,
        limits: httpx.Limits,
        expected_dimension: int,
        batch_size: int,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._runner = asyncio.Runner()
        self._http = httpx.AsyncClient(timeout=timeout, limits=limits)
        self._client = TeiEmbeddingClient(
            base_url,
            self._http,
            expected_dimension=expected_dimension,
        )
        self.batch_size = batch_size
        self._closed = False

    def __enter__(self) -> "TeiInsertionSession":
        return self

    def embed_documents(
        self,
        documents: Sequence[str],
        source_record_ids: Sequence[Any],
    ) -> list[list[float]]:
        if self._closed:
            raise RuntimeError("TEI insertion session is closed")
        return self._runner.run(
            embed_documents_in_batches(
                self._client,
                documents,
                source_record_ids,
                batch_size=self.batch_size,
            )
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._runner.run(self._http.aclose())
        self._runner.close()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
