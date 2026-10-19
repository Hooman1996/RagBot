"""Draft FAQ suggestions for unanswered rows, with fake model replies. Synthetic data only."""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import stat
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from coverage_check import prompts, suggest_prompts
from coverage_check.jobs import CheckJobs
from coverage_check.settings import CoverageSettings, RunSettings, SettingsError, load_settings
from coverage_check.store import CheckStore
from coverage_check.suggest_jobs import SuggestJobs
from coverage_check.suggester import Suggester, context_chunk_ids
from tests.test_coverage_check import (  # noqa: F401  (fixtures)
    DOCUMENTS, VERSION, api, async_wait_until, plain_result, run_settings, wait_until)
from tests.test_web_auth import csrf, login, setup  # noqa: F401  (fixture)
from utils.concurrency import AdmissionLimiter

SETTINGS = CoverageSettings(artifact_dir=None, upload_max_bytes=5242880, max_rows=100, run=RunSettings(),
                            combine_max=10, chunk_max_chars=4000, model_max_tokens=300)
GOOD = {"chunk_numbers": [1], "missing": ["daily limit"], "faq_question": "پرسش ساختگی؟",
        "faq_answer": "پاسخ ساختگی. [تکمیل شود: سقف روزانه]"}
PLACEHOLDER = "[تکمیل شود: سقف ۳ مورد]"


class SuggestRag:
    """``reply(call)`` scripts the model; a ("length", reply) tuple is a reply cut at max_tokens."""

    model_id = "synthetic-model"

    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply or (lambda call: GOOD)

    async def _completion(self, **kwargs):
        payload = json.loads(kwargs["messages"][1]["content"])
        call = {"kwargs": kwargs, "payload": payload}
        self.calls.append(call)
        reply = self.reply(call)
        finish_reason, reply = reply if isinstance(reply, tuple) else ("stop", reply)
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish_reason,
                                                        message=SimpleNamespace(content=content))])


def new_store(tmp_path, rows=1):
    store = CheckStore(tmp_path / "private")
    meta = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                        prompt_version=VERSION,
                        rows=[{"row": n, "id": str(n), "question": f" synthetic question {n} "}
                              for n in range(1, rows + 1)])
    return store, meta["run_id"]


def partial_result(store, run_id, skip_text=()):
    """Batch 1 partial (relies on c), batch 2 none, batch 3 partial (relies on g), a partial combine of c, g."""
    ids = ["a", "b", "c", "d", "e", "f", "g"]
    keys = store.write_texts(run_id, {cid: f"synthetic text {cid}" for cid in ids if cid not in skip_text})
    return {
        "result": "partial", "answer_chunk_ids": [], "titles": {cid: f"title {cid}" for cid in ids},
        "batches": [
            {"number": 1, "phase": "initial", "verdict": "partial", "chunk_ids": ["a", "b", "c"],
             "relied_chunk_ids": ["c"], "note": ""},
            {"number": 2, "phase": "initial", "verdict": "none", "chunk_ids": ["d", "e"],
             "relied_chunk_ids": [], "note": ""},
            {"number": 3, "phase": "initial", "verdict": "partial", "chunk_ids": ["f", "g"],
             "relied_chunk_ids": ["g"], "note": ""}],
        "combines": [{"phase": "initial", "verdict": "partial", "chunk_ids": ["c", "g"],
                      "relied_chunk_ids": ["g"], "note": ""}],
        "error_code": None, "model_calls": 4, "duration_ms": 1, "text_keys": keys}


def suggest(store, run_id, result, rag=None, limiter=None, **overrides):
    rag = rag or SuggestRag()
    settings = CoverageSettings(**{**SETTINGS.__dict__, **overrides})
    suggester = Suggester(rag, limiter or asyncio.Semaphore(1), store, settings)
    return asyncio.run(suggester.suggest(run_id, 1, " synthetic question 1 ", result)), rag


# Settings ---------------------------------------------------------------

def test_settings_defaults_and_ranges():
    settings = load_settings({})
    assert (settings.suggest_context, settings.suggest_max_tokens) == (5, 700)
    assert "suggest_context" not in settings.run_values(settings.run)
    for key, value in (("KNOWLEDGE_COVERAGE_SUGGEST_CONTEXT", "0"), ("KNOWLEDGE_COVERAGE_SUGGEST_CONTEXT", "21"),
                       ("KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS", "127"),
                       ("KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS", "2049"),
                       ("KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS", "x")):
        with pytest.raises(SettingsError) as raised:
            load_settings({key: value})
        assert str(raised.value) == key
    edge = load_settings({"KNOWLEDGE_COVERAGE_SUGGEST_CONTEXT": "20", "KNOWLEDGE_COVERAGE_SUGGEST_MAX_TOKENS": "128"})
    assert (edge.suggest_context, edge.suggest_max_tokens) == (20, 128)


