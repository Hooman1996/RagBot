"""Coverage check with fakes for the answering service, RAG and limiter. Synthetic data only."""
from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import os
import stat
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from answering_service import AnswerRequestContext, AnsweringService
from conversation_history import TurnExecutionPolicy
from coverage_check import api as coverage_api
from coverage_check import prompts
from coverage_check.checker import CoverageChecker
from coverage_check.jobs import CheckJobs
from coverage_check.settings import CoverageSettings, RunSettings, SettingsError, load_settings
from coverage_check.store import CheckStore, StoreError, parse_csv
from tests.test_web_auth import csrf, login, setup  # noqa: F401  (fixture)

DOCUMENTS = ["Synthetic_FAQ"]
QUESTION = "  مي‌خوام مساعده بگيرم  "


class Runner:
    async def run(self, function, *args, **kwargs):
        kwargs.pop("wait_for_completion_on_cancel", None)
        return function(*args, **kwargs)


class TextProcessor:
    """Synthetic normalizer: Arabic yeh to Persian yeh, plus padding to strip."""

    def normalize(self, text):
        return " " + text.replace("ي", "ی") + " "


class Classifier:
    def __init__(self, intent="general"):
        self.intent = intent
        self.inputs = []

    async def classify_detailed(self, text):
        self.inputs.append(text)
        return {"type": self.intent, "scenario_id": None}


@dataclass
class Candidate:
    doc_id: str
    content: str


def chunk(n):
    return Candidate(f"k{n}", f"Question: synthetic question {n}\nAnswer: synthetic answer {n}")


class SearchEngine:
    def __init__(self):
        self.calls = []

    async def rerank_search_results(self, query, candidates, top_k):
        self.calls.append({"query": query, "count": len(candidates), "top_k": top_k})
        return list(candidates)[:top_k]


class Rag:
    """retrieve returns k0..k(top_k-1) in rank order; ``judge`` scripts the model."""

    model_id = "synthetic-model"

    def __init__(self, judge=None):
        self.search_engine = SearchEngine()
        self.retrieve_calls = []
        self.completions = []
        self.judge = judge or (lambda kind, ids, call: {"verdict": "none", "chunk_numbers": [], "note": ""})

    async def retrieve(self, query, top_k=None, allowed_docs=None, rerank=False, *,
                       bm25_candidate_limit=None, semantic_candidate_limit=None):
        self.retrieve_calls.append({"query": query, "top_k": top_k, "allowed_docs": allowed_docs,
                                    "bm25": bm25_candidate_limit, "semantic": semantic_candidate_limit})
        return [chunk(n) for n in range(top_k)]

    async def _completion(self, **kwargs):
        system, user = kwargs["messages"]
        kind = "combine" if "each judged a partial answer" in system["content"] else "batch"
        payload = json.loads(user["content"])
        ids = ["k" + item["text"].split("synthetic question ")[1].split("\n")[0] for item in payload["chunks"]]
        call = {"kind": kind, "ids": ids, "kwargs": kwargs, "question": payload["question"]}
        self.completions.append(call)
        reply = self.judge(kind, ids, call)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def answering(rag, intent="general"):
    agent = SimpleNamespace(rag_system=rag)
    return SimpleNamespace(agent_service=agent, text_processor=TextProcessor(), blocking_runner=Runner(),
                           intent_classifier=Classifier(intent), selection_validator=None)


def run_settings(**overrides):
    return CoverageSettings(artifact_dir=None, upload_max_bytes=5242880, max_rows=10000,
                            run=RunSettings(), combine_max=10, chunk_max_chars=4000,
                            model_max_tokens=300).run_values(RunSettings(**overrides))


def check(rag, question=QUESTION, intent="general", **overrides):
    service = answering(rag, intent)
    checker = CoverageChecker(service, asyncio.Semaphore(1), DOCUMENTS, run_settings(**overrides))
    return asyncio.run(checker.check(question)), service


def numbers(ids, wanted):
    return [ids.index(w) + 1 for w in wanted if w in ids]


# Same path as chat ----------------------------------------------------

