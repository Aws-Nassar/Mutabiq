"""Generate evaluation testset from corpus samples.

Uses the LLM to create rephrasings of existing fatwas for evaluation.
Output: eval/testset_draft.jsonl (requires human review before merging).

Usage:
    python -m scripts.make_testset [--count 40] [--output eval/testset_draft.jsonl]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

import yaml

from app.llm.provider import Provider


def load_corpus(path: Path, sample_size: int, seed: int = 42) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    rng = random.Random(seed)
    if len(records) > sample_size:
        records = rng.sample(records, sample_size)
    return records


def generate_rephrasing(provider: Provider, title: str, question: str, answer: str) -> list[str]:
    prompt = (
        "You are creating test questions for an Arabic fatwa retrieval system. "
        "Given a fatwa title and question, generate 2-3 alternative phrasings "
        "that a real user might type. The phrasings should:\n"
        "- Be in colloquial or informal Arabic (not the formal fatwa language)\n"
        "- NOT copy distinctive words from the original fatwa\n"
        "- Vary in length (short, medium, rambling)\n"
        "- Preserve the core question/intent\n\n"
        "Return ONLY a JSON array of strings.\n\n"
        f"Title: {title}\n"
        f"Question: {question}\n"
        f"Answer excerpt: {answer[:200]}"
    )
    try:
        out = provider.complete(prompt, max_tokens=400, temperature=0.7)
        import re
        m = re.search(r"\[.*\]", out, re.DOTALL)
        if m:
            items = json.loads(m.group(0))
            return [s for s in items if isinstance(s, str) and s.strip()]
    except Exception:
        pass
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate evaluation testset")
    parser.add_argument("--count", type=int, default=40, help="Number of corpus items to sample")
    parser.add_argument("--output", default="eval/testset_draft.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = {}
    config_path = Path("config/config.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    corpus_path = Path(config.get("corpus", {}).get("path", "data/corpus.jsonl"))
    if not corpus_path.exists():
        print(f"Corpus not found: {corpus_path}", file=sys.stderr)
        return 1

    try:
        provider = Provider(config)
    except Exception as e:
        print(f"LLM provider unavailable: {e}", file=sys.stderr)
        return 1

    records = load_corpus(corpus_path, args.count, args.seed)
    print(f"Sampled {len(records)} corpus items")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    generated = 0
    with output_path.open("w", encoding="utf-8") as f:
        for rec in records:
            phrasings = generate_rephrasing(
                provider,
                rec.get("title", ""),
                rec.get("question", ""),
                rec.get("answer", ""),
            )
            for i, phrasing in enumerate(phrasings):
                out = {
                    "id": f"gen-{rec['id']}-{i}",
                    "type": "rephrasing",
                    "query": phrasing,
                    "gold_ids": [rec["id"]],
                    "expected_status": "SUPPORTED",
                    "needs_human_review": True,
                }
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
                generated += 1

    print(f"Generated {generated} test queries -> {output_path}")
    print("NOTE: Review and merge with manual testset before evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
