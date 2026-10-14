"""Stable answer offsets and snapshot-qualified sentence references."""
import re
from knowledge_audit.privacy import AuditError

SEGMENTER_VERSION = "answer-sentences-1"


def segment_answer(answer: str) -> list[dict]:
    # Preserve every character, including bullets, blank lines, Persian punctuation
    # and decimals. Boundaries include sentence terminators and complete line ends.
    boundaries = [0]
    for match in re.finditer(r"(?:[.!?؟؛]+(?=\s|$)|\r?\n)", answer):
        if match.end() > boundaries[-1]:
            boundaries.append(match.end())
    if boundaries[-1] != len(answer):
        boundaries.append(len(answer))
    return [{"sentence_number": i, "start": start, "end": end, "text": answer[start:end]}
            for i, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1)]


class EvidenceIndex:
    def __init__(self, snapshot: dict):
        self.snapshot = snapshot
        self.snapshot_id = snapshot["snapshot_id"]
        self.records = {r["chunk_id"]: r for r in snapshot["records"]}
        self.sentences = {cid: segment_answer(r["answer"]) for cid, r in self.records.items()}
        if len(self.records) != len(snapshot["records"]):
            raise AuditError("duplicate_snapshot_ids")

    def entry(self, chunk_id: str) -> dict:
        if chunk_id not in self.records:
            raise AuditError("candidate_snapshot_mismatch")
        r = self.records[chunk_id]
        if r.get("faq_entry_id") is None or r.get("taxonomy_status") == "ambiguous":
            raise AuditError("unsupported_snapshot_entry")
        return {"snapshot_id": self.snapshot_id, "faq_entry_id": r["faq_entry_id"],
                "chunk_id": chunk_id, "question": r["question"], "answer": r["answer"],
                "main_category": r.get("main_category"), "sub_category": r.get("sub_category"),
                "document_revision": r.get("document_revision"), "content_sha256": r["content_sha256"],
                "redaction_changed": r.get("redaction_changed", False),
                "segmenter_version": SEGMENTER_VERSION, "sentences": self.sentences[chunk_id]}

    def resolve(self, reference: dict, *, allowed_ids=None) -> dict:
        cid = reference["chunk_id"]
        if reference["snapshot_id"] != self.snapshot_id or (allowed_ids is not None and cid not in allowed_ids):
            raise AuditError("invalid_citation")
        entry = self.entry(cid)
        if reference["faq_entry_id"] != entry["faq_entry_id"]:
            raise AuditError("invalid_citation")
        number = reference["sentence_number"]
        if type(number) is not int or not 1 <= number <= len(entry["sentences"]):
            raise AuditError("invalid_citation")
        return entry["sentences"][number - 1]
