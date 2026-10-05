"""FastAPI app serving API and static frontend.

One service on Render as specified. Routes:
- GET  /health
- POST /api/query   (full pipeline: restate → sensitive → retrieve → compare → status)
- Static files under / (web/)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.pipeline import Pipeline, QueryResult

_pipeline: Pipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    _pipeline = Pipeline()
    yield


app = FastAPI(
    title="Mutabiq",
    description="Arabic-first fatwa retrieval",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str = Field(..., max_length=500)
    top_k: int = Field(3, ge=1, le=10)


class CandidateOut(BaseModel):
    id: str
    url: str
    title: str
    question: str
    answer: str
    summary: str
    category: str
    match_score: float
    rrf_score: float
    sources: dict[str, float]
    excerpts: list[str]


class QueryResponse(BaseModel):
    query_original: str
    query_restated: str
    query_normalized: str
    llm_degraded: bool
    notice: str | None
    status: str
    sensitive_group: str | None
    candidates: list[CandidateOut]
    comparison: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    n = len(_pipeline.records) if _pipeline else 0
    return {"status": "ok", "corpus_count": n}


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")
    try:
        result: QueryResult = _pipeline.run(req.question, top_k=req.top_k)
    except Exception as e:
        # Hard rule 6: degrade, never crash.
        raise HTTPException(status_code=500, detail="Retrieval failed") from e
    return QueryResponse(**result.to_dict())


# Serve static frontend
web_dir = Path("web")
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")
