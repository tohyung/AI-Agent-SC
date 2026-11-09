"""Source-grounded retry after deterministic compiler rejection."""

from __future__ import annotations

import json
from typing import Any


class CompilerFeedbackModel:
    """Ask for a fresh core; never edit the prior candidate or user history."""

    def __init__(self, base: Any, prior_core: dict, diagnostics: list[str]) -> None:
        self.base = base
        self.prior_core = prior_core
        self.diagnostics = diagnostics

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def generate(self, system: str, user: str) -> dict:
        feedback = (
            "\nPrevious core passed semantic-core and full structural validation, "
            "but the deterministic compiler rejected it. Regenerate the COMPLETE "
            "seven-field semantic core from requirement_history. Correct only "
            "source-grounded omissions or mappings shown below. Do not delete a "
            "real requirement, invent a business fact, change resolution merely "
            "to match a compiler profile, or edit the previous candidate in place. "
            "Re-evaluate every unscored observation against later explicit "
            "revisions and already represented scopes/claims; do not preserve "
            "a superseded uncertainty as unsupported behavior. A named actor's "
            "approval can be encoded as that actor's Choice without requiring "
            "the user to specify wallet-signature, oracle, or multisig mechanics "
            "unless such a mechanism is itself a business requirement. "
            "If a later absolute deadline resolves an earlier relative date, "
            "retain the actual deadline claims but drop the obsolete uncertainty "
            "observation. A statement that the contract does not submit its own "
            "transactions describes normal ledger operation, not an autonomous "
            "contract feature or a missing trigger for a time-based payment; "
            "do not turn it into an autonomous_execution claim or question. "
            "The result will be independently validated and compiled again.\n"
            "Compiler diagnostics:\n"
            + json.dumps(self.diagnostics, ensure_ascii=False)
            + "\nPrevious valid core:\n"
            + json.dumps(self.prior_core, ensure_ascii=False)
        )
        return self.base.generate(system, user + feedback)
