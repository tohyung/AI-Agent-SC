"""Compare only against independently sourced, reviewed behavioral expectations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus

from .reference import ReferenceExecutor, ReferenceRequest


@dataclass(frozen=True)
class BehaviorExpectation:
    source_artifact_id: str
    source_kind: str
    request: ReferenceRequest
    expected_status: str
    expected_final_contract: Any | None = None
    reviewer_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"source_artifact_id": self.source_artifact_id, "source_kind": self.source_kind,
                "request": self.request.to_dict(), "expected_status": self.expected_status,
                "expected_final_contract": self.expected_final_contract,
                "reviewer_id": self.reviewer_id}


class SemanticComparisonPort:
    def __init__(self, executor: ReferenceExecutor | None = None,
                 expectation_policy: ExpectationPolicy | None = None) -> None:
        self.executor = executor
        self.expectation_policy = expectation_policy

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        contract = latest_artifact(artifacts, "contract-candidate")
        accepted = latest_artifact(artifacts, "accepted-intent")
        if contract is None or accepted is None:
            return StageExecution(StageResult("semantic_comparison", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED,
                                              diagnostics=["contract or accepted intent missing"]))
        expectation_artifact = latest_artifact(artifacts, "behavior-expectation")
        if expectation_artifact is None or self.executor is None:
            return StageExecution(StageResult("semantic_comparison", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.INCONCLUSIVE,
                                              input_artifacts=[contract.artifact_id, accepted.artifact_id],
                                              diagnostics=["independent expectation or reference executor unavailable"]))
        source_payload = expectation_artifact.payload
        request_payload = source_payload.get("request", {})
        if (not isinstance(request_payload, dict) or request_payload.get("contract") is not None
                or not isinstance(request_payload.get("state"), dict)
                or not isinstance(request_payload.get("transactions"), list)
                or source_payload.get("expected_status") not in {"Success", "TransactionError"}
                or self.expectation_policy is None
                or not self.expectation_policy.authorize(expectation_artifact)):
            return StageExecution(StageResult("semantic_comparison", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                              StageRunStatus.BLOCKED,
                                              diagnostics=["expectation shape or reviewer policy invalid"]))
        expectation = BehaviorExpectation(
            source_payload.get("source_artifact_id", ""), source_payload.get("source_kind", ""),
            ReferenceRequest(request_payload.get("contract"), request_payload.get("state", {}),
                             tuple(request_payload.get("transactions", []))),
            source_payload.get("expected_status", ""),
            source_payload.get("expected_final_contract"), source_payload.get("reviewer_id"))
        sources = {item.artifact_id: item for item in artifacts}
        source = sources.get(expectation.source_artifact_id)
        allowed_source = (
            (expectation.source_kind == "accepted_intent"
             and expectation.source_artifact_id == accepted.artifact_id)
            or (expectation.source_kind == "reviewed_profile"
                and source is not None and source.artifact_type == "reviewed-profile"
                and bool(source.payload.get("reviewer_id")))
            or (expectation.source_kind == "reviewed_scenario"
                and source is not None and source.artifact_type == "reviewed-scenario"
                and bool(source.payload.get("reviewer_id")))
        )
        if (not allowed_source or not expectation.reviewer_id
                or expectation.source_artifact_id == contract.artifact_id):
            return StageExecution(StageResult("semantic_comparison", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                              StageRunStatus.BLOCKED,
                                              diagnostics=["expectation source is not independent accepted evidence"]))
        request = ReferenceRequest(contract.payload["contract"], expectation.request.state,
                                   expectation.request.transactions)
        raw = self.executor.execute(request)
        status = str(raw.get("status", "Unknown"))
        meta = raw.get("meta", {})
        reference_identity = (f"{meta.get('upstream_commit')}:{meta.get('reference_driver_version')}"
                              if isinstance(meta, dict) and meta.get("upstream_commit")
                              and meta.get("reference_driver_version") else None)
        if status in {"Unavailable", "Timeout", "InternalError", "Unsupported", "InvalidInput"}:
            run_status = StageRunStatus.UNAVAILABLE if status in {"Unavailable", "Timeout"} else StageRunStatus.INCONCLUSIVE
            verdict = "INCONCLUSIVE"
        elif status not in {"Success", "TransactionError"} or reference_identity is None:
            run_status = StageRunStatus.INCONCLUSIVE
            verdict = "INCONCLUSIVE"
        else:
            observed = raw.get("final_contract", raw.get("finalContract"))
            same = status == expectation.expected_status
            if expectation.expected_final_contract is not None:
                same = same and observed == expectation.expected_final_contract
            verdict = "SATISFIED" if same else "VIOLATED"
            run_status = StageRunStatus.SUCCEEDED if same else StageRunStatus.FAILED
        result = ArtifactEnvelope("reference-comparison", "v1", "semantic_comparison",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY,
                                  {"reference_result": raw, "reference_identity": reference_identity,
                                   "expectation": expectation.to_dict(),
                                   "verdict": verdict, "contract_artifact_id": contract.artifact_id})
        return StageExecution(StageResult(
            "semantic_comparison", ImplementationStatus.IMPLEMENTED_UNVALIDATED, run_status,
            semantic_status=verdict, input_artifacts=[contract.artifact_id, accepted.artifact_id,
                                                     expectation_artifact.artifact_id],
            limitations=["one reference trace is not compiler proof or ledger validity"]), [result])


class ExpectationPolicy(Protocol):
    def authorize(self, expectation_artifact: ArtifactEnvelope) -> bool: ...
