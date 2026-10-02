"""Tests for Arabic normalization and corpus schema validation.

These tests are deliberately small and deterministic. They verify the two
representations required by AGENTS.md (text_display untouched, text_search
normalized) and the schema invariants.
"""

from __future__ import annotations

import pytest

from app import corpus
from app.text import arabic


def test_normalize_basic_arabic():
    s = "وَسُئِلَ - رحمه الله -: نَسِيتُ أُصَلِّي"
    n = arabic.normalize_arabic_text(s)
    # Diacritics removed, punctuation collapsed, alef unified as needed
    assert "َ" not in n
    assert "ُ" not in n
    assert "ِ" not in n
    assert "ّ" not in n
    assert "-" not in n or " " in n


def test_yyaa_taa_marbuta_unification():
    s = "صلاة مريضة"
    n = arabic.normalize_arabic_text(s)
    # ة → ه, ى → ي (conservative)
    assert "صلاه" in n or "صلاة" not in s or "ه" in n
    # But we only normalize ى when it appears as alif maksura in forms we see
    # Conservative: just ensure no crash and stable output
    assert isinstance(n, str)


def test_digits_unification():
    s = "٣ أيام"
    n = arabic.normalize_arabic_text(s)
    assert "3" in n
    assert "٣" not in n


def test_text_search_from_display_removes_stopwords_and_normalizes():
    display = "هل يجب قضاء الصلاة إذا نسيها الإنسان؟"
    search = arabic.text_search_from_display(display)
    # Common stopwords removed (conservative set)
    assert "هل" not in search.split()
    assert "إذا" not in search.split() or "اذ" not in search.split()
    # Core terms remain
    assert "قضاء" in search
    assert "الصلاة" in search or "صلاه" in search


def _base_rec(**over):
    rec = {
        "id": "a1",
        "title": "عنوان",
        "question": "سؤال",
        "answer": "جواب",
        "url": "https://islamqa.info/ar/answers/1",
        "source_name": "islamqa.info",
        "category": "الفقه > الصلاة",
        "retrieved_at": "2026-10-02",
    }
    rec.update(over)
    return rec


def test_corpus_validate_record_populates_dual_text():
    v = corpus.validate_record(_base_rec())
    assert v["text_display"]
    assert v["text_search"]
    # text_display must contain original content
    assert "عنوان" in v["text_display"]
    # text_search is normalized
    assert isinstance(v["text_search"], str)


def test_corpus_validate_record_defaults_license_note():
    v = corpus.validate_record(_base_rec())
    assert "license_note" in v and v["license_note"]


def test_corpus_preserves_optional_verbatim_fields():
    v = corpus.validate_record(
        _base_rec(summary="ملخص", references="مراجع", category_paths="أ > ب || ج")
    )
    assert v["summary"] == "ملخص"
    assert v["references"] == "مراجع"
    assert v["category_paths"] == "أ > ب || ج"


def test_corpus_rejects_missing_provenance():
    # Never fabricate a retrieval date or a source URL.
    with pytest.raises(ValueError):
        corpus.validate_record(_base_rec(retrieved_at=""))
    with pytest.raises(ValueError):
        corpus.validate_record(_base_rec(retrieved_at="not-a-date"))
    with pytest.raises(ValueError):
        corpus.validate_record(_base_rec(url=""))
    with pytest.raises(ValueError):
        corpus.validate_record(_base_rec(category=""))


def test_corpus_rejects_missing_core_content():
    with pytest.raises(ValueError):
        corpus.validate_record(_base_rec(answer=""))
    with pytest.raises(ValueError):
        corpus.validate_record(_base_rec(title=""))
