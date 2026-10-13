"""Synthetic A1 contracts; no customer fixtures or live service calls."""
from __future__ import annotations

import asyncio
import copy
import csv
from dataclasses import replace
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from knowledge_audit.calendar import jalali_date
from knowledge_audit.export import export_preparation
from knowledge_audit.history import AuditHistoryProvider
from knowledge_audit.inputs import ColumnMapping, CsvInputAdapter, TimestampPolicy
from knowledge_audit.preparation import QueryPreparer, prepare_dataset
from knowledge_audit.privacy import AuditError, Redactor, formula_safe, private_directory
from knowledge_audit.snapshot import (capture_snapshot, enforce_run_compatibility,
                                     load_snapshot, read_postgres_snapshot, _source_records)
from tests.test_answering_service import (Agent, Classifier, HistoryProvider, ImmediateRunner,
                                         Processor, Rewriter)
from tests.test_kb_audit_tools import _signature
from utils.read_only_audit import canonical_sha256


@pytest.fixture
def redactor():
    return Redactor(b"synthetic-private-key-only-123456789")


def dataset(tmp_path, redactor, rows, *, columns=("query", "session", "timestamp", "role"),
            mapping=None, policy=None, bom=True):
    path = tmp_path / "synthetic.csv"
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows(rows)
    path.write_bytes(stream.getvalue().encode("utf-8-sig" if bom else "utf-8"))
    mapping = mapping or ColumnMapping("query", "session", "timestamp", role="role")
    return CsvInputAdapter(path, mapping, policy=policy).load(redactor)


def t(hour):
    return f"2026-01-01T{hour:02d}:00:00+03:30"


def test_persian_bom_multiline_duplicates_and_order(tmp_path, redactor):
    text = 'پرسش، "نقل قول",\nنیم\u200cفاصله'
    data = dataset(tmp_path, redactor, [[text, "synthetic-session", t(2), "user"],
        [text, "synthetic-session", t(1), "user"], [text, "synthetic-session", t(1), "user"]])
    again = CsvInputAdapter(tmp_path / "synthetic.csv", data.mapping).load(redactor)
    assert data.structure["encoding"] == "utf-8-bom"
    assert [e.content for e in data.selected] == [text] * 3
    assert len({e.source_row_id for e in data.selected}) == 3
    assert [e.source_row_id for e in data.selected] == [e.source_row_id for e in again.selected]
    assert [e.ordinal for e in data.processing_order()] == [2, 3, 1]
    assert "synthetic-session" not in repr(data)


def test_invalid_blank_width_and_unknown_roles_retained(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["", "", "invalid", "user"], [],
        ["text", "", "", "unknown"], ["text", "", "", "user", "extra"]])
    assert len(data.selected) == 4
    assert "missing_query" in data.events[0].issues
    assert data.events[0].timestamp_status == "invalid"
    assert "invalid_record_width" in data.events[1].issues
    assert "invalid_role" in data.events[2].issues
    assert len({e.source_row_id for e in data.selected}) == 4


@pytest.mark.parametrize("mapping,columns", [
    (ColumnMapping("query"), ("query", "query")),
    (ColumnMapping("missing"), ("query",)),
    (ColumnMapping("query", "query"), ("query",)),
    (ColumnMapping("query", date="date"), ("query", "date")),
    (ColumnMapping("query", timestamp="stamp", date="date", time="time"), ("query", "stamp", "date", "time")),
])
def test_mapping_rejects_ambiguity(tmp_path, redactor, mapping, columns):
    with pytest.raises(AuditError):
        dataset(tmp_path, redactor, [], columns=columns, mapping=mapping)


def test_csv_file_syntax_rejected_without_content(tmp_path, redactor):
    path = tmp_path / "invalid.csv"
    path.write_text('query\n"PRIVATE SYNTHETIC malformed', encoding="utf-8")
    with pytest.raises(AuditError, match="^csv_syntax_or_encoding_error$"):
        CsvInputAdapter(path, ColumnMapping("query")).load(redactor)


