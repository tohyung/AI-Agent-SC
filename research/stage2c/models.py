"""Review and acceptance objects, separate from Stage 2B model candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IntentDecisionStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    CONFLICT = "CONFLICT"
    UNSUPPORTED = "UNSUPPORTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ClarificationIssue:
    issue_id: str
    category: str
    description: str
    claim_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class ClarificationAnswer:
    issue_id: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return vars(self).copy()


@dataclass(frozen=True)
class IntentReviewSession:
    candidate_artifact_id: str
    issues: tuple[ClarificationIssue, ...]
    implementation_status: str = "IMPLEMENTED_UNVALIDATED"

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_artifact_id": self.candidate_artifact_id,
                "issues": [item.to_dict() for item in self.issues],
                "implementation_status": self.implementation_status}


@dataclass(frozen=True)
class IntentDecision:
    status: IntentDecisionStatus
    reviewer_id: str
    explicit_consent: bool = False
    answers: tuple[ClarificationAnswer, ...] = ()
    approved_spec: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "reviewer_id": self.reviewer_id,
                "explicit_consent": self.explicit_consent,
                "answers": [answer.to_dict() for answer in self.answers],
                "approved_spec": self.approved_spec}


@dataclass(frozen=True)
class AcceptedIntentSpec:
    candidate_artifact_id: str
    reviewer_id: str
    accepted_spec: dict[str, Any]
    answers: tuple[ClarificationAnswer, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_artifact_id": self.candidate_artifact_id,
                "reviewer_id": self.reviewer_id, "accepted_spec": self.accepted_spec,
                "answers": [answer.to_dict() for answer in self.answers]}


@dataclass(frozen=True)
class IntentAcceptanceResult:
    status: IntentDecisionStatus
    accepted: AcceptedIntentSpec | None = None
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value,
                "accepted": self.accepted.to_dict() if self.accepted else None,
                "diagnostics": list(self.diagnostics)}


@dataclass(frozen=True)
class IntentFreezeManifest:
    accepted_artifact_id: str
    candidate_artifact_id: str
    accepted_spec_schema: str
    source_history_hash: str
    reviewer_id: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {"accepted_artifact_id": self.accepted_artifact_id,
                "candidate_artifact_id": self.candidate_artifact_id,
                "accepted_spec_schema": self.accepted_spec_schema,
                "source_history_hash": self.source_history_hash,
                "reviewer_id": self.reviewer_id, "evidence_ids": list(self.evidence_ids)}
