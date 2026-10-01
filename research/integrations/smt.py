"""Optional Node 3 SMT boundary; no solver is launched on import."""

from __future__ import annotations

from typing import Any


class SMTAdapter:
    def analyze(self, contract: Any) -> dict[str, Any]:
        from marlowe_ai_agent.marlowe_agent.node3_smt import MarloweSMTBackend
        result = MarloweSMTBackend().analyze(contract)
        return {"status": result.status,
                "warnings": [item.to_dict() for item in result.warnings],
                "counterexample": result.counterexample,
                "analysis_notes": result.analysis_notes,
                "elapsed_seconds": result.elapsed_seconds}
