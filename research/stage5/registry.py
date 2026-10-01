"""No candidate is promoted without an external checker and explicit review."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from research.architecture.artifacts import ArtifactEnvelope, stable_artifact_id
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus


class PropertyStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    VALIDATED_FOR_SCOPE = "VALIDATED_FOR_SCOPE"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class PropertyCandidate:
    property_id: str
    statement: str
    source_finding_id: str
    contract_artifact_id: str
    scope: dict[str, Any]
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


class PropertyChecker(Protocol):
    def check(self, candidate: PropertyCandidate) -> dict[str, Any]: ...


class PropertyRegistry:
    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, Any]]] = {}

    def add(self, candidate: PropertyCandidate, status: PropertyStatus,
            evidence_ids: list[str] | None = None, reviewer_id: str | None = None) -> None:
        evidence_ids = evidence_ids or []
        if status == PropertyStatus.VALIDATED_FOR_SCOPE and (not evidence_ids or not reviewer_id):
            raise ValueError("scoped validation needs checker evidence and explicit reviewer")
        history = self._history.setdefault(candidate.property_id, [])
        entry = {"candidate": candidate.to_dict(), "status": status.value,
                 "evidence_ids": list(evidence_ids), "reviewer_id": reviewer_id}
        if history and history[-1] == entry:
            return
        if history and candidate.version <= history[-1]["candidate"]["version"]:
            raise ValueError("property versions must increase")
        history.append(entry)

    def history(self, property_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(property_id, []))


class PropertyValidationPort:
    def __init__(self, checker: PropertyChecker | None = None,
                 registry: PropertyRegistry | None = None) -> None:
        self.checker = checker
        self.registry = registry or PropertyRegistry()

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        adversarial = latest_artifact(artifacts, "adversarial-candidates")
        contract = latest_artifact(artifacts, "contract-candidate")
        if adversarial is None or contract is None:
            return StageExecution(StageResult("property_validation", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED))
        candidates = []
        for item in adversarial.payload["candidates"]:
            finding = item["finding"]
            candidate = PropertyCandidate(
                stable_artifact_id("property-candidate", "v1", finding),
                f"Review oracle {finding['oracle_id']} violation on observed trace",
                finding["trace_id"], contract.artifact_id,
                {"trace_id": finding["trace_id"], "oracle_id": finding["oracle_id"]})
            self.registry.add(candidate, PropertyStatus.CANDIDATE)
            candidates.append(candidate.to_dict())
        output = ArtifactEnvelope("property-candidates", "v1", "property_validation",
                                  ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY,
                                  {"candidates": candidates, "validated": False,
                                   "checker_configured": self.checker is not None})
        return StageExecution(StageResult(
            "property_validation", ImplementationStatus.SCAFFOLDED,
            StageRunStatus.INCONCLUSIVE, input_artifacts=[adversarial.artifact_id],
            limitations=["property formalization/checker/review are not implemented"]), [output])
