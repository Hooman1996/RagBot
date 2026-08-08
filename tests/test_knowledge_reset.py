from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

from new_architecture.knowledge_reset import (
    PRODUCTION_RESET_CONFIRMATION,
    KnowledgeResetConfig,
    KnowledgeResetService,
    ResetPhaseError,
    _assert_reset_allowed,
    scrub_selection_metadata,
)
from new_architecture.setup_dbs import schema_reset_requested


def _config(root: Path) -> KnowledgeResetConfig:
    return KnowledgeResetConfig(
        postgres={},
        qdrant_host="qdrant",
        qdrant_port=6333,
        qdrant_api_key=None,
        qdrant_https=False,
        qdrant_collection="application-knowledge",
        qdrant_vector_size=4,
        minio_endpoint="minio:9000",
        minio_access_key="test",
        minio_secret_key="test",
        minio_secure=False,
        minio_bucket="application-knowledge",
        minio_prefix="",
        generated_root=root,
        environment="development",
    )


class FakeMinio:
    def __init__(self, names=()):
        self.names = list(names)

    def bucket_exists(self, _bucket):
        return True

    def list_objects(self, _bucket, prefix="", recursive=True):
        del recursive
        return [
            SimpleNamespace(object_name=name, size=1)
            for name in self.names
            if name.startswith(prefix)
        ]

    def remove_object(self, _bucket, name):
        self.names.remove(name)


class FakeQdrant:
    def __init__(self):
        self.points = [
            SimpleNamespace(
                payload={"document_id": 9, "document": "removed-source"}
            )
        ]

    def get_collections(self):
        return SimpleNamespace(
            collections=[SimpleNamespace(name="application-knowledge")]
        )

    def scroll(self, **_kwargs):
        return list(self.points), None

    def delete(self, **_kwargs):
        self.points.clear()

    def close(self):
        pass


class FakePostgresCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split()).lower()
        self.connection.queries.append(normalized)
        if "from information_schema.tables" in normalized:
            self.rows = [
                ("chat_sessions",),
                ("collections",),
                ("documents",),
                ("mass_answer_jobs",),
            ]
        elif normalized.startswith("select id, meta_data from chat_sessions"):
            self.rows = [(1, self.connection.session_metadata)]
        elif normalized.startswith("update chat_sessions"):
            self.connection.session_metadata = json.loads(params[0])
            self.rows = []
        elif normalized.startswith(
            "select id, selected_documents from mass_answer_jobs"
        ):
            self.rows = [("job", self.connection.job_selection)]
        elif normalized.startswith("update mass_answer_jobs"):
            self.connection.job_selection = json.loads(params[0])
            self.rows = []
        elif normalized.startswith("delete from documents"):
            self.connection.deleted_documents = True
            self.rows = []
        else:
            self.rows = []

    def fetchall(self):
        return list(self.rows)


class FakePostgresConnection:
    def __init__(self):
        self.session_metadata = {
            "agent_state": {
                "allowed_docs": ["removed"],
                "doc_category": "FAQ",
            }
        }
        self.job_selection = ["removed"]
        self.deleted_documents = False
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return FakePostgresCursor(self)

    def rollback(self):
        pass

    def close(self):
        pass


class KnowledgeResetTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_scrub_selection_metadata_removes_stale_state(self):
        metadata = {
            "selected_documents": ["current", "removed"],
            "agent_state": {
                "allowed_docs": ["removed"],
                "doc_category": "FAQ",
                "messages": ["preserved"],
            },
        }

        cleaned, removed = scrub_selection_metadata(metadata, {"current"})

        self.assertEqual(removed, 2)
        self.assertEqual(cleaned["selected_documents"], ["current"])
        self.assertEqual(cleaned["agent_state"]["allowed_docs"], [])
        self.assertIsNone(cleaned["agent_state"]["doc_category"])
        self.assertEqual(cleaned["agent_state"]["messages"], ["preserved"])

    def test_qdrant_reset_is_idempotent(self):
        qdrant = FakeQdrant()
        service = KnowledgeResetService(_config(self.root), qdrant_client=qdrant)

        first = service.clear_qdrant_knowledge()
        second = service.clear_qdrant_knowledge()

        self.assertEqual(first, {"removed_points": 1, "changed": True})
        self.assertEqual(second, {"removed_points": 0, "changed": False})

    def test_minio_reset_is_scoped_and_idempotent(self):
        minio = FakeMinio(["one.csv", "nested/two.csv"])
        service = KnowledgeResetService(_config(self.root), minio_client=minio)

        first = service.clear_minio_knowledge()
        second = service.clear_minio_knowledge()

        self.assertEqual(first["removed_objects"], 2)
        self.assertTrue(first["changed"])
        self.assertEqual(second["removed_objects"], 0)
        self.assertFalse(second["changed"])

    def test_generated_reset_preserves_gitkeep_and_is_idempotent(self):
        documents = self.root / "DOCUMENTS"
        chunks = self.root / "CHUNKS" / "General_FAQ"
        documents.mkdir(parents=True)
        chunks.mkdir(parents=True)
        (documents / ".gitkeep").write_text("\n")
        (documents / "General_FAQ.csv").write_text("data")
        (chunks / ".gitkeep").write_text("\n")
        (chunks / "General_FAQ_0.txt").write_text("chunk")
        service = KnowledgeResetService(_config(self.root))

        first = service.clear_generated_knowledge()
        second = service.clear_generated_knowledge()

        self.assertEqual(first["removed_source_documents"], 1)
        self.assertEqual(first["removed_chunks"], 1)
        self.assertEqual(second["removed_source_documents"], 0)
        self.assertEqual(second["removed_chunks"], 0)
        self.assertTrue((documents / ".gitkeep").exists())
        self.assertTrue((chunks / ".gitkeep").exists())

    def test_partial_failure_stops_before_postgres_and_reports_phase(self):
        calls = []

        class FailingService(KnowledgeResetService):
            def clear_qdrant_knowledge(self, *, dry_run=False):
                calls.append("qdrant")
                return {"changed": True}

            def clear_minio_knowledge(self, *, dry_run=False):
                calls.append("minio")
                raise RuntimeError("unavailable")

            def clear_knowledge_metadata(self, *, dry_run=False):
                calls.append("postgres")
                return {"changed": True}

        service = FailingService(_config(self.root))
        with self.assertRaises(ResetPhaseError) as raised:
            service.full_knowledge_reset()

        self.assertEqual(calls, ["qdrant", "minio"])
        self.assertFalse(raised.exception.result.success)
        self.assertEqual(raised.exception.result.failed_phase, "minio")
        self.assertIn("RuntimeError", raised.exception.result.error)

    def test_postgres_reset_deletes_documents_and_stale_selections(self):
        connection = FakePostgresConnection()

        class PostgresService(KnowledgeResetService):
            inspections = 0

            def inspect_postgres(self):
                self.inspections += 1
                if self.inspections == 1:
                    return {
                        "documents": 1,
                        "chunks": 2,
                        "stale_selections": 0,
                        "datasource_selections_to_clear": 2,
                    }
                return {
                    "documents": 0,
                    "chunks": 0,
                    "stale_selections": 0,
                    "datasource_selections_to_clear": 0,
                }

        service = PostgresService(
            _config(self.root),
            postgres_connect=lambda **_kwargs: connection,
        )
        result = service.clear_knowledge_metadata()

        self.assertTrue(connection.deleted_documents)
        self.assertEqual(
            connection.session_metadata["agent_state"]["allowed_docs"], []
        )
        self.assertIsNone(
            connection.session_metadata["agent_state"]["doc_category"]
        )
        self.assertEqual(connection.job_selection, [])
        self.assertEqual(result["removed_documents"], 1)
        self.assertEqual(result["removed_chunks"], 2)
        self.assertEqual(result["removed_selections"], 2)

    def test_validate_clean_state_accepts_only_zero_state(self):
        class CleanService(KnowledgeResetService):
            def inspect_postgres(self):
                return {
                    "datasources": 0,
                    "documents": 0,
                    "chunks": 0,
                    "orphan_chunks": 0,
                    "orphan_embeddings": 0,
                    "stale_selections": 0,
                }

            def inspect_qdrant(self):
                return {"points": 0}

            def inspect_minio(self):
                return {"objects": 0}

            def inspect_filesystem(self):
                return {"source_documents": 0, "chunks": 0}

        report = CleanService(_config(self.root)).validate_clean_state()
        self.assertTrue(report["clean"])

    def test_setup_do_not_drop_responses_preserve_schema(self):
        for response in ("", "n", "no", "anything else"):
            with self.subTest(response=response):
                self.assertFalse(schema_reset_requested(response))

    def test_setup_drop_responses_request_deterministic_reset(self):
        for response in ("y", "Y", "yes", " YES "):
            with self.subTest(response=response):
                self.assertTrue(schema_reset_requested(response))

    def test_production_reset_requires_flag_and_stronger_confirmation(self):
        config = _config(self.root)
        production = KnowledgeResetConfig(
            **{**config.__dict__, "environment": "production"}
        )
        with self.assertRaisesRegex(RuntimeError, "Production reset refused"):
            _assert_reset_allowed(
                production,
                allow_production_reset=False,
                confirmation=PRODUCTION_RESET_CONFIRMATION,
            )
        with self.assertRaisesRegex(RuntimeError, "exactly match"):
            _assert_reset_allowed(
                production,
                allow_production_reset=True,
                confirmation="RESET KNOWLEDGE",
            )
        _assert_reset_allowed(
            production,
            allow_production_reset=True,
            confirmation=PRODUCTION_RESET_CONFIRMATION,
        )


if __name__ == "__main__":
    unittest.main()
