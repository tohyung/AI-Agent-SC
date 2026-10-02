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
    expected_final_state: dict[str, Any] | None = None
    expected_warnings: tuple[dict[str, Any], ...] | None = None
    expected_payments: tuple[dict[str, Any], ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {"source_artifact_id": self.source_artifact_id, "source_kind": self.source_kind,
                  "request": self.request.to_dict(), "expected_status": self.expected_status,
                  "expected_final_contract": self.expected_final_contract,
                  "reviewer_id": self.reviewer_id}
        if self.expected_final_state is not None:
            result["expected_final_state"] = self.expected_final_state
        if self.expected_warnings is not None:
            result["expected_warnings"] = list(self.expected_warnings)
        if self.expected_payments is not None:
            result["expected_payments"] = list(self.expected_payments)
        return result


def _observed_items(raw: dict[str, Any], field: str) -> list[dict[str, Any]] | None:
    steps = raw.get("steps")
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        return None
    successful = [step for step in steps if step.get("status") == "Success"]
    if not successful:
        return None
    items: list[dict[str, Any]] = []
    for step in successful:
        values = step.get(field)
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            return None
        items.extend(values)
    return items


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
        optional_shapes_valid = (
            ("expected_final_state" not in source_payload
             or isinstance(source_payload["expected_final_state"], dict))
            and all(key not in source_payload or (
                isinstance(source_payload[key], list)
                and all(isinstance(item, dict) for item in source_payload[key]))
                for key in ("expected_warnings", "expected_payments")))
        if (not isinstance(request_payload, dict) or request_payload.get("contract") is not None
                or not isinstance(request_payload.get("state"), dict)
                or not isinstance(request_payload.get("transactions"), list)
                or not optional_shapes_valid
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
            source_payload.get("expected_final_contract"), source_payload.get("reviewer_id"),
            source_payload.get("expected_final_state"),
            (tuple(source_payload["expected_warnings"])
             if "expected_warnings" in source_payload else None),
            (tuple(source_payload["expected_payments"])
             if "expected_payments" in source_payload else None))
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
        mismatches: list[str] = []
        unavailable: list[str] = []
        if status in {"Unavailable", "Timeout", "InternalError", "Unsupported", "InvalidInput"}:
            run_status = StageRunStatus.UNAVAILABLE if status in {"Unavailable", "Timeout"} else StageRunStatus.INCONCLUSIVE
            verdict = "INCONCLUSIVE"
        elif status not in {"Success", "TransactionError"} or reference_identity is None:
            run_status = StageRunStatus.INCONCLUSIVE
            verdict = "INCONCLUSIVE"
        else:
            observed = raw.get("final_contract", raw.get("finalContract"))
            if status != expectation.expected_status:
                mismatches.append("status")
            if expectation.expected_final_contract is not None:
                if observed is None:
                    if any(value is not None for value in (
                            expectation.expected_final_state,
                            expectation.expected_warnings, expectation.expected_payments)):
                        unavailable.append("final_contract")
                    else:
                        mismatches.append("final_contract")
                elif observed != expectation.expected_final_contract:
                    mismatches.append("final_contract")
            if expectation.expected_final_state is not None:
                final_state = raw.get("final_state")
                if not isinstance(final_state, dict):
                    unavailable.append("final_state")
                elif final_state != expectation.expected_final_state:
                    mismatches.append("final_state")
            for field, expected_items in (("warnings", expectation.expected_warnings),
                                          ("payments", expectation.expected_payments)):
                if expected_items is None:
                    continue
                observed_items = _observed_items(raw, field)
                if observed_items is None:
                    unavailable.append(field)
                elif observed_items != list(expected_items):
                    mismatches.append(field)
            if unavailable:
                verdict, run_status = "INCONCLUSIVE", StageRunStatus.INCONCLUSIVE
            elif mismatches:
                verdict, run_status = "VIOLATED", StageRunStatus.FAILED
            else:
                verdict, run_status = "SATISFIED", StageRunStatus.SUCCEEDED
        payload = {"reference_result": raw, "reference_identity": reference_identity,
                   "expectation": expectation.to_dict(), "verdict": verdict,
                   "contract_artifact_id": contract.artifact_id}
        if mismatches:
            payload["mismatches"] = mismatches
        if unavailable:
            payload["unavailable_observables"] = unavailable
        result = ArtifactEnvelope("reference-comparison", "v1", "semantic_comparison",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY, payload)
        return StageExecution(StageResult(
            "semantic_comparison", ImplementationStatus.IMPLEMENTED_UNVALIDATED, run_status,
            semantic_status=verdict, input_artifacts=[contract.artifact_id, accepted.artifact_id,
                                                     expectation_artifact.artifact_id],
            diagnostics=[f"observable mismatch: {field}" for field in mismatches]
                        + [f"observable unavailable: {field}" for field in unavailable],
            limitations=["one reference trace is not compiler proof or ledger validity"]), [result])


class ExpectationPolicy(Protocol):
    def authorize(self, expectation_artifact: ArtifactEnvelope) -> bool: ...
