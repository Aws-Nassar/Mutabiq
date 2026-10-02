"""Minimal CLI for a quick sanity check of the pipeline.

Usage: python -m app.cli "your question"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.retrieval import bm25, dense, hybrid
from app.text import arabic


def load_corpus(p: Path) -> list[dict]:
    recs: list[dict] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("Usage: python -m app.cli \"question\"", file=sys.stderr)
        return 1
    q = " ".join(argv)
    corpus_path = Path("data/corpus.jsonl")
    index_dir = Path("data/index")
    recs = load_corpus(corpus_path)
    byid = {r["id"]: r for r in recs}
    br = bm25.BM25Retriever(recs)
    dr = dense.DenseRetriever(index_dir)
    hr = hybrid.HybridRetriever({"bm25": br, "dense": dr}, depth=40)
    arabic.text_search_from_display(q)
    for r in hr.query(q, top_k=3):
        c = byid[r.doc_id]
        print(c["id"], round(r.score, 4), c["title"])
        print(c["url"])
        print("---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
