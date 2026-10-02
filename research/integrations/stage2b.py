"""Preserve raw core, projection diagnostics, and model candidate provenance."""

from __future__ import annotations

from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus


class Stage2BExtractionPort:
    def __init__(self, model: Any | None = None) -> None:
        self.model = model

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        source = latest_artifact(artifacts, "requirement-history")
        if source is None or self.model is None:
            return StageExecution(StageResult("intent_extraction", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED,
                                              diagnostics=["shadow model not configured"]))
        from research.stage2b.projector import classify_projection, project_intent_spec
        from research.stage2b.shadow_extractor import IntentShadowExtractor

        history = source.payload
        try:
            core = IntentShadowExtractor(self.model).extract(history)
        except (RuntimeError, ValueError) as exc:
            from research.stage2b.model_errors import sanitized_model_error

            safe_error = sanitized_model_error(exc)
            return StageExecution(StageResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.FAILED, semantic_status="MODEL_ERROR",
                input_artifacts=[source.artifact_id],
                diagnostics=[f"model extraction failed: {safe_error['code']}"],
                safe_error=safe_error))
        core_errors = core.validation_errors(expected_history=history)
        try:
            projection = project_intent_spec(core, expected_history=history)
            full_errors = projection.intent_spec.validation_errors(expected_history=history)
            classification = classify_projection(core_errors, full_errors, projection.projection_diagnostics)
        except Exception:
            return StageExecution(StageResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.FAILED, semantic_status="PROJECTOR_BUG",
                input_artifacts=[source.artifact_id],
                diagnostics=["deterministic projection failed"]))
        payload = {"semantic_core": core.to_dict(), "intent_spec": projection.intent_spec.to_dict(),
                   "source_history": history, "source_artifact_id": source.artifact_id,
                   "core_validation_errors": core_errors, "full_validation_errors": full_errors,
                   "projection_diagnostics": projection.projection_diagnostics,
                   "projection_classification": classification}
        try:
            candidate = ArtifactEnvelope("intent-candidate", "v1", "intent_extraction",
                                         ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                         AuthorityLevel.MODEL_CANDIDATE, payload)
        except TypeError:
            return StageExecution(StageResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.FAILED, input_artifacts=[source.artifact_id],
                diagnostics=["model output is not canonical JSON"]))
        return StageExecution(StageResult(
            "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StageRunStatus.SUCCEEDED, semantic_status=classification,
            input_artifacts=[source.artifact_id],
            authority_level=AuthorityLevel.MODEL_CANDIDATE,
            diagnostics=core_errors + full_errors,
            limitations=["structural validity is not semantic acceptance"]), [candidate])
