"""Explicit CSV mapping and an event adapter seam for future approved DB input.

Raw mapped content is memory-only. Source IDs use byte identity + record ordinal,
never text deduplication or physical line numbers. No arbitrary source columns
survive import. DB adapters must freeze an ordered selection and map actual
message availability times; latest-state DatabaseManager history is unsuitable.
"""
from __future__ import annotations

from collections import Counter
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import io
import re
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from knowledge_audit.calendar import jalali_date
from knowledge_audit.privacy import AuditError, Redactor
from utils.read_only_audit import canonical_sha256


@dataclass(frozen=True)
class ColumnMapping:
    query: str
    session: str | None = None
    timestamp: str | None = None
    date: str | None = None
    time: str | None = None
    role: str | None = None
    source_query_id: str | None = None

    def validate(self, columns: list[str]) -> None:
        names = [v for v in asdict(self).values() if v is not None]
        if not self.query or len(set(columns)) != len(columns) or any(not c for c in columns):
            raise AuditError("ambiguous_csv_header")
        if len(names) != len(set(names)) or any(n not in columns for n in names):
            raise AuditError("invalid_column_mapping")
        if bool(self.date) != bool(self.time) or (self.timestamp and self.date):
            raise AuditError("invalid_timestamp_mapping")


@dataclass(frozen=True)
class TimestampPolicy:
    calendar: str = "gregorian"
    source_timezone: str | None = None
    authoritative_source_order: bool = False
    parser_version: str = "a1-time-1"

    def __post_init__(self):
        if self.calendar not in {"gregorian", "jalali"}:
            raise AuditError("invalid_calendar")
        if not isinstance(self.authoritative_source_order, bool):
            raise AuditError("invalid_order_policy")
        if self.source_timezone:
            try:
                ZoneInfo(self.source_timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise AuditError("invalid_source_timezone") from None

    def parse(self, value: str) -> tuple[datetime | None, str, dict]:
        provenance = {"parser_version": self.parser_version, "calendar": self.calendar,
                      "source_timezone": self.source_timezone, "offset_seconds": None}
        if not value.strip():
            return None, "missing", provenance
        try:
            if self.calendar == "jalali":
                match = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2})", value.strip())
                if not match:
                    raise AuditError("invalid_timestamp")
                y, m, d, hour, minute, second = map(int, match.groups())
                day = jalali_date(y, m, d)
                parsed = datetime(day.year, day.month, day.day, hour, minute, second)
            else:
                # Explicit ISO-8601; no locale guessing or date-only midnight.
                if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value.strip()):
                    raise AuditError("invalid_timestamp")
                parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                if not self.source_timezone:
                    return None, "unresolved", provenance
                zone = ZoneInfo(self.source_timezone)
                candidates = [parsed.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
                valid = [p for p in candidates if p.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == parsed]
                if not valid:
                    return None, "invalid", provenance
                if len({p.utcoffset() for p in valid}) > 1:
                    return None, "ambiguous", provenance
                parsed = valid[0]
                provenance["timezone_basis"] = "explicit_source_timezone"
            else:
                provenance["timezone_basis"] = "source_offset"
            provenance["offset_seconds"] = int(parsed.utcoffset().total_seconds())
            return parsed.astimezone(timezone.utc), "resolved", provenance
        except (ValueError, OverflowError):
            return None, "invalid", provenance


@dataclass(frozen=True)
class InputEvent:
    source_row_id: str
    ordinal: int
    safe_session_ref: str
    source_query_ref: str
    content: str = field(repr=False)
    role: str
    timestamp: datetime | None
    timestamp_status: str
    time_provenance: dict
    issues: tuple[str, ...] = ()

    @property
    def selected(self) -> bool:
        # Unknown roles retain a validation result; never silently lose rows.
        return self.role == "user" or "invalid_role" in self.issues


@dataclass(frozen=True)
class ImportedDataset:
    input_id: str
    events: tuple[InputEvent, ...]
    structure: dict
    mapping: ColumnMapping
    timestamp_policy: TimestampPolicy

    @property
    def selected(self) -> tuple[InputEvent, ...]:
        return tuple(e for e in self.events if e.selected)

    def processing_order(self) -> tuple[InputEvent, ...]:
        return tuple(sorted(self.selected, key=lambda e: (
            e.timestamp is None, e.timestamp or datetime.max.replace(tzinfo=timezone.utc), e.ordinal)))


class AuditInputAdapter(Protocol):
    """Future DB adapter returns this same immutable, cutoff-capable contract.

    Use approved source/owner filters with existing psycopg2 read-only repeatable
    read patterns; created_at for questions, completed_at for assistant events.
    Require a confirmed timezone for naive DB times and stable source selection
    identity. No new SQL query schema, DB reads or enrichment are implemented.
    """

    def load(self, redactor: Redactor) -> ImportedDataset: ...


class CsvInputAdapter:
    def __init__(self, path, mapping: ColumnMapping, *, policy: TimestampPolicy | None = None,
                 encoding: str = "utf-8-sig", delimiter: str = ","):
        if encoding not in {"utf-8-sig", "utf-8", "utf-16"} or delimiter not in {",", ";", "\t", "|"}:
            raise AuditError("invalid_csv_format")
        self.path, self.mapping = path, mapping
        self.policy = policy or TimestampPolicy()
        self.encoding, self.delimiter = encoding, delimiter

    def load(self, redactor: Redactor) -> ImportedDataset:
        raw = self.path.read_bytes()
        identity = hashlib.sha256(raw).hexdigest()
        try:
            decoded = raw.decode(self.encoding)
            reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=self.delimiter, strict=True)
            columns = next(reader)
            self.mapping.validate(columns)
            events, widths, missing = [], Counter(), Counter()
            for ordinal, row in enumerate(reader, 1):
                widths[len(row)] += 1
                fields = {c: row[i] if i < len(row) else "" for i, c in enumerate(columns)}
                for column, value in fields.items():
                    if not value.strip():
                        missing[column] += 1
                def get(name):
                    return fields[name] if name else ""
                content = get(self.mapping.query)
                role = get(self.mapping.role).strip().lower() if self.mapping.role else "user"
                role = {"ai": "assistant", "model": "assistant"}.get(role, role)
                issues = []
                if len(row) != len(columns):
                    issues.append("invalid_record_width")
                if role not in {"user", "assistant", "system"}:
                    issues.append("invalid_role")
                if not content.strip():
                    issues.append("missing_query" if role == "user" else "missing_message")
                time_value = get(self.mapping.timestamp)
                if self.mapping.date:
                    date_value, clock = get(self.mapping.date), get(self.mapping.time)
                    time_value = f"{date_value} {clock}" if date_value.strip() and clock.strip() else ""
                timestamp, status, provenance = self.policy.parse(time_value)
                if status != "resolved":
                    issues.append("timestamp_" + status)
                session = get(self.mapping.session).strip()
                row_id = "row_" + canonical_sha256([identity, ordinal])[:32]
                session_ref = "session_" + redactor.opaque("session:" + identity, session) if session else ""
                source_query = get(self.mapping.source_query_id).strip()
                events.append(InputEvent(row_id, ordinal, session_ref,
                    "query_" + redactor.opaque("query:" + identity, source_query) if source_query else "",
                    content, role, timestamp, status, provenance, tuple(issues)))
        except (UnicodeError, csv.Error, StopIteration):
            raise AuditError("csv_syntax_or_encoding_error") from None
        structure = {"encoding": "utf-8-bom" if raw.startswith(b"\xef\xbb\xbf") else self.encoding.removesuffix("-sig"),
                     "delimiter": self.delimiter, "columns": columns, "source_row_count": len(events),
                     "selected_row_count": sum(e.selected for e in events),
                     "history_only_row_count": sum(not e.selected for e in events),
                     "record_width_counts": dict(widths), "missing_by_column": {c: missing[c] for c in columns},
                     "timestamp_status_counts": dict(Counter(e.timestamp_status for e in events)),
                     "validation_issue_counts": dict(Counter(i for e in events for i in e.issues))}
        return ImportedDataset(identity, tuple(events), structure, self.mapping, self.policy)
