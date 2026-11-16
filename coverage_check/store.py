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
import time
from datetime import datetime, timezone
from pathlib import PurePosixPath

import psycopg2
from psycopg2.extras import Json, RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool

from coverage_check.schema import SCHEMA_SQL

RUN_ID = re.compile(r"^c_[0-9a-f]{32}$")
CHUNK_KEY = re.compile(r"[0-9a-f]{64}")
STATES = ("queued", "running", "completed", "cancelled", "interrupted")
# A queued or running run whose owning process has not written a heartbeat for
# this long has no live owner; any process may mark it interrupted.
STALE_SECONDS = 60
# A pooled connection idle longer than this is checked before reuse, because a
# server, proxy or firewall may have closed it in the meantime.
IDLE_CHECK_SECONDS = 30
# Columns kept for coordination between processes, not shown by the API.
INTERNAL_COLUMNS = ("heartbeat_at", "cancel_requested")


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
                                keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
                                options="-c statement_timeout=10000 -c lock_timeout=3000")
    return connect


class _CallableConnectionPool(ThreadedConnectionPool):
    """Use the supplied connector directly, including in isolated tests."""

    def __init__(self, connect):
        self._connection_factory = connect
        self._idle_since: dict[int, float] = {}
        super().__init__(minconn=1, maxconn=4)

    def live_conn(self):
        """A pooled connection that is still open; a dead one is discarded and replaced once."""
        connection = self.getconn()
        idle_since = self._idle_since.pop(id(connection), None)
        if not connection.closed and (idle_since is None or time.monotonic() - idle_since < IDLE_CHECK_SECONDS):
            return connection
        if not connection.closed:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                connection.rollback()
                return connection
            except psycopg2.Error:
                pass
        self.putconn(connection, close=True)
        return self.getconn()

    def release(self, connection):
        if not connection.closed:
            self._idle_since[id(connection)] = time.monotonic()
        self.putconn(connection)

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

    @contextmanager
    def _transaction(self):
        connection = None
        try:
            with self._pool_lock:
                if self._pool is None:
                    self._pool = _CallableConnectionPool(self._connect)
                pool = self._pool
            connection = pool.live_conn()
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
                    pool.release(connection)
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
        for column in INTERNAL_COLUMNS:
            meta.pop(column, None)
        meta.setdefault("active_row", None)
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
                "state": "queued", "row_count": len(rows), "active_row": None}
        with self._transaction() as cursor:
            cursor.execute("""INSERT INTO coverage_runs
                (run_id, created_at, owner_id, file_name, documents, settings, prompt_version, state, row_count,
                 heartbeat_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                (run_id, meta["created_at"], owner_id, meta["file_name"], Json(documents), Json(settings),
                 meta["prompt_version"], "queued", len(rows)))
            execute_values(cursor, "INSERT INTO coverage_rows (run_id, row_number, input) VALUES %s",
                           [(run_id, item["row"], Json(item)) for item in rows], page_size=500)
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
            # Queued or running: a live owner, no Stop yet. Any other state: nothing is being checked.
            cursor.execute("""UPDATE coverage_runs SET state = %s,
                    active_row = CASE WHEN %s IN ('queued', 'running') THEN active_row END,
                    heartbeat_at = CASE WHEN %s IN ('queued', 'running') THEN now() ELSE heartbeat_at END,
                    cancel_requested = CASE WHEN %s IN ('queued', 'running') THEN cancel_requested ELSE FALSE END
                WHERE run_id = %s RETURNING *""", (state, state, state, state, run_id))
            return self._meta_dict(cursor.fetchone())

    def set_active(self, run_id: str, row: int | None) -> None:
        """The row being checked (None between rows), visible to every process."""
        self._validate(run_id)
        with self._transaction() as cursor:
            cursor.execute("UPDATE coverage_runs SET active_row = %s, heartbeat_at = now() WHERE run_id = %s",
                           (None if row is None else int(row), run_id))

    def heartbeat(self, run_ids) -> set[str]:
        """Marks these runs as owned by a live process; returns the ones with a Stop asked for."""
        run_ids = [run_id for run_id in run_ids if isinstance(run_id, str) and RUN_ID.match(run_id)]
        if not run_ids:
            return set()
        with self._transaction() as cursor:
            cursor.execute("""UPDATE coverage_runs SET heartbeat_at = now()
                WHERE run_id = ANY(%s) AND state IN ('queued', 'running')
                RETURNING run_id, cancel_requested""", (run_ids,))
            return {record["run_id"] for record in cursor.fetchall() if record["cancel_requested"]}

    def request_cancel(self, run_id: str) -> bool:
        """Asks the owning process to stop a running run; False when no live process owns it."""
        self._validate(run_id)
        with self._transaction() as cursor:
            cursor.execute("""UPDATE coverage_runs SET cancel_requested = TRUE
                WHERE run_id = %s AND state = 'running' AND heartbeat_at > now() - make_interval(secs => %s)
                RETURNING run_id""", (run_id, STALE_SECONDS))
            return cursor.fetchone() is not None

    def interrupt_stale(self, seconds: int = STALE_SECONDS) -> int:
        """Queued or running runs with no live owning process become interrupted."""
        with self._transaction() as cursor:
            cursor.execute("""UPDATE coverage_runs SET state = 'interrupted', active_row = NULL,
                    cancel_requested = FALSE
                WHERE state IN ('queued', 'running')
                  AND (heartbeat_at IS NULL OR heartbeat_at <= now() - make_interval(secs => %s))
                RETURNING run_id""", (seconds,))
            return len(cursor.fetchall())

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

    def inputs(self, run_id: str) -> list[dict]:
        self._validate(run_id)
        with self._transaction() as cursor:
            self._meta(cursor, run_id)
            cursor.execute("SELECT input FROM coverage_rows WHERE run_id = %s ORDER BY row_number", (run_id,))
            return [record["input"] for record in cursor.fetchall()]

    def _codes(self, cursor, run_id, column):
        # Always read from PostgreSQL: another process may be writing this run's rows.
        self._meta(cursor, run_id)
        # column is selected only by the two internal callers below.
        cursor.execute(f"SELECT row_number, {column} FROM coverage_rows WHERE run_id = %s AND {column} IS NOT NULL",
                       (run_id,))
        return {record["row_number"]: record[column] for record in cursor.fetchall()}

    def result_codes(self, run_id: str) -> dict[int, str]:
        self._validate(run_id)
        with self._transaction() as cursor:
            return self._codes(cursor, run_id, "result_code")

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
            cursor.execute("""UPDATE coverage_rows SET result = %s, result_code = %s
                              WHERE run_id = %s AND row_number = %s""",
                           (Json(data), data["result"], run_id, int(row)))
            if not cursor.rowcount:
                raise StoreError("not_found")

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
        self._validate(run_id)
        with self._transaction() as cursor:
            return self._codes(cursor, run_id, "suggestion_status")

    def suggested_rows(self, run_id: str) -> set[int]:
        return {row for row, status in self.suggestion_statuses(run_id).items() if status == "done"}

    def suggestion(self, run_id: str, row: int) -> dict | None:
        return self._row_value(run_id, row, "suggestion")

    def write_suggestion(self, run_id: str, row: int, data: dict) -> None:
        """A new suggestion for a row replaces the old one."""
        self._validate(run_id)
        with self._transaction() as cursor:
            cursor.execute("""UPDATE coverage_rows SET suggestion = %s, suggestion_status = %s
                              WHERE run_id = %s AND row_number = %s""",
                           (Json(data), data["status"], run_id, int(row)))
            if not cursor.rowcount:
                raise StoreError("not_found")

    def row_page(self, run_id: str, after_row: int, limit: int) -> list[dict]:
        """Ordered input, result and suggestion for up to limit rows after after_row."""
        self._validate(run_id)
        with self._transaction() as cursor:
            cursor.execute("""SELECT input, result, suggestion FROM coverage_rows
                WHERE run_id = %s AND row_number > %s ORDER BY row_number LIMIT %s""",
                           (run_id, after_row, limit))
            return [dict(record) for record in cursor.fetchall()]
