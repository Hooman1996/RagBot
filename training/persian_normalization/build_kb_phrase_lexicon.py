#!/usr/bin/env python3
"""Build the answer-free high-confidence Persian phrase lexicon.

The builder reads every valid General_FAQ chunk through the repository's
strict FAQ parser.  Categories and sub-categories are primary evidence;
question text contributes only repeated, explicitly approved banking terms.
Answers are required for source-format validation but are never inspected for
phrase discovery and are never written to the artifact.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.intent_classifier.common import normalize_persian, read_faqs


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FAQ_DIR = ROOT / "data_insertion_chunks/CHUNKS/General_FAQ"
DEFAULT_OUTPUT = (
    ROOT / "training/persian_normalization/kb_phrase_lexicon.json"
)

PERSIAN_LETTERS = (
    "\u0621-\u063a"
    "\u0641-\u064a"
    "\u066e-\u066f"
    "\u0671-\u06d3"
    "\u06fa-\u06fc"
)
PERSIAN_WORD_RE = re.compile(rf"^[{PERSIAN_LETTERS}]+$")
TOKEN_RE = re.compile(rf"[{PERSIAN_LETTERS}]+")

# Question n-grams are admitted only when an operator-reviewable banking term
# is present in the current KB.  This list does not create mappings by itself.
APPROVED_BANKING_TERMS = frozenset(
    {
        "احراز هویت",
        "افتتاح حساب",
        "اطلاعات حساب",
        "شماره حساب",
        "موجودی حساب",
        "مدیریت حساب",
        "حساب وکالتی",
        "حساب بانکی",
        "قرض الحسنه",
        "کوتاه مدت",
        "شماره شبا",
        "انتقال وجه",
        "کارت به کارت",
        "اطلاعات کارت",
        "شماره کارت",
        "صدور کارت",
        "مسدودی کارت",
        "کارت ملی",
        "کد ملی",
        "رمز پویا",
        "رمز عبور",
        "نام کاربری",
        "امضای دیجیتال",
        "سفته الکترونیک",
        "باشگاه مشتریان",
        "کیف پول",
        "کیف کارت",
        "دسته چک",
        "ثبت چک",
        "چک صیادی",
        "سفر فصلی",
        "سفر فصلی من",
        "وضعیت مالی",
        "تسهیلات حمایتی",
        "پرداخت قسط",
        "سرمایه گذاری",
        "پایانه فروش",
        "خدمات خودرو",
        "دعوت از دوستان",
        "مرسوله پستی",
        "شماره همراه",
        "تلفن همراه",
        "کد پستی",
        "ثبت نام",
    }
)

GENERIC_PHRASES = frozenset(
    {
        "چه اقدامی",
        "چه شرایطی",
        "چه زمانی",
        "چگونه می",
        "می توانم",
        "امکان دارد",
        "علت چیست",
        "برای من",
        "در حال",
        "حال حاضر",
    }
)


def _clean_phrase(value: str) -> str:
    value = normalize_persian(value)
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[«»\"'()\[\]{}؟?!.,؛،:]", " ", value)
    return re.sub(r"\s+", " ", value).strip(" .-|/")


def _metadata_segments(value: str) -> list[str]:
    return [
        cleaned
        for part in re.split(r"[|/؛،]+", value)
        if (cleaned := _clean_phrase(part))
    ]


def _safe_shape(phrase: str) -> bool:
    words = phrase.split()
    return (
        2 <= len(words) <= 4
        and phrase not in GENERIC_PHRASES
        and all(len(word) >= 2 and PERSIAN_WORD_RE.fullmatch(word) for word in words)
    )


def _question_ngrams(question: str) -> set[str]:
    words = TOKEN_RE.findall(_clean_phrase(question))
    return {
        " ".join(words[index : index + size])
        for size in (2, 3)
        for index in range(len(words) - size + 1)
    }


def phrase_variants(canonical: str) -> list[str]:
    """Create bounded, reviewable boundary/character variants."""

    words = canonical.split()
    variants = {
        canonical,
        "\u200c".join(words),
        "".join(words),
        "  ".join(words),
    }
    for boundary in range(len(words) - 1):
        for separator in ("", "\u200c", "  "):
            separators = [" "] * (len(words) - 1)
            separators[boundary] = separator
            variants.add(
                "".join(
                    word + (separators[index] if index < len(separators) else "")
                    for index, word in enumerate(words)
                )
            )
    for value in tuple(variants):
        arabic = value.replace("ی", "ي").replace("ک", "ك")
        variants.add(arabic)
    return sorted(variants, key=lambda value: (len(value), value))


def build_lexicon(faq_dir: Path) -> dict:
    faqs, ignored = read_faqs(faq_dir)
    evidence: dict[str, Counter[str]] = defaultdict(Counter)

    for faq in faqs:
        for phrase in _metadata_segments(faq.category):
            evidence[phrase]["category"] += 1
        for phrase in _metadata_segments(faq.sub_category):
            evidence[phrase]["subcategory"] += 1
        for phrase in _question_ngrams(faq.question):
            evidence[phrase]["question"] += 1

    discovered = {
        phrase: counts
        for phrase, counts in evidence.items()
        if _safe_shape(phrase)
        and (
            counts["category"] > 0
            or counts["subcategory"] > 0
            or counts["question"] >= 3
        )
    }

    accepted: dict[str, dict] = {}
    rejected_reasons: Counter[str] = Counter()
    rejected_examples: list[dict] = []
    for phrase, counts in sorted(discovered.items()):
        reason = ""
        confidence = 0.0
        if counts["category"] >= 2:
            confidence = 0.99
        elif counts["subcategory"] >= 3:
            confidence = 0.96
        elif phrase in APPROVED_BANKING_TERMS and counts["question"] >= 1:
            confidence = 0.94
        else:
            reason = "insufficient_high_confidence_evidence"

        if reason:
            rejected_reasons[reason] += 1
            if len(rejected_examples) < 50:
                rejected_examples.append(
                    {"canonical": phrase, "evidence": dict(counts), "reason": reason}
                )
            continue

        sources = [
            source
            for source in ("category", "subcategory", "question")
            if counts[source]
        ]
        accepted[phrase] = {
            "canonical": phrase,
            "variants": phrase_variants(phrase),
            "source": "|".join(sources),
            "frequency": sum(counts.values()),
            "source_frequency": dict(sorted(counts.items())),
            "confidence": confidence,
        }

    # Reject any canonical whose compact/ZWNJ spelling collides with another
    # phrase.  Ambiguous variants must never be resolved by ordering.
    owners: dict[str, set[str]] = defaultdict(set)
    for canonical, entry in accepted.items():
        for variant in entry["variants"]:
            owners[_clean_phrase(variant).replace(" ", "")].add(canonical)
    colliding = {
        canonical
        for variants in owners.values()
        if len(variants) > 1
        for canonical in variants
    }
    for canonical in sorted(colliding):
        entry = accepted.pop(canonical)
        rejected_reasons["variant_collision"] += 1
        if len(rejected_examples) < 50:
            rejected_examples.append(
                {
                    "canonical": canonical,
                    "evidence": entry["source_frequency"],
                    "reason": "variant_collision",
                }
            )

    entries = [accepted[key] for key in sorted(accepted)]
    return {
        "schema_version": 1,
        "source": str(faq_dir.relative_to(ROOT)),
        "statistics": {
            "valid_faq_files": len(faqs),
            **ignored,
            "discovered_candidates": len(discovered),
            "accepted_phrases": len(entries),
            "rejected_candidates": len(discovered) - len(entries),
            "rejected_by_reason": dict(sorted(rejected_reasons.items())),
        },
        "entries": entries,
        "rejected_examples": rejected_examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faq-dir", type=Path, default=DEFAULT_FAQ_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    artifact = build_lexicon(args.faq_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(artifact["statistics"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
