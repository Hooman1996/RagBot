#!/usr/bin/env python3
"""Build a deterministic, answer-free Persian adversarial intent dataset.

The generator is deliberately local and template-driven: it never calls a live
application service, reads credentials, or invents banking facts. Banking
examples remain anchored to the exact source FAQ question; answers are parsed
only so source integrity can be checked and are never written to any dataset.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from training.intent_classifier.common import (
    FAQ,
    LABEL_BANKING,
    LABEL_NONBANKING,
    REQUIRED_COLUMNS,
    deduplicate_rows,
    grouped_split,
    normalize_persian,
    read_faqs,
    stable_id,
    validate_dataset,
    write_csv,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FAQ_DIR = ROOT / "data_insertion_chunks/CHUNKS/General_FAQ"
DEFAULT_DATA_DIR = ROOT / "training/intent_classifier/data"
DEFAULT_REPORT = ROOT / "training/intent_classifier/reports/dataset_summary.md"
DEFAULT_INVENTORY = ROOT / "docs/intent_classifier/02-banking-intent-inventory.md"


def clean_question(question: str) -> str:
    return re.sub(r"\s+", " ", question).strip().strip(":؛، ").rstrip("؟?!.")


def colloquialize(question: str) -> str:
    value = clean_question(question)
    replacements = (
        (r"^چگونه\s+", "چطور "),
        (r"^به چه صورت\s+", "چطور "),
        (r"^آیا\s+", "می‌خواستم بدونم آیا "),
        (r"\bمی[‌ ]توانم\b", "می‌تونم"),
        (r"\bمی[‌ ]تواند\b", "می‌تونه"),
        (r"\bنمی[‌ ]شود\b", "نمیشه"),
        (r"\bمی[‌ ]شود\b", "میشه"),
        (r"\bچیست\b", "چیه"),
        (r"\bکدام\b", "کدوم"),
        (r"\bنمایم\b", "کنم"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    return value + "؟"


def formal_rephrase(question: str) -> str:
    value = clean_question(question)
    replacements = (
        (r"^چطور\s+", "چگونه "),
        (r"^چرا\s+", "به چه دلیل "),
        (r"^کی\s+", "چه زمانی "),
        (r"\bمی‌تونم\b", "می‌توانم"),
        (r"\bمیشه\b", "امکان دارد"),
        (r"\bچیه\b", "چیست"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    return value + "؟"


def typo_variants(question: str) -> list[str]:
    plain = clean_question(question).replace("\u200c", " ")
    arabic_chars = plain.replace("ی", "ي", 1).replace("ک", "ك", 1)
    compact = re.sub(r"\s+", " ", plain).replace("می ", "می", 1)
    return [plain, arabic_chars if arabic_chars != plain else compact]


ORTHOGRAPHIC_TRAINING_PHRASES = (
    "احراز هویت",
    "افتتاح حساب",
    "شماره حساب",
    "قرض الحسنه",
    "سفر فصلی",
    "کارت به کارت",
    "باشگاه مشتریان",
    "انتقال وجه",
    "رمز عبور",
    "نام کاربری",
)

def phrase_spacing_variants(text: str, phrase: str) -> list[str]:
    """Create bounded training-only boundary errors for a known phrase."""

    words = phrase.split()
    if len(words) < 2:
        return []
    pattern = re.compile(r"[ \u200c]+".join(map(re.escape, words)))
    if not pattern.search(text):
        return []
    return [
        pattern.sub("".join(words), text, count=1),
        pattern.sub("\u200c".join(words), text, count=1),
        pattern.sub("  ".join(words), text, count=1),
    ]


def _banking_row(
    faq: FAQ,
    text: str,
    example_type: str,
    difficulty: str,
    family: str,
) -> dict[str, Any]:
    return {
        "text": text.strip(),
        "label": LABEL_BANKING,
        "example_type": example_type,
        "difficulty": difficulty,
        "source_question_id": faq.source_question_id,
        "source_question": faq.question,
        "category": faq.category,
        "sub_category": faq.sub_category,
        "generation_family": family,
        "split": "",
    }


def banking_examples(faq: FAQ) -> list[dict[str, Any]]:
    q = faq.question.strip()
    q_clean = clean_question(q)
    colloquial = colloquialize(q)
    formal = formal_rephrase(q)
    subject = faq.sub_category or faq.category.rstrip(".")
    candidates = [
        (q, "original_banking", "easy", "source"),
        (formal, "banking_paraphrase", "easy", "formal"),
        (colloquial, "banking_paraphrase", "medium", "colloquial"),
        (f"لطفاً درباره این موضوع راهنمایی کنید: {q}", "banking_paraphrase", "easy", "polite"),
        (f"می‌خواستم در مورد «{subject}» بدونم؛ {colloquial}", "banking_paraphrase", "medium", "subject_context"),
        (f"این مورد در های‌بانک برام پیش اومده: {q}", "contextual_variant", "medium", "hibank_context"),
        (f"در بخش {faq.category.rstrip('.')} یک سؤال دارم؛ {q}", "contextual_variant", "medium", "category_context"),
        (f"ممکنه خیلی ساده توضیح بدید {colloquial}", "indirect_variant", "medium", "explanation_request"),
        (f"برای «{subject}» گیر کردم؛ {q_clean}", "short_variant", "hard", "short_subject"),
    ]
    for index, variant in enumerate(typo_variants(q)):
        candidates.append((variant, "typo_variant", "hard", f"typo_{index + 1}"))
    for phrase in ORTHOGRAPHIC_TRAINING_PHRASES:
        variants = phrase_spacing_variants(q, phrase)
        for index, variant in enumerate(variants):
            candidates.append(
                (
                    variant,
                    "typo_variant",
                    "hard",
                    f"phrase_spacing:{normalize_persian(phrase)}:{index + 1}",
                )
            )
    candidates.extend(
        [
            (f"یه سؤال بانکی داشتم، {colloquial}", "conversational_variant", "medium", "casual"),
            (f"اگر وقت دارید راهنمایی‌ام کنید؛ {q}", "conversational_variant", "medium", "soft_request"),
            (f"سلام وقت بخیر، یه سؤال کوچیک داشتم: {q}", "hard_negative", "hard", "greeting_banking"),
            (f"ممنون از کمکتون؛ فقط سوالم اینه: {q_clean}؟", "hard_negative", "hard", "thanks_banking"),
            (f"ببخشید مزاحم شدم؛ مسئله‌ام اینه: {q_clean}؟", "hard_negative", "hard", "apology_banking"),
            (f"خسته شدم و اعصابم خورده؛ لطفاً بگید {colloquial}", "hard_negative", "hard", "emotion_banking"),
            (f"سلام خوبی؟ دستیار جان می‌تونی کمکم کنی بفهمم {colloquial}", "hard_negative", "hard", "meta_banking"),
            (f"داشتم با دوستم حرف می‌زدم که یادم افتاد اینو بپرسم؛ {q}", "hard_negative", "hard", "story_banking"),
        ]
    )
    return [
        _banking_row(faq, text, example_type, difficulty, f"banking:{family}")
        for text, example_type, difficulty, family in candidates
    ]


CHAT_GREETINGS = (
    "سلام", "درود", "صبح بخیر", "عصر بخیر", "شب بخیر", "سلام رفیق",
    "وقت بخیر", "سلام دستیار", "روزت بخیر", "خسته نباشی",
)
CHAT_TAILS = (
    "حالت چطوره؟", "چه خبر؟", "امروز خوبی؟", "روزت چطور بود؟",
    "خوشحالم می‌بینمت", "امیدوارم حالت عالی باشه", "فعلاً خداحافظ",
    "ممنون که هستی", "یه کم باهام حرف می‌زنی؟", "حوصله‌ام سر رفته",
    "برام یه لطیفه می‌گی؟", "می‌خوام گپ بزنیم", "تو خیلی مهربونی",
    "اسم تو چیه؟", "تو رباتی؟", "چه کارهایی بلدی؟", "خسته می‌شی؟",
)
CHAT_CONTEXTS = (
    "امروز روز شلوغی داشتم", "کمی ناراحتم", "خیلی خوشحالم", "دلم گرفته",
    "امروز تولدمه", "تازه از سر کار برگشتم", "خوابم نمی‌بره",
    "یک خبر خوب شنیدم", "دلم می‌خواد درد دل کنم", "امروز هوا دلگیره",
    "کمی استرس دارم", "از تنهایی خسته شدم", "امروز انرژی زیادی دارم",
)

NONBANKING_ENTITIES = {
    "برنامه‌نویسی": ("پایتون", "جاوااسکریپت", "گیت", "لینوکس", "Docker", "FastAPI", "SQL", "React"),
    "علم": ("سیاه‌چاله", "نسبیت", "اتم", "ژن", "نور", "گرانش", "کوانتوم", "اقلیم"),
    "پزشکی": ("سردرد", "آلرژی", "ویتامین دی", "فشار خون", "خواب", "کمردرد", "تب", "میگرن"),
    "ورزش": ("فوتبال", "والیبال", "شنا", "دویدن", "بدنسازی", "تنیس", "بسکتبال", "کوهنوردی"),
    "آشپزی": ("قرمه‌سبزی", "کیک", "پاستا", "سوپ", "نان", "قهوه", "برنج", "سالاد"),
    "سفر": ("شیراز", "تبریز", "کیش", "استانبول", "رم", "توکیو", "کویر", "جنگل"),
    "هنر": ("نقاشی", "عکاسی", "موسیقی", "سینما", "خوشنویسی", "تئاتر", "شعر", "معماری"),
    "آموزش": ("زبان انگلیسی", "ریاضی", "فیزیک", "کنکور", "دانشگاه", "مطالعه", "حافظه", "ارائه"),
    "فناوری": ("گوشی", "لپ‌تاپ", "هوش مصنوعی", "پرینتر", "بلوتوث", "اندروید", "ابر", "ربات"),
    "طبیعت": ("گربه", "سگ", "کاکتوس", "ارکیده", "پرنده", "آکواریوم", "باغچه", "زنبور"),
    "سرگرمی": ("شطرنج", "بازی رایانه‌ای", "فیلم کمدی", "رمان", "پادکست", "گیتار", "جدول", "انیمیشن"),
    "جامعه": ("تاریخ ایران", "جغرافیا", "انتخابات", "فلسفه", "روان‌شناسی", "محیط زیست", "زبان‌شناسی", "حقوق شهروندی"),
    "خودرو": ("موتور خودرو", "لاستیک", "روغن موتور", "باتری خودرو", "ترمز", "گیربکس", "کولر ماشین", "چراغ خودرو"),
    "کار": ("رزومه", "مصاحبه شغلی", "دورکاری", "مدیریت زمان", "جلسه کاری", "ایمیل اداری", "ارائه شغلی", "یادگیری مهارت"),
}
NONBANKING_QUESTIONS = (
    "درباره {entity} یک توضیح ساده می‌دی؟",
    "چطور اطلاعات بیشتری درباره {entity} پیدا کنم؟",
    "مزایا و معایب {entity} چیه؟",
    "اگر تازه با {entity} آشنا شده باشم، چه نکاتی را باید بدانم؟",
    "چند منبع خوب برای شناخت {entity} معرفی می‌کنی؟",
    "فرق {entity} با موضوعات مشابهش چیه؟",
    "چه اشتباه‌های رایجی درباره {entity} وجود داره؟",
    "کاربردهای اصلی {entity} چیست؟",
    "برای تحقیق درباره {entity} از کجا شروع کنم؟",
    "چطور منبع معتبر درباره {entity} را تشخیص بدهم؟",
    "تازه‌ترین پیشرفت‌های مرتبط با {entity} را کجا دنبال کنم؟",
    "یک معرفی کوتاه و غیرفنی از {entity} می‌گی؟",
)
NONBANKING_STYLES = (
    "{q}",
    "سلام، یک سؤال غیربانکی دارم؛ {q}",
    "راستی میشه بپرسم {q}",
    "لطفاً کمکم کن: {q}",
    "این پرسش درباره بانک نیست: {q}",
    "برای اطلاعات عمومی می‌پرسم، {q}",
    "اگر ممکنه کوتاه راهنمایی کن؛ {q}",
    "مدتیه کنجکاوم بدونم {q}",
)

COLLISIONS = {
    "account": {
        "entities": ("اینستاگرام", "گیت‌هاب", "گوگل", "تلگرام", "بازی آنلاین", "سایت دانشگاه", "سامانه کتابخانه", "فروشگاه اینترنتی", "شبکه اجتماعی", "انجمن برنامه‌نویسی", "سرویس ایمیل", "پلتفرم موسیقی", "ویندوز", "اپل", "سامانه مدرسه", "سرویس پخش فیلم"),
        "templates": (
            "چرا حساب کاربری {entity} من مسدود شده؟", "چطور حساب {entity} را بازیابی کنم؟",
            "حساب کاربری {entity} را چطور حذف کنم؟", "چرا وارد حساب {entity} نمی‌شوم؟",
            "ایمیل حساب {entity} را چطور تغییر بدهم؟", "چطور حساب دوم در {entity} بسازم؟",
        ),
    },
    "card": {
        "entities": ("گرافیک", "حافظه", "صدا", "شبکه", "کپچر", "ملی", "دانشجویی", "ورود شرکت", "مترو", "بازی", "ویزیت", "کسب‌وکار", "کتابخانه", "عضویت باشگاه", "پایان خدمت", "سلامت"),
        "templates": (
            "چرا کارت {entity} من درست کار نمی‌کند؟", "برای تهیه یا تعویض کارت {entity} چه کار کنم؟",
            "درباره کارت {entity} و کاربردش توضیح می‌دهی؟", "چطور مشخصات کارت {entity} را بررسی کنم؟",
            "فرق کارت {entity} با نمونه‌های مشابه چیست؟", "مشکل کارت {entity} را چطور عیب‌یابی کنم؟",
        ),
    },
    "password": {
        "entities": ("وای‌فای", "ایمیل", "لپ‌تاپ", "ویندوز", "گیت‌هاب", "گوشی", "مودم", "اینستاگرام", "بازی", "پنل سایت", "فایل PDF", "تلگرام", "پرینتر", "فضای ابری", "اکانت اپل", "سامانه دانشگاه"),
        "templates": (
            "رمز {entity} را چطور عوض کنم؟", "رمز {entity} یادم رفته، چیکار کنم؟",
            "چرا رمز {entity} تأیید نمی‌شود؟", "چطور برای {entity} رمز امن بسازم؟",
            "رمز دومرحله‌ای {entity} را چطور فعال کنم؟", "چرا پیام بازیابی رمز {entity} نمی‌رسد؟",
        ),
    },
    "transfer": {
        "entities": ("فایل به گوشی", "عکس به لپ‌تاپ", "دامنه سایت", "مالکیت خودرو", "داده به سرور", "مخاطبان گوشی", "پروژه گیت", "ویدئو به حافظه", "بازی به کنسول", "شماره تلفن", "سند خودرو", "پوشه به فضای ابری", "موسیقی به پخش‌کننده", "نسخه پشتیبان", "مالکیت سیم‌کارت", "کتاب الکترونیکی"),
        "templates": (
            "انتقال {entity} چرا انجام نمی‌شود؟", "برای انتقال {entity} چه روشی بهتره؟",
            "انتقال {entity} وسط کار متوقف شده، چیکار کنم؟", "چطور وضعیت انتقال {entity} را بررسی کنم؟",
            "برای انتقال {entity} چه ابزار یا مدارکی لازم است؟", "مشکل انتقال {entity} را چطور رفع کنم؟",
        ),
    },
    "verification": {
        "entities": ("اینستاگرام", "گیت‌هاب", "گوگل", "ایمیل", "سایت دانشگاه", "بازی آنلاین", "شبکه اجتماعی", "فروشگاه اینترنتی", "سامانه آموزشی", "حساب توسعه‌دهنده", "پلتفرم ویدئو", "اپلیکیشن کاری", "حساب اپل", "سامانه بیمه", "پنل فریلنسری", "سایت کاریابی"),
        "templates": (
            "احراز هویت {entity} چرا رد می‌شود؟", "برای تأیید هویت در {entity} چه مدرکی لازم است؟",
            "کد تأیید {entity} چرا نمی‌رسد؟", "تأیید دومرحله‌ای {entity} را چطور خاموش کنم؟",
            "چرا عکس هویتی من در {entity} قبول نمی‌شود؟", "فرایند وریفای {entity} چقدر طول می‌کشد؟",
        ),
    },
    "blocked": {
        "entities": ("سیم‌کارت", "سایت", "آدرس IP", "ایمیل", "بازی آنلاین", "حساب اینستاگرام", "نرم‌افزار", "شماره تلفن", "کانال", "فایل", "دسترسی ویندوز", "اکانت گیت‌هاب", "دامنه اینترنتی", "حساب گوگل", "درگاه دانشگاه", "اکانت بازی"),
        "templates": (
            "چرا {entity} من مسدود شده؟", "برای رفع مسدودی {entity} چه کار کنم؟",
            "از کجا بفهمم {entity} بلاک شده؟", "مسدودی {entity} چقدر طول می‌کشد؟",
            "چطور درخواست بازبینی مسدودی {entity} بدهم؟", "بعد از مسدود شدن {entity} اطلاعاتم برمی‌گردد؟",
        ),
    },
}
COLLISION_STYLES = (
    "{q}", "سلام، {q}", "لطفاً راهنمایی کن؛ {q}", "خیلی کلافه شدم، {q}",
    "یه سؤال دارم: {q}", "ممنون میشم بگی {q}", "دستیار جان، {q}",
    "این موضوع بانکی نیست؛ {q}", "برای یک سرویس غیربانکی می‌پرسم: {q}",
    "منظورم هیچ حساب بانکی‌ای نیست؛ {q}", "این مشکل مربوط به اینترنت و نرم‌افزاره: {q}",
    "یه راهنمایی عمومی لازم دارم؛ {q}", "سؤالم درباره خدمات های‌بانک نیست: {q}",
    "قبل از هر چیز بگم موضوع مالی نیست؛ {q}", "در یک زمینه کاملاً متفاوت می‌پرسم، {q}",
    "ممکنه واژه‌اش بانکی به نظر برسه اما {q}",
    "این سؤال فقط درباره یک حساب یا ابزار دیجیتاله: {q}",
    "برای حل یک مشکل فنی کمک می‌خوام؛ {q}",
    "واژه مشترکه، اما منظورم یک موضوع غیربانکیه: {q}",
)


def _nonbank_row(text: str, example_type: str, difficulty: str, family: str, category: str, subcategory: str = "") -> dict[str, Any]:
    return {
        "text": text.strip(), "label": LABEL_NONBANKING, "example_type": example_type,
        "difficulty": difficulty, "source_question_id": "", "source_question": "",
        "category": category, "sub_category": subcategory,
        "generation_family": family, "split": "",
    }


def chitchat_pool() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for greeting in CHAT_GREETINGS:
        for tail in CHAT_TAILS:
            proposition = f"{greeting}، {tail}"
            group = stable_id("chat", proposition)
            rows.append(_nonbank_row(proposition, "chit_chat", "easy", f"chitchat:{group}", "گفت‌وگوی اجتماعی"))
            rows.append(_nonbank_row(f"{proposition} دوست دارم فقط کمی گپ بزنیم.", "chit_chat", "medium", f"chitchat:{group}", "گفت‌وگوی اجتماعی"))
    for context in CHAT_CONTEXTS:
        for tail in CHAT_TAILS:
            proposition = f"{context}؛ {tail}"
            group = stable_id("chat", proposition)
            rows.append(_nonbank_row(proposition, "chit_chat", "medium", f"chitchat:{group}", "گفت‌وگوی احساسی"))
            rows.append(_nonbank_row(f"سلام، {proposition}", "chit_chat", "medium", f"chitchat:{group}", "گفت‌وگوی احساسی"))
    for greeting in CHAT_GREETINGS:
        for context in CHAT_CONTEXTS:
            for tail in CHAT_TAILS:
                proposition = f"{greeting}، {context} و {tail}"
                group = stable_id("chat", proposition)
                rows.append(_nonbank_row(proposition, "chit_chat", "medium", f"chitchat:{group}", "گفت‌وگوی اجتماعی"))
                rows.append(_nonbank_row(f"فقط برای گپ دوستانه می‌گم: {proposition}", "chit_chat", "medium", f"chitchat:{group}", "گفت‌وگوی اجتماعی"))
    return rows


def straightforward_nonbanking_pool() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for topic, entities in NONBANKING_ENTITIES.items():
        for entity in entities:
            for template in NONBANKING_QUESTIONS:
                proposition = template.format(entity=entity)
                group = stable_id("nonbank", topic, proposition)
                for style in NONBANKING_STYLES:
                    rows.append(_nonbank_row(style.format(q=proposition), "non_banking", "easy", f"nonbank:{topic}:{group}", topic, entity))
                for index, variant in enumerate(
                    phrase_spacing_variants(proposition, entity)
                ):
                    for style in NONBANKING_STYLES[:3]:
                        rows.append(
                            _nonbank_row(
                                style.format(q=variant),
                                "non_banking",
                                "hard",
                                f"nonbank:{topic}:{group}",
                                topic,
                                f"{entity}:spacing_{index + 1}",
                            )
                        )
    return rows


def hard_positive_pool() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept, definition in COLLISIONS.items():
        for entity in definition["entities"]:
            for template in definition["templates"]:
                proposition = template.format(entity=entity)
                group = stable_id("collision", concept, proposition)
                for style in COLLISION_STYLES:
                    rows.append(_nonbank_row(style.format(q=proposition), "hard_positive", "hard", f"lexical_collision:{concept}:{group}", "هم‌پوشانی واژگانی غیربانکی", concept))
    return rows


def select_balanced_nonbanking(target: int, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    pools = [chitchat_pool(), straightforward_nonbanking_pool(), hard_positive_pool()]
    quotas = [round(target * 0.20), round(target * 0.38)]
    quotas.append(target - sum(quotas))
    selected: list[dict[str, Any]] = []
    unused: list[dict[str, Any]] = []
    for pool, quota in zip(pools, quotas, strict=True):
        pool, _ = deduplicate_rows(pool)
        rng.shuffle(pool)
        if len(pool) < quota:
            raise ValueError(f"Non-banking candidate pool has {len(pool)} rows but needs {quota}")
        selected.extend(pool[:quota])
        unused.extend(pool[quota:])
    return selected, unused


def semantic_sanity(rows: Iterable[dict[str, Any]], valid_source_ids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    answer_markers = ("پاسخ:", "جواب:", "مشتری عزیز")
    explicit_nonbank_markers = {
        entity for definition in COLLISIONS.values() for entity in definition["entities"]
    } | {"غیربانکی"}
    for row in rows:
        reason = ""
        text = str(row["text"])
        if int(row["label"]) == LABEL_BANKING and row["source_question_id"] not in valid_source_ids:
            reason = "banking row is not anchored to a FAQ"
        elif int(row["label"]) == LABEL_BANKING and normalize_persian(row["category"], punctuation=True) == "چت بات":
            reason = "source FAQ conflicts with the explicit rule that assistant/meta questions are label 1"
        elif any(marker in text for marker in answer_markers):
            reason = "answer-like marker"
        elif row["example_type"] == "hard_positive" and not any(marker in text for marker in explicit_nonbank_markers):
            reason = "lexical collision lacks an explicit non-banking entity"
        if reason:
            flagged = dict(row)
            flagged["review_reason"] = reason
            flagged["split"] = "review_required"
            review.append(flagged)
        else:
            accepted.append(row)
    return accepted, review


def make_adversarial_set(
    master: list[dict[str, Any]], unused_nonbanking: list[dict[str, Any]], seed: int, pairs: int = 200
) -> list[dict[str, Any]]:
    rng = random.Random(seed + 991)
    master_norm = {normalize_persian(row["text"], punctuation=True) for row in master}
    faq_by_id: dict[str, dict[str, Any]] = {}
    for row in master:
        if int(row["label"]) == 0 and row["split"] == "test":
            faq_by_id.setdefault(row["source_question_id"], row)
    sources = list(faq_by_id.values())
    rng.shuffle(sources)
    banking_rows: list[dict[str, Any]] = []
    banking_wrappers = (
        "راستش اول می‌خواستم فقط سلام کنم، اما یک مشکل واقعی دارم: {q}",
        "شاید سؤال ساده‌ای باشه ولی واقعاً نگرانم؛ {q}",
        "من از دستیار سؤال شخصی ندارم؛ مسئله‌ام اینه: {q}",
        "بعد از کلی جست‌وجو هنوز جواب نگرفتم. در های‌بانک {q}",
    )
    combinations = [(source, wrapper) for source in sources for wrapper in banking_wrappers]
    rng.shuffle(combinations)
    for index, (source, wrapper) in enumerate(combinations[:pairs]):
        text = wrapper.format(q=source["source_question"])
        row = dict(source)
        row.update(text=text, example_type="hard_negative", difficulty="hard", generation_family=f"adversarial_banking:{source['source_question_id']}:{index}", split="adversarial")
        if normalize_persian(text, punctuation=True) not in master_norm:
            banking_rows.append(row)
    nonbank_rows: list[dict[str, Any]] = []
    for source in unused_nonbanking:
        key = normalize_persian(source["text"], punctuation=True)
        if source["example_type"] == "hard_positive" and key not in master_norm:
            row = dict(source)
            row["split"] = "adversarial"
            row["generation_family"] = "adversarial_" + row["generation_family"]
            nonbank_rows.append(row)
            if len(nonbank_rows) >= len(banking_rows):
                break
    result, _ = deduplicate_rows(banking_rows + nonbank_rows)
    rng.shuffle(result)
    return result


def percentile(sorted_values: list[int], probability: float) -> float:
    if not sorted_values:
        return 0.0
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[lower])
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (position - lower)


def write_summary(
    path: Path, faqs: list[FAQ], rows: list[dict[str, Any]], adversarial: list[dict[str, Any]],
    review: list[dict[str, Any]], duplicate_count: int, parser_stats: dict[str, int], seed: int,
) -> None:
    label_counts = Counter(int(row["label"]) for row in rows)
    split_counts = Counter(row["split"] for row in rows)
    types = Counter(row["example_type"] for row in rows)
    lengths = sorted(len(row["text"]) for row in rows)
    per_source = Counter(row["source_question_id"] for row in rows if row["source_question_id"])
    categories = {normalize_persian(faq.category, punctuation=True) for faq in faqs}
    subcategories = {normalize_persian(faq.sub_category, punctuation=True) for faq in faqs if faq.sub_category}
    body = f"""# Intent-classifier dataset summary

