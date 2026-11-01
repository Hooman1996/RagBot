"""Synthetic platform/session tests; no application services or private data."""

import asyncio
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from answering_service import AnswerRequestContext
from conversation_history import ConversationSnapshot
from document_category import get_document_category
from platform_context import (
    PlatformContext,
    instance_platform,
    resolve_platform,
    session_platform,
)
from tests import test_answering_service as answering_tests
from tests.test_mobile_history_content import (
    GatewayChatManager,
    StatefulCloseDatabase,
    database_module,
    mobile_api,
    request_with,
    session_row,
)
from utils.service_errors import InvalidRequestError


@pytest.fixture(autouse=True)
def shared_mode(monkeypatch):
    monkeypatch.setenv("CHATBOT_PLATFORM", "auto")


def test_default_and_configuration(monkeypatch):
    monkeypatch.delenv("CHATBOT_PLATFORM")
    assert instance_platform() == "hibank"
    assert resolve_platform().platform == "hibank"
    monkeypatch.setenv("CHATBOT_PLATFORM", "unknown")
    with pytest.raises(ValueError, match="CHATBOT_PLATFORM"):
        instance_platform()


@pytest.mark.parametrize(
    "title,owner",
    [
        ("General_FAQ", "hibank"),
        ("NegahBoom_FAQ", "negahboom"),
        ("قرارداد نمونه", "hibank"),
        ("ابلاغیه نمونه", "hibank"),
    ],
)
def test_ownership_independent_of_category(title, owner):
    assert resolve_platform(documents=[title]).platform == owner
    if title.endswith("FAQ"):
        assert get_document_category(title) == "FAQ"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"documents": ["General_FAQ", "NegahBoom_FAQ"]},
        {"documents": ["NegahBoom_FAQ", "General_FAQ"]},
        {"documents": ["unknown"]},
        {"header": "auto"},
        {"header": "NegahBoom"},
        {"header": ""},
        {"documents": ["General_FAQ"], "header": "negahboom"},
        {"header": "negahboom", "session": {"meta_data": {}}},
        {
            "documents": ["General_FAQ"],
            "session": {"meta_data": {"chatbot_platform": "negahboom"}},
        },
    ],
)
def test_invalid_or_conflicting_signals(kwargs):
    with pytest.raises(InvalidRequestError):
        resolve_platform(**kwargs)


@pytest.mark.parametrize(
    "mode,other", [("hibank", "NegahBoom_FAQ"), ("negahboom", "General_FAQ")]
)
def test_fixed_instances(mode, other):
    assert resolve_platform(mode=mode).platform == mode
    with pytest.raises(InvalidRequestError):
        resolve_platform(mode=mode, documents=[other])
    with pytest.raises(InvalidRequestError):
        resolve_platform(
            mode=mode, header="negahboom" if mode == "hibank" else "hibank"
        )


def test_legacy_and_existing_sessions():
    assert session_platform({"meta_data": None}) == "hibank"
    assert session_platform({"meta_data": "{}"}) == "hibank"
    row = {"meta_data": {"chatbot_platform": "negahboom"}}
    assert resolve_platform(session=row).platform == "negahboom"


class BoundProvider:
    namespace = "production"

    def __init__(self, platform):
        self.platform = platform
        self.history_reads = 0

    async def load_snapshot(self, key):
        metadata = {} if self.platform is None else {"chatbot_platform": self.platform}
        return ConversationSnapshot(key, 7, {}, metadata)

    async def load_rewrite_messages(self, key):
        self.history_reads += 1
        return [{"role": "user", "content": "synthetic history"}]


def test_cross_platform_stops_before_rewrite_and_generation():
    async def run():
        fixture = answering_tests.AnsweringServiceTests()
        provider = BoundProvider(None)
        service = fixture.make_service(history_provider=provider)
        with pytest.raises(InvalidRequestError):
            await service.answer(
                AnswerRequestContext(
                    original_query="synthetic",
                    session_id="12",
                    selected_documents=("NegahBoom_FAQ",),
                )
            )
        assert provider.history_reads == 0
        assert fixture.rewriter.rewrite_calls == []
        assert fixture.agent.persisted == []
        assert fixture.classifier.queries == []

    asyncio.run(run())


