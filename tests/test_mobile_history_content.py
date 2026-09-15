from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


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

    async def run_with_limit(_limiter, operation, **_kwargs):
        return await operation()

    concurrency.run_with_limit = run_with_limit

    performance_config = types.ModuleType("utils.performance_config")
    performance_config.PERFORMANCE_SETTINGS = SimpleNamespace(
        application_request_timeout_seconds=50.0,
        request_admission_timeout_seconds=1.0,
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

    def test_closed_sessions_remain_listed_and_foreign_sessions_do_not(self):
        _, sessions = self.get_sessions(
            [
                session_row(12, status="closed"),
                session_row(13, user_id=92),
            ],
            [],
        )

        self.assertEqual([session["id"] for session in sessions], ["12"])
        self.assertEqual(sessions[0]["status"], "closed")


class ImmediateRunner:
    async def run(self, function, /, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class GatewayDatabase:
    @staticmethod
    def get_or_create_user_by_national_code(_national_code):
        return {"id": 7}


class GatewayChatManager:
    def __init__(self, content="افتتاح حساب چگونه است؟", status="active"):
        self.db = GatewayDatabase()
        self.session_list_calls = []
        self.content = content
        self.status = status

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
                "status": self.status,
                "is_pinned": False,
                "meta_data": {},
                "created_at": "2026-06-22T10:00:00",
                "updated_at": "2026-06-22T10:01:00",
                "last_activity_at": "2026-06-22T10:01:00",
                "content": self.content,
            }
        }

    @staticmethod
    def resolve_mobile_session(
            user_id, session_id, require_active=True):
        if user_id != 7 or session_id != "mobile-uuid":
            raise AssertionError("mobile session resolution changed")
        if require_active:
            raise AssertionError("history must permit owner-only closed reads")
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