Generated deterministically with seed `{seed}`. FAQ answers were parsed only for source understanding/integrity and are not stored in any output dataset.

## Counts

| Measure | Count |
|---|---:|
| FAQ chunk files parsed | {len(faqs):,} |
| Unique source-question groups | {len({faq.source_question_id for faq in faqs}):,} |
| Banking source groups represented after review exclusions | {len(per_source):,} |
| Normalized categories | {len(categories):,} |
| Normalized subcategories | {len(subcategories):,} |
| Total master examples | {len(rows):,} |
| Label 0 — banking/in-scope | {label_counts[0]:,} |
| Label 1 — chit-chat/out-of-scope | {label_counts[1]:,} |
| Label-0 ratio | {label_counts[0] / len(rows):.2%} |
| Hard negatives (banking) | {types['hard_negative']:,} |
| Hard positives (out-of-scope collision) | {types['hard_positive']:,} |
| Train | {split_counts['train']:,} |
| Validation | {split_counts['validation']:,} |
| Test | {split_counts['test']:,} |
| Separate adversarial test | {len(adversarial):,} |
| Review required (excluded) | {len(review):,} |
| Normalized duplicates removed | {duplicate_count:,} |

## Text lengths (Unicode characters)

Average: `{statistics.fmean(lengths):.1f}`; p50: `{percentile(lengths, .50):.1f}`; p90: `{percentile(lengths, .90):.1f}`; p95: `{percentile(lengths, .95):.1f}`; p99: `{percentile(lengths, .99):.1f}`.