def test_bound_negahboom_turns_and_explicit_rewrite_context():
    async def run():
        fixture = answering_tests.AnsweringServiceTests()
        service = fixture.make_service(
            intent="chitchat", history_provider=BoundProvider("negahboom")
        )
        for documents in [("NegahBoom_FAQ",), ()]:
            await service.answer(
                AnswerRequestContext(
                    original_query="synthetic",
                    session_id="12",
                    selected_documents=documents,
                )
            )
        assert all(
            call["platform_context"].platform == "negahboom"
            for call in fixture.agent.persisted
        )
        assert all(
            call["platform_context"].platform == "negahboom"
            for call in fixture.rewriter.rewrite_calls
        )

    asyncio.run(run())


def test_concurrent_answers_have_independent_context():
    async def run():
        fixture = answering_tests.AnsweringServiceTests()
        service = fixture.make_service()

        async def rewrite(**kwargs):
            await asyncio.sleep(0)
            fixture.rewriter.rewrite_calls.append(kwargs)
            return kwargs["current_query"]

        fixture.rewriter.rewrite_query = rewrite
        await asyncio.gather(
            *[
                service.answer(
                    AnswerRequestContext(
                        original_query=platform,
                        session_id=str(index),
                        selected_documents=(document,),
                    )
                )
                for index, (platform, document) in enumerate(
                    [
                        ("hibank", "General_FAQ"),
                        ("negahboom", "NegahBoom_FAQ"),
                    ]
                )
            ]
        )
        for call in fixture.agent.persisted:
            assert call["user_message"] == call["platform_context"].platform
        for call in fixture.rewriter.rewrite_calls:
            assert call["current_query"] == call["platform_context"].platform

    asyncio.run(run())


class RacingDatabase(database_module.DatabaseManager):
    """Model PostgreSQL UUID uniqueness and atomic statement execution."""

    def __init__(self):
        self.row = None
        self.lock = threading.Lock()
        self.first_reads = threading.Barrier(2)
        self.local = threading.local()
        self.updates = []

    def get_session_by_uuid(self, uuid):
        if not getattr(self.local, "read", False):
            self.local.read = True
            self.first_reads.wait(timeout=5)
            return None
        with self.lock:
            return copy.deepcopy(self.row)

    def _execute(self, query, params=None, fetch=None):
        with self.lock:
            if "INSERT INTO chat_sessions" in query:
                assert "ON CONFLICT (uuid) DO NOTHING" in query
                if self.row is not None:
                    return None
                self.row = session_row(12, meta_data=json.loads(params[3]))
                return copy.deepcopy(self.row)
            assert "COALESCE(meta_data::jsonb->>'chatbot_platform', 'hibank')" in query
            assert "jsonb_build_object" in query
            binding = session_platform(self.row)
            self.row["meta_data"].update(json.loads(params[0]))
            self.row["meta_data"]["chatbot_platform"] = binding
            self.updates.append(query)


@pytest.mark.parametrize(
    "platforms", [("negahboom", "hibank"), ("negahboom", "negahboom")]
)
def test_concurrent_first_creation_and_stale_metadata_updates(platforms):
    db = RacingDatabase()

    def create(platform):
        try:
            return db.get_or_create_mobile_session(
                7, "synthetic-uuid", platform_context=PlatformContext(platform)
            )
        except InvalidRequestError:
            return None

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(create, platforms))
    winner = session_platform(db.row)
    assert sum(result is not None for result in results) == (
        2 if platforms[0] == platforms[1] else 1
    )
    assert all(session_platform(result) == winner for result in results if result)
    # An old snapshot and an attempted overwrite cannot erase/change the binding.
    db.update_session_metadata(12, {"agent_state": {"messages": []}})
    db.update_session_metadata(
        12,
        {
            "chatbot_platform": "hibank" if winner == "negahboom" else "negahboom",
            "other": True,
        },
    )
    assert session_platform(db.row) == winner
    assert db.row["meta_data"]["other"] is True
    assert "agent_state" in db.row["meta_data"]


