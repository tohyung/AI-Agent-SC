from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from .logic_graph import LogicGraphVerifier
from .marlowe_ast import normalize_marlowe_ast
from .marlowe_validator import validate_contract
from .models import (
    ContractDraft,
    LLMError,
    LogicGraphResult,
    PipelineResult,
    TraceEvent,
    VerificationResult,
)
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

    def clarify_logic_prompt(self, prompt: str, draft: ContractDraft, logic: LogicGraphResult,
                             stall_hint: str = "") -> str:
        clarification = self.reasoner.logic_feedback_to_clarification(prompt, draft, logic)
        self.last_clarification_audit = str(clarification.get("reasoning_narrative") or "")
        instruction = "\n".join(part for part in [
            "Lỗi logic hiện tại: " + "; ".join(logic.errors[:8]),
            str(clarification.get("internal_instruction") or "").strip(), stall_hint,
        ] if part)
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
        return self.verifier.verify(draft.marlowe_contract, draft)

    def audit_narrative(self, logic: LogicGraphResult) -> str:
        count = len(logic.graph.get("nodes", []))
        if logic.passed:
            return f"Node 3 đã kiểm tra {count} node, {logic.paths_explored} đường đi; có {len(logic.warnings)} cảnh báo."
        return (f"Node 3 kiểm tra {count} node và phát hiện {len(logic.errors)} lỗi, "
                f"{len(logic.warnings)} cảnh báo: {'; '.join(logic.errors[:3])}")


TraceCallback = Callable[[TraceEvent], None]
STALL_HINT = (
    "Draft hiện tại lặp lại cùng AST và cùng lỗi như lượt trước. "
    "Không lặp lại cách sửa cũ. Hãy phân tích lại nguyên nhân và tạo AST khác về cấu trúc "
    "nếu cần, nhưng giữ nguyên business intent của người dùng."
)


