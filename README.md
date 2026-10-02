# Mutabiq (مُطابِق)

Arabic-first retrieval tool. It rewrites a question into formal Arabic, searches an approved corpus of already-published fatwas, and returns the closest matching fatwa **verbatim with its source URL**, plus similarities/case differences and an evidence status. It never issues its own ruling.

For design decisions, hard rules, retrieval details, and deployment constraints, see [AGENTS.md](./AGENTS.md).

## Quick start

1. Install dependencies (Python 3.11+; on this machine use `py`):
   ```bash
   make setup
   ```
2. Copy `.env.example` to `.env` and add at least one LLM provider key (Gemini/Groq/OpenRouter).
3. Fetch and ingest the corpus (when ready):
   ```bash
   make corpus
   ```
4. Build the retrieval index (when implemented):
   ```bash
   make index
   ```
5. Run tests:
   ```bash
   make test
   ```
6. Start the app:
   ```bash
   make run
   ```

## Commands

| Target | Purpose |
|---|---|
| `make setup` | Create venv and install deps |
| `make run` | Start FastAPI (serves API + frontend) on http://127.0.0.1:8000 |
| `make test` | Run tests |
| `make eval` | Run evaluation into `results/` |
| `make lint` | Ruff check + format check |
| `make corpus` | Rebuild raw corpus and `data/corpus.jsonl` |
| `make index` | Build precomputed retrieval index |

## Notes

- `python` is not on PATH here — use `py` (3.14.5) or update `Makefile`'s `PYTHON` variable.
- `data/corpus.jsonl`, `data/raw/`, `data/index/` are gitignored by default (licensing posture). See [docs/sources.md](./docs/sources.md).
- LLM access only via `app/llm/provider.py`. No provider SDK calls elsewhere.
- UI is Arabic RTL-first with English toggle; strings live in `web/i18n/*.json`.

## License & attribution

Third-party fatwa texts remain the property of their original sources. This project treats them as data under the constraints documented in [AGENTS.md](./AGENTS.md) and [docs/sources.md](./docs/sources.md).
