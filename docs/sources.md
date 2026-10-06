# Sources, licenses and verification

This file tracks provenance for every corpus source. The repository is public;
fatwa texts are third-party content. Follow the policy in `AGENTS.md` §9.

| Source | URL pattern | License/permission | Date retrieved | How it is used | How it is verified |
|---|---|---|---|---|---|
| islamqa.info (topic 70: الصلاة / Prayer) | `https://islamqa.info/{lang}/answers/<id>`, category `/ar/categories/topics/70` | TODO | TODO | Retrieval corpus only. Texts are stored in `data/corpus.jsonl` (gitignored by default). Display is verbatim with source URL. | TODO |
| islamweb.net (Prayer categories) | `https://www.islamweb.net/ar/fatwa/<id>`, categories under `/ar/fatawa/1324/الصلاة` | TODO | TODO | Supplemental retrieval corpus. Texts are stored in `data/corpus_islamweb.jsonl` (gitignored by default). Display is verbatim with source URL. | TODO |

## Notes

- **Publishing posture (default):** do not republish fatwa texts in the public repo. Keep `data/raw/` and `data/corpus.jsonl` gitignored. Commit only a small permitted sample under `data/samples/` if the organizers approve. Ship `scripts/fetch_corpus.py` to rebuild the raw dump.
- **If permission is granted:** remove the corresponding line(s) from `.gitignore` and commit the corpus after recording the written permission here.
- Unknown fields are marked `TODO` and must be resolved before final submission. Never invent values.
- Exact-substring verification is enforced at runtime for every quote shown (see `app/verify/compare.py`).
