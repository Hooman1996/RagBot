"""Coverage check with fakes for the answering service, RAG and limiter. Synthetic data only."""
from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import os
import stat
import threading
import time
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
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
from utils.concurrency import AdmissionLimiter

DOCUMENTS = ["Synthetic_FAQ"]
VERSION = prompts.PROMPT_VERSION
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
        kind = "combine" if system["content"] == prompts.SYSTEM["combine"] else "batch"
        payload = json.loads(user["content"])
        ids = ["k" + item["text"].split("synthetic question ")[1].split("\n")[0] for item in payload["chunks"]]
        call = {"kind": kind, "ids": ids, "kwargs": kwargs, "question": payload["question"]}
        self.completions.append(call)
        reply = self.judge(kind, ids, call)
        # A ("length", reply) tuple scripts a reply cut off at max_tokens.
        finish_reason, reply = reply if isinstance(reply, tuple) else ("stop", reply)
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason,
                                                        message=SimpleNamespace(content=content))])


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
    assert schema["name"] == "coverage_batch_2" and schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert kwargs["messages"][0]["content"] == prompts.SYSTEM["batch"]
    assert kwargs["messages"][0]["content"].startswith("You are a strict grader for a bank's FAQ knowledge base.")


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

    extra_field = Rag(judge=lambda kind, ids, call: {"note": "", "chunk_numbers": [], "verdict": "none", "x": 1})
    assert check(extra_field)[0]["error_code"] == "invalid_model_output"


@pytest.mark.parametrize("verdict,chunk_numbers", [
    ("complete", []), ("partial", []), ("complete", [1, 1]), ("partial", [2, 2]),
    ("complete", [6]), ("partial", [0]), ("complete", [-1])])
def test_bad_chunk_numbers_give_invalid_chunk_numbers_after_two_attempts(verdict, chunk_numbers):
    rag = Rag(judge=lambda kind, ids, call: {"note": "", "chunk_numbers": chunk_numbers, "verdict": verdict})
    result, _ = check(rag)
    assert result["result"] == "error" and result["error_code"] == "invalid_chunk_numbers"
    assert len(rag.completions) == 2 and result["model_calls"] == 2


def test_none_with_numbers_is_stored_with_no_relied_chunks():
    rag = Rag(judge=lambda kind, ids, call: {"note": "", "chunk_numbers": [2], "verdict": "none"})
    result, _ = check(rag)
    assert result["result"] == "not_answered" and result["batches"]
    assert all(b["verdict"] == "none" and b["relied_chunk_ids"] == [] for b in result["batches"])


def test_long_note_is_stored_as_200_characters():
    rag = Rag(judge=lambda kind, ids, call: {"note": "n" * 600, "chunk_numbers": [1], "verdict": "complete"})
    result, _ = check(rag)
    assert result["result"] == "answered" and result["answer_chunk_ids"] == ["k0"]
    assert result["note"] == "n" * 200 and result["batches"][0]["note"] == "n" * 200


def test_reply_cut_at_max_tokens_twice_gives_model_output_cut():
    full = {"note": "", "chunk_numbers": [1], "verdict": "complete"}
    rag = Rag(judge=lambda kind, ids, call: ("length", full))
    result, _ = check(rag)
    assert result["result"] == "error" and result["error_code"] == "model_output_cut"
    assert result["model_calls"] == 2 and len(rag.completions) == 2


def test_cut_reply_then_valid_reply_is_used():
    replies = iter([("length", '{"note": "'), {"note": "", "chunk_numbers": [1], "verdict": "complete"}])
    rag = Rag(judge=lambda kind, ids, call: next(replies))
    result, _ = check(rag)
    assert result["result"] == "answered" and result["model_calls"] == 2


