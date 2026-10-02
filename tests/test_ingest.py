"""Ingest parsing tests against a synthetic HTML fixture (no network)."""

from __future__ import annotations

from pathlib import Path

from scripts.ingest import parse_answer_file

FIXTURE = Path(__file__).parent / "fixtures" / "12345.html"


def test_parse_answer_file_extracts_sections_and_category():
    rec = parse_answer_file(FIXTURE, "2026-10-02")
    assert rec is not None

    assert rec["id"] == "12345"
    assert rec["title"] == "هل قضاء الصلاة واجب على من نسيها؟"
    # question section ("السؤال 12345" -> prefix match)
    assert "نسيت أصلي" in rec["question"]
    # answer section
    assert "من نسي صلاة" in rec["answer"]
    # summary section
    assert rec["summary"] == "ملخص مختصر."
    # category breadcrumb: root + title stripped
    assert rec["category"] == "الفقه وأصوله > الفقه > عبادات > الصلاة"
    assert rec["url"] == "https://islamqa.info/ar/answers/12345"
    assert rec["retrieved_at"] == "2026-10-02"


def test_parse_answer_file_returns_none_when_answer_missing():
    html = "<html><body><main><h1>عنوان</h1></main></body></html>"
    tmp = FIXTURE.parent / "_tmp_no_answer.html"
    tmp.write_text(html, encoding="utf-8")
    try:
        rec = parse_answer_file(tmp, "2026-10-02")
        assert rec is None
    finally:
        tmp.unlink()