def request_with(chat_manager, answering_service=None):
    state = SimpleNamespace(
        agent_service=object(),
        chat_manager=chat_manager,
        intent_classifier=object(),
        history_rewriting_service=object(),
        answering_service=answering_service or object(),
        blocking_runner=ImmediateRunner(),
        request_limiter=object(),
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

    async def test_national_code_history_keeps_closed_session_visible(self):
        result = await mobile_api.gateway_history(
            request_with(GatewayChatManager(status="closed")),
            national_code="1234567890",
        )

        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(result["sessions"][0]["id"], 12)


class MobileTalkSessionIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_session_id_is_an_opaque_string(self):
        class TalkChatManager:
            def __init__(self):
                self.db = GatewayDatabase()
                self.resolved_session_ids = []
                self.messages = []

            def resolve_mobile_session(self, user_id, session_id):
                self.resolved_session_ids.append((user_id, session_id))
                return "12"

            def add_message(
                self, session_id, role, content, user_id=None, query_id=None
            ):
                self.messages.append(
                    (session_id, role, content, user_id, query_id)
                )
                return {"id": 41 if role == "user" else 42}

        class AnsweringService:
            def __init__(self):
                self.requests = []

            async def answer(self, request):
                self.requests.append(request)
                return SimpleNamespace(
                    answer="پاسخ",
                    related_questions=[],
                    feedback_needed=False,
                )

        session_ids = (
            "DP1234567890123456",
            "DP12345678901234567890",
            "55012345-e29b-41d4-a716-446655854444",
        )
        for session_id in session_ids:
            with self.subTest(session_id=session_id):
                chat_manager = TalkChatManager()
                answering_service = AnsweringService()
                request = mobile_api.TalkRequest(
                    session_id=session_id,
                    query="پیام هامو چجوری فعال کنم؟",
                    national_code="8888664190",
                    documents=["General_FAQ"],
                )

                response = await mobile_api.gateway_talk(
                    request,
                    request_with(chat_manager, answering_service),
                )

                self.assertEqual(
                    chat_manager.resolved_session_ids, [(7, session_id)]
                )
                self.assertEqual(answering_service.requests[0].session_id, "12")
                self.assertEqual(response.query_id, "42")
                self.assertEqual(response.session_id, session_id)
                self.assertEqual(response.query, request.query)
                self.assertEqual(response.answer, "پاسخ")
                self.assertEqual(response.related_questions, [])
                self.assertFalse(response.feedback_needed)
                self.assertEqual(
                    chat_manager.messages,
                    [
                        ("12", "user", request.query, 7, None),
                        ("12", "assistant", "پاسخ", 7, 41),
                    ],
                )


class ScriptedMobileSessionDatabase(database_module.DatabaseManager):
    def __init__(self, lookups, insert_result=None):
        self.lookups = list(lookups)
        self.insert_result = insert_result
        self.executions = []

    @staticmethod
    def get_or_create_user_by_national_code(_national_code):
        return {"id": 7}

    def get_session_by_uuid(self, session_uuid):
        if not self.lookups:
            raise AssertionError("unexpected UUID lookup")
        self.executions.append(("lookup", session_uuid))
        return self.lookups.pop(0)

    def _execute(self, query, params=None, fetch=None):
        self.executions.append((query, params, fetch))
        if "INSERT INTO chat_sessions" not in query:
            raise AssertionError("unexpected SQL")
        return self.insert_result


class MobileSessionAuthorizationTests(unittest.TestCase):
    def test_existing_active_session_for_correct_owner_resolves(self):
        db = ScriptedMobileSessionDatabase([session_row(12)])
        manager = database_module.ChatManager(db)

        self.assertEqual(manager.resolve_mobile_session(7, "mobile-uuid"), "12")
        self.assertEqual(db.executions, [("lookup", "mobile-uuid")])

    def test_existing_session_for_wrong_owner_is_rejected(self):
        db = ScriptedMobileSessionDatabase([session_row(12, user_id=25)])
        manager = database_module.ChatManager(db)

        with self.assertRaises(database_module.SessionUnavailableError) as raised:
            manager.resolve_mobile_session(92, "mobile-uuid")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.public_message, "Session unavailable.")

    def test_existing_closed_session_cannot_be_continued(self):
        db = ScriptedMobileSessionDatabase([session_row(12, status="closed")])
        manager = database_module.ChatManager(db)

        with self.assertRaises(database_module.SessionUnavailableError):
            manager.resolve_mobile_session(7, "mobile-uuid")

    def test_owner_can_read_existing_closed_session_history(self):
        db = ScriptedMobileSessionDatabase([session_row(12, status="closed")])
        manager = database_module.ChatManager(db)

        self.assertEqual(
            manager.resolve_mobile_session(
                7, "mobile-uuid", require_active=False
            ),
            "12",
        )

    def test_new_session_is_bound_to_user_as_active(self):
        created = session_row(12, uuid="new-mobile-uuid")
        db = ScriptedMobileSessionDatabase([None], insert_result=created)
        manager = database_module.ChatManager(db)

        self.assertEqual(manager.resolve_mobile_session(7, "new-mobile-uuid"), "12")
        insert_sql, params, fetch = db.executions[1]
        self.assertIn("ON CONFLICT (uuid) DO NOTHING", insert_sql)
        self.assertIn("'active'", insert_sql)
        self.assertEqual(params[:3], ("new-mobile-uuid", 7, "Mobile App Chat"))
        self.assertEqual(fetch, "one")

    def test_conflict_winner_same_owner_active_is_allowed(self):
        winner = session_row(12, uuid="raced-mobile-uuid")
        db = ScriptedMobileSessionDatabase(
            [None, winner], insert_result=None
        )
        manager = database_module.ChatManager(db)

        self.assertEqual(
            manager.resolve_mobile_session(7, "raced-mobile-uuid"), "12"
        )
        self.assertEqual(
            [call for call in db.executions if call[0] == "lookup"],
            [
                ("lookup", "raced-mobile-uuid"),
                ("lookup", "raced-mobile-uuid"),
            ],
        )

    def test_conflict_winner_different_owner_is_rejected(self):
        winner = session_row(
            12, uuid="raced-mobile-uuid", user_id=25
        )
        db = ScriptedMobileSessionDatabase(
            [None, winner], insert_result=None
        )
        manager = database_module.ChatManager(db)

        with self.assertRaises(database_module.SessionUnavailableError):
            manager.resolve_mobile_session(92, "raced-mobile-uuid")


