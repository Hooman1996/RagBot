from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


class ModulePatch:
    def __init__(self, replacements):
        self.replacements = replacements
        self.previous = {}

    def __enter__(self):
        for name, module in self.replacements.items():
            self.previous[name] = sys.modules.get(name)
            sys.modules[name] = module

    def __exit__(self, exc_type, exc, traceback):
        for name, previous in self.previous.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def import_stubs():
    fastapi = types.ModuleType("fastapi")

    class APIRouter:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def _decorator(*_args, **_kwargs):
            return lambda function: function

        get = _decorator
        post = _decorator

    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.APIRouter = APIRouter
    fastapi.Request = object
    fastapi.HTTPException = HTTPException

    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.Error = Exception
    psycopg2.connect = lambda **_kwargs: None
    extras = types.ModuleType("psycopg2.extras")
    extras.RealDictCursor = object
    psycopg2.extras = extras

    concurrency = types.ModuleType("utils.concurrency")

    async def run_with_limit(*_args, **_kwargs):
        raise AssertionError("not used by history tests")

    concurrency.run_with_limit = run_with_limit

    performance_config = types.ModuleType("utils.performance_config")
    performance_config.PERFORMANCE_SETTINGS = SimpleNamespace(
        application_request_timeout_seconds=50.0,
    )

    answering_service = types.ModuleType("answering_service")

    class AnswerRequestContext:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    answering_service.AnswerRequestContext = AnswerRequestContext

    instrumentation = types.ModuleType("utils.request_instrumentation")
    instrumentation.current_trace = lambda: None
    instrumentation.mark_event = lambda *_args, **_kwargs: None

    @asynccontextmanager
    async def trace_span(*_args, **_kwargs):
        yield

    instrumentation.trace_span = trace_span

    return {
        "fastapi": fastapi,
        "psycopg2": psycopg2,
        "psycopg2.extras": extras,
        "utils.concurrency": concurrency,
        "utils.performance_config": performance_config,
        "answering_service": answering_service,
        "utils.request_instrumentation": instrumentation,
    }


with ModulePatch(import_stubs()):
    database_module = load_module(
        "mobile_history_database_under_test",
        ROOT / "new_architecture/app/services/history/database.py",
    )
    mobile_api = load_module(
        "mobile_history_api_under_test", ROOT / "mobile_api.py"
    )


BASE_TIME = datetime(2026, 6, 22, 10, 0, 0)


def session_row(session_id: int, **overrides):
    row = {
        "id": session_id,
        "uuid": f"mobile-session-{session_id}",
        "user_id": 7,
        "title": "Mobile App Chat",
        "description": None,
        "model_name": None,
        "temperature": 0.7,
        "query_count": 0,
        "total_tokens": 0,
        "status": "active",
        "is_pinned": False,
        "meta_data": {},
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
        "last_activity_at": BASE_TIME,
    }
    row.update(overrides)
    return row


def query_row(query_id: int, session_id: int, text: str, created_at, **overrides):
    row = {
        "id": query_id,
        "chat_session_id": session_id,
        "query_text": text,
        "response_text": None,
        "created_at": created_at,
        "completed_at": None,
    }
    row.update(overrides)
    return row


class InMemoryHistoryDatabase(database_module.DatabaseManager):
    def __init__(self, sessions, queries):
        self.sessions = sessions
        self.queries = queries
        self.executions = []

    def _execute(self, query, params=None, fetch=None):
        self.executions.append((query, params, fetch))
        self.assert_session_query(query, params, fetch)
        rows = [
            dict(row)
            for row in self.sessions
            if row["user_id"] == params[0] and row["status"] != "deleted"
        ]
        rows.sort(
            key=lambda row: (row["is_pinned"], row["last_activity_at"]),
            reverse=True,
        )
        if "LEFT JOIN LATERAL" in query:
            for row in rows:
                user_queries = sorted(
                    (
                        item for item in self.queries
                        if item["chat_session_id"] == row["id"]
                    ),
                    key=lambda item: (item["created_at"], item["id"]),
                )
                row["content"] = (
                    user_queries[0]["query_text"] if user_queries else None
                )
        return rows

    @staticmethod
    def assert_session_query(query, params, fetch):
        if "FROM   chat_sessions" not in query:
            raise AssertionError("unexpected SQL")
        if params != (7,) or fetch != "all":
            raise AssertionError("session query contract changed")


