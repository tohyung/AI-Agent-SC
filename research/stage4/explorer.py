"""Enumerate explicit transaction domains using pinned reference transitions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from research.architecture.artifacts import ArtifactEnvelope, stable_artifact_id
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import (AuthorityLevel, CoverageStatus,
                                          ImplementationStatus, StageRunStatus)
from research.stage3.reference import ReferenceExecutor, ReferenceRequest


class TransactionDomain(Protocol):
    domain_id: str
    finite: bool

    def transactions(self, state: dict[str, Any], contract: Any) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class ExplorationBounds:
    max_depth: int = 3
    max_traces: int = 100


def explore(contract: Any, initial_state: dict[str, Any], domain: TransactionDomain,
            reference: ReferenceExecutor, bounds: ExplorationBounds) -> dict[str, Any]:
    if bounds.max_depth < 1 or bounds.max_traces < 1:
        raise ValueError("exploration bounds must be positive")
    frontier = deque([(contract, initial_state, [], [])])
    traces: list[dict[str, Any]] = []
    truncated = False
    while frontier:
        current, state, transactions, steps = frontier.popleft()
        if len(transactions) >= bounds.max_depth:
            if domain.transactions(state, current):
                truncated = True
            continue
        for transaction in domain.transactions(state, current):
            if len(traces) >= bounds.max_traces:
                truncated = True
                break
            result = reference.execute(ReferenceRequest(current, state, (transaction,)))
            status = result.get("status", "Unknown")
            trace = {"transactions": transactions + [transaction],
                     "steps": steps + [result], "status": status}
            trace["trace_id"] = stable_artifact_id("reference-trace", "v1", trace)
            traces.append(trace)
            if status == "Success":
                final_state = result.get("final_state")
                final_contract = result.get("final_contract")
                if final_state is None or final_contract is None:
                    truncated = True
                else:
                    frontier.append((final_contract, final_state,
                                     trace["transactions"], trace["steps"]))
            elif status not in {"TransactionError"}:
                truncated = True
        if len(traces) >= bounds.max_traces:
            break
    coverage = CoverageStatus.BOUNDED
    return {"domain_id": domain.domain_id, "bounds": vars(bounds),
            "coverage": coverage.value, "truncated": truncated, "traces": traces,
            "enumeration_exhausted": bool(domain.finite and not truncated),
            "limitations": ["domain completeness is relative to the supplied transaction generator",
                            "finite trace coverage is not ledger validation"]}


class ExplorationPort:
    def __init__(self, domain: TransactionDomain | None = None,
                 reference: ReferenceExecutor | None = None,
                 initial_state: dict[str, Any] | None = None,
                 bounds: ExplorationBounds = ExplorationBounds()) -> None:
        self.domain = domain
        self.reference = reference
        self.initial_state = initial_state
        self.bounds = bounds

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        contract = latest_artifact(artifacts, "contract-candidate")
        if contract is None or self.domain is None or self.reference is None or self.initial_state is None:
            return StageExecution(StageResult("exploration", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED,
                                              diagnostics=["contract, domain, state or reference unavailable"]))
        graph = explore(contract.payload["contract"], self.initial_state,
                        self.domain, self.reference, self.bounds)
        output = ArtifactEnvelope("exploration-graph", "v1", "exploration",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY, graph)
        evaluated = bool(graph["traces"]) and all(
            trace["status"] in {"Success", "TransactionError"}
            for trace in graph["traces"])
        return StageExecution(StageResult(
            "exploration", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StageRunStatus.SUCCEEDED if evaluated else StageRunStatus.INCONCLUSIVE,
            semantic_status="BOUNDED_TRACES" if evaluated else "NO_RELIABLE_TRACES",
            input_artifacts=[contract.artifact_id],
            diagnostics=[] if evaluated else ["no reliable reference traces in declared domain"],
            limitations=graph["limitations"]), [output])
