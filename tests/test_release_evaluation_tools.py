"""Offline checks of the staging-only release evaluation tools (step 13)."""
from __future__ import annotations

import asyncio
import csv
import importlib.util
import json
import os
from pathlib import Path
import sys
import textwrap
import time
from types import SimpleNamespace
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from document_category import get_document_category  # noqa: E402
from scripts import _staging_guard as guard  # noqa: E402
from scripts import answer_quality_eval as aqe  # noqa: E402
from scripts import retrieval_eval as rev  # noqa: E402

_spec = importlib.util.spec_from_file_location("_retrieval_child", ROOT / "scripts" / "_retrieval_child.py")
child = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(child)

LOOPBACK_ENV = {"ENVIRONMENT": "staging", "QDRANT_HOST": "localhost", "POSTGRES_HOST": "127.0.0.1",
                "TEI_EMBED_URL": "http://127.0.0.1:7997", "TEI_RERANK_URL": "http://127.0.0.1:7998",
                "VLLM_URL": "http://localhost:8000/v1"}
THRESHOLDS = {"min_hit_diff": -0.02, "min_recall_diff": -0.02, "max_p95_ms": 45_000.0, "max_p95_ratio": 1.2}


def private(base: Path, name: str) -> Path:
    path = base / name
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def staging_env(monkeypatch, tmp_path, values=LOOPBACK_ENV, name="envdir"):
    env_file = private(tmp_path, name) / ".env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    monkeypatch.setattr(guard, "ENV_FILE", env_file)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def run_record(label, contexts, latency=100.0):
    return {"label": label, "per_question": {
        q: {"retrieved_ids": ids, "context_ids": ids, "latency_ms": latency, "error": None}
        for q, ids in contexts.items()}}


# 1. Metrics

def test_question_metrics_are_exact():
    assert rev.question_metrics({"b", "d"}, ["a", "b", "c", "d"], ["c", "b", "a"]) == {
        "hit_context": 1.0, "recall_context": 0.5, "mrr_context": 0.5, "recall_retrieved": 1.0, "empty": 0.0}
    assert rev.question_metrics({"z"}, ["a", "b"], ["a"]) == {
        "hit_context": 0.0, "recall_context": 0.0, "mrr_context": 0.0, "recall_retrieved": 0.0, "empty": 0.0}
    assert rev.question_metrics({"a", "b"}, [], []) == {
        "hit_context": 0.0, "recall_context": 0.0, "mrr_context": 0.0, "recall_retrieved": 0.0, "empty": 1.0}


# 2. Selection mirror

class FakeRag:
    def __init__(self, ids):
        self.calls, self.ids = [], ids
        self.search_engine = self

    async def retrieve(self, query, top_k, allowed_docs):
        self.calls.append(("retrieve", query, top_k, tuple(allowed_docs)))
        if query == "boom":
            raise ValueError("private text that must not be recorded")
        return [SimpleNamespace(doc_id=i, content=f"question: title {i} answer: x") for i in self.ids]

    async def rerank_search_results(self, query, results, top_k):
        self.calls.append(("rerank", query, top_k))
        return list(reversed(results))


def test_selection_mirrors_production():
    settings = SimpleNamespace(rag_retrieval_top_k=7, rag_context_rerank_enabled=True, rag_context_rerank_top_k=5)
    select = lambda rag, docs, s: asyncio.run(child.select_context(
        rag, "q", docs, settings=s, category_of=get_document_category))
    rag = FakeRag([1, 2, 3, 4, 5])
    retrieved, reranked, context = select(rag, ["FAQ bank"], settings)
    assert rag.calls == [("retrieve", "q", 7, ("FAQ bank",)), ("rerank", "q", 5)]
    assert [r.doc_id for r in reranked] == [5, 4, 3, 2, 1] and context == reranked
    rag = FakeRag([1, 2, 3, 4, 5])
    _, reranked, context = select(rag, ["قرارداد نمونه"], settings)
    assert [r.doc_id for r in context] == [5, 4, 3]
    off = SimpleNamespace(**{**vars(settings), "rag_context_rerank_enabled": False})
    rag = FakeRag([1, 2, 3, 4, 5])
    retrieved, reranked, context = select(rag, ["قرارداد نمونه"], off)
    assert [c[0] for c in rag.calls] == ["retrieve"] and reranked is None
    assert [r.doc_id for r in context] == [1, 2, 3]
    rows, titles, errors = asyncio.run(child.evaluate(
        FakeRag([1, 2]), [{"question_id": "q1", "retrieval_query": "boom"},
                          {"question_id": "q2", "retrieval_query": "fine"}],
        ["FAQ bank"], settings=settings, category_of=get_document_category))
    assert errors == 1 and rows[0] == {"question_id": "q1", "error": "ValueError"}
    assert rows[1]["context_ids"] == ["2", "1"] and titles == {"1": "title 1", "2": "title 2"}


