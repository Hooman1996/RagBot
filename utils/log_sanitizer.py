"""Bounded, recursive sanitization for structured application logs."""

from __future__ import annotations

import hashlib
import json
import hmac
import math
import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
MAX_DEPTH = 8
MAX_ITEMS = 100
MAX_TEXT_CHARS = 32768
_DIGIT = "0-9۰-۹٠-٩"
_SECRET_KEYS = frozenset({
    "password", "passwordhash", "passwd", "authorization", "proxyauthorization",
    "cookie", "setcookie", "csrf", "csrftoken", "token", "accesstoken",
    "refreshtoken", "idtoken", "apikey", "secret", "clientsecret",
    "postgrespassword", "qdrantapikey", "logpiihmacsecret", "websessionsecret",
    "jobaccess",
})
_PII_KEYS = frozenset({
    "nationalcode", "phone", "phonenumber", "mobile", "mobilenumber", "email",
    "username", "fullname", "displayname",
})
_EMAIL = re.compile(r"(?<![\w.@])(?:[A-Za-z0-9._%+-]{1,64})@(?:[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24})(?![\w.@])")
_MOBILE = re.compile(rf"(?<![{_DIGIT}])(?:\+[9۹٩][8۸٨]|[0۰٠][0۰٠][9۹٩][8۸٨]|[0۰٠])[\s-]?[9۹٩](?:[{_DIGIT}][\s-]?){{9}}(?![{_DIGIT}])")
_NATIONAL = re.compile(rf"(?<![{_DIGIT}])[{_DIGIT}]{{10}}(?![{_DIGIT}])")
_CARD = re.compile(rf"(?<![{_DIGIT}])(?:[{_DIGIT}][ -]?){{15}}[{_DIGIT}](?![{_DIGIT}])")
_IBAN = re.compile(rf"(?<![A-Za-z0-9])IR[{_DIGIT}]{{24}}(?![A-Za-z0-9])", re.IGNORECASE)
_JWT = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])")
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*", re.IGNORECASE)
_INLINE_SECRET = re.compile(r"\b(?:password|passwd|api[_-]?key|(?:client|web[_-]?session|log[_-]?pii[_-]?hmac)?[_-]?secret|authorization|cookie|csrf(?:[_-]?token)?|access[_-]?token|refresh[_-]?token|username|full[_-]?name|display[_-]?name|job[_-]?access)\b(?:\\?[\"'])?\s*[:=]\s*(?:Bearer\s+)?(?:\\?\"[^\"]*\"|\\?'[^']*'|[^\s,;}]+)", re.IGNORECASE)
_KEY_NORMALIZE = re.compile(r"[^a-z0-9]")
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _digits(value: str) -> str:
    return value.translate(_PERSIAN_DIGITS)


def _valid_national(value: str) -> bool:
    digits = _digits(value)
    if len(set(digits)) == 1:
        return False
    check = sum(int(digits[i]) * (10 - i) for i in range(9)) % 11
    return int(digits[9]) == (check if check < 2 else 11 - check)


def _valid_card(value: str) -> bool:
    digits = re.sub(r"[ -]", "", _digits(value))
    if len(digits) != 16 or len(set(digits)) == 1:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        number = int(digit)
        if index % 2:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def pseudonymize(value: str, secret: str | None) -> str:
    """Use an independent keyed digest; redact when no logging secret exists."""
    if not secret:
        return REDACTED
    canonical = _digits(value)
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"pii_{digest[:24]}"


