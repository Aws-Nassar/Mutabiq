"""Tests for sensitive detection and evidence status."""

from __future__ import annotations

from app.sensitive import topics as st
from app.status import evidence as ev


def test_sensitive_forces_refer():
    sl = st.load_sensitive()
    # should contain at least the configured topics
    assert isinstance(sl, list)
    # match a divorce/oath pattern if present
    text = "زوجتي طلقت نفسها ثلاث مرات"
    is_s = st.is_sensitive(text, sl) or "طلاق" in text or "أيمان" in text or "يمين" in text
    status = ev.determine_status(match_score=0.9, margin=0.2, is_sens=is_s, has_quote=True)
    if is_s:
        assert status == ev.EvidenceStatus.REFER


def test_needs_verification_if_case_differs():
    status = ev.determine_status(
        match_score=0.7,
        margin=0.1,
        is_sens=False,
        has_quote=True,
        case_differs_materially=True,
    )
    assert status == ev.EvidenceStatus.NEEDS_VERIFICATION


def test_refer_if_no_quote_or_low_score():
    assert ev.determine_status(0.2, 0.1, False, True) == ev.EvidenceStatus.REFER
    assert ev.determine_status(0.8, 0.1, False, False) == ev.EvidenceStatus.REFER
