# Schema: data/corpus.jsonl

Each line is a single JSON object representing one fatwa record. Fields are
strict and validated by `app/corpus.validate_record`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Fatwa identifier (e.g. numeric id from islamqa.info). |
| `title` | string | yes | Title of the fatwa as published. |
| `question` | string | yes | Question text as published. |
| `answer` | string | yes | Answer text as published. |
| `url` | string | yes | Canonical URL to the fatwa, e.g. `https://islamqa.info/ar/answers/<id>`. |
| `source_name` | string | yes | `islamqa.info` (or the actual source). |
| `license_note` | string | yes | License/permission status. Default: `TODO: license/permission not yet recorded in docs/sources.md`. |
| `category` | string | yes | Category path or name (e.g. `الصلاة`). |
| `retrieved_at` | string (YYYY-MM-DD) | yes | Date the fatwa was retrieved. |
| `text_display` | string | yes | **Untouched.** Original text assembled from title/question/answer. Never normalized. |
| `text_search` | string | yes | Normalized for matching only (see `app/text/arabic.py`). Conservative normalization; diacritics stripped, alef/yaa/taa-marbuta unified, digits unified, punctuation collapsed, stopwords removed. |

## Invariants

- `text_display` is never modified by normalization code. Any change to how users see text is a bug.
- `text_search` is always derived from `text_display` (or explicitly re-normalized) so the two stay consistent.
- Records with missing required fields are **skipped** during ingestion (never fabricated).
- URLs, when present, are validated conservatively; canonical form preferred.