def test_error_after_two_judged_batches_keeps_both_batches():
    def judge(kind, ids, call):
        if "k10" in ids:
            return "not json"
        return {"note": "synthetic", "chunk_numbers": [], "verdict": "none"}
    rag = Rag(judge)
    result, _ = check(rag)
    assert result["result"] == "error" and result["error_code"] == "invalid_model_output"
    assert [b["number"] for b in result["batches"]] == [1, 2]
    assert [b["chunk_ids"] for b in result["batches"]] == [
        ["k0", "k1", "k2", "k3", "k4"], ["k5", "k6", "k7", "k8", "k9"]]
    assert result["model_calls"] == 4


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
    verdict, code = prompts.parse_verdict('{"note":"","chunk_numbers":[],"verdict":"none"}', 5)
    assert verdict.verdict == "none" and code is None
    assert prompts.parse_verdict('{"note":"","chunk_numbers":[],"verdict":"none","x":1}', 5) == \
        (None, "invalid_model_output")
    assert prompts.parse_verdict('{"note":"","chunk_numbers":[],"verdict":"maybe"}', 5) == \
        (None, "invalid_model_output")
    assert prompts.parse_verdict(None, 5) == (None, "invalid_model_output")
    verdict, code = prompts.parse_verdict('{"note":"' + "a" * 600 + '","chunk_numbers":[3],"verdict":"partial"}', 5)
    assert code is None and verdict.note == "a" * 200 and verdict.chunk_numbers == [3]
    verdict, _ = prompts.parse_verdict('{"note":"","chunk_numbers":[2, 9],"verdict":"none"}', 5)
    assert verdict.chunk_numbers == []
    for numbers_ in ("[]", "[1,1]", "[0]", "[6]"):
        reply = '{"note":"","chunk_numbers":' + numbers_ + ',"verdict":"complete"}'
        assert prompts.parse_verdict(reply, 5) == (None, "invalid_chunk_numbers")


def test_verdict_schema_lists_note_then_chunk_numbers_then_verdict():
    schema = prompts.Verdict.model_json_schema()
    assert list(schema["properties"]) == ["note", "chunk_numbers", "verdict"]
    assert schema["required"] == ["note", "chunk_numbers", "verdict"]
    assert schema["additionalProperties"] is False and "maxLength" not in schema["properties"]["note"]
    assert prompts.response_format()["json_schema"]["name"] == prompts.SCHEMA_NAME == "coverage_batch_2"


def test_prompt_version_changes_when_any_prompt_string_changes():
    schema = prompts.Verdict.model_json_schema()
    version = prompts.prompt_version(prompts.SYSTEM, schema, prompts.SCHEMA_NAME)
    assert version == prompts.PROMPT_VERSION and len(version) == 12
    assert all(ch in "0123456789abcdef" for ch in version)
    for kind in ("batch", "combine"):
        changed = {**prompts.SYSTEM, kind: prompts.SYSTEM[kind] + " "}
        assert prompts.prompt_version(changed, schema, prompts.SCHEMA_NAME) != version
    for part in ("RULES", "FIELDS", "BATCH", "COMBINE"):
        pieces = {name: getattr(prompts, name) for name in ("RULES", "FIELDS", "BATCH", "COMBINE")}
        pieces[part] += "x"
        system = {"batch": pieces["RULES"] + pieces["BATCH"] + pieces["FIELDS"],
                  "combine": pieces["RULES"] + pieces["COMBINE"] + pieces["FIELDS"]}
        assert prompts.prompt_version(system, schema, prompts.SCHEMA_NAME) != version, part
    assert prompts.prompt_version(prompts.SYSTEM, schema, "coverage_batch_3") != version
    assert prompts.SYSTEM == {"batch": prompts.RULES + prompts.BATCH + prompts.FIELDS,
                              "combine": prompts.RULES + prompts.COMBINE + prompts.FIELDS}


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
          ("GET", "/api/knowledge-coverage/checks/{id}/rows/1"),
          ("POST", "/api/knowledge-coverage/checks/{id}/cancel"),
          ("POST", "/api/knowledge-coverage/checks/{id}/resume"),
          ("DELETE", "/api/knowledge-coverage/checks/{id}"),
          ("GET", "/api/knowledge-coverage/checks/{id}/export"),
          ("POST", "/api/knowledge-coverage/checks/{id}/suggestions"),
          ("GET", "/api/knowledge-coverage/checks/{id}/suggestions"),
          ("POST", "/api/knowledge-coverage/checks/{id}/suggestions/cancel")]


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
        assert meta["prompt_version"] == prompts.PROMPT_VERSION
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
        assert listing[0]["prompt_version"] == prompts.PROMPT_VERSION
        detail = viewer.get(f"/api/knowledge-coverage/checks/{run_id}").json()
        assert detail["counts"]["waiting"] == 2 and detail["done"] == 0
        rows = viewer.get(f"/api/knowledge-coverage/checks/{run_id}/rows?limit=100").json()
        assert [r["question"] for r in rows["rows"]] == ["first synthetic question", "=SUM(1)"]
        assert viewer.get(f"/api/knowledge-coverage/checks/{run_id}/rows?limit=101").status_code == 422
        assert viewer.get(f"/api/knowledge-coverage/checks/{run_id}/export").status_code == 200
        for method, path in ROUTES:
            if method != "GET" or path.endswith("/documents"):
                url = path.replace("{id}", run_id)
                kwargs = {"headers": csrf(viewer)} if method != "GET" else {}
                if path.endswith("/checks"):
                    kwargs["json"] = start_payload()
                assert viewer.request(method, url, **kwargs).status_code == 403, url

        cancelled = admin.post(f"/api/knowledge-coverage/checks/{run_id}/cancel", headers=csrf(admin))
        assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
        assert admin.post(f"/api/knowledge-coverage/checks/{run_id}/cancel", headers=csrf(admin)).status_code == 409
        resumed = admin.post(f"/api/knowledge-coverage/checks/{run_id}/resume", headers=csrf(admin))
        assert resumed.status_code == 200 and api.queued == [run_id, run_id]