def test_same_normalization_intent_input_and_retrieval_query_as_chat():
    rag = Rag(judge=lambda kind, ids, call: {"verdict": "complete", "chunk_numbers": [1], "note": ""})
    result, service = check(rag)
    assert result["result"] == "answered"

    chat_rag = Rag()
    chat_classifier = Classifier()
    captured = {}

    class Agent:
        rag_system = chat_rag

        async def process_stateless_message(self, **kwargs):
            captured.update(kwargs)
            await chat_rag.retrieve(kwargs["retrieval_query"], top_k=50, allowed_docs=kwargs["selected_docs"])
            return SimpleNamespace(state={"messages": []}, answer="", history_before=[])

    chat = AnsweringService(agent_service=Agent(), intent_classifier=chat_classifier,
                            history_rewriting_service=None, text_processor=TextProcessor(),
                            blocking_runner=Runner(), category_resolver=lambda doc: "FAQ")
    chat_result = asyncio.run(chat._answer(
        AnswerRequestContext(QUESTION, selected_documents=tuple(DOCUMENTS), use_history=False,
                             persist_agent_state=False),
        history_provider=None, execution_policy=TurnExecutionPolicy()))
    assert service.intent_classifier.inputs == chat_classifier.inputs == [chat_result.normalized_query]
    assert rag.retrieve_calls[0]["query"] == chat_rag.retrieve_calls[0]["query"] == chat_result.final_retrieval_query
    assert rag.completions[0]["question"] == chat_result.final_retrieval_query


def test_chitchat_stops_before_retrieval():
    rag = Rag()
    result, _ = check(rag, intent="chitchat")
    assert result["result"] == "chitchat"
    assert rag.retrieve_calls == [] and rag.completions == []
    assert result["model_calls"] == 0 and result["retrievals"] == 0


# Batches --------------------------------------------------------------

def test_early_stop_at_batch_two():
    def judge(kind, ids, call):
        if "k7" in ids:
            return {"verdict": "complete", "chunk_numbers": numbers(ids, ["k7"]), "note": "synthetic"}
        return {"verdict": "none", "chunk_numbers": [], "note": ""}
    rag = Rag(judge)
    result, _ = check(rag)
    assert len(rag.retrieve_calls) == 1
    first = rag.retrieve_calls[0]
    assert (first["top_k"], first["bm25"], first["semantic"], first["allowed_docs"]) == (150, 150, 150, DOCUMENTS)
    assert rag.search_engine.calls == [{"query": first["query"], "count": 150, "top_k": 50}]
    assert len(rag.completions) == 2 and result["model_calls"] == 2
    assert [c["ids"] for c in rag.completions] == [["k0", "k1", "k2", "k3", "k4"], ["k5", "k6", "k7", "k8", "k9"]]
    assert result["result"] == "answered" and result["answer_batch"] == 2 and result["answer_phase"] == "initial"
    assert result["answer_chunk_ids"] == ["k7"]
    assert result["batches"][1]["chunk_ids"] == ["k5", "k6", "k7", "k8", "k9"]
    assert result["titles"]["k7"] == "synthetic question 7"
    kwargs = rag.completions[0]["kwargs"]
    assert (kwargs["model"], kwargs["temperature"], kwargs["top_p"], kwargs["seed"], kwargs["max_tokens"]) == \
        ("synthetic-model", 0, 1, 42, 300)
    schema = kwargs["response_format"]["json_schema"]
    assert schema["name"] == "coverage_batch_1" and schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert kwargs["messages"][0]["content"].startswith(
        "You check whether a bank's FAQ chunks answer a customer's question.")


def test_batch_size_ten_gives_at_most_five_batch_calls():
    rag = Rag()
    result, _ = check(rag, batch_size=10, keep=50)
    assert len(rag.completions) == 5 and all(len(c["ids"]) == 10 for c in rag.completions)
    assert result["result"] == "not_answered"


def test_combine_partials_in_rank_order():
    def judge(kind, ids, call):
        if kind == "combine":
            return {"verdict": "complete", "chunk_numbers": [1, 3], "note": ""}
        if "k0" in ids:
            return {"verdict": "partial", "chunk_numbers": numbers(ids, ["k3", "k1"]), "note": ""}
        if "k10" in ids:
            return {"verdict": "partial", "chunk_numbers": numbers(ids, ["k12"]), "note": ""}
        return {"verdict": "none", "chunk_numbers": [], "note": ""}
    rag = Rag(judge)
    result, _ = check(rag)
    combines = [c for c in rag.completions if c["kind"] == "combine"]
    assert len(combines) == 1 and combines[0]["ids"] == ["k1", "k3", "k12"]
    assert len(rag.completions) == 11
    assert result["result"] == "answered_combined" and result["answer_chunk_ids"] == ["k1", "k12"]
    assert result["answer_batch"] is None


