"""Read-only PostgreSQL contract tests with synthetic CTE rows and real SQL."""
from datetime import datetime, timedelta, timezone
import json
import os

import pytest
from fastapi.testclient import TestClient

import main
from analytics_metrics import aggregate_analytics
from tests.test_web_auth import setup, login


NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


class SyntheticCursor:
    def __init__(self, cursor, rows):
        self.cursor, self.rows = cursor, rows

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()

    @property
    def description(self):
        return self.cursor.description

    def fetchall(self):
        return self.cursor.fetchall()

    def execute(self, sql, params):
        if "FROM documents" in sql:
            prefix = "WITH documents AS (SELECT 'completed'::text AS processing_status) "
            self.cursor.execute(prefix + sql, params)
            return
        if self.rows:
            values = ",".join(["(%s::int,%s::int,%s::timestamp,%s::timestamp,%s::text,%s::int)"] * len(self.rows))
            prefix = ("queries(user_id,chat_session_id,created_at,completed_at,status,is_helpful) AS "
                      f"(VALUES {values})")
            synthetic = [value for row in self.rows for value in row]
        else:
            prefix = ("queries(user_id,chat_session_id,created_at,completed_at,status,is_helpful) AS "
                      "(SELECT NULL::int,NULL::int,NULL::timestamp,NULL::timestamp,NULL::text,NULL::int WHERE FALSE)")
            synthetic = []
        sql = sql.strip()
        if sql.startswith("WITH "):
            sql = "WITH " + prefix + ", " + sql[5:]
        else:
            sql = "WITH " + prefix + " " + sql
        self.cursor.execute(sql, tuple(synthetic) + tuple(params))


class SyntheticConnection:
    def __init__(self, connection, rows):
        self.connection, self.rows = connection, rows

    def set_session(self, **kwargs):
        self.connection.set_session(**kwargs)

    def cursor(self):
        return SyntheticCursor(self.connection.cursor(), self.rows)

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


class SyntheticDatabase:
    def __init__(self, connect, rows):
        self.connect, self.rows = connect, rows

    def get_connection(self):
        return SyntheticConnection(self.connect(), self.rows)


