"""Case comparison: similarities and differences vs the retrieved fatwa.

Generated text is limited (hard rule 1) to similarities and differences —
never a ruling. Every item may carry a `quote`, which MUST be an exact
substring of the retrieved passage (hard rule 2): items whose quote fails
verification are dropped, not kept.

Output shape (JSON from the LLM):
{
  "similarities": [{"statement": "...", "quote": "..."}],
  "differences":  [{"statement": "...", "quote": "..."}]
}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.verify import compare as verify

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class CaseComparison:
    similarities: list[dict[str, str]] = field(default_factory=list)
    differences: list[dict[str, str]] = field(default_factory=list)
    degraded: bool = False
    # True when we produced nothing usable (LLM down or unparseable).
    unavailable: bool = True


def _verify_items(items: list[Any], passage: str) -> list[dict[str, str]]:
    """Keep only items whose quote is an exact substring of the passage.

    Hard rule 2: EVERY comparison sentence must be supported by a verbatim
    quote. Items without a quote, or whose quote fails exact-substring
    verification, are dropped — never kept.
    """
    kept: list[dict[str, str]] = []
    if not isinstance(items, list):
        return kept
    for it in items:
        if not isinstance(it, dict):
            continue
        statement = str(it.get("statement", "")).strip()
        quote = str(it.get("quote", "")).strip()
        if not statement or not quote:
            continue  # unsupported statement: drop
        if not verify.verify_exact_substring(quote, passage):
            continue  # hard rule 2: drop, never keep an unsupported quote
        quote = verify.find_quote_in_passage(quote, passage) or quote
        kept.append({"statement": statement, "quote": quote})
    return kept


def compare_cases(
    provider: Any | None,
    user_question: str,
    fatwa_title: str,
    fatwa_passage: str,
) -> CaseComparison:
    """Compare the user's case with the retrieved fatwa's case."""
    if provider is None:
        return CaseComparison(degraded=True, unavailable=True)

    passage_short = (fatwa_passage or "")[:1500]
    prompt = (
        "You are assisting a tool that only RETRIEVES published fatwas. "
        "You must NOT issue a ruling or fatwa, and you must NOT judge the user. "
        "Compare the user's case with the retrieved fatwa below and return JSON "
        "with two keys: 'similarities' and 'differences'. Each is a list of "
        "objects {\"statement\": short factual sentence in Arabic, "
        "\"quote\": an EXACT verbatim excerpt copied word-for-word from the "
        "fatwa passage that supports it, or empty string if none}. "
        "Statements describe factual situation alignment only (e.g. 'narrator "
        "was asleep at work' vs 'case concerns a traveler'), never religious "
        "rulings. Max 4 items per key. Return ONLY the JSON.\n\n"
        f"User case: {user_question}\n\n"
        f"Fatwa title: {fatwa_title}\n"
        f"Fatwa passage:\n{passage_short}"
    )
    try:
        out = provider.complete(prompt, max_tokens=600, temperature=0)
    except Exception:
        return CaseComparison(degraded=True, unavailable=True)

    m = _JSON_RE.search(out or "")
    if not m:
        return CaseComparison(degraded=True, unavailable=True)
    try:
        data = json.loads(m.group(0))
    except Exception:
        return CaseComparison(degraded=True, unavailable=True)

    sims = _verify_items(data.get("similarities"), fatwa_passage)
    diffs = _verify_items(data.get("differences"), fatwa_passage)
    if not sims and not diffs:
        return CaseComparison(degraded=True, unavailable=True)
    return CaseComparison(similarities=sims, differences=diffs, unavailable=False)
