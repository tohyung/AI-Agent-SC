from __future__ import annotations

from typing import Any

import pytest
from marlowe_agent.marlowe_ast import escrow_contract
from marlowe_agent.models import ContractDraft, PartySpec
from marlowe_agent.node3_policy import StructuredWarning
from marlowe_agent.node3_smt import SMTAnalysis

DEPOSIT_TIMEOUT = 1_893_456_000_000
DECISION_TIMEOUT = 1_893_542_400_000
AMOUNT = 250_000_000


def make_draft(contract: Any = None) -> ContractDraft:
    if contract is None:
        contract = escrow_contract("Alice", "Bob", AMOUNT, DEPOSIT_TIMEOUT, DECISION_TIMEOUT)
    return ContractDraft(
        original_prompt="Alice escrow 250 ADA for Bob",
        intent="escrow",
        parties=[PartySpec("buyer", "Alice"), PartySpec("seller", "Bob")],
        amount=AMOUNT,
        token="ADA",
        deposit_timeout=DEPOSIT_TIMEOUT,
        decision_timeout=DECISION_TIMEOUT,
        marlowe_contract=contract,
    )


class FakeSMTBackend:
    def __init__(self, statuses: list[str | SMTAnalysis] | None = None) -> None:
        self.statuses = list(statuses or [])
        self.call_count = 0

    def analyze(self, contract: Any) -> SMTAnalysis:
        self.call_count += 1
        if self.statuses:
            result = self.statuses.pop(0)
            if isinstance(result, SMTAnalysis):
                return result
            status = result
        else:
            status = "counterexample" if isinstance(contract, dict) and "pay" in contract else "valid"
        warnings = ([StructuredWarning("TransactionPartialPay", {
            "account": {"role_token": "Alice"}, "payee": {"party": {"role_token": "Bob"}},
            "expected": contract.get("pay", 10), "paid": 0,
        })] if status == "counterexample" else [])
        return SMTAnalysis(status, warnings, {"transaction": []} if warnings else None, [], 0.01)


@pytest.fixture(autouse=True)
def default_fake_smt_backend(monkeypatch):
    from marlowe_agent import nodes

    monkeypatch.setattr(nodes, "MarloweSMTBackend", FakeSMTBackend)


@pytest.fixture
def draft_factory():
    return make_draft
