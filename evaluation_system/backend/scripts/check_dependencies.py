"""Read-only dependency check; never connects to services."""

from __future__ import annotations

import importlib
import sys


REQUIRED = (
    "fastapi", "pydantic", "sqlalchemy", "alembic", "asyncpg", "psycopg2",
    "openpyxl", "httpx", "dotenv", "multipart", "uvicorn",
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