def test_absent_sessions_are_independent(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["loan", t(1)], ["how long does it take?", t(2)]],
        columns=("query", "timestamp"), mapping=ColumnMapping("query", timestamp="timestamp"))
    assert all(not e.safe_session_ref for e in data.events)
    assert AuditHistoryProvider(data, redactor).before(data.events[1]).messages == ()


def test_roles_isolation_cutoff_and_user_only(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["later", "a", t(5), "user"],
        ["prior", "a", t(1), "user"], ["foreign", "b", t(2), "assistant"],
        ["available answer", "a", t(2), "assistant"], ["now", "a", t(3), "user"],
        ["answer completes later", "a", t(4), "assistant"]])
    context = AuditHistoryProvider(data, redactor).before(data.events[4])
    assert context.messages == ({"role": "user", "content": "prior"}, {"role": "assistant", "content": "available answer"})
    assert data.structure["selected_row_count"] == 3
    assert data.structure["history_only_row_count"] == 3
    only = replace(data, events=tuple(e for e in data.events if e.role == "user"))
    context = AuditHistoryProvider(only, redactor).before(only.events[2])
    assert context.provenance["history_status"] == "user_only"
    assert all(m["role"] == "user" for m in context.messages)


def test_equal_timestamps_excluded_and_prior_order_uncertain(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["first", "a", t(1), "user"],
        ["same-time answer", "a", t(1), "assistant"], ["now", "a", t(1), "user"],
        ["later", "a", t(2), "user"]])
    provider = AuditHistoryProvider(data, redactor)
    assert provider.before(data.events[2]).messages == ()
    assert provider.before(data.events[2]).provenance["history_status"] == "ambiguous"
    assert provider.before(data.events[3]).provenance["prior_order_ambiguous"]
    authoritative = replace(data, timestamp_policy=TimestampPolicy(authoritative_source_order=True))
    context = AuditHistoryProvider(authoritative, redactor).before(data.events[2])
    assert len(context.messages) == 2
    assert context.provenance["ordering_basis"] == "confirmed_source_sequence"
    assert not context.provenance["prior_order_ambiguous"]


def test_unknown_times_incomplete_and_explicit_sequence(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["prior", "a", "broken", "user"], ["now", "a", t(2), "user"]])
    assert not AuditHistoryProvider(data, redactor).before(data.events[1]).messages
    assert AuditHistoryProvider(data, redactor).before(data.events[1]).provenance["history_status"] == "incomplete"
    authoritative = replace(data, timestamp_policy=TimestampPolicy(authoritative_source_order=True))
    assert len(AuditHistoryProvider(authoritative, redactor).before(data.events[1]).messages) == 1


def test_production_history_limit(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [[f"prior {i}", "a", t(i), "user"] for i in range(1, 13)])
    ctx = AuditHistoryProvider(data, redactor).before(data.events[-1])
    assert len(ctx.messages) == 10
    from conversation_history import format_rewrite_history
    assert len(format_rewrite_history(list(ctx.messages), max_turns=3).splitlines()) == 6


def test_timezone_offsets_naive_dst_and_jalali_validation():
    p = TimestampPolicy()
    assert p.parse("2026-01-01 12:00:00")[1] == "unresolved"
    local = TimestampPolicy(source_timezone="Asia/Tehran")
    assert local.parse("2026-01-01 12:00:00")[0] == p.parse("2026-01-01T12:00:00+03:30")[0]
    assert local.parse("2026-01-01 12:00:00")[2]["offset_seconds"] == 12600
    assert TimestampPolicy(source_timezone="America/New_York").parse("2026-11-01 01:30:00")[1] == "ambiguous"
    assert TimestampPolicy(source_timezone="America/New_York").parse("2026-03-08 02:30:00")[1] == "invalid"
    assert p.parse("2026-01-01")[1] == "invalid"
    assert jalali_date(1405, 1, 1) == date(2026, 3, 21)
    assert jalali_date(1395, 1, 23) == date(2016, 4, 11)
    assert jalali_date(1403, 12, 30) == date(2025, 3, 20)
    assert jalali_date(1404, 1, 1) == date(2025, 3, 21)
    with pytest.raises(AuditError):
        jalali_date(1404, 12, 30)
    with pytest.raises(AuditError):
        TimestampPolicy(source_timezone="invalid-zone")
    j = TimestampPolicy("jalali", "Asia/Tehran")
    assert j.parse("1405/01/01 12:00:00")[0].isoformat() == "2026-03-21T08:30:00+00:00"
    assert j.parse("1405/13/01 12:00:00")[1] == "invalid"


