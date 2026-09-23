from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """A model request failed or exceeded its call budget."""


@dataclass
class PartySpec:
    role: str
    name: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "name": self.name}


@dataclass
class ContractDraft:
    original_prompt: str
    intent: str
    parties: list[PartySpec]
    amount: int | None
    token: str | None = None
    deposit_timeout: int | None = None
    decision_timeout: int | None = None
    clauses: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    reasoning_narrative: str = ""
    contract_plan: dict[str, Any] = field(default_factory=dict)
    marlowe_contract: Any = field(default_factory=dict)
    normalization_notes: list[str] = field(default_factory=list)

    def party_by_role(self, role: str) -> PartySpec | None:
        return next((party for party in self.parties if party.role == role), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_prompt": self.original_prompt,
            "intent": self.intent,
            "parties": [party.to_dict() for party in self.parties],
            "amount": self.amount,
            "token": self.token,
            "deposit_timeout": self.deposit_timeout,
            "decision_timeout": self.decision_timeout,
            "clauses": self.clauses,
            "assumptions": self.assumptions,
            "clarification_questions": self.clarification_questions,
            "reasoning_summary": self.reasoning_summary,
            "reasoning_narrative": self.reasoning_narrative,
            "contract_plan": self.contract_plan,
            "marlowe_contract": self.marlowe_contract,
            "normalization_notes": self.normalization_notes,
        }


@dataclass
class VerificationResult:
    passed: bool
    score: float
    findings: list[str]
    questions: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    reasoning_narrative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "findings": self.findings,
            "questions": self.questions,
            "reasoning_summary": self.reasoning_summary,
            "reasoning_narrative": self.reasoning_narrative,
        }


@dataclass
class LogicGraphResult:
    passed: bool
    findings: list[str]
    graph: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "findings": self.findings, "graph": self.graph}


@dataclass
class TraceEvent:
    node: str
    status: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "status": self.status,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class PipelineResult:
    draft: ContractDraft
    semantic_verification: VerificationResult
    logic_verification: LogicGraphResult
    iterations: int
    trace: list[TraceEvent] = field(default_factory=list)
    status: str = "blocked"
    stop_reason: str = "max_iterations"

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "trace": [event.to_dict() for event in self.trace],
            "draft": self.draft.to_dict(),
            "semantic_verification": self.semantic_verification.to_dict(),
            "logic_verification": self.logic_verification.to_dict(),
            "marlowe_contract": self.draft.marlowe_contract,
        }
