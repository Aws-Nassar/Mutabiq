"""FastAPI app serving API and static frontend.

One service on Render as specified. Routes:
- GET /health
- POST /api/query
- Static files under / (web/)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.llm import provider
from app.retrieval import bm25, dense, hybrid
from app.text import arabic

app = FastAPI(title="Mutabiq", description="Arabic-first fatwa retrieval", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(3, ge=1, le=10)


class Candidate(BaseModel):
    id: str
    url: str
    title: str
    question: str | None = None
    answer: str | None = None
    score: float | None = None
    sources: dict[str, float] | None = None


class QueryResponse(BaseModel):
    query: str
    query_normalized: str
    candidates: list[Candidate]
    evidence_status: str | None = None


@app.on_event("startup")
def load_state():
    global _recs, _byid, _hr, _prov
    corpus_path = Path("data/corpus.jsonl")
    index_dir = Path("data/index")
    recs: list[dict[str, Any]] = []
    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    _recs = recs
    _byid = {r["id"]: r for r in recs}
    br = bm25.BM25Retriever(recs)
    dr = dense.DenseRetriever(index_dir)
    _hr = hybrid.HybridRetriever({"bm25": br, "dense": dr}, depth=40)
    try:
        _prov = provider.Provider()
    except Exception:
        _prov = None


@app.get("/health")
def health():
    return {"status": "ok", "corpus_count": len(_recs) if "_recs" in globals() else 0}


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest):
    q = req.question.strip()
    qnorm = arabic.text_search_from_display(q)
    candidates: list[Candidate] = []
    try:
        for r in _hr.query(q, top_k=req.top_k):
            c = _byid.get(r.doc_id)
            if not c:
                continue
            candidates.append(
                Candidate(
                    id=c["id"],
                    url=c["url"],
                    title=c["title"],
                    question=c.get("question"),
                    answer=c.get("answer"),
                    score=float(r.score),
                    sources=getattr(r, "sources", None),
                )
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Retrieval failed") from e
    return QueryResponse(
        query=q,
        query_normalized=qnorm,
        candidates=candidates,
        evidence_status=None,
    )


# Serve static frontend
web_dir = Path("web")
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")
