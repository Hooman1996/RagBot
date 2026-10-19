"""Deterministic guard: a ticket referral is evidence only for a contact question.

The prompt asks the model to apply this rule; the code enforces it, so the same
model cannot accept "please submit a ticket" as the answer to a fee question.
"""
import re

from knowledge_audit.evidence import segment_answer
from utils.faq_fallback import FAQ_FALLBACK_FRAGMENT
from utils.persian_normalization import normalize_persian_text

VERSION = "referral-guard-1"


def normalized(text) -> str:
    return normalize_persian_text(str(text or "")).lower()


def _phrase(text):
    # Words of a phrase may be separated by any run of spaces or half-spaces.
    return re.compile(r"[\s‌]+".join(re.escape(word) for word in normalized(text).split()))


# The whole fallback and each of its sentences, because a citation points at
# one sentence of an entry that may repeat the fallback text.
_FALLBACK = (FAQ_FALLBACK_FRAGMENT,) + tuple(
    s["text"] for s in segment_answer(FAQ_FALLBACK_FRAGMENT) if s["text"].strip())

# Longer phrases come first, so deleting matches removes each one whole.
REFERRAL_PATTERNS = tuple(_phrase(p) for p in dict.fromkeys(_FALLBACK + (
    "اقدام به ثبت تیکت", "ثبت تیکت", "تیکت ثبت کن",
    "با پشتیبانی تماس بگیرید", "به پشتیبانی پیام دهید", "از طریق پشتیبانی",
    "submit a ticket", "open a ticket", "contact customer support", "contact support",
)))

SUBSTANCE = re.compile(
    r"[0-9۰-۹٠-٩]"
    r"|ریال|تومان|rial"
    r"|روز|ساعت|دقیقه|هفته|ماه|day|hour|minute|week|month"
    r"|سقف|حداقل|حداکثر|کارمزد|هزینه|fee|limit|minimum|maximum"
    r"|شرط|شرایط|مشمول|eligible|condition")

SUBSTANTIVE_ASPECT = re.compile(
    r"کارمزد|هزینه|مبلغ|سقف|حداقل|حداکثر|مدت|زمان|چقدر|چند|روز|ساعت|شرایط|شرط|مشمول|نرخ|سود|درصد"
    r"|fee|cost|amount|limit|minimum|maximum|how long|how much|duration|time|days?|hours?"
    r"|eligib|condition|requirement|rate|interest|percent")

CONTACT_ASPECT = re.compile(r"تیکت|پشتیبانی|تماس|ارتباط|شکایت|اعتراض|ticket|support|contact|complain|reach")


def is_referral_only(sentence) -> bool:
    """True when the sentence refers to a ticket or support and states no fact."""
    text = normalized(sentence)
    if not any(p.search(text) for p in REFERRAL_PATTERNS):
        return False
    for pattern in REFERRAL_PATTERNS:
        text = pattern.sub(" ", text)
    return not SUBSTANCE.search(text)


def classify_aspect(aspect) -> str:
    description = normalized(aspect.get("description"))
    if SUBSTANTIVE_ASPECT.search(description):
        return "substantive_fact"
    if CONTACT_ASPECT.search(description):
        return "contact_procedure"
    return "unclassified"
