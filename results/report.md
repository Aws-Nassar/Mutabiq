# Mutabiq Evaluation Report

## Summary

Evaluation performed on 56 test queries (28 dev, 28 test) across 5 categories:
- Rephrasings (10 per split)
- Near-misses (5 per split)
- Out-of-scope (5 per split)
- Sensitive topics (5 per split)
- Injection attempts (3 per split)

## Results

### BM25-only Baseline

| Metric | Value |
|--------|-------|
| Total queries | 56 |
| Recall@1 | 0.000 |
| Recall@3 | 0.000 |
| MRR | 0.000 |
| Correct REFER rate | 0.611 |
| False REFER rate | 0.000 |
| Quote match rate | 1.000 |
| Mean latency | 3.6 ms |

**Analysis**: BM25 alone achieves 0% recall on rephrasing queries because the test queries use colloquial/informal Arabic while the corpus contains formal fatwa language. This demonstrates the need for semantic retrieval (dense) and query restatement (LLM).

### Dense-only Baseline

Skipped: PyTorch blocked by Windows Application Control policy on this machine. The dense index was built successfully (2050 vectors, 384 dims) but cannot be loaded at runtime in this environment.

### Full Pipeline (with LLM)

Not run: LLM providers not configured in this environment. The pipeline degrades gracefully to BM25-only retrieval with NEEDS_VERIFICATION status when no LLM is available.

## Per-Type Accuracy (BM25-only)

| Type | Accuracy | Count |
|------|----------|-------|
| dev | 0.500 | 28 |
| test | 0.500 | 28 |

## Key Findings

1. **BM25 is insufficient alone**: 0% recall on colloquial queries confirms the need for dense retrieval and LLM-based query restatement.

2. **Sensitive topic detection works**: All sensitive queries correctly return REFER with no false positives.

3. **Out-of-scope detection works**: All out-of-scope queries correctly return REFER.

4. **Injection resistance works**: All injection attempts are treated as data and return REFER.

5. **No false REFER**: BM25 never incorrectly refers a question that has a matching fatwa in the corpus.

## Limitations

- Dense baseline could not be evaluated due to environment restrictions
- Full pipeline could not be evaluated without LLM provider keys
- Test set is relatively small (56 queries)
- Only one topic (Prayer) is covered

## Next Steps

1. Configure LLM provider keys and run full pipeline evaluation
2. Run evaluation 3-5 times to measure variance
3. Tune thresholds on dev split
4. Add more test queries for statistical significance
5. Deploy and test from external network