def test_partial_when_combine_is_not_complete():
    def judge(kind, ids, call):
        if kind == "batch" and "k0" in ids:
            return {"verdict": "partial", "chunk_numbers": [1], "note": ""}
        return {"verdict": "none", "chunk_numbers": [], "note": ""}
    result, _ = check(Rag(judge))
    assert result["result"] == "partial" and result["model_calls"] == 11


def test_wider_search_off_not_answered():
    rag = Rag()
    result, _ = check(rag)
    assert result["result"] == "not_answered"
    assert len(rag.retrieve_calls) == 1 and len(rag.completions) == 10 and not result["broader_used"]


def test_wider_search_on_continues_numbering_and_excludes_judged():
    def judge(kind, ids, call):
        if "k55" in ids:
            return {"verdict": "complete", "chunk_numbers": numbers(ids, ["k55"]), "note": ""}
        return {"verdict": "none", "chunk_numbers": [], "note": ""}
    rag = Rag(judge)
    result, _ = check(rag, broader_enabled=True)
    assert [c["top_k"] for c in rag.retrieve_calls] == [150, 200]
    assert rag.retrieve_calls[1]["bm25"] == rag.retrieve_calls[1]["semantic"] == 200
    assert rag.search_engine.calls[1]["top_k"] == 200
    broader = rag.completions[10:]
    assert broader[0]["ids"] == ["k50", "k51", "k52", "k53", "k54"]
    assert not {i for c in broader for i in c["ids"]} & {f"k{n}" for n in range(50)}
    assert [b["number"] for b in result["batches"]][10:] == [11, 12]
    assert result["result"] == "answered" and result["answer_batch"] == 12 and result["answer_phase"] == "broader"
    assert result["broader_used"] is True


def test_invalid_output_retries_once_then_errors():
    rag = Rag(judge=lambda kind, ids, call: "not json")
    result, _ = check(rag)
    assert result["result"] == "error" and result["error_code"] == "invalid_model_output"
    assert len(rag.completions) == 2

    out_of_batch = Rag(judge=lambda kind, ids, call: {"verdict": "complete", "chunk_numbers": [6], "note": ""})
    assert check(out_of_batch)[0]["error_code"] == "invalid_model_output"
    repeated = Rag(judge=lambda kind, ids, call: {"verdict": "partial", "chunk_numbers": [1, 1], "note": ""})
    assert check(repeated)[0]["error_code"] == "invalid_model_output"


def test_failed_calls_record_fixed_codes_only():
    class Failing(Rag):
        async def retrieve(self, *args, **kwargs):
            self.retrieve_calls.append(kwargs)
            raise RuntimeError("synthetic secret text")
    rag = Failing()
    result, _ = check(rag)
    assert result["error_code"] == "retrieval_failed" and len(rag.retrieve_calls) == 2
    assert "synthetic secret text" not in json.dumps(result)


def test_parse_verdict_rules():
    assert prompts.parse_verdict('{"verdict":"none","chunk_numbers":[],"note":""}', 5).verdict == "none"
    assert prompts.parse_verdict('{"verdict":"none","chunk_numbers":[],"note":"","x":1}', 5) is None
    assert prompts.parse_verdict('{"verdict":"none","chunk_numbers":[],"note":"' + "a" * 201 + '"}', 5) is None
    assert prompts.parse_verdict(None, 5) is None


# CSV and settings ---------------------------------------------------

def test_csv_rules():
    with pytest.raises(StoreError, match="missing_query_column"):
        parse_csv(b"question,id\nx,1\n", 10)
    rows = parse_csv("\ufeffid,query,secret\n7,first,hidden\n8,,hidden\n".encode(), 10)
    assert rows == [{"row": 1, "id": "7", "question": "first"}, {"row": 2, "id": "8", "question": ""}]
    with pytest.raises(StoreError, match="too_many_rows"):
        parse_csv(b"query\na\nb\nc\n", 2)
    rag = Rag()
    result, _ = check(rag, question="")
    assert result["error_code"] == "empty_query" and rag.retrieve_calls == [] and rag.completions == []