# 3. Compare

def test_bootstrap_identical_runs_and_verdicts():
    diffs = {"hit_context": [1.0, 0.0, -1.0, 0.0, 1.0], "recall_context": [0.5, 0.0, 0.0, -0.5, 1.0],
             "mrr_context": [0.0] * 5}
    assert rev.paired_bootstrap(diffs) == rev.paired_bootstrap(diffs)
    contexts = {f"q{i}": [f"c{i}", "x"] for i in range(20)}
    labels = {q: {ids[0]} for q, ids in contexts.items()}
    cases = {"cases": [{"question_id": q} for q in contexts] + [{"question_id": "unlabeled"}]}
    same = rev.evaluate_runs(cases, labels, [run_record("base", contexts), run_record("rc", contexts)])
    assert same["no_relevant"] == 1 and len(same["labeled"]) == 20
    result = rev.compare_runs(same, ["base", "rc"], "base", THRESHOLDS)
    for stats in result["comparisons"][0]["metrics"].values():
        assert stats["mean"] == 0 and stats["low"] <= 0 <= stats["high"]
    assert result["verdicts"]["rc"]["pass"]
    worse = {q: (["x"] if i % 2 else ids) for i, (q, ids) in enumerate(contexts.items())}
    failed = rev.compare_runs(rev.evaluate_runs(cases, labels, [run_record("base", contexts), run_record("rc", worse)]),
                              ["base", "rc"], "base", THRESHOLDS)["verdicts"]["rc"]
    assert not failed["pass"] and not failed["checks"]["hit_context_lower"]
    slow = rev.compare_runs(rev.evaluate_runs(cases, labels, [run_record("base", contexts),
                                                              run_record("rc", contexts, latency=130.0)]),
                            ["base", "rc"], "base", THRESHOLDS)["verdicts"]["rc"]
    assert slow["checks"] == {"hit_context_lower": True, "recall_context_lower": True,
                              "p95_absolute": True, "p95_ratio": False}
    assert rev.comparison_pairs(["base", "p1", "p2"], "base") == [("p1", "base"), ("p2", "base"), ("p2", "p1")]


# 4. Blind and score

def test_blind_score_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(rev, "REPORT_ROOT", tmp_path)
    cases_dir = private(tmp_path, "cases")
    (cases_dir / "cases.json").write_text(json.dumps({"cases": [
        {"question_id": f"q{i}", "question": f"question {i}"} for i in range(8)]}), encoding="utf-8")
    digest = rev.cases_sha256(cases_dir)
    for label in ("cfgalpha", "cfgbeta"):
        d = private(tmp_path, label)
        (d / "collect.json").write_text(json.dumps({"label": label, "cases_sha256": digest,
                                                    "cases_file": str(cases_dir / "cases.json")}))
        (d / "answers.json").write_text(json.dumps([{"question_id": f"q{i}", "answer": f"reply {i} {label[-1]}",
                                                     "status": 200, "latency_ms": 1.0} for i in range(8)]))
    out = private(tmp_path, "blind")
    assert aqe.blind(tmp_path / "cfgalpha", tmp_path / "cfgbeta", 7, out) == 0
    sheet_text = (out / "grading-sheet.csv").read_text(encoding="utf-8-sig")
    assert "cfgalpha" not in sheet_text and "cfgbeta" not in sheet_text and "reply 0 a" in sheet_text
    key = json.loads((out / "grading-key.json").read_text())
    assert {i["answer_1"] for i in key["items"].values()} == {"a", "b"}
    rows = list(csv.DictReader((out / "grading-sheet.csv").open(encoding="utf-8-sig")))
    for n, row in enumerate(rows):
        item = key["items"][row["item_id"]]
        for slot in "12":
            baseline = item[f"answer_{slot}"] == "a"
            row[f"correct_{slot}"] = "correct" if baseline else ("incorrect" if n < 3 else "partly")
            row[f"grounded_{slot}"] = "yes" if baseline or n % 2 else "no"
        row["preference"] = "1" if item["answer_1"] == "a" else "2"
    result = aqe.tally(rows, key)
    assert result["stats"]["a"]["correct"] == {"correct": 8}
    assert result["stats"]["b"]["correct"] == {"incorrect": 3, "partly": 5} and result["stats"]["b"]["grounded"] == 4
    assert result["preference"] == {"a": 8} and result["p_value"] == pytest.approx(2 / 256)
    verdict = aqe.score_verdict(result, alpha=0.05, max_extra_incorrect=2)
    assert verdict["sign_test_favors_baseline"] and verdict["extra_incorrect"] == 3 and not verdict["pass"]
    assert aqe.sign_test(3, 3) == 1.0 and aqe.sign_test(0, 6) == pytest.approx(2 / 64)
    graded = private(tmp_path, "graded") / "sheet.csv"
    with graded.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=aqe.SHEET_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    assert aqe.score(graded, out / "grading-key.json", tmp_path / "score.md") == 1
    report = (tmp_path / "score.md").read_text(encoding="utf-8")
    assert "| `cfgbeta` | 0 | 5 | 3 |" in report and "question 1" not in report and "reply" not in report


