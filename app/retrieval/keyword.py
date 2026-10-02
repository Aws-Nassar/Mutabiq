"""Keyword retriever using LLM-generated fiqh terms.

Matches LLM-proposed fiqh terms (and optionally predicted topic/category tokens)
against `title` and `category`/`category_paths`. This is intentionally shallow
by design (blind to exact durations/numbers but strong on terminology). The
LLM call is routed through `app.llm.provider.Provider` so it degrades cleanly
on failure (hard rule 6): if terms cannot be generated, return empty results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_AR_TOKEN = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


def _extract_tokens(s: str) -> set[str]:
    return {t for t in _AR_TOKEN.findall(s or "") if t}


@dataclass
class KeywordResult:
    doc_id: str
    score: float
    rank: int


class KeywordRetriever:
    def __init__(self, corpus: list[dict[str, Any]], provider=None, max_terms: int = 6):
        self.corpus = corpus
        self.index = {c["id"]: c for c in corpus}
        self.provider = provider
        self.max_terms = max_terms

    def _generate_terms(self, text: str) -> list[str]:
        if not self.provider:
            return []
        prompt = (
            "You are an Arabic fiqh term extractor for Islamic fatwa retrieval. "
            "Return ONLY a space-separated list of the most relevant fiqh/Islamic "
            "legal terms in Arabic (and optionally key category words). "
            "Do NOT answer the question. Do NOT issue a ruling. "
            "Max terms: 6. Focus on nouns/technical terms (e.g. قضاء الصلوات, سجود السهو, "
            "صلاة الجماعة). Question: "
            f"{text[:400]}"
        )
        try:
            out = self.provider.complete(prompt, max_tokens=60, temperature=0)
            terms = [t.strip() for t in out.split() if t.strip()]
            return terms[: self.max_terms]
        except Exception:
            return []

    def query(self, text: str, top_k: int = 50) -> list[KeywordResult]:
        terms = self._generate_terms(text)
        if not terms:
            return []
        hits: list[tuple[str, float]] = []
        for c in self.corpus:
            hay = " ".join(
                [
                    c.get("title", ""),
                    c.get("category", ""),
                    c.get("category_paths", ""),
                ]
            )
            hay_tokens = _extract_tokens(hay)
            # simple overlap scoring (term frequency by exact token presence)
            score = 0.0
            for t in terms:
                if t in hay:
                    score += 1.0
                elif _extract_tokens(t) and hay_tokens.intersection(_extract_tokens(t)):
                    score += 0.8
            if score > 0:
                hits.append((c["id"], score))
        ranked = sorted(hits, key=lambda x: x[1], reverse=True)
        out: list[KeywordResult] = []
        for i, (doc_id, s) in enumerate(ranked[:top_k], start=1):
            out.append(KeywordResult(doc_id=doc_id, score=float(s), rank=i))
        return out
