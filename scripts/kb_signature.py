#!/usr/bin/env python3
"""Create and compare read-only, content-safe RagBot KB signatures.

Exit codes: 0 means FULL_MATCH, 1 means valid signatures differ, and 2 means
invalid input or an execution/configuration error.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dotenv import load_dotenv

load_dotenv(REPOSITORY_ROOT / ".env", override=False)

import psycopg2.extras
from qdrant_client import QdrantClient

from new_architecture.app.services.history.database import DatabaseManager
from utils.read_only_audit import (
    canonical_sha256,
    json_safe,
    text_sha256,
    vector_float32_le_signature,
    write_json_report,
)


SCHEMA_VERSION = 1
TERMINAL_DIFFERENCE_LIMIT = 20
POSTGRES_CHUNK_QUERY = """
    SELECT
        c.id AS chunk_id,
        c.document_id,
        c.chunk_index,
        c.content,
        c.chunk_type,
        c.page_number,
        c.meta_data AS chunk_meta_data,
        d.title AS document_title
    FROM chunks c
    LEFT JOIN documents d ON d.id = c.document_id
    ORDER BY c.id ASC, c.document_id ASC, c.chunk_index ASC
"""


def _logical_id(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    result = str(value).strip()
    return result or None


def _mapping_metadata(
    document_id: Any, chunk_index: Any, document_title: Any
) -> dict[str, Any]:
    return {
        "document_id": _logical_id(document_id),
        "chunk_index": chunk_index,
        "document_title_sha256": (
            text_sha256(document_title)
            if isinstance(document_title, str)
            else None
        ),
    }


def _postgres_signature() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    database = DatabaseManager()
    connection = database.get_connection()
    records: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    identifiers: list[str] = []
    missing_content_ids: list[str] = []
    try:
        connection.set_session(readonly=True, autocommit=False)
        with connection.cursor(
            name="ragbot_kb_signature_chunks",
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cursor:
            cursor.itersize = 1000
            cursor.execute(POSTGRES_CHUNK_QUERY)
            for ordinal, row in enumerate(cursor, start=1):
                chunk_id = _logical_id(row.get("chunk_id"))
                document_title = row.get("document_title")
                content = row.get("content")
                issues: list[str] = []
                if chunk_id is None:
                    issues.append("missing_chunk_id")
                if _logical_id(row.get("document_id")) is None:
                    issues.append("missing_document_id")
                if not isinstance(row.get("chunk_index"), int):
                    issues.append("invalid_chunk_index")
                if not isinstance(document_title, str) or not document_title.strip():
                    issues.append("missing_document_title")
                if not isinstance(content, str) or not content:
                    issues.append("missing_content")
                    if chunk_id is not None:
                        missing_content_ids.append(chunk_id)

                mapping = _mapping_metadata(
                    row.get("document_id"),
                    row.get("chunk_index"),
                    document_title,
                )
                metadata = {
                    **mapping,
                    "chunk_type": row.get("chunk_type"),
                    "page_number": row.get("page_number"),
                    "chunk_meta_data": row.get("chunk_meta_data"),
                }
                record = {
                    "chunk_id": chunk_id,
                    "document_id": mapping["document_id"],
                    "chunk_index": row.get("chunk_index"),
                    "document_title_sha256": mapping["document_title_sha256"],
                    "content_sha256": (
                        text_sha256(content) if isinstance(content, str) else None
                    ),
                    "metadata_sha256": canonical_sha256(metadata),
                    "cross_store_metadata_sha256": canonical_sha256(mapping),
                }
                records.append(record)
                if chunk_id is not None:
                    identifiers.append(chunk_id)
                if issues:
                    malformed.append({
                        "record_ordinal": ordinal,
                        "chunk_id": chunk_id,
                        "issues": issues,
                    })
    finally:
        connection.rollback()
        connection.close()

    records.sort(key=lambda row: (
        row.get("chunk_id") or "",
        row.get("document_id") or "",
        row.get("chunk_index") if isinstance(row.get("chunk_index"), int) else -1,
        row.get("content_sha256") or "",
    ))
    counts = collections.Counter(identifiers)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    unique = {
        row["chunk_id"]: row
        for row in records
        if row["chunk_id"] is not None and counts[row["chunk_id"]] == 1
    }
    return ({
        "record_count": len(records),
        "aggregate_sha256": canonical_sha256(records),
        "duplicate_logical_ids": duplicates,
        "malformed_rows": malformed,
        "missing_identifier_count": sum(
            row["chunk_id"] is None for row in records
        ),
        "missing_content_count": len(missing_content_ids),
        "missing_content_ids": sorted(set(missing_content_ids)),
        "records": records,
    }, unique)


def _collection_config(info: Any) -> dict[str, Any]:
    config = info.config
    params = config.params
    return json_safe({
        "vectors": getattr(params, "vectors", None),
        "sparse_vectors": getattr(params, "sparse_vectors", None),
        "shard_number": getattr(params, "shard_number", None),
        "replication_factor": getattr(params, "replication_factor", None),
        "write_consistency_factor": getattr(
            params, "write_consistency_factor", None
        ),
        "on_disk_payload": getattr(params, "on_disk_payload", None),
        "hnsw_config": getattr(config, "hnsw_config", None),
        "quantization_config": getattr(config, "quantization_config", None),
        "optimizer_config": getattr(config, "optimizer_config", None),
        "strict_mode_config": getattr(config, "strict_mode_config", None),
    })


def _expected_vector_dimensions(info: Any) -> dict[str, int]:
    vectors = info.config.params.vectors
    if isinstance(vectors, dict):
        return {
            str(name): int(params.size)
            for name, params in vectors.items()
        }
    size = getattr(vectors, "size", None)
    return {"": int(size)} if size is not None else {}


def _dense_values(value: Any) -> Iterable[float] | None:
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (list, tuple)):
            return None
        return value
    if hasattr(value, "tolist"):
        converted = value.tolist()
        if isinstance(converted, list) and (
            not converted or not isinstance(converted[0], list)
        ):
            return converted
    return None


def _vector_records(raw_vector: Any) -> list[dict[str, Any]]:
    vectors = raw_vector if isinstance(raw_vector, dict) else {"": raw_vector}
    signatures: list[dict[str, Any]] = []
    for name, raw in sorted(vectors.items(), key=lambda item: str(item[0])):
        values = _dense_values(raw)
        if values is None:
            signatures.append({
                "name": str(name),
                "present": False,
                "dimension": None,
                "sha256": None,
            })
            continue
        signature = vector_float32_le_signature(values)
        signatures.append({
            "name": str(name),
            "present": True,
            **signature,
        })
    if not signatures:
        signatures.append({
            "name": "",
            "present": False,
            "dimension": None,
            "sha256": None,
        })
    return signatures


def _qdrant_client() -> QdrantClient:
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
        api_key=os.getenv("QDRANT_API_KEY"),
        https=os.getenv("QDRANT_HTTPS", "false").strip().lower() == "true",
        timeout=30.0,
    )


def _qdrant_signature() -> tuple[
    dict[str, Any], dict[str, dict[str, Any]]
]:
    collection_name = os.getenv("QDRANT_COLLECTION", "hihelp_embeddings")
    client = _qdrant_client()
    records: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    identifiers: list[str] = []
    try:
        info = client.get_collection(collection_name)
        config = _collection_config(info)
        expected_dimensions = _expected_vector_dimensions(info)
        offset = None
        seen_offsets: set[str] = set()
        while True:
            points, next_offset = client.scroll(
                collection_name=collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            for point in points:
                payload = dict(point.payload or {})
                chunk_id = _logical_id(payload.get("chunk_id"))
                point_id = _logical_id(point.id)
                issues: list[str] = []
                if chunk_id is None:
                    issues.append("missing_logical_chunk_id")
                mapping = _mapping_metadata(
                    payload.get("document_id"),
                    payload.get("chunk_index"),
                    payload.get("document"),
                )
                if mapping["document_id"] is None:
                    issues.append("missing_document_id")
                if not isinstance(payload.get("chunk_index"), int):
                    issues.append("invalid_chunk_index")
                if mapping["document_title_sha256"] is None:
                    issues.append("missing_document_title")

                content_field = next(
                    (
                        key for key in ("content", "text")
                        if key in payload
                    ),
                    None,
                )
                payload_content = (
                    payload.get(content_field) if content_field else None
                )
                content_sha256 = (
                    text_sha256(payload_content)
                    if isinstance(payload_content, str)
                    else None
                )
                if content_field and not isinstance(payload_content, str):
                    issues.append("invalid_payload_content")

                vectors = _vector_records(point.vector)
                record = {
                    "logical_chunk_id": chunk_id,
                    "qdrant_point_id": point_id,
                    "document_id": mapping["document_id"],
                    "chunk_index": payload.get("chunk_index"),
                    "document_title_sha256": mapping["document_title_sha256"],
                    "payload_metadata_sha256": canonical_sha256(mapping),
                    "payload_sha256": canonical_sha256(payload),
                    "payload_content_field": content_field,
                    "content_sha256": content_sha256,
                    "vector_present": all(item["present"] for item in vectors),
                    "vectors": vectors,
                }
                records.append(record)
                if chunk_id is not None:
                    identifiers.append(chunk_id)
                if issues:
                    malformed.append({
                        "qdrant_point_id": point_id,
                        "logical_chunk_id": chunk_id,
                        "issues": issues,
                    })

            if next_offset is None:
                break
            offset_key = str(next_offset)
            if offset_key in seen_offsets:
                raise RuntimeError("Qdrant scroll returned a repeated offset")
            seen_offsets.add(offset_key)
            offset = next_offset
    finally:
        client.close()

    records.sort(key=lambda row: (
        row.get("logical_chunk_id") or "",
        row.get("payload_sha256") or "",
        canonical_sha256(row.get("vectors") or []),
        row.get("qdrant_point_id") or "",
    ))
    counts = collections.Counter(identifiers)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    unique = {
        row["logical_chunk_id"]: row
        for row in records
        if row["logical_chunk_id"] is not None
        and counts[row["logical_chunk_id"]] == 1
    }
    missing_vectors = sorted({
        row["logical_chunk_id"] or f"point:{row['qdrant_point_id']}"
        for row in records
        if not row["vector_present"]
    })
    wrong_dimensions = sorted({
        row["logical_chunk_id"] or f"point:{row['qdrant_point_id']}"
        for row in records
        for vector in row["vectors"]
        if vector["present"] and (
            vector["name"] not in expected_dimensions
            or vector["dimension"] != expected_dimensions[vector["name"]]
        )
    })
    logical_records = [
        {
            key: row[key]
            for key in (
                "logical_chunk_id",
                "document_id",
                "chunk_index",
                "document_title_sha256",
                "payload_metadata_sha256",
                "payload_sha256",
                "payload_content_field",
                "content_sha256",
            )
        }
        for row in records
    ]
    vector_records = [
        {
            "logical_chunk_id": row["logical_chunk_id"],
            "vectors": row["vectors"],
        }
        for row in records
    ]
    return ({
        "point_count": len(records),
        "logical_aggregate_sha256": canonical_sha256(logical_records),
        "vector_aggregate_sha256": canonical_sha256(vector_records),
        "vector_hash_representation": (
            "SHA256 over dense vector values converted one-by-one to "
            "IEEE-754 float32 little-endian bytes"
        ),
        "collection_config_sha256": canonical_sha256(config),
        "collection_config": config,
        "expected_vector_dimensions": expected_dimensions,
        "duplicate_logical_ids": duplicates,
        "malformed_points": malformed,
        "missing_logical_id_count": sum(
            row["logical_chunk_id"] is None for row in records
        ),
        "missing_vector_count": len(missing_vectors),
        "missing_vector_ids": missing_vectors,
        "wrong_dimension_count": len(wrong_dimensions),
        "wrong_dimension_ids": wrong_dimensions,
        "records": records,
    }, unique)


def _cross_store_signature(
    postgres: dict[str, Any],
    pg_records: dict[str, dict[str, Any]],
    qdrant: dict[str, Any],
    qdrant_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pg_ids = set(pg_records)
    qdrant_ids = set(qdrant_records)
    postgres_only = sorted(pg_ids - qdrant_ids)
    qdrant_only = sorted(qdrant_ids - pg_ids)
    metadata_mismatches = sorted(
        chunk_id
        for chunk_id in pg_ids & qdrant_ids
        if pg_records[chunk_id]["cross_store_metadata_sha256"]
        != qdrant_records[chunk_id]["payload_metadata_sha256"]
    )
    content_mismatches = sorted(
        chunk_id
        for chunk_id in pg_ids & qdrant_ids
        if qdrant_records[chunk_id]["content_sha256"] is not None
        and pg_records[chunk_id]["content_sha256"]
        != qdrant_records[chunk_id]["content_sha256"]
    )
    duplicate_ids = sorted(set(
        postgres["duplicate_logical_ids"] + qdrant["duplicate_logical_ids"]
    ))
    consistent = not any((
        postgres_only,
        qdrant_only,
        duplicate_ids,
        metadata_mismatches,
        content_mismatches,
        postgres["malformed_rows"],
        qdrant["malformed_points"],
        qdrant["missing_vector_ids"],
        qdrant["wrong_dimension_ids"],
    ))
    return {
        "postgres_only_count": len(postgres_only),
        "postgres_only_ids": postgres_only,
        "qdrant_only_count": len(qdrant_only),
        "qdrant_only_ids": qdrant_only,
        "duplicate_logical_id_count": len(duplicate_ids),
        "duplicate_logical_ids": duplicate_ids,
        "metadata_mismatch_count": len(metadata_mismatches),
        "metadata_mismatch_ids": metadata_mismatches,
        "content_mismatch_count": len(content_mismatches),
        "content_mismatch_ids": content_mismatches,
        "missing_vector_count": qdrant["missing_vector_count"],
        "missing_vector_ids": qdrant["missing_vector_ids"],
        "wrong_dimension_count": qdrant["wrong_dimension_count"],
        "wrong_dimension_ids": qdrant["wrong_dimension_ids"],
        "consistent": consistent,
    }


def create_signature(label: str) -> dict[str, Any]:
    postgres, pg_records = _postgres_signature()
    qdrant, qdrant_records = _qdrant_signature()
    cross_store = _cross_store_signature(
        postgres, pg_records, qdrant, qdrant_records
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generation": {
            "label": label,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "postgres": postgres,
        "qdrant": qdrant,
        "cross_store": cross_store,
    }


def _validate_signature(payload: Any, source: Path) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"{source}: unsupported or missing schema_version")
    for section in ("generation", "postgres", "qdrant", "cross_store"):
        if not isinstance(payload.get(section), dict):
            raise ValueError(f"{source}: missing {section} object")
    if not isinstance(payload["postgres"].get("records"), list):
        raise ValueError(f"{source}: postgres.records must be a list")
    if not isinstance(payload["qdrant"].get("records"), list):
        raise ValueError(f"{source}: qdrant.records must be a list")
    return payload


def load_signature(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read signature {path}") from exc
    return _validate_signature(payload, path)


def _record_groups(
    records: list[dict[str, Any]], key: str
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        logical_id = _logical_id(record.get(key))
        if logical_id is not None:
            groups[logical_id].append(record)
    return dict(groups)


def _field_mismatches(
    left: dict[str, list[dict[str, Any]]],
    right: dict[str, list[dict[str, Any]]],
    field: str,
) -> list[dict[str, Any]]:
    mismatches = []
    for chunk_id in sorted(set(left) & set(right)):
        left_values = sorted(str(row.get(field)) for row in left[chunk_id])
        right_values = sorted(str(row.get(field)) for row in right[chunk_id])
        if left_values != right_values:
            mismatches.append({
                "chunk_id": chunk_id,
                "left": left_values,
                "right": right_values,
            })
    return mismatches


def _config_differences(left: Any, right: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(left, dict) and isinstance(right, dict):
        differences: list[dict[str, Any]] = []
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                differences.append({
                    "field": child,
                    "left": left.get(key),
                    "right": right.get(key),
                })
            else:
                differences.extend(_config_differences(
                    left[key], right[key], child
                ))
        return differences
    if left != right:
        return [{"field": path, "left": left, "right": right}]
    return []


def compare_signatures(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    left_pg = _record_groups(left["postgres"]["records"], "chunk_id")
    right_pg = _record_groups(right["postgres"]["records"], "chunk_id")
    left_qd = _record_groups(left["qdrant"]["records"], "logical_chunk_id")
    right_qd = _record_groups(right["qdrant"]["records"], "logical_chunk_id")

    pg_only_left = sorted(set(left_pg) - set(right_pg))
    pg_only_right = sorted(set(right_pg) - set(left_pg))
    content_mismatches = _field_mismatches(
        left_pg, right_pg, "content_sha256"
    )
    postgres_metadata_mismatches = _field_mismatches(
        left_pg, right_pg, "metadata_sha256"
    )
    aggregate_mismatches: list[dict[str, Any]] = []
    aggregate_fields = (
        ("postgres.aggregate_sha256", left["postgres"], right["postgres"], "aggregate_sha256"),
        (
            "qdrant.logical_aggregate_sha256",
            left["qdrant"],
            right["qdrant"],
            "logical_aggregate_sha256",
        ),
        (
            "qdrant.vector_aggregate_sha256",
            left["qdrant"],
            right["qdrant"],
            "vector_aggregate_sha256",
        ),
        (
            "qdrant.collection_config_sha256",
            left["qdrant"],
            right["qdrant"],
            "collection_config_sha256",
        ),
    )
    for field_name, left_section, right_section, key in aggregate_fields:
        if left_section.get(key) != right_section.get(key):
            aggregate_mismatches.append({
                "field": field_name,
                "left": left_section.get(key),
                "right": right_section.get(key),
            })
    postgres_aggregate_match = not any(
        row["field"] == "postgres.aggregate_sha256"
        for row in aggregate_mismatches
    )
    postgres_match = not any((
        pg_only_left,
        pg_only_right,
        content_mismatches,
        postgres_metadata_mismatches,
        left["postgres"].get("malformed_rows"),
        right["postgres"].get("malformed_rows"),
    )) and postgres_aggregate_match and left["postgres"].get("record_count") == right["postgres"].get(
        "record_count"
    )

    qdrant_only_left = sorted(set(left_qd) - set(right_qd))
    qdrant_only_right = sorted(set(right_qd) - set(left_qd))
    qdrant_metadata_mismatches = _field_mismatches(
        left_qd, right_qd, "payload_sha256"
    )
    vector_dimension_mismatches = _field_mismatches(
        left_qd, right_qd, "vectors"
    )
    vector_hash_mismatches: list[dict[str, Any]] = []
    vector_dimension_only: list[dict[str, Any]] = []
    for mismatch in vector_dimension_mismatches:
        chunk_id = mismatch["chunk_id"]
        left_vectors = left_qd[chunk_id][0].get("vectors", [])
        right_vectors = right_qd[chunk_id][0].get("vectors", [])
        left_dims = [(v.get("name"), v.get("dimension")) for v in left_vectors]
        right_dims = [(v.get("name"), v.get("dimension")) for v in right_vectors]
        left_hashes = [(v.get("name"), v.get("sha256")) for v in left_vectors]
        right_hashes = [(v.get("name"), v.get("sha256")) for v in right_vectors]
        if left_dims != right_dims:
            vector_dimension_only.append({
                "chunk_id": chunk_id,
                "left": left_dims,
                "right": right_dims,
            })
        if left_hashes != right_hashes:
            vector_hash_mismatches.append({
                "chunk_id": chunk_id,
                "left": left_hashes,
                "right": right_hashes,
            })
    point_id_mismatches = []
    for chunk_id in sorted(set(left_qd) & set(right_qd)):
        left_ids = sorted(
            str(row.get("qdrant_point_id")) for row in left_qd[chunk_id]
        )
        right_ids = sorted(
            str(row.get("qdrant_point_id")) for row in right_qd[chunk_id]
        )
        if left_ids != right_ids:
            point_id_mismatches.append({
                "chunk_id": chunk_id,
                "left": left_ids,
                "right": right_ids,
            })

    qdrant_logical_aggregate_match = not any(
        row["field"] == "qdrant.logical_aggregate_sha256"
        for row in aggregate_mismatches
    )
    qdrant_logical_match = not any((
        qdrant_only_left,
        qdrant_only_right,
        qdrant_metadata_mismatches,
        left["qdrant"].get("malformed_points"),
        right["qdrant"].get("malformed_points"),
    )) and qdrant_logical_aggregate_match and left["qdrant"].get("point_count") == right["qdrant"].get(
        "point_count"
    )
    vector_aggregate_match = not any(
        row["field"] == "qdrant.vector_aggregate_sha256"
        for row in aggregate_mismatches
    )
    vector_exact_match = not any((
        qdrant_only_left,
        qdrant_only_right,
        vector_dimension_only,
        vector_hash_mismatches,
        left["qdrant"].get("missing_vector_ids"),
        right["qdrant"].get("missing_vector_ids"),
    )) and vector_aggregate_match
    config_differences = _config_differences(
        left["qdrant"].get("collection_config"),
        right["qdrant"].get("collection_config"),
    )
    config_aggregate_match = not any(
        row["field"] == "qdrant.collection_config_sha256"
        for row in aggregate_mismatches
    )
    config_match = not config_differences and config_aggregate_match
    left_health = left["cross_store"].get("consistent") is True
    right_health = right["cross_store"].get("consistent") is True
    full_match = all((
        postgres_match,
        qdrant_logical_match,
        vector_exact_match,
        config_match,
        left_health,
        right_health,
    ))
    return {
        "schema_version": 1,
        "labels": {
            "left": left["generation"].get("label"),
            "right": right["generation"].get("label"),
        },
        "status": {
            "POSTGRES_LOGICAL_MATCH": postgres_match,
            "QDRANT_LOGICAL_MATCH": qdrant_logical_match,
            "QDRANT_VECTOR_EXACT_MATCH": vector_exact_match,
            "QDRANT_COLLECTION_CONFIG_MATCH": config_match,
            "CROSS_STORE_HEALTH_LEFT": left_health,
            "CROSS_STORE_HEALTH_RIGHT": right_health,
            "FULL_MATCH": full_match,
        },
        "differences": {
            "postgres_only_left": pg_only_left,
            "postgres_only_right": pg_only_right,
            "content_mismatches": content_mismatches,
            "postgres_metadata_mismatches": postgres_metadata_mismatches,
            "qdrant_only_left": qdrant_only_left,
            "qdrant_only_right": qdrant_only_right,
            "qdrant_metadata_mismatches": qdrant_metadata_mismatches,
            "vector_hash_mismatches": vector_hash_mismatches,
            "vector_dimension_mismatches": vector_dimension_only,
            "collection_config_mismatches": config_differences,
            "aggregate_mismatches": aggregate_mismatches,
            "qdrant_point_id_mismatches_diagnostic_only": point_id_mismatches,
        },
    }


def _print_create_summary(signature: dict[str, Any], output: Path) -> None:
    pg = signature["postgres"]
    qd = signature["qdrant"]
    cross = signature["cross_store"]
    print(f"OUTPUT={output}")
    print(f"POSTGRES_RECORDS={pg['record_count']}")
    print(f"POSTGRES_AGGREGATE_SHA256={pg['aggregate_sha256']}")
    print(f"QDRANT_POINTS={qd['point_count']}")
    print(f"QDRANT_LOGICAL_AGGREGATE_SHA256={qd['logical_aggregate_sha256']}")
    print(f"QDRANT_VECTOR_AGGREGATE_SHA256={qd['vector_aggregate_sha256']}")
    print(f"QDRANT_COLLECTION_CONFIG_SHA256={qd['collection_config_sha256']}")
    print(f"POSTGRES_ONLY={cross['postgres_only_count']}")
    print(f"QDRANT_ONLY={cross['qdrant_only_count']}")
    print(f"DUPLICATE_LOGICAL_IDS={cross['duplicate_logical_id_count']}")
    print(f"MISSING_VECTORS={cross['missing_vector_count']}")
    print(f"WRONG_VECTOR_DIMENSION={cross['wrong_dimension_count']}")
    print(f"CROSS_STORE_CONSISTENT={str(cross['consistent']).lower()}")


def _print_comparison(report: dict[str, Any]) -> None:
    for key, value in report["status"].items():
        print(f"{key}={str(value).upper()}")
    differences = report["differences"]
    labels = report["labels"]
    headings = (
        ("POSTGRES_ONLY_IN_LEFT", "postgres_only_left"),
        ("POSTGRES_ONLY_IN_RIGHT", "postgres_only_right"),
        ("CONTENT_MISMATCH", "content_mismatches"),
        ("DOCUMENT_METADATA_MISMATCH", "postgres_metadata_mismatches"),
        ("QDRANT_ONLY_IN_LEFT", "qdrant_only_left"),
        ("QDRANT_ONLY_IN_RIGHT", "qdrant_only_right"),
        ("QDRANT_METADATA_MISMATCH", "qdrant_metadata_mismatches"),
        ("VECTOR_HASH_MISMATCH", "vector_hash_mismatches"),
        ("VECTOR_DIMENSION_MISMATCH", "vector_dimension_mismatches"),
        ("COLLECTION_CONFIG_MISMATCH", "collection_config_mismatches"),
        ("AGGREGATE_MISMATCH", "aggregate_mismatches"),
        (
            "QDRANT_POINT_ID_MISMATCH_DIAGNOSTIC_ONLY",
            "qdrant_point_id_mismatches_diagnostic_only",
        ),
    )
    for heading, key in headings:
        rows = differences[key]
        if not rows:
            continue
        print(
            f"{heading} ({labels['left']} vs {labels['right']}): "
            f"{len(rows)}"
        )
        for row in rows[:TERMINAL_DIFFERENCE_LIMIT]:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
        if len(rows) > TERMINAL_DIFFERENCE_LIMIT:
            print(f"... {len(rows) - TERMINAL_DIFFERENCE_LIMIT} more")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or compare read-only RagBot KB signatures. Exit codes: "
            "0=FULL_MATCH, 1=mismatch, 2=invalid input/execution error."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="create a local KB signature")
    create.add_argument("--label", required=True)
    create.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare", help="compare two signatures")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            signature = create_signature(args.label)
            write_json_report(args.output, signature)
            _print_create_summary(signature, args.output)
            return 0
        left = load_signature(args.left)
        right = load_signature(args.right)
        report = compare_signatures(left, right)
        if args.output:
            write_json_report(args.output, report)
        _print_comparison(report)
        return 0 if report["status"]["FULL_MATCH"] else 1
    except Exception as exc:
        print(f"ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
