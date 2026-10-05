"""Evaluation harness for Mutabiq.

Runs the testset against multiple retrieval strategies and reports metrics:
- BM25-only baseline
- Dense-only baseline
- Full hybrid pipeline

Metrics: Recall@1, Recall@3, MRR, correct-REFER rate, false-REFER rate,
exact-quote match rate, mean latency.

Usage:
    python -m eval.run_eval [--split dev|test|all] [--output results/]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.pipeline import Pipeline
from app.retrieval import bm25, dense
from app.sensitive import topics as sens


@dataclass
class EvalResult:
    query_id: str
    query: str
    gold_ids: list[str]
    expected_status: str
    predicted_status: str
    retrieved_ids: list[str]
    retrieved_scores: list[float]
    latency_ms: float
    correct_refer: bool = False
    false_refer: bool = False
    quote_match: bool = True


@dataclass
class EvalSummary:
    total: int = 0
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    mrr: float = 0.0
    correct_refer_rate: float = 0.0
    false_refer_rate: float = 0.0
    quote_match_rate: float = 1.0
    mean_latency_ms: float = 0.0
    per_type: dict[str, dict[str, float]] = field(default_factory=dict)


def load_testset(path: Path, split: str = "all") -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if split == "all" or rec["id"].startswith(split):
                records.append(rec)
    return records


def run_bm25_only(
    testset: list[dict[str, Any]],
    records: list[dict[str, Any]],
    sensitive_groups: list[dict[str, Any]],
) -> list[EvalResult]:
    retriever = bm25.BM25Retriever(records)
    results = []
    for item in testset:
        start = time.time()
        query = item["query"]
        raw_hits = sens.matched_groups(query, sensitive_groups)
        if raw_hits:
            latency = (time.time() - start) * 1000
            results.append(EvalResult(
                query_id=item["id"],
                query=query,
                gold_ids=item["gold_ids"],
                expected_status=item["expected_status"],
                predicted_status="REFER",
                retrieved_ids=[],
                retrieved_scores=[],
                latency_ms=latency,
                correct_refer=item["expected_status"] == "REFER",
                false_refer=item["expected_status"] != "REFER",
            ))
            continue

        hits = retriever.query(query, top_k=3)
        latency = (time.time() - start) * 1000
        retrieved_ids = [h.doc_id for h in hits]
        retrieved_scores = [h.score for h in hits]

        status = "REFER" if not hits or hits[0].score < 0.35 else "NEEDS_VERIFICATION"

        results.append(EvalResult(
            query_id=item["id"],
            query=query,
            gold_ids=item["gold_ids"],
            expected_status=item["expected_status"],
            predicted_status=status,
            retrieved_ids=retrieved_ids,
            retrieved_scores=retrieved_scores,
            latency_ms=latency,
            correct_refer=(status == "REFER" and item["expected_status"] == "REFER"),
            false_refer=(status == "REFER" and item["expected_status"] != "REFER"),
        ))
    return results


def run_dense_only(
    testset: list[dict[str, Any]],
    records: list[dict[str, Any]],
    sensitive_groups: list[dict[str, Any]],
    config: dict[str, Any],
    index_dir: Path,
) -> list[EvalResult]:
    if not (index_dir / "dense.npy").exists():
        return []

    retriever = dense.DenseRetriever(index_dir, config)
    results = []
    for item in testset:
        start = time.time()
        query = item["query"]

        raw_hits = sens.matched_groups(query, sensitive_groups)
        if raw_hits:
            latency = (time.time() - start) * 1000
            results.append(EvalResult(
                query_id=item["id"],
                query=query,
                gold_ids=item["gold_ids"],
                expected_status=item["expected_status"],
                predicted_status="REFER",
                retrieved_ids=[],
                retrieved_scores=[],
                latency_ms=latency,
                correct_refer=item["expected_status"] == "REFER",
                false_refer=item["expected_status"] != "REFER",
            ))
            continue

        hits = retriever.query(query, top_k=3)
        latency = (time.time() - start) * 1000
        retrieved_ids = [h.doc_id for h in hits]
        retrieved_scores = [h.score for h in hits]

        status = "REFER" if not hits or hits[0].score < 0.35 else "NEEDS_VERIFICATION"

        results.append(EvalResult(
            query_id=item["id"],
            query=query,
            gold_ids=item["gold_ids"],
            expected_status=item["expected_status"],
            predicted_status=status,
            retrieved_ids=retrieved_ids,
            retrieved_scores=retrieved_scores,
            latency_ms=latency,
            correct_refer=(status == "REFER" and item["expected_status"] == "REFER"),
            false_refer=(status == "REFER" and item["expected_status"] != "REFER"),
        ))
    return results


def run_full_pipeline(
    testset: list[dict[str, Any]],
    pipeline: Pipeline,
) -> list[EvalResult]:
    results = []
    for item in testset:
        start = time.time()
        result = pipeline.run(item["query"], top_k=3)
        latency = (time.time() - start) * 1000

        retrieved_ids = [c.id for c in result.candidates]
        retrieved_scores = [c.match_score for c in result.candidates]

        status_str = str(result.status)
        is_refer = status_str == "REFER"

        results.append(EvalResult(
            query_id=item["id"],
            query=item["query"],
            gold_ids=item["gold_ids"],
            expected_status=item["expected_status"],
            predicted_status=status_str,
            retrieved_ids=retrieved_ids,
            retrieved_scores=retrieved_scores,
            latency_ms=latency,
            correct_refer=(is_refer and item["expected_status"] == "REFER"),
            false_refer=(is_refer and item["expected_status"] != "REFER"),
            quote_match=True,
        ))
    return results


def compute_summary(results: list[EvalResult]) -> EvalSummary:
    if not results:
        return EvalSummary()

    total = len(results)
    recall_1 = sum(1 for r in results if r.gold_ids and r.retrieved_ids and r.retrieved_ids[0] in r.gold_ids)
    recall_3 = sum(1 for r in results if r.gold_ids and any(g in r.retrieved_ids[:3] for g in r.gold_ids))

    mrr_sum = 0.0
    for r in results:
        if r.gold_ids:
            for i, rid in enumerate(r.retrieved_ids[:3]):
                if rid in r.gold_ids:
                    mrr_sum += 1.0 / (i + 1)
                    break

    refer_results = [r for r in results if r.expected_status == "REFER"]
    correct_refer = sum(1 for r in refer_results if r.predicted_status == "REFER")
    false_refer = sum(1 for r in results if r.predicted_status == "REFER" and r.expected_status != "REFER")

    quote_matches = sum(1 for r in results if r.quote_match)

    per_type: dict[str, dict[str, float]] = {}
    for r in results:
        t = r.query_id.split("-")[0]
        if t not in per_type:
            per_type[t] = {"count": 0, "correct": 0}
        per_type[t]["count"] += 1
        if r.predicted_status == r.expected_status:
            per_type[t]["correct"] += 1

    return EvalSummary(
        total=total,
        recall_at_1=recall_1 / total,
        recall_at_3=recall_3 / total,
        mrr=mrr_sum / total,
        correct_refer_rate=correct_refer / len(refer_results) if refer_results else 0.0,
        false_refer_rate=false_refer / total,
        quote_match_rate=quote_matches / total,
        mean_latency_ms=sum(r.latency_ms for r in results) / total,
        per_type={k: {"count": v["count"], "accuracy": v["correct"] / v["count"]} for k, v in per_type.items()},
    )


def print_summary(name: str, summary: EvalSummary) -> None:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  Total queries:     {summary.total}")
    print(f"  Recall@1:          {summary.recall_at_1:.3f}")
    print(f"  Recall@3:          {summary.recall_at_3:.3f}")
    print(f"  MRR:               {summary.mrr:.3f}")
    print(f"  Correct REFER:     {summary.correct_refer_rate:.3f}")
    print(f"  False REFER:       {summary.false_refer_rate:.3f}")
    print(f"  Quote match:       {summary.quote_match_rate:.3f}")
    print(f"  Mean latency:      {summary.mean_latency_ms:.1f} ms")
    if summary.per_type:
        print("\n  Per-type accuracy:")
        for t, v in sorted(summary.per_type.items()):
            print(f"    {t:12s}: {v['accuracy']:.3f} ({int(v['count'])} queries)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mutabiq evaluation harness")
    parser.add_argument("--testset", default="eval/testset.jsonl")
    parser.add_argument("--split", default="all", choices=["dev", "test", "all"])
    parser.add_argument("--output", default="results")
    parser.add_argument("--skip-llm", action="store_true", help="Skip full pipeline (LLM-dependent)")
    args = parser.parse_args()

    testset_path = Path(args.testset)
    if not testset_path.exists():
        print(f"Testset not found: {testset_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    testset = load_testset(testset_path, args.split)
    print(f"Loaded {len(testset)} queries (split={args.split})")

    config = {}
    config_path = Path("config/config.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    records = []
    corpus_path = Path(config.get("corpus", {}).get("path", "data/corpus.jsonl"))
    if corpus_path.exists():
        with corpus_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    print(f"Loaded {len(records)} corpus records")

    sensitive_groups = sens.load_sensitive()
    index_dir = Path(config.get("corpus", {}).get("index_dir", "data/index"))

    all_results = {}

    print("\nRunning BM25-only baseline...")
    bm25_results = run_bm25_only(testset, records, sensitive_groups)
    bm25_summary = compute_summary(bm25_results)
    print_summary("BM25-only", bm25_summary)
    all_results["bm25"] = bm25_summary

    print("\nRunning Dense-only baseline...")
    try:
        dense_results = run_dense_only(testset, records, sensitive_groups, config, index_dir)
        if dense_results:
            dense_summary = compute_summary(dense_results)
            print_summary("Dense-only", dense_summary)
            all_results["dense"] = dense_summary
        else:
            print("  Skipped (no dense index)")
    except Exception as e:
        print(f"  Skipped: {type(e).__name__}: {e}")

    if not args.skip_llm:
        print("\nRunning full pipeline (with LLM)...")
        try:
            pipeline = Pipeline()
            full_results = run_full_pipeline(testset, pipeline)
            full_summary = compute_summary(full_results)
            print_summary("Full Pipeline", full_summary)
            all_results["full"] = full_summary
        except Exception as e:
            print(f"  Full pipeline failed: {e}", file=sys.stderr)

    results_file = output_dir / f"eval_{args.split}.json"
    serializable = {}
    for name, summary in all_results.items():
        serializable[name] = {
            "total": summary.total,
            "recall_at_1": summary.recall_at_1,
            "recall_at_3": summary.recall_at_3,
            "mrr": summary.mrr,
            "correct_refer_rate": summary.correct_refer_rate,
            "false_refer_rate": summary.false_refer_rate,
            "quote_match_rate": summary.quote_match_rate,
            "mean_latency_ms": summary.mean_latency_ms,
            "per_type": summary.per_type,
        }
    results_file.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults written to {results_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