class MobileHistoryContentDatabaseTests(unittest.TestCase):
    def get_sessions(self, sessions, queries):
        db = InMemoryHistoryDatabase(sessions, queries)
        manager = database_module.ChatManager(db)
        result = list(manager.get_user_sessions(7, True).values())
        self.assertEqual(len(db.executions), 1)
        return db, result

    def test_one_session_uses_first_user_message_as_content(self):
        db, sessions = self.get_sessions(
            [session_row(12)],
            [query_row(1, 12, "افتتاح حساب چگونه است؟", BASE_TIME)],
        )

        self.assertEqual(sessions[0]["content"], "افتتاح حساب چگونه است؟")
        sql = db.executions[0][0]
        self.assertIn("LEFT JOIN LATERAL", sql)
        self.assertIn("SELECT q.query_text AS content", sql)
        self.assertIn("ORDER  BY q.created_at ASC, q.id ASC", sql)
        self.assertIn("LIMIT  1", sql)

    def test_multiple_user_and_assistant_messages_use_earliest_user(self):
        _, sessions = self.get_sessions(
            [session_row(12)],
            [
                query_row(
                    1, 12, "افتتاح حساب چگونه است؟", BASE_TIME,
                    response_text="پاسخ اول",
                ),
                query_row(
                    2, 12, "مدارکش چیست؟", BASE_TIME + timedelta(minutes=2),
                    response_text="پاسخ دوم",
                ),
            ],
        )

        self.assertEqual(sessions[0]["content"], "افتتاح حساب چگونه است؟")

    def test_assistant_timestamp_before_user_still_uses_user_query(self):
        _, sessions = self.get_sessions(
            [session_row(12)],
            [
                query_row(
                    1, 12, "اولین پیام کاربر", BASE_TIME,
                    response_text="پیام دستیار",
                    completed_at=BASE_TIME - timedelta(minutes=1),
                )
            ],
        )

        self.assertEqual(sessions[0]["content"], "اولین پیام کاربر")

    def test_multiple_sessions_receive_their_own_first_user_query(self):
        _, sessions = self.get_sessions(
            [
                session_row(12, last_activity_at=BASE_TIME),
                session_row(13, last_activity_at=BASE_TIME + timedelta(hours=1)),
            ],
            [
                query_row(3, 12, "مدارکش چیست؟", BASE_TIME + timedelta(minutes=2)),
                query_row(2, 13, "رمز کارت را چطور تغییر بدهم؟", BASE_TIME),
                query_row(1, 12, "افتتاح حساب چگونه است؟", BASE_TIME),
            ],
        )

        by_id = {session["id"]: session["content"] for session in sessions}
        self.assertEqual(
            by_id,
            {
                "12": "افتتاح حساب چگونه است؟",
                "13": "رمز کارت را چطور تغییر بدهم؟",
            },
        )

    def test_session_without_user_messages_has_null_content(self):
        _, sessions = self.get_sessions([session_row(12)], [])

        self.assertIsNone(sessions[0]["content"])


class ImmediateRunner:
    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class GatewayDatabase:
    @staticmethod
    def get_or_create_user_by_national_code(_national_code):
        return {"id": 7}


