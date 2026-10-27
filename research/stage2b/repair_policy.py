"""Small, stable diagnostic taxonomy for repair accounting, not business rules."""

from __future__ import annotations


REPAIR_POLICY_VERSION = "source-draft-v44"


def diagnostic_code(error: str) -> str:
    if "evidence" in error or "source span" in error:
        return "SOURCE_EVIDENCE"
    if "deadline value contradicts" in error or "normalization_basis" in error:
        return "NORMALIZATION"
    if "derived_from" in error or "supersession" in error:
        return "PROVENANCE_LINK"
    if (error.startswith("scope ") or "root transitions" in error
            or "behavior scope" in error):
        return "SCOPE_GRAPH"
    if "conflict" in error or "conflicted" in error:
        return "CLAIM_CONFLICT"
    if ("resolution" in error or "clarification" in error
            or "prediction" in error):
        return "BUSINESS_DECISION"
    return "SCHEMA"


def diagnostic_codes(errors: list[str]) -> list[str]:
    return sorted({diagnostic_code(error) for error in errors})


def repair_progress(before: list[str], after: list[str]) -> bool:
    """Count distinct validator findings; duplicated messages are not progress."""
    return len(set(after)) < len(set(before))