@pytest.mark.parametrize("version", ["0123456789ab", None])
def test_resume_with_a_different_prompt_version_returns_409(api, version):
    api.db.users[1]["role"] = "admin"
    store = api.runtime.store
    meta = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                        prompt_version=VERSION, rows=[{"row": 1, "id": "", "question": "synthetic"}])
    run_id = meta["run_id"]
    store.set_state(run_id, "cancelled")
    stored = store.meta(run_id)
    if version is None:
        stored.pop("prompt_version")  # a run created before step 23
    else:
        stored["prompt_version"] = version
    store._write(store.root / run_id / "meta.json", stored)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        listing = client.get("/api/knowledge-coverage/checks").json()
        assert listing[0]["prompt_version"] == version
        response = client.post(f"/api/knowledge-coverage/checks/{run_id}/resume", headers=csrf(client))
    assert response.status_code == 409 and response.json()["detail"] == "prompt_changed"
    assert store.meta(run_id)["state"] == "cancelled" and api.queued == []


def test_plain_user_is_denied_everywhere(api):
    api.db.users[1]["role"] = "user"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        for method, path in ROUTES:
            url = path.replace("{id}", "c_" + "a" * 32)
            kwargs = {"headers": csrf(client)} if method != "GET" else {}
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
            kwargs = {"headers": csrf(client)} if method != "GET" else {}
            assert client.request(method, url, **kwargs).status_code == 404, url
        assert 'href="/knowledge-coverage"' not in client.get("/app").text


@pytest.mark.parametrize("path,menu", [("/app", ".sidebar__nav"), ("/analytics", ".sidebar__nav"),
                                       ("/knowledge-base/", ".web-header-controls--kb"),
                                       ("/knowledge-coverage", ".sidebar__nav")])
def test_knowledge_coverage_is_the_last_menu_link(api, path, menu):
    api.db.users[1]["role"] = "admin"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        page = client.get(path)
    assert page.status_code == 200, path
    links = BeautifulSoup(page.text, "html.parser").select_one(menu).select("a[href]")
    assert len(links) >= 3 and links[-1]["href"] == "/knowledge-coverage", [a["href"] for a in links]


# Delete ------------------------------------------------------------------

def finished_run(store, state="completed"):
    meta = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                        prompt_version=VERSION, rows=[{"row": 1, "id": "", "question": "synthetic"}])
    run_id = meta["run_id"]
    store.write_result(run_id, 1, plain_result())
    store.write_suggestion(run_id, 1, {"status": "error", "error_code": "empty_suggestion"})
    store.set_state(run_id, state)
    return run_id


def delete(client, run_id):
    return client.delete(f"/api/knowledge-coverage/checks/{run_id}", headers=csrf(client))


@pytest.mark.parametrize("state", ["completed", "cancelled", "interrupted"])
def test_delete_removes_a_finished_run_and_its_caches(api, state, caplog):
    api.db.users[1]["role"] = "admin"
    store = api.runtime.store
    run_id, kept = finished_run(store, state), finished_run(store)
    assert store.result_codes(run_id) and store.suggestion_statuses(run_id)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        with caplog.at_level("INFO", logger="coverage_check"):
            response = delete(client, run_id)
        assert response.status_code == 200 and response.json() == {"deleted": run_id}
        assert not (store.root / run_id).exists() and (store.root / kept).is_dir()
        assert run_id not in store._results and run_id not in store._suggestions
        for url in (f"/api/knowledge-coverage/checks/{run_id}", f"/api/knowledge-coverage/checks/{run_id}/rows",
                    f"/api/knowledge-coverage/checks/{run_id}/rows/1"):
            assert client.get(url).status_code == 404, url
        assert [c["run_id"] for c in client.get("/api/knowledge-coverage/checks").json()] == [kept]
        assert delete(client, run_id).status_code == 404
    events = [r.ragbot_event_data for r in caplog.records if hasattr(r, "ragbot_event_data")]
    assert [e for e in events if e["event"] == "coverage_check_deleted"] == [
        {"event": "coverage_check_deleted", "data": {"run_id": run_id}}]


