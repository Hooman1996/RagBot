"""Canonical knowledge-base reset and clean-state validation service.

The configured Qdrant collection and MinIO bucket/prefix are treated as the
application knowledge scope.  Users, chats, queries, and other operational
records are preserved by a knowledge reset; only stale datasource selections
inside those records are scrubbed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from dotenv import load_dotenv

from new_architecture.knowledge_sources import (
    count_generated_knowledge,
    discover_chunk_files,
    is_ignored_path,
)


load_dotenv()

RESET_CONFIRMATION = "RESET KNOWLEDGE"
PRODUCTION_RESET_CONFIRMATION = "RESET PRODUCTION KNOWLEDGE"
SELECTION_KEYS = {
    "active_documents",
    "allowed_docs",
    "documents",
    "selected_documents",
    "selected_sources",
    "source_selection",
}


CHUNK_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS chunk_versions (
    id SERIAL PRIMARY KEY,
    chunk_id INT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    changed_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
)
"""


KNOWLEDGE_DOCUMENT_REVISIONS_DDL = """
CREATE TABLE IF NOT EXISTS knowledge_document_revisions (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    revision BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
)
"""


MASS_ANSWER_JOBS_DDL = """
CREATE TABLE IF NOT EXISTS mass_answer_jobs (
    id VARCHAR(36) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    input_filename TEXT NOT NULL,
    input_format VARCHAR(8) NOT NULL,
    selected_documents JSONB NOT NULL DEFAULT '[]',
    artifact_directory TEXT NOT NULL,
    result_path TEXT,
    total_rows INTEGER NOT NULL DEFAULT 0,
    valid_rows INTEGER NOT NULL DEFAULT 0,
    completed_rows INTEGER NOT NULL DEFAULT 0,
    successful_rows INTEGER NOT NULL DEFAULT 0,
    failed_rows INTEGER NOT NULL DEFAULT 0,
    timed_out_rows INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    total_duration_ms FLOAT,
    average_row_ms FLOAT,
    p50_row_ms FLOAT,
    p95_row_ms FLOAT,
    p99_row_ms FLOAT,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
"""


@dataclass(frozen=True)
class KnowledgeResetConfig:
    postgres: dict[str, Any]
    qdrant_host: str
    qdrant_port: int
    qdrant_api_key: str | None
    qdrant_https: bool
    qdrant_collection: str
    qdrant_vector_size: int
    minio_endpoint: str
    minio_access_key: str | None
    minio_secret_key: str | None
    minio_secure: bool
    minio_bucket: str
    minio_prefix: str
    generated_root: Path
    environment: str

    @classmethod
    def from_environment(cls) -> "KnowledgeResetConfig":
        required = {
            "POSTGRES_HOST": os.getenv("POSTGRES_HOST"),
            "POSTGRES_PORT": os.getenv("POSTGRES_PORT"),
            "POSTGRES_DB": os.getenv("POSTGRES_DB"),
            "POSTGRES_USER": os.getenv("POSTGRES_USER"),
            "POSTGRES_PASSWORD": os.getenv("POSTGRES_PASSWORD"),
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT"),
            "MINIO_ACCESS_KEY": os.getenv("MINIO_ACCESS_KEY"),
            "MINIO_SECRET_KEY": os.getenv("MINIO_SECRET_KEY"),
            "MINIO_BUCKET": os.getenv("MINIO_BUCKET"),
        }
        missing = sorted(key for key, value in required.items() if not value)
        if missing:
            raise RuntimeError(
                "Missing reset configuration: " + ", ".join(missing)
            )
        return cls(
            postgres={
                "host": required["POSTGRES_HOST"],
                "port": required["POSTGRES_PORT"],
                "dbname": required["POSTGRES_DB"],
                "user": required["POSTGRES_USER"],
                "password": required["POSTGRES_PASSWORD"],
                "connect_timeout": 5,
                "options": "-c statement_timeout=30000 -c lock_timeout=5000",
            },
            qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
            qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
            qdrant_api_key=os.getenv("QDRANT_API_KEY"),
            qdrant_https=os.getenv("QDRANT_HTTPS", "false").lower() == "true",
            qdrant_collection=os.getenv(
                "QDRANT_COLLECTION", "hihelp_embeddings"
            ),
            qdrant_vector_size=int(os.getenv("QDRANT_VECTOR_SIZE", "1024")),
            minio_endpoint=str(required["MINIO_ENDPOINT"]),
            minio_access_key=required["MINIO_ACCESS_KEY"],
            minio_secret_key=required["MINIO_SECRET_KEY"],
            minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            minio_bucket=str(required["MINIO_BUCKET"]),
            minio_prefix=os.getenv("MINIO_KNOWLEDGE_PREFIX", "").strip("/"),
            generated_root=Path(
                os.getenv(
                    "DATA_INSERTION_DIRECTORY",
                    str(Path(__file__).resolve().parents[1] / "data_insertion_chunks"),
                )
            ),
            environment=os.getenv("ENVIRONMENT", "development").lower(),
        )