def test_user_only_followup_and_insufficient_context(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["loan approval", "a", t(1), "user"],
        ["how long does it take?", "a", t(2), "user"], ["how long does it take?", "b", t(3), "user"]])
    rewriter = Rewriter(result="How long does loan approval take?")
    classifier = Classifier()
    results = asyncio.run(prepare_dataset(data, QueryPreparer(Processor(), ImmediateRunner(), rewriter, classifier), redactor, model_limit=3))
    assert results[1]["preparation_status"] == "prepared"
    assert results[1]["history_status"] == "user_only"
    assert results[2]["preparation_status"] == "needs_context"
    assert len(rewriter.rewrite_calls) == 1
    assert len(classifier.queries) == 2
    assert all(r["coverage_status"] == "" for r in results)
    assert not any(m.startswith("AI:") for m in rewriter.rewrite_calls[0]["current_summary"].splitlines())


@pytest.mark.parametrize("response", ["How long does card shipping take?", "how long does it take?", ""])
def test_rewrite_cannot_supply_unsupported_subject(tmp_path, redactor, response):
    data = dataset(tmp_path, redactor, [["loan approval", "a", t(1), "user"], ["how long does it take?", "a", t(2), "user"]])
    results = asyncio.run(prepare_dataset(data, QueryPreparer(Processor(), ImmediateRunner(), Rewriter(result=response), Classifier()), redactor, model_limit=2))
    assert results[-1]["preparation_status"] == "needs_context"


@pytest.mark.parametrize("intent", ["general", "chitchat"])
@pytest.mark.parametrize("has_history", [False, True])
def test_actual_answering_preparation_parity(tmp_path, redactor, intent, has_history):
    from answering_service import AnsweringService, AnswerRequestContext
    from utils.persian_hybrid_search import PersianTextProcessor
    original = "  مدت زمان افتتاح حساب چقدره؟ يک تست  "
    rows = [["prior subject", "a", t(1), "user"], [original, "a", t(2), "user"]] if has_history else [[original, "a", t(2), "user"]]
    data = dataset(tmp_path, redactor, rows)
    event = data.events[-1]
    history = AuditHistoryProvider(data, redactor).before(event)
    processor = PersianTextProcessor(use_stemming=False)
    rewriter, classifier, agent = Rewriter(result="مدت زمان افتتاح حساب چقدر است؟"), Classifier(intent), Agent()
    service = AnsweringService(agent_service=agent, intent_classifier=classifier,
        history_rewriting_service=rewriter, text_processor=processor, blocking_runner=ImmediateRunner(),
        category_resolver=lambda _: "FAQ", history_provider=HistoryProvider(list(history.messages)))
    async def check():
        audit = await QueryPreparer.from_answering_service(service).prepare(event, AuditHistoryProvider(data, redactor), redactor, model_prepare=True)
        assert not agent.stateless and not agent.persisted
        production = await service.answer(AnswerRequestContext(original_query=original, selected_documents=("synthetic",),
            session_id="synthetic", persist_agent_state=False))
        assert audit["normalized_query_redacted"] == production.normalized_query
        assert audit["standalone_query_redacted"] == production.rewritten_query
        assert audit["canonical_retrieval_query_redacted"] == production.final_retrieval_query
        assert audit["existing_intent"] == production.intent
        assert audit["scope_status"] == ("chitchat" if intent == "chitchat" else "unknown")
    asyncio.run(check())


