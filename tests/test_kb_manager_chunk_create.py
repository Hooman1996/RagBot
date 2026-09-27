import json
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

import kb_manager


class ChunkCreateTests(unittest.TestCase):
    def setUp(self):
        self.document_id = 47
        self.chunk_id = 83
        self.queries = []
        self.fail_sql = None
        self.document_title = "General_FAQ"
        self.cursor = Mock()
        self.connection = Mock()
        self.connection.cursor.return_value = self.cursor
        self.cursor.execute.side_effect = self.execute
        self.cursor.fetchone.side_effect = self.fetchone
        self.search = Mock()
        self.search.embed_documents_sync.return_value = [[0.1, 0.2]]
        self.search.query_embedding_model = "configured-model"
        self.main = types.ModuleType("main")
        self.main.rag_system = Mock(search_engine=self.search)
        self.main.qdrant_client = Mock()
        self.main.QDRANT_COLLECTION = "current_collection"
        self.main.Config = types.SimpleNamespace(QDRANT_VECTOR_SIZE=2)
        self.payload = kb_manager.ChunkCreatePayload(
            document_id=self.document_id,
            question="Question",
            answer="Answer",
            is_qa=True,
            changed_by="Tester",
        )
        self.patches = [
            patch.dict(sys.modules, {"main": self.main}),
            patch.dict(os.environ, {"EMBEDDING_MODEL": "configured-model"}),
            patch.object(kb_manager, "get_db_connection", return_value=self.connection),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def execute(self, sql, params):
        self.queries.append((sql, params))
        if self.fail_sql and self.fail_sql in sql:
            raise RuntimeError("synthetic database failure")

    def fetchone(self):
        sql = self.queries[-1][0]
        if "FROM documents" in sql:
            return {"title": self.document_title}
        if "next_idx" in sql:
            return {"next_idx": 4}
        if "RETURNING id" in sql:
            return {"id": self.chunk_id}
        raise AssertionError(sql)

    def query(self, fragment):
        return next((sql, params) for sql, params in self.queries if fragment in sql)

    def test_success_preserves_lineage_metadata_payload_and_cache(self):
        for title in ("General_FAQ", "A regular document"):
            with self.subTest(title=title):
                self.document_title = title
                self.queries.clear()
                self.connection.reset_mock()
                self.search.reset_mock()
                self.main.qdrant_client.reset_mock()
                self.search.embed_documents_sync.return_value = [[0.1, 0.2]]

                result = kb_manager.api_create_chunk(self.payload)

                self.assertEqual(result["chunk_id"], self.chunk_id)
                _, chunk_values = self.query("INSERT INTO chunks")
                self.assertEqual(chunk_values[0], self.document_id)
                embedding_sql, values = self.query("INSERT INTO embeddings")
                columns = embedding_sql.split("(", 1)[1].split(")", 1)[0]
                columns = [column.strip() for column in columns.split(",")]
                row = dict(zip(columns, values))
                self.assertEqual(len(columns), len(values))
                self.assertEqual(row["chunk_id"], self.chunk_id)
                self.assertEqual(row["document_id"], self.document_id)
                self.assertEqual(json.loads(row["vector"]), [0.1, 0.2])
                self.assertEqual(row["vector_dimension"], 2)
                self.assertEqual(row["model_name"], "configured-model")
                self.assertTrue(row["uuid"])
                self.assertEqual(row["vector_db_id"], str(self.chunk_id))
                self.assertEqual(row["vector_db_collection"], "current_collection")
                self.assertEqual(row["status"], "active")
                self.assertIsNotNone(row["created_at"])
                self.assertIsNotNone(row["updated_at"])
                point = self.main.qdrant_client.upsert.call_args.kwargs["points"][0]
                self.assertEqual(point.id, self.chunk_id)
                self.assertEqual(point.payload["chunk_id"], self.chunk_id)
                self.assertEqual(point.payload["document_id"], self.document_id)
                self.assertEqual(point.payload["chunk_index"], 4)
                self.assertEqual(point.payload["document"], title)
                self.assertEqual(point.payload["text"], point.payload["content"])
                self.query("INSERT INTO chunk_versions")
                self.query("INSERT INTO knowledge_document_revisions")
                self.connection.commit.assert_called_once_with()
                self.search.clear_document_cache.assert_called_once_with()
                self.main.qdrant_client.delete.assert_not_called()

    def test_missing_document_creates_nothing(self):
        self.cursor.fetchone.side_effect = lambda: None
        with self.assertRaises(HTTPException) as raised:
            kb_manager.api_create_chunk(self.payload)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(len(self.queries), 1)
        self.search.embed_documents_sync.assert_not_called()
        self.connection.commit.assert_not_called()
        self.main.qdrant_client.upsert.assert_not_called()

    def test_embedding_insert_failure_rolls_back_before_qdrant(self):
        self.fail_sql = "INSERT INTO embeddings"
        with self.assertRaises(HTTPException) as raised:
            kb_manager.api_create_chunk(self.payload)
        self.assertEqual(raised.exception.status_code, 500)
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_not_called()
        self.main.qdrant_client.upsert.assert_not_called()

    def test_qdrant_failure_rolls_back_and_compensates_ambiguous_write(self):
        self.main.qdrant_client.upsert.side_effect = RuntimeError("synthetic Qdrant failure")
        with self.assertRaises(HTTPException):
            kb_manager.api_create_chunk(self.payload)
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_not_called()
        self.main.qdrant_client.delete.assert_called_once()
        self.assertEqual(
            self.main.qdrant_client.delete.call_args.kwargs["points_selector"].points,
            [self.chunk_id],
        )

    def test_commit_failure_compensates_qdrant(self):
        self.connection.commit.side_effect = RuntimeError("synthetic commit failure")
        with self.assertRaises(HTTPException):
            kb_manager.api_create_chunk(self.payload)
        self.connection.rollback.assert_called_once_with()
        self.main.qdrant_client.upsert.assert_called_once()
        self.main.qdrant_client.delete.assert_called_once()
        self.search.clear_document_cache.assert_not_called()

    def test_unavailable_encoder_preserves_503(self):
        self.main.rag_system = None
        with self.assertRaises(HTTPException) as raised:
            kb_manager.api_create_chunk(self.payload)
        self.assertEqual(raised.exception.status_code, 503)
        self.connection.commit.assert_not_called()

    def test_wrong_vector_dimension_creates_nothing(self):
        self.search.embed_documents_sync.return_value = [[0.1]]
        with self.assertRaises(HTTPException) as raised:
            kb_manager.api_create_chunk(self.payload)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertFalse(any("INSERT INTO" in sql for sql, _ in self.queries))
        self.connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