class GatewayChatManager:
    def __init__(self, content="افتتاح حساب چگونه است؟"):
        self.db = GatewayDatabase()
        self.session_list_calls = []
        self.content = content

    def get_user_sessions(self, user_id, include_first_user_content=False):
        self.session_list_calls.append((user_id, include_first_user_content))
        return {
            "12": {
                "id": "12",
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Mobile App Chat",
                "description": None,
                "model_name": None,
                "temperature": 0.7,
                "query_count": 1,
                "total_tokens": 0,
                "status": "active",
                "is_pinned": False,
                "meta_data": {},
                "created_at": "2026-06-22T10:00:00",
                "updated_at": "2026-06-22T10:01:00",
                "last_activity_at": "2026-06-22T10:01:00",
                "content": self.content,
            }
        }

    @staticmethod
    def resolve_mobile_session(user_id, session_id):
        if user_id != 7 or session_id != "mobile-uuid":
            raise AssertionError("mobile session resolution changed")
        return "12"

    @staticmethod
    def get_messages(session_id):
        if session_id != "12":
            raise AssertionError("internal session id changed")
        return [{
            "id": "4",
            "role": "user",
            "content": "پیام موجود",
            "created_at": "2026-06-22T10:00:00",
        }]


def request_with(chat_manager):
    state = SimpleNamespace(
        agent_service=object(),
        chat_manager=chat_manager,
        intent_classifier=object(),
        history_rewriting_service=object(),
        blocking_runner=ImmediateRunner(),
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


class MobileHistoryContentApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_id_history_response_is_unchanged(self):
        chat_manager = GatewayChatManager()

        result = await mobile_api.gateway_history(
            request_with(chat_manager),
            national_code="1234567890",
            session_id="mobile-uuid",
        )

        self.assertEqual(result["session_id"], "mobile-uuid")
        self.assertEqual(len(result["messages"]), 1)
        message = result["messages"][0]
        self.assertEqual(message.id, "4")
        self.assertEqual(message.role, "user")
        self.assertEqual(message.content, "پیام موجود")
        self.assertEqual(message.created_at, "2026-06-22T10:00:00")
        self.assertEqual(chat_manager.session_list_calls, [])

    async def test_national_code_history_preserves_fields_and_adds_content(self):
        chat_manager = GatewayChatManager()

        result = await mobile_api.gateway_history(
            request_with(chat_manager), national_code="1234567890"
        )

        self.assertEqual(result["national_code"], "1234567890")
        self.assertEqual(chat_manager.session_list_calls, [(7, True)])
        session = result["sessions"][0]
        self.assertEqual(
            set(session),
            {"id", "mobile_session_id", "content", "created_at"},
        )
        self.assertEqual(session["id"], 12)
        self.assertEqual(
            session["mobile_session_id"],
            "550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(session["created_at"], "2026-06-22T10:00:00")
        self.assertEqual(session["content"], "افتتاح حساب چگونه است؟")
        self.assertTrue({
            "uuid",
            "title",
            "meta_data",
            "updated_at",
            "last_activity_at",
            "status",
            "query_count",
        }.isdisjoint(session))

    async def test_national_code_history_without_user_query_has_null_content(self):
        result = await mobile_api.gateway_history(
            request_with(GatewayChatManager(content=None)),
            national_code="1234567890",
        )

        session = result["sessions"][0]
        self.assertEqual(
            set(session),
            {"id", "mobile_session_id", "content", "created_at"},
        )
        self.assertIsNone(session["content"])


class MobileTalkSessionIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_session_uuid_is_rejected_before_database_access(self):
        request = mobile_api.TalkRequest(
            session_id="550123455-e29b-41d4-a716-446655854444",
            query="پیام هامو چجوری فعال کنم؟",
            national_code="8888664190",
            documents=["General_FAQ"],
        )

        with self.assertRaises(mobile_api.HTTPException) as raised:
            await mobile_api._gateway_talk(request, object())

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(
            raised.exception.detail, "session_id must be a valid UUID."
        )

    async def test_canonical_session_uuid_remains_valid(self):
        self.assertIsNone(
            mobile_api._validate_mobile_session_id(
                "55012345-e29b-41d4-a716-446655854444"
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
