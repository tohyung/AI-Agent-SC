"""LLM candidates never inherit deterministic compiler authority."""

from __future__ import annotations

from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.models import StepResult
from research.orchestration.ports import StepContext, StepExecution, latest_artifact
from research.orchestration.status import AuthorityLevel, ImplementationStatus, StepRunStatus


class CandidateGatePort:
    def execute(self, artifacts: list[ArtifactEnvelope], context: StepContext) -> StepExecution:
        contract = latest_artifact(artifacts, "contract-candidate")
        comparison = latest_artifact(artifacts, "reference-comparison")
        if contract is None:
            return StepExecution(StepResult(
                "compiler_authority", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.NOT_EVALUATED, diagnostics=["contract candidate unavailable"],
            ))
        outcome = ArtifactEnvelope(
            "compiler-authority-decision", "v2", "compiler_authority",
            ImplementationStatus.IMPLEMENTED_UNVALIDATED, AuthorityLevel.NO_AUTHORITY,
            {"status": "CANDIDATE_ONLY", "generation_mode": contract.payload.get("generation_mode"),
             "contract_artifact_id": contract.artifact_id,
             "comparison_id": comparison.artifact_id if comparison else None,
             "scope_limit": "LLM candidate has no deterministic compiler or ledger authority"},
        )
        return StepExecution(StepResult(
            "compiler_authority", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StepRunStatus.SUCCEEDED, semantic_status="CANDIDATE_ONLY",
            input_artifacts=[contract.artifact_id] + ([comparison.artifact_id] if comparison else []),
            limitations=["candidate-only is not a production authorization"],
        ), [outcome])
