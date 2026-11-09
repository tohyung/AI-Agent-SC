"""Counterexample candidates and repair suggestions are non-authoritative."""

from __future__ import annotations

from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.models import StepResult
from research.orchestration.ports import StepContext, StepExecution, latest_artifact
from research.orchestration.status import AuthorityLevel, ImplementationStatus, StepRunStatus


class AdversarialPort:
    def execute(self, artifacts: list[ArtifactEnvelope], context: StepContext) -> StepExecution:
        findings = latest_artifact(artifacts, "oracle-findings")
        if findings is None:
            return StepExecution(StepResult("adversarial_search", ImplementationStatus.SCAFFOLDED,
                                              StepRunStatus.NOT_EVALUATED))
        candidates = [{"finding": item, "repair_suggestion": None,
                       "automatic_repair_allowed": False}
                      for item in findings.payload["findings"] if item["verdict"] == "VIOLATED"]
        output = ArtifactEnvelope("adversarial-candidates", "v1", "adversarial_search",
                                  ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY,
                                  {"candidates": candidates, "search_performed": False,
                                   "source_findings_id": findings.artifact_id})
        return StepExecution(StepResult("adversarial_search", ImplementationStatus.SCAFFOLDED,
                                          StepRunStatus.SUCCEEDED,
                                          input_artifacts=[findings.artifact_id],
                                          limitations=["candidate selection only; no adversarial search performed"]), [output])