# Versions ---------------------------------------------------------------

def test_check_prompts_are_unchanged_and_suggestion_version_is_recorded():
    assert prompts.PROMPT_VERSION == "0974b3653393"
    schema = suggest_prompts.Suggestion.model_json_schema()
    raw = json.dumps({"system": suggest_prompts.SYSTEM, "schema": schema, "name": "coverage_suggestion_1"},
                     sort_keys=True, ensure_ascii=False)
    assert suggest_prompts.SUGGEST_PROMPT_VERSION == hashlib.sha256(raw.encode()).hexdigest()[:12]
    assert list(schema["properties"]) == ["chunk_numbers", "missing", "faq_question", "faq_answer"]
    assert schema["additionalProperties"] is False
    assert not any("maxLength" in field or "maxItems" in field for field in schema["properties"].values())
    assert suggest_prompts.SYSTEM.startswith("You draft a new FAQ entry for a bank's knowledge base.")
    first_line = open(suggest_prompts.__file__, encoding="utf-8").readline()
    assert first_line.startswith("# Edit the suggestion prompt here. Restart the app after a change.")


# Chunk choice -----------------------------------------------------------

def test_relied_chunks_come_first_then_batch_order(tmp_path):
    store, run_id = new_store(tmp_path)
    result = partial_result(store, run_id)
    assert context_chunk_ids(result) == ["c", "g", "a", "b", "d", "e", "f"]
    data, rag = suggest(store, run_id, result, suggest_context=4)
    payload = rag.calls[0]["payload"]
    assert payload["question"] == "synthetic question 1"
    assert payload["chunks"] == [{"number": n, "text": f"synthetic text {cid}"}
                                 for n, cid in enumerate(["c", "g", "a", "b"], 1)]
    assert data["chunks"] == [{"number": n, "chunk_id": cid, "title": f"title {cid}"}
                              for n, cid in enumerate(["c", "g", "a", "b"], 1)]
    assert data["status"] == "done" and data["used_chunk_ids"] == ["c"]
    kwargs = rag.calls[0]["kwargs"]
    assert (kwargs["model"], kwargs["max_tokens"], kwargs["temperature"], kwargs["top_p"], kwargs["seed"]) == \
        ("synthetic-model", 700, 0, 1, 42)
    schema = kwargs["response_format"]["json_schema"]
    assert schema["name"] == "coverage_suggestion_1" and schema["strict"] is True
    assert kwargs["messages"][0] == {"role": "system", "content": suggest_prompts.SYSTEM}
    assert data["suggest_prompt_version"] == suggest_prompts.SUGGEST_PROMPT_VERSION
    assert data["model_calls"] == 1 and data["created_at"] and isinstance(data["duration_ms"], int)


def test_chunks_without_text_are_skipped_and_none_left_is_no_saved_chunks(tmp_path):
    store, run_id = new_store(tmp_path)
    data, rag = suggest(store, run_id, partial_result(store, run_id, skip_text={"g", "a"}), suggest_context=3)
    assert [c["chunk_id"] for c in data["chunks"]] == ["c", "b", "d"]

    old = partial_result(store, run_id)
    old.pop("text_keys")  # checked before step 22
    data, rag = suggest(store, run_id, old)
    assert data["status"] == "error" and data["error_code"] == "no_saved_chunks"
    assert rag.calls == [] and data["model_calls"] == 0


@pytest.mark.parametrize("result", [None, {"result": "answered"}, {"result": "answered_combined"},
                                    {"result": "chitchat"}, {"result": "error"}])
def test_suggester_refuses_rows_that_are_not_eligible(tmp_path, result):
    store, run_id = new_store(tmp_path)
    data, rag = suggest(store, run_id, result)
    assert (data["status"], data["error_code"], rag.calls) == ("error", "not_eligible", [])


# Parsing ----------------------------------------------------------------

