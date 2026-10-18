"""KB content privacy policy, separate from customer-query and logging policies.

Every identifier here is invented; valid check digits are generated below.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import re

import pytest

from knowledge_audit.privacy import AuditError, Redactor, _valid_iban, private_json
from knowledge_audit.recommendations import eligibility
from knowledge_audit.settings import load_coverage_settings
from knowledge_audit.snapshot import _source_records, capture_snapshot, load_snapshot
from tests.test_kb_audit_tools import _signature
from tests.test_knowledge_coverage_pipeline import LabeledModel, Retrieval, evaluate, snapshot
from utils.log_sanitizer import _valid_card, _valid_national, scrub_text
from utils.read_only_audit import canonical_sha256

PLACEHOLDER = re.compile(r"\[PRIVATE_[0-9a-f]{12}\]")


@pytest.fixture
def redactor():
    return Redactor(b"synthetic-only-private-key-1234567890")


def luhn(prefix: str) -> str:
    total = 0
    for index, digit in enumerate(reversed(prefix + "0")):
        number = int(digit) * (2 if index % 2 else 1)
        total += number - 9 if number > 9 else number
    return prefix + str((10 - total % 10) % 10)


def iban(bban: str) -> str:
    # I=18, R=27, check digits 00 moved to the end before mod 97.
    return "IR%02d%s" % (98 - int(bban + "182700") % 97, bban)


def national(nine: str) -> str:
    remainder = sum(int(d) * (10 - i) for i, d in enumerate(nine)) % 11
    return nine + str(remainder if remainder < 2 else 11 - remainder)


CARD = luhn("999912345678901")
CARD_INVALID = CARD[:-1] + str((int(CARD[-1]) + 1) % 10)
IBAN = iban("0123456789012345678901")
IBAN_INVALID = IBAN[:2] + "%02d" % ((int(IBAN[2:4]) + 1) % 100) + IBAN[4:]
NATIONAL = national("123456789")
NATIONAL_INVALID = NATIONAL[:-1] + str((int(NATIONAL[-1]) + 1) % 10)


def test_generated_identifiers_pass_and_fail_their_checksums():
    assert _valid_card(CARD) and not _valid_card(CARD_INVALID)
    assert _valid_iban(IBAN) and not _valid_iban(IBAN_INVALID)
    assert _valid_iban(IBAN.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))
    assert _valid_national(NATIONAL) and not _valid_national(NATIONAL_INVALID)


@pytest.mark.parametrize("text", [
    "کارمزد صدور کارت 50,000 ریال است.",
    "سقف انتقال روزانه 100000000 ریال می‌باشد.",
    "برای پشتیبانی با شماره 02112345678 تماس بگیرید.",
    "با کد *123# یا شماره 4040 تماس بگیرید.",
    "تا 3 روز کاری از تاریخ 1403/05/01 طول می‌کشد.",
    "رمز: دوم یکبار مصرف را از اپلیکیشن دریافت کنید.",
    "نام: نام کامل خود را وارد کنید.",
])
def test_kb_text_keeps_public_facts(redactor, text):
    assert redactor.kb_text(text) == text


@pytest.mark.parametrize("secret", [
    "Bearer abcdefghijklmnopqrstuv",
    "eyJhbGciOiJIUzI1.eyJzdWIiOiJzeW50.c3ludGhldGljc2ln",
    "api_key=synthetic-value-123",
    CARD,
    CARD[:4] + " " + CARD[4:8] + " " + CARD[8:12] + " " + CARD[12:],
    IBAN,
    NATIONAL,
    "09121234567",
    "synthetic.person@example.com",
])
def test_kb_text_scrubs_secrets_and_validated_identifiers(redactor, secret):
    result = redactor.kb_text("مقدار " + secret + " ثبت شد.", ("support@fablebank.example",))
    assert secret not in result and PLACEHOLDER.search(result)
    assert result.startswith("مقدار ") and result.endswith(" ثبت شد.")


def test_kb_text_scrubs_only_the_labelled_value(redactor):
    result = redactor.kb_text("شماره حساب: 0101234567890 را وارد کنید.")
    assert re.fullmatch(r"شماره حساب: \[PRIVATE_[0-9a-f]{12}\] را وارد کنید\.", result)
    assert redactor.kb_text("شماره حساب: شماره ۱۳ رقمی خود را وارد کنید.") == "شماره حساب: شماره ۱۳ رقمی خود را وارد کنید."
    # Same placeholder as the customer-query policy for the same value.
    assert redactor.text("0101234567890") in result


@pytest.mark.parametrize("text", [
    "شماره " + CARD_INVALID + " نمونه است.",
    "کد " + NATIONAL_INVALID + " نمونه است.",
    "شبای نمونه " + IBAN_INVALID + " است.",
    "ایمیل support@fablebank.example است.",
    "ایمیل help@contact.fablebank.example است.",
    "شماره +۹۸ ۹۱۲ ۹۸۷ ۶۵۴۳ پاسخگو است.",
])
def test_kb_text_keeps_failed_checksums_and_allow_listed_contacts(redactor, text):
    contacts = ("support@fablebank.example", "@contact.fablebank.example", "09129876543")
    assert redactor.kb_text(text, contacts) == text


def test_kb_text_limit(redactor):
    with pytest.raises(AuditError, match="redaction_text_limit"):
        redactor.kb_text("x" * 32769)


def test_customer_and_logging_policies_unchanged(redactor):
    for value in ("کارمزد 50,000 ریال", "کد پیگیری 123456", "09121234567"):
        assert value not in redactor.text("متن " + value) and PLACEHOLDER.search(redactor.text("متن " + value))
    sample = ("fee 50,000 rial; call 09121234567; mail person@example.com; api_key=synthetic-value-1; "
              "card 1234 5678 9012 3452; id 0000000001; iban IR000000000000000000000000")
    assert scrub_text(sample) == ("fee 50,000 rial; call [REDACTED]; mail [REDACTED]; [REDACTED]; "
                                  "card [REDACTED]; id 0000000001; iban [REDACTED]")


def test_public_contacts_setting_normalises_three_shapes():
    settings = load_coverage_settings({"KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS":
        " Support@FableBank.example , @Contact.FableBank.example, +98 912-987-6543, 0098۹۱۲۰۰۰۰۰۰۱, 021 1234 5678 "})
    assert settings.public_contacts == ("support@fablebank.example", "@contact.fablebank.example",
                                        "09129876543", "09120000001", "02112345678")
    assert load_coverage_settings({}).public_contacts == ()
    assert "public_contacts" not in json.dumps(load_coverage_settings({}).manifest())


@pytest.mark.parametrize("bad", ["support", "support@", "@nodot", "12", "phone 0912", "a@b.example,,c@d.example"])
def test_public_contacts_setting_rejects_unknown_shapes(bad):
    with pytest.raises(AuditError, match="invalid_coverage_public_contacts"):
        load_coverage_settings({"KNOWLEDGE_COVERAGE_PUBLIC_CONTACTS": bad})


FACTS = "کارمزد صدور کارت 50,000 ریال است. سقف انتقال روزانه 100000000 ریال می‌باشد."


def capture(tmp_path, redactor, content, contacts=()):
    row = {"chunk_id": 1, "document_id": 10, "chunk_index": 0, "document_title": "synthetic FAQ",
           "content": "question: کارمزد\nanswer: " + content + "\nquestion category: تست\nsub_category: زیرمجموعه",
           "chunk_type": "text", "page_number": 1, "chunk_meta_data": {}}
    signature = _signature()
    signature["postgres"]["records"] = _source_records([row])
    signature["postgres"]["aggregate_sha256"] = canonical_sha256(signature["postgres"]["records"])
    source = {"rows": [row], "document_revisions": {"10": 2}, "latest_stored_version_ids": {"1": 7}}
    manifest = capture_snapshot(tmp_path, redactor, signature_provider=lambda _: copy.deepcopy(signature),
                                content_provider=lambda: source, public_contacts=contacts)
    return manifest, row


def test_capture_snapshot_keeps_amounts_and_never_logs_kb_text(tmp_path, redactor, monkeypatch):
    seen = []
    monkeypatch.setattr(logging.Logger, "_log", lambda self, level, msg, args, *a, **k: seen.append((msg, args, a, k)))
    contacts = ("09129876543",)
    manifest, row = capture(tmp_path, redactor, FACTS, contacts)
    snap = load_snapshot(tmp_path / "kb-snapshot.json")
    record = snap["records"][0]
    assert snap["schema_version"] == "a1-kb-snapshot-2" and manifest["schema_version"] == "a1-kb-manifest-2"
    assert snap["kb_redaction_policy"] == {"version": "kb-content-1", "public_contacts_sha256": canonical_sha256(sorted(contacts))}
    assert record["content"] == row["content"] and FACTS in record["answer"] and record["redaction_changed"] is False
    assert manifest["redacted_record_count"] == 0
    assert "knowledge_audit/privacy.py" in snap["capture_code_sha256"]
    assert (tmp_path / "kb-snapshot.json").stat().st_mode & 0o777 == 0o600
    assert not any("50,000" in repr(call) or "کارمزد" in repr(call) for call in seen)


def test_capture_snapshot_counts_real_scrubs(tmp_path, redactor):
    manifest, row = capture(tmp_path, redactor, FACTS + " کارت نمونه " + CARD)
    record = load_snapshot(tmp_path / "kb-snapshot.json")["records"][0]
    assert CARD not in json.dumps(record) and "50,000" in record["content"] and record["redaction_changed"] is True
    assert manifest["redacted_record_count"] == 1


def test_old_snapshots_load_but_cannot_start_runs(tmp_path, redactor):
    (tmp_path / "v2").mkdir(mode=0o700)
    capture(tmp_path / "v2", redactor, FACTS)
    current = load_snapshot(tmp_path / "v2" / "kb-snapshot.json")
    old = {k: v for k, v in current.items() if k not in {"snapshot_id", "kb_redaction_policy"}}
    old["schema_version"] = "a1-kb-snapshot-1"
    old["snapshot_id"] = canonical_sha256(old)
    (tmp_path / "v1").mkdir(mode=0o700)
    private_json(tmp_path / "v1" / "kb-snapshot.json", old)
    assert load_snapshot(tmp_path / "v1" / "kb-snapshot.json")["schema_version"] == "a1-kb-snapshot-1"


def test_create_run_refuses_superseded_snapshot(tmp_path, monkeypatch):
    from knowledge_audit.api import SAFE_API_CODES
    from knowledge_audit.failures import RUN_ADMISSION_CODES
    from knowledge_audit.jobs import versions
    from tests.test_knowledge_coverage_access_jobs import seed
    monkeypatch.setenv("KNOWLEDGE_COVERAGE_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    store, d, s, meta, data, *_ = seed(tmp_path)
    old = store.snapshot(s["snapshot_id"], 1)
    old = {k: v for k, v in old.items() if k not in {"snapshot_id", "kb_redaction_policy"}}
    old["schema_version"] = "a1-kb-snapshot-1"
    old["snapshot_id"] = canonical_sha256(old)
    (tmp_path / "old").mkdir(mode=0o700)
    private_json(tmp_path / "old" / "kb-snapshot.json", old)
    private_json(tmp_path / "old" / "kb-snapshot-manifest.json", {"snapshot_id": old["snapshot_id"],
        "content_file_sha256": hashlib.sha256((tmp_path / "old" / "kb-snapshot.json").read_bytes()).hexdigest()})
    registered = store.register_snapshot(tmp_path / "old" / "kb-snapshot.json", tmp_path / "old" / "kb-snapshot-manifest.json", 1)
    with pytest.raises(AuditError, match="snapshot_policy_superseded"):
        store.create_run(1, d["dataset_id"], registered["snapshot_id"], [data.selected[0].source_row_id],
                         {"entry_budget": 300, "documents": ["Synthetic_FAQ"]}, versions())
    assert RUN_ADMISSION_CODES <= SAFE_API_CODES
    assert meta["snapshot_id"] == s["snapshot_id"]


META = lambda snap: {"state": "completed", "snapshot_id": snap["snapshot_id"]}


def test_scrubbed_entry_without_support_goes_to_review_not_recommendation():
    snap = snapshot({"1": "The card issuance fee is [PRIVATE_0123456789ab].", "2": "Unrelated."})
    snap["records"][0]["redaction_changed"] = True
    row = evaluate(snap, LabeledModel(snap, {}, aspects=1), Retrieval(["1"], ["1", "2"]))[0]
    assert row["outcome"] == "needs_review" and row["coverage_status"] == "uncertain"
    assert "kb_redaction_affected" in row["review_codes"]
    decision = eligibility(row, META(snap))
    assert decision["eligible"] is False and "kb_redaction_unresolved" in decision["reason_codes"]


def test_clean_entry_without_support_is_still_a_possible_gap():
    snap = snapshot({"1": "The card issuance fee is published elsewhere.", "2": "Unrelated."})
    row = evaluate(snap, LabeledModel(snap, {}, aspects=1), Retrieval(["1"], ["1", "2"]))[0]
    assert row["outcome"] == "possible_gap" and "kb_redaction_affected" not in row["review_codes"]
    assert "kb_redaction_unresolved" not in eligibility(row, META(snap))["reason_codes"]


def test_witness_avoiding_scrubbed_entry_keeps_code_residual_only():
    snap = snapshot({"2": "Contact [PRIVATE_0123456789ab] for details.", "3": "Approval takes two working days."})
    snap["records"][0]["redaction_changed"] = True
    row = evaluate(snap, LabeledModel(snap, {"3": ["a1"]}, aspects=1), Retrieval(["2", "3"], ["2", "3"]))[0]
    assert row["outcome"].startswith("covered_") and row["coverage_status"] == "full"
    assert "kb_redaction_affected" in row["residual_review_codes"]
    assert "kb_redaction_affected" not in row["review_codes"]
    assert "kb_redaction_unresolved" in eligibility(row, META(snap))["reason_codes"]


def test_eligibility_reads_redaction_code_from_every_phase():
    snap = snapshot({"1": "Unrelated."})
    row = evaluate(snap, LabeledModel(snap, {}, aspects=1), Retrieval(["1"], ["1"]))[0]
    assert "kb_redaction_unresolved" not in eligibility(row, META(snap))["reason_codes"]
    phased = {**row, "review_codes_by_phase": {"broader": ["kb_redaction_affected"]}}
    assert "kb_redaction_unresolved" in eligibility(phased, META(snap))["reason_codes"]