@pytest.mark.parametrize("state", ["queued", "running"])
def test_delete_refuses_a_queued_or_running_run(api, state):
    api.db.users[1]["role"] = "admin"
    store = api.runtime.store
    run_id = finished_run(store, state)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = delete(client, run_id)
    assert response.status_code == 409 and response.json()["detail"] == "invalid_state"
    assert (store.root / run_id / "meta.json").is_file() and store.meta(run_id)["state"] == state


def test_delete_refuses_while_a_suggestion_is_queued(api):
    api.db.users[1]["role"] = "admin"
    store = api.runtime.store
    run_id = finished_run(store)
    api.runtime.suggest_jobs._queued.add((run_id, 1))
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = delete(client, run_id)
    assert response.status_code == 409 and response.json()["detail"] == "suggestions_running"
    assert (store.root / run_id / "meta.json").is_file()


def test_delete_bad_id_or_symlinked_run_is_404_and_touches_nothing_outside(api, tmp_path):
    api.db.users[1]["role"] = "admin"
    store = api.runtime.store
    finished_run(store)
    outside = tmp_path / "outside"
    target_id = finished_run(CheckStore(outside))
    target = outside / "checks" / target_id
    link_id = "c_" + "b" * 32
    os.symlink(target, store.root / link_id)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        for run_id in ("c_" + "a" * 32, "not-a-run", "c_" + "A" * 32, link_id):
            response = delete(client, run_id)
            assert response.status_code == 404 and response.json()["detail"] == "not_found", run_id
    assert (store.root / link_id).is_symlink()
    assert (target / "meta.json").is_file() and (target / "results" / "1.json").is_file()
    with pytest.raises(StoreError):
        store.delete(link_id)
    assert target.is_dir()


@pytest.mark.parametrize("role", ["user", "dashboard_viewer"])
def test_delete_needs_coverage_run_start(api, role):
    api.db.users[1]["role"] = role
    store = api.runtime.store
    run_id = finished_run(store)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        assert delete(client, run_id).status_code == 403
    assert (store.root / run_id / "meta.json").is_file()


# Export and restart ---------------------------------------------------

def make_run(tmp_path, rows):
    store = CheckStore(tmp_path / "private")
    meta = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                         prompt_version=VERSION, rows=rows)
    return store, meta["run_id"]


def test_export_columns_and_formula_prefix(api):
    api.db.users[1]["role"] = "dashboard_viewer"
    store = api.runtime.store
    meta = store.create(owner_id=2, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                        prompt_version=VERSION,
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
                        "error_code", "note", "suggested_question", "suggested_answer", "missing_facts",
                        "suggestion_unverified_numbers", "suggestion_status"]
    assert lines[1] == ["1", "'-5", "'=cmd", "answered", "2", "initial", "k7", "'=title", "2", "false", "2", "12",
                        "", "'-note", "", "", "", "", ""]
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
                         prompt_version=VERSION,
                         rows=[{"row": n, "id": "", "question": f"a{n}"} for n in (1, 2, 3)])["run_id"]
    second = store.create(owner_id=1, file_name="b.csv", documents=DOCUMENTS, settings=run_settings(),
                          prompt_version=VERSION, rows=[{"row": 1, "id": "", "question": "b1"}])["run_id"]
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


# Active row, Stop, chunk text ------------------------------------------

