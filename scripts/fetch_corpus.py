"""Fetch the islamqa.info Prayer corpus (topic 70) into data/raw/.

Two stages:

1. **Discovery** - walk every category in ``config.yaml -> corpus.prayer_subtree``
   and collect ``/ar/answers/<id>`` links. The category tree on the page is
   embedded in the global topic sidebar, so the subtree is declared explicitly
   in config (verified) instead of being scraped from the DOM. Within a
   category, pagination is probed with ``?page=N`` because the page only links
   the first, second and last page.

2. **Hydration** - download each answer page to ``data/raw/answers/<id>.html``.

Politeness: one request at a time with a configurable delay, a descriptive
User-Agent, and ``--resume`` so an interrupted run continues instead of
re-downloading. Listing pages are kept too, as the provenance record for which
listing an id was discovered in.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup

BASE_URL = "https://islamqa.info"
ANSWER_RE = re.compile(r"/[a-z]{2,3}/answers/(\d+)")
PAGE_RE = re.compile(r"[?&]page=(\d+)")
USER_AGENT = "Mutabiq/0.1 (+research; contact: challenge submission)"


def load_subtree(config_path: Path) -> list[dict]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    corpus = cfg.get("corpus", {})
    subtree = corpus.get("prayer_subtree")
    if not subtree:
        raise SystemExit(f"No corpus.prayer_subtree in {config_path}")
    return subtree


def make_client(timeout: float) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.9"},
        timeout=timeout,
        follow_redirects=True,
    )


def get_text(client: httpx.Client, url: str) -> str:
    r = client.get(url)
    r.raise_for_status()
    return r.text


def answer_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    return {m.group(1) for a in soup.find_all("a", href=True) if (m := ANSWER_RE.search(a["href"]))}


def last_page_hint(html: str) -> int:
    """Highest page number linked anywhere on the listing (the 'last' link)."""
    pages = [int(m.group(1)) for a in BeautifulSoup(html, "lxml").find_all("a", href=True) if (m := PAGE_RE.search(a["href"]))]
    return max(pages) if pages else 1


def discover(
    client: httpx.Client,
    subtree: list[dict],
    raw_dir: Path,
    delay: float,
    max_pages: int,
    verbose: bool = True,
) -> dict[str, str]:
    """Return {answer_id: source_listing_url}. Also saves listing HTML."""
    found: dict[str, str] = {}
    topics_dir = raw_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    for node in subtree:
        tid = node["id"]
        name = node.get("name", "")
        base = f"{BASE_URL}/ar/categories/topics/{tid}"
        page = 1
        hint = None
        topic_new = 0
        while page <= max_pages:
            url = base if page == 1 else f"{base}?page={page}"
            time.sleep(delay)
            try:
                html = get_text(client, url)
            except Exception as exc:
                if verbose:
                    print(f"  [{tid}] page {page} failed: {type(exc).__name__}")
                break
            (topics_dir / f"topic_{tid}_page_{page}.html").write_text(html, encoding="utf-8")
            ids = answer_ids(html)
            if not ids:
                break
            if hint is None:
                hint = last_page_hint(html)
            fresh = 0
            for i in ids:
                if i not in found:
                    found[i] = url
                    fresh += 1
            topic_new += fresh
            # Stop when a page yields no unseen ids: pagination has wrapped past
            # the end (the site clamps out-of-range page numbers).
            if page > 1 and fresh == 0:
                break
            page += 1
        if verbose:
            print(f"[{tid}] {name}: +{topic_new} (running total {len(found)})")
    return found


def hydrate(
    client: httpx.Client,
    found: dict[str, str],
    answers_dir: Path,
    delay: float,
    max_answers: int,
    resume: bool,
    verbose: bool = True,
) -> int:
    answers_dir.mkdir(parents=True, exist_ok=True)
    ids = sorted(found, key=int)
    if max_answers > 0:
        ids = ids[:max_answers]
    done = 0
    for n, aid in enumerate(ids, 1):
        out = answers_dir / f"{aid}.html"
        if resume and out.exists() and out.stat().st_size > 0:
            done += 1
            continue
        time.sleep(delay)
        url = f"{BASE_URL}/ar/answers/{aid}"
        try:
            html = get_text(client, url)
        except Exception as exc:
            if verbose:
                print(f"  answer {aid} failed: {type(exc).__name__}")
            continue
        out.write_text(html, encoding="utf-8")
        done += 1
        if verbose and n % 25 == 0:
            print(f"  hydrated {n}/{len(ids)}")
    return done


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch islamqa.info topic 70 (Prayer) corpus")
    p.add_argument("--config", default="config/config.yaml")
    p.add_argument("--raw-dir", default="data/raw")
    p.add_argument("--stage", choices=["discover", "hydrate", "all"], default="all")
    p.add_argument("--max-answers", type=int, default=0, help="Cap hydrated answers (0 = all)")
    p.add_argument("--max-pages", type=int, default=0, help="Cap listing pages per topic (0 = all)")
    p.add_argument("--delay", type=float, default=None, help="Seconds between requests")
    p.add_argument("--resume", action="store_true", default=True)
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.add_argument("--manifest", default="data/raw/discovered_ids.json")
    args = p.parse_args()

    delay = args.delay if args.delay is not None else float(os.getenv("FETCH_DELAY_SECONDS", "1.5"))
    timeout = float(os.getenv("FETCH_TIMEOUT_SECONDS", "30"))
    max_pages = args.max_pages or int(os.getenv("FETCH_MAX_PAGES", "200"))
    raw_dir = Path(args.raw_dir)

    subtree = load_subtree(Path(args.config))
    print(f"Prayer subtree: {len(subtree)} categories; delay={delay}s")

    with make_client(timeout) as client:
        if args.stage in ("discover", "all"):
            found = discover(client, subtree, raw_dir, delay, max_pages)
            mf = Path(args.manifest)
            mf.parent.mkdir(parents=True, exist_ok=True)
            import json

            mf.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"Discovered {len(found)} unique answer ids -> {mf}")
        else:
            import json

            mf = Path(args.manifest)
            if not mf.exists():
                print(f"No manifest at {mf}; run --stage discover first", file=sys.stderr)
                return 1
            found = json.loads(mf.read_text(encoding="utf-8"))
            print(f"Loaded {len(found)} ids from {mf}")

        if args.stage in ("hydrate", "all"):
            n = hydrate(client, found, raw_dir / "answers", delay, args.max_answers, args.resume)
            print(f"Hydrated {n} answer pages -> {raw_dir / 'answers'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
