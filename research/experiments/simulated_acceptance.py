"""Batch-only customer simulation boundary; never grants human intent authority."""

from __future__ import annotations

from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import validate_intent_spec


class SimulatedIntentAcceptancePort:
    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        candidate = latest_artifact(artifacts, "intent-candidate")
        if candidate is None:
            return StageExecution(StageResult(
                "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.NOT_EVALUATED, diagnostics=["intent candidate unavailable"]))
        payload = candidate.payload
        spec = payload.get("intent_spec")
        history = payload.get("source_history")
        errors = list(payload.get("core_validation_errors") or []) + list(
            payload.get("full_validation_errors") or [])
        errors.extend(validate_intent_spec(spec, expected_history=history))
        if errors:
            return StageExecution(StageResult(
                "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.BLOCKED, input_artifacts=[candidate.artifact_id],
                diagnostics=["invalid model candidate", *errors]))
        if (spec.get("predicted_resolution") != "accepted_interpretation"
                or spec.get("required_clarifications")
                or any(claim.get("criticality") == "financial" and claim.get("status") in {
                    "unresolved", "conflicted", "assumed"} for claim in spec["claims"])):
            return StageExecution(StageResult(
                "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.WAITING_USER, input_artifacts=[candidate.artifact_id],
                diagnostics=["simulated customer must answer unresolved intent first"]))
        transcript: Any = context.options.get("simulation_transcript", [])
        if (not isinstance(transcript, list)
                or any(not isinstance(item, dict) or not isinstance(item.get("question"), str)
                       or not item["question"].strip() or not isinstance(item.get("answer"), str)
                       or not item["answer"].strip()
                       or not isinstance(item.get("synthetic_assumption"), bool)
                       for item in transcript)):
            return StageExecution(StageResult(
                "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.BLOCKED, input_artifacts=[candidate.artifact_id],
                diagnostics=["invalid simulated customer transcript"]))
        later_messages = [message for revision in history[1:]
                          for message in revision["messages"]]
        if any(item["answer"] not in later_messages for item in transcript):
            return StageExecution(StageResult(
                "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.BLOCKED, input_artifacts=[candidate.artifact_id],
                diagnostics=["simulated answer absent from requirement history"]))
        accepted = ArtifactEnvelope(
            "accepted-intent", "simulated-v1", "intent_acceptance",
            ImplementationStatus.IMPLEMENTED_UNVALIDATED, AuthorityLevel.NO_AUTHORITY,
            {"accepted_spec": spec, "candidate_artifact_id": candidate.artifact_id,
             "simulation_only": True, "simulation_transcript": transcript})
        return StageExecution(StageResult(
            "intent_acceptance", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StageRunStatus.SUCCEEDED, semantic_status="SIMULATED_CUSTOMER_ACCEPTED",
            input_artifacts=[candidate.artifact_id],
            authority_level=AuthorityLevel.NO_AUTHORITY,
            limitations=["simulated customer is tuning evidence, not human acceptance"]),
            [accepted])
