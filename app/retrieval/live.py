"""Live search fallback for when local corpus retrieval returns REFER.

This module provides a last-resort search across islamqa.info and islamweb.net.
In the current implementation it uses HTTP scraping of their public search
endpoints. Both sites increasingly rely on JavaScript rendering, so this
may return empty results on some queries. It should always be presented as
experimental and never replace the pre-vetted local corpus.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

BASE_ISLAMQA = "https://old.islamqa.info"
BASE_ISLAMWEB = "https://www.islamweb.net"
USER_AGENT = "Mutabiq/0.1 (+research; contact: challenge submission)"
TIMEOUT = 10.0
DELAY = 1.5

# Simple in-memory cache to avoid hammering sites on repeated queries.
_cache: dict[str, list["LiveHit"]] = {}
_cache_ts: dict[str, float] = {}
CACHE_TTL = 300  # 5 minutes


@dataclass
class LiveHit:
    id: str
    title: str
    url: str
    source: str  # "islamqa" or "islamweb"
    snippet: str


def _cached(key: str) -> list[LiveHit] | None:
    now = time.time()
    if key in _cache and now - _cache_ts.get(key, 0) < CACHE_TTL:
        return _cache[key]
    return None


def _store(key: str, hits: list[LiveHit]) -> None:
    _cache[key] = hits
    _cache_ts[key] = time.time()


def _search_islamqa(query: str, max_results: int = 5) -> list[LiveHit]:
    key = f"islamqa:{query}"
    cached = _cached(key)
    if cached is not None:
        return cached

    try:
        time.sleep(DELAY)
        url = f"{BASE_ISLAMQA}/ar/search?utf8=%E2%9C%93&q={quote_plus(query)}&s=Question"
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        hits: list[LiveHit] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            m = re.search(r"/answers/(\d+)", href)
            if m:
                hits.append(LiveHit(
                    id=f"islamqa-{m.group(1)}",
                    title=title,
                    url=f"https://islamqa.info/ar/answers/{m.group(1)}",
                    source="islamqa",
                    snippet="",
                ))
            if len(hits) >= max_results:
                break
        _store(key, hits)
        return hits
    except Exception:
        return []


def _search_islamweb(query: str, max_results: int = 5) -> list[LiveHit]:
    key = f"islamweb:{query}"
    cached = _cached(key)
    if cached is not None:
        return cached

    try:
        time.sleep(DELAY)
        url = f"{BASE_ISLAMWEB}/ar/fatwa/?search_words[]={quote_plus(query)}"
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        hits: list[LiveHit] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            m = re.search(r"/ar/fatwa/(\d+)/", href)
            if m:
                hits.append(LiveHit(
                    id=f"islamweb-{m.group(1)}",
                    title=title,
                    url=f"https://www.islamweb.net/ar/fatwa/{m.group(1)}",
                    source="islamweb",
                    snippet="",
                ))
            if len(hits) >= max_results:
                break
        _store(key, hits)
        return hits
    except Exception:
        return []


def live_search(query: str, max_results: int = 5) -> list[LiveHit]:
    """Run live search on islamqa and islamweb, merge and deduplicate by URL."""
    hits = _search_islamqa(query, max_results=max_results)
    hits += _search_islamweb(query, max_results=max_results)
    seen: set[str] = set()
    out: list[LiveHit] = []
    for h in hits:
        if h.url not in seen:
            seen.add(h.url)
            out.append(h)
    return out[:max_results]
