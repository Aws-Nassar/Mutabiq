"""Understand user question: rewrite to formal Arabic for retrieval.

Does NOT issue a ruling. Focuses on clarity and formal phrasing while keeping
the user's intent intact. Output is used for retrieval only; the original
question is always displayed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class QuestionUnderstanding:
    restated_arabic: str
    keywords: list[str]
    language: str | None = None
    # True when the LLM was unavailable/failed and we fell back to the raw
    # question. Callers use this to show the hard-rule-6 degradation notice
    # and to be conservative in evidence status.
    degraded: bool = False


def restate_question(provider: Any | None, question: str) -> QuestionUnderstanding:
    if not question or not question.strip():
        return QuestionUnderstanding(restated_arabic="", keywords=[])

    # If no provider, do a conservative pass: return trimmed original
    if provider is None:
        q = question.strip()
        return QuestionUnderstanding(restated_arabic=q, keywords=[], degraded=True)

    prompt = (
        "You are an assistant for Islamic fatwa retrieval. "
        "Rewrite the user's question into clear, correct FORMAL ARABIC suitable "
        "for searching a corpus of published fatwas. Do NOT issue a ruling, fatwa, "
        "or answer. Do NOT suggest a legal opinion. Preserve the factual/case "
        "details exactly. Remove colloquialisms without changing meaning. "
        "Output ONLY the rewritten Arabic question text, with no explanation.\n\n"
        f"User question: {question}"
    )
    try:
        out = provider.complete(prompt, max_tokens=200, temperature=0)
    except Exception:
        return QuestionUnderstanding(restated_arabic=question.strip(), keywords=[], degraded=True)

    out = out.strip().strip('"').strip("'")
    if not out:
        return QuestionUnderstanding(restated_arabic=question.strip(), keywords=[], degraded=True)
    return QuestionUnderstanding(restated_arabic=out, keywords=[])
