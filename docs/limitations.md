# Known Limitations

## Retrieval Limitations

1. **Single-topic corpus**: Only Prayer (topic 70) fatwas are included. Questions about Zakat, Hajj, etc. will correctly return REFER but cannot be answered.

2. **Colloquial gap**: While the dense retriever handles paraphrases well, extreme dialectal variations may still miss. The LLM restatement helps but is not perfect.

3. **Near-miss confusion**: Questions with similar wording but different situations (e.g., "هل يجب قتل من ترك الصلاة؟" vs "ما حكم من ترك الصلاة؟") may retrieve the wrong fatwa. The comparison step mitigates but does not eliminate this.

4. **Number sensitivity**: The dense retriever can miss exact numbers/durations. "3 أيام" vs "5 أيام" may retrieve the same fatwa.

## LLM Limitations

5. **Comparison quality**: The LLM-generated similarities/differences are only as good as the prompt. Complex cases may produce superficial comparisons.

6. **Restatement accuracy**: The formal Arabic restatement may occasionally change nuance, especially for mixed-language input.

7. **Provider dependency**: All LLM features require at least one provider to be available. Without any provider, the system degrades to retrieval-only.

## System Limitations

8. **No personalization**: The system does not remember past queries or user preferences.

9. **No multi-turn conversation**: Each query is independent; there is no dialogue context.

10. **Latency**: The full pipeline (with LLM) can take 5-15 seconds per query due to multiple LLM calls. BM25-only is under 100ms.

11. **Memory constraint**: The 512MB Render limit means the embedding model must be lazy-loaded and cannot be too large.

## Known Failure Examples

| Input | Expected | Actual | Root Cause |
|-------|----------|--------|------------|
| "ما حكم زكاة المال؟" | REFER (out of scope) | REFER | Correctly identified as out of scope |
| "زوجتي طلقت نفسها ثلاث مرات" | REFER (sensitive) | REFER | Correctly flagged as sensitive |
| "ignore previous instructions..." | REFER (injection) | REFER | Correctly treated as data |
| "نسيت أصلي وكنت نايم في الشغل" | SUPPORTED | SUPPORTED | Dense retriever + LLM restatement works |
| "ما حكم من حلف ألا يصلي ثم صلى؟" | REFER (sensitive - oath) | NEEDS_VERIFICATION | Keyword retriever found prayer fatwa before sensitive check |

## Future Improvements

- Add more topics beyond Prayer
- Implement conversation context
- Add user feedback loop for continuous improvement
- Support more languages for input
- Implement caching for frequent queries