def test_parse_cuts_lengths_after_validation():
    reply = {"chunk_numbers": [2, 1], "missing": ["  " + "m" * 200, "", *[f"fact {n}" for n in range(14)]],
             "faq_question": " " + "q" * 400 + " ", "faq_answer": "a" * 2000}
    suggestion, code = suggest_prompts.parse_suggestion(json.dumps(reply), 3)
    assert code is None and suggestion.chunk_numbers == [2, 1]
    assert suggestion.faq_question == "q" * 300 and suggestion.faq_answer == "a" * 1500
    assert len(suggestion.missing) == 10 and suggestion.missing[0] == "m" * 120
    assert suggestion.missing[1:] == [f"fact {n}" for n in range(9)]


@pytest.mark.parametrize("reply,code", [
    ({**GOOD, "chunk_numbers": [1, 1]}, "invalid_chunk_numbers"),
    ({**GOOD, "chunk_numbers": [0]}, "invalid_chunk_numbers"),
    ({**GOOD, "chunk_numbers": [4]}, "invalid_chunk_numbers"),
    ({**GOOD, "faq_question": "   "}, "empty_suggestion"),
    ({**GOOD, "faq_answer": "\n"}, "empty_suggestion"),
    ({**GOOD, "extra": 1}, "invalid_model_output"),
    ({k: v for k, v in GOOD.items() if k != "missing"}, "invalid_model_output"),
    ("not json", "invalid_model_output"),
    (None, "invalid_model_output"),
])
def test_parse_errors(reply, code):
    content = reply if reply is None or isinstance(reply, str) else json.dumps(reply)
    assert suggest_prompts.parse_suggestion(content, 3) == (None, code)
    assert suggest_prompts.parse_suggestion(json.dumps({**GOOD, "chunk_numbers": []}), 3)[1] is None


def test_cut_reply_twice_gives_model_output_cut(tmp_path):
    store, run_id = new_store(tmp_path)
    data, rag = suggest(store, run_id, partial_result(store, run_id), rag=SuggestRag(lambda call: ("length", GOOD)))
    assert (data["status"], data["error_code"], data["model_calls"], len(rag.calls)) == \
        ("error", "model_output_cut", 2, 2)
    assert data["faq_question"] is None and data["faq_answer"] is None


def test_invalid_then_valid_reply_and_failed_calls(tmp_path):
    store, run_id = new_store(tmp_path)
    replies = iter([{**GOOD, "chunk_numbers": [9]}, GOOD])
    data, _ = suggest(store, run_id, partial_result(store, run_id), rag=SuggestRag(lambda call: next(replies)))
    assert data["status"] == "done" and data["model_calls"] == 2

    class Failing(SuggestRag):
        async def _completion(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("synthetic secret text")
    data, rag = suggest(store, run_id, partial_result(store, run_id), rag=Failing())
    assert (data["error_code"], data["model_calls"], len(rag.calls)) == ("model_failed", 2, 2)
    assert "synthetic secret text" not in json.dumps(data)


# Numbers ----------------------------------------------------------------

def test_unverified_numbers():
    answer = "کارمزد ۵۰۰۰ ریال است " + PLACEHOLDER
    assert suggest_prompts.unverified_numbers(answer, ["synthetic fee is 5000 rials"]) == []
    assert suggest_prompts.unverified_numbers(answer, ["synthetic text without the fee"]) == ["5000"]
    assert suggest_prompts.unverified_numbers("مبلغ ٧٥ و ۵۰۰۰ و 12 و ۷۵", ["کارمزد ۵٠٠٠"]) == ["12", "75"]
    assert suggest_prompts.unverified_numbers("500", ["5000"]) == ["500"]


def test_unverified_numbers_are_stored_with_the_suggestion(tmp_path):
    store, run_id = new_store(tmp_path)
    reply = {**GOOD, "faq_answer": "سقف ۲۰ میلیون است و کارمزد 7 درصد " + PLACEHOLDER}
    data, _ = suggest(store, run_id, partial_result(store, run_id), rag=SuggestRag(lambda call: reply))
    assert data["status"] == "done" and data["unverified_numbers"] == ["20", "7"]


# Store ------------------------------------------------------------------

def test_suggestion_files_are_private_and_replaced(tmp_path):
    store, run_id = new_store(tmp_path, rows=3)
    assert store.suggestion_statuses(run_id) == {} and store.suggestion(run_id, 1) is None
    assert not (store.root / run_id / "suggestions").exists()
    store.write_suggestion(run_id, 1, {"status": "error", "error_code": "model_failed"})
    store.write_suggestion(run_id, 2, {"status": "done"})
    store.write_suggestion(run_id, 1, {"status": "done", "faq_question": "synthetic"})
    folder = store.root / run_id / "suggestions"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in folder.glob("*.json"))
    assert store.suggestion(run_id, 1)["faq_question"] == "synthetic"
    assert store.suggested_rows(run_id) == {1, 2}
    fresh = CheckStore(tmp_path / "private")
    assert fresh.suggestion_statuses(run_id) == {1: "done", 2: "done"}


