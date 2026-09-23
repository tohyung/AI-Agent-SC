from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any

import pytest

from marlowe_agent.marlowe_ast import escrow_contract
from marlowe_agent.models import ContractDraft, LLMError, PartySpec, VerificationResult


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


class FakeReasoner:
    def __init__(self, drafts: list[Any], semantics: list[Any] | None = None,
                 clarifications: list[Any] | None = None) -> None:
        self.drafts = deque(drafts)
        self.semantics = deque(semantics or [VerificationResult(True, 1.0, ["Đạt."])])
        self.clarifications = deque(clarifications or [])
        self.calls: list[str] = []
        self.max_llm_calls = 40

    def set_call_budget(self, limit: int) -> None:
        self.max_llm_calls = limit
        self.calls.clear()

    def _take(self, name: str, values: deque[Any]) -> Any:
        if len(self.calls) >= self.max_llm_calls:
            raise LLMError("Fake LLM call cap reached")
        self.calls.append(name)
        value = values.popleft() if len(values) > 1 else values[0]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)

    def draft_from_prompt(self, prompt: str) -> ContractDraft:
        draft = self._take("draft", self.drafts)
        draft.original_prompt = prompt
        return draft

    def semantic_verify(self, prompt: str, draft: ContractDraft) -> VerificationResult:
        return self._take("semantic", self.semantics)

    def logic_feedback_to_clarification(self, prompt: str, draft: ContractDraft, logic: Any) -> dict[str, Any]:
        return self._take("clarification", self.clarifications)


@pytest.fixture
def draft_factory():
    return make_draft
