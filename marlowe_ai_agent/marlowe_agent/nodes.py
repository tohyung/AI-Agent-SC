from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .logic_graph import LogicGraphVerifier
from .marlowe_ast import normalize_marlowe_ast
from .marlowe_validator import validate_contract
from .models import ContractDraft, LLMError, LogicGraphResult, PipelineResult, TraceEvent, VerificationResult
from .utils import fingerprint, unique_strings


class PromptToDraftNode:
    def __init__(self, reasoner: Any, interactive: bool = False) -> None:
        self.reasoner = reasoner
        self.interactive = interactive
        self.last_clarification_audit = ""

    def run(self, prompt: str) -> ContractDraft:
        return self.reasoner.draft_from_prompt(prompt)

    def clarify_prompt(self, prompt: str, verification: VerificationResult) -> str:
        self.last_clarification_audit = verification.reasoning_narrative
        return self.ask_for_clarifications(
            prompt, unique_strings(verification.questions or verification.findings)[:4],
            "Thong tin bo sung tu nguoi dung",
        )

    def clarify_logic_prompt(self, prompt: str, draft: ContractDraft, logic: LogicGraphResult) -> str:
        clarification = self.reasoner.logic_feedback_to_clarification(prompt, draft, logic)
        self.last_clarification_audit = str(clarification.get("reasoning_narrative") or "")
        instruction = str(clarification.get("internal_instruction") or "").strip()
        questions = unique_strings(clarification.get("questions") or [])[:4]
        if clarification.get("needs_user_input") and questions:
            answered = self.ask_for_clarifications(
                prompt, questions, "Thong tin bo sung tu nguoi dung sau kiem logic graph",
            )
            if answered == prompt:
                return prompt
            return self.append_internal_feedback(answered, instruction)
        if instruction:
            return self.append_internal_feedback(prompt, instruction)
        return prompt

    def ask_for_clarifications(self, prompt: str, questions: list[str], heading: str) -> str:
        if not self.interactive or not questions:
            return prompt
        additions = []
        for index, question in enumerate(questions, start=1):
            answer = input(f"Cau hoi {index}: {question}\n> ").strip()
            if answer:
                additions.append(f"- {question}\n  Tra loi: {answer}")
        return prompt + f"\n\n{heading}:\n" + "\n".join(additions) if additions else prompt

    def append_internal_feedback(self, prompt: str, instruction: str) -> str:
        if not instruction.strip():
            return prompt
        prompt = prompt.split("\n\nPhan hoi noi bo tu Node 3 de Node 1 sinh lai draft:\n", 1)[0]
        return prompt + "\n\nPhan hoi noi bo tu Node 3 de Node 1 sinh lai draft:\n" + instruction.strip()


class SemanticVerificationNode:
    def __init__(self, reasoner: Any) -> None:
        self.reasoner = reasoner

    def run(self, prompt: str, draft: ContractDraft) -> VerificationResult:
        return self.reasoner.semantic_verify(prompt, draft)


class LogicGraphVerificationNode:
    def __init__(self) -> None:
        self.verifier = LogicGraphVerifier()

    def run(self, draft: ContractDraft) -> LogicGraphResult:
        return self.verifier.verify(draft.marlowe_contract)

    def audit_narrative(self, logic: LogicGraphResult) -> str:
        count = len(logic.graph.get("nodes", []))
        if logic.passed:
            return f"Node 3 đã kiểm tra {count} node trong logic graph; không phát hiện lỗi."
        return f"Node 3 kiểm tra {count} node và phát hiện: {'; '.join(logic.findings[:3])}"


TraceCallback = Callable[[TraceEvent], None]


