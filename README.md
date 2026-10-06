# Mutabiq (مُطابِق)

Arabic-first retrieval tool. It rewrites a question into formal Arabic, searches an approved corpus of already-published fatwas, and returns the closest matching fatwa **verbatim with its source URL**, plus similarities/case differences and an evidence status. It never issues its own ruling.

For design decisions, hard rules, retrieval details, and deployment constraints, see [AGENTS.md](./AGENTS.md).

## Run locally

### 1. Prerequisites

- **Git**
- **Python 3.11 or newer** — check with `python --version` (or `py --version` on Windows if `python` is not on PATH)
- **~500 MB free disk** — the embedding model is downloaded from Hugging Face on first use
- **Internet access** — for the model download and for LLM API calls at runtime
- Optional: **Make** (only if you want to use the `make` targets; every step below also works without it)

### 2. Clone the repository

```bash
git clone https://github.com/Aws-Nassar/Mutabiq.git
cd Mutabiq
```

### 3. Install the dependencies

Windows (the provided Makefile uses Windows paths):

```bash
make setup
```

macOS / Linux (do it manually — the Makefile paths are Windows-style):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

If you prefer not to use `make` at all on Windows:

```bash
py -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -e ".[dev]"
```

### 4. Configure your API keys (`.env`)

Copy the template and open it in an editor:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Fill in **at least one** LLM provider key. The app tries providers in the order configured in `config/config.yaml` (`groq` → `openrouter`) and falls back to the next one if a request fails.

| Variable | Required? | Where to get it | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | **One of these two is required** | <https://console.groq.com/keys> | Free tier; create an account, then an API key. Recommended default. |
| `OPENROUTER_API_KEY` | **One of these two is required** | <https://openrouter.ai/keys> | Free/cheap tier; create an account, then a key. Serves as fallback. |
| `GEMINI_API_KEY` | No | <https://aistudio.google.com/apikey> | Supported by the provider code but **not** in the default fallback order. |
| `LLM_TIMEOUT_SECONDS` | No (default `20`) | — | Seconds before a provider is considered unavailable. |
| `LLM_MAX_RETRIES` | No (default `2`) | — | Retries per provider before falling back. |
| `GROQ_MODEL` | No | — | Override the default Groq model. |
| `OPENROUTER_MODEL` | No | — | Override the default OpenRouter model. |
| `FETCH_DELAY_SECONDS` / `FETCH_MAX_PAGES` | No | — | Only used by the corpus fetch scripts. |

Security rules:

- `.env` is already gitignored — **never commit it**.
- Do not hard-code keys anywhere else. All LLM access goes through `app/llm/provider.py`, which reads them from the environment.
- **No key?** The app still starts: every query degrades to retrieval-only mode with evidence status `NEEDS_VERIFICATION`, and a visible notice is shown instead of an LLM-written comparison.

### 5. Corpus and retrieval index

**Nothing to do** — `data/corpus_merged.jsonl` (the fatwa corpus) and `data/index/` (the precomputed embeddings) are already committed to the repository, so the app runs right after cloning.

Only needed if you want to rebuild them from the source sites:

```bash
make corpus   # re-fetch the raw pages and rebuild data/corpus.jsonl
make index    # rebuild the precomputed retrieval index in data/index/
```

### 6. Start the app

```bash
make run
```

or without `make`:

```bash
# Windows
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# macOS / Linux
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then open **<http://127.0.0.1:8000>** — the Arabic RTL UI loads by default, with an English toggle.

### 7. Verify the installation

1. `GET /health` should return the corpus count:
   ```bash
   curl http://127.0.0.1:8000/health
   ```
2. Send a question:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/query \
     -H "Content-Type: application/json" \
     -d "{\"question\": \"نسيت أصلي وكنت نايم في الشغل، باقي عندي صلاتين\"}"
   ```
3. Run the test suite:
   ```bash
   make test
   ```

### First-run notes and troubleshooting

- **Embedding model download:** the dense retriever (`intfloat/multilingual-e5-small`, ~500 MB) is downloaded from Hugging Face on the **first query**, then cached in your Hugging Face cache directory. Subsequent runs are offline.
- **Skip the model entirely:** set `DISABLE_DENSE=1` in `.env` to run BM25 + keyword retrieval only. The app also falls back to BM25-only automatically if the model fails to load — it never crashes.
- **Windows note:** the dense retriever was blocked by Windows policy in one dev environment; the app degrades to BM25-only there. This does not affect the deployed Linux instance.
- **No/invalid API key:** you will see a provider error in the terminal and a retrieval-only result in the UI — this is the intended graceful degradation, not a crash.
- **Ports:** if port 8000 is busy, change `--port` in the uvicorn command.
- **`python` not found on Windows:** use `py` instead (e.g. `py -m venv .venv`).

## Commands

| Target | Purpose |
|---|---|
| `make setup` | Create venv and install deps |
| `make run` | Start FastAPI (serves API + frontend) on http://127.0.0.1:8000 |
| `make test` | Run tests |
| `make eval` | Run evaluation into `results/` (gitignored) |
| `make lint` | Ruff check + format check |
| `make corpus` | Rebuild raw corpus and `data/corpus.jsonl` |
| `make index` | Build precomputed retrieval index |

## Architecture

```
User Question → Sensitive Check → Restate (LLM) → Retrieve (BM25 + Dense + Keyword) → Compare (LLM) → Status
```

- **BM25**: Exact fiqh terminology matching
- **Dense**: Semantic matching via multilingual-e5-small embeddings
- **Keyword**: LLM-generated fiqh terms matched against titles/categories
- **RRF Fusion**: Reciprocal Rank Fusion merges all three retrievers

## API

- `GET /health` — corpus count and status
- `POST /api/query` — full pipeline (restate → sensitive → retrieve → compare → status)

## Evaluation

56 test queries (28 dev / 28 test) across 5 categories: rephrasings, near-misses, out-of-scope, sensitive, injection attempts.

| Metric | BM25-only | Full Pipeline |
|--------|-----------|---------------|
| Recall@1 | 0.000 | 0.000* |
| Correct REFER | 0.611 | 0.556 |
| False REFER | 0.000 | 0.000 |
| Quote match | 1.000 | 1.000 |
| Latency | 3.6 ms | 1733 ms |

*Dense retriever blocked by Windows policy in dev environment; works on Linux/Render.

`make eval` writes `report.md` and the metric JSON files into `results/`, which is gitignored — run it locally to regenerate the numbers above.

## Notes

- Fatwa texts are committed to this repo so the demo runs out of the box after cloning; their original sources keep the copyright. `data/raw/` (the raw HTML dump) stays gitignored. See [docs/sources.md](./docs/sources.md).
- LLM access only via `app/llm/provider.py`. No provider SDK calls elsewhere.
- UI is Arabic RTL-first with English toggle; strings live in `web/i18n/*.json`.
- Eval outputs, logs (`*.log`, `*.err`), and local scratch files are gitignored.

## License & attribution

Third-party fatwa texts remain the property of their original sources. This project treats them as data under the constraints documented in [AGENTS.md](./AGENTS.md) and [docs/sources.md](./docs/sources.md).
