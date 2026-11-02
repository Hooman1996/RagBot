"""The same synthetic storage contract in memory and isolated PostgreSQL tables."""
from datetime import datetime, timedelta, timezone
import ast
import os
from pathlib import Path
import re

import pytest

from coverage_check import store as storage
from coverage_check.schema import SCHEMA_SQL, TABLES
from coverage_check.store import CheckStore, StoreError, postgres_connect_from_env
from tests.coverage_memory_store import MemoryCheckStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.integration)])
def store(request):
    if request.param == "memory":
        result = MemoryCheckStore()
    else:
        psycopg2 = pytest.importorskip("psycopg2")
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        if not all(os.getenv(k) for k in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")):
            pytest.skip("development PostgreSQL is not configured")
        if os.environ["POSTGRES_HOST"] not in {"localhost", "127.0.0.1", "::1"}:
            pytest.skip("coverage SQL fixtures require localhost development PostgreSQL")
        try:
            connection = postgres_connect_from_env()()
        except psycopg2.OperationalError:
            pytest.skip("development PostgreSQL unavailable")
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO pg_temp")
        connection.commit()
        result = CheckStore(lambda: connection)
    try:
        result.ensure_schema()
        if request.param == "postgres":
            with result._transaction() as cursor:
                cursor.execute("SELECT relnamespace = pg_my_temp_schema() AS isolated FROM pg_class WHERE oid = to_regclass('coverage_runs')")
                assert cursor.fetchone()["isolated"] is True
        yield result
    finally:
        result.close()


def create(store, count=2):
    rows = [{"row": n, "id": str(n), "question": f"synthetic {n}"} for n in range(1, count + 1)]
    return store.create(owner_id=7, file_name="C:\\fake\\queries.csv", documents=["Synthetic_FAQ"],
                        settings={"depth": 150}, rows=rows, prompt_version="synthetic")


def missing(call):
    with pytest.raises(StoreError, match="^not_found$"):
        call()


def test_create_meta_inputs_and_timestamp(store):
    meta = create(store)
    assert store.meta(meta["run_id"]) == meta
    assert meta["file_name"] == "queries.csv" and meta["row_count"] == 2 and meta["state"] == "queued"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00", meta["created_at"])
    assert store.inputs(meta["run_id"]) == [{"row": n, "id": str(n), "question": f"synthetic {n}"} for n in (1, 2)]
    missing(lambda: store.meta("invalid"))
    missing(lambda: store.meta("c_" + "0" * 32))


def test_state(store):
    run = create(store)["run_id"]
    assert store.set_state(run, "running")["state"] == "running"
    with pytest.raises(StoreError, match="^invalid_state$"):
        store.set_state(run, "invalid")
    missing(lambda: store.set_state("invalid", "running"))


def test_results_and_cache_reload(store):
    run = create(store)["run_id"]
    assert store.result_codes(run) == {} and store.result(run, 1) is None
    data = {"result": "partial", "text_keys": {"k1": "a" * 64}, "note": "synthetic"}
    store.write_result(run, 1, data)
    assert store.result(run, 1) == data and store.result_codes(run) == {1: "partial"}
    store._results.clear()
    assert store.result_codes(run) == {1: "partial"}
    snapshot = store.result_codes(run)
    snapshot[2] = "error"
    assert store.result_codes(run) == {1: "partial"}
    missing(lambda: store.write_result(run, 3, data))


def test_text_dedupe_and_bad_keys(store):
    run = create(store)["run_id"]
    keys = store.write_texts(run, {"a": "synthetic shared", "b": "synthetic shared"})
    assert keys["a"] == keys["b"] and len(keys["a"]) == 64
    assert store.write_texts(run, {"a": "synthetic shared"})["a"] == keys["a"]
    assert store.chunk_text(run, keys["a"]) == "synthetic shared"
    for key in (None, "../meta", keys["a"].upper(), keys["a"] + "\n", "b" * 64):
        assert store.chunk_text(run, key) is None
    if isinstance(store, CheckStore):
        with store._transaction() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM coverage_chunks WHERE run_id = %s", (run,))
            assert cursor.fetchone()["n"] == 1
    else:
        assert len(store.chunks[run]) == 1


def test_suggestions_replace_and_cache_reload(store):
    run = create(store)["run_id"]
    assert store.suggestion_statuses(run) == {} and store.suggestion(run, 1) is None
    store.write_suggestion(run, 1, {"status": "error", "error_code": "model_failed"})
    data = {"status": "done", "faq_question": "synthetic"}
    store.write_suggestion(run, 1, data)
    assert store.suggestion(run, 1) == data and store.suggested_rows(run) == {1}
    store._suggestions.clear()
    assert store.suggestion_statuses(run) == {1: "done"}
    missing(lambda: store.write_suggestion(run, 3, data))


def test_row_page_across_501_rows(store):
    run = create(store, 501)["run_id"]
    store.write_result(run, 500, {"result": "partial"})
    store.write_suggestion(run, 500, {"status": "done"})
    page = store.row_page(run, 0, 500)
    assert [r["input"]["row"] for r in page] == list(range(1, 501))
    assert page[0]["result"] is None and page[0]["suggestion"] is None
    assert page[-1]["result"] == {"result": "partial"} and page[-1]["suggestion"] == {"status": "done"}
    assert [r["input"]["row"] for r in store.row_page(run, 500, 500)] == [501]
    assert store.row_page(run, 501, 500) == []


def test_list_window_and_order(store, monkeypatch):
    old = datetime.now(timezone.utc) - timedelta(days=45)
    monkeypatch.setattr(storage, "now", lambda: old.isoformat(timespec="milliseconds"))
    finished = create(store)["run_id"]
    store.set_state(finished, "completed")
    running = create(store)["run_id"]
    store.set_state(running, "running")
    queued = create(store)["run_id"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    assert {m["run_id"] for m in store.list(since=cutoff)} == {running, queued}
    assert [m["run_id"] for m in store.list()] == sorted([finished, running, queued], reverse=True)
    assert len(store.list(since=old - timedelta(days=1))) == 3


def test_delete_cascades_and_second_delete_not_found(store):
    run = create(store)["run_id"]
    key = store.write_texts(run, {"a": "synthetic"})["a"]
    store.write_result(run, 1, {"result": "answered"})
    store.write_suggestion(run, 1, {"status": "done"})
    store.delete(run)
    assert run not in store._results and run not in store._suggestions
    assert store.row_page(run, 0, 500) == []
    missing(lambda: store.meta(run))
    missing(lambda: store.chunk_text(run, key))
    missing(lambda: store.delete(run))
    if isinstance(store, CheckStore):
        with store._transaction() as cursor:
            for table in TABLES:
                cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE run_id = %s", (run,))
                assert cursor.fetchone()["n"] == 0
    else:
        assert run not in store.rows and run not in store.chunks


def test_schema_and_commands_only_create_and_insert():
    for source in (SCHEMA_SQL, (ROOT / "scripts/create_coverage_tables.py").read_text(),
                   (ROOT / "scripts/coverage_import_folders.py").read_text()):
        assert not re.search(r"\b(?:DROP|TRUNCATE|ALTER)\b", source, re.I)
    statements = []
    for path in (ROOT / "coverage_check").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for value in ast.walk(node):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str) and re.search(r"\bDELETE\s+FROM\b", value.value, re.I):
                        statements.append((path.name, node.name))
    assert statements == [("store.py", "delete")]


def test_postgres_errors_are_fixed_codes():
    import psycopg2
    def unavailable():
        raise psycopg2.OperationalError("synthetic SQL and parameters must stay private")
    store = CheckStore(unavailable)
    with pytest.raises(StoreError) as error:
        store.ensure_schema()
    assert error.value.code == "storage_unavailable" and error.value.__suppress_context__
    store.close()


def test_owner_commands_use_isolated_tables_and_import_read_only(store, tmp_path, monkeypatch, capsys):
    if not isinstance(store, CheckStore):
        return
    from scripts import coverage_import_folders, create_coverage_tables
    import json

    connection = store._connect()
    class BorrowedConnection:
        def cursor(self, *args, **kwargs):
            return connection.cursor(*args, **kwargs)
        def commit(self):
            connection.commit()
        def close(self):
            pass
        def __enter__(self):
            connection.__enter__()
            return self
        def __exit__(self, *args):
            return connection.__exit__(*args)
    for command in (create_coverage_tables, coverage_import_folders):
        monkeypatch.setattr(command, "load_config", lambda: {})
        monkeypatch.setattr(command, "connect", lambda config: BorrowedConnection())
    monkeypatch.setattr(create_coverage_tables, "database_identity", lambda *args: None)
    for argv in (["--check"], [], []):
        assert create_coverage_tables.main(argv) == 0
        assert capsys.readouterr().out == "coverage_runs: present\ncoverage_rows: present\ncoverage_chunks: present\n"

    run = "c_" + "a" * 32
    root = tmp_path / "legacy" / "checks"
    folder = root / run
    for name in ("results", "chunks", "suggestions"):
        (folder / name).mkdir(parents=True, exist_ok=True)
    meta = {"run_id": run, "owner_id": 7, "created_at": "2026-10-01T12:00:00.123+00:00",
            "file_name": "synthetic.csv", "documents": ["Synthetic_FAQ"], "settings": {},
            "state": "running", "row_count": 1}
    key = "a" * 64
    files = {"meta.json": meta, "input.json": [{"row": 1, "id": "1", "question": "synthetic private question"}],
             "results/1.json": {"result": "partial", "text_keys": {"k1": key}},
             "chunks/" + key + ".json": {"text": "synthetic private text"},
             "suggestions/1.json": {"status": "done", "faq_question": "synthetic private draft"}}
    for name, value in files.items():
        (folder / name).write_text(json.dumps(value))
    unreadable = root / ("c_" + "b" * 32)
    unreadable.mkdir()
    (unreadable / "meta.json").write_text("invalid")
    external = tmp_path / "external"
    external.mkdir()
    (root / ("c_" + "c" * 32)).symlink_to(external, target_is_directory=True)
    # An external file with a plausible chunk key must never be read.
    (folder / "chunks" / ("b" * 64 + ".json")).symlink_to(external / "missing.json")
    snapshot = {p: p.read_bytes() for p in root.rglob("*.json") if not p.is_symlink()}
    for argv, imported, present in ((["--dry-run"], 0, 0), ([], 1, 0), ([], 0, 1)):
        assert coverage_import_folders.main(["--folder", str(root.parent), *argv]) == 0
        assert capsys.readouterr().out == (
            f"runs found: 3\nruns imported: {imported}\nruns already present: {present}\nruns skipped (unreadable): 2\n")
        if argv:
            missing(lambda: store.meta(run))
    assert all(p.read_bytes() == value for p, value in snapshot.items())
    assert store.meta(run) == {**meta, "state": "interrupted", "prompt_version": ""}
    assert store.result(run, 1) == files["results/1.json"]
    assert store.chunk_text(run, key) == "synthetic private text"
    assert store.chunk_text(run, "b" * 64) is None
    assert store.suggestion(run, 1) == files["suggestions/1.json"]


def test_postgres_connection_reused_for_row_reads(store, monkeypatch):
    if not isinstance(store, CheckStore):
        return
    run = create(store)["run_id"]
    def extra_connection():
        raise AssertionError("row reads must reuse the existing pooled connection")
    monkeypatch.setattr(store, "_connect", extra_connection)
    for _ in range(10):
        assert store.result(run, 1) is None
        assert store.meta(run)["run_id"] == run
    assert store._pool.minconn == 1 and store._pool.maxconn == 4
