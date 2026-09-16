"""Content-free evaluation error-code validation."""

from __future__ import annotations

import re


_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


def safe_error_code(value: object, *, fallback: str = "EVALUATION_ERROR") -> str:
    candidate = str(value or "").upper()
    return candidate if _SAFE_CODE.fullmatch(candidate) else fallback
