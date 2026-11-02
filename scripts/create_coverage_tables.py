#!/usr/bin/env python3
"""Create missing coverage tables, or report their presence with --check."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coverage_check.schema import SCHEMA_SQL, TABLES  # noqa: E402
from scripts.manage_web_users import connect, database_identity, load_config  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    connection = None
    try:
        config = load_config()
        connection = connect(config)
        database_identity(connection, config)
        if not args.check:
            with connection.cursor() as cursor:
                cursor.execute(SCHEMA_SQL)
            connection.commit()
        with connection.cursor() as cursor:
            present = []
            for table in TABLES:
                cursor.execute("SELECT to_regclass(%s)", (table,))
                found = cursor.fetchone()[0] is not None
                present.append(found)
                print(f"{table}: {'present' if found else 'missing'}")
        connection.commit()
        return 0 if all(present) else 1
    except Exception as exc:
        print(f"error: {type(exc).__name__}")
        return 2
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
