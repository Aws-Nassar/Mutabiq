"""Corpus schema and validation.

Defines the single source of truth for a fatwa record. The schema is as
specified in the work plan:
- id, title, question, answer, url, source_name, license_note, category, retrieved_at

Two text representations are stored:
- text_display — the original, untouched text (as published)
- text_search  — normalized text for matching only (see app/text/arabic.py)

When writing data/corpus.jsonl, every record must have both fields derived
from the published content.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from app.text import arabic

REQUIRED_FIELDS = (
    "id",
    "title",
    "question",
    "answer",
    "url",
    "source_name",
    "license_note",
    "category",
    "retrieved_at",
    "text_display",
    "text_search",
)

# Optional extra fields preserved when present. `summary` is the site's own
# "ملخص الجواب" block, `references` is the "المراجع" block. Both are verbatim
# published text, so they are kept rather than discarded, but neither is required.
OPTIONAL_FIELDS = (
    "summary",
    "references",
    "category_paths",
    "lang",
    "topic_id",
)

# islamqa fatwa URLs look like https://islamqa.info/ar/answers/12345
ISLAMQA_ANSWER_RE = re.compile(r"^https://islamqa\.info/(?:[a-z]{2,3})/answers/\d+$")


def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return str(v)
    except Exception:
        return ""


def _coerce_date(v: Any) -> str:
    """Return an ISO date, or raise if the value is missing/malformed.

    We deliberately do NOT fall back to "today": silently stamping a fabricated
    retrieval date is exactly the kind of invented provenance AGENTS.md forbids.
    The fetch/ingest scripts are responsible for supplying the real date.
    """
    if isinstance(v, date):
        return v.isoformat()
    s = _coerce_str(v).strip()
    if not s:
        raise ValueError("retrieved_at is required (no default; provenance must be real)")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValueError(f"retrieved_at must be YYYY-MM-DD, got {s!r}")
    # Verify the date actually exists (rejects 2024-13-45)
    y, m, d = (int(x) for x in s.split("-"))
    date(y, m, d)
    return s


def _build_text_display(title: str, question: str, answer: str) -> str:
    """Assemble a conservative display body from the three fields.

    The display copy must remain faithful to the published text. We join with
    double newlines to preserve paragraph structure without inventing content.
    If a field is empty, it is omitted.
    """
    parts = []
    t = _coerce_str(title).strip()
    q = _coerce_str(question).strip()
    a = _coerce_str(answer).strip()
    if t:
        parts.append(t)
    if q:
        parts.append(q)
    if a:
        parts.append(a)
    return "\n\n".join(parts)


def validate_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a single corpus record.

    Returns a cleaned dict suitable for writing to corpus.jsonl. Raises
    ValueError if a required invariant fails.
    """
    if not isinstance(rec, dict):
        raise ValueError("record must be a dict")

    out: dict[str, Any] = {}

    # Identifiers and core fields
    out["id"] = _coerce_str(rec.get("id")).strip()
    if not out["id"]:
        raise ValueError("id is required")

    out["title"] = _coerce_str(rec.get("title")).strip()
    out["question"] = _coerce_str(rec.get("question")).strip()
    out["answer"] = _coerce_str(rec.get("answer")).strip()
    if not out["title"]:
        raise ValueError("title is required")
    if not out["answer"]:
        raise ValueError("answer is required")

    # URL and provenance
    url = _coerce_str(rec.get("url")).strip()
    if not url:
        raise ValueError("url is required (never fabricate a source link)")
    out["url"] = url
    out["source_name"] = _coerce_str(rec.get("source_name")).strip() or "islamqa.info"
    out["license_note"] = _coerce_str(rec.get("license_note")).strip() or "TODO: license/permission not yet recorded in docs/sources.md"
    out["category"] = _coerce_str(rec.get("category")).strip()
    if not out["category"]:
        raise ValueError("category is required (used as retrieval metadata)")

    for opt in OPTIONAL_FIELDS:
        v = _coerce_str(rec.get(opt)).strip()
        if v:
            out[opt] = v

    # Dates
    out["retrieved_at"] = _coerce_date(rec.get("retrieved_at"))

    # Dual text representations
    display = _coerce_str(rec.get("text_display")).strip()
    if not display:
        display = _build_text_display(out["title"], out["question"], out["answer"])
    out["text_display"] = display

    search = _coerce_str(rec.get("text_search")).strip()
    if not search:
        search = arabic.text_search_from_display(display)
    else:
        # If explicitly provided, still normalize it defensively to keep the
        # invariant that text_search is normalized search copy.
        search = arabic.text_search_from_display(search)
    out["text_search"] = search

    # Preserve optional verbatim fields, then required keys in stable order.
    result: dict[str, Any] = {}
    for opt in OPTIONAL_FIELDS:
        if out.get(opt):
            result[opt] = out[opt]
    for k in REQUIRED_FIELDS:
        result[k] = out.get(k, "")
    return result


def dumps_record(rec: dict[str, Any]) -> str:
    """Serialize one record to a single JSONL line (no trailing newline)."""
    return json.dumps(rec, ensure_ascii=False, separators=(",", ":"))


def iter_valid_records(records: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for rec in records:
        try:
            yield validate_record(rec)
        except Exception:
            # Ingestion must be conservative: skip malformed records rather than
            # fabricating data. The caller logs/prints counts.
            continue


def write_corpus_jsonl(records: Iterable[dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for rec in iter_valid_records(records):
            f.write(dumps_record(rec) + "\n")
            count += 1
    return count
