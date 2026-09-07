from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from new_architecture.knowledge_update import (
    KnowledgeUpdateCoordinator,
    KnowledgeUpdateFailure,
    LockedChunk,
    PersistedChunk,
    VectorPoint,
)


OLD_CONTENT = "question: تست بروزرسانی دانش شماره ۱\nanswer: پاسخ قدیمی تست"


def fake_vector(text: str) -> list[float]:
    checksum = sum(text.encode("utf-8"))
    return [float(len(text)), float(checksum % 997)]


class SharedPostgresState:
    def __init__(self):
        self.lock = threading.RLock()
        self.content = OLD_CONTENT
        self.vector = fake_vector(OLD_CONTENT)
        self.versions = [OLD_CONTENT]


class FakeRepository:
    def __init__(self, shared: SharedPostgresState, fail_at: str | None = None):
        self.shared = shared
        self.fail_at = fail_at
        self.staged = None
        self.locked = False
        self.committed = False

    def lock(self, chunk_id: int):
        self.shared.lock.acquire()
        self.locked = True
        if self.fail_at == "lock":
            raise RuntimeError("synthetic PostgreSQL lock failure")
        return LockedChunk(
            chunk_id=chunk_id,
            document_id=7,
            chunk_index=0,
            document_title="General_FAQ",
            content=self.shared.content,
            vector=deepcopy(self.shared.vector),
        )

    def stage(self, *, content, vector, changed_by, **_kwargs):
        if self.fail_at == "stage":
            raise RuntimeError("synthetic PostgreSQL write failure")
        self.staged = (content, deepcopy(vector), changed_by)

    def commit(self):
        if self.fail_at == "commit":
            raise RuntimeError("synthetic PostgreSQL commit failure")
        content, vector, _changed_by = self.staged
        self.shared.content = content
        self.shared.vector = vector
        self.shared.versions.append(content)
        self.committed = True
        self._release()
        if self.fail_at == "commit_response_lost":
            raise RuntimeError("synthetic lost commit response")

    def rollback(self):
        self.staged = None
        self._release()

    def read_fresh(self, _chunk_id: int):
        if self.fail_at == "fresh_read":
            return PersistedChunk("stale", [0.0, 0.0])
        return PersistedChunk(
            self.shared.content,
            deepcopy(self.shared.vector),
        )

    def close(self):
        self._release()

    def _release(self):
        if self.locked:
            self.locked = False
            self.shared.lock.release()


class FakeVectorStore:
    collection_name = "synthetic_knowledge"

    def __init__(self):
        self.point = VectorPoint(
            1,
            fake_vector(OLD_CONTENT),
            {"content": OLD_CONTENT, "text": OLD_CONTENT},
        )
        self.fail_upsert = False
        self.fail_confirmation = False
        self.fail_restore = False
        self.read_count = 0
        self.upsert_count = 0
        self.restore_count = 0

    def read(self, _point_id: int):
        self.read_count += 1
        point = deepcopy(self.point)
        if self.fail_confirmation and self.read_count % 2 == 0:
            point.payload["content"] = "stale"
        return point

    def upsert(self, point: VectorPoint):
        self.upsert_count += 1
        if self.fail_upsert:
            raise RuntimeError("synthetic Qdrant failure")
        self.point = deepcopy(point)

    def restore(self, _point_id: int, previous: VectorPoint | None):
        self.restore_count += 1
        if self.fail_restore:
            raise RuntimeError("synthetic compensation failure")
        self.point = deepcopy(previous)


class CacheInvalidator:
    def __init__(self, fail: bool = False):
        self.calls = 0
        self.fail = fail

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("synthetic cache invalidation failure")


class KnowledgeUpdateConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.postgres = SharedPostgresState()
        self.qdrant = FakeVectorStore()
        self.cache = CacheInvalidator()
        self.repository_failure = None
        self.embedding_calls = 0
        self.fail_embedding = False

    def embed(self, content):
        self.embedding_calls += 1
        if self.fail_embedding:
            raise RuntimeError("synthetic embedding failure")
        return fake_vector(content)

    def coordinator(self):
        return KnowledgeUpdateCoordinator(
            repository_factory=lambda: FakeRepository(
                self.postgres, self.repository_failure
            ),
            vector_store=self.qdrant,
            embed_content=self.embed,
            invalidate_local_cache=self.cache,
        )

    def update(self, answer: str):
        content = f"question: تست بروزرسانی دانش شماره ۱\nanswer: {answer}"
        return self.coordinator().update(
            chunk_id=1,
            content=content,
            normalized_content=content,
            changed_by="synthetic-test",
        )

    def test_success_is_acknowledged_verified_and_old_answer_is_absent(self):
        result = self.update("پاسخ جدید تست")

        self.assertTrue(result.success)
        self.assertEqual(self.postgres.content, self.qdrant.point.payload["content"])
        self.assertEqual(self.postgres.vector, self.qdrant.point.vector)
        self.assertNotIn("پاسخ قدیمی تست", self.postgres.content)
        self.assertEqual(self.cache.calls, 1)
        self.assertEqual(self.qdrant.upsert_count, 1)
        self.assertGreaterEqual(self.qdrant.read_count, 2)
        self.assertIn("postgresql.chunks", result.updated_stores)
        self.assertIn("qdrant", result.updated_stores)

    def test_twenty_sequential_updates_never_restore_an_old_answer(self):
        for version in range(1, 21):
            self.update(f"پاسخ نسخه {version}")
            expected = f"پاسخ نسخه {version}"
            self.assertIn(expected, self.postgres.content)
            self.assertEqual(
                self.postgres.content,
                self.qdrant.point.payload["content"],
            )
            if version > 1:
                self.assertNotIn(
                    f"پاسخ نسخه {version - 1}", self.postgres.content
                )
        self.assertEqual(self.cache.calls, 20)

    def test_fresh_coordinator_instance_observes_persisted_update(self):
        self.update("پاسخ پس از راه‌اندازی مجدد")
        first_embedding_calls = self.embedding_calls
        second_process = self.coordinator()
        second_process.update(
            chunk_id=1,
            content=self.postgres.content,
            normalized_content=self.postgres.content,
            changed_by="fresh-process",
        )
        self.assertEqual(
            self.postgres.content,
            self.qdrant.point.payload["content"],
        )
        self.assertEqual(self.embedding_calls, first_embedding_calls)

    def test_concurrent_updates_are_serialized_last_lock_holder_wins(self):
        answers = ("پاسخ همزمان الف", "پاسخ همزمان ب")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.update, answer) for answer in answers]
            for future in futures:
                future.result(timeout=2)

        self.assertIn(self.postgres.content, self.postgres.versions[-1:])
        self.assertEqual(self.postgres.content, self.qdrant.point.payload["content"])
        self.assertTrue(any(answer in self.postgres.content for answer in answers))
        self.assertEqual(len(self.postgres.versions), 3)

    def test_postgres_failure_rolls_back_and_does_not_report_success(self):
        self.repository_failure = "stage"
        with self.assertRaises(KnowledgeUpdateFailure) as raised:
            self.update("نباید ثبت شود")
        self.assertEqual(raised.exception.reason_code, "POSTGRES_UPDATE_FAILED")
        self.assertEqual(self.postgres.content, OLD_CONTENT)
        self.assertEqual(self.qdrant.point.payload["content"], OLD_CONTENT)

    def test_embedding_failure_changes_no_store_and_is_not_success(self):
        self.fail_embedding = True
        with self.assertRaises(KnowledgeUpdateFailure) as raised:
            self.update("بردارسازی ناموفق")
        self.assertEqual(raised.exception.reason_code, "EMBEDDING_FAILED")
        self.assertEqual(self.postgres.content, OLD_CONTENT)
        self.assertEqual(self.qdrant.point.payload["content"], OLD_CONTENT)

    def test_qdrant_failure_rolls_back_postgres_and_compensates(self):
        self.qdrant.fail_upsert = True
        with self.assertRaises(KnowledgeUpdateFailure) as raised:
            self.update("نباید ثبت شود")
        self.assertEqual(raised.exception.reason_code, "QDRANT_UPDATE_FAILED")
        self.assertEqual(self.postgres.content, OLD_CONTENT)
        self.assertEqual(self.qdrant.point.payload["content"], OLD_CONTENT)
        self.assertEqual(self.qdrant.restore_count, 1)

    def test_qdrant_confirmation_failure_does_not_report_success(self):
        self.qdrant.fail_confirmation = True
        with self.assertRaises(KnowledgeUpdateFailure) as raised:
            self.update("خوانده نمی‌شود")
        self.assertEqual(
            raised.exception.reason_code, "QDRANT_CONFIRMATION_FAILED"
        )
        self.assertEqual(self.postgres.content, OLD_CONTENT)
        self.assertEqual(self.qdrant.point.payload["content"], OLD_CONTENT)

    def test_postgres_commit_failure_restores_previous_qdrant_point(self):
        self.repository_failure = "commit"
        with self.assertRaises(KnowledgeUpdateFailure) as raised:
            self.update("کامیت ناموفق")
        self.assertEqual(raised.exception.reason_code, "POSTGRES_UPDATE_FAILED")
        self.assertEqual(self.postgres.content, OLD_CONTENT)
        self.assertEqual(self.qdrant.point.payload["content"], OLD_CONTENT)

    def test_lost_commit_response_is_resolved_by_fresh_read(self):
        self.repository_failure = "commit_response_lost"
        result = self.update("کامیت انجام شد اما پاسخ شبکه گم شد")
        self.assertTrue(result.success)
        self.assertEqual(self.postgres.content, self.qdrant.point.payload["content"])
        self.assertEqual(self.qdrant.restore_count, 0)

    def test_fresh_read_failure_is_repair_required_and_not_success(self):
        self.repository_failure = "fresh_read"
        with self.assertRaises(KnowledgeUpdateFailure) as raised:
            self.update("ثبت شده ولی تایید نشده")
        self.assertEqual(
            raised.exception.reason_code, "KNOWLEDGE_VERIFY_FAILED"
        )
        self.assertTrue(raised.exception.repair_required)

    def test_cache_failure_after_commit_is_repair_required_and_not_success(self):
        self.cache.fail = True
        with self.assertRaises(KnowledgeUpdateFailure) as raised:
            self.update("ثبت شده اما کش پاک نشده")
        self.assertEqual(
            raised.exception.reason_code, "CACHE_INVALIDATION_FAILED"
        )
        self.assertTrue(raised.exception.repair_required)
        self.assertEqual(self.postgres.content, self.qdrant.point.payload["content"])


if __name__ == "__main__":
    unittest.main()