class AgentPipeline:
    def __init__(
        self,
        reasoner: Any,
        interactive: bool = False,
        max_iterations: int = 8,
        max_llm_calls: int = 40,
        require_semantic_pass: bool = True,
        trace_callback: TraceCallback | None = None,
    ) -> None:
        if max_iterations < 1 or max_llm_calls < 1:
            raise ValueError("max_iterations và max_llm_calls phải >= 1")
        self.node_1 = PromptToDraftNode(reasoner, interactive=interactive)
        self.node_2 = SemanticVerificationNode(reasoner)
        self.node_3 = LogicGraphVerificationNode()
        self.max_iterations = max_iterations
        self.max_llm_calls = max_llm_calls
        self.require_semantic_pass = require_semantic_pass
        self.trace_callback = trace_callback
        self.trace: list[TraceEvent] = []
        self.reasoner = reasoner

    def track(self, node: str, status: str, message: str, data: dict[str, Any] | None = None) -> None:
        event = TraceEvent(node, status, message, data or {})
        self.trace.append(event)
        if self.trace_callback:
            self.trace_callback(event)

    def _result(
        self, draft: ContractDraft, semantic: VerificationResult, logic: LogicGraphResult,
        iterations: int, status: str, reason: str,
    ) -> PipelineResult:
        self.track("pipeline", status, "Workflow đã hoàn tất." if status == "done" else "Workflow đã dừng.",
                   {"iterations": iterations, "stop_reason": reason})
        return PipelineResult(draft, semantic, logic, iterations, self.trace, status, reason)

    def _stalled(self, seen: set[str], contract: Any, errors: list[str]) -> bool:
        signature = fingerprint({"contract": contract, "errors": sorted(errors)})
        if signature in seen:
            return True
        seen.add(signature)
        return False

    def run(self, prompt: str) -> PipelineResult:
        self.trace = []
        if hasattr(self.reasoner, "set_call_budget"):
            self.reasoner.set_call_budget(self.max_llm_calls)
        current_prompt = prompt
        iterations = 0
        seen: set[str] = set()
        draft = ContractDraft(prompt, "", [], None)
        semantic = VerificationResult(False, 0.0, [])
        logic = LogicGraphResult(False, [], {"nodes": [], "edges": []})
        self.track("pipeline", "start", "Đã nhận prompt.", {"max_iterations": self.max_iterations})

        try:
            while iterations < self.max_iterations:
                iterations += 1
                self.track("node_1_prompt_to_draft", "start", "Đang sinh draft.", {"iteration": iterations})
                draft = self.node_1.run(current_prompt)
                self.track("node_1_prompt_to_draft", "done", "Đã sinh draft.", {
                    "reasoning_narrative": draft.reasoning_narrative,
                    "intent": draft.intent,
                })

                draft.marlowe_contract, notes = normalize_marlowe_ast(draft.marlowe_contract)
                notes = draft.normalization_notes + notes
                if notes:
                    self.track("structural_gate", "normalized", "Đã chuẩn hóa AST cũ.", {"notes": notes})

                errors = validate_contract(draft.marlowe_contract)
                if errors:
                    logic = LogicGraphResult(False, errors, {"nodes": [], "edges": []})
                    self.track("structural_gate", "fail", "AST chưa hợp lệ.", {"findings": errors})
                    if self._stalled(seen, draft.marlowe_contract, errors):
                        return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                    current_prompt = self.node_1.append_internal_feedback(
                        current_prompt, "Sửa AST theo lỗi cấu trúc: " + "; ".join(errors[:8])
                    )
                    continue
                self.track("structural_gate", "pass", "AST hợp lệ.")

                self.track("node_2_semantic_verification", "start", "Đang kiểm semantic.")
                semantic = self.node_2.run(current_prompt, draft)
                self.track("node_2_semantic_verification", "pass" if semantic.passed else "fail",
                           "Đã kiểm semantic.", {"findings": semantic.findings,
                                                  "reasoning_narrative": semantic.reasoning_narrative})
                if not semantic.passed:
                    if self._stalled(seen, draft.marlowe_contract, semantic.findings + semantic.questions):
                        return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                    next_prompt = self.node_1.clarify_prompt(current_prompt, semantic)
                    if next_prompt != current_prompt:
                        current_prompt = next_prompt
                        continue
                    if self.require_semantic_pass:
                        self.track("node_3_logic_graph_verification", "skipped", "Semantic chưa đạt.")
                        return self._result(draft, semantic, logic, iterations, "blocked", "no_user_input")

                self.track("node_3_logic_graph_verification", "start", "Đang kiểm logic graph.")
                logic = self.node_3.run(draft)
                self.track("node_3_logic_graph_verification", "pass" if logic.passed else "fail",
                           "Đã kiểm logic graph.", {"findings": logic.findings,
                                                     "reasoning_narrative": self.node_3.audit_narrative(logic)})
                if logic.passed:
                    status = "done" if semantic.passed else "blocked"
                    reason = "ok" if semantic.passed else "semantic_not_passed"
                    return self._result(draft, semantic, logic, iterations, status, reason)
                if self._stalled(seen, draft.marlowe_contract, logic.findings):
                    return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                next_prompt = self.node_1.clarify_logic_prompt(current_prompt, draft, logic)
                if next_prompt == current_prompt:
                    return self._result(draft, semantic, logic, iterations, "blocked", "no_user_input")
                self.track("node_1_prompt_to_draft", "done", "Đã nhận phản hồi từ Node 3.",
                           {"reasoning_narrative": self.node_1.last_clarification_audit})
                current_prompt = next_prompt

            return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
        except LLMError as exc:
            self.track("pipeline", "error", "Lời gọi LLM thất bại.", {"error": str(exc)})
            return self._result(draft, semantic, logic, iterations, "blocked", "llm_error")
