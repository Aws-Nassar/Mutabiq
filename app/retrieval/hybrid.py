"""Hybrid retrieval using Reciprocal Rank Fusion (RRF).

Merges BM25, dense, and keyword retrievers. RRF ignores raw score scales and
uses ranks only, so values never need normalization. A match across views is
rewarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


@dataclass
class HybridResult:
    doc_id: str
    score: float
    rank: int
    sources: dict[str, float]  # per-retriever contribution (debug)


class HybridRetriever:
    def __init__(self, retrievers: dict[str, Any], k_rrf: int = 60, depth: int = 50):
        self.retrievers = retrievers
        self.k_rrf = k_rrf
        self.depth = depth

    def query(self, text: str, top_k: int = 3) -> list[HybridResult]:
        results, _ = self.fuse(text, top_k)
        return results

    def fuse(self, text: str, top_k: int = 3) -> tuple[list[HybridResult], dict[str, Any]]:
        """Fuse retrievers. Returns (results, stats) where stats records how
        many retrievers actually produced results (`active`), so callers can
        normalize RRF against the theoretical maximum for THIS query."""
        votes: dict[str, dict[str, float]] = {}  # doc_id -> {source: contrib}
        active = 0
        for name, ret in self.retrievers.items():
            try:
                res = ret.query(text, top_k=self.depth)
            except Exception:
                continue  # degrade per rule 6
            if res:
                active += 1
            for r in res:
                votes.setdefault(r.doc_id, {})[name] = rrf_score(r.rank, k=self.k_rrf)
        # aggregate
        agg: list[tuple[str, float, dict[str, float]]] = []
        for doc_id, srcs in votes.items():
            total = sum(srcs.values())
            agg.append((doc_id, total, srcs))
        agg.sort(key=lambda x: x[1], reverse=True)
        out: list[HybridResult] = []
        for i, (doc_id, total, srcs) in enumerate(agg[:top_k], start=1):
            out.append(HybridResult(doc_id=doc_id, score=float(total), rank=i, sources=srcs))
        stats = {"active": active, "k_rrf": self.k_rrf, "total_rrf": len(self.retrievers)}
        return out, stats
