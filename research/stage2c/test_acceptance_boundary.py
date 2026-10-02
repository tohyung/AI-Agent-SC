"""Stage 2C pauses and accepts only the reviewed candidate content."""

from copy import deepcopy

from research.architecture.artifacts import ArtifactEnvelope, canonical_json_v1
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import extract_core_view
from research.stage2c.acceptance import IntentAcceptancePort
from research.stage2c.models import IntentDecision, IntentDecisionStatus
from research.stage3.test_direct_payment_v1 import direct_payment_spec


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
    waiting = port.execute([candidate], StageContext("unit"))
    assert waiting.result.run_status == StageRunStatus.WAITING_USER
    approved = IntentDecision(IntentDecisionStatus.ACCEPTED, "unit-reviewer", True, (), spec)
    accepted = port.execute([candidate], StageContext("unit", {"intent_decision": approved}))
    assert accepted.result.run_status == StageRunStatus.SUCCEEDED
    assert next(item for item in accepted.artifacts
                if item.artifact_type == "accepted-intent").payload["accepted_spec"] == spec
    altered = deepcopy(spec)
    altered["claims"][-1]["value"] = "Carol"
    denied = port.execute([candidate], StageContext("unit", {"intent_decision": IntentDecision(
        IntentDecisionStatus.ACCEPTED, "unit-reviewer", True, (), altered)}))
    assert denied.result.run_status == StageRunStatus.BLOCKED
    assert not any(item.artifact_type == "accepted-intent" for item in denied.artifacts)
