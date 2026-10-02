"""Sensitive topic detection (forces REFER)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def load_sensitive(path: Path = Path("config/sensitive_topics.yaml")) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("topics", []) if data else []


def _match(text: str, patterns: list[str]) -> bool:
    for p in patterns:
        try:
            if re.search(p, text, re.IGNORECASE | re.MULTILINE):
                return True
        except re.error:
            if p and p in text:
                return True
    return False


def is_sensitive(text: str, sensitive_list: list[dict[str, Any]]) -> bool:
    if not text:
        return False
    t = text
    for topic in sensitive_list:
        pats = topic.get("patterns", [])
        if _match(t, pats):
            return True
    return False
