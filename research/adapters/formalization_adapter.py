"""Preserve raw core, projection diagnostics, and model candidate provenance."""

from __future__ import annotations

from typing import Any

from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.models import StepResult
from research.orchestration.ports import StepContext, StepExecution, latest_artifact
from research.orchestration.status import AuthorityLevel, ImplementationStatus, StepRunStatus


class FormalizationPort:
    def __init__(self, model: Any | None = None) -> None:
        self.model = model

    def execute(self, artifacts: list[ArtifactEnvelope], context: StepContext) -> StepExecution:
        source = latest_artifact(artifacts, "requirement-history")
        if source is None or self.model is None:
            return StepExecution(StepResult("intent_extraction", ImplementationStatus.SCAFFOLDED,
                                              StepRunStatus.NOT_EVALUATED,
                                              diagnostics=["shadow model not configured"]))
        from research.formalization.projector import classify_projection, project_intent_spec
        from research.formalization.shadow_extractor import IntentShadowExtractor
        from research.formalization.intent_spec import CORE_SCHEMA_VERSION
        from research.formalization.repair_policy import REPAIR_POLICY_VERSION, diagnostic_codes

        history = source.payload
        call_start = getattr(self.model, "llm_calls", None)
        if context.options.get("formalization_method", "DCF") == "AFF":
            return self._execute_aff(source, history, context, call_start)
        try:
            repairs = context.options.get("max_core_validation_repairs", 0)
            extractor = IntentShadowExtractor(
                self.model,
                core_schema_version=context.options.get("core_schema_version", CORE_SCHEMA_VERSION),
            )
            if repairs:
                core, initial_errors = extractor.extract_with_validation_feedback(
                    history, max_repairs=repairs)
            else:
                core = extractor.extract(history)
                initial_errors = []
        except (RuntimeError, ValueError) as exc:
            from research.formalization.model_errors import sanitized_model_error

            safe_error = sanitized_model_error(exc)
            return StepExecution(StepResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, semantic_status="MODEL_ERROR",
                input_artifacts=[source.artifact_id],
                diagnostics=[f"model extraction failed: {safe_error['code']}"],
                safe_error=safe_error))
        core_errors = extractor.validation_errors(core, history)
        replay_metadata = getattr(self.model, "replay_metadata_for", None)
        if callable(replay_metadata):
            preserved_errors = replay_metadata(core.to_dict())
            if (isinstance(preserved_errors, list)
                    and all(isinstance(item, str) for item in preserved_errors)):
                initial_errors = preserved_errors
        try:
            projection = project_intent_spec(core, expected_history=history)
            full_errors = projection.intent_spec.validation_errors(expected_history=history)
            classification = classify_projection(core_errors, full_errors, projection.projection_diagnostics)
        except Exception:
            return StepExecution(StepResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, semantic_status="PROJECTOR_BUG",
                input_artifacts=[source.artifact_id],
                diagnostics=["deterministic projection failed"]))
        telemetry = {
            "repair_policy_version": REPAIR_POLICY_VERSION,
            "physical_calls": (getattr(self.model, "llm_calls", 0) - call_start
                               if type(call_start) is int else None),
            "initial_error_codes": diagnostic_codes(initial_errors),
            "final_error_codes": diagnostic_codes(core_errors),
            "final_error_count": len(set(core_errors)),
            "normalization_actions": extractor.normalization_actions,
            "repair_trace": extractor.repair_trace,
        }
        payload = {"semantic_core": core.to_dict(), "intent_spec": projection.intent_spec.to_dict(),
                   "initial_core_validation_errors": initial_errors,
                   "source_history": history, "source_artifact_id": source.artifact_id,
                   "core_validation_errors": core_errors, "full_validation_errors": full_errors,
                   "projection_diagnostics": projection.projection_diagnostics,
                   "projection_classification": classification}
        try:
            candidate = ArtifactEnvelope("intent-candidate", "v1", "intent_extraction",
                                         ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                         AuthorityLevel.MODEL_CANDIDATE, payload)
        except TypeError:
            return StepExecution(StepResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, input_artifacts=[source.artifact_id],
                diagnostics=["model output is not canonical JSON"]))
        return StepExecution(StepResult(
            "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StepRunStatus.SUCCEEDED, semantic_status=classification,
            input_artifacts=[source.artifact_id],
            authority_level=AuthorityLevel.MODEL_CANDIDATE,
            telemetry=telemetry,
            diagnostics=core_errors + full_errors,
            limitations=["structural validity is not semantic acceptance"]), [candidate])

    def _execute_aff(self, source: ArtifactEnvelope, history: Any, context: StepContext,
                     call_start: Any) -> StepExecution:
        """AFF (E4): the model writes a FactDraft, the deterministic builder makes the core.

        Draft problems are repaired through the model (up to `max_draft_repairs`, default 3); a core
        the builder made that still fails validation is a builder bug, never repaired by the model.
        """
        from research.formalization.fact_extractor import FACT_PROMPT_VERSION, extract_fact_core
        from research.formalization.projector import project_intent_spec

        def calls() -> int | None:
            return (getattr(self.model, "llm_calls", 0) - call_start
                    if type(call_start) is int else None)

        try:
            result = extract_fact_core(self.model, history,
                                       max_repairs=context.options.get("max_draft_repairs", 3))
        except (RuntimeError, ValueError) as exc:
            from research.formalization.model_errors import sanitized_model_error

            safe_error = sanitized_model_error(exc)
            return StepExecution(StepResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, semantic_status="MODEL_ERROR",
                input_artifacts=[source.artifact_id],
                diagnostics=[f"model extraction failed: {safe_error['code']}"],
                safe_error=safe_error, telemetry={"formalization_method": "AFF",
                                                  "physical_calls": calls()}))
        problems = [f"{item}: {message}" for attempt in result["attempts"]
                    for item, message in attempt["problems"]]
        telemetry = {"formalization_method": "AFF", "fact_prompt_version": FACT_PROMPT_VERSION,
                     "physical_calls": calls(), "draft_attempts": len(result["attempts"]),
                     "draft_problem_count": len(problems), "builder_bug": result["builder_bug"]}
        core = result["semantic_core"]
        if core is None:
            return StepExecution(StepResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, semantic_status="DRAFT_INVALID",
                input_artifacts=[source.artifact_id], telemetry=telemetry,
                diagnostics=problems[-20:] or ["no valid FactDraft"]))
        try:
            projection = project_intent_spec(core, expected_history=history)
        except Exception:
            return StepExecution(StepResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, semantic_status="PROJECTOR_BUG",
                input_artifacts=[source.artifact_id], telemetry=telemetry,
                diagnostics=["deterministic projection failed"]))
        core_errors = result["core_validation_errors"]
        full_errors = result["full_validation_errors"]
        classification = result["projection_classification"]
        payload = {"semantic_core": core, "intent_spec": projection.intent_spec.to_dict(),
                   "initial_core_validation_errors": [],
                   "source_history": history, "source_artifact_id": source.artifact_id,
                   "core_validation_errors": core_errors, "full_validation_errors": full_errors,
                   "projection_diagnostics": projection.projection_diagnostics,
                   "projection_classification": classification,
                   "formalization_method": "AFF", "fact_drafts": result["attempts"]}
        try:
            candidate = ArtifactEnvelope("intent-candidate", "v1", "intent_extraction",
                                         ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                         AuthorityLevel.MODEL_CANDIDATE, payload)
        except TypeError:
            return StepExecution(StepResult(
                "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, input_artifacts=[source.artifact_id], telemetry=telemetry,
                diagnostics=["model output is not canonical JSON"]))
        return StepExecution(StepResult(
            "intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StepRunStatus.SUCCEEDED, semantic_status=classification,
            input_artifacts=[source.artifact_id], authority_level=AuthorityLevel.MODEL_CANDIDATE,
            telemetry=telemetry, diagnostics=core_errors + full_errors,
            limitations=["structural validity is not semantic acceptance"]), [candidate])
