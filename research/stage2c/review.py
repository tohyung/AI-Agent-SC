"""Deterministically surface candidate issues without interpreting user answers."""

from __future__ import annotations

from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from .models import ClarificationIssue, IntentReviewSession


def review_candidate(candidate: ArtifactEnvelope) -> IntentReviewSession:
    if candidate.artifact_type != "intent-candidate":
        raise ValueError("review requires an intent-candidate artifact")
    payload: dict[str, Any] = candidate.payload
    spec = payload.get("intent_spec") or {}
    issues: list[ClarificationIssue] = []
    for index, error in enumerate(payload.get("core_validation_errors", [])):
        issues.append(ClarificationIssue(f"core-{index}", "INVALID_CORE", str(error)))
    for index, error in enumerate(payload.get("full_validation_errors", [])):
        issues.append(ClarificationIssue(f"full-{index}", "INVALID_INTENT_SPEC", str(error)))
    claims = spec.get("claims")
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict) or claim.get("criticality") != "financial":
            continue
        if claim.get("status") in {"unresolved", "conflicted", "assumed"}:
            issues.append(ClarificationIssue(
                f"claim:{claim.get('claim_id')}", str(claim["status"]).upper(),
                f"critical claim {claim.get('kind')} needs review", claim.get("claim_id")))
    questions = spec.get("required_clarifications")
    for index, question in enumerate(questions if isinstance(questions, list) else []):
        description = question.get("question") if isinstance(question, dict) else question
        issues.append(ClarificationIssue(f"question-{index}", "CLARIFICATION", str(description)))
    if spec.get("predicted_resolution") == "unsupported_for_current_study":
        issues.append(ClarificationIssue("unsupported", "UNSUPPORTED", "candidate marks feature unsupported"))
    if not payload.get("semantic_core") or not spec:
        issues.append(ClarificationIssue("candidate-output", "INVALID_OUTPUT", "candidate is incomplete"))
    return IntentReviewSession(candidate.artifact_id, tuple(issues))
