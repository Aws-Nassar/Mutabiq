"""Exact-substring verification against retrieved passages.

Every quote shown must be an exact substring of the retrieved passage
(whitespace-normalized only). We do not invent or paraphrase sources.
"""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


def verify_exact_substring(quote: str, passage: str) -> bool:
    if not quote or not passage:
        return False
    qn = _norm(quote)
    pn = _norm(passage)
    if not qn or not pn:
        return False
    return qn in pn


def find_quote_in_passage(quote: str, passage: str) -> str | None:
    if verify_exact_substring(quote, passage):
        return _norm(quote)
    return None