@dataclass
class ResetResult:
    dry_run: bool
    phases: dict[str, dict[str, Any]] = field(default_factory=dict)
    success: bool = True
    failed_phase: str | None = None
    error: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResetPhaseError(RuntimeError):
    def __init__(self, result: ResetResult):
        super().__init__(result.error or "Knowledge reset failed")
        self.result = result


def _decode_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _filter_selection_value(value: Any, valid_names: set[str]) -> tuple[Any, int]:
    if isinstance(value, list):
        kept = [item for item in value if str(item) in valid_names]
        return kept, len(value) - len(kept)
    if isinstance(value, str):
        return (value if value in valid_names else None), int(value not in valid_names)
    return value, 0


def scrub_selection_metadata(
    metadata: dict[str, Any], valid_names: Iterable[str]
) -> tuple[dict[str, Any], int]:
    """Remove invalid datasource selections from known metadata fields."""
    valid = set(valid_names)
    cleaned = dict(metadata)
    removed = 0

    def scrub_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
        nonlocal removed
        output = dict(mapping)
        for key in SELECTION_KEYS.intersection(output):
            output[key], count = _filter_selection_value(output[key], valid)
            removed += count
        if not output.get("allowed_docs"):
            output["doc_category"] = None
        return output

    cleaned = scrub_mapping(cleaned)
    agent_state = cleaned.get("agent_state")
    if isinstance(agent_state, dict):
        cleaned["agent_state"] = scrub_mapping(agent_state)
    return cleaned, removed


