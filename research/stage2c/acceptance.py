"""Human acceptance never infers a corrected intent from free-form text."""

from __future__ import annotations

from typing import Any, Protocol

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import validate_intent_spec

from .freeze import freeze_accepted_intent
from .models import (AcceptedIntentSpec, ClarificationAnswer, IntentAcceptanceResult,
                     IntentDecision, IntentDecisionStatus, IntentReviewSession)
from .review import review_candidate


def apply_decision(candidate: ArtifactEnvelope, review: IntentReviewSession,
                   decision: IntentDecision | None) -> IntentAcceptanceResult:
    if decision is None:
        return IntentAcceptanceResult(IntentDecisionStatus.NEEDS_CLARIFICATION,
                                      diagnostics=("explicit human acceptance is required",))
    if decision.status != IntentDecisionStatus.ACCEPTED:
        return IntentAcceptanceResult(decision.status, diagnostics=("candidate was not accepted",))
    if not decision.reviewer_id.strip() or not decision.explicit_consent or decision.approved_spec is None:
        return IntentAcceptanceResult(IntentDecisionStatus.NEEDS_CLARIFICATION,
                                      diagnostics=("reviewer, consent and approved spec are required",))
    unknown = {answer.issue_id for answer in decision.answers} - {
        issue.issue_id for issue in review.issues}
    if unknown or any(not answer.text.strip() for answer in decision.answers):
        return IntentAcceptanceResult(IntentDecisionStatus.NEEDS_CLARIFICATION,
                                      diagnostics=("answers must address existing issues with nonempty text",))
    history = list(candidate.payload["source_history"])
    if decision.answers:
        version = max(item["version"] for item in history) + 1
        history.append({"version": version,
                        "messages": [answer.text for answer in decision.answers]})
    spec = decision.approved_spec
    errors = validate_intent_spec(spec, expected_history=history)
    if errors:
        return IntentAcceptanceResult(IntentDecisionStatus.NEEDS_CLARIFICATION,
                                      diagnostics=tuple(errors))
    if (spec.get("predicted_resolution") != "accepted_interpretation"
            or spec.get("required_clarifications")
            or any(claim.get("criticality") == "financial" and claim.get("status") in {
                "unresolved", "conflicted", "assumed"} for claim in spec.get("claims", []))):
        return IntentAcceptanceResult(IntentDecisionStatus.NEEDS_CLARIFICATION,
                                      diagnostics=("critical intent remains unresolved",))
    accepted = AcceptedIntentSpec(candidate.artifact_id, decision.reviewer_id,
                                  spec, decision.answers)
    return IntentAcceptanceResult(IntentDecisionStatus.ACCEPTED, accepted)


class IntentAcceptancePort:
    def __init__(self, reviewer_policy: ReviewerPolicy | None = None) -> None:
        self.reviewer_policy = reviewer_policy

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        candidate = latest_artifact(artifacts, "intent-candidate")
        if candidate is None:
            return StageExecution(StageResult("intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                              StageRunStatus.NOT_EVALUATED,
                                              diagnostics=["intent candidate unavailable"]))
        review = review_candidate(candidate)
        review_artifact = ArtifactEnvelope("intent-review", "v1", "intent_acceptance",
                                           ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                           AuthorityLevel.NO_AUTHORITY, review.to_dict())
        invalid = candidate.payload.get("core_validation_errors", []) + candidate.payload.get(
            "full_validation_errors", [])
        if invalid:
            return StageExecution(StageResult(
                "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.BLOCKED, input_artifacts=[candidate.artifact_id],
                diagnostics=["invalid Stage 2B candidate cannot be human-accepted", *invalid]),
                [review_artifact])
        raw_decision: Any = context.options.get("intent_decision")
        if isinstance(raw_decision, dict):
            raw_decision = IntentDecision(
                IntentDecisionStatus(raw_decision["status"]), raw_decision.get("reviewer_id", ""),
                bool(raw_decision.get("explicit_consent", False)),
                tuple(ClarificationAnswer(**item) for item in raw_decision.get("answers", [])),
                raw_decision.get("approved_spec"))
        if (isinstance(raw_decision, IntentDecision)
                and raw_decision.status == IntentDecisionStatus.ACCEPTED
                and (self.reviewer_policy is None
                     or not self.reviewer_policy.authorize(candidate, raw_decision))):
            return StageExecution(StageResult(
                "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.BLOCKED, input_artifacts=[candidate.artifact_id],
                diagnostics=["reviewer authorization policy missing or denied"]),
                [review_artifact])
        if (raw_decision is None
                and candidate.payload.get("semantic_core", {}).get(
                    "predicted_resolution") == "unsupported_for_current_study"):
            outcome = IntentAcceptanceResult(
                IntentDecisionStatus.UNSUPPORTED,
                diagnostics=("source-backed candidate requests unsupported behavior; "
                             "no contract was accepted or compiled",),
            )
        else:
            outcome = apply_decision(candidate, review, raw_decision)
        outputs = [review_artifact]
        status = StageRunStatus.WAITING_USER
        authority = AuthorityLevel.NO_AUTHORITY
        if outcome.accepted:
            answer_artifacts = [ArtifactEnvelope(
                "clarification-answer", "v1", "intent_acceptance",
                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                AuthorityLevel.NO_AUTHORITY,
                {"candidate_artifact_id": candidate.artifact_id,
                 "issue_id": answer.issue_id, "text": answer.text,
                 "reviewer_id": outcome.accepted.reviewer_id})
                for answer in outcome.accepted.answers]
            accepted_artifact, manifest_artifact = freeze_accepted_intent(
                outcome.accepted, tuple(item.artifact_id for item in answer_artifacts))
            outputs.extend((*answer_artifacts, accepted_artifact, manifest_artifact))
            status = StageRunStatus.SUCCEEDED
            authority = AuthorityLevel.USER_ACCEPTED_INTENT
        elif outcome.status == IntentDecisionStatus.UNSUPPORTED:
            status = StageRunStatus.UNSUPPORTED
        elif outcome.status == IntentDecisionStatus.REJECTED:
            status = StageRunStatus.BLOCKED
        return StageExecution(StageResult(
            "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED, status,
            semantic_status=outcome.status.value, input_artifacts=[candidate.artifact_id],
            diagnostics=list(outcome.diagnostics), authority_level=authority,
            limitations=["human acceptance is not compiler or ledger validation"]), outputs)


class ReviewerPolicy(Protocol):
    def authorize(self, candidate: ArtifactEnvelope, decision: IntentDecision) -> bool: ...
