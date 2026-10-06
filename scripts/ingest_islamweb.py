"""Parse hydrated Islamweb fatwa HTML into data/corpus_islamweb.jsonl."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

BASE_URL = "https://www.islamweb.net"


def _clean(text: str) -> str:
    return re.sub(r"[ \t\u00a0]+", " ", text).strip()


def extract_title(soup: BeautifulSoup) -> str:
    # Islamweb uses <h2> for the fatwa title on detail pages.
    h2 = soup.find("h2")
    if h2:
        txt = _clean(h2.get_text(" ", strip=True))
        if txt and txt != "الفتوى":
            return txt
    # Fallback: the first major heading after the breadcrumb.
    for tag in soup.find_all(["h1", "h2", "h3"]):
        txt = _clean(tag.get_text(" ", strip=True))
        if txt and txt != "الفتوى":
            return txt
    return ""


def extract_question(soup: BeautifulSoup) -> str:
    # Prefer itemprop="text" inside the question container.
    container = soup.find("div", attrs={"itemprop": "text"})
    if container:
        # Only use this if the page also contains a 'السؤال' heading
        if any("السؤال" in h.get_text() for h in soup.find_all(["h2", "h3", "h4", "strong"])):
            txt = _clean(container.get_text(" ", strip=True))
            if txt:
                return txt
    # Fallback: look for heading containing 'السؤال'
    for h in soup.find_all(["h2", "h3", "h4", "strong"]):
        txt = _clean(h.get_text(" ", strip=True))
        if "السؤال" in txt:
            buf: list[str] = []
            for sib in h.next_siblings:
                if isinstance(sib, Tag) and sib.name in {"h2", "h3", "h4"}:
                    break
                if isinstance(sib, NavigableString):
                    if sib.strip():
                        buf.append(_clean(str(sib)))
                elif isinstance(sib, Tag):
                    st = _clean(sib.get_text(" ", strip=True))
                    if st:
                        buf.append(st)
            return "\n".join(buf).strip()
    return ""


def extract_answer(soup: BeautifulSoup) -> str:
    # Prefer acceptedAnswer container
    container = soup.find("div", attrs={"itemprop": "acceptedAnswer"})
    if container:
        # The actual answer text is in a child div with itemprop="text"
        inner = container.find("div", attrs={"itemprop": "text"})
        if inner:
            txt = _clean(inner.get_text(" ", strip=True))
            if txt:
                return txt
        txt = _clean(container.get_text(" ", strip=True))
        if txt:
            return txt
    # Fallback: look for heading containing 'الإجاب' or 'الجواب'
    for h in soup.find_all(["h2", "h3", "h4", "strong"]):
        txt = _clean(h.get_text(" ", strip=True))
        if "الإجاب" in txt or "الجواب" in txt:
            buf: list[str] = []
            for sib in h.next_siblings:
                if isinstance(sib, Tag) and sib.name in {"h2", "h3", "h4"}:
                    break
                if isinstance(sib, NavigableString):
                    if sib.strip():
                        buf.append(_clean(str(sib)))
                elif isinstance(sib, Tag):
                    cls = " ".join(sib.get("class") or [])
                    if "no_print" in cls or "dropdown" in cls:
                        continue
                    st = _clean(sib.get_text(" ", strip=True))
                    if st:
                        buf.append(st)
            return "\n".join(buf).strip()
    return ""


def extract_breadcrumb(soup: BeautifulSoup) -> str:
    # Islamweb breadcrumb is an ordered list of links.
    for ol in soup.find_all("ol"):
        items = []
        for li in ol.find_all("li"):
            a = li.find("a")
            if a:
                items.append(_clean(a.get_text(" ", strip=True)))
        if len(items) >= 2:
            # drop first if it's 'الرئيسية'
            if items[0] == "الرئيسية":
                items = items[1:]
            return " > ".join(items)
    return ""


def parse_fatwa_file(path: Path, retrieved_at: str) -> dict | None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    aid = path.stem
    title = extract_title(soup)
    question = extract_question(soup)
    answer = extract_answer(soup)
    if not title or not answer:
        return None
    category = extract_breadcrumb(soup)
    rec = {
        "id": f"islamweb-{aid}",
        "title": title,
        "question": question,
        "answer": answer,
        "summary": "",
        "references": "",
        "url": f"{BASE_URL}/ar/fatwa/{aid}",
        "source_name": "islamweb.net",
        "category": category or "TODO: category not detected",
        "lang": "ar",
        "retrieved_at": retrieved_at,
    }
    return rec


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest Islamweb HTML into corpus.jsonl")
    p.add_argument("--answers-dir", default="data/raw/islamweb/answers")
    p.add_argument("--out", default="data/corpus_islamweb.jsonl")
    p.add_argument("--retrieved-at", default=None)
    args = p.parse_args()

    answers_dir = Path(args.answers_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    from app import corpus as corpus_mod

    files = sorted(answers_dir.glob("*.html"))
    if not files:
        print(f"No HTML files in {answers_dir}")
        return 1

    stamps = {f.stat().st_mtime for f in files}
    newest = dt.datetime.fromtimestamp(max(stamps), dt.UTC).date().isoformat()
    retrieved_at = args.retrieved_at or newest

    written = 0
    dropped: list[str] = []
    with out.open("w", encoding="utf-8") as fh:
        for f in files:
            rec = parse_fatwa_file(f, retrieved_at)
            if rec is None:
                dropped.append(f.stem)
                continue
            try:
                v = corpus_mod.validate_record(rec)
            except Exception as exc:
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
