"""Dense retriever with query-only embedding at runtime.

At index build time we compute document embeddings for all records and save to
`data/index/dense.npy` plus a parallel `doc_ids.json`. At runtime we load the
index, lazily initialize the embedding model, and embed *only the query*.
This matches the constraint "precompute document embeddings offline, embed only
the query at runtime".

Model choice is controlled by `config.yaml` (default: multilingual-e5-small,
int8). If the model fails to load, raise a clean exception so hybrid can
degrade to BM25-only (hard rule 6).
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class DenseResult:
    doc_id: str
    score: float
    rank: int


def _load_index(index_dir: Path) -> tuple[np.ndarray, list[str]]:
    mat = np.load(index_dir / "dense.npy")
    doc_ids = json.loads((index_dir / "doc_ids.json").read_text(encoding="utf-8"))
    return mat, doc_ids


class DenseRetriever:
    def __init__(self, index_dir: Path, config: dict[str, Any] | None = None):
        self.index_dir = Path(index_dir)
        self.config = config or {}
        self.mat, self.doc_ids = _load_index(self.index_dir)
        # build doc_id -> index
        self._doc_to_idx = {d: i for i, d in enumerate(self.doc_ids)}
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        # Lazy import so startup is cheap if degraded
        from sentence_transformers import SentenceTransformer

        dense_cfg = (self.config or {}).get("retrieval", {}).get("dense", {})
        model_name = dense_cfg.get("model", "intfloat/multilingual-e5-small")
        # quantization hint (not directly supported by ST; left for docs)
        device = dense_cfg.get("device", None)
        self._model = SentenceTransformer(model_name, device=device)
        max_len = dense_cfg.get("max_seq_length")
        if max_len:
            with contextlib.suppress(Exception):
                self._model.max_seq_length = int(max_len)

    def query(self, text: str, top_k: int = 50) -> list[DenseResult]:
        if not text:
            return []
        self._ensure_model()
        # Embed query only
        q = self._model.encode([text], normalize_embeddings=True, show_progress_bar=False)
        qv = q[0].astype(np.float32)
        # cosine similarity (already normalized)
        sims = (self.mat @ qv).tolist()
        # rank
        pairs = sorted(zip(self.doc_ids, sims, strict=False), key=lambda x: x[1], reverse=True)
        out: list[DenseResult] = []
        for i, (doc_id, s) in enumerate(pairs[:top_k], start=1):
            out.append(DenseResult(doc_id=doc_id, score=float(s), rank=i))
        return out
