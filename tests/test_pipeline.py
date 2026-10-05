"""Integration tests for the full pipeline."""

from __future__ import annotations

from app.pipeline import Pipeline


def test_pipeline_empty_question():
    p = Pipeline()
    result = p.run("", top_k=3)
    assert result.query_original == ""
    assert str(result.status) == "REFER"
    assert len(result.candidates) == 0


def test_pipeline_sensitive_question():
    p = Pipeline()
    result = p.run("زوجتي طلقت نفسها ثلاث مرات", top_k=3)
    assert str(result.status) == "REFER"
    assert result.sensitive_group is not None
    assert len(result.candidates) == 0


def test_pipeline_basic_retrieval():
    p = Pipeline()
    result = p.run("نسيت أصلي وكنت نايم في الشغل", top_k=3)
    assert result.query_original == "نسيت أصلي وكنت نايم في الشغل"
    assert len(result.candidates) > 0
    assert result.candidates[0].id is not None
    assert result.candidates[0].url.startswith("https://islamqa.info")


def test_pipeline_preserves_original():
    p = Pipeline()
    original = "ما حكم من نسي صلاة الفجر؟"
    result = p.run(original, top_k=3)
    assert result.query_original == original


def test_pipeline_status_is_valid():
    p = Pipeline()
    result = p.run("نسيت أصلي", top_k=3)
    assert str(result.status) in ("SUPPORTED", "NEEDS_VERIFICATION", "REFER")
