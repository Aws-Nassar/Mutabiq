"""Fetch Islamweb fatwas into data/raw/islamweb/.

Two stages:
1. **Discovery** - walk category pages to collect ``/ar/fatwa/<id>`` links.
   Pagination is probed with ``?page=N`` (the site does not always expose all
   page links). We stop when a page yields no new IDs.
2. **Hydration** - download each fatwa page to ``data/raw/islamweb/<id>.html``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.islamweb.net"
FATWA_RE = re.compile(r"/ar/fatwa/(\d+)/")
PAGE_RE = re.compile(r"[?&]page=(\d+)")
USER_AGENT = "Mutabiq/0.1 (+research; contact: challenge submission)"

# Islamweb category IDs for Prayer-related topics.
CATEGORY_MAP = [
    {"id": "1324", "name": "الصلاة"},
    {"id": "1204", "name": "الطهارة"},
    {"id": "1396", "name": "صلاة التطوع"},
    {"id": "1408", "name": "الاستخارة"},
    {"id": "1324", "name": "الصلاة"},
]


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


def fatwa_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    return {m.group(1) for a in soup.find_all("a", href=True) if (m := FATWA_RE.search(a["href"]))}


def discover(client: httpx.Client, raw_dir: Path, delay: float, max_pages: int) -> dict[str, str]:
    found: dict[str, str] = {}
    topics_dir = raw_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    for cat in CATEGORY_MAP:
        cid = cat["id"]
        base = f"{BASE_URL}/ar/fatawa/{cid}/{cat['name'].replace(' ', '-')}"
        page = 1
        new_total = 0
        while page <= max_pages:
            url = base if page == 1 else f"{base}?page={page}"
            time.sleep(delay)
            try:
                html = get_text(client, url)
            except Exception as exc:
                print(f"  [{cid}] page {page} failed: {type(exc).__name__}")
                break
            (topics_dir / f"topic_{cid}_page_{page}.html").write_text(html, encoding="utf-8")
            ids = fatwa_ids(html)
            if not ids:
                break
            fresh = sum(1 for i in ids if i not in found)
            for i in ids:
                if i not in found:
                    found[i] = url
            new_total += fresh
            if page > 1 and fresh == 0:
                break
            page += 1
        print(f"[{cid}] {new_total} new; total {len(found)}")
    return found


def hydrate(client: httpx.Client, found: dict[str, str], answers_dir: Path, delay: float, max_answers: int, resume: bool) -> int:
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
        # We need the slug to fetch the canonical URL; for hydration we use the
        # discovered listing URL to find the first detail link matching this id.
        # Simpler: construct a best-effort URL. Islamweb usually redirects to the
        # canonical slug.
        url = f"{BASE_URL}/ar/fatwa/{aid}"
        try:
            html = get_text(client, url)
        except Exception as exc:
            print(f"  fatwa {aid} failed: {type(exc).__name__}")
            continue
        out.write_text(html, encoding="utf-8")
        done += 1
        if n % 25 == 0:
            print(f"  hydrated {n}/{len(ids)}")
    return done


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch Islamweb fatwas")
    p.add_argument("--raw-dir", default="data/raw/islamweb")
    p.add_argument("--stage", choices=["discover", "hydrate", "all"], default="all")
    p.add_argument("--max-answers", type=int, default=0)
    p.add_argument("--max-pages", type=int, default=0)
    p.add_argument("--delay", type=float, default=None)
    p.add_argument("--resume", action="store_true", default=True)
    p.add_argument("--no-resume", dest="resume", action="store_false")
    p.add_argument("--manifest", default="data/raw/islamweb_ids.json")
    args = p.parse_args()

    delay = args.delay if args.delay is not None else float(os.getenv("FETCH_DELAY_SECONDS", "1.5"))
    timeout = float(os.getenv("FETCH_TIMEOUT_SECONDS", "30"))
    max_pages = args.max_pages or int(os.getenv("FETCH_MAX_PAGES", "200"))
    raw_dir = Path(args.raw_dir)

    print(f"Islamweb fetch; delay={delay}s")

    with make_client(timeout) as client:
        if args.stage in ("discover", "all"):
            found = discover(client, raw_dir, delay, max_pages)
            mf = Path(args.manifest)
            mf.parent.mkdir(parents=True, exist_ok=True)
            import json

            mf.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"Discovered {len(found)} unique fatwa ids -> {mf}")
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
            print(f"Hydrated {n} fatwa pages -> {raw_dir / 'answers'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
