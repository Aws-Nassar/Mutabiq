"""Parse hydrated islamqa answer HTML into data/corpus.jsonl.

Input:  data/raw/answers/<id>.html  (written by scripts/fetch_corpus.py)
Output: data/corpus.jsonl           (one JSON object per line)

Extraction is deliberately explicit about which block is which, so a layout
change shows up as a *skipped* record rather than a silently mangled one.
We never fabricate: if title, question, or answer cannot be located, the
record is dropped and reported.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

SECTION_TITLES = {
    "السؤال",
    "ملخص الجواب",
    "الجواب",
    "المراجع",
    "المصدر :",
}
# "المصدر :" sometimes appears as "المصدر" with a stray nbsp
SECTION_RE = re.compile(r"^(السؤال|ملخص\s+الجواب|الجواب|المراجع|المصدر)\s*:?\s*$")

# The h2 labels sometimes carry extra tokens, e.g. "السؤال 656810" (the id) or
# "المصدر :" with a stray nbsp, so match on prefix rather than exact equality.
SECTION_PREFIXES = (
    ("السؤال", "question"),
    ("ملخص الجواب", "summary"),
    ("الجواب", "answer"),
    ("المراجع", "references"),
    ("المصدر", "source"),
)


def _clean(text: str) -> str:
    return re.sub(r"[ \t\u00a0]+", " ", text).strip()


def _section_key(label: str) -> str | None:
    """Map an h2 label to a canonical section key, or None if not a section."""
    lab = label.rstrip(":").strip()
    for prefix, key in SECTION_PREFIXES:
        if lab == prefix or lab.startswith(prefix + " ") or lab.startswith(prefix):
            return key
    return None


def _gather_section(h2: Tag) -> str:
    """Collect the text of a section: all siblings after `h2` up to the next h2."""
    buf: list[str] = []
    for sib in h2.next_siblings:
        if isinstance(sib, Tag) and sib.name == "h2":
            break
        if isinstance(sib, NavigableString):
            if sib.strip():
                buf.append(_clean(str(sib)))
        elif isinstance(sib, Tag):
            # skip purely navigational / interactive chrome
            cls = " ".join(sib.get("class") or [])
            if "no_print" in cls or "dropdown" in cls:
                continue
            txt = _clean(sib.get_text(" ", strip=True))
            if txt:
                buf.append(txt)
    return "\n".join(buf).strip()


def extract_sections(soup: BeautifulSoup) -> dict[str, str]:
    """Return section text keyed by canonical name ('question','summary',
    'answer','references','source')."""
    sections: dict[str, str] = {}
    for h2 in soup.find_all("h2"):
        label = _clean(h2.get_text(" ", strip=True))
        key = _section_key(label)
        if key is None:
            continue
        text = _gather_section(h2)
        if text:
            sections.setdefault(key, text)
    return sections


def extract_category_paths(soup: BeautifulSoup) -> list[str]:
    """Extract every category breadcrumb path for a fatwa.

    The site renders one breadcrumb nav per category the fatwa belongs to
    (e.g. الصلاة, الصوم, الطهارة>الغسل). Each nav is marked `no_print`. The
    first li is the site root ('الموضوعية') and the last is the fatwa title, so
    both are dropped to leave the real category path.
    """
    paths: list[str] = []
    for nav in soup.find_all("nav"):
        cls = " ".join(nav.get("class") or [])
        if "no_print" not in cls:
            continue
        items: list[str] = []
        for li in nav.find_all("li"):
            txt = _clean(li.get_text(" ", strip=True)).lstrip(":").strip()
            if txt:
                items.append(txt)
        if len(items) < 2:
            continue
        inner = items[1:-1]  # drop root and fatwa title
        if not inner:
            continue
        path = " > ".join(inner)
        if path not in paths:
            paths.append(path)
    return paths


def extract_category_path(soup: BeautifulSoup) -> str:
    """Primary category path (first breadcrumb)."""
    paths = extract_category_paths(soup)
    return paths[0] if paths else ""


def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    return _clean(h1.get_text(" ", strip=True)) if h1 else ""


def parse_answer_file(path: Path, retrieved_at: str) -> dict | None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    aid = path.stem
    title = extract_title(soup)
    sections = extract_sections(soup)
    question = sections.get("question", "")
    answer = sections.get("answer", "")
    # Fallback: if the question section is missing, some pages put the
    # question in the summary-adjacent block. If both missing -> drop.
    if not question:
        question = ""
    if not title or not answer:
        return None
    paths = extract_category_paths(soup)
    rec = {
        "id": aid,
        "title": title,
        "question": question,
        "answer": answer,
        "summary": sections.get("summary", ""),
        "references": sections.get("references", ""),
        "url": f"https://islamqa.info/ar/answers/{aid}",
        "source_name": "islamqa.info",
        "category": paths[0] if paths else "TODO: category not detected",
        "lang": "ar",
        "retrieved_at": retrieved_at,
    }
    if len(paths) > 1:
        rec["category_paths"] = " || ".join(paths)
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest islamqa answer HTML into corpus.jsonl")
    p.add_argument("--answers-dir", default="data/raw/answers", help="Per-answer HTML directory")
    p.add_argument("--out", default="data/corpus.jsonl", help="Output JSONL path")
    p.add_argument(
        "--retrieved-at",
        default=None,
        help="Override retrieval date (YYYY-MM-DD). Defaults to the raw HTML mtime.",
    )
    args = p.parse_args()

    answers_dir = Path(args.answers_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    from app import corpus as corpus_mod

    files = sorted(answers_dir.glob("*.html"))
    if not files:
        print(f"No HTML files in {answers_dir}")
        return 1

    # Ingestion date = when the raw HTML was actually written to disk.
    # Use the file mtime so the provenance is real, not "today" by default.
    # --retrieved-at overrides this for a known single-day crawl.
    stamps = {f.stat().st_mtime for f in files}
    newest = dt.datetime.fromtimestamp(max(stamps), dt.UTC).date().isoformat()
    retrieved_at = args.retrieved_at or newest

    written = 0
    dropped: list[str] = []
    with out.open("w", encoding="utf-8") as fh:
        for f in files:
            rec = parse_answer_file(f, retrieved_at)
            if rec is None:
                dropped.append(f.stem)
                continue
            try:
                v = corpus_mod.validate_record(rec)
            except Exception as exc:  # validation must never fabricate
                dropped.append(f"{f.stem} ({exc})")
                continue
            fh.write(corpus_mod.dumps_record(v))
            fh.write("\n")
            written += 1

    print(f"Parsed {len(files)} files (retrieved_at={retrieved_at}); wrote {written} records to {out}")
    if dropped:
        print(f"Dropped {len(dropped)}: {dropped[:10]}{'...' if len(dropped) > 10 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
