"""Pinned reference-driver adapter; importing this module never invokes the driver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ReferenceRequest:
    contract: Any
    state: dict[str, Any]
    transactions: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"contract": self.contract, "state": self.state,
                "transactions": list(self.transactions)}


class ReferenceExecutor(Protocol):
    def execute(self, request: ReferenceRequest) -> dict[str, Any]: ...


class PinnedMarloweReference:
    def execute(self, request: ReferenceRequest) -> dict[str, Any]:
        from tools.marlowe_smt.run_reference import execute
        return execute(request.to_dict())