def wait_until(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


async def async_wait_until(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return False


def plain_result(result="not_answered", texts=None):
    return {"result": result, "error_code": None, "model_calls": 0, "duration_ms": 0, "texts": texts or {}}


def test_active_row_while_a_row_is_being_checked(api):
    api.db.users[1]["role"] = "admin"
    entered, release = threading.Event(), threading.Event()

    class GatedChecker:
        async def check(self, question):
            if question == "second synthetic question":
                entered.set()
                while not release.is_set():
                    await asyncio.sleep(0.01)
            return plain_result()

    jobs = CheckJobs(api.runtime.store, lambda meta: GatedChecker())
    api.runtime.jobs = jobs
    body = "id,query\n1,first synthetic question\n2,second synthetic question\n3,third synthetic question\n"
    payload = start_payload(csv_base64=base64.b64encode(body.encode()).decode())
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        run_id = client.post("/api/knowledge-coverage/checks", json=payload, headers=csrf(client)).json()["run_id"]
        try:
            assert entered.wait(5)
            detail = client.get(f"/api/knowledge-coverage/checks/{run_id}").json()
            assert detail["active_row"] == 2 and detail["meta"]["active_row"] == 2
            assert client.get("/api/knowledge-coverage/checks").json()[0]["active_row"] == 2
            rows = client.get(f"/api/knowledge-coverage/checks/{run_id}/rows").json()["rows"]
            assert [r["active"] for r in rows] == [False, True, False]
        finally:
            release.set()
        assert wait_until(lambda: client.get(f"/api/knowledge-coverage/checks/{run_id}").json()["meta"]["state"]
                          == "completed")
        detail = client.get(f"/api/knowledge-coverage/checks/{run_id}").json()
        assert detail["active_row"] is None and detail["meta"]["active_row"] is None
        rows = client.get(f"/api/knowledge-coverage/checks/{run_id}/rows").json()["rows"]
        assert not any(r["active"] for r in rows)
        client.portal.call(jobs.aclose)


def test_stop_cancels_the_model_call_at_once_and_resume_rechecks_the_row(tmp_path):
    rows = [{"row": n, "id": str(n), "question": f"synthetic question {n}"} for n in (1, 2, 3)]
    store, run_id = make_run(tmp_path, rows)
    limiter = AdmissionLimiter(1, name="coverage-test")
    gate = SimpleNamespace(block=True, calls=0, entered=None, cancelled_at=None)

    class GatedRag(Rag):
        async def _completion(self, **kwargs):
            gate.calls += 1
            if gate.block and gate.calls == 2:  # row 2's first model call
                gate.entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    gate.cancelled_at = time.perf_counter()
                    raise
            return await super()._completion(**kwargs)

    rag = GatedRag(judge=lambda kind, ids, call: {"verdict": "complete", "chunk_numbers": [1], "note": "synthetic"})
    service = answering(rag)

    async def scenario():
        gate.entered = asyncio.Event()
        jobs = CheckJobs(store, lambda meta: CoverageChecker(service, limiter, DOCUMENTS, meta["settings"]))
        jobs.enqueue(run_id)
        await asyncio.wait_for(gate.entered.wait(), 5)
        assert jobs.active_row(run_id) == 2 and limiter.snapshot().active == 1
        asked = time.perf_counter()
        await jobs.cancel(run_id)
        assert await async_wait_until(lambda: store.meta(run_id)["state"] == "cancelled")
        assert gate.cancelled_at is not None and gate.cancelled_at - asked < 1.0
        assert not (store.root / run_id / "results" / "2.json").exists()
        assert store.result_codes(run_id) == {1: "answered"}
        snapshot = limiter.snapshot()
        assert snapshot.active == 0 and snapshot.waiting == 0
        assert snapshot.acquired_total == snapshot.released_total
        assert jobs.active_row(run_id) is None

        gate.block = False
        store.set_state(run_id, "queued")
        jobs.enqueue(run_id)
        assert await async_wait_until(lambda: store.meta(run_id)["state"] == "completed")
        await jobs.aclose()

    asyncio.run(scenario())
    assert store.result_codes(run_id) == {1: "answered", 2: "answered", 3: "answered"}
    assert limiter.snapshot().active == 0


@pytest.mark.parametrize("stop_pending", [False, True])
def test_app_shutdown_reraises_and_leaves_the_run_to_recover(tmp_path, stop_pending):
    rows = [{"row": n, "id": str(n), "question": f"synthetic {n}"} for n in (1, 2, 3)]
    store, run_id = make_run(tmp_path, rows)

    async def scenario():
        entered = asyncio.Event()

        class Checker:
            async def check(self, question):
                if question == "synthetic 2":
                    entered.set()
                    await asyncio.Event().wait()
                return plain_result()

        jobs = CheckJobs(store, lambda meta: Checker())
        jobs.enqueue(run_id)
        await asyncio.wait_for(entered.wait(), 5)
        worker = jobs._task
        if stop_pending:
            jobs._cancel.add(run_id)  # a Stop not yet acted on does not swallow shutdown
        await jobs.aclose()
        assert worker.cancelled()
        assert store.meta(run_id)["state"] == "running"
        assert jobs.active is None
        fresh = CheckJobs(CheckStore(tmp_path / "private"), lambda meta: Checker())
        assert await fresh.recover() == 1

    asyncio.run(scenario())
    assert store.meta(run_id)["state"] == "interrupted"
    assert not (store.root / run_id / "results" / "2.json").exists()


def test_shared_chunk_text_is_stored_once(tmp_path):
    rows = [{"row": n, "id": str(n), "question": f"synthetic {n}"} for n in (1, 2)]
    store, run_id = make_run(tmp_path, rows)
    shared = "Question: synthetic shared\nAnswer: synthetic shared answer"

    class Checker:
        async def check(self, question):
            return plain_result("answered", {"k1": shared, "k-" + question: "synthetic own text " + question})

    async def scenario():
        jobs = CheckJobs(store, lambda meta: Checker())
        jobs.enqueue(run_id)
        assert await async_wait_until(lambda: store.meta(run_id)["state"] == "completed")
        await jobs.aclose()

    asyncio.run(scenario())
    folder = store.root / run_id / "chunks"
    files = sorted(folder.glob("*.json"))
    assert len(files) == 3
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in files)
    first, second = store.result(run_id, 1), store.result(run_id, 2)
    assert "texts" not in first and shared not in json.dumps(first)
    assert first["text_keys"]["k1"] == second["text_keys"]["k1"]
    assert store.chunk_text(run_id, first["text_keys"]["k1"]) == shared


def test_checker_saves_exactly_the_text_the_model_saw():
    long_text = "Question: synthetic question 0\nAnswer: " + "x" * 5000

    class LongRag(Rag):
        async def retrieve(self, query, top_k=None, **kwargs):
            items = await super().retrieve(query, top_k=top_k, **kwargs)
            items[0] = Candidate("k0", long_text)
            return items

    rag = LongRag(judge=lambda kind, ids, call: {"verdict": "complete", "chunk_numbers": [1], "note": ""})
    result, _ = check(rag)
    sent = json.loads(rag.completions[0]["kwargs"]["messages"][1]["content"])["chunks"]
    assert set(result["texts"]) == {"k0", "k1", "k2", "k3", "k4"}
    assert result["texts"]["k0"] == sent[0]["text"] == long_text[:4000]


def write_detail_run(store):
    meta = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                        prompt_version=VERSION,
                        rows=[{"row": n, "id": str(n), "question": f"synthetic {n}"} for n in (1, 2, 3, 4)])
    run_id = meta["run_id"]
    keys = store.write_texts(run_id, {"k1": "synthetic text one", "k2": "synthetic text two",
                                      "k3": "synthetic text three"})
    store.write_result(run_id, 1, {
        "result": "answered_combined", "answer_batch": None, "answer_phase": "initial",
        "answer_chunk_ids": ["k1", "k3"], "titles": {"k1": "title one", "k2": None, "k3": "title three"},
        "batches": [
            {"number": 1, "phase": "initial", "verdict": "partial", "chunk_ids": ["k1", "k2"],
             "relied_chunk_ids": ["k1"], "note": "synthetic note one"},
            {"number": 2, "phase": "initial", "verdict": "partial", "chunk_ids": ["k3"],
             "relied_chunk_ids": ["k3"], "note": "synthetic note two"}],
        "combines": [{"phase": "initial", "verdict": "complete", "chunk_ids": ["k1", "k3"],
                      "relied_chunk_ids": ["k1", "k3"], "note": "synthetic combine note"}],
        "broader_used": False, "model_calls": 3, "duration_ms": 30, "error_code": None,
        "note": "synthetic combine note", "text_keys": keys})
    # Written before this step: no text_keys.
    store.write_result(run_id, 2, {
        "result": "not_answered", "answer_batch": None, "answer_phase": None, "answer_chunk_ids": [],
        "titles": {"k1": "title one"}, "combines": [], "broader_used": False, "model_calls": 1,
        "duration_ms": 5, "error_code": None, "note": "",
        "batches": [{"number": 1, "phase": "initial", "verdict": "none", "chunk_ids": ["k1"],
                     "relied_chunk_ids": [], "note": ""}]})
    # Tampered keys never read outside chunks/.
    store.write_result(run_id, 3, {
        "result": "not_answered", "answer_batch": None, "answer_phase": None, "answer_chunk_ids": [],
        "titles": {}, "combines": [], "broader_used": False, "model_calls": 1, "duration_ms": 5,
        "error_code": None, "note": "",
        "text_keys": {"a": "../meta", "b": "../results/1", "c": keys["k1"].upper(), "d": keys["k1"] + "\n"},
        "batches": [{"number": 1, "phase": "initial", "verdict": "none", "chunk_ids": ["a", "b", "c", "d"],
                     "relied_chunk_ids": [], "note": ""}]})
    return run_id, keys


