#!/usr/bin/env python3
"""Read legacy coverage folders without changing any files. Print counts only."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from psycopg2.extras import Json, execute_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coverage_check.schema import TABLES  # noqa: E402
from coverage_check.store import CHUNK_KEY, RUN_ID, STATES  # noqa: E402
from scripts.manage_web_users import connect, load_config  # noqa: E402


class Unreadable(ValueError):
    pass


def inside(path, root):
    """Reject symbolic links in every component, and paths outside checks."""
    if not path.resolve().is_relative_to(root):
        raise Unreadable()
    current = path
    while current != root:
        if current.is_symlink():
            raise Unreadable()
        current = current.parent
    if root.is_symlink():
        raise Unreadable()
    return path


def read_json(path, root):
    with inside(path, root).open(encoding="utf-8") as stream:
        return json.load(stream)


def records(folder, root, pattern):
    inside(folder, root)
    if not folder.exists():
        return {}
    found = {}
    for path in folder.glob("*.json"):
        if path.is_symlink() or not pattern(path.stem):
            continue
        found[path.stem] = read_json(path, root)
    return found


def read_run(path, root):
    inside(path, root)
    meta = read_json(path / "meta.json", root)
    rows = read_json(path / "input.json", root)
    if meta["run_id"] != path.name or meta["state"] not in STATES:
        raise Unreadable()
    datetime.fromisoformat(meta["created_at"])
    if len(rows) != meta["row_count"] or len({r["row"] for r in rows}) != len(rows):
        raise Unreadable()
    results = records(path / "results", root, str.isdigit)
    suggestions = records(path / "suggestions", root, str.isdigit)
    chunks = records(path / "chunks", root, lambda value: CHUNK_KEY.fullmatch(value))
    state = "interrupted" if meta["state"] in {"queued", "running"} else meta["state"]
    run = (path.name, meta["owner_id"], meta["created_at"], meta["file_name"], Json(meta["documents"]),
           Json(meta["settings"]), meta.get("prompt_version") or "", state, len(rows))
    values = []
    for row in rows:
        if type(row["row"]) is not int or row["row"] < 1 or not isinstance(row["id"], str) or not isinstance(row["question"], str):
            raise Unreadable()
        result, suggestion = results.get(str(row["row"])), suggestions.get(str(row["row"]))
        values.append((path.name, row["row"], Json(row), result["result"] if result else None,
                       Json(result) if result is not None else None,
                       suggestion["status"] if suggestion else None,
                       Json(suggestion) if suggestion is not None else None))
    return run, values, [(path.name, key, item["text"]) for key, item in chunks.items()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    connection = None
    try:
        connection = connect(load_config())
        with connection.cursor() as cursor:
            for table in TABLES:
                cursor.execute("SELECT to_regclass(%s)", (table,))
                if cursor.fetchone()[0] is None:
                    print("error: tables_missing")
                    print("Run scripts/create_coverage_tables.py first.")
                    return 1
        connection.commit()
        root = args.folder.absolute() / "checks"
        counts = {"runs found": 0, "runs imported": 0, "runs already present": 0,
                  "runs skipped (unreadable)": 0}
        if root.is_symlink() or root.resolve() != root:
            raise Unreadable()
        for path in sorted(root.iterdir()):
            if not RUN_ID.fullmatch(path.name):
                continue
            counts["runs found"] += 1
            try:
                run, rows, chunks = read_run(path, root)
            except (OSError, ValueError, KeyError, TypeError):
                counts["runs skipped (unreadable)"] += 1
                continue
            with connection:
                with connection.cursor() as cursor:
                    if args.dry_run:
                        cursor.execute("SELECT 1 FROM coverage_runs WHERE run_id = %s", (path.name,))
                        exists = cursor.fetchone() is not None
                    else:
                        cursor.execute("""INSERT INTO coverage_runs
                            (run_id, owner_id, created_at, file_name, documents, settings, prompt_version, state, row_count)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING run_id""", run)
                        exists = cursor.fetchone() is None
                        if not exists:
                            execute_values(cursor, """INSERT INTO coverage_rows
                                (run_id, row_number, input, result_code, result, suggestion_status, suggestion)
                                VALUES %s ON CONFLICT DO NOTHING""", rows, page_size=500)
                            execute_values(cursor, """INSERT INTO coverage_chunks (run_id, text_key, text)
                                VALUES %s ON CONFLICT DO NOTHING""", chunks, page_size=500)
                    if exists:
                        counts["runs already present"] += 1
                    elif not args.dry_run:
                        counts["runs imported"] += 1
        for label, count in counts.items():
            print(f"{label}: {count}")
        return 0
    except Exception as exc:
        print(f"error: {type(exc).__name__}")
        return 2
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
