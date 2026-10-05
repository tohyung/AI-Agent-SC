"""LLM candidates never inherit deterministic compiler authority."""

from __future__ import annotations

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus


class CandidateGatePort:
    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        contract = latest_artifact(artifacts, "contract-candidate")
        comparison = latest_artifact(artifacts, "reference-comparison")
        if contract is None:
            return StageExecution(StageResult(
                "compiler_authority", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.NOT_EVALUATED, diagnostics=["contract candidate unavailable"],
            ))
        outcome = ArtifactEnvelope(
            "compiler-authority-decision", "v2", "compiler_authority",
            ImplementationStatus.IMPLEMENTED_UNVALIDATED, AuthorityLevel.NO_AUTHORITY,
            {"status": "CANDIDATE_ONLY", "generation_mode": contract.payload.get("generation_mode"),
             "contract_artifact_id": contract.artifact_id,
             "comparison_id": comparison.artifact_id if comparison else None,
             "scope_limit": "LLM candidate has no deterministic compiler or ledger authority"},
        )
        return StageExecution(StageResult(
            "compiler_authority", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StageRunStatus.SUCCEEDED, semantic_status="CANDIDATE_ONLY",
            input_artifacts=[contract.artifact_id] + ([comparison.artifact_id] if comparison else []),
            limitations=["candidate-only is not a production authorization"],
        ), [outcome])