class MobileAuthorizationApiTests(unittest.IsolatedAsyncioTestCase):
    async def assert_talk_denied_before_pipeline(self, existing_session):
        chat_manager = database_module.ChatManager(
            ScriptedMobileSessionDatabase([existing_session])
        )
        chat_manager.add_message = Mock()
        chat_manager.get_messages = Mock()
        answering_service = SimpleNamespace(answer=AsyncMock())
        history_rewriter = SimpleNamespace(rewrite=Mock())
        request = request_with(chat_manager, answering_service)
        request.app.state.history_rewriting_service = history_rewriter
        talk_request = mobile_api.TalkRequest(
            session_id="foreign-mobile-uuid",
            query="secure question",
            national_code="current-user",
        )

        with self.assertRaises(database_module.SessionUnavailableError) as raised:
            await mobile_api.gateway_talk(talk_request, request)

        self.assertEqual(raised.exception.public_message, "Session unavailable.")
        chat_manager.add_message.assert_not_called()
        chat_manager.get_messages.assert_not_called()
        answering_service.answer.assert_not_awaited()
        history_rewriter.rewrite.assert_not_called()

    async def test_talk_wrong_owner_stops_before_writes_or_answering(self):
        await self.assert_talk_denied_before_pipeline(
            session_row(12, user_id=25)
        )

    async def test_talk_closed_owner_stops_before_writes_or_answering(self):
        await self.assert_talk_denied_before_pipeline(
            session_row(12, status="closed")
        )

    async def test_specific_history_wrong_owner_returns_no_messages(self):
        chat_manager = database_module.ChatManager(
            ScriptedMobileSessionDatabase([session_row(12, user_id=25)])
        )
        chat_manager.get_messages = Mock()

        with self.assertRaises(database_module.SessionUnavailableError) as raised:
            await mobile_api.gateway_history(
                request_with(chat_manager),
                national_code="current-user",
                session_id="foreign-mobile-uuid",
            )

        self.assertEqual(raised.exception.public_message, "Session unavailable.")
        chat_manager.get_messages.assert_not_called()


class StatefulCloseDatabase(database_module.DatabaseManager):
    def __init__(self, row):
        self.row = dict(row)
        self.executions = []

    @staticmethod
    def get_or_create_user_by_national_code(_national_code):
        return {"id": 7}

    def _execute(self, query, params=None, fetch=None):
        self.executions.append((query, params, fetch))
        updated_at, session_uuid, user_id = params
        if (
            self.row["uuid"] != session_uuid
            or self.row["user_id"] != user_id
        ):
            return None
        self.row["status"] = "closed"
        self.row["updated_at"] = updated_at
        return dict(self.row)


class MobileCloseSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_can_close_session_without_removing_or_rebinding_it(self):
        original = session_row(12, uuid="mobile-uuid", meta_data={"state": 1})
        db = StatefulCloseDatabase(original)
        manager = database_module.ChatManager(db)

        result = await mobile_api.gateway_close_session(
            "mobile-uuid",
            mobile_api.CloseSessionRequest(national_code="current-user"),
            request_with(manager),
        )

        self.assertEqual(
            result, {"status": "success", "session_id": "mobile-uuid"}
        )
        self.assertEqual(db.row["status"], "closed")
        self.assertNotEqual(db.row["updated_at"], original["updated_at"])
        for key in original.keys() - {"status", "updated_at"}:
            self.assertEqual(db.row[key], original[key])
        sql, params, fetch = db.executions[0]
        self.assertIn("WHERE uuid = %s AND user_id = %s", sql)
        self.assertEqual(params[1:], ("mobile-uuid", 7))
        self.assertEqual(fetch, "one")

    async def test_closing_an_already_closed_session_is_idempotent(self):
        db = StatefulCloseDatabase(
            session_row(12, uuid="mobile-uuid", status="closed")
        )
        manager = database_module.ChatManager(db)

        result = await mobile_api.gateway_close_session(
            "mobile-uuid",
            mobile_api.CloseSessionRequest(national_code="current-user"),
            request_with(manager),
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(db.row["status"], "closed")

    async def test_foreign_user_cannot_close_session(self):
        db = StatefulCloseDatabase(
            session_row(12, uuid="mobile-uuid", user_id=25)
        )
        manager = database_module.ChatManager(db)

        with self.assertRaises(database_module.SessionUnavailableError) as raised:
            await mobile_api.gateway_close_session(
                "mobile-uuid",
                mobile_api.CloseSessionRequest(national_code="current-user"),
                request_with(manager),
            )

        self.assertEqual(raised.exception.public_message, "Session unavailable.")
        self.assertEqual(db.row["status"], "active")


if __name__ == "__main__":
    unittest.main(verbosity=2)
