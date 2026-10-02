# Mutabiq
#
# Targets: setup | run | test | eval | lint
# Note: on this machine `python` is not on PATH. Use `py` (3.14.5), or set
# PYTHON yourself. The project targets 3.11+.

PYTHON ?= py
VENV   ?= .venv
PIP    ?= $(VENV)\Scripts\pip.exe
PY     ?= $(VENV)\Scripts\python.exe

.DEFAULT_GOAL := help
.PHONY: help setup run test eval lint corpus index clean

help:  ## Show this help
	@echo "setup   create the virtualenv and install dependencies"
	@echo "run     start the app on http://127.0.0.1:8000"
	@echo "test    run the test suite"
	@echo "eval    run the evaluation harness into results/"
	@echo "lint    ruff check + format check"
	@echo "corpus  re-fetch the raw corpus and rebuild data/corpus.jsonl"
	@echo "index   build the precomputed retrieval index"

setup:  ## Create the virtualenv and install dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

run:  ## Start the app
	$(PY) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:  ## Run the test suite
	$(PY) -m pytest

eval:  ## Run the evaluation harness
	$(PY) -m eval.run_eval

lint:  ## Lint and format check
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

corpus:  ## Rebuild the corpus from the source
	$(PY) -m scripts.fetch_corpus
	$(PY) -m scripts.ingest

index:  ## Build the precomputed retrieval index
	$(PY) -m scripts.build_index

clean:  ## Remove caches and build artifacts
	rmdir /s /q $(VENV) 2>nul || true
	rmdir /s /q .pytest_cache .ruff_cache 2>nul || true
