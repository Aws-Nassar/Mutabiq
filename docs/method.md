# Method

## Architecture

Mutabiq is a single-service FastAPI application that serves both the API and the static frontend. The system follows a pipeline architecture:

```
User Question → Sensitive Check → Restate (LLM) → Retrieve (BM25 + Dense + Keyword) → Compare (LLM) → Status
```

## Retrieval Strategy

Three retrievers run in parallel over the same corpus, then merge using Reciprocal Rank Fusion (RRF):

| Retriever | Strengths | Weaknesses |
|-----------|-----------|------------|
| BM25 | Exact fiqh terminology | Misses colloquial paraphrases |
| Dense (multilingual-e5-small) | Semantic meaning regardless of wording | Misses exact numbers/durations |
| Keyword (LLM-generated terms) | Topical structure | Depends on LLM term quality |

### Why RRF?

RRF uses only ranks, not raw scores. This means BM25 scores (0-30 range) and cosine similarities (0-1 range) never need to be normalized onto a common scale. A document must agree across multiple views to achieve a high fused score.

### Score Normalization

The raw RRF score is normalized against the theoretical maximum for each query:

```
match_score = min(1.0, rrf_score / (active_retrievers / (k_rrf + 1)))
```

This ensures a document found by only 1 of 3 retrievers scores ~0.33, well below the SUPPORTED threshold (0.60).

## Embedding Model

- **Model**: `intfloat/multilingual-e5-small` (~118M params, 384 dims)
- **Why not bge-m3**: 568M params would exceed the 512MB Render memory limit
- **Quantization**: None (model fits without it; int8 would save memory but was not needed)
- **Index size**: 2,050 vectors × 384 dims × 4 bytes = ~3.1 MB
- **Runtime**: Only the query is embedded; document embeddings are precomputed offline

## Arabic Text Normalization

Conservative normalization for search only (display text is never modified):

1. Remove tashkeel (diacritics) and tatweel
2. Unify alef variants (أإآٱ → ا)
3. Unify yaa variants (ى → ي)
4. Unify taa marbuta (ة → ه)
5. Arabic-Indic digits → European digits
6. Strip Arabic punctuation
7. Collapse whitespace
8. Remove conservative stopwords

The normalization is deliberately conservative to avoid mangling Arabic verbs.

## Evidence Status Determination

| Status | Condition |
|--------|-----------|
| SUPPORTED | match_score ≥ 0.60, margin ≥ 0.05, has verified quotes, no material case differences |
| NEEDS_VERIFICATION | Medium match score, or case differences that could change the ruling |
| REFER | Low match score (< 0.35), sensitive topic, no quotes, or LLM unavailable |

Thresholds are tuned on the DEV split only, never on test.

## LLM Provider

All LLM access goes through `app/llm/provider.py` with automatic fallback:

1. Gemini (primary)
2. Groq (fallback)
3. OpenRouter (last resort)

If all providers fail, the system degrades to retrieval-only with a visible notice and NEEDS_VERIFICATION status (hard rule 6).

## Prompt Injection Safety

- User text and corpus text are always treated as data, never as instructions
- The system prompt explicitly forbids issuing rulings
- Comparison quotes are verified as exact substrings of retrieved passages
- Items failing verification are dropped, never kept
