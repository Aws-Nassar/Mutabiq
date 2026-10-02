"""BM25 retriever over `text_search`.

Uses rank_bm25.BM25Okapi. Tokenization is whitespace-based (Arabic text is space-
separated in normalized form). We index text_search per record and keep a
lightweight mapping to the original record id for merging.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from app.text import arabic


def tokenize_arabic(s: str) -> list[str]:
    """Simple whitespace tokenization on normalized Arabic text."""
    s = s.strip()
    if not s:
        return []
    # normalize once more defensively
    s = arabic.normalize_arabic_text(s)
    # split on whitespace
    return [t for t in s.split() if t]


@dataclass
class BM25Result:
    doc_id: str
    score: float
    rank: int


class BM25Retriever:
    def __init__(self, corpus: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75):
        self.corpus = corpus
        self.doc_ids: list[str] = [c["id"] for c in corpus]
        self.index = {c["id"]: c for c in corpus}
        tokenized = [tokenize_arabic(c.get("text_search", "")) for c in corpus]
        self.bm25 = BM25Okapi(tokenized, k1=k1, b=b)

    def query(self, text: str, top_k: int = 50) -> list[BM25Result]:
        if not text:
            return []
        q = tokenize_arabic(text)
        if not q:
            q = tokenize_arabic(arabic.text_search_from_display(text))
        scores = self.bm25.get_scores(q)
        # rank by score desc
        ranked = sorted(zip(self.doc_ids, scores, strict=False), key=lambda x: x[1], reverse=True)
        out: list[BM25Result] = []
        for i, (doc_id, s) in enumerate(ranked[:top_k], start=1):
            if s <= 0 and i > 10:  # prune long tail noise
                pass  # keep small scores but not necessary; we'll cap depth
            out.append(BM25Result(doc_id=doc_id, score=float(s), rank=i))
        return out