def scrub_text(value: str, *, hmac_secret: str | None = None, max_chars: int = MAX_TEXT_CHARS) -> str:
    """Scrub only a bounded prefix; never use an unbounded regex input."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    truncated = len(value) > max_chars
    # Drop the tail of a truncated prefix so partial identifiers do not leak.
    result = value[:max(0, max_chars - 256)] if truncated else value
    if hmac_secret:
        result = result.replace(hmac_secret, REDACTED)
    result = _INLINE_SECRET.sub(REDACTED, result)
    result = _BEARER.sub(REDACTED, result)
    result = _JWT.sub(REDACTED, result)
    result = _EMAIL.sub(REDACTED, result)
    result = _MOBILE.sub(REDACTED, result)
    result = _IBAN.sub(REDACTED, result)
    result = _CARD.sub(lambda m: REDACTED if _valid_card(m.group()) else m.group(), result)
    result = _NATIONAL.sub(
        lambda m: pseudonymize(m.group(), hmac_secret) if _valid_national(m.group()) else m.group(),
        result,
    )
    return result + ("[TRUNCATED]" if truncated else "")


def sanitize(value: Any, *, hmac_secret: str | None = None, max_chars: int = MAX_TEXT_CHARS) -> Any:
    """Return a JSON-safe copy; unknown objects and all binary content are omitted."""
    seen: set[int] = set()
    remaining_chars = max_chars

    def visit(item: Any, depth: int, key: str = "") -> Any:
        if len(key) > 128:
            return REDACTED
        normalized = _KEY_NORMALIZE.sub("", key.lower())
        if normalized in _SECRET_KEYS or normalized.endswith(("password", "apikey", "secret", "csrftoken", "authorization", "cookie", "token")):
            return REDACTED
        if normalized in _PII_KEYS or normalized.endswith(("nationalcode", "phonenumber", "mobilenumber", "email")):
            if item == REDACTED or (isinstance(item, str) and re.fullmatch(r"pii_[0-9a-f]{24}", item)):
                return item
            if normalized.endswith("nationalcode") and isinstance(item, (str, int)):
                return pseudonymize(str(item), hmac_secret)
            return REDACTED
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            return item if math.isfinite(item) else "[NON_FINITE_NUMBER]"
        if isinstance(item, str):
            nonlocal remaining_chars
            if remaining_chars <= 0:
                return "[TRUNCATED]"
            allowance = remaining_chars
            remaining_chars -= min(len(item), allowance)
            return scrub_text(item, hmac_secret=hmac_secret, max_chars=allowance)
        if isinstance(item, (bytes, bytearray, memoryview)):
            return {"binary_omitted": True, "size_bytes": len(item)}
        if depth >= MAX_DEPTH:
            return "[MAX_DEPTH]"
        identity = id(item)
        if identity in seen:
            return "[CYCLE]"
        if isinstance(item, Mapping):
            seen.add(identity)
            try:
                result: dict[str, Any] = {}
                for index, (raw_key, child) in enumerate(item.items()):
                    if index >= MAX_ITEMS:
                        result["items_truncated"] = True
                        break
                    safe_key = scrub_text(raw_key[:128], hmac_secret=hmac_secret, max_chars=128) if isinstance(raw_key, str) else "[NON_STRING_KEY]"
                    result[safe_key] = visit(child, depth + 1, raw_key if isinstance(raw_key, str) else "")
                return result
            finally:
                seen.remove(identity)
        if isinstance(item, (list, tuple)):
            seen.add(identity)
            try:
                result = [visit(child, depth + 1) for child in item[:MAX_ITEMS]]
                if len(item) > MAX_ITEMS:
                    result.append("[ITEMS_TRUNCATED]")
                return result
            finally:
                seen.remove(identity)
        return "[UNSERIALIZABLE]"

    return visit(value, 0)


def sanitize_body(body: Any, *, max_bytes: int = 32768, hmac_secret: str | None = None,
                  original_size_bytes: int | None = None) -> dict[str, Any]:
    """Prepare a body already bounded by the caller; binary data is metadata only."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if isinstance(body, (bytes, bytearray, memoryview)):
        return {"body": {"binary_omitted": True, "size_bytes": len(body)}}
    if isinstance(body, str):
        # Character count is a cheap lower bound on UTF-8 byte size. A caller
        # may supply the original byte size from its already-bounded read.
        if len(body) > max_bytes:
            return {"body": "[TRUNCATED]", "body_truncated": True,
                    "original_size_bytes": original_size_bytes}
        size = len(body.encode("utf-8"))
        truncated = size > max_bytes
        return {
            # Do not emit a partial secret cut at the byte boundary.
            "body": "[TRUNCATED]" if truncated else scrub_text(body, hmac_secret=hmac_secret, max_chars=max_bytes),
            "body_truncated": truncated,
            "original_size_bytes": original_size_bytes if original_size_bytes is not None else size,
        }
    safe = sanitize(body, hmac_secret=hmac_secret, max_chars=max_bytes)
    serialized_size = len(json.dumps(safe, ensure_ascii=False).encode("utf-8"))
    if serialized_size > max_bytes:
        return {"body": "[TRUNCATED]", "body_truncated": True,
                "original_size_bytes": original_size_bytes}
    return {"body": safe, "body_truncated": False,
            "original_size_bytes": original_size_bytes}