def test_row_detail_route_returns_numbered_chunks_text_and_notes(api):
    api.db.users[1]["role"] = "dashboard_viewer"
    store = api.runtime.store
    run_id, keys = write_detail_run(store)
    base = f"/api/knowledge-coverage/checks/{run_id}/rows"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = client.get(base + "/1")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        view = response.json()
        assert view["row"] == 1 and view["result"] == "answered_combined"
        first, second = view["batches"]
        assert (first["number"], first["verdict"], first["note"]) == (1, "partial", "synthetic note one")
        assert first["chunks"] == [
            {"number": 1, "chunk_id": "k1", "title": "title one", "text": "synthetic text one", "relied": True},
            {"number": 2, "chunk_id": "k2", "title": None, "text": "synthetic text two", "relied": False}]
        assert second["chunks"][0]["number"] == 1 and second["note"] == "synthetic note two"
        combine = view["combines"][0]
        assert combine["note"] == "synthetic combine note"
        assert [(c["number"], c["chunk_id"], c["text"], c["relied"]) for c in combine["chunks"]] == \
            [(1, "k1", "synthetic text one", True), (2, "k3", "synthetic text three", True)]

        old = client.get(base + "/2").json()
        assert old["batches"][0]["chunks"] == [
            {"number": 1, "chunk_id": "k1", "title": "title one", "text": None, "relied": False}]
        tampered = client.get(base + "/3").json()
        assert [c["text"] for c in tampered["batches"][0]["chunks"]] == [None, None, None, None]
        waiting = client.get(base + "/4").json()
        assert waiting["result"] is None and waiting["batches"] == [] and waiting["question"] == "synthetic 4"
        missing = client.get(base + "/5")
        assert missing.status_code == 404 and missing.json()["detail"] == "not_found"
        assert client.get(base + "/0").status_code == 404

        listing = client.get(base).json()
        assert "synthetic text" not in json.dumps(listing)
    for bad in ("../meta", "../results/1", keys["k1"].upper(), keys["k1"] + "\n", None, 7):
        assert store.chunk_text(run_id, bad) is None
    assert store.chunk_text(run_id, "0" * 64) is None


