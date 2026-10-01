"""Evidence-linked assurance claims never imply authority by themselves."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .artifacts import ArtifactStore
from .status import AssuranceMethod, AssuranceVerdict, CoverageStatus


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: str
    source: str
    artifact_id: str | None = None
    location: str | None = None
    content_hash: str | None = None
    description: str = ""
    created_by_stage: str = ""

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()

    def verify_artifact(self, store: ArtifactStore) -> bool:
        if self.artifact_id is None or self.content_hash is None or not store.has(self.artifact_id):
            return False
        artifact = store.get(self.artifact_id)
        return artifact.content_hash == self.content_hash


@dataclass(frozen=True)
class AssuranceClaim:
    claim_id: str
    subject: str
    verdict: AssuranceVerdict
    method: AssuranceMethod
    scope: dict[str, Any]
    coverage: dict[str, Any]
    evidence: tuple[EvidenceRef, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    produced_by: str = ""
    schema_version: str = "assurance-claim-v1"

    def __post_init__(self) -> None:
        if self.verdict in {AssuranceVerdict.SATISFIED, AssuranceVerdict.VIOLATED} and not self.evidence:
            raise ValueError("conclusive assurance claim requires evidence")

    def to_dict(self) -> dict[str, Any]:
        return {"claim_id": self.claim_id, "subject": self.subject,
                "verdict": self.verdict.value, "method": self.method.value,
                "scope": self.scope, "coverage": self.coverage,
                "evidence": [item.to_dict() for item in self.evidence],
                "assumptions": list(self.assumptions), "limitations": list(self.limitations),
                "produced_by": self.produced_by, "schema_version": self.schema_version}


@dataclass(frozen=True)
class CoverageReport:
    status: CoverageStatus
    observed: dict[str, Any] = field(default_factory=dict)
    domain_definition: dict[str, Any] | None = None
    completeness_argument: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if self.status == CoverageStatus.COMPLETE_FOR_DEFINED_FINITE_DOMAIN and (
                not self.domain_definition or not self.completeness_argument or not self.evidence):
            raise ValueError("complete coverage requires a domain, argument and evidence")

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "observed": self.observed,
                "domain_definition": self.domain_definition,
                "completeness_argument": self.completeness_argument,
                "evidence": [item.to_dict() for item in self.evidence]}
