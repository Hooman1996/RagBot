"""Read-only diagnostics for the Knowledge Management update pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = {
    "POSTGRES_PASSWORD",
    "QDRANT_API_KEY",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
}
CONFIG_NAMES = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "QDRANT_URL",
    "QDRANT_HOST",
    "QDRANT_PORT",
    "QDRANT_COLLECTION",
    "MINIO_ENDPOINT",
    "MINIO_BUCKET",
    "DATA_INSERTION_DIRECTORY",
    "KNOWLEDGE_BASE_CSV",
    "WEB_CONCURRENCY",
)


def _configured(name: str) -> dict[str, Any]:
    value = os.getenv(name)
    return {
        "name": name,
        "configured": bool(value),
        "value": None if name in SECRET_NAMES else value,
    }


def check_configuration() -> dict[str, Any]:
    values = [_configured(name) for name in CONFIG_NAMES]
    return {
        "status": "ok",
        "values": values,
        "notes": [
            "Knowledge Manager and RAG both use POSTGRES_* and QDRANT_COLLECTION.",
            "QDRANT_URL is not used by the verified runtime; QDRANT_HOST/PORT are.",
            "No secret values are emitted by this command.",
        ],
    }


def check_paths() -> dict[str, Any]:
    configured_root = os.getenv("DATA_INSERTION_DIRECTORY")
    data_root = (
        Path(configured_root).expanduser()
        if configured_root
        else ROOT / "data_insertion_chunks"
    ).resolve()
    paths = [
        data_root,
        data_root / "DOCUMENTS",
        data_root / "CHUNKS",
        data_root / "CHUNKS" / "General_FAQ",
    ]
    return {
        "status": "ok",
        "paths": [
            {
                "path": str(path),
                "exists": path.exists(),
                "is_directory": path.is_dir(),
                "readable": os.access(path, os.R_OK) if path.exists() else False,
                "writable_permission": (
                    os.access(path, os.W_OK) if path.exists() else False
                ),
                "runtime_answer_dependency": False,
            }
            for path in paths
        ],
        "note": (
            "These paths are ingestion inputs. Live answer retrieval reads "
            "PostgreSQL chunks and Qdrant, not these files."
        ),
    }


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _tcp_check(host: str | None, port: str | int | None) -> dict[str, Any]:
    if not host or not port:
        return {"status": "not_configured"}
    try:
        with socket.create_connection((host, int(port)), timeout=3):
            return {"status": "reachable", "host": host, "port": int(port)}
    except Exception as exc:
        return {
            "status": "unreachable",
            "host": host,
            "port": int(port),
            "error_type": type(exc).__name__,
        }


def check_connections() -> dict[str, Any]:
    postgres = _tcp_check(
        os.getenv("POSTGRES_HOST"), os.getenv("POSTGRES_PORT", "5432")
    )
    qdrant = _tcp_check(
        os.getenv("QDRANT_HOST"), os.getenv("QDRANT_PORT", "6333")
    )
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "")
    minio_host, separator, minio_port = minio_endpoint.rpartition(":")
    minio = _tcp_check(
        minio_host if separator else minio_endpoint,
        minio_port if separator else "9000",
    )
    return {
        "status": "ok",
        "tcp": {"postgresql": postgres, "qdrant": qdrant, "minio": minio},
        "python_drivers": {
            "psycopg2": _module_available("psycopg2"),
            "qdrant_client": _module_available("qdrant_client"),
            "minio": _module_available("minio"),
        },
        "note": (
            "TCP checks are read-only and do not prove database, collection, "
            "or bucket identity. Use the documented authenticated commands."
        ),
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Read-only knowledge-update diagnostics (never prints secrets)."
    )
    command.add_argument("--check-connections", action="store_true")
    command.add_argument("--check-paths", action="store_true")
    command.add_argument("--check-configuration", action="store_true")
    command.add_argument("--synthetic-update-test", action="store_true")
    command.add_argument("--confirm-synthetic-write", action="store_true")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.synthetic_update_test:
        if not args.confirm_synthetic_write:
            print(
                json.dumps(
                    {
                        "status": "refused",
                        "reason": "explicit --confirm-synthetic-write is required",
                    }
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "status": "not_run",
                    "reason": (
                        "No repository-owned isolated PostgreSQL/Qdrant/MinIO "
                        "test namespace is configured. Configure one and run the "
                        "documented integration procedure; live records are never used."
                    ),
                }
            )
        )
        return 3

    selected = any(
        (args.check_connections, args.check_paths, args.check_configuration)
    )
    report: dict[str, Any] = {
        "read_only": True,
        "working_directory": str(Path.cwd()),
        "repository_root": str(ROOT),
    }
    if args.check_configuration or not selected:
        report["configuration"] = check_configuration()
    if args.check_paths or not selected:
        report["paths"] = check_paths()
    if args.check_connections or not selected:
        report["connections"] = check_connections()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