def test_history_and_close_respect_platform_and_preserve_owner_checks():
    async def run():
        for platform in ("hibank", "negahboom"):
            row = session_row(
                12, uuid="synthetic-uuid", meta_data={"chatbot_platform": platform}
            )
            db = StatefulCloseDatabase(row)
            manager = database_module.ChatManager(db)
            req = request_with(manager)
            req.headers = {
                "X-Chatbot-Platform": "hibank"
                if platform == "negahboom"
                else "negahboom"
            }
            with pytest.raises(InvalidRequestError):
                await mobile_api.gateway_close_session(
                    "synthetic-uuid",
                    mobile_api.CloseSessionRequest(national_code="synthetic"),
                    req,
                )
            assert db.row["status"] == "active"
            manager.get_messages = lambda _key: []
            with pytest.raises(InvalidRequestError):
                await mobile_api.gateway_history(req, "synthetic", "synthetic-uuid")
            # Ownership denial takes precedence even when platform signals conflict.
            db.row["user_id"] = 25
            with pytest.raises(database_module.SessionUnavailableError):
                await mobile_api.gateway_close_session(
                    "synthetic-uuid",
                    mobile_api.CloseSessionRequest(national_code="synthetic"),
                    req,
                )
            with pytest.raises(database_module.SessionUnavailableError):
                await mobile_api.gateway_history(req, "synthetic", "synthetic-uuid")
            db.row["user_id"] = 7
            req.headers = {}
            await mobile_api.gateway_close_session(
                "synthetic-uuid",
                mobile_api.CloseSessionRequest(national_code="synthetic"),
                req,
            )
            assert db.row["status"] == "closed"
            assert session_platform(db.row) == platform

        manager = GatewayChatManager()
        original = manager.get_user_sessions

        def listing(*args):
            rows = original(*args)
            rows["13"] = {
                **rows["12"],
                "id": "13",
                "meta_data": {"chatbot_platform": "negahboom"},
            }
            return rows

        manager.get_user_sessions = listing
        req = request_with(manager)
        assert [
            s["id"]
            for s in (await mobile_api.gateway_history(req, "synthetic"))["sessions"]
        ] == [12]
        req.headers = {"X-Chatbot-Platform": "negahboom"}
        assert [
            s["id"]
            for s in (await mobile_api.gateway_history(req, "synthetic"))["sessions"]
        ] == [13]

    asyncio.run(run())


def test_real_agent_and_history_provider_preserve_binding_across_turns():
    from tests import test_p0_p1_repairs as agent_tests

    async def run():
        fixture = agent_tests.AgentServiceContractTests()
        await fixture.asyncSetUp()
        try:
            db = fixture.FakeDb()
            db.metadata = {"chatbot_platform": "negahboom", "other": "synthetic"}
            service = fixture.module.AgentService(
                rag_system=object(),
                intent_classifier=object(),
                scenarios_db={},
                db_manager=db,
                chat_manager=object(),
            )
            for documents in [["NegahBoom_FAQ"], []]:
                result = await service.process_message_detailed(
                    "12", "synthetic", selected_docs=documents
                )
                assert result.state["platform"] == "negahboom"
                assert db.metadata["chatbot_platform"] == "negahboom"
                assert db.metadata["other"] == "synthetic"
            assert len(db.metadata["agent_state"]["messages"]) == 4
            before = len(fixture.graph.inputs)
            with pytest.raises(InvalidRequestError):
                await service.process_message_detailed(
                    "12", "synthetic", selected_docs=["General_FAQ"]
                )
            assert len(fixture.graph.inputs) == before
        finally:
            await fixture.asyncTearDown()

    asyncio.run(run())


def web_functions(**overrides):
    """Execute the actual handlers without starting heavy application services."""
    import ast
    from pathlib import Path

    from fastapi import HTTPException

    from platform_context import check_query, check_session, request_header

    tree = ast.parse(Path("main.py").read_text())
    names = {
        "require_owned_session",
        "get_sessions",
        "get_session",
        "create_session",
        "query_documents",
        "lifespan",
    }
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in names
    ]
    for node in functions:
        node.decorator_list = []
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            *functions,
        ],
        type_ignores=[],
    )
    namespace = dict(
        resolve_platform=resolve_platform,
        session_platform=session_platform,
        check_session=check_session,
        check_query=check_query,
        request_header=request_header,
        blocking_runner=answering_tests.ImmediateRunner(),
        HTTPException=HTTPException,
        **overrides,
    )
    exec(compile(ast.fix_missing_locations(module), "main.py", "exec"), namespace)  # noqa: S102 - isolated actual handlers
    return namespace


