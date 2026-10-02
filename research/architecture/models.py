"""Stage records; domain results live in their owning stage packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .assurance import AssuranceClaim
from .status import AuthorityLevel, ImplementationStatus, StageRunStatus


@dataclass
class StageResult:
    stage: str
    implementation_status: ImplementationStatus
    run_status: StageRunStatus
    semantic_status: str | None = None
    input_artifacts: list[str] = field(default_factory=list)
    output_artifacts: list[str] = field(default_factory=list)
    assurance_claims: list[AssuranceClaim] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    authority_level: AuthorityLevel = AuthorityLevel.NO_AUTHORITY
    safe_error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"stage": self.stage, "implementation_status": self.implementation_status.value,
                "run_status": self.run_status.value, "semantic_status": self.semantic_status,
                "input_artifacts": list(self.input_artifacts),
                "output_artifacts": list(self.output_artifacts),
                "assurance_claims": [claim.to_dict() for claim in self.assurance_claims],
                "diagnostics": list(self.diagnostics), "limitations": list(self.limitations),
                "blocked_by": list(self.blocked_by), "authority_level": self.authority_level.value}
        if self.safe_error is not None:
            allowed = {"code", "phase", "message", "model_content_received",
                       "repair_attempted", "exception_type"}
            if set(self.safe_error) != allowed:
                raise ValueError("safe_error must use the closed normalized schema")
            result["safe_error"] = dict(self.safe_error)
        return result


@dataclass
class ResearchPipelineRun:
    run_id: str
    requirement_artifact_id: str
    stages: dict[str, StageResult] = field(default_factory=dict)
    provenance_edges: list[str] = field(default_factory=list)
    provenance_records: dict[str, dict[str, str]] = field(default_factory=dict)
    stage_executions: int = 0
    external_artifact_ids: list[str] = field(default_factory=list)
    entry_stage: str = "intent_extraction"

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "requirement_artifact_id": self.requirement_artifact_id,
                "entry_stage": self.entry_stage,
                "stages": {key: value.to_dict() for key, value in self.stages.items()},
                "provenance_edges": list(self.provenance_edges),
                "provenance_records": dict(self.provenance_records),
            "stage_executions": self.stage_executions,
            "external_artifact_ids": list(self.external_artifact_ids)}
