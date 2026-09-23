from __future__ import annotations

from typing import Any

import pytest
from marlowe_agent.marlowe_ast import escrow_contract
from marlowe_agent.models import ContractDraft, PartySpec

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


@pytest.fixture
def draft_factory():
    return make_draft
