"""Synchronous, verifiable knowledge-chunk update coordination.

PostgreSQL ``chunks.content`` is the authoritative answering text.  Qdrant and
the PostgreSQL ``embeddings`` row are derived representations.  This module
keeps the cross-store policy independent from FastAPI and vendor SDKs so it can
be failure-injection tested without live infrastructure.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol


LOGGER = logging.getLogger("knowledge_update")


class KnowledgeUpdateFailure(RuntimeError):
    """A safe, stage-specific failure suitable for translation to an API error."""

    def __init__(
        self,
        reason_code: str,
        update_id: str,
        *,
        repair_required: bool = False,
    ) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.update_id = update_id
        self.repair_required = repair_required


class KnowledgeChunkNotFound(KnowledgeUpdateFailure):
    pass


@dataclass(frozen=True)
class LockedChunk:
    chunk_id: int
    document_id: int
    chunk_index: int
    document_title: str
    content: str
    vector: Any


@dataclass(frozen=True)
class PersistedChunk:
    content: str
    vector: Any


@dataclass(frozen=True)
class VectorPoint:
    point_id: int
    vector: Any
    payload: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeUpdateResult:
    success: bool
    question_id: str
    revision: str
    knowledge_update_id: str
    updated_stores: tuple[str, ...]
    stage_durations_ms: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "question_id": self.question_id,
            "revision": self.revision,
            "knowledge_update_id": self.knowledge_update_id,
            "updated_stores": list(self.updated_stores),
            "stage_durations_ms": self.stage_durations_ms,
        }


class KnowledgeRepository(Protocol):
    def lock(self, chunk_id: int) -> LockedChunk | None: ...

    def stage(
        self,
        *,
        chunk_id: int,
        content: str,
        vector: Any,
        changed_by: str,
        changed_at: datetime,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def read_fresh(self, chunk_id: int) -> PersistedChunk | None: ...

    def close(self) -> None: ...


class KnowledgeVectorStore(Protocol):
    collection_name: str

    def read(self, point_id: int) -> VectorPoint | None: ...

    def upsert(self, point: VectorPoint) -> None: ...

    def restore(self, point_id: int, previous: VectorPoint | None) -> None: ...


def _vector_payload(vector: Any) -> Any:
    if isinstance(vector, str):
        return json.loads(vector)
    return vector


def vectors_equivalent(left: Any, right: Any, tolerance: float = 1e-7) -> bool:
    """Compare dense or named vectors without relying on NumPy."""
    left = _vector_payload(left)
    right = _vector_payload(right)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            vectors_equivalent(left[key], right[key], tolerance)
            for key in left
        )
    if not isinstance(left, (list, tuple)) or not isinstance(
        right, (list, tuple)
    ):
        return left == right
    if len(left) != len(right):
        return False
    return all(
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
        and math.isclose(float(a), float(b), rel_tol=tolerance, abs_tol=tolerance)
        for a, b in zip(left, right)
    )


class PsycopgKnowledgeRepository:
    """One short row-locked transaction plus an independent verification read."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory
        self._connection = None
        self._cursor = None
        self._document_id = None

    def lock(self, chunk_id: int) -> LockedChunk | None:
        self._connection = self._connection_factory()
        self._cursor = self._connection.cursor()
        self._cursor.execute(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.content,
                   d.title AS document_title, e.vector
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN embeddings e ON e.chunk_id = c.id
            WHERE c.id = %s
            FOR UPDATE OF c, e
            """,
            (chunk_id,),
        )
        row = self._cursor.fetchone()
        if not row:
            return None
        self._document_id = int(row["document_id"])
        return LockedChunk(
            chunk_id=int(row["id"]),
            document_id=int(row["document_id"]),
            chunk_index=int(row["chunk_index"]),
            document_title=str(row["document_title"]),
            content=str(row["content"]),
            vector=_vector_payload(row["vector"]),
        )

    def stage(
        self,
        *,
        chunk_id: int,
        content: str,
        vector: Any,
        changed_by: str,
        changed_at: datetime,
    ) -> None:
        if self._cursor is None:
            raise RuntimeError("knowledge transaction has not been opened")
        normalized_tokens = len(content.split())
        self._cursor.execute(
            """
            UPDATE chunks
            SET content = %s, char_count = %s, token_count = %s, updated_at = %s
            WHERE id = %s
            """,
            (content, len(content), normalized_tokens, changed_at, chunk_id),
        )
        if self._cursor.rowcount != 1:
            raise RuntimeError("authoritative chunk update affected no row")
        self._cursor.execute(
            """
            UPDATE embeddings SET vector = %s, updated_at = %s WHERE chunk_id = %s
            """,
            (json.dumps(vector), changed_at, chunk_id),
        )
        if self._cursor.rowcount != 1:
            raise RuntimeError("embedding update affected no row")
        self._cursor.execute(
            """
            INSERT INTO chunk_versions (chunk_id, content, changed_by, created_at)
            VALUES (%s, %s, %s, %s)
            """,
            (chunk_id, content, changed_by, changed_at),
        )
        self._cursor.execute(
            """
            INSERT INTO knowledge_document_revisions
                (document_id, revision, updated_at)
            VALUES (%s, 1, %s)
            ON CONFLICT (document_id) DO UPDATE
            SET revision = knowledge_document_revisions.revision + 1,
                updated_at = EXCLUDED.updated_at
            """,
            (self._document_id, changed_at),
        )

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        if self._connection is not None:
            self._connection.rollback()

    def read_fresh(self, chunk_id: int) -> PersistedChunk | None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.content, e.vector
                    FROM chunks c
                    JOIN embeddings e ON e.chunk_id = c.id
                    WHERE c.id = %s
                    """,
                    (chunk_id,),
                )
                row = cursor.fetchone()
            if not row:
                return None
            return PersistedChunk(
                content=str(row["content"]),
                vector=_vector_payload(row["vector"]),
            )
        finally:
            connection.close()

    def close(self) -> None:
        if self._cursor is not None:
            self._cursor.close()
            self._cursor = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class KnowledgeUpdateCoordinator:
    """Coordinate one FAQ update with acknowledgement and read-after-write proof."""

    def __init__(
        self,
        *,
        repository_factory: Callable[[], KnowledgeRepository],
        vector_store: KnowledgeVectorStore,
        embed_content: Callable[[str], Any],
        invalidate_local_cache: Callable[[], Any],
        database_name: str | None = None,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self._repository_factory = repository_factory
        self._vector_store = vector_store
        self._embed_content = embed_content
        self._invalidate_local_cache = invalidate_local_cache
        self._database_name = database_name
        self._logger = logger

    def _log(
        self,
        event: str,
        *,
        update_id: str,
        chunk_id: int,
        answer_hash: str,
        duration_ms: float | None = None,
        reason_code: str | None = None,
        repair_required: bool = False,
    ) -> None:
        self._logger.info(
            json.dumps(
                {
                    "event": event,
                    "knowledge_update_id": update_id,
                    "chunk_id": chunk_id,
                    "worker_pid": os.getpid(),
                    "qdrant_collection": self._vector_store.collection_name,
                    "postgres_database": self._database_name,
                    "answer_sha256": answer_hash,
                    "duration_ms": duration_ms,
                    "reason_code": reason_code,
                    "repair_required": repair_required,
                },
                sort_keys=True,
            ),
            extra={
                "event": event,
                "knowledge_update_id": update_id,
                "chunk_id": chunk_id,
                "worker_pid": os.getpid(),
                "qdrant_collection": self._vector_store.collection_name,
                "postgres_database": self._database_name,
                "answer_sha256": answer_hash,
                "duration_ms": duration_ms,
                "reason_code": reason_code,
                "repair_required": repair_required,
            },
        )

    def update(
        self,
        *,
        chunk_id: int,
        content: str,
        normalized_content: str,
        changed_by: str,
    ) -> KnowledgeUpdateResult:
        update_id = str(uuid.uuid4())
        answer_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        revision = f"{update_id}:{answer_hash[:16]}"
        durations: dict[str, float] = {}
        repository = self._repository_factory()
        previous_point: VectorPoint | None = None
        qdrant_attempted = False
        committed = False
        compensation_safe = True
        stage = "POSTGRES_UPDATE_FAILED"
        self._log(
            "UPDATE_RECEIVED",
            update_id=update_id,
            chunk_id=chunk_id,
            answer_hash=answer_hash,
        )
        try:
            preflight = repository.read_fresh(chunk_id)
            if preflight is not None and preflight.content == content:
                vector = preflight.vector
                durations["embedding"] = 0.0
            else:
                stage = "EMBEDDING_FAILED"
                started = time.perf_counter()
                vector = self._embed_content(normalized_content)
                durations["embedding"] = (
                    time.perf_counter() - started
                ) * 1000

            stage = "POSTGRES_UPDATE_FAILED"
            postgres_started = time.perf_counter()
            locked = repository.lock(chunk_id)
            if locked is None:
                raise KnowledgeChunkNotFound("CHUNK_NOT_FOUND", update_id)
            if locked.content == content:
                vector = locked.vector
                durations["embedding"] = 0.0
            elif preflight is not None and preflight.content == content:
                # The row changed after the preflight read. Embed while holding
                # the lock so the requested content still receives its vector.
                stage = "EMBEDDING_FAILED"
                embed_started = time.perf_counter()
                vector = self._embed_content(normalized_content)
                durations["embedding"] = (
                    time.perf_counter() - embed_started
                ) * 1000
            stage = "QDRANT_UPDATE_FAILED"
            previous_point = self._vector_store.read(chunk_id)
            stage = "POSTGRES_UPDATE_FAILED"
            repository.stage(
                chunk_id=chunk_id,
                content=content,
                vector=vector,
                changed_by=changed_by,
                changed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            durations["postgres_stage"] = (
                time.perf_counter() - postgres_started
            ) * 1000
            self._log(
                "POSTGRES_STAGED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                duration_ms=durations["postgres_stage"],
            )

            payload = dict(previous_point.payload) if previous_point else {}
            payload.update(
                {
                    "chunk_id": chunk_id,
                    "chunk_index": locked.chunk_index,
                    "document_id": locked.document_id,
                    "document": locked.document_title,
                    "content": content,
                    "text": content,
                    "knowledge_revision": revision,
                }
            )
            expected_point = VectorPoint(chunk_id, vector, payload)

            stage = "QDRANT_UPDATE_FAILED"
            started = time.perf_counter()
            qdrant_attempted = True
            self._vector_store.upsert(expected_point)
            durations["qdrant_update"] = (
                time.perf_counter() - started
            ) * 1000
            self._log(
                "QDRANT_UPDATED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                duration_ms=durations["qdrant_update"],
            )

            stage = "QDRANT_CONFIRMATION_FAILED"
            confirmed_point = self._vector_store.read(chunk_id)
            if (
                confirmed_point is None
                or confirmed_point.payload.get("content") != content
                or confirmed_point.payload.get("text") != content
                or confirmed_point.payload.get("knowledge_revision") != revision
                or not vectors_equivalent(confirmed_point.vector, vector)
            ):
                raise RuntimeError("Qdrant read-after-write verification failed")

            stage = "POSTGRES_UPDATE_FAILED"
            started = time.perf_counter()
            compensation_safe = False
            try:
                repository.commit()
                committed = True
            except Exception:
                # A transport error during COMMIT has an unknown outcome. A
                # fresh read distinguishes an applied commit from a proven
                # rollback; if it cannot, leave Qdrant untouched and flag
                # manual repair rather than restoring stale data blindly.
                commit_outcome = repository.read_fresh(chunk_id)
                if (
                    commit_outcome is not None
                    and commit_outcome.content == content
                    and vectors_equivalent(commit_outcome.vector, vector)
                ):
                    committed = True
                elif (
                    commit_outcome is not None
                    and commit_outcome.content == locked.content
                    and vectors_equivalent(commit_outcome.vector, locked.vector)
                ):
                    compensation_safe = True
                    raise
                else:
                    raise
            durations["postgres_commit"] = (
                time.perf_counter() - started
            ) * 1000
            self._log(
                "POSTGRES_UPDATED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                duration_ms=durations["postgres_commit"],
            )

            stage = "KNOWLEDGE_VERIFY_FAILED"
            started = time.perf_counter()
            persisted = repository.read_fresh(chunk_id)
            if (
                persisted is None
                or persisted.content != content
                or not vectors_equivalent(persisted.vector, vector)
            ):
                raise RuntimeError("fresh PostgreSQL verification failed")
            durations["verification"] = (
                time.perf_counter() - started
            ) * 1000
            self._log(
                "READ_AFTER_WRITE_VERIFIED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                duration_ms=durations["verification"],
            )

            stage = "CACHE_INVALIDATION_FAILED"
            started = time.perf_counter()
            self._invalidate_local_cache()
            durations["cache_invalidation"] = (
                time.perf_counter() - started
            ) * 1000
            self._log(
                "CACHE_INVALIDATED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                duration_ms=durations["cache_invalidation"],
            )

            self._log(
                "UPDATE_COMPLETED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                duration_ms=sum(durations.values()),
            )
            return KnowledgeUpdateResult(
                success=True,
                question_id=str(chunk_id),
                revision=revision,
                knowledge_update_id=update_id,
                updated_stores=(
                    "postgresql.chunks",
                    "postgresql.embeddings",
                    "postgresql.chunk_versions",
                    "qdrant",
                    "local_bm25_cache",
                ),
                stage_durations_ms={
                    key: round(value, 3) for key, value in durations.items()
                },
            )
        except KnowledgeChunkNotFound:
            repository.rollback()
            self._log(
                "UPDATE_FAILED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                reason_code="CHUNK_NOT_FOUND",
            )
            raise
        except Exception as exc:
            repair_required = committed or not compensation_safe
            if not committed:
                repository.rollback()
                if qdrant_attempted and compensation_safe:
                    try:
                        self._vector_store.restore(chunk_id, previous_point)
                    except Exception:
                        repair_required = True
                        self._logger.exception(
                            "QDRANT_COMPENSATION_FAILED",
                            extra={
                                "knowledge_update_id": update_id,
                                "chunk_id": chunk_id,
                                "worker_pid": os.getpid(),
                            },
                        )
            self._log(
                "UPDATE_FAILED",
                update_id=update_id,
                chunk_id=chunk_id,
                answer_hash=answer_hash,
                reason_code=stage,
                repair_required=repair_required,
            )
            raise KnowledgeUpdateFailure(
                stage,
                update_id,
                repair_required=repair_required,
            ) from exc
        finally:
            repository.close()