@pytest.mark.parametrize("key,value", [
    ("KNOWLEDGE_COVERAGE_ENABLED", "maybe"), ("KNOWLEDGE_COVERAGE_ARTIFACT_DIR", "relative/dir"),
    ("KNOWLEDGE_COVERAGE_ARTIFACT_DIR", "/tmp/coverage"), ("KNOWLEDGE_COVERAGE_ARTIFACT_DIR", os.getcwd() + "/x"),
    ("KNOWLEDGE_COVERAGE_UPLOAD_MAX_BYTES", "1023"), ("KNOWLEDGE_COVERAGE_MAX_ROWS", "100001"),
    ("KNOWLEDGE_COVERAGE_DEPTH", "0"), ("KNOWLEDGE_COVERAGE_KEEP", "151"), ("KNOWLEDGE_COVERAGE_BATCH_SIZE", "21"),
    ("KNOWLEDGE_COVERAGE_BROADER_ENABLED", "yes"), ("KNOWLEDGE_COVERAGE_BROADER_DEPTH", "150"),
    ("KNOWLEDGE_COVERAGE_BROADER_KEEP", "1001"), ("KNOWLEDGE_COVERAGE_COMBINE_MAX", "1"),
    ("KNOWLEDGE_COVERAGE_CHUNK_MAX_CHARS", "499"), ("KNOWLEDGE_COVERAGE_MODEL_MAX_TOKENS", "2049"),
    ("KNOWLEDGE_COVERAGE_DEPTH", "abc"),
])
def test_out_of_range_env_values_name_the_variable(key, value):
    from coverage_check.settings import coverage_enabled
    env = {key: value}
    with pytest.raises(SettingsError) as raised:
        coverage_enabled(env)
        load_settings(env)
    assert str(raised.value) == key and value not in str(raised.value)


def test_env_defaults():
    settings = load_settings({})
    assert settings.run == RunSettings(150, 50, 5, False, 200, 50)
    assert (settings.combine_max, settings.chunk_max_chars, settings.model_max_tokens, settings.max_rows) == (10, 4000, 300, 10000)


@pytest.mark.parametrize("field,overrides", [
    ("depth", {"depth": 1001}), ("keep", {"keep": 151}), ("keep", {"keep": 0}),
    ("batch_size", {"batch_size": 0}), ("broader_depth", {"broader_depth": 150}),
    ("broader_depth", {"broader_depth": 1001}), ("broader_keep", {"broader_keep": 0}),
    ("broader_enabled", {"broader_enabled": 1}), ("depth", {"depth": True}),
])
def test_out_of_range_request_values(field, overrides):
    with pytest.raises(SettingsError, match=f"^{field}$"):
        RunSettings(**overrides)


# API ------------------------------------------------------------------

