from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any

from marlowe_agent.models import ContractDraft, LLMError, VerificationResult


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
