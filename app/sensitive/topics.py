"""Sensitive topic detection (forces REFER — hard rule 5).

Config: config/sensitive_topics.yaml uses `groups` with `terms`.
Matching is token-boundary based, case-insensitive, on the whitespace- and
normalization-collapsed text, so the substring "دم" never fires inside "مدير".

The caller must run this against BOTH the raw user question and the restated
one: the raw catches colloquial phrasings, the restated catches formal ones.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.text import arabic

_WS_RE = re.compile(r"\s+")


def load_sensitive(path: Path = Path("config/sensitive_topics.yaml")) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = data.get("groups") or data.get("topics") or []
    return groups


def _norm(s: str) -> str:
    # Lowercasing only affects Latin terms ("Terminal" == "terminal").
    return _WS_RE.sub(" ", arabic.normalize_arabic_text(s)).strip().lower()


def _terms(group: dict[str, Any]) -> list[str]:
    return [t for t in (group.get("terms") or group.get("patterns") or []) if t]


def match_group(text: str, group: dict[str, Any]) -> bool:
    """Token-boundary match against one group."""
    if not text:
        return False
    norm_text = _norm(text)
    if not norm_text:
        return False
    for term in _terms(group):
        nt = _norm(term)
        if not nt:
            continue
        cands = [nt]
        if nt.startswith("ال"):
            cands.append(nt[2:])
        for ntc in cands:
            if not ntc:
                continue
            if f" {ntc} " in f" {norm_text} ":
                return True
            if re.search(rf"(?<![\w]){re.escape(ntc)}(?![\w])", norm_text):
                return True
    return False


def matched_groups(text: str, groups: list[dict[str, Any]]) -> list[str]:
    """Ids of every group that matches `text`."""
    return [g.get("id", "?") for g in groups if match_group(text, g)]


def is_sensitive(text: str, sensitive_list: list[dict[str, Any]]) -> bool:
    if not text:
        return False
    return any(match_group(text, group) for group in sensitive_list)
