"""Coverage accounting preserves domain and truncation limits."""

from __future__ import annotations

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus


class CoveragePort:
    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        graph = latest_artifact(artifacts, "exploration-graph")
        findings = latest_artifact(artifacts, "oracle-findings")
        if graph is None or findings is None:
            return StageExecution(StageResult("coverage", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED))
        report = {"domain_id": graph.payload["domain_id"],
                  "coverage": graph.payload["coverage"],
                  "truncated": graph.payload["truncated"],
                  "trace_count": len(graph.payload["traces"]),
                  "oracle_finding_count": len(findings.payload["findings"]),
                  "graph_id": graph.artifact_id, "findings_id": findings.artifact_id}
        output = ArtifactEnvelope("coverage-report", "v1", "coverage",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY, report)
        return StageExecution(StageResult("coverage", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                          StageRunStatus.SUCCEEDED,
                                          input_artifacts=[graph.artifact_id, findings.artifact_id],
                                          limitations=["coverage is only over the declared domain"]), [output])