class KnowledgeResetService:
    """Coordinates scoped, idempotent reset operations across all stores."""

    def __init__(
        self,
        config: KnowledgeResetConfig,
        *,
        postgres_connect: Callable[..., Any] | None = None,
        qdrant_client: Any | None = None,
        minio_client: Any | None = None,
    ):
        self.config = config
        self._postgres_connect = postgres_connect
        self._qdrant_client = qdrant_client
        self._minio_client = minio_client

    @classmethod
    def from_environment(cls) -> "KnowledgeResetService":
        return cls(KnowledgeResetConfig.from_environment())

    def _connect_postgres(self):
        if self._postgres_connect is None:
            import psycopg2

            self._postgres_connect = psycopg2.connect
        return self._postgres_connect(**self.config.postgres)

    def _get_qdrant(self):
        if self._qdrant_client is None:
            from qdrant_client import QdrantClient

            self._qdrant_client = QdrantClient(
                host=self.config.qdrant_host,
                port=self.config.qdrant_port,
                api_key=self.config.qdrant_api_key,
                https=self.config.qdrant_https,
                timeout=10.0,
            )
        return self._qdrant_client

    def _get_minio(self):
        if self._minio_client is None:
            from minio import Minio

            self._minio_client = Minio(
                self.config.minio_endpoint,
                access_key=self.config.minio_access_key,
                secret_key=self.config.minio_secret_key,
                secure=self.config.minio_secure,
            )
        return self._minio_client

    @staticmethod
    def _table_names(cursor) -> set[str]:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
        return {row[0] for row in cursor.fetchall()}

    def inspect_postgres(self) -> dict[str, Any]:
        conn = self._connect_postgres()
        try:
            conn.set_session(readonly=True, autocommit=True)
            with conn.cursor() as cursor:
                tables = self._table_names(cursor)
                report: dict[str, Any] = {
                    "datasources": 0,
                    "documents": 0,
                    "chunks": 0,
                    "chunk_metadata": 0,
                    "blank_documents": 0,
                    "zero_chunk_documents": 0,
                    "orphan_chunks": 0,
                    "orphan_embeddings": 0,
                    "stale_selections": 0,
                    "datasource_selections_to_clear": 0,
                    "document_ids_and_names": [],
                }
                if "documents" in tables:
                    cursor.execute("SELECT COUNT(*) FROM documents")
                    report["documents"] = cursor.fetchone()[0]
                    if "chunks" in tables:
                        cursor.execute(
                            """
                            SELECT d.id, d.title, COUNT(c.id)
                            FROM documents d
                            LEFT JOIN chunks c ON c.document_id = d.id
                            GROUP BY d.id, d.title
                            ORDER BY d.id
                            """
                        )
                        rows = cursor.fetchall()
                    else:
                        cursor.execute(
                            "SELECT id, title, 0 FROM documents ORDER BY id"
                        )
                        rows = cursor.fetchall()
                    report["document_ids_and_names"] = [
                        {"id": row[0], "name": row[1], "chunks": row[2]}
                        for row in rows
                    ]
                    report["blank_documents"] = sum(
                        1 for _, title, _ in rows if not str(title or "").strip()
                    )
                    report["zero_chunk_documents"] = sum(
                        1 for _, _, count in rows if count == 0
                    )
                    report["datasources"] = sum(
                        1
                        for _, title, count in rows
                        if str(title or "").strip() and count > 0
                    )
                    valid_names = {
                        str(title)
                        for _, title, count in rows
                        if str(title or "").strip() and count > 0
                    }
                else:
                    valid_names = set()
                if "chunks" in tables:
                    cursor.execute("SELECT COUNT(*) FROM chunks")
                    report["chunks"] = cursor.fetchone()[0]
                    report["chunk_metadata"] = report["chunks"]
                    if "documents" in tables:
                        cursor.execute(
                            """
                            SELECT COUNT(*) FROM chunks c
                            LEFT JOIN documents d ON d.id = c.document_id
                            WHERE d.id IS NULL
                            """
                        )
                        report["orphan_chunks"] = cursor.fetchone()[0]
                if {"embeddings", "chunks", "documents"}.issubset(tables):
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM embeddings e
                        LEFT JOIN chunks c ON c.id = e.chunk_id
                        LEFT JOIN documents d ON d.id = e.document_id
                        WHERE c.id IS NULL OR d.id IS NULL
                        """
                    )
                    report["orphan_embeddings"] = cursor.fetchone()[0]
                report["stale_selections"] = self._count_stale_selections(
                    cursor, tables, valid_names
                )
                report["datasource_selections_to_clear"] = (
                    self._count_stale_selections(cursor, tables, set())
                )
                return report
        finally:
            conn.close()

    def _count_stale_selections(
        self, cursor, tables: set[str], valid_names: set[str]
    ) -> int:
        stale = 0
        if "chat_sessions" in tables:
            cursor.execute("SELECT meta_data FROM chat_sessions")
            for (raw_metadata,) in cursor.fetchall():
                metadata = _decode_json(raw_metadata, {})
                if isinstance(metadata, dict):
                    _, removed = scrub_selection_metadata(metadata, valid_names)
                    stale += removed
        if "mass_answer_jobs" in tables:
            cursor.execute("SELECT selected_documents FROM mass_answer_jobs")
            for (raw_selection,) in cursor.fetchall():
                selections = _decode_json(raw_selection, [])
                _, removed = _filter_selection_value(selections, valid_names)
                stale += removed
        return stale

    def inspect_qdrant(self) -> dict[str, Any]:
        client = self._get_qdrant()
        collection = self.config.qdrant_collection
        names = {item.name for item in client.get_collections().collections}
        if collection not in names:
            return {
                "collection_exists": False,
                "points": 0,
                "datasource_ids": [],
                "datasource_names": [],
                "missing_datasource_metadata": 0,
            }

        points = []
        offset = None
        while True:
            batch, offset = client.scroll(
                collection_name=collection,
                limit=256,
                offset=offset,
                with_payload=["document", "document_id"],
                with_vectors=False,
            )
            points.extend(batch)
            if offset is None:
                break
        payloads = [point.payload or {} for point in points]
        return {
            "collection_exists": True,
            "points": len(points),
            "datasource_ids": sorted(
                {str(payload.get("document_id")) for payload in payloads}
            ),
            "datasource_names": sorted(
                {str(payload.get("document")) for payload in payloads}
            ),
            "missing_datasource_metadata": sum(
                1
                for payload in payloads
                if payload.get("document_id") is None
                or not str(payload.get("document") or "").strip()
            ),
        }

    def inspect_minio(self) -> dict[str, Any]:
        client = self._get_minio()
        bucket = self.config.minio_bucket
        prefix = self.config.minio_prefix
        if not client.bucket_exists(bucket):
            return {
                "bucket_exists": False,
                "objects": 0,
                "prefixes": [],
                "scope": self._minio_scope(),
            }
        objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
        prefixes = sorted(
            {
                item.object_name[len(prefix) :].lstrip("/").split("/", 1)[0]
                for item in objects
                if item.object_name
            }
        )
        return {
            "bucket_exists": True,
            "objects": len(objects),
            "prefixes": prefixes,
            "scope": self._minio_scope(),
        }

    def _minio_scope(self) -> str:
        if self.config.minio_prefix:
            return f"{self.config.minio_bucket}/{self.config.minio_prefix}/"
        return f"{self.config.minio_bucket} (entire configured bucket)"

    def inspect_filesystem(self) -> dict[str, Any]:
        report = count_generated_knowledge(self.config.generated_root)
        report["root"] = str(self.config.generated_root)
        return report

    def validate_clean_state(self) -> dict[str, Any]:
        report = {
            "postgres": self.inspect_postgres(),
            "qdrant": self.inspect_qdrant(),
            "minio": self.inspect_minio(),
            "filesystem": self.inspect_filesystem(),
        }
        pg = report["postgres"]
        report["clean"] = all(
            (
                pg["datasources"] == 0,
                pg["documents"] == 0,
                pg["chunks"] == 0,
                pg["orphan_chunks"] == 0,
                pg["orphan_embeddings"] == 0,
                pg["stale_selections"] == 0,
                report["qdrant"]["points"] == 0,
                report["minio"]["objects"] == 0,
                report["filesystem"]["source_documents"] == 0,
                report["filesystem"]["chunks"] == 0,
            )
        )
        return report

    def clear_qdrant_knowledge(self, *, dry_run: bool = False) -> dict[str, Any]:
        before = self.inspect_qdrant()
        if dry_run or before["points"] == 0:
            return {"removed_points": before["points"], "changed": False}
        from qdrant_client.models import Filter, FilterSelector

        self._get_qdrant().delete(
            collection_name=self.config.qdrant_collection,
            points_selector=FilterSelector(filter=Filter(must=[])),
            wait=True,
        )
        after = self.inspect_qdrant()
        if after["points"] != 0:
            raise RuntimeError(
                f"Qdrant still contains {after['points']} application points"
            )
        return {"removed_points": before["points"], "changed": True}

    def clear_minio_knowledge(self, *, dry_run: bool = False) -> dict[str, Any]:
        client = self._get_minio()
        bucket = self.config.minio_bucket
        prefix = self.config.minio_prefix
        if not client.bucket_exists(bucket):
            return {"removed_objects": 0, "changed": False, "scope": self._minio_scope()}
        objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
        if not dry_run:
            for item in objects:
                client.remove_object(bucket, item.object_name)
            remaining = list(
                client.list_objects(bucket, prefix=prefix, recursive=True)
            )
            if remaining:
                raise RuntimeError(
                    f"MinIO still contains {len(remaining)} objects in reset scope"
                )
        return {
            "removed_objects": len(objects),
            "changed": bool(objects) and not dry_run,
            "scope": self._minio_scope(),
        }

    def clear_datasource_selections(
        self, cursor, tables: set[str], valid_names: set[str]
    ) -> int:
        removed = 0
        if "chat_sessions" in tables:
            cursor.execute("SELECT id, meta_data FROM chat_sessions")
            for session_id, raw_metadata in cursor.fetchall():
                metadata = _decode_json(raw_metadata, {})
                if not isinstance(metadata, dict):
                    continue
                cleaned, count = scrub_selection_metadata(metadata, valid_names)
                if count:
                    cursor.execute(
                        "UPDATE chat_sessions SET meta_data = %s WHERE id = %s",
                        (json.dumps(cleaned, ensure_ascii=False), session_id),
                    )
                    removed += count
        if "mass_answer_jobs" in tables:
            cursor.execute("SELECT id, selected_documents FROM mass_answer_jobs")
            for job_id, raw_selection in cursor.fetchall():
                selections = _decode_json(raw_selection, [])
                cleaned, count = _filter_selection_value(selections, valid_names)
                if count:
                    cursor.execute(
                        """
                        UPDATE mass_answer_jobs
                        SET selected_documents = %s::jsonb
                        WHERE id = %s
                        """,
                        (json.dumps(cleaned, ensure_ascii=False), job_id),
                    )
                    removed += count
        return removed

    def clear_knowledge_metadata(self, *, dry_run: bool = False) -> dict[str, Any]:
        before = self.inspect_postgres()
        if dry_run:
            return {
                "removed_documents": before["documents"],
                "removed_chunks": before["chunks"],
                "removed_selections": before["datasource_selections_to_clear"],
                "changed": False,
            }

        conn = self._connect_postgres()
        try:
            with conn:
                with conn.cursor() as cursor:
                    tables = self._table_names(cursor)
                    removed_selections = self.clear_datasource_selections(
                        cursor, tables, set()
                    )
                    if "documents" in tables:
                        cursor.execute("DELETE FROM documents")
                    if "collections" in tables:
                        cursor.execute(
                            """
                            UPDATE collections
                            SET document_count = 0, total_size = 0
                            """
                        )
            after = self.inspect_postgres()
            if after["documents"] or after["chunks"] or after["stale_selections"]:
                raise RuntimeError("PostgreSQL knowledge metadata is not clean")
            return {
                "removed_documents": before["documents"],
                "removed_chunks": before["chunks"],
                "removed_selections": removed_selections,
                "changed": bool(
                    before["documents"]
                    or before["chunks"]
                    or removed_selections
                ),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def clear_generated_knowledge(self, *, dry_run: bool = False) -> dict[str, Any]:
        root = self.config.generated_root
        documents = root / "DOCUMENTS"
        chunks = root / "CHUNKS"
        source_files = (
            [path for path in documents.iterdir() if not is_ignored_path(path)]
            if documents.is_dir()
            else []
        )
        chunk_files: list[Path] = []
        chunk_dirs: list[Path] = []
        if chunks.is_dir():
            for chunk_dir in chunks.iterdir():
                if not chunk_dir.is_dir() or chunk_dir.name.startswith("."):
                    continue
                chunk_dirs.append(chunk_dir)
                chunk_files.extend(discover_chunk_files(chunk_dir))
        if not dry_run:
            for path in source_files + chunk_files:
                path.unlink()
            for chunk_dir in chunk_dirs:
                if not any(chunk_dir.iterdir()):
                    chunk_dir.rmdir()
        return {
            "removed_source_documents": len(source_files),
            "removed_chunks": len(chunk_files),
            "changed": bool(source_files or chunk_files) and not dry_run,
        }

    def full_knowledge_reset(
        self, *, dry_run: bool = False, include_filesystem: bool = False
    ) -> ResetResult:
        result = ResetResult(dry_run=dry_run)
        phases = [
            ("qdrant", self.clear_qdrant_knowledge),
            ("minio", self.clear_minio_knowledge),
            ("postgres", self.clear_knowledge_metadata),
        ]
        if include_filesystem:
            phases.append(("filesystem", self.clear_generated_knowledge))
        for name, operation in phases:
            try:
                result.phases[name] = operation(dry_run=dry_run)
            except Exception as exc:
                result.success = False
                result.failed_phase = name
                result.error = f"{name} reset failed: {type(exc).__name__}"
                raise ResetPhaseError(result) from exc
        return result

    def close(self) -> None:
        if self._qdrant_client is not None and hasattr(
            self._qdrant_client, "close"
        ):
            self._qdrant_client.close()
        if self._minio_client is not None and hasattr(
            self._minio_client, "_http"
        ):
            self._minio_client._http.clear()


async def reset_postgres_schema(engine, metadata) -> None:
    """Drop and recreate only the repository-owned application tables."""
    from sqlalchemy import text

    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS chunk_versions CASCADE"))
        await connection.execute(
            text("DROP TABLE IF EXISTS knowledge_document_revisions CASCADE")
        )
        await connection.execute(text("DROP TABLE IF EXISTS mass_answer_jobs CASCADE"))
        await connection.run_sync(metadata.drop_all)
        await connection.run_sync(metadata.create_all)
        await connection.execute(text(CHUNK_VERSIONS_DDL))
        await connection.execute(text(KNOWLEDGE_DOCUMENT_REVISIONS_DDL))
        await connection.execute(text(MASS_ANSWER_JOBS_DDL))
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_mass_jobs_expiry "
                "ON mass_answer_jobs(expires_at)"
            )
        )


def _assert_reset_allowed(
    config: KnowledgeResetConfig,
    *,
    allow_production_reset: bool,
    confirmation: str | None,
) -> None:
    production = config.environment == "production"
    if production and not allow_production_reset:
        raise RuntimeError(
            "Production reset refused; pass --allow-production-reset only "
            "after an approved change procedure"
        )
    expected = PRODUCTION_RESET_CONFIRMATION if production else RESET_CONFIRMATION
    if confirmation != expected:
        raise RuntimeError(f"Reset confirmation must exactly match: {expected}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--validate", action="store_true")
    action.add_argument("--reset-knowledge", action="store_true")
    action.add_argument("--full-dev-reset", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--allow-production-reset", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    service = KnowledgeResetService.from_environment()
    try:
        if args.validate:
            report = service.validate_clean_state()
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return 0 if report["clean"] else 1

        if args.full_dev_reset and service.config.environment == "production":
            raise RuntimeError("FULL_DEV_RESET is never allowed in production")
        if not args.dry_run:
            _assert_reset_allowed(
                service.config,
                allow_production_reset=args.allow_production_reset,
                confirmation=args.confirm,
            )
        result = service.full_knowledge_reset(
            dry_run=args.dry_run,
            include_filesystem=args.full_dev_reset,
        )
        print(json.dumps(result.public_dict(), indent=2, ensure_ascii=False))
        return 0
    except ResetPhaseError as exc:
        print(
            json.dumps(exc.result.public_dict(), indent=2, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(f"Knowledge reset refused or failed: {exc}", file=sys.stderr)
        return 2
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