# 5. Guards and leaks

def test_guards_refuse(tmp_path, monkeypatch, capsys):
    staging_env(monkeypatch, tmp_path)
    guard.require_staging(guard.RETRIEVAL_KEYS)
    monkeypatch.delenv("ENVIRONMENT")
    with pytest.raises(SystemExit) as exc:
        guard.require_staging(guard.RETRIEVAL_KEYS)
    assert exc.value.code == 3
    staging_env(monkeypatch, tmp_path, {**LOOPBACK_ENV, "TEI_EMBED_URL": "http://10.20.30.40:7997"}, "remote")
    with pytest.raises(SystemExit) as exc:
        guard.require_staging(guard.RETRIEVAL_KEYS)
    assert exc.value.code == 3
    monkeypatch.setenv("TEI_EMBED_URL", "http://127.0.0.1:7997")
    with pytest.raises(SystemExit) as exc:
        guard.require_staging(guard.RETRIEVAL_KEYS)
    assert exc.value.code == 3
    with pytest.raises(SystemExit) as exc:
        guard.require_loopback_url("--base-url", "http://10.20.30.40:8000")
    assert exc.value.code == 3
    err = capsys.readouterr().err
    assert err.splitlines() == ["staging guard: refused (ENVIRONMENT)", "staging guard: refused (TEI_EMBED_URL)",
                                "staging guard: refused (TEI_EMBED_URL)", "staging guard: refused (--base-url)"]
    staging_env(monkeypatch, tmp_path, name="again")
    inputs = private(tmp_path, "inputs")
    (inputs / "questions.csv").write_text("question_id,question\nq1,synthetic\n", encoding="utf-8")
    (inputs / "cases.json").write_text(json.dumps({"cases": [{"question_id": "q1", "question": "synthetic"}]}))
    (inputs / "identities.json").write_text(json.dumps({"identities": [{"alias": "s1", "national_code": "0000000001"}]}))
    inside = ROOT / f"_release_eval_refused_{uuid.uuid4().hex}"
    for call in (lambda: rev.freeze(inputs / "questions.csv", inside, prepare=str),
                 lambda: rev.label_sheet(inputs, [], inside),
                 lambda: aqe.collect("http://127.0.0.1:9", "x", inputs, "FAQ", inputs / "identities.json", inside)):
        with pytest.raises(SystemExit) as exc:
            call()
        assert exc.value.code == 2 and not inside.exists()
    assert capsys.readouterr().err.count("refused (artifact_repository_forbidden)") == 3
    old = "x = 1\n        rag_system = await blocking_runner.run(\n            RAGSystem,\n            a=b,\n        )\ny = 2\n"
    assert not rev.ragsystem_call_touched("@@ -6 +6 @@\n-y = 2\n+y = 3\n", old, old.replace("y = 2", "y = 3"))
    assert rev.ragsystem_call_touched("@@ -4 +4 @@\n-            a=b,\n+            a=c,\n", old, old.replace("a=b", "a=c"))


FAKE_CHILD = textwrap.dedent('''
    import json, os, sys
    from pathlib import Path
    run_dir = Path(sys.argv[sys.argv.index("--run-dir") + 1])
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    cases = json.loads(Path(request["cases_file"]).read_text(encoding="utf-8"))["cases"]
    marker = cases[0]["question"].split()[-1]
    print("child stdout", marker); print("child stderr", marker, file=sys.stderr)
    def write(name, payload):
        fd = os.open(run_dir / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
    swap = os.environ.get("FAKE_SWAP") == "1"
    rows = [{"question_id": c["question_id"], "retrieved_ids": ["c1", "c2", "c3"],
             "reranked_ids": ["c2", "c1", "c3"] if swap else ["c1", "c2", "c3"],
             "context_ids": ["c2", "c1", "c3"] if swap else ["c1", "c2", "c3"],
             "empty": False, "latency_ms": 10.0 + i, "error": None} for i, c in enumerate(cases)]
    write("per_question.json", rows)
    write("titles.json", {c: "title " + marker for c in ("c1", "c2", "c3")})
    write("child.json", {"settings": {"rag_retrieval_top_k": 10}, "case_count": len(cases), "error_count": 0, "fatal": None})
''')