@pytest.fixture
def api(setup, tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_COVERAGE_ENABLED", raising=False)
    if not any(getattr(r, "path", None) == "/api/knowledge-coverage/checks" for r in main.app.routes):
        main.app.include_router(coverage_api.router)
    settings = CoverageSettings(artifact_dir=tmp_path / "private", upload_max_bytes=5242880, max_rows=100,
                                run=RunSettings(), combine_max=10, chunk_max_chars=4000, model_max_tokens=300)
    rag = Rag()
    service = answering(rag)
    monkeypatch.setattr(main.app.state, "answering_service", service, raising=False)
    monkeypatch.setattr(main.app.state, "request_limiter", asyncio.Semaphore(1), raising=False)
    monkeypatch.setattr(main.app.state, "blocking_runner", Runner(), raising=False)
    setup.get_available_documents = lambda: [{"title": "Synthetic_FAQ"}]
    monkeypatch.setattr(main.app.state, "db_manager", setup, raising=False)
    runtime = coverage_api.CoverageRuntime(main.app, settings)
    queued = []
    runtime.jobs.enqueue = queued.append
    monkeypatch.setattr(main.app.state, "coverage_check", runtime, raising=False)
    return SimpleNamespace(db=setup, runtime=runtime, queued=queued)


def start_payload(**overrides):
    body = "id,query,extra\n1,first synthetic question,drop\n2,=SUM(1),drop\n".encode()
    payload = {"csv_base64": base64.b64encode(body).decode(), "file_name": "C:\\fake\\questions.csv",
               "documents": ["Synthetic_FAQ"], "depth": 150, "keep": 50, "batch_size": 5,
               "broader_enabled": False, "broader_depth": 200, "broader_keep": 50}
    return {**payload, **overrides}


ROUTES = [("GET", "/knowledge-coverage"), ("GET", "/api/knowledge-coverage/documents"),
          ("POST", "/api/knowledge-coverage/checks"), ("GET", "/api/knowledge-coverage/checks"),
          ("GET", "/api/knowledge-coverage/checks/{id}"), ("GET", "/api/knowledge-coverage/checks/{id}/rows"),
          ("POST", "/api/knowledge-coverage/checks/{id}/cancel"),
          ("POST", "/api/knowledge-coverage/checks/{id}/resume"),
          ("GET", "/api/knowledge-coverage/checks/{id}/export")]


def test_admin_starts_and_viewer_reads_another_users_run(api):
    api.db.users[1]["role"] = "admin"
    api.db.users[2]["role"] = "dashboard_viewer"
    with TestClient(main.app, raise_server_exceptions=False) as admin, \
            TestClient(main.app, raise_server_exceptions=False) as viewer:
        login(admin, "alice")
        assert admin.get("/knowledge-coverage").status_code == 200
        assert admin.get("/api/knowledge-coverage/documents").json()["documents"][0]["name"] == "Synthetic_FAQ"
        response = admin.post("/api/knowledge-coverage/checks", json=start_payload(), headers=csrf(admin))
        assert response.status_code == 201, response.text
        run_id = response.json()["run_id"]
        assert api.queued == [run_id]
        bad = admin.post("/api/knowledge-coverage/checks", json=start_payload(keep=151), headers=csrf(admin))
        assert bad.status_code == 422 and bad.json()["detail"] == "invalid_keep"

        stored = api.runtime.store
        meta = stored.meta(run_id)
        assert meta["file_name"] == "questions.csv" and meta["owner_id"] == 1 and meta["state"] == "queued"
        assert meta["settings"]["depth"] == 150 and meta["settings"]["model_max_tokens"] == 300
        assert "drop" not in json.dumps(stored.inputs(run_id))
        folder = stored.root / run_id
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
        assert stat.S_IMODE((folder / "meta.json").stat().st_mode) == 0o600

        login(viewer, "bob")
        page = viewer.get("/knowledge-coverage")
        assert page.status_code == 200 and 'id="coverageForm"' not in page.text
        listing = viewer.get("/api/knowledge-coverage/checks").json()
        assert [c["run_id"] for c in listing] == [run_id] and listing[0]["done"] == 0
        detail = viewer.get(f"/api/knowledge-coverage/checks/{run_id}").json()
        assert detail["counts"]["waiting"] == 2 and detail["done"] == 0
        rows = viewer.get(f"/api/knowledge-coverage/checks/{run_id}/rows?limit=100").json()
        assert [r["question"] for r in rows["rows"]] == ["first synthetic question", "=SUM(1)"]
        assert viewer.get(f"/api/knowledge-coverage/checks/{run_id}/rows?limit=101").status_code == 422
        assert viewer.get(f"/api/knowledge-coverage/checks/{run_id}/export").status_code == 200
        for method, path in ROUTES:
            if method == "POST" or path.endswith("/documents"):
                url = path.replace("{id}", run_id)
                kwargs = {"headers": csrf(viewer)} if method == "POST" else {}
                if path.endswith("/checks"):
                    kwargs["json"] = start_payload()
                assert viewer.request(method, url, **kwargs).status_code == 403, url

        cancelled = admin.post(f"/api/knowledge-coverage/checks/{run_id}/cancel", headers=csrf(admin))
        assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
        assert admin.post(f"/api/knowledge-coverage/checks/{run_id}/cancel", headers=csrf(admin)).status_code == 409
        resumed = admin.post(f"/api/knowledge-coverage/checks/{run_id}/resume", headers=csrf(admin))
        assert resumed.status_code == 200 and api.queued == [run_id, run_id]


def test_plain_user_is_denied_everywhere(api):
    api.db.users[1]["role"] = "user"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        for method, path in ROUTES:
            url = path.replace("{id}", "c_" + "a" * 32)
            kwargs = {"headers": csrf(client)} if method == "POST" else {}
            assert client.request(method, url, **kwargs).status_code == 403, url
        assert 'href="/knowledge-coverage"' not in client.get("/app").text


def test_plain_user_page_forbidden_and_no_sidebar_link(api):
    api.db.users[1]["role"] = "user"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        page = client.get("/knowledge-coverage", follow_redirects=False)
        assert page.status_code == 403 and "Access denied" in page.text
        app_page = client.get("/app")
        assert app_page.status_code == 200
        assert "Knowledge coverage" not in app_page.text
        assert 'href="/knowledge-coverage"' not in app_page.text


def test_disabled_flag_returns_404_and_hides_link(api, monkeypatch):
    api.db.users[1]["role"] = "admin"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        assert 'href="/knowledge-coverage"' in client.get("/app").text
        monkeypatch.setenv("KNOWLEDGE_COVERAGE_ENABLED", "false")
        for method, path in ROUTES:
            url = path.replace("{id}", "c_" + "a" * 32)
            kwargs = {"headers": csrf(client)} if method == "POST" else {}
            assert client.request(method, url, **kwargs).status_code == 404, url
        assert 'href="/knowledge-coverage"' not in client.get("/app").text


# Export and restart ---------------------------------------------------

def make_run(tmp_path, rows):
    store = CheckStore(tmp_path / "private")
    meta = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(), rows=rows)
    return store, meta["run_id"]


