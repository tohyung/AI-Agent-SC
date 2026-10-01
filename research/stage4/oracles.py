"""Trace-local oracle results do not establish a universal property."""

from __future__ import annotations

from typing import Any, Protocol

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import (AssuranceVerdict, AuthorityLevel,
                                          ImplementationStatus, StageRunStatus)


class TraceOracle(Protocol):
    oracle_id: str

    def evaluate(self, trace: dict[str, Any]) -> dict[str, Any]: ...


class NoWarningsOracle:
    oracle_id = "no-transaction-warning-v1"

    def evaluate(self, trace: dict[str, Any]) -> dict[str, Any]:
        if trace["status"] != "Success":
            verdict = AssuranceVerdict.NOT_EVALUATED
        else:
            steps = [item for response in trace["steps"] for item in response.get("steps", [])]
            if not steps or any(not isinstance(item.get("warnings"), list) for item in steps):
                verdict = AssuranceVerdict.INCONCLUSIVE
            else:
                verdict = (AssuranceVerdict.VIOLATED if any(item["warnings"] for item in steps)
                           else AssuranceVerdict.SATISFIED)
        return {"trace_id": trace["trace_id"], "oracle_id": self.oracle_id,
                "verdict": verdict.value}


class OraclePort:
    def __init__(self, oracles: list[TraceOracle] | None = None) -> None:
        self.oracles = list(oracles or [])

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        graph = latest_artifact(artifacts, "exploration-graph")
        if graph is None or not self.oracles:
            return StageExecution(StageResult("oracle_evaluation", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED,
                                              diagnostics=["exploration graph or oracle unavailable"]))
        findings = [oracle.evaluate(trace) for trace in graph.payload["traces"]
                    for oracle in self.oracles]
        output = ArtifactEnvelope("oracle-findings", "v1", "oracle_evaluation",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY,
                                  {"graph_id": graph.artifact_id, "findings": findings,
                                   "scope": "observed traces only"})
        return StageExecution(StageResult(
            "oracle_evaluation", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StageRunStatus.SUCCEEDED, input_artifacts=[graph.artifact_id],
            limitations=["a SATISFIED trace is not universal proof"]), [output])