def test_failures_preserved_errors_private_and_bounded_sequential(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["question", "a", t(1), "user"]] * 12)
    active = 0
    seen = []
    class Guard:
        async def classify(self, query):
            nonlocal active
            active += 1
            assert active == 1
            await asyncio.sleep(0)
            active -= 1
            seen.append(query)
            raise RuntimeError("password=synthetic-secret customer 09123456789")
    results = asyncio.run(prepare_dataset(data, QueryPreparer(Processor(), ImmediateRunner(), Rewriter(), Guard()), redactor, model_limit=10))
    assert len(results) == 12 and len(seen) == 10
    assert [r["preparation_status"] for r in results] == ["failed"] * 10 + ["pending_model"] * 2
    assert "synthetic-secret" not in json.dumps(results)
    assert all(r["preparation_errors"] == ["query_preparation_failed"] for r in results[:10])
    with pytest.raises(AuditError):
        asyncio.run(prepare_dataset(data, QueryPreparer(Processor(), ImmediateRunner()), redactor, model_limit=11))


def test_redaction_consistent_model_inputs_outputs_and_exports(tmp_path, redactor):
    sensitive = "09123456789"
    text = f"phone {sensitive}, email=person@example.test password=synthetic-secret account 1234567890123456 مبلغ 250 تومان"
    safe = redactor.text(text)
    for value in (sensitive, "person@example.test", "synthetic-secret", "1234567890123456", "250 تومان"):
        assert value not in safe
    assert redactor.text(sensitive) in safe
    data = dataset(tmp_path, redactor, [[text, "RAW-SESSION-SYNTHETIC", t(1), "user"], ["question", "RAW-SESSION-SYNTHETIC", t(2), "user"]])
    rewriter = Rewriter(result=text)
    classifier = Classifier()
    rows = asyncio.run(prepare_dataset(data, QueryPreparer(Processor(), ImmediateRunner(), rewriter, classifier), redactor, model_limit=2))
    assert sensitive not in str(rewriter.rewrite_calls) + str(classifier.queries)
    export = export_preparation(tmp_path, data, rows, run_id="synthetic-run", configuration={}, code_identity={}, redactor=redactor)
    artifacts = (tmp_path / "preparation.csv").read_text("utf-8-sig") + (tmp_path / "preparation-manifest.json").read_text()
    assert sensitive not in artifacts and "RAW-SESSION-SYNTHETIC" not in artifacts
    assert export["coverage_evaluation"] == "not_run"


@pytest.mark.parametrize("value", ["=1+1", "  +1", "\u202e@command", "\tordinary", "\r\ntext", "\x00 -12", "\u200f\u200e=1"])
def test_formula_protection_preserves_cell(value):
    assert formula_safe(value) == "'" + value
    assert formula_safe("پرسش،\nنیم\u200cفاصله") == "پرسش،\nنیم\u200cفاصله"


