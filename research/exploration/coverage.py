"""Coverage accounting preserves domain and truncation limits."""

from __future__ import annotations

from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.models import StepResult
from research.orchestration.ports import StepContext, StepExecution, latest_artifact
from research.orchestration.status import AuthorityLevel, ImplementationStatus, StepRunStatus


class CoveragePort:
    def execute(self, artifacts: list[ArtifactEnvelope], context: StepContext) -> StepExecution:
        graph = latest_artifact(artifacts, "exploration-graph")
        findings = latest_artifact(artifacts, "oracle-findings")
        if graph is None or findings is None:
            return StepExecution(StepResult("coverage", ImplementationStatus.SCAFFOLDED,
                                              StepRunStatus.NOT_EVALUATED))
        report = {"domain_id": graph.payload["domain_id"],
                  "coverage": graph.payload["coverage"],
                  "truncated": graph.payload["truncated"],
                  "trace_count": len(graph.payload["traces"]),
                  "oracle_finding_count": len(findings.payload["findings"]),
                  "graph_id": graph.artifact_id, "findings_id": findings.artifact_id}
        output = ArtifactEnvelope("coverage-report", "v1", "coverage",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY, report)
        return StepExecution(StepResult("coverage", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                          StepRunStatus.SUCCEEDED,
                                          input_artifacts=[graph.artifact_id, findings.artifact_id],
                                          limitations=["coverage is only over the declared domain"]), [output])
