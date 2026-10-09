"""No candidate is promoted without an external checker and explicit review."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from copy import deepcopy
from typing import Any, Protocol

from research.architecture.artifacts import ArtifactEnvelope, stable_artifact_id
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus

from .dataset import PropertyDataset


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
    def check(self, candidate: PropertyCandidate) -> PropertyCheckResult: ...


@dataclass(frozen=True)
class PropertyCheckResult:
    status: PropertyStatus
    evidence_ids: tuple[str, ...] = ()
    reviewer_id: str | None = None
    diagnostics: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {PropertyStatus.VALIDATED_FOR_SCOPE,
                               PropertyStatus.REFUTED, PropertyStatus.INCONCLUSIVE}:
            raise ValueError("checker must return a check outcome")


class PropertyRegistry:
    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, Any]]] = {}

    def add(self, candidate: PropertyCandidate, status: PropertyStatus,
            evidence_ids: list[str] | None = None, reviewer_id: str | None = None) -> None:
        evidence_ids = evidence_ids or []
        if status in {PropertyStatus.VALIDATED_FOR_SCOPE, PropertyStatus.REFUTED} and (
                not evidence_ids or not reviewer_id):
            raise ValueError("terminal property outcome needs evidence and explicit reviewer")
        history = self._history.setdefault(candidate.property_id, [])
        entry = {"candidate": candidate.to_dict(), "status": status.value,
                 "evidence_ids": list(evidence_ids), "reviewer_id": reviewer_id}
        if history:
            latest = history[-1]["candidate"]
            if candidate.version < latest["version"]:
                raise ValueError("older property version cannot supersede newer version")
            if candidate.version == latest["version"] and candidate.to_dict() != latest:
                raise ValueError("same property version has different candidate content")
        if entry in history:
            return
        history.append(deepcopy(entry))

    def history(self, property_id: str) -> list[dict[str, Any]]:
        return deepcopy(self._history.get(property_id, []))


class PropertyValidationPort:
    def __init__(self, checker: PropertyChecker | None = None,
                 registry: PropertyRegistry | None = None,
                 dataset: PropertyDataset | None = None) -> None:
        self.checker = checker
        self.registry = registry or PropertyRegistry()
        self.dataset = dataset

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        adversarial = latest_artifact(artifacts, "adversarial-candidates")
        contract = latest_artifact(artifacts, "contract-candidate")
        if adversarial is None or contract is None:
            return StageExecution(StageResult("property_validation", ImplementationStatus.SCAFFOLDED,
                                              StageRunStatus.NOT_EVALUATED))
        observation_ids = (self.dataset.ingest_artifacts(artifacts, context.run_id)
                           if self.dataset is not None else [])
        candidates = []
        outcomes = []
        diagnostics = []
        for item in adversarial.payload["candidates"]:
            finding = item["finding"]
            candidate = PropertyCandidate(
                stable_artifact_id("property-candidate", "v1", {
                    "finding": finding, "contract_artifact_id": contract.artifact_id}),
                f"Review oracle {finding['oracle_id']} violation on observed trace",
                finding["trace_id"], contract.artifact_id,
                {"trace_id": finding["trace_id"], "oracle_id": finding["oracle_id"]})
            self.registry.add(candidate, PropertyStatus.CANDIDATE)
            if self.dataset is not None:
                self.dataset.record_property_candidate(candidate.to_dict(), context.run_id)
            candidates.append(candidate.to_dict())
            if self.checker is not None:
                check = self.checker.check(candidate)
                if not isinstance(check, PropertyCheckResult):
                    raise TypeError("property checker must return PropertyCheckResult")
                self.registry.add(candidate, check.status, list(check.evidence_ids), check.reviewer_id)
                if self.dataset is not None:
                    self.dataset.record_checker_outcome(
                        candidate.property_id, status=check.status.value,
                        evidence_ids=list(check.evidence_ids),
                        reviewer_id=check.reviewer_id, run_id=context.run_id)
                outcomes.append({"property_id": candidate.property_id,
                                 "status": check.status.value,
                                 "evidence_ids": list(check.evidence_ids),
                                 "reviewer_id": check.reviewer_id,
                                 "diagnostics": list(check.diagnostics),
                                 "limitations": list(check.limitations)})
                diagnostics.extend(check.diagnostics)
        if not candidates:
            status, semantic = StageRunStatus.SUCCEEDED, "NO_CANDIDATES"
        elif self.checker is None or any(item["status"] == PropertyStatus.INCONCLUSIVE.value
                                             for item in outcomes):
            status, semantic = StageRunStatus.INCONCLUSIVE, "INCONCLUSIVE"
        else:
            status = StageRunStatus.SUCCEEDED
            semantic = (outcomes[0]["status"] if len({item["status"] for item in outcomes}) == 1
                        else "MIXED_TERMINAL_RESULTS")
        output = ArtifactEnvelope("property-candidates", "v1", "property_validation",
                                  ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY,
                                  {"candidates": candidates, "outcomes": outcomes,
                                   "dataset_observation_ids": observation_ids,
                                   "validated": bool(outcomes) and all(
                                       item["status"] == PropertyStatus.VALIDATED_FOR_SCOPE.value
                                       for item in outcomes),
                                   "checker_configured": self.checker is not None})
        return StageExecution(StageResult(
            "property_validation", ImplementationStatus.SCAFFOLDED,
            status, semantic_status=semantic,
            input_artifacts=[adversarial.artifact_id, contract.artifact_id],
            diagnostics=diagnostics,
            limitations=["checked outcomes are scoped; stage success does not imply safety"]), [output])