# Queue ------------------------------------------------------------------

def test_cancel_stops_the_model_call_at_once_and_writes_nothing(tmp_path):
    store, run_id = new_store(tmp_path, rows=3)
    for row in (1, 2, 3):
        store.write_result(run_id, row, partial_result(store, run_id))
    limiter = AdmissionLimiter(1, name="coverage-suggest-test")
    gate = SimpleNamespace(entered=None, cancelled_at=None)

    class GatedRag(SuggestRag):
        async def _completion(self, **kwargs):
            gate.entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                gate.cancelled_at = time.perf_counter()
                raise

    async def scenario():
        gate.entered = asyncio.Event()
        jobs = SuggestJobs(store, lambda: Suggester(GatedRag(), limiter, store, SETTINGS))
        assert jobs.enqueue(run_id, [1, 2, 3]) == 3
        await asyncio.wait_for(gate.entered.wait(), 5)
        assert jobs.active_row(run_id) == 1 and jobs.queued_rows(run_id) == {2, 3}
        assert limiter.snapshot().active == 1
        asked = time.perf_counter()
        assert await jobs.cancel(run_id) == 3
        assert await async_wait_until(lambda: jobs.active is None)
        assert gate.cancelled_at is not None and gate.cancelled_at - asked < 1.0
        assert jobs.queued_rows(run_id) == set() and jobs.status(run_id, 1) is None
        snapshot = limiter.snapshot()
        assert snapshot.active == 0 and snapshot.waiting == 0
        assert snapshot.acquired_total == snapshot.released_total
        await jobs.aclose()

    asyncio.run(scenario())
    assert not (store.root / run_id / "suggestions").exists()
    assert store.suggestion_statuses(run_id) == {}


def test_duplicates_are_skipped_and_shutdown_is_reraised(tmp_path):
    store, run_id = new_store(tmp_path, rows=2)

    async def scenario():
        entered = asyncio.Event()

        class Blocking:
            async def suggest(self, run_id, row, question, result):
                entered.set()
                await asyncio.Event().wait()

        jobs = SuggestJobs(store, Blocking)
        assert jobs.enqueue(run_id, [1, 2, 2]) == 2
        await asyncio.wait_for(entered.wait(), 5)
        assert jobs.enqueue(run_id, [1, 2]) == 0
        assert (jobs.status(run_id, 1), jobs.status(run_id, 2)) == ("active", "queued")
        worker = jobs._task
        jobs._stopping.add(run_id)  # a Stop not yet acted on does not swallow shutdown
        await jobs.aclose()
        assert worker.cancelled()

    asyncio.run(scenario())
    assert store.suggestion_statuses(run_id) == {}


def test_suggestion_runs_while_a_check_is_running(tmp_path):
    store, run_id = new_store(tmp_path, rows=3)
    events = []

    async def scenario():
        check_gate, suggest_gate, suggest_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
        row_two = asyncio.Event()

        class GatedChecker:
            async def check(self, question):
                if question.strip() == "synthetic question 2":
                    row_two.set()
                    await check_gate.wait()
                    events.append("check row 2")
                return plain_result()

        class GatedRag(SuggestRag):
            async def _completion(self, **kwargs):
                suggest_entered.set()
                await suggest_gate.wait()
                return await super()._completion(**kwargs)

        checks = CheckJobs(store, lambda meta: GatedChecker())
        suggestions = SuggestJobs(store, lambda: Suggester(GatedRag(), asyncio.Semaphore(2), store, SETTINGS))
        checks.enqueue(run_id)
        await asyncio.wait_for(row_two.wait(), 5)
        store.write_result(run_id, 1, {**store.result(run_id, 1), **partial_result(store, run_id)})
        assert suggestions.enqueue(run_id, [1]) == 1
        await asyncio.wait_for(suggest_entered.wait(), 5)
        assert checks.active_row(run_id) == 2 and suggestions.active_row(run_id) == 1
        suggest_gate.set()
        assert await async_wait_until(lambda: store.suggestion(run_id, 1) is not None)
        events.append("suggestion row 1")
        assert store.result(run_id, 2) is None and checks.active_row(run_id) == 2
        check_gate.set()
        assert await async_wait_until(lambda: store.meta(run_id)["state"] == "completed")
        await suggestions.aclose()
        await checks.aclose()

    asyncio.run(scenario())
    assert events == ["suggestion row 1", "check row 2"]
    assert store.suggestion(run_id, 1)["status"] == "done"