def test_web_creation_listing_access_and_ownership():
    from fastapi import HTTPException

    async def run():
        row = session_row(12, meta_data={"chatbot_platform": "negahboom"})
        db = SimpleNamespace(get_session_by_id=lambda _id: row)
        manager = SimpleNamespace(
            get_user_sessions=lambda _id: {"12": row, "13": session_row(13)},
            get_session=lambda _id: row,
            create_new_chat=lambda _id, **kwargs: kwargs,
        )
        ns = web_functions(db_manager=db, chat_manager=manager)
        request = SimpleNamespace(headers={})
        user = SimpleNamespace(id=7)
        assert len((await ns["get_sessions"](user, request))["sessions"]) == 1
        assert (await ns["get_sessions"](user, request))["sessions"][0]["id"] == 13
        request.headers = {"X-Chatbot-Platform": "negahboom"}
        assert (await ns["get_sessions"](user, request))["sessions"] == [row]
        created = await ns["create_session"](None, user, request)
        assert created["platform_context"].platform == "negahboom"
        assert await ns["get_session"]("12", user, request) == row
        request.headers = {"X-Chatbot-Platform": "hibank"}
        with pytest.raises(InvalidRequestError):
            await ns["get_session"]("12", user, request)
        with pytest.raises(HTTPException) as denied:
            await ns["get_session"]("12", SimpleNamespace(id=99), request)
        assert denied.value.status_code == 404

    asyncio.run(run())


def test_web_insert_includes_binding_before_first_history_read():
    db = database_module.DatabaseManager.__new__(database_module.DatabaseManager)
    captured = []

    def execute(query, params=None, fetch=None):
        captured.append((query, params))
        assert "'active', FALSE, %s" in query
        return session_row(12, meta_data=json.loads(params[5]))

    db._execute = execute
    row = db.create_session(7, platform_context=PlatformContext("negahboom"))
    assert session_platform(row) == "negahboom"
    assert len(captured) == 1


def test_legacy_database_session_cannot_be_claimed():
    from tests.test_mobile_history_content import ScriptedMobileSessionDatabase

    db = ScriptedMobileSessionDatabase([session_row(12)])
    with pytest.raises(InvalidRequestError):
        db.get_or_create_mobile_session(
            7, "synthetic", platform_context=PlatformContext("negahboom")
        )
    assert len(db.executions) == 1


def test_startup_rejects_invalid_mode_before_service_initialization(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("CHATBOT_PLATFORM", "invalid")
    ns = web_functions(
        validate_config=lambda: None, instance_platform=instance_platform
    )

    async def run():
        startup = ns["lifespan"](SimpleNamespace(state=SimpleNamespace()))
        with pytest.raises(ValueError, match="CHATBOT_PLATFORM"):
            await anext(startup)

    asyncio.run(run())


def test_web_and_mobile_reject_switch_before_turn_side_effects():
    from types import SimpleNamespace

    async def run():
        row = session_row(12)
        db = SimpleNamespace(
            _validate_mobile_session=database_module.DatabaseManager._validate_mobile_session,
            get_session_by_id=lambda _key: row,
            get_session_by_uuid=lambda _key: row,
            get_or_create_user_by_national_code=lambda _code: {"id": 7},
        )
        ns = web_functions(db_manager=db)
        req = SimpleNamespace(headers={})
        with pytest.raises(InvalidRequestError):
            await ns["query_documents"](
                SimpleNamespace(session_id="12", documents=["NegahBoom_FAQ"]),
                req,
                SimpleNamespace(id=7),
            )
        req = request_with(SimpleNamespace(db=db))
        with pytest.raises(InvalidRequestError):
            await mobile_api.gateway_talk(
                mobile_api.TalkRequest(
                    session_id="synthetic",
                    query="synthetic",
                    national_code="synthetic",
                    documents=["NegahBoom_FAQ"],
                ),
                req,
            )
        # These minimal doubles deliberately have no history/generation/write APIs.

    asyncio.run(run())