## Examples per banking source

Minimum: `{min(per_source.values())}`; median: `{statistics.median(per_source.values()):.1f}`; maximum: `{max(per_source.values())}`.

## Integrity controls

- All examples from a banking `source_question_id` are assigned to one split only.
- Closely related label-1 variants share a generation-family group and are assigned together.
- Exact and Persian-normalized duplicates (`ي/ی`, `ك/ک`, punctuation, whitespace, and نیم‌فاصله) are removed, except controlled raw-distinct rows explicitly tagged `typo_variant`.
- Label-0 examples must reference a parsed FAQ source ID.
- Hard positives must contain an explicit non-banking entity; ambiguous candidates go to `review_required.csv`.
- Adversarial examples are stored separately and are never written to train/validation/test files.
- Parser ignored {parser_stats['hidden_ignored']} hidden, {parser_stats['empty_ignored']} empty, and {parser_stats['non_txt_ignored']} non-text files.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def write_inventory(path: Path, faqs: list[FAQ]) -> None:
    categories: dict[str, list[FAQ]] = defaultdict(list)
    for faq in faqs:
        key = normalize_persian(faq.category, punctuation=True)
        categories[key].append(faq)
    lines = [
        "# Banking intent inventory", "",
        f"Inventory of **{len(faqs):,}** parsed chunks and **{len({faq.source_question_id for faq in faqs}):,}** unique normalized questions.",
        "Answers are intentionally omitted. Category spelling and punctuation variants are merged for counting.", "",
        "| Normalized category | Chunks | Unique subcategories | Representative question topics |", "|---|---:|---:|---|",
    ]
    for category, members in sorted(categories.items(), key=lambda item: (-len(item[1]), item[0])):
        subs = {normalize_persian(item.sub_category, punctuation=True) for item in members if item.sub_category}
        samples = []
        for member in members:
            topic = member.sub_category.strip().rstrip(".") or clean_question(member.question)[:70]
            if topic and normalize_persian(topic) not in {normalize_persian(value) for value in samples}:
                samples.append(topic)
            if len(samples) == 3:
                break
        safe_category = category.replace("|", "\\|")
        safe_samples = "؛ ".join(samples).replace("|", "\\|")
        lines.append(f"| {safe_category} | {len(members):,} | {len(subs):,} | {safe_samples} |")
    lines.extend([
        "", "## Generation vocabulary", "",
        "The generator derives intent language from each source question plus its category/subcategory. It applies formal/informal wording, realistic character and نیم‌فاصله variation, short contextual requests, and conversational wrappers. It does not synthesize banking procedures, limits, eligibility rules, fees, or answers.",
        "", "## Source traceability", "",
        "Every banking row carries a deterministic `faq_<sha256-prefix>` ID derived from the normalized source question, the original question, category, subcategory, and source split. Duplicate source questions share an ID so they cannot leak across splits.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(args: argparse.Namespace) -> dict[str, Any]:
    faqs, parser_stats = read_faqs(args.faq_dir)
    if not faqs:
        raise ValueError("No FAQ chunks were parsed")
    valid_source_ids = {faq.source_question_id for faq in faqs}
    raw_banking = [row for faq in faqs for row in banking_examples(faq)]
    banking, banking_duplicates = deduplicate_rows(raw_banking)
    banking, banking_review = semantic_sanity(banking, valid_source_ids)
    nonbanking, unused_nonbanking = select_balanced_nonbanking(len(banking), args.seed)
    nonbanking, nonbanking_review = semantic_sanity(nonbanking, valid_source_ids)
    review = banking_review + nonbanking_review
    rows, final_duplicates = deduplicate_rows(banking + nonbanking)
    rows = grouped_split(rows, seed=args.seed)
    validation = validate_dataset(rows, valid_source_ids)
    adversarial = make_adversarial_set(rows, unused_nonbanking, args.seed, args.adversarial_pairs)

    args.data_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.data_dir / "intent_classifier_finetune.csv", rows)
    for split in ("train", "validation", "test"):
        write_csv(args.data_dir / f"intent_classifier_{split}.csv", [row for row in rows if row["split"] == split])
    write_csv(args.data_dir / "intent_classifier_adversarial_test.csv", adversarial)
    write_csv(args.data_dir / "review_required.csv", review, (*REQUIRED_COLUMNS, "review_reason"))
    write_summary(args.report, faqs, rows, adversarial, review, banking_duplicates + final_duplicates, parser_stats, args.seed)
    write_inventory(args.inventory, faqs)
    return {
        **validation,
        "faq_chunks": len(faqs),
        "unique_source_questions": len(valid_source_ids),
        "hard_negatives": sum(row["example_type"] == "hard_negative" for row in rows),
        "hard_positives": sum(row["example_type"] == "hard_positive" for row in rows),
        "splits": dict(Counter(row["split"] for row in rows)),
        "adversarial": len(adversarial),
        "review_required": len(review),
        "duplicates_removed": banking_duplicates + final_duplicates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faq-dir", type=Path, default=DEFAULT_FAQ_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--adversarial-pairs", type=int, default=200, help="Target number per label")
    return parser.parse_args()


def main() -> None:
    result = build(parse_args())
    print("Pre-training dataset gate: PASS")
    for key, value in result.items():
        print(f"{key}: {value}")
    print("Estimated training command:")
    print("  /root/miniconda3/envs/faq/bin/python3.12 training/intent_classifier/train_intent_classifier.py --device cuda --seed 42 --confirm-resource-safe")


if __name__ == "__main__":
    main()
