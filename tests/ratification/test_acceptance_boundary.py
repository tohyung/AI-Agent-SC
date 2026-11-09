"""Ratification pauses and accepts only the reviewed candidate content."""

from copy import deepcopy

from research.orchestration.artifacts import ArtifactEnvelope, canonical_json_v1
from research.orchestration.ports import StepContext
from research.orchestration.status import AuthorityLevel, ImplementationStatus, StepRunStatus
from research.formalization.intent_spec import extract_core_view
from research.ratification.acceptance import IntentAcceptancePort
from research.ratification.models import IntentDecision, IntentDecisionStatus
from tests.synthesis.test_direct_payment_v1 import direct_payment_spec


class ExactReviewer:
    def authorize(self, candidate, decision):
        return (decision.reviewer_id == "unit-reviewer"
                and canonical_json_v1(decision.approved_spec)
                == canonical_json_v1(candidate.payload["intent_spec"]))


def test_pause_then_freeze_exact_candidate_only():
    spec = direct_payment_spec()
    candidate = ArtifactEnvelope("intent-candidate", "v1", "unit",
                                 ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                 AuthorityLevel.MODEL_CANDIDATE,
                                 {"intent_spec": spec, "source_history": spec["requirement_history"],
                                  "semantic_core": extract_core_view(spec), "core_validation_errors": [],
                                  "full_validation_errors": []})
    port = IntentAcceptancePort(ExactReviewer())
    waiting = port.execute([candidate], StepContext("unit"))
    assert waiting.result.run_status == StepRunStatus.WAITING_USER
    approved = IntentDecision(IntentDecisionStatus.ACCEPTED, "unit-reviewer", True, (), spec)
    accepted = port.execute([candidate], StepContext("unit", {"intent_decision": approved}))
    assert accepted.result.run_status == StepRunStatus.SUCCEEDED
    assert next(item for item in accepted.artifacts
                if item.artifact_type == "accepted-intent").payload["accepted_spec"] == spec
    altered = deepcopy(spec)
    altered["claims"][-1]["value"] = "Carol"
    denied = port.execute([candidate], StepContext("unit", {"intent_decision": IntentDecision(
        IntentDecisionStatus.ACCEPTED, "unit-reviewer", True, (), altered)}))
    assert denied.result.run_status == StepRunStatus.BLOCKED
    assert not any(item.artifact_type == "accepted-intent" for item in denied.artifacts)


def test_malformed_candidate_collections_block_review_without_crashing():
    candidate = ArtifactEnvelope("intent-candidate", "v1", "unit",
                                 ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                 AuthorityLevel.MODEL_CANDIDATE,
                                 {"intent_spec": {"claims": None,
                                                  "required_clarifications": None},
                                  "semantic_core": {},
                                  "core_validation_errors": ["invalid claims"],
                                  "full_validation_errors": []})
    outcome = IntentAcceptancePort().execute([candidate], StepContext("unit"))
    assert outcome.result.run_status == StepRunStatus.BLOCKED
    assert any("invalid claims" in issue["description"] for issue in
               outcome.artifacts[0].payload["issues"])


def test_structured_clarification_renders_question_not_python_dict():
    candidate = ArtifactEnvelope("intent-candidate", "v1", "unit",
                                 ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                 AuthorityLevel.MODEL_CANDIDATE,
                                 {"intent_spec": {"claims": [], "required_clarifications": [
                                     {"question": "When is the deposit due?"}]},
                                  "semantic_core": {"schema_version": "test"},
                                  "core_validation_errors": [], "full_validation_errors": []})
    outcome = IntentAcceptancePort().execute([candidate], StepContext("unit"))
    questions = [item["description"] for item in outcome.artifacts[0].payload["issues"]]
    assert "When is the deposit due?" in questions
    assert not any("{'question'" in item for item in questions)


def test_source_backed_unsupported_candidate_stops_without_user_acceptance():
    spec = direct_payment_spec()
    spec["predicted_resolution"] = "unsupported_for_current_study"
    candidate = ArtifactEnvelope(
        "intent-candidate", "v1", "unit",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED,
        AuthorityLevel.MODEL_CANDIDATE,
        {"intent_spec": spec, "semantic_core": extract_core_view(spec),
         "core_validation_errors": [], "full_validation_errors": []},
    )
    outcome = IntentAcceptancePort().execute([candidate], StepContext("unit"))
    assert outcome.result.run_status == StepRunStatus.UNSUPPORTED
    assert outcome.result.authority_level == AuthorityLevel.NO_AUTHORITY
    assert not any(item.artifact_type == "accepted-intent" for item in outcome.artifacts)