@pytest.mark.parametrize("role", ["user", "dashboard_viewer"])
def test_row_detail_route_needs_results_access(api, monkeypatch, role):
    import web_permissions
    monkeypatch.setitem(web_permissions.COVERAGE_ROLE_CAPABILITIES, "dashboard_viewer", frozenset())
    api.db.users[1]["role"] = role
    run_id, _ = write_detail_run(api.runtime.store)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = client.get(f"/api/knowledge-coverage/checks/{run_id}/rows/1")
    assert response.status_code == 403
    assert "synthetic" not in response.text


# Comparison script ----------------------------------------------------

COMPARE_QUESTIONS = ["پرسش ساختگی یک", "پرسش ساختگی دو", "پرسش ساختگی سه",
                     "پرسش ساختگی چهار", "پرسش ساختگی پنج", "پرسش ساختگی شش"]
COMPARE_NOTE = "synthetic private note"


def compare_run(store, results, version, row_count=6, durations=None):
    rows = [{"row": n, "id": str(n), "question": COMPARE_QUESTIONS[(n - 1) % 6]} for n in range(1, row_count + 1)]
    run_id = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                          prompt_version=version, rows=rows)["run_id"]
    for row, (result, error_code) in results.items():
        store.write_result(run_id, row, {
            "result": result, "error_code": error_code, "note": COMPARE_NOTE, "model_calls": row,
            "duration_ms": (durations or {}).get(row, row * 100), "batches": [],
            "titles": {"k1": "synthetic private title"}, "answer_chunk_ids": ["k1"]})
    store.set_state(run_id, "completed")
    return run_id


def run_compare(tmp_path, argv):
    from scripts import coverage_compare
    out = io.StringIO()
    code = coverage_compare.main(argv, artifact_dir=tmp_path / "private", out=out)
    text = out.getvalue()
    for secret in (*COMPARE_QUESTIONS, COMPARE_NOTE, "synthetic private title"):
        assert secret not in text
    return code, [json.loads(line) for line in text.splitlines()], text


def compare_pair(tmp_path):
    store = CheckStore(tmp_path / "private")
    before = compare_run(store, {1: ("answered", None), 2: ("partial", None), 3: ("error", "invalid_model_output"),
                                 4: ("not_answered", None), 5: ("chitchat", None), 6: ("answered", None)},
                         "aaaaaaaaaaaa")
    after = compare_run(store, {1: ("answered_combined", None), 2: ("answered", None), 3: ("not_answered", None),
                                4: ("not_answered", None), 5: ("chitchat", None)}, VERSION)
    return store, before, after


