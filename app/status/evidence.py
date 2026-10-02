"""Evidence status determination."""

from __future__ import annotations

from enum import StrEnum


class EvidenceStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    REFER = "REFER"


def determine_status(
    match_score: float,
    margin: float,
    is_sens: bool,
    has_quote: bool,
    case_differs_materially: bool = False,
) -> EvidenceStatus:
    if is_sens:
        return EvidenceStatus.REFER
    if not has_quote:
        return EvidenceStatus.REFER
    if case_differs_materially:
        return EvidenceStatus.NEEDS_VERIFICATION
    if match_score >= 0.60 and margin >= 0.05:
        return EvidenceStatus.SUPPORTED
    if match_score < 0.35:
        return EvidenceStatus.REFER
    return EvidenceStatus.NEEDS_VERIFICATION
