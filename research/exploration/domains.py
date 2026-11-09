"""Explicit transaction templates; no actors or amounts are inferred from AST."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from copy import deepcopy
from typing import Any


class IntervalRelation(StrEnum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    STRADDLES = "STRADDLES"


def classify_interval(start: int, end: int, deadline: int) -> IntervalRelation:
    if start > end:
        raise ValueError("interval start must not exceed end")
    if end < deadline:
        return IntervalRelation.BEFORE
    if start >= deadline:
        return IntervalRelation.AFTER
    return IntervalRelation.STRADDLES


@dataclass(frozen=True)
class TransactionTemplate:
    action_kind: str
    interval_from: int
    interval_to: int
    inputs: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if self.action_kind not in {"Deposit", "Choice", "Notify", "Timeout", "NoInput"}:
            raise ValueError("unsupported action kind")
        if (not isinstance(self.interval_from, int) or not isinstance(self.interval_to, int)
                or isinstance(self.interval_from, bool) or isinstance(self.interval_to, bool)
                or self.interval_from > self.interval_to):
            raise ValueError("invalid POSIX millisecond interval")
        expected = [] if self.action_kind in {"Timeout", "NoInput"} else [self.action_kind]
        if [item.get("type") for item in self.inputs] != expected:
            raise ValueError("input kind does not match transaction template")
        fields = {"Deposit": {"type", "account", "party", "token", "amount"},
                  "Choice": {"type", "choice_id", "chosen"},
                  "Notify": {"type"}}
        if self.action_kind not in {"Timeout", "NoInput"} and set(self.inputs[0]) != fields[self.action_kind]:
            raise ValueError("input fields do not match the pinned reference request")

    def to_transaction(self) -> dict[str, Any]:
        return {"interval": {"from": self.interval_from, "to": self.interval_to},
                "inputs": deepcopy(list(self.inputs))}


class ExplicitTransactionDomain:
    finite = True

    def __init__(self, domain_id: str, templates: list[TransactionTemplate]) -> None:
        if not domain_id or not templates:
            raise ValueError("explicit domain needs an ID and at least one transaction")
        self.domain_id = domain_id
        self._templates = tuple(templates)

    def transactions(self, state: dict[str, Any], contract: Any) -> list[dict[str, Any]]:
        return [item.to_transaction() for item in self._templates]
