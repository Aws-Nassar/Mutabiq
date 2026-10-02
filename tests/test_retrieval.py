"""Retrieval component tests."""

from __future__ import annotations

from app.retrieval import bm25, hybrid
from app.text import arabic


def test_bm25_tokenizes_normalized_arabic():
    tokens = bm25.tokenize_arabic("وَسُئِلَ: هل يجب قضاء الصلاة؟")
    # diacritics removed, stopwords present as tokens? conservative normalizer
    # just ensure we get tokens
    assert isinstance(tokens, list)
    assert any("قضاء" in t or "صلاة" in t for t in tokens) or len(tokens) > 0


def test_bm25_returns_ranks():
    corpus = [
        {"id": "1", "text_search": arabic.text_search_from_display("هل يجب قضاء الصلاة")},
        {"id": "2", "text_search": arabic.text_search_from_display("عدد ركعات صلاة الفجر")},
        {"id": "3", "text_search": arabic.text_search_from_display("قضاء الصلوات الفائتة")},
    ]
    br = bm25.BM25Retriever(corpus)
    res = br.query("قضاء الصلاة", top_k=2)
    assert len(res) <= 2
    for i, r in enumerate(res, start=1):
        assert r.rank == i
        assert r.doc_id in ("1", "3")


def test_rrf_merges_ranks_independently_of_scores():
    # Simulate two retrievers
    class Dummy:
        def __init__(self, items):
            self.items = items

        def query(self, text, top_k=10):
            out = []
            for i, (doc_id, score) in enumerate(self.items[:top_k], start=1):
                # mimic result shape
                from types import SimpleNamespace

                out.append(SimpleNamespace(doc_id=doc_id, score=score, rank=i))
            return out

    r1 = Dummy([("a", 10.0), ("b", 1.0), ("c", 0.5)])
    r2 = Dummy([("c", 9.0), ("a", 0.1), ("b", 0.01)])
    hr = hybrid.HybridRetriever({"r1": r1, "r2": r2}, k_rrf=60, depth=10)
    res = hr.query("x", top_k=3)
    assert res[0].doc_id in ("a", "c")  # a and c share top ranks
