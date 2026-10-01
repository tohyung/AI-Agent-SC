"""Counterexample candidates and repair suggestions are non-authoritative."""

from __future__ import annotations

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus


class AdversarialPort:
    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        findings = latest_artifact(artifacts, "oracle-findings")
        if findings is None:
            return StageExecution(StageResult("adversarial_search", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED))
        candidates = [{"finding": item, "repair_suggestion": None,
                       "automatic_repair_allowed": False}
                      for item in findings.payload["findings"] if item["verdict"] == "VIOLATED"]
        output = ArtifactEnvelope("adversarial-candidates", "v1", "adversarial_search",
                                  ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY,
                                  {"candidates": candidates, "search_performed": False,
                                   "source_findings_id": findings.artifact_id})
        return StageExecution(StageResult("adversarial_search", ImplementationStatus.SCAFFOLDED,
                                          StageRunStatus.SUCCEEDED,
                                          input_artifacts=[findings.artifact_id],
                                          limitations=["candidate selection only; no adversarial search performed"]), [output])
