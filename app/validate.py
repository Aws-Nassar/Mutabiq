"""Input validation: catches nonsense, gibberish, profanity, off-topic, and
injection attempts before any retrieval or LLM work happens.

Returns a ValidationResult with `ok=True` if the question is worth processing.
Otherwise `ok=False` and `reason` tells the pipeline which early-exit path to
return.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.text import arabic

_WHITESPACE_RE = re.compile(r"\s+")

_ARABIC_LETTER_RE = re.compile(r"[آ-ي]")

# Arabic/English bad-word terms — keep conservative.
BAD_WORDS = [
    "شرموطة", "عرص", "قحبة", "خول", "عاهرة", "زنا", "نيك",
    "fuck", "shit", "bitch", "asshole", "bastard", "cunt",
    "nigger", "faggot", "whore", "slut",
]

INJECTION_TRIGGERS = [
    "تجاهل التعليمات", "تجاهل ما سبق", "ignore previous instructions",
    "ignore all instructions", "أصدر لي حكماً", "give me your own ruling",
    "tell me your own ruling", "give me your own fatwa",
]

# Broad Islamic terms; if none appear it's likely off-topic.
ISLAAMIC_TERMS = [
    "صلاة", "صلوات", "صلاه", "صلوات", "قرآن", "حديث", "مسجد", "رمضان", "زكاة",
    "حج", "عمرة", "صيام", "فتوى", "فقه", "دين", "إسلام",
    "نبي", "رسول", "الله", "رب", "وضوء", "تيمم", "جنابة",
    "طهارة", "عذر", "فطر", "عيد", "مكروه", "حرام", "حلال",
    "واجب", "فرض", "سنة", "نفل", "سنّة", "مستحب", "مباح",
    "طلاق", "طلقت", "خلع", "مهر", "يمين", "أيمان", "نذر", "قتل", "قصاص",
    "كافر", "تكفر", "ردة", "طوارئ", "إنقاذ", "جلطة", "إغماء",
    "prayer", "quran", "hadith", "mosque", "ramadan", "zakat",
    "hajj", "umrah", "fasting", "fatwa", "fiqh", "islam",
    "prophet", "allah", "wudu", "ramadan",
]


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""  # 'empty', 'too_short', 'too_long', 'gibberish', 'profanity', 'off_topic', 'injection'
    notice: str = ""


def _norm(s: str) -> str:
    return _WHITESPACE_RE.sub(" ", arabic.normalize_arabic_text(s)).strip().lower()


def is_gibberish(text: str) -> bool:
    """True if the text looks like noise rather than a real question."""
    norm = _norm(text)
    if not norm:
        return True

    # Only symbols/numbers, no letters at all
    if not _ARABIC_LETTER_RE.search(norm) and not any(c.isalpha() for c in norm):
        return True

    # Repeated same character at least 4 times in a row
    if re.search(r"(.)\1{3,}", norm):
        return True

    # Very short after normalization and not a single Arabic word
    tokens = norm.split()
    if len(tokens) <= 1 and len(norm) < 3:
        return True

    return False


def contains_bad_word(text: str) -> bool:
    norm = _norm(text)
    for w in BAD_WORDS:
        if re.search(rf"(?<!\w){re.escape(_norm(w))}(?!\w)", norm):
            return True
    return False


def is_off_topic(text: str) -> bool:
    """True if the question does not appear to be about Islam."""
    norm = _norm(text)
    if not norm:
        return True
    for term in ISLAAMIC_TERMS:
        if term in norm:
            return False
    return True


def is_injection_attempt(text: str) -> bool:
    norm = _norm(text)
    for trigger in INJECTION_TRIGGERS:
        if _norm(trigger) in norm:
            return True
    return False


def validate_question(question: str, max_length: int = 500) -> ValidationResult:
    if not question or not question.strip():
        return ValidationResult(ok=False, reason="empty", notice="الرجاء كتابة سؤالك.")

    q = question.strip()

    if len(q) < 4:
        return ValidationResult(ok=False, reason="too_short", notice="السؤال قصير جداً. حاول كتابة سؤال أوضح.")

    if len(q) > max_length:
        return ValidationResult(ok=False, reason="too_long", notice=f"السؤال طويل جداً (أكثر من {max_length} حرفاً). حاول الاختصار.")

    if is_injection_attempt(q):
        return ValidationResult(ok=False, reason="injection", notice="عذراً، لا يمكننا الإجابة على هذا الطلب.")

    if contains_bad_word(q):
        return ValidationResult(ok=False, reason="profanity", notice="عذراً، يرجى استخدام ألفاظ محترمة.")

    if is_gibberish(q):
        return ValidationResult(ok=False, reason="gibberish", notice="يبدو أن السؤال غير واضح. حاول كتابة سؤال فعلي.")

    # After LLM restatement we check off-topic; here we do a conservative
    # pre-check on the raw text only to avoid rejecting valid dialectal input.
    # If the raw text has no Islamic term AND is very short, treat as off-topic.
    if is_off_topic(q) and len(q.split()) <= 3:
        return ValidationResult(ok=False, reason="off_topic", notice="عذراً، هذا السؤال يبدو غير متعلق بالإسلام.")

    return ValidationResult(ok=True)