class AgentPipeline:
    def __init__(
        self,
        reasoner: Any,
        interactive: bool = False,
        max_iterations: int | None = None,
        max_llm_calls: int | None = None,
        stop_on_stall: int | None = None,
        require_semantic_pass: bool = True,
        trace_callback: TraceCallback | None = None,
    ) -> None:
        if any(limit is not None and limit < 1 for limit in (max_iterations, max_llm_calls, stop_on_stall)):
            raise ValueError("Các giới hạn phải >= 1")
        self.node_1 = PromptToDraftNode(reasoner, interactive=interactive)
        self.node_2 = SemanticVerificationNode(reasoner)
        self.node_3 = LogicGraphVerificationNode()
        self.max_iterations = max_iterations
        self.max_llm_calls = max_llm_calls
        self.stop_on_stall = stop_on_stall
        self.stall_count = 0
        self.require_semantic_pass = require_semantic_pass
        self.trace_callback = trace_callback
        self.trace: list[TraceEvent] = []
        self.reasoner = reasoner
        self._iteration_start: float | None = None
        self._iteration_trace_start = 0
        self._iteration_number = 0

    def track(self, node: str, status: str, message: str, data: dict[str, Any] | None = None) -> None:
        event = TraceEvent(node, status, message, data or {})
        self.trace.append(event)
        if self.trace_callback:
            self.trace_callback(event)

    def _result(
        self, draft: ContractDraft, semantic: VerificationResult, logic: LogicGraphResult,
        iterations: int, status: str, reason: str,
    ) -> PipelineResult:
        self._finish_iteration()
        self.track("pipeline", status, "Workflow đã hoàn tất." if status == "done" else "Workflow đã dừng.",
                   {"iterations": iterations, "stop_reason": reason})
        return PipelineResult(draft, semantic, logic, iterations, self.trace, status, reason)

    def _llm_call_count(self) -> int:
        if hasattr(self.reasoner, "llm_calls"):
            return self.reasoner.llm_calls
        return len(getattr(self.reasoner, "calls", []))

    def _finish_iteration(self) -> None:
        if self._iteration_start is None:
            return
        states = {"structural": "skip", "semantic": "skip", "logic": "skip"}
        nodes = {"structural_gate": "structural", "node_2_semantic_verification": "semantic",
                 "node_3_logic_graph_verification": "logic"}
        logic_errors = logic_warnings = 0
        for event in self.trace[self._iteration_trace_start:]:
            key = nodes.get(event.node)
            if key and event.status in {"pass", "fail"}:
                states[key] = event.status
            if key == "logic" and event.status in {"pass", "fail"}:
                logic_errors = len(event.data.get("errors", []))
                logic_warnings = len(event.data.get("warnings", []))
        self.track("pipeline", "iteration", "Đã hoàn tất lượt xử lý.", {
            "iteration": self._iteration_number, **states,
            "logic_errors": logic_errors, "logic_warnings": logic_warnings,
            "stall_count": self.stall_count, "llm_calls": self._llm_call_count(),
            "elapsed_seconds": round(perf_counter() - self._iteration_start, 3),
        })
        self._iteration_start = None

    def _observe_stall(self, seen: dict[str, int], contract: Any, errors: list[str]) -> tuple[bool, str]:
        signature = fingerprint({"contract": contract, "errors": sorted(errors)})
        occurrences = seen.get(signature, 0) + 1
        seen[signature] = occurrences
        if occurrences >= 2:
            self.stall_count += 1
            self.track("pipeline", "warn", "Draft và lỗi đang lặp lại.", {
                "reason": "stalled", "fingerprint": signature[:12],
                "occurrences": occurrences, "stall_count": self.stall_count,
            })
        return (self.stop_on_stall is not None and occurrences >= self.stop_on_stall,
                STALL_HINT if occurrences >= 2 else "")

    def _limit_reached(self, iterations: int) -> bool:
        return self.max_iterations is not None and iterations >= self.max_iterations

    def run(self, prompt: str) -> PipelineResult:
        self.trace = []
        self.stall_count = 0
        self._iteration_start = None
        if hasattr(self.reasoner, "set_call_budget"):
            self.reasoner.set_call_budget(self.max_llm_calls)
        current_prompt = prompt
        iterations = 0
        seen: dict[str, int] = {}
        draft = ContractDraft(prompt, "", [], None)
        semantic = VerificationResult(False, 0.0, [])
        logic = LogicGraphResult(False, [], {"nodes": [], "edges": []})
        self.track("pipeline", "start", "Đã nhận prompt.", {"max_iterations": self.max_iterations})

        try:
            while True:
                self._finish_iteration()
                iterations += 1
                self._iteration_number = iterations
                self._iteration_trace_start = len(self.trace)
                self._iteration_start = perf_counter()
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

                empty_contract = draft.marlowe_contract is None or draft.marlowe_contract == {}
                if empty_contract and draft.clarification_questions:
                    self.track("structural_gate", "skipped", "Chưa có AST do thiếu thông tin nghiệp vụ.")
                    next_prompt = self.node_1.ask_for_clarifications(
                        current_prompt, unique_strings(draft.clarification_questions)[:4],
                        "Thong tin bo sung tu nguoi dung",
                    )
                    if next_prompt == current_prompt:
                        return self._result(draft, semantic, logic, iterations, "blocked", "no_user_input")
                    if self._limit_reached(iterations):
                        return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
                    current_prompt = next_prompt
                    continue

                errors = [] if empty_contract else validate_contract(draft.marlowe_contract)
                if errors:
                    logic = LogicGraphResult(False, errors, {"nodes": [], "edges": []})
                    self.track("structural_gate", "fail", "AST chưa hợp lệ.", {"findings": errors})
                    stalled, stall_hint = self._observe_stall(seen, draft.marlowe_contract, errors)
                    if stalled:
                        return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                    if self._limit_reached(iterations):
                        return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
                    current_prompt = self.node_1.append_internal_feedback(
                        current_prompt, "Sửa AST theo lỗi cấu trúc: " + "; ".join(errors[:8])
                        + ("\n" + stall_hint if stall_hint else "")
                    )
                    continue
                if not empty_contract:
                    self.track("structural_gate", "pass", "AST hợp lệ.")
                else:
                    self.track("structural_gate", "skipped", "Chưa có AST; chuyển Node 2 xác minh.")

                self.track("node_2_semantic_verification", "start", "Đang kiểm semantic.")
                semantic = self.node_2.run(current_prompt, draft)
                self.track("node_2_semantic_verification", "pass" if semantic.passed else "fail",
                           "Đã kiểm semantic.", {"findings": semantic.findings,
                                                  "reasoning_narrative": semantic.reasoning_narrative})
                if empty_contract and semantic.passed:
                    self.track("node_3_logic_graph_verification", "skipped", "Chưa có AST để kiểm logic graph.")
                    return self._result(draft, semantic, logic, iterations, "blocked", "semantic_not_passed")
                if not semantic.passed:
                    stalled, _ = self._observe_stall(seen, draft.marlowe_contract,
                                                     semantic.findings + semantic.questions)
                    if stalled:
                        return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                    if self._limit_reached(iterations):
                        return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
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
                                                     "errors": logic.errors, "warnings": logic.warnings,
                                                     "reasoning_narrative": self.node_3.audit_narrative(logic)})
                if logic.passed:
                    status = "done" if semantic.passed else "blocked"
                    reason = "ok" if semantic.passed else "semantic_not_passed"
                    return self._result(draft, semantic, logic, iterations, status, reason)
                stalled, stall_hint = self._observe_stall(seen, draft.marlowe_contract, logic.findings)
                if stalled:
                    return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                if self._limit_reached(iterations):
                    return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
                next_prompt = self.node_1.clarify_logic_prompt(current_prompt, draft, logic, stall_hint)
                if next_prompt == current_prompt:
                    return self._result(draft, semantic, logic, iterations, "blocked", "no_user_input")
                self.track("node_1_prompt_to_draft", "done", "Đã nhận phản hồi từ Node 3.",
                           {"reasoning_narrative": self.node_1.last_clarification_audit})
                current_prompt = next_prompt

        except LLMError as exc:
            self.track("pipeline", "error", "Lời gọi LLM thất bại.", {"error": str(exc)})
            return self._result(draft, semantic, logic, iterations, "blocked", "llm_error")
        except KeyboardInterrupt:
            self.track("pipeline", "warn", "Đã dừng theo yêu cầu người dùng.")
            return self._result(draft, semantic, logic, iterations, "blocked", "interrupted")