@pytest.fixture
def postgres_connect():
    psycopg2 = pytest.importorskip("psycopg2")
    from dotenv import load_dotenv
    load_dotenv(".env")
    if not all(os.getenv(k) for k in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")):
        pytest.skip("development PostgreSQL is not configured")
    if os.getenv("POSTGRES_HOST") not in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("analytics SQL fixtures require localhost development PostgreSQL")
    def connect():
        try:
            return psycopg2.connect(
                host=os.environ["POSTGRES_HOST"], port=os.environ["POSTGRES_PORT"],
                dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"], connect_timeout=3,
                options="-c statement_timeout=5000 -c default_transaction_read_only=on",
            )
        except psycopg2.OperationalError:
            pytest.skip("development PostgreSQL unavailable")
    return connect


def sample_rows():
    def dt(day, hour=0, minute=0, second=0):
        return datetime(2026, 9, day, hour, minute, second)
    return [
        (1, 10, dt(20, 23, 59, 59), dt(21, 0), "completed", 1),  # outside seven days
        (1, 10, dt(21), dt(21, 0, 0, 3), "completed", None),
        (1, 10, dt(27, 9, 59, 59), dt(27, 10, 0, 5), "completed", 0),
        (2, 20, dt(27, 9), None, "pending", None),
        (2, None, dt(22, 10), None, "completed", 1),
        (3, 30, dt(27, 10), dt(27, 10, 0, 2), "completed", 1),  # at exclusive end
    ]


def test_empty_and_unrated_windows(postgres_connect):
    empty = aggregate_analytics(SyntheticDatabase(postgres_connect, []), 7, NOW)
    assert empty["kpis"]["total_queries"] == 0
    assert empty["kpis"]["avg_completion_seconds"] is None
    assert empty["feedback_outcomes"]["data"] == [0, 0, 0]
    assert empty["conversation_depth"]["sessions"] == 0
    assert empty["query_states"]["labels"] == []
    assert empty["heatmap"]["total"] == 0
    assert len(empty["heatmap"]["matrix"]) == 7
    assert all(len(row) == 24 for row in empty["heatmap"]["matrix"])
    assert empty["kpis"]["documents_indexed"] == 1

    row = [(1, 10, datetime(2026, 9, 21), None, "pending", None)]
    unrated = aggregate_analytics(SyntheticDatabase(postgres_connect, row), 7, NOW)
    assert unrated["feedback_outcomes"]["data"] == [0, 0, 1]
    assert unrated["feedback_outcomes"]["rated_responses"] == 0
    assert unrated["completion_duration"]["measured"] == 0
    assert unrated["completion_duration"]["unavailable_reason"]


def test_mixed_votes_depth_boundaries_timezone_and_incomplete(postgres_connect):
    data = aggregate_analytics(SyntheticDatabase(postgres_connect, sample_rows()), 7, NOW)
    assert data["meta"]["start"] == "2026-09-21T00:00:00Z"
    assert data["meta"]["end"] == "2026-09-27T10:00:00Z"
    assert data["meta"]["timezone"] == "UTC"
    assert data["meta"]["contract_version"] == "main-analytics/v3"
    assert data["kpis"]["total_queries"] == 4
    assert data["kpis"]["active_users"] == 2
    assert data["feedback_outcomes"]["data"] == [1, 1, 2]
    assert data["feedback_outcomes"]["rated_responses"] == 2
    assert data["conversation_depth"]["data"] == [1, 1, 0, 0]
    assert data["conversation_depth"]["sessions"] == 2
    assert data["conversation_depth"]["queries_without_session"] == 1
    assert data["kpis"]["completed_queries"] == 3
    assert data["kpis"]["completion_measured"] == 2
    assert data["kpis"]["avg_completion_seconds"] == 4.5
    assert data["completion_duration"]["data"] == [0, 1, 1, 0, 0]
    assert data["completion_duration"]["excluded_completed"] == 1
    assert data["query_states"] == {"labels": ["completed", "pending"], "data": [3, 1], "total": 4}
    assert data["heatmap"]["matrix"][0][0] == 1  # Monday 00:00 UTC
    assert data["heatmap"]["matrix"][6][9] == 2  # Sunday 09:00 UTC
    assert data["queries_per_day"]["data"][0] == 1
    assert data["users_per_day"]["data"][-1] == 2
    assert data["weekly_comparison"]["current_total"] == 4
    assert data["weekly_comparison"]["previous_total"] == 1


def test_all_conversation_depth_buckets_and_failed_state(postgres_connect):
    created = datetime(2026, 9, 25, 12)
    rows = []
    for session, count in ((1, 1), (2, 3), (3, 5), (4, 10)):
        rows.extend((session, session, created, created + timedelta(seconds=1),
                     "completed", None) for _ in range(count))
    rows.append((5, 5, created, None, "failed", None))
    data = aggregate_analytics(SyntheticDatabase(postgres_connect, rows), 7, NOW)
    assert data["conversation_depth"]["data"] == [2, 1, 1, 1]
    assert data["conversation_depth"]["sessions"] == 5
    assert data["query_states"]["labels"] == ["completed", "failed"]
    assert data["query_states"]["data"] == [19, 1]
    assert data["completion_duration"]["measured"] == 19


@pytest.mark.parametrize("days", [7, 14, 30])
def test_allowed_windows_have_stable_shape(postgres_connect, days):
    data = aggregate_analytics(SyntheticDatabase(postgres_connect, sample_rows()), days, NOW)
    assert set(data) == {"meta", "kpis", "queries_per_day", "users_per_day",
                         "feedback_outcomes", "conversation_depth", "completion_duration",
                         "query_states", "heatmap", "weekly_comparison"}
    assert len(data["queries_per_day"]["labels"]) == days
    assert len(data["queries_per_day"]["data"]) == days
    assert not any(key in json.dumps(data).lower() for key in ("query_text", "response_text", "retrieved_documents"))


def test_api_range_shape_and_role_boundary(setup, monkeypatch, postgres_connect):
    synthetic = SyntheticDatabase(postgres_connect, sample_rows())
    monkeypatch.setattr(setup, "get_connection", synthetic.get_connection, raising=False)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        assert client.get("/api/analytics").status_code == 401
        login(client, "alice")
        for role in ("user", "surprise_role"):
            setup.users[1]["role"] = role
            assert client.get("/api/analytics").status_code == 403
            assert client.get("/analytics").status_code == 403
        for role in ("admin", "analytics_viewer"):
            setup.users[1]["role"] = role
            assert client.get("/analytics").status_code == 200
            for days in (7, 14, 30):
                response = client.get(f"/api/analytics?days={days}")
                assert response.status_code == 200
                assert response.json()["meta"]["days"] == days
                assert response.json()["meta"]["timezone"] == "UTC"
                assert response.json()["meta"]["contract_version"] == "main-analytics/v3"
                assert set(response.json()) == {"meta", "kpis", "queries_per_day", "users_per_day",
                                                "feedback_outcomes", "conversation_depth", "completion_duration",
                                                "query_states", "heatmap", "weekly_comparison"}
                assert not any(key in response.text for key in ("query_text", "response_text",
                                                                 "retrieved_documents", "user_id", "chat_session_id"))
            for invalid in ("0", "8", "31", "wrong"):
                assert client.get(f"/api/analytics?days={invalid}").status_code == 422
