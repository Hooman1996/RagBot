"""Deterministic, dependency-light Persian text normalization.

The displayed/raw user text must remain separate from this retrieval-oriented
representation.  The rules here intentionally address orthographic variance;
they are not a stemmer, spell checker, or semantic query rewriter.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from utils.persian_query_normalizer import normalize_kb_phrases


ZWNJ = "\u200c"

_PERSIAN_LETTERS = (
    "\u0621-\u063a"
    "\u0641-\u064a"
    "\u066e-\u066f"
    "\u0671-\u06d3"
    "\u06fa-\u06fc"
)
_STEM = rf"[{_PERSIAN_LETTERS}]{{2,}}"

_CHARACTER_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "\u200d": ZWNJ,  # ZWJ is a frequent accidental half-space substitute.
        "\u200e": "",
        "\u200f": "",
        "\u202a": "",
        "\u202b": "",
        "\u202c": "",
        "\u202d": "",
        "\u202e": "",
        "\u2060": "",
        "\ufeff": "",
    }
)

_PLURAL_OBJECT_RE = re.compile(
    rf"(?<![{_PERSIAN_LETTERS}])"
    rf"(?P<stem>{_STEM})[ {ZWNJ}]*ها[ {ZWNJ}]*(?:رو|را)"
    rf"(?![{_PERSIAN_LETTERS}])"
)
_PLURAL_Y_RE = re.compile(
    rf"(?<![{_PERSIAN_LETTERS}])"
    rf"(?P<stem>{_STEM})[ {ZWNJ}]*های"
    rf"(?![{_PERSIAN_LETTERS}])"
)
_PLURAL_HA_RE = re.compile(
    rf"(?<![{_PERSIAN_LETTERS}])"
    rf"(?P<stem>{_STEM})[ {ZWNJ}]*ها"
    rf"(?![{_PERSIAN_LETTERS}])"
)
_MI_BECOME_RE = re.compile(
    rf"(?<![{_PERSIAN_LETTERS}])می[ {ZWNJ}]*(?:شه|شود)"
    rf"(?![{_PERSIAN_LETTERS}])"
)
_PLURAL_NAMING_QUESTION_RE = re.compile(
    rf"^اسم\s+(?P<stem>{_STEM})[ {ZWNJ}]*ها\s+"
    rf"(?:چیست|چیه)\s*[؟?]?$"
)
_REPEATED_ZWNJ_RE = re.compile(rf"[ {ZWNJ}]*{ZWNJ}[ {ZWNJ}]*")
_WHITESPACE_RE = re.compile(r"\s+")

# Do not split lexical words that merely end in the letters ``ها``.
_NON_PLURAL_WORDS = frozenset({"تنها"})


def _normalize_unicode_spaces(value: str) -> str:
    """Map Unicode separator characters and ordinary whitespace to ASCII space."""

    return "".join(
        " "
        if character.isspace()
        or unicodedata.category(character) in {"Zs", "Zl", "Zp"}
        else character
        for character in value
    )


def _canonical_plural_object(match: re.Match[str]) -> str:
    stem = match.group("stem")
    original_word = f"{stem}ها"
    if original_word in _NON_PLURAL_WORDS:
        return match.group(0)
    # This is a retrieval representation, not a spelling recommendation.  The
    # deployed embedding/index pair measurably retrieves the intended FAQ for
    # this generic colloquial segmentation and not for the other equivalent
    # suffix layouts.  ``رو`` is changed only inside an unambiguous plural-object
    # construction; standalone ``رو`` is deliberately untouched.
    return f"{stem} هارو"


def _canonical_plural(match: re.Match[str], suffix: str) -> str:
    stem = match.group("stem")
    original_word = f"{stem}{suffix}"
    if original_word in _NON_PLURAL_WORDS:
        return match.group(0)
    return f"{stem}{ZWNJ}{suffix}"


def _canonical_plural_naming_question(match: re.Match[str]) -> str:
    """Canonicalize the narrow ``name of plural X`` interrogative pattern."""

    return f"اسم {match.group('stem')} هارو بگی"


def normalize_persian_orthography(text: object) -> str:
    """Normalize general Persian orthography without domain phrase repair.

    The function is stateless, thread-safe, and linear for ordinary inputs.  It
    preserves digits, URLs, account/card numbers, Latin identifiers, and all
    punctuation.  It does not perform stemming, typo correction, or global
    colloquial-to-formal rewriting.
    """

    if text is None:
        return ""

    value = unicodedata.normalize("NFKC", str(text))
    value = value.translate(_CHARACTER_TRANSLATION)
    value = _normalize_unicode_spaces(value)
    value = _REPEATED_ZWNJ_RE.sub(ZWNJ, value)
    value = _WHITESPACE_RE.sub(" ", value).strip()

    value = _MI_BECOME_RE.sub("میشه", value)
    value = _PLURAL_NAMING_QUESTION_RE.sub(
        _canonical_plural_naming_question, value
    )
    value = _PLURAL_OBJECT_RE.sub(_canonical_plural_object, value)
    value = _PLURAL_Y_RE.sub(
        lambda match: _canonical_plural(match, "های"), value
    )
    value = _PLURAL_HA_RE.sub(
        lambda match: _canonical_plural(match, "ها"), value
    )
    return _WHITESPACE_RE.sub(" ", value).strip()


def normalize_persian_text(text: object) -> str:
    """Return the canonical model/retrieval representation.

    General Unicode, character, whitespace, and suffix rules run first.  The
    generated KB lexicon then restores only approved domain phrase boundaries.
    """

    return normalize_kb_phrases(normalize_persian_orthography(text))


def query_fingerprint(text: object) -> str:
    """Return a bounded content fingerprint for privacy-conscious tracing."""

    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


__all__ = [
    "ZWNJ",
    "normalize_persian_orthography",
    "normalize_persian_text",
    "query_fingerprint",
]
