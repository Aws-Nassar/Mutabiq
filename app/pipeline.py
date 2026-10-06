"""Query pipeline: restate → sensitive check → retrieve → compare → status.

Single orchestration point used by the API (and CLI). Invariants enforced here:

- The ORIGINAL question is always preserved and returned; restated text is for
  retrieval only (AGENTS.md "Non-Arabic input").
- Sensitive groups are matched against BOTH raw and restated text; a hit
  forces REFER and returns no candidates (hard rule 5).
- Comparison quotes are exact-substring verified; failures are dropped by
  app.understanding.compare (hard rule 2).
- LLM failure degrades to retrieval-only with a visible notice and
  NEEDS_VERIFICATION (hard rule 6). Never raises.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.llm.provider import Provider
from app.retrieval import bm25, dense, hybrid, keyword
from app.status.evidence import EvidenceStatus, determine_status
from app.text import arabic
from app.understanding import compare as cases
from app.understanding import question as understand
from app.validate import validate_question
from app.retrieval import live


@dataclass
class Candidate:
    id: str
    url: str
    title: str
    question: str
    answer: str
    summary: str
    category: str
    match_score: float
    rrf_score: float
    sources: dict[str, float] = field(default_factory=dict)
    # Verbatim excerpts that passed exact-substring verification.
    excerpts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "question": self.question,
            "answer": self.answer,
            "summary": self.summary,
            "category": self.category,
            "match_score": self.match_score,
            "rrf_score": self.rrf_score,
            "sources": self.sources,
            "excerpts": self.excerpts,
        }


@dataclass
class QueryResult:
    query_original: str
    query_restated: str
    query_normalized: str
    llm_degraded: bool
    notice: str | None
    status: EvidenceStatus
    sensitive_group: str | None
    candidates: list[Candidate]
    comparison: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_original": self.query_original,
            "query_restated": self.query_restated,
            "query_normalized": self.query_normalized,
            "llm_degraded": self.llm_degraded,
            "notice": self.notice,
            "status": str(self.status),
            "sensitive_group": self.sensitive_group,
            "candidates": [c.to_dict() for c in self.candidates],
            "comparison": self.comparison,
        }


DEGRADED_NOTICE = (
    "LLM unavailable: results are retrieval-only (no case comparison). "
    "Treat this result as NEEDS_VERIFICATION."
)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or _PROJECT_ROOT / "config" / "config.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def _resolve_path(p: str | Path) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return _PROJECT_ROOT / path


class Pipeline:
    def __init__(self, corpus_path: Path | None = None, index_dir: Path | None = None):
        self.config = _load_config()
        if corpus_path is None:
            corpus_path = _resolve_path(self.config.get("corpus", {}).get("path", "data/corpus.jsonl"))
        if index_dir is None:
            index_dir = _resolve_path(self.config.get("corpus", {}).get("index_dir", "data/index"))

        self.records: list[dict[str, Any]] = []
        if corpus_path.exists():
            with corpus_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.records.append(json.loads(line))
        self.by_id = {r["id"]: r for r in self.records}

        self.bm25 = bm25.BM25Retriever(self.records)
        self.bm25_islamweb = None
        islamweb_records = [r for r in self.records if r.get("source_name") == "islamweb.net"]
        if islamweb_records:
            self.bm25_islamweb = bm25.BM25Retriever(islamweb_records)
        self.dense = None
        if os.getenv("DISABLE_DENSE") != "1" and (index_dir / "dense.npy").exists():
            try:
                self.dense = dense.DenseRetriever(index_dir, self.config)
            except Exception:
                self.dense = None
        self.keyword = keyword.KeywordRetriever(
            self.records, max_terms=self.config.get("retrieval", {}).get("keyword", {}).get("max_terms", 6)
        )

        # Load LLM provider; absence is not fatal (degrades at query time).
        try:
            self.provider = Provider(self.config)
        except Exception:
            self.provider = None
        # Fixed at startup so concurrent requests never race on shared state.
        self.keyword.provider = self.provider

        from app.sensitive import topics as sens

        self.sensitive_groups = sens.load_sensitive()
        self.status_cfg = self.config.get("status", {})

    def run(self, question: str, top_k: int = 3) -> QueryResult:
        original = (question or "").strip()
        if not original:
            return QueryResult(
                query_original="",
                query_restated="",
                query_normalized="",
                llm_degraded=False,
                notice=None,
                status=EvidenceStatus.REFER,
                sensitive_group=None,
                candidates=[],
            )

        norm = arabic.text_search_from_display(original)

        # --- Input validation (nonsense, profanity, off-topic, injection) ---
        val_cfg = self.config.get("validation", {})
        if val_cfg.get("enabled", True):
            vr = validate_question(original, max_length=int(val_cfg.get("max_question_chars", 500)))
            if not vr.ok:
                return QueryResult(
                    query_original=original,
                    query_restated="",
                    query_normalized=norm,
                    llm_degraded=False,
                    notice=vr.notice,
                    status=EvidenceStatus.REFER,
                    sensitive_group=None,
                    candidates=[],
                )

        from app.sensitive import topics as sens

        # --- Sensitive check on RAW text first (hard rule 5) ---
        raw_hits = sens.matched_groups(original, self.sensitive_groups)
        if raw_hits:
            return QueryResult(
                query_original=original,
                query_restated="",
                query_normalized=norm,
                llm_degraded=False,
                notice=None,
                status=EvidenceStatus.REFER,
                sensitive_group=raw_hits[0],
                candidates=[],
            )

        # --- Restate for retrieval (original always displayed) ---
        und = understand.restate_question(self.provider, original)
        degraded = und.degraded
        restated = und.restated_arabic or original

        # --- Sensitive check on RESTATED text too ---
        rest_hits = sens.matched_groups(restated, self.sensitive_groups)
        if rest_hits:
            return QueryResult(
                query_original=original,
                query_restated=restated,
                query_normalized=norm,
                llm_degraded=degraded,
                notice=None,
                status=EvidenceStatus.REFER,
                sensitive_group=rest_hits[0],
                candidates=[],
            )

        # --- Retrieve ---
        # If the LLM is down, drop the keyword retriever (it needs the LLM for
        # term generation and would only burn a timeout). Built per call so
        # concurrent requests never mutate shared state.
        fusion = self.config.get("retrieval", {}).get("fusion", {})
        retrievers: dict[str, Any] = {"bm25": self.bm25}
        if self.dense is not None:
            retrievers["dense"] = self.dense
        if not degraded:
            retrievers["keyword"] = self.keyword
        hr = hybrid.HybridRetriever(
            retrievers,
            k_rrf=int(fusion.get("k", 60)),
            depth=int(fusion.get("depth_per_retriever", 50)),
        )
        hits, stats = hr.fuse(restated, top_k=top_k * 2)

        candidates: list[Candidate] = []
        for hit in hits:
            rec = self.by_id.get(hit.doc_id)
            if not rec:
                continue
            candidates.append(
                Candidate(
                    id=rec["id"],
                    url=rec["url"],
                    title=rec.get("title", ""),
                    question=rec.get("question", ""),
                    answer=rec.get("answer", ""),
                    summary=rec.get("summary", ""),
                    category=rec.get("category", ""),
                    match_score=0.0,
                    rrf_score=float(hit.score),
                    sources=dict(getattr(hit, "sources", {}) or {}),
                    excerpts=[],
                )
            )
        candidates = candidates[:top_k]

        # Normalize RRF against the theoretical maximum for THIS query:
        # all `active` retrievers ranking it #1 => active/(k+1).
        # So a doc found by only 1 of 3 views scores ~0.33 — well below
        # supported_min_score (0.60). Cross-view agreement is required to win,
        # which is exactly what AGENTS.md asks of the fusion.
        active = int(stats.get("active", 0)) or 1
        k_rrf = int(stats.get("k_rrf", 60))
        denom = active / (k_rrf + 1)
        if candidates and denom > 0:
            for c in candidates:
                c.match_score = min(1.0, c.rrf_score / denom)

        # --- Cross-source fallback: if top result is from islamqa with low
        # confidence, check islamweb-only for a better match ---
        xsf_cfg = self.config.get("retrieval", {}).get("cross_source_fallback", {})
        if (
            xsf_cfg.get("enabled", True)
            and candidates
            and self.bm25_islamweb is not None
        ):
            top = candidates[0]
            threshold = float(xsf_cfg.get("trigger_threshold", 0.70))
            if top.match_score < threshold and top.id.startswith("islamqa-"):
                islamweb_hits = self.bm25_islamweb.query(restated, top_k=top_k)
                if islamweb_hits:
                    # BM25 raw scores are comparable within the same index;
                    # normalize against the best possible score for this query.
                    best_possible = islamweb_hits[0].score
                    if best_possible > 0:
                        islamweb_candidates = []
                        for i, h in enumerate(islamweb_hits[:top_k]):
                            rec = self.by_id.get(h.doc_id)
                            if not rec:
                                continue
                            islamweb_candidates.append(
                                Candidate(
                                    id=rec["id"],
                                    url=rec["url"],
                                    title=rec.get("title", ""),
                                    question=rec.get("question", ""),
                                    answer=rec.get("answer", ""),
                                    summary=rec.get("summary", ""),
                                    category=rec.get("category", ""),
                                    match_score=min(1.0, h.score / best_possible),
                                    rrf_score=0.0,
                                    sources={"islamweb_bm25": 1.0},
                                    excerpts=[],
                                )
                            )
                        if islamweb_candidates:
                            # Compare: use islamweb if its top score is higher
                            # than the islamqa top score.
                            if islamweb_candidates[0].match_score > top.match_score:
                                candidates = islamweb_candidates

        if not candidates:
            # Fallback to live search when local corpus yields nothing
            live_hits = live.live_search(original, max_results=top_k)
            if live_hits:
                live_candidates = []
                for h in live_hits:
                    live_candidates.append(
                        Candidate(
                            id=h.id,
                            url=h.url,
                            title=h.title,
                            question="",
                            answer="",
                            summary="",
                            category=h.source,
                            match_score=0.5,
                            rrf_score=0.0,
                            sources={"live": 1.0},
                            excerpts=[],
                        )
                    )
                return QueryResult(
                    query_original=original,
                    query_restated=restated,
                    query_normalized=norm,
                    llm_degraded=degraded,
                    notice="النتائج من بحث مباشر على الإنترنت (islamqa و islamweb). يرجى التحقق من المصدر قبل الاعتماد عليها.",
                    status=EvidenceStatus.NEEDS_VERIFICATION,
                    sensitive_group=None,
                    candidates=live_candidates,
                )
            return QueryResult(
                query_original=original,
                query_restated=restated,
                query_normalized=norm,
                llm_degraded=degraded,
                notice=None,
                status=EvidenceStatus.REFER,
                sensitive_group=None,
                candidates=[],
            )

        # --- Case comparison (LLM) ---
        comparison: dict[str, Any] | None = None
        comp_unavailable = False
        if not degraded:
            top = candidates[0]
            passage = "\n".join(
                x for x in (top.question, top.summary, top.answer) if x
            )[:3000]
            cc = cases.compare_cases(self.provider, restated, top.title, passage)
            if cc.unavailable:
                comp_unavailable = True
            else:
                top.excerpts = [
                    i["quote"] for i in (cc.similarities + cc.differences) if i.get("quote")
                ]
                comparison = {
                    "similarities": cc.similarities,
                    "differences": cc.differences,
                }

        # --- Status ---
        is_degraded = degraded or comp_unavailable
        notice = DEGRADED_NOTICE if is_degraded else None
        margin = 0.0
        if len(candidates) > 1:
            margin = candidates[0].match_score - candidates[1].match_score
        else:
            margin = candidates[0].match_score

        if is_degraded:
            # Hard rule 6: LLM failure degrades, never crashes. Results are
            # retrieval-only with a visible notice; the status must not claim
            # SUPPORTED (nothing was compared) — NEEDS_VERIFICATION.
            status = EvidenceStatus.NEEDS_VERIFICATION
        else:
            case_differs = bool(comparison and comparison.get("differences"))
            status = determine_status(
                match_score=candidates[0].match_score,
                margin=margin,
                is_sens=False,
                has_quote=bool(candidates[0].excerpts),
                case_differs_materially=case_differs,
                supported_min_score=float(self.status_cfg.get("supported_min_score", 0.60)),
                supported_min_margin=float(self.status_cfg.get("supported_min_margin", 0.05)),
                refer_max_score=float(self.status_cfg.get("refer_max_score", 0.35)),
            )

        return QueryResult(
            query_original=original,
            query_restated=restated,
            query_normalized=norm,
            llm_degraded=is_degraded,
            notice=notice,
            status=status,
            sensitive_group=None,
            candidates=candidates,
            comparison=comparison,
        )