# API --------------------------------------------------------------------

def api_run(api):
    """Rows 1-2 not answered, 3 partial, 4 answered, 5 chit-chat, 6 error, 7 waiting; row 1 has a done
    suggestion, row 3 an error suggestion."""
    store = api.runtime.store
    meta = store.create(owner_id=1, file_name="q.csv", documents=DOCUMENTS, settings=run_settings(),
                        prompt_version=VERSION,
                        rows=[{"row": n, "id": str(n), "question": f"synthetic question {n}"} for n in range(1, 8)])
    run_id = meta["run_id"]
    for row, code in ((1, "not_answered"), (2, "not_answered"), (3, "partial"), (4, "answered"),
                      (5, "chitchat"), (6, "error")):
        store.write_result(run_id, row, {**partial_result(store, run_id), "result": code})
    store.write_suggestion(run_id, 1, {"status": "done", "error_code": None, "faq_question": "=draft question",
                                       "faq_answer": "-draft answer", "missing": ["=fee", "limit"],
                                       "unverified_numbers": ["12", "5"], "chunks": [], "used_chunk_ids": []})
    store.write_suggestion(run_id, 3, {"status": "error", "error_code": "model_failed"})
    return run_id


class Gate:
    """A suggester that blocks every row until released, so the queue stays filled."""

    def __init__(self):
        self.release = threading.Event()
        self.rows = []

    def __call__(self):
        return self

    async def suggest(self, run_id, row, question, result):
        self.rows.append(row)
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        return {"status": "done", "error_code": None, "faq_question": "synthetic", "faq_answer": "synthetic",
                "missing": [], "unverified_numbers": [], "chunks": [], "used_chunk_ids": [],
                "model_calls": 1, "duration_ms": 1}


def test_all_queues_only_eligible_rows_without_a_done_suggestion(api):
    api.db.users[1]["role"] = "admin"
    run_id = api_run(api)
    gate = Gate()
    api.runtime.suggest_jobs = SuggestJobs(api.runtime.store, gate)
    base = f"/api/knowledge-coverage/checks/{run_id}/suggestions"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        try:
            summary = client.get(base)
            assert summary.headers["cache-control"] == "no-store"
            assert summary.json() == {"queued": 0, "active_row": None, "done": 1, "errors": 1, "eligible": 2}
            assert client.post(base, json={"all": True}, headers=csrf(client)).json() == {"queued": 2}
            assert wait_until(lambda: gate.rows == [2])
            assert client.post(base, json={"all": True}, headers=csrf(client)).json() == {"queued": 0}
            assert client.post(base, json={"rows": [2, 3]}, headers=csrf(client)).json() == {"queued": 0}
            assert client.get(base).json() == {"queued": 1, "active_row": 2, "done": 1, "errors": 1, "eligible": 2}
            rows = client.get(f"/api/knowledge-coverage/checks/{run_id}/rows").json()["rows"]
            assert [r["suggestion_status"] for r in rows] == ["done", "active", "queued", None, None, None, None]
            assert "draft question" not in json.dumps(rows)
            assert client.get(f"/api/knowledge-coverage/checks/{run_id}/rows/3").json()["suggestion_status"] == \
                "queued"
            # A row that already has a done suggestion is suggested again when listed.
            assert client.post(base, json={"rows": [1]}, headers=csrf(client)).json() == {"queued": 1}
        finally:
            gate.release.set()
        assert wait_until(lambda: client.get(base).json()["queued"] == 0
                          and client.get(base).json()["active_row"] is None)
        assert gate.rows == [2, 3, 1]
        assert client.get(base).json() == {"queued": 0, "active_row": None, "done": 3, "errors": 0, "eligible": 0}
        filtered = client.get(f"/api/knowledge-coverage/checks/{run_id}/rows?suggested=1").json()
        assert filtered["total"] == 3 and [r["row"] for r in filtered["rows"]] == [1, 2, 3]
        detail = client.get(f"/api/knowledge-coverage/checks/{run_id}/rows/2").json()
        assert detail["suggestion"]["status"] == "done" and detail["suggestion_status"] == "done"
        assert client.get(f"/api/knowledge-coverage/checks/{run_id}/rows/4").json()["suggestion"] is None
        client.portal.call(api.runtime.suggest_jobs.aclose)


