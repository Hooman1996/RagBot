"""Historical event replay; no latest-state summaries and no fabricated replies."""
from dataclasses import dataclass

from conversation_history import canonical_history_messages, trim_agent_messages
from knowledge_audit.inputs import ImportedDataset, InputEvent
from knowledge_audit.privacy import Redactor
from utils.read_only_audit import canonical_sha256


@dataclass(frozen=True)
class HistoricalContext:
    messages: tuple[dict, ...]
    provenance: dict


class AuditHistoryProvider:
    namespace = "knowledge_audit"

    def __init__(self, dataset: ImportedDataset, redactor: Redactor):
        self.dataset, self.redactor = dataset, redactor

    def before(self, current: InputEvent) -> HistoricalContext:
        """The current event is the explicit cutoff, including its row identity."""
        peers = [e for e in self.dataset.events if current.safe_session_ref and e.safe_session_ref == current.safe_session_ref
                 and e.source_row_id != current.source_row_id]
        unresolved = any(e.timestamp is None for e in peers)
        ties = [e for e in peers if current.timestamp is not None and e.timestamp == current.timestamp]
        authoritative = self.dataset.timestamp_policy.authoritative_source_order
        prior = []
        for event in peers:
            if event.role not in {"user", "assistant"} or not event.content.strip() or any(
                i in event.issues for i in ("invalid_record_width", "invalid_role")):
                continue
            if current.timestamp is not None and event.timestamp is not None:
                precedes = event.timestamp < current.timestamp or (
                    authoritative and event.timestamp == current.timestamp and event.ordinal < current.ordinal)
            else:
                precedes = authoritative and event.ordinal < current.ordinal
            if precedes:
                prior.append(event)
        # With unknown times an explicitly trusted source sequence is the only
        # ordering that can establish chronology, including mixed known times.
        if authoritative and (current.timestamp is None or unresolved):
            prior.sort(key=lambda e: e.ordinal)
        else:
            prior.sort(key=lambda e: (e.timestamp, e.ordinal))
        # Ties anywhere in the used history also make conversational order
        # uncertain; a stable CSV ordinal is not verified chronology.
        used_tie = len({e.timestamp for e in prior}) != len(prior)
        ambiguous = bool(ties or used_tie) and not authoritative
        messages = trim_agent_messages(canonical_history_messages([
            {"role": e.role, "content": self.redactor.text(e.content)} for e in prior]))
        status = "ambiguous" if ambiguous else "incomplete" if unresolved else (
            "user_only" if messages and all(m["role"] == "user" for m in messages) else
            "incomplete" if messages else "unavailable")
        return HistoricalContext(tuple(messages), {
            "history_status": status, "cutoff_row_id": current.source_row_id,
            "cutoff_timestamp": current.timestamp.isoformat() if current.timestamp else None,
            "same_session_only": True, "equal_timestamp_event_count": len(ties),
            "prior_order_ambiguous": ambiguous, "unresolved_peer_times": unresolved,
            "ordering_basis": "confirmed_source_sequence" if authoritative else "timestamp_then_unverified_ordinal",
            "excluded_equal_timestamp_ids": [e.source_row_id for e in ties] if not authoritative else [],
            "history_row_ids": [e.source_row_id for e in prior][-10:],
            "history_digest": canonical_sha256(messages), "state_message_limit": 10,
            "history_redaction_changed": any(self.redactor.text(e.content) != e.content for e in prior),
            "rewrite_message_limit": 6, "capture_completeness": "not_verified",
        })
