"""Build retrieval indexes (offline).

Precompute dense embeddings for all records in `data/corpus.jsonl` and write:
- `data/index/dense.npy` (float32, L2-normalized)
- `data/index/doc_ids.json`

BM25 requires no serialized index artifact beyond what we can build on-the-fly
from tokenized text (small corpus). This script focuses on dense (query-only
runtime).
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

import numpy as np


def load_corpus(path: Path) -> list[dict]:
    recs: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            recs.append(json.loads(line))
    return recs


def main() -> int:
    p = argparse.ArgumentParser(description="Build retrieval indexes")
    p.add_argument("--corpus", default="data/corpus.jsonl")
    p.add_argument("--out-dir", default="data/index")
    p.add_argument("--model", default=None, help="Override model name")
    p.add_argument("--batch-size", type=int, default=16)
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus(Path(args.corpus))
    if not corpus:
        print("No records in corpus; aborting")
        return 1

    # lazy import model
    from sentence_transformers import SentenceTransformer

    # load config if present for defaults
    model_name = args.model
    if model_name is None:
        try:
            import yaml

            cfg = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
            model_name = cfg["retrieval"]["dense"]["model"]
        except Exception:
            model_name = "intfloat/multilingual-e5-small"

    print(f"Loading model {model_name}")
    model = SentenceTransformer(model_name)
    max_len = None
    try:
        import yaml

        cfg = yaml.safe_load(Path("config/config.yaml").read_text(encoding="utf-8"))
        max_len = cfg["retrieval"]["dense"].get("max_seq_length")
    except Exception:
        pass
    if max_len:
        with contextlib.suppress(Exception):
            model.max_seq_length = int(max_len)

    # embed documents: use text_search (normalized) for retrieval quality
    texts = [c.get("text_search") or c.get("text_display", "") for c in corpus]
    embs = model.encode(texts, normalize_embeddings=True, batch_size=args.batch_size, show_progress_bar=True)
    mat = np.array(embs, dtype=np.float32)
    np.save(out_dir / "dense.npy", mat)
    doc_ids = [c["id"] for c in corpus]
    (out_dir / "doc_ids.json").write_text(json.dumps(doc_ids, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {mat.shape[0]} vectors ({mat.shape[1]} dims) to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
