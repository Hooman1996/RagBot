"""Transactional PostgreSQL storage for coverage checks."""
from __future__ import annotations

import csv
from contextlib import contextmanager
import hashlib
import io
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import PurePosixPath

import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

from coverage_check.schema import SCHEMA_SQL

RUN_ID = re.compile(r"^c_[0-9a-f]{32}$")
CHUNK_KEY = re.compile(r"[0-9a-f]{64}")
STATES = ("queued", "running", "completed", "cancelled", "interrupted")


class StoreError(Exception):
    """A fixed error code for the API; never carries file contents."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def parse_csv(raw: bytes, max_rows: int, extra: str | None = None) -> list[dict]:
    """Rows of {row, id, question}, plus ``extra`` when named; every other column is dropped here."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise StoreError("invalid_csv_encoding") from None
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",")
    try:
        header = next(reader, None)
        names = [str(name).strip().lower() for name in header or []]
        if "query" not in names:
            raise StoreError("missing_query_column")
        query_index = names.index("query")
        id_index = names.index("id") if "id" in names else None
        if extra is not None and extra not in names:
            raise StoreError(f"missing_{extra}_column")
        extra_index = names.index(extra) if extra is not None else None
        rows = []
        for record in reader:
            if not record or all(not cell.strip() for cell in record):
                continue
            if len(rows) >= max_rows:
                raise StoreError("too_many_rows")
            question = record[query_index] if query_index < len(record) else ""
            row_id = record[id_index] if id_index is not None and id_index < len(record) else ""
            row = {"row": len(rows) + 1, "id": row_id, "question": question}
            if extra_index is not None:
                row[extra] = record[extra_index] if extra_index < len(record) else ""
            rows.append(row)
    except csv.Error:
        raise StoreError("invalid_csv") from None
    if not rows:
        raise StoreError("empty_csv")
    return rows


def safe_file_name(name: str) -> str:
    base = PurePosixPath(str(name).replace("\\", "/")).name
    return "".join(ch for ch in base if ch.isprintable())[:120]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def postgres_connect_from_env(environ=None):
    """Snapshot PostgreSQL configuration without exposing it in errors."""
    env = os.environ if environ is None else environ
    config = {name: env.get("POSTGRES_" + name.upper())
              for name in ("host", "port", "user", "password")}
    config["dbname"] = env.get("POSTGRES_DB")

    def connect():
        return psycopg2.connect(**config, connect_timeout=5,
                                options="-c statement_timeout=10000 -c lock_timeout=3000")
    return connect


class _CallableConnectionPool(ThreadedConnectionPool):
    """Use the supplied connector directly, including in isolated tests."""

    def __init__(self, connect):
        self._connection_factory = connect
        super().__init__(minconn=1, maxconn=4)

    def _connect(self, key=None):
        connection = self._connection_factory()
        if key is None:
            self._pool.append(connection)
        else:
            self._used[key] = connection
            self._rused[id(connection)] = key
        return connection


