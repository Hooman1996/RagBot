"""Cached, KB-derived restoration of known Persian multi-word phrases."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Final


ZWNJ: Final = "\u200c"
_PERSIAN_LETTERS: Final = (
    "\u0621-\u063a"
    "\u0641-\u064a"
    "\u066e-\u066f"
    "\u0671-\u06d3"
    "\u06fa-\u06fc"
)
DEFAULT_LEXICON_PATH: Final = (
    Path(__file__).resolve().parents[1]
    / "training/persian_normalization/kb_phrase_lexicon.json"
)


def _prepare_variant(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"}))
    return re.sub(r"\s+", " ", value).strip()


class KBPhraseNormalizer:
    """Immutable normalizer compiled once from the generated KB artifact."""

    def __init__(self, artifact_path: Path = DEFAULT_LEXICON_PATH):
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("Unsupported KB phrase lexicon schema")

        variant_map: dict[str, str] = {}
        for entry in payload.get("entries", []):
            canonical = _prepare_variant(entry["canonical"]).replace(ZWNJ, " ")
            for raw_variant in entry["variants"]:
                variant = _prepare_variant(raw_variant)
                owner = variant_map.setdefault(variant, canonical)
                if owner != canonical:
                    raise ValueError(
                        f"Ambiguous KB phrase variant {variant!r}: "
                        f"{owner!r} versus {canonical!r}"
                    )

        self.artifact_path = artifact_path
        self.statistics = dict(payload.get("statistics", {}))
        self.phrase_count = len(payload.get("entries", []))
        self._variants = variant_map
        alternatives = sorted(
            (re.escape(value) for value in variant_map),
            key=len,
            reverse=True,
        )
        self._pattern = (
            re.compile(
                rf"(?<![{_PERSIAN_LETTERS}])(?:{'|'.join(alternatives)})"
                rf"(?![{_PERSIAN_LETTERS}])"
            )
            if alternatives
            else None
        )

    def normalize(self, text: str) -> str:
        """Restore only lexicon-approved phrases; never segment unknown words."""

        if not text or self._pattern is None:
            return text
        return self._pattern.sub(
            lambda match: self._variants[match.group(0)], text
        )


KB_PHRASE_NORMALIZER: Final = KBPhraseNormalizer()


def normalize_kb_phrases(text: str) -> str:
    return KB_PHRASE_NORMALIZER.normalize(text)


__all__ = [
    "DEFAULT_LEXICON_PATH",
    "KBPhraseNormalizer",
    "KB_PHRASE_NORMALIZER",
    "normalize_kb_phrases",
]