def test_export_columns_and_formula_prefix(api):
    api.db.users[1]["role"] = "dashboard_viewer"
    store = api.runtime.store
    meta = store.create(owner_id=2, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                        rows=[{"row": 1, "id": "-5", "question": "=cmd"}, {"row": 2, "id": "@x", "question": "+1"}])
    run_id = meta["run_id"]
    store.write_result(run_id, 1, {"result": "answered", "answer_batch": 2, "answer_phase": "initial",
                                   "answer_chunk_ids": ["k7"], "combines": [],
                                   "batches": [{"number": n, "phase": "initial", "verdict": v, "chunk_ids": ["k7"]}
                                               for n, v in ((1, "none"), (2, "complete"))],
                                   "titles": {"k7": "=title"}, "broader_used": False, "model_calls": 2,
                                   "duration_ms": 12, "error_code": None, "note": "-note"})
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = client.get(f"/api/knowledge-coverage/checks/{run_id}/export")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    lines = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert lines[0] == ["row", "id", "question", "result", "answer_batch", "answer_phase", "answer_chunk_ids",
                        "answer_faq_titles", "batches_checked", "broader_used", "model_calls", "duration_ms",
                        "error_code", "note"]
    assert lines[1] == ["1", "'-5", "'=cmd", "answered", "2", "initial", "k7", "'=title", "2", "false", "2", "12",
                        "", "'-note"]
    assert lines[2][:4] == ["2", "'@x", "'+1", "waiting"]


def test_restart_interrupts_and_resume_finishes_only_missing_rows(tmp_path):
    rows = [{"row": n, "id": str(n), "question": f"synthetic {n}"} for n in (1, 2, 3)]
    store, run_id = make_run(tmp_path, rows)
    store.set_state(run_id, "running")
    store.write_result(run_id, 1, {"result": "answered"})
    checked = []

    class Checker:
        async def check(self, question):
            checked.append(question)
            return {"result": "not_answered", "error_code": None, "model_calls": 10, "duration_ms": 1}

    async def scenario():
        jobs = CheckJobs(CheckStore(tmp_path / "private"), lambda meta: Checker())
        assert await jobs.recover() == 1
        assert jobs.store.meta(run_id)["state"] == "interrupted"
        jobs.store.set_state(run_id, "queued")
        jobs.enqueue(run_id)
        for _ in range(200):
            if jobs.store.meta(run_id)["state"] == "completed":
                break
            await asyncio.sleep(0.01)
        await jobs.aclose()
        return jobs.store

    final = asyncio.run(scenario())
    assert final.meta(run_id)["state"] == "completed"
    assert checked == ["synthetic 2", "synthetic 3"]
    assert final.result_codes(run_id) == {1: "answered", 2: "not_answered", 3: "not_answered"}


def test_queue_runs_in_fifo_order_and_cancel_between_rows(tmp_path):
    store = CheckStore(tmp_path / "private")
    first = store.create(owner_id=1, file_name="a.csv", documents=DOCUMENTS, settings=run_settings(),
                         rows=[{"row": n, "id": "", "question": f"a{n}"} for n in (1, 2, 3)])["run_id"]
    second = store.create(owner_id=1, file_name="b.csv", documents=DOCUMENTS, settings=run_settings(),
                          rows=[{"row": 1, "id": "", "question": "b1"}])["run_id"]
    order = []

    async def scenario():
        jobs = None

        class Checker:
            async def check(self, question):
                order.append(question)
                if question == "a1":
                    await jobs.cancel(first)
                return {"result": "not_answered", "error_code": None, "model_calls": 0, "duration_ms": 0}

        jobs = CheckJobs(store, lambda meta: Checker())
        jobs.enqueue(first)
        jobs.enqueue(second)
        for _ in range(200):
            if store.meta(second)["state"] == "completed":
                break
            await asyncio.sleep(0.01)
        await jobs.aclose()

    asyncio.run(scenario())
    assert order == ["a1", "b1"]
    assert store.meta(first)["state"] == "cancelled" and store.meta(second)["state"] == "completed"