def test_end_to_end_leaves_no_private_text(tmp_path, monkeypatch, capfd):
    marker = f"LEAKMARK{uuid.uuid4().hex}"
    started = time.time_ns()
    staging_env(monkeypatch, tmp_path)
    monkeypatch.setattr(rev, "checkout_head", lambda: "0" * 40)
    monkeypatch.setattr(rev, "check_worktree", lambda worktree: "f" * 40)
    inputs, out = private(tmp_path, "inputs"), private(tmp_path, "out")
    questions = inputs / "questions.csv"
    with questions.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows([["question_id", "question"], *[[f"q{i}", f"کارمزد انتقال {i} {marker}"] for i in range(4)]])
    (inputs / "identities.json").write_text(json.dumps({"identities": [
        {"alias": "synthetic-1", "national_code": "0000000001"}]}), encoding="utf-8")
    fake_child = inputs / "fake_child.py"
    fake_child.write_text(FAKE_CHILD, encoding="utf-8")
    tag = uuid.uuid4().hex
    reports = [rev.REPORT_ROOT / f"_test_release_eval_{tag}_{name}.md" for name in ("retrieval", "answers")]
    try:
        assert rev.freeze(questions, out / "cases") == 0
        cases = json.loads((out / "cases" / "cases.json").read_text(encoding="utf-8"))
        assert cases["query_rule"] == "general_canonical" and marker in cases["cases"][0]["retrieval_query"]
        assert rev.run(tmp_path, out / "cases", "base", "FAQ synthetic", out / "runs", child=fake_child) == 0
        monkeypatch.setenv("FAKE_SWAP", "1")
        assert rev.run(tmp_path, out / "cases", "rc", "FAQ synthetic", out / "runs", child=fake_child) == 0
        assert rev.label_sheet(out / "cases", [out / "runs" / "base", out / "runs" / "rc"], out / "labels") == 0
        rows = list(csv.reader((out / "labels" / "label-sheet.csv").open(encoding="utf-8-sig")))
        assert marker in rows[1][1] and marker in rows[1][3]
        labeled = [r[:4] + ["1" if r[2] == "c1" else ""] if r[0] and r[0] != "question_id" else r for r in rows]
        sheet = private(tmp_path, "labeled") / "sheet.csv"
        with sheet.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.writer(stream).writerows(labeled)
        assert rev.compare(out / "cases", sheet, [out / "runs" / "base", out / "runs" / "rc"], "base",
                           reports[0], THRESHOLDS) == 0
        async def post(url, body, timeout):
            assert url == "http://127.0.0.1:9/api/mobile/v1/talk" and timeout == 50.0
            return 200, f"پاسخ {body['query']} {marker}"
        for label in ("base", "rc"):
            assert aqe.collect("http://127.0.0.1:9", label, out / "cases", "FAQ synthetic",
                               inputs / "identities.json", out / "answers", post=post) == 0
        assert aqe.blind(out / "answers" / "base", out / "answers" / "rc", 3, out / "blind") == 0
        graded = list(csv.DictReader((out / "blind" / "grading-sheet.csv").open(encoding="utf-8-sig")))
        for row in graded:
            row.update(correct_1="correct", correct_2="correct", grounded_1="yes", grounded_2="yes", preference="same")
        sheet = private(tmp_path, "graded") / "sheet.csv"
        with sheet.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=aqe.SHEET_HEADER)
            writer.writeheader()
            writer.writerows(graded)
        assert aqe.score(sheet, out / "blind" / "grading-key.json", reports[1]) == 0
        retrieval_report = reports[0].read_text(encoding="utf-8")
        assert "| `rc` − `base` | mrr_context | -0.5000 | [-0.5000, -0.5000] |" in retrieval_report
        assert "| `rc` | pass | pass | pass | pass | **PASS** |" in retrieval_report and "Overall: **PASS**" in retrieval_report
        for report in reports:
            assert marker not in report.read_text(encoding="utf-8") and "کارمزد" not in report.read_text(encoding="utf-8")
        for name in ("per_question.json", "titles.json", "run.json"):
            assert (out / "runs" / "rc" / name).stat().st_mode & 0o777 == 0o600
        assert marker in (out / "answers" / "rc" / "answers.json").read_text(encoding="utf-8")
        leaked = []
        for directory, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules"}]
            for name in files:
                path = Path(directory) / name
                try:
                    if path.stat().st_mtime_ns >= started and marker.encode() in path.read_bytes():
                        leaked.append(path.name)
                except OSError:
                    pass
        assert leaked == []
    finally:
        for report in reports:
            report.unlink(missing_ok=True)
    captured = capfd.readouterr()
    assert marker not in captured.out and marker not in captured.err
    assert "run: label=rc cases=4 errors=0 status=complete" in captured.out