def test_export_manifest_identity_roundtrip_and_row_accounting(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["\u202e=1+1", "a", t(2), "user"], ['پرسش "quoted",\nنیم\u200cفاصله', "a", t(1), "user"]])
    results = asyncio.run(prepare_dataset(data, QueryPreparer(Processor(), ImmediateRunner()), redactor))
    original_hash = hashlib.sha256((tmp_path / "synthetic.csv").read_bytes()).hexdigest()
    manifest = export_preparation(tmp_path, data, results[::-1], run_id="synthetic", configuration={"version": 1}, code_identity={}, redactor=redactor)
    raw = (tmp_path / "preparation.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    parsed = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    assert [r["source_row_id"] for r in parsed] == manifest["row_ids"]
    assert all(r["export_id"] == manifest["export_id"] and r["coverage_status"] == "" for r in parsed)
    assert parsed[0]["input_query_redacted"] == "'\u202e=1+1"
    assert parsed[1]["input_query_redacted"] == data.events[1].content
    assert isinstance(json.loads(parsed[0]["history_provenance"]), dict)
    assert hashlib.sha256(raw).hexdigest() == manifest["csv_sha256"]
    assert original_hash == data.input_id
    assert (tmp_path / "preparation.csv").stat().st_mode & 0o777 == 0o600
    with pytest.raises(AuditError, match="export_row_accounting_mismatch"):
        export_preparation(tmp_path, data, [results[0], results[0]], run_id="synthetic", configuration={}, code_identity={}, redactor=redactor)


def capture_fixture():
    row = {"chunk_id": 1, "document_id": 10, "chunk_index": 0, "document_title": "synthetic FAQ",
           "content": "question: تست\nanswer: پاسخ کامل، شرط اول\nشرط دوم\nquestion category: تست\nsub_category: زیرمجموعه",
           "chunk_type": "text", "page_number": 1, "chunk_meta_data": {"not_copied": "synthetic-person"}}
    signature = _signature()
    signature["postgres"]["records"] = _source_records([row])
    signature["postgres"]["aggregate_sha256"] = canonical_sha256(signature["postgres"]["records"])
    capture = {"rows": [row], "document_revisions": {"10": 2}, "latest_stored_version_ids": {"1": 7}}
    return signature, capture


def test_snapshot_full_content_taxonomy_manifest_and_integrity(tmp_path, redactor):
    signature, capture = capture_fixture()
    manifest = capture_snapshot(tmp_path, redactor, signature_provider=lambda _: copy.deepcopy(signature), content_provider=lambda: capture)
    snapshot = load_snapshot(tmp_path / manifest["content_file"])
    chunk = snapshot["records"][0]
    assert chunk["content"] == capture["rows"][0]["content"]
    assert "شرط دوم" in chunk["answer"]
    assert (chunk["chunk_id"], chunk["faq_entry_id"], chunk["main_category"], chunk["sub_category"]) == ("1", "1", "تست", "زیرمجموعه")
    assert chunk["document_revision"] == 2 and chunk["latest_stored_version_id"] == 7
    assert not manifest["retrieval_frozen"]
    assert manifest["snapshot_id"] == snapshot["snapshot_id"]
    assert "synthetic-person" not in (tmp_path / "kb-snapshot.json").read_text()
    snapshot["records"][0]["content"] = "tampered"
    (tmp_path / "kb-snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(AuditError):
        load_snapshot(tmp_path / "kb-snapshot.json")


@pytest.mark.parametrize("drift", ["source", "vector", "configuration", "health", "capture"])
def test_snapshot_inconsistent_capture_refused(tmp_path, redactor, drift):
    signature, capture = capture_fixture()
    after = copy.deepcopy(signature)
    if drift == "source":
        after["postgres"]["aggregate_sha256"] = "changed"
    if drift == "vector":
        after["qdrant"]["vector_aggregate_sha256"] = "changed"
    if drift == "configuration":
        after["qdrant"]["collection_config_sha256"] = "changed"
    if drift == "health":
        after["cross_store"]["consistent"] = False
    if drift == "capture":
        capture["rows"][0]["content"] = "changed mid-capture"
    signatures = iter([signature, after])
    with pytest.raises(AuditError):
        capture_snapshot(tmp_path, redactor, signature_provider=lambda _: next(signatures), content_provider=lambda: capture)
    assert not (tmp_path / "kb-snapshot.json").exists()


def test_later_runner_rejects_source_index_config_drift():
    signature, _ = capture_fixture()
    snapshot = {"source_signature": signature}
    enforce_run_compatibility(snapshot, copy.deepcopy(signature), "config", "config")
    changed = copy.deepcopy(signature)
    changed["qdrant"]["vector_aggregate_sha256"] = "changed"
    with pytest.raises(AuditError, match="source_or_index_drift"):
        enforce_run_compatibility(snapshot, changed, "config", "config")
    with pytest.raises(AuditError, match="configuration_drift"):
        enforce_run_compatibility(snapshot, signature, "config", "other")


def test_readonly_repeatable_read_cleanup_on_failure():
    connection = Mock()
    connection.cursor.return_value.__enter__ = Mock(side_effect=RuntimeError("synthetic DB error"))
    connection.cursor.return_value.__exit__ = Mock()
    with pytest.raises(RuntimeError):
        read_postgres_snapshot(lambda: connection)
    connection.set_session.assert_called_once_with(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
    connection.commit.assert_not_called()


@pytest.mark.parametrize("output,expected", [
    ("<rewrite>How long does loan approval take?</rewrite>", "prepared"),
    ("unstructured model output", "needs_context"),
])
def test_actual_production_rewriter_mocked_model_and_observer_isolation(tmp_path, redactor, output, expected):
    from new_architecture.app.services.history.rewriting import HistoryRewritingService
    from pipeline_observer import bind_pipeline_observer
    from tests.test_answering_service import Observer
    data = dataset(tmp_path, redactor, [["loan approval", "a", t(1), "user"], ["how long does it take?", "a", t(2), "user"]])
    prompts = []
    class Model:
        model_id = "synthetic-model"
        async def generate_text(self, prompt):
            prompts.append(prompt)
            return output
    rewriter = HistoryRewritingService(Model(), None)
    inherited = Observer()
    async def run():
        with bind_pipeline_observer(inherited):
            return await QueryPreparer(Processor(), ImmediateRunner(), rewriter, Classifier()).prepare(
                data.events[1], AuditHistoryProvider(data, redactor), redactor, model_prepare=True)
    result = asyncio.run(run())
    assert result["preparation_status"] == expected
    assert len(prompts) == 1 and not inherited.records
    assert result["rewrite_status"] == ("rewritten" if expected == "prepared" else "unverified_context")


def test_numeric_redaction_nonidentifier_suffix_has_no_nested_backtracking(redactor):
    text = " " + "1" * 120 + "suffix"
    assert isinstance(redactor.text(text), str)


def test_snapshot_redacts_sensitive_content_without_truncation(tmp_path, redactor):
    signature, capture = capture_fixture()
    capture["rows"][0]["content"] += "\nphone 09123456789"
    signature["postgres"]["records"] = _source_records(capture["rows"])
    signature["postgres"]["aggregate_sha256"] = canonical_sha256(signature["postgres"]["records"])
    manifest = capture_snapshot(tmp_path, redactor, signature_provider=lambda _: copy.deepcopy(signature), content_provider=lambda: capture)
    snapshot = load_snapshot(tmp_path / "kb-snapshot.json")
    assert "09123456789" not in json.dumps(snapshot)
    assert "شرط دوم" in snapshot["records"][0]["answer"]
    assert manifest["redacted_record_count"] == 1


def test_opaque_hash_digits_preserved_only_in_typed_fields(redactor):
    from knowledge_audit.export import _redact
    opaque = "row_" + "0123456789" * 3 + "ab"
    digest = "a" * 10 + "0123456789" + "b" * 44
    safe = _redact({"source_row_id": opaque, "history_provenance": {"history_row_ids": [opaque],
        "history_digest": digest}, "input_query_redacted": "0123456789"}, redactor)
    assert safe["source_row_id"] == opaque
    assert safe["history_provenance"]["history_row_ids"] == [opaque]
    assert safe["history_provenance"]["history_digest"] == digest
    assert safe["input_query_redacted"] != "0123456789"
    token = "[PRIVATE_0123456789ab]"
    assert redactor.text(token) == token
    assert redactor.text(redactor.text("09123456789")) == redactor.text("09123456789")


def test_timeout_keeps_row_without_model_retry(tmp_path, redactor):
    data = dataset(tmp_path, redactor, [["question", "a", t(1), "user"]])
    calls = []
    class SlowClassifier:
        async def classify(self, query):
            calls.append(query)
            await asyncio.sleep(10)
    result = asyncio.run(prepare_dataset(data, QueryPreparer(Processor(), ImmediateRunner(), Rewriter(), SlowClassifier()),
        redactor, model_limit=1, timeout_seconds=0.01))
    assert result[0]["source_row_id"] == data.selected[0].source_row_id
    assert result[0]["preparation_errors"] == ["preparation_timeout"]
    assert len(calls) == 1 and result[0]["model_selected"]


def test_artifacts_reject_repo_symlinks_permissions_and_overwrite(tmp_path):
    with pytest.raises(AuditError, match="artifact_repository_forbidden"):
        private_directory(Path(__file__).resolve().parents[1] / "static" / "synthetic")
    other = tmp_path / "permissive"
    other.mkdir(mode=0o755)
    with pytest.raises(AuditError, match="artifact_directory_permissions"):
        private_directory(other)
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(AuditError, match="artifact_symlink_forbidden"):
        private_directory(link / "child")
    from knowledge_audit.privacy import private_write
    private_write(tmp_path / "synthetic-private", b"safe")
    with pytest.raises(FileExistsError):
        private_write(tmp_path / "synthetic-private", b"replace")
