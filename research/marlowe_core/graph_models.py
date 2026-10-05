"""Typed outputs and optional draft view for static Marlowe linting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class DraftParty(Protocol):
    role: str
    name: str


class DraftView(Protocol):
    parties: list[DraftParty]
    amount: int | None
    deposit_timeout: int | None
    decision_timeout: int | None
    marlowe_contract: Any


@dataclass
class LogicGraphResult:
    passed: bool
    findings: list[str]
    graph: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    paths_explored: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "findings": self.findings, "graph": self.graph,
                "errors": self.errors, "warnings": self.warnings,
                "paths_explored": self.paths_explored}