def test_compare_prints_runs_change_table_and_changed_rows(tmp_path):
    _, before, after = compare_pair(tmp_path)
    code, lines, _ = run_compare(tmp_path, ["--before", before, "--after", after])
    assert code == 0
    first, second, table, changed = lines
    assert first["kind"] == "run" and first["side"] == "before" and first["run_id"] == before
    assert first["prompt_version"] == "aaaaaaaaaaaa" and second["prompt_version"] == VERSION
    assert first["results"] == {"answered": 2, "chitchat": 1, "error": 1, "not_answered": 1, "partial": 1}
    assert first["error_codes"] == {"invalid_model_output": 1} and second["error_codes"] == {}
    assert second["results"] == {"answered": 1, "answered_combined": 1, "chitchat": 1, "not_answered": 2,
                                 "waiting": 1}
    assert (first["model_calls_total"], first["model_calls_mean"]) == (21, 3.5)
    assert (second["model_calls_total"], second["model_calls_mean"]) == (15, 3.0)
    assert (first["duration_ms_mean"], first["duration_ms_p95"]) == (350.0, 600)
    assert (second["duration_ms_mean"], second["duration_ms_p95"]) == (300.0, 500)
    assert table == {"kind": "change_table", "pairs": [
        {"before": "answered", "after": "answered_combined", "count": 1},
        {"before": "answered", "after": "waiting", "count": 1},
        {"before": "chitchat", "after": "chitchat", "count": 1},
        {"before": "error", "after": "not_answered", "count": 1},
        {"before": "not_answered", "after": "not_answered", "count": 1},
        {"before": "partial", "after": "answered", "count": 1}]}
    assert changed == {"kind": "changed_rows", "pairs": [
        {"before": "answered", "after": "answered_combined", "rows": [1]},
        {"before": "answered", "after": "waiting", "rows": [6]},
        {"before": "error", "after": "not_answered", "rows": [3]},
        {"before": "partial", "after": "answered", "rows": [2]}]}


def test_compare_with_expected_prints_agreement(tmp_path):
    _, before, after = compare_pair(tmp_path)
    expected = tmp_path / "expected.csv"
    labels = ["answered", "Answered ", "not_answered", "partial", "chitchat", "answered"]
    # A blank line after row 2 is skipped, as the upload's parse_csv does.
    body = "id,query,expected\n" + "".join(f"{n},{q},{label}\n" + (",,\n" if n == 2 else "")
                                           for n, (q, label) in enumerate(zip(COMPARE_QUESTIONS, labels), 1))
    expected.write_text("﻿" + body, encoding="utf-8")
    code, lines, _ = run_compare(tmp_path, ["--before", before, "--after", after, "--expected", str(expected)])
    assert code == 0
    agreement = [line for line in lines if line["kind"] == "agreement"]
    assert agreement == [
        {"kind": "agreement", "side": "before", "run_id": before, "agree": 3, "total": 6, "rate": 0.5,
         "wrong_rows": [2, 3, 4]},
        {"kind": "agreement", "side": "after", "run_id": after, "agree": 4, "total": 6, "rate": 0.6667,
         "wrong_rows": [4, 6]}]


def test_compare_unknown_expected_value_exits_2(tmp_path):
    _, before, after = compare_pair(tmp_path)
    expected = tmp_path / "expected.csv"
    rows = "".join(f"{q},{'answered' if n != 4 else 'maybe'}\n" for n, q in enumerate(COMPARE_QUESTIONS, 1))
    expected.write_text("query,expected\n" + rows, encoding="utf-8")
    code, lines, _ = run_compare(tmp_path, ["--before", before, "--after", after, "--expected", str(expected)])
    assert code == 2 and lines == [{"error": "unknown_expected_value", "row": 4}]
    expected.write_text("query\n" + "".join(q + "\n" for q in COMPARE_QUESTIONS), encoding="utf-8")
    code, lines, _ = run_compare(tmp_path, ["--before", before, "--after", after, "--expected", str(expected)])
    assert code == 2 and lines == [{"error": "missing_expected_column"}]


def test_compare_mismatched_row_counts_exit_2(tmp_path):
    store = CheckStore(tmp_path / "private")
    before = compare_run(store, {1: ("answered", None)}, VERSION, row_count=6)
    after = compare_run(store, {1: ("answered", None)}, VERSION, row_count=5)
    code, lines, text = run_compare(tmp_path, ["--before", before, "--after", after])
    assert code == 2 and "row_count_mismatch" in text
    assert lines == [{"error": "row_count_mismatch", "before": 6, "after": 5}]
    code, lines, _ = run_compare(tmp_path, ["--before", before, "--after", "c_" + "0" * 32])
    assert code == 2 and lines[0]["error"] == "not_found"
