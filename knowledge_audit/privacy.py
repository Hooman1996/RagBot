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
