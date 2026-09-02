"""Read-only dependency check; never connects to services."""

from __future__ import annotations

import importlib
import sys


REQUIRED = (
    "fastapi", "pydantic", "sqlalchemy", "alembic", "asyncpg", "psycopg2",
    "celery", "redis", "openpyxl", "httpx", "dotenv", "openai", "qdrant_client",
    "langgraph", "langchain_classic", "numpy", "torch", "transformers",
    "parsivar", "rank_bm25", "tqdm",
)


def main() -> int:
    missing = []
    for module in REQUIRED:
        try:
            importlib.import_module(module)
        except Exception:
            missing.append(module)
    if missing:
        print("Missing evaluation runtime dependencies: " + ", ".join(missing))
        return 1
    print("Evaluation backend dependencies are importable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
