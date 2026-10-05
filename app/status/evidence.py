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
    *,
    supported_min_score: float = 0.60,
    supported_min_margin: float = 0.05,
    refer_max_score: float = 0.35,
) -> EvidenceStatus:
    """Map retrieval signals to one of the three allowed statuses.

    Thresholds default to the values in config/config.yaml (tuned on the DEV
    split only — never on test). Callers pass overrides from config so the file
    stays the single source of truth.
    """
    if is_sens:
        return EvidenceStatus.REFER
    if not has_quote:
        return EvidenceStatus.REFER
    if case_differs_materially:
        return EvidenceStatus.NEEDS_VERIFICATION
    if match_score >= supported_min_score and margin >= supported_min_margin:
        return EvidenceStatus.SUPPORTED
    if match_score < refer_max_score:
        return EvidenceStatus.REFER
    return EvidenceStatus.NEEDS_VERIFICATION
