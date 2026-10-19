"""Private artifact boundary and consistent, conservative redaction.

Regex redaction cannot recognize every name, address, amount or banking fact.
Artifacts remain private and require authorized review before sharing.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import re
import unicodedata

from utils.log_sanitizer import scrub_text
from utils.read_only_audit import canonical_json


class AuditError(ValueError):
    """Only fixed machine codes may cross the diagnostic boundary."""


class Redactor:
    version = "a1-redaction-1"

    def __init__(self, key: bytes):
        if len(key) < 32:
            raise AuditError("invalid_privacy_key")
        self._key = key

    def opaque(self, namespace: str, value: str) -> str:
        digest = hmac.new(self._key, (namespace + "\0" + value).encode(), hashlib.sha256)
        return digest.hexdigest()[:32]

    def text(self, value: str) -> str:
        if len(value) > 32768:
            raise AuditError("redaction_text_limit")
        # Include failed-checksum identifiers, grouped numbers, and labeled PII.
        # Scrub the repository's supported patterns first through a callback so
        # repeated references get the same placeholder, then its final scrub.
        from utils import log_sanitizer as policy
        patterns = (policy._INLINE_SECRET, policy._BEARER, policy._JWT,
                    policy._EMAIL, policy._MOBILE, policy._IBAN, policy._CARD,
                    policy._NATIONAL,
                    re.compile(r"(?<!\w)\d(?:[\d ,،.\-]*\d)?\s*(?:تومان|ریال|rials?)(?!\w)", re.I),
                    re.compile(r"(?<!\w)\d[\d -]{3,}\d(?!\w)"),
                    re.compile(r"(?:نام(?: و نام خانوادگی)?|کد ملی|شماره حساب|رمز)\s*[:=]\s*[^\n,،;]+"))
        result = value
        placeholder = re.compile(r"(\[\s*PRIVATE_[0-9a-f]{12}\s*\])")
        for pattern in patterns:
            result = "".join(part if placeholder.fullmatch(part) else pattern.sub(
                lambda m: "[PRIVATE_" + self.opaque("text", m.group())[:12] + "]", part)
                for part in placeholder.split(result))
        return "".join(part if placeholder.fullmatch(part) else scrub_text(part)
                       for part in placeholder.split(result))

    kb_version = "kb-content-1"

    def kb_text(self, value: str, public_contacts=()) -> str:
        """Bank-published KB content: scrub secrets and validated identifiers only.

        Amounts, limits, dates, landlines, short codes, checksum-failing digit
        runs, allow-listed contacts and form-field instructions are kept.
        """
        if len(value) > 32768:
            raise AuditError("redaction_text_limit")
        from utils import log_sanitizer as policy
        allowed = {normalize_public_contact(c) for c in public_contacts}

        def mask(text):
            return "[PRIVATE_" + self.opaque("text", text)[:12] + "]"

        def email(m):
            address = m.group().lower()
            return m.group() if address in allowed or "@" + address.rsplit("@", 1)[1] in allowed else mask(m.group())

        def mobile(m):
            # _MOBILE also consumes one separator after the last digit; keep it.
            number = m.group().rstrip(" \t\r\n-")
            tail = m.group()[len(number):]
            return m.group() if _phone(number) in allowed else mask(number) + tail

        def labelled(m):
            digits = sum(c.isdigit() for c in m.group("value"))
            return m.group("label") + mask(m.group("value")) if digits >= 8 else m.group()

        rules = ((policy._INLINE_SECRET, None), (policy._BEARER, None), (policy._JWT, None),
                 (policy._EMAIL, email),
                 (policy._MOBILE, mobile),
                 (policy._IBAN, lambda m: mask(m.group()) if _valid_iban(m.group()) else m.group()),
                 (policy._CARD, lambda m: mask(m.group()) if policy._valid_card(m.group()) else m.group()),
                 (policy._NATIONAL, lambda m: mask(m.group()) if policy._valid_national(m.group()) else m.group()),
                 (_KB_LABELLED, labelled))
        result = value
        placeholder = re.compile(r"(\[\s*PRIVATE_[0-9a-f]{12}\s*\])")
        for pattern, keep_or_mask in rules:
            callback = keep_or_mask or (lambda m: mask(m.group()))
            result = "".join(part if placeholder.fullmatch(part) else pattern.sub(callback, part)
                             for part in placeholder.split(result))
        return result


_KB_DIGIT = "0-9۰-۹٠-٩"
_KB_LABELLED = re.compile(rf"(?P<label>(?:کد ملی|شماره حساب|شماره کارت|شبا)\s*[:=]\s*)"
                          rf"(?P<value>(?:IR)?[{_KB_DIGIT}]+(?:[ -][{_KB_DIGIT}]+)*)", re.I)
_PUBLIC_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")
_PUBLIC_DOMAIN = re.compile(r"@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")


def _phone(value: str) -> str:
    from utils.log_sanitizer import _digits
    digits = re.sub(r"[\s-]", "", _digits(value))
    if digits.startswith("+98"):
        return "0" + digits[3:]
    if digits.startswith("0098"):
        return "0" + digits[4:]
    return digits


def normalize_public_contact(entry: str) -> str:
    """One allow-list entry: exact email, @domain, or a normalised phone number."""
    entry = entry.strip()
    if _PUBLIC_EMAIL.fullmatch(entry) or _PUBLIC_DOMAIN.fullmatch(entry):
        return entry.lower()
    phone = _phone(entry)
    if re.fullmatch(r"[0-9]{3,15}", phone):
        return phone
    raise AuditError("invalid_coverage_public_contacts")


def _valid_iban(value: str) -> bool:
    """ISO 13616 mod-97 check after Persian and Arabic digit normalisation."""
    from utils.log_sanitizer import _digits
    iban = re.sub(r"[\s-]", "", _digits(value)).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1


def private_directory(path: Path) -> Path:
    """Require a dedicated owner-only directory outside the repository.

    No symlink traversal, Git/static artifacts, overwrites or permissive parents
    supplied as the output directory. /tmp's sticky parent is acceptable.
    """
    path = path.absolute()
    root = Path(__file__).resolve().parents[1]
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise AuditError("artifact_symlink_forbidden")
    if path == root or root in path.parents:
        raise AuditError("artifact_repository_forbidden")
    if not path.parent.is_dir():
        raise AuditError("artifact_parent_missing")
    if not path.exists():
        path.mkdir(mode=0o700)
    stat = path.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise AuditError("artifact_directory_permissions")
    return path


def private_write(path: Path, data: bytes) -> None:
    private_directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def private_json(path: Path, payload: object) -> None:
    private_write(path, (canonical_json(payload) + "\n").encode("utf-8"))


def formula_safe(value: str) -> str:
    effective = value.lstrip()
    while effective and (effective[0].isspace() or unicodedata.category(effective[0]) in {"Cc", "Cf"}):
        effective = effective[1:]
    if any(c in value[:len(value) - len(effective)] for c in "\t\r\n") or effective[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value
