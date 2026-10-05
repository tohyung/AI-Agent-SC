"""Optional Node 3 SMT boundary; no solver is launched on import."""

from __future__ import annotations

from typing import Any


class SMTAdapter:
    def analyze(self, contract: Any) -> dict[str, Any]:
        from research.integrations.smt_driver import analyze
        return analyze(contract)