@pytest.mark.parametrize("rows", [[4], [5], [6], [7], [8], [2, 4]])
def test_rows_that_are_not_eligible_return_409_and_queue_nothing(api, rows):
    api.db.users[1]["role"] = "admin"
    run_id = api_run(api)
    queued = []
    api.runtime.suggest_jobs.enqueue = lambda run, items: queued.append((run, items)) or 0
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = client.post(f"/api/knowledge-coverage/checks/{run_id}/suggestions", json={"rows": rows},
                               headers=csrf(client))
    assert response.status_code == 409 and response.json()["detail"] == "not_eligible"
    assert queued == []


@pytest.mark.parametrize("body", [{}, {"rows": [2], "all": True}, {"all": False}, {"rows": []},
                                  {"rows": ["2"]}, {"rows": [2], "x": 1}, {"rows": list(range(1, 1002))}])
def test_suggest_body_must_be_rows_or_all(api, body):
    api.db.users[1]["role"] = "admin"
    run_id = api_run(api)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = client.post(f"/api/knowledge-coverage/checks/{run_id}/suggestions", json=body,
                               headers=csrf(client))
    assert response.status_code == 422 and response.json()["detail"] == "invalid_request"


def test_cancel_route_stops_the_runs_suggestions(api):
    api.db.users[1]["role"] = "admin"
    run_id = api_run(api)
    gate = Gate()
    api.runtime.suggest_jobs = SuggestJobs(api.runtime.store, gate)
    base = f"/api/knowledge-coverage/checks/{run_id}/suggestions"
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        assert client.post(base, json={"rows": [1, 2, 3]}, headers=csrf(client)).json() == {"queued": 3}
        assert wait_until(lambda: gate.rows == [1])
        assert client.post(base + "/cancel", headers=csrf(client)).json() == {"cancelled": 3}
        assert wait_until(lambda: client.get(base).json()["active_row"] is None)
        assert client.get(base).json()["queued"] == 0
        assert client.post(base + "/cancel", headers=csrf(client)).json() == {"cancelled": 0}
        assert api.runtime.store.suggestion(run_id, 1)["faq_question"] == "=draft question"
        assert client.post(f"/api/knowledge-coverage/checks/c_{'0' * 32}/suggestions/cancel",
                           headers=csrf(client)).status_code == 404
        client.portal.call(api.runtime.suggest_jobs.aclose)


def test_export_has_the_five_suggestion_columns_made_formula_safe(api):
    api.db.users[1]["role"] = "dashboard_viewer"
    run_id = api_run(api)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        login(client, "alice")
        response = client.get(f"/api/knowledge-coverage/checks/{run_id}/export")
    lines = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert lines[0][-5:] == ["suggested_question", "suggested_answer", "missing_facts",
                             "suggestion_unverified_numbers", "suggestion_status"]
    assert lines[1][-5:] == ["'=draft question", "'-draft answer", "'=fee | limit", "12 5", "done"]
    assert lines[2][-5:] == ["", "", "", "", ""]
    assert lines[3][-5:] == ["", "", "", "", "error"]


def test_plain_user_and_viewer_permissions_on_the_three_routes(api, monkeypatch):
    run_id = api_run(api)
    base = f"/api/knowledge-coverage/checks/{run_id}/suggestions"
    api.db.users[1]["role"] = "user"
    api.db.users[2]["role"] = "dashboard_viewer"
    with TestClient(main.app, raise_server_exceptions=False) as user, \
            TestClient(main.app, raise_server_exceptions=False) as viewer:
        login(user, "alice")
        assert user.get(base).status_code == 403
        assert user.post(base, json={"all": True}, headers=csrf(user)).status_code == 403
        assert user.post(base + "/cancel", headers=csrf(user)).status_code == 403
        login(viewer, "bob")
        assert viewer.get(base).status_code == 200
        assert viewer.post(base, json={"all": True}, headers=csrf(viewer)).status_code == 403
        assert viewer.post(base + "/cancel", headers=csrf(viewer)).status_code == 403
    assert api.runtime.suggest_jobs.queued_rows(run_id) == set()