class CheckStore:
    def __init__(self, connect):
        self._connect = connect
        self._pool = None
        self._pool_lock = threading.Lock()
        self._lock = threading.Lock()
        self._results: dict[str, dict[int, str]] = {}
        self._suggestions: dict[str, dict[int, str]] = {}

    @contextmanager
    def _transaction(self):
        connection = None
        try:
            with self._pool_lock:
                if self._pool is None:
                    self._pool = _CallableConnectionPool(self._connect)
                pool = self._pool
            connection = pool.getconn()
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                yield cursor
            connection.commit()
        except BaseException as exc:
            if connection is not None:
                try:
                    connection.rollback()
                except psycopg2.Error:
                    pass
            if isinstance(exc, psycopg2.Error):
                raise StoreError("storage_unavailable") from None
            raise
        finally:
            if connection is not None:
                try:
                    pool.putconn(connection)
                except psycopg2.Error:
                    raise StoreError("storage_unavailable") from None

    def close(self):
        with self._pool_lock:
            if self._pool is not None:
                try:
                    self._pool.closeall()
                except psycopg2.Error:
                    raise StoreError("storage_unavailable") from None
                self._pool = None

    def ensure_schema(self):
        with self._transaction() as cursor:
            cursor.execute(SCHEMA_SQL)

    @staticmethod
    def _validate(run_id):
        if not isinstance(run_id, str) or not RUN_ID.match(run_id):
            raise StoreError("not_found")

    @staticmethod
    def _meta_dict(record):
        if record is None:
            raise StoreError("not_found")
        meta = dict(record)
        meta["created_at"] = meta["created_at"].astimezone(timezone.utc).isoformat(timespec="milliseconds")
        return meta

    def _meta(self, cursor, run_id):
        self._validate(run_id)
        cursor.execute("SELECT * FROM coverage_runs WHERE run_id = %s", (run_id,))
        return self._meta_dict(cursor.fetchone())

    def create(self, *, owner_id: int, file_name: str, documents: list[str],
               settings: dict, rows: list[dict], prompt_version: str) -> dict:
        run_id = "c_" + secrets.token_hex(16)
        meta = {"run_id": run_id, "created_at": now(), "owner_id": owner_id,
                "file_name": safe_file_name(file_name), "documents": list(documents),
                "settings": dict(settings), "prompt_version": str(prompt_version),
                "state": "queued", "row_count": len(rows)}
        with self._transaction() as cursor:
            cursor.execute("""INSERT INTO coverage_runs
                (run_id, created_at, owner_id, file_name, documents, settings, prompt_version, state, row_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, meta["created_at"], owner_id, meta["file_name"], Json(documents), Json(settings),
                 meta["prompt_version"], "queued", len(rows)))
            execute_values(cursor, "INSERT INTO coverage_rows (run_id, row_number, input) VALUES %s",
                           [(run_id, item["row"], Json(item)) for item in rows], page_size=500)
        with self._lock:
            self._results[run_id] = {}
        return meta

    def meta(self, run_id: str) -> dict:
        self._validate(run_id)
        with self._transaction() as cursor:
            return self._meta(cursor, run_id)

    def set_state(self, run_id: str, state: str) -> dict:
        if state not in STATES:
            raise StoreError("invalid_state")
        self._validate(run_id)
        with self._transaction() as cursor:
            cursor.execute("UPDATE coverage_runs SET state = %s WHERE run_id = %s RETURNING *", (state, run_id))
            return self._meta_dict(cursor.fetchone())

    def list(self, since: datetime | None = None) -> list[dict]:
        with self._transaction() as cursor:
            if since is None:
                cursor.execute("SELECT * FROM coverage_runs ORDER BY created_at DESC, run_id DESC")
            else:
                cursor.execute("""SELECT * FROM coverage_runs
                    WHERE created_at >= %s OR state IN ('queued', 'running')
                    ORDER BY created_at DESC, run_id DESC""", (since,))
            return [self._meta_dict(record) for record in cursor.fetchall()]

    def delete(self, run_id: str) -> None:
        self._validate(run_id)
        with self._transaction() as cursor:
            cursor.execute("DELETE FROM coverage_runs WHERE run_id = %s", (run_id,))
            if not cursor.rowcount:
                raise StoreError("not_found")
        with self._lock:
            self._results.pop(run_id, None)
            self._suggestions.pop(run_id, None)

    def inputs(self, run_id: str) -> list[dict]:
        self._validate(run_id)
        with self._transaction() as cursor:
            self._meta(cursor, run_id)
            cursor.execute("SELECT input FROM coverage_rows WHERE run_id = %s ORDER BY row_number", (run_id,))
            return [record["input"] for record in cursor.fetchall()]

    def _codes(self, cursor, run_id, cache, column):
        with self._lock:
            cached = cache.get(run_id)
            if cached is not None:
                return dict(cached)
        self._meta(cursor, run_id)
        # column is selected only by the two internal callers below.
        cursor.execute(f"SELECT row_number, {column} FROM coverage_rows WHERE run_id = %s AND {column} IS NOT NULL",
                       (run_id,))
        codes = {record["row_number"]: record[column] for record in cursor.fetchall()}
        with self._lock:
            cache.setdefault(run_id, codes)
            return dict(cache[run_id])

    def result_codes(self, run_id: str) -> dict[int, str]:
        with self._lock:
            cached = self._results.get(run_id)
            if cached is not None:
                return dict(cached)
        self._validate(run_id)
        with self._transaction() as cursor:
            return self._codes(cursor, run_id, self._results, "result_code")

    def _row_value(self, run_id, row, column):
        self._validate(run_id)
        with self._transaction() as cursor:
            self._meta(cursor, run_id)
            cursor.execute(f"SELECT {column} FROM coverage_rows WHERE run_id = %s AND row_number = %s",
                           (run_id, int(row)))
            record = cursor.fetchone()
            return record[column] if record else None

    def result(self, run_id: str, row: int) -> dict | None:
        return self._row_value(run_id, row, "result")

    def write_result(self, run_id: str, row: int, data: dict) -> None:
        self._validate(run_id)
        with self._transaction() as cursor:
            self._codes(cursor, run_id, self._results, "result_code")
            cursor.execute("""UPDATE coverage_rows SET result = %s, result_code = %s
                              WHERE run_id = %s AND row_number = %s""",
                           (Json(data), data["result"], run_id, int(row)))
            if not cursor.rowcount:
                raise StoreError("not_found")
        with self._lock:
            self._results.setdefault(run_id, {})[int(row)] = data["result"]

    def write_texts(self, run_id: str, texts: dict[str, str]) -> dict[str, str]:
        """Chunk id -> sha256; each distinct text is stored once per run."""
        self._validate(run_id)
        keys, values = {}, {}
        for chunk_id, text in texts.items():
            key = hashlib.sha256(str(text).encode("utf-8")).hexdigest()
            keys[str(chunk_id)] = key
            values[key] = str(text)
        with self._transaction() as cursor:
            self._meta(cursor, run_id)
            execute_values(cursor, """INSERT INTO coverage_chunks (run_id, text_key, text) VALUES %s
                                      ON CONFLICT (run_id, text_key) DO NOTHING""",
                           [(run_id, key, text) for key, text in values.items()], page_size=500)
        return keys

    def chunk_text(self, run_id: str, key) -> str | None:
        if not isinstance(key, str) or not CHUNK_KEY.fullmatch(key):
            return None
        self._validate(run_id)
        with self._transaction() as cursor:
            self._meta(cursor, run_id)
            cursor.execute("SELECT text FROM coverage_chunks WHERE run_id = %s AND text_key = %s", (run_id, key))
            record = cursor.fetchone()
            return record["text"] if record else None

    def suggestion_statuses(self, run_id: str) -> dict[int, str]:
        with self._lock:
            cached = self._suggestions.get(run_id)
            if cached is not None:
                return dict(cached)
        self._validate(run_id)
        with self._transaction() as cursor:
            return self._codes(cursor, run_id, self._suggestions, "suggestion_status")

    def suggested_rows(self, run_id: str) -> set[int]:
        return {row for row, status in self.suggestion_statuses(run_id).items() if status == "done"}

    def suggestion(self, run_id: str, row: int) -> dict | None:
        return self._row_value(run_id, row, "suggestion")

    def write_suggestion(self, run_id: str, row: int, data: dict) -> None:
        """A new suggestion for a row replaces the old one."""
        self._validate(run_id)
        with self._transaction() as cursor:
            self._codes(cursor, run_id, self._suggestions, "suggestion_status")
            cursor.execute("""UPDATE coverage_rows SET suggestion = %s, suggestion_status = %s
                              WHERE run_id = %s AND row_number = %s""",
                           (Json(data), data["status"], run_id, int(row)))
            if not cursor.rowcount:
                raise StoreError("not_found")
        with self._lock:
            self._suggestions.setdefault(run_id, {})[int(row)] = data["status"]

    def row_page(self, run_id: str, after_row: int, limit: int) -> list[dict]:
        """Ordered input, result and suggestion for up to limit rows after after_row."""
        self._validate(run_id)
        with self._transaction() as cursor:
            cursor.execute("""SELECT input, result, suggestion FROM coverage_rows
                WHERE run_id = %s AND row_number > %s ORDER BY row_number LIMIT %s""",
                           (run_id, after_row, limit))
            return [dict(record) for record in cursor.fetchall()]
