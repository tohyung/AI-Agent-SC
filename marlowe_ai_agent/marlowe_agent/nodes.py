from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from time import perf_counter, sleep
from typing import Any, TypeVar

from .logic_graph import LogicGraphVerifier
from .marlowe_ast import normalize_marlowe_ast
from .marlowe_validator import validate_contract
from .models import (
    ContractDraft,
    LLMError,
    LLMTransientError,
    LogicGraphResult,
    PipelineResult,
    SemanticHistoryEntry,
    TraceEvent,
    VerificationResult,
)
from .utils import fingerprint, unique_strings


class ClarificationAction(Enum):
    REGENERATE = "regenerate"
    BLOCK_NO_INPUT = "block_no_input"
    NO_ACTION = "no_action"


@dataclass
class ClarificationOutcome:
    prompt: str
    action: ClarificationAction
    user_answered: bool = False


@dataclass
class StallTracker:
    structural_seen: dict[str, int] = field(default_factory=dict)
    semantic_seen: dict[str, int] = field(default_factory=dict)
    logic_seen: dict[str, int] = field(default_factory=dict)
    semantic_generation: int = 0
    total_stall_count: int = 0


class PromptToDraftNode:
    def __init__(self, reasoner: Any, interactive: bool = False,
                 call_llm: Callable[[str, str, Callable[[], Any]], Any] | None = None) -> None:
        self.reasoner = reasoner
        self.interactive = interactive
        self.call_llm = call_llm or (lambda _node, _operation, call: call())
        self.last_clarification_audit = ""
        self.last_answered_questions_count = 0

    def run(self, prompt: str) -> ContractDraft:
        return self.call_llm("node_1_prompt_to_draft", "draft_from_prompt",
                             lambda: self.reasoner.draft_from_prompt(prompt))

    def clarify_prompt(self, prompt: str, verification: VerificationResult,
                       allow_no_action: bool = False) -> ClarificationOutcome:
        self.last_clarification_audit = verification.reasoning_narrative
        outcome = self.ask_for_clarifications(
            prompt, unique_strings(verification.questions or verification.findings)[:4],
            "Thong tin bo sung tu nguoi dung",
        )
        if outcome.action is ClarificationAction.BLOCK_NO_INPUT and allow_no_action:
            return ClarificationOutcome(prompt, ClarificationAction.NO_ACTION)
        return outcome

    def clarify_logic_prompt(self, prompt: str, draft: ContractDraft, logic: LogicGraphResult,
                             stall_hint: str = "") -> ClarificationOutcome:
        clarification = self.call_llm(
            "node_1_prompt_to_draft", "logic_feedback_to_clarification",
            lambda: self.reasoner.logic_feedback_to_clarification(prompt, draft, logic),
        )
        self.last_clarification_audit = str(clarification.get("reasoning_narrative") or "")
        llm_instruction = str(clarification.get("internal_instruction") or "").strip()
        instruction = "\n".join(part for part in [
            "Lỗi logic hiện tại: " + "; ".join(logic.errors[:8]),
            llm_instruction, stall_hint,
        ] if part)
        questions = unique_strings(clarification.get("questions") or [])[:4]
        if clarification.get("needs_user_input") and questions:
            outcome = self.ask_for_clarifications(
                prompt, questions, "Thong tin bo sung tu nguoi dung sau kiem logic graph",
            )
            if outcome.action is ClarificationAction.BLOCK_NO_INPUT and not llm_instruction:
                return outcome
            return ClarificationOutcome(self.append_internal_feedback(outcome.prompt, instruction),
                                        ClarificationAction.REGENERATE, outcome.user_answered)
        return ClarificationOutcome(self.append_internal_feedback(prompt, instruction),
                                    ClarificationAction.REGENERATE)

    def ask_for_clarifications(self, prompt: str, questions: list[str], heading: str) -> ClarificationOutcome:
        self.last_answered_questions_count = 0
        if not self.interactive or not questions:
            return ClarificationOutcome(prompt, ClarificationAction.BLOCK_NO_INPUT)
        additions = []
        for index, question in enumerate(questions, start=1):
            answer = input(f"Cau hoi {index}: {question}\n> ").strip()
            if answer:
                additions.append(f"- {question}\n  Tra loi: {answer}")
        self.last_answered_questions_count = len(additions)
        if not additions:
            return ClarificationOutcome(prompt, ClarificationAction.BLOCK_NO_INPUT)
        return ClarificationOutcome(prompt + f"\n\n{heading}:\n" + "\n".join(additions),
                                    ClarificationAction.REGENERATE, True)

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
T = TypeVar("T")
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
        retry_sleep: Callable[[float], None] = sleep,
    ) -> None:
        if any(limit is not None and limit < 1 for limit in (max_iterations, max_llm_calls, stop_on_stall)):
            raise ValueError("Các giới hạn phải >= 1")
        self.node_1 = PromptToDraftNode(reasoner, interactive=interactive, call_llm=self._call_llm_with_retry)
        self.node_2 = SemanticVerificationNode(reasoner)
        self.node_3 = LogicGraphVerificationNode()
        self.max_iterations = max_iterations
        self.max_llm_calls = max_llm_calls
        self.stop_on_stall = stop_on_stall
        self.stall_tracker = StallTracker()
        self.semantic_history: list[SemanticHistoryEntry] = []
        self.require_semantic_pass = require_semantic_pass
        self.trace_callback = trace_callback
        self.retry_sleep = retry_sleep
        self.trace: list[TraceEvent] = []
        self.reasoner = reasoner
        self._iteration_start: float | None = None
        self._iteration_trace_start = 0
        self._iteration_number = 0

    @property
    def stall_count(self) -> int:
        return self.stall_tracker.total_stall_count

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
        return PipelineResult(draft, semantic, logic, iterations, self.trace, status, reason,
                              self.semantic_history.copy())

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
        elapsed = round(perf_counter() - self._iteration_start, 3)
        self._iteration_start = None
        self.track("pipeline", "iteration", "Đã hoàn tất lượt xử lý.", {
            "iteration": self._iteration_number, **states,
            "logic_errors": logic_errors, "logic_warnings": logic_warnings,
            "stall_count": self.stall_count, "llm_calls": self._llm_call_count(),
            "semantic_generation": self.stall_tracker.semantic_generation,
            "semantic_history_entries": len(self.semantic_history),
            "elapsed_seconds": elapsed,
        })

    def _observe_stall(self, scope: str, contract: Any, errors: list[str]) -> tuple[bool, str]:
        seen = getattr(self.stall_tracker, f"{scope}_seen")
        signature = fingerprint({"contract": contract, "errors": sorted(errors)})
        occurrences = seen.get(signature, 0) + 1
        seen[signature] = occurrences
        if occurrences >= 2:
            self.stall_tracker.total_stall_count += 1
            self.track("pipeline", "warn", "Draft và lỗi đang lặp lại.", {
                "reason": "stalled", "fingerprint": signature[:12],
                "occurrences": occurrences, "stall_count": self.stall_count,
            })
        return (self.stop_on_stall is not None and occurrences >= self.stop_on_stall,
                STALL_HINT if occurrences >= 2 else "")

    def _record_semantic(self, iteration: int, prompt: str, draft: ContractDraft,
                         semantic: VerificationResult, user_answered: bool = False) -> None:
        self.semantic_history.append(SemanticHistoryEntry(
            iteration, self.stall_tracker.semantic_generation,
            fingerprint({"contract": draft.marlowe_contract,
                         "errors": sorted(semantic.findings + semantic.questions)}),
            fingerprint(prompt), fingerprint(draft.marlowe_contract), semantic.passed, user_answered,
        ))

    def _reset_semantic_after_answer(self) -> None:
        self.stall_tracker.semantic_seen.clear()
        self.stall_tracker.semantic_generation += 1
        self.track("pipeline", "semantic_reset",
                   "Đã reset semantic stall state sau khi nhận thông tin mới từ người dùng.", {
                       "semantic_generation": self.stall_tracker.semantic_generation,
                       "history_entries": len(self.semantic_history),
                       "answered_questions_count": self.node_1.last_answered_questions_count,
                   })

    def _limit_reached(self, iterations: int) -> bool:
        return self.max_iterations is not None and iterations >= self.max_iterations

    def _call_llm_with_retry(self, node: str, operation: str, call: Callable[[], T],
                             max_attempts: int = 3) -> T:
        for attempt in range(1, max_attempts + 1):
            try:
                return call()
            except LLMTransientError as exc:
                if attempt == max_attempts:
                    raise
                self.track(node, "retry", "Lỗi LLM tạm thời; thử lại operation.", {
                    "operation": operation, "attempt": attempt, "max_attempts": max_attempts,
                    "error": str(exc)[:200],
                })
                self.retry_sleep(0.5 * attempt)
        raise AssertionError("unreachable")

    def run(self, prompt: str) -> PipelineResult:
        self.trace = []
        self.stall_tracker = StallTracker()
        self.semantic_history = []
        self._iteration_start = None
        if hasattr(self.reasoner, "set_call_budget"):
            self.reasoner.set_call_budget(self.max_llm_calls)
        current_prompt = prompt
        iterations = 0
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
                    outcome = self.node_1.ask_for_clarifications(
                        current_prompt, unique_strings(draft.clarification_questions)[:4],
                        "Thong tin bo sung tu nguoi dung",
                    )
                    if outcome.action is ClarificationAction.BLOCK_NO_INPUT:
                        return self._result(draft, semantic, logic, iterations, "blocked", "no_user_input")
                    if outcome.user_answered:
                        self._reset_semantic_after_answer()
                    if self._limit_reached(iterations):
                        return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
                    current_prompt = outcome.prompt
                    continue

                errors = [] if empty_contract else validate_contract(draft.marlowe_contract)
                if errors:
                    logic = LogicGraphResult(False, errors, {"nodes": [], "edges": []})
                    self.track("structural_gate", "fail", "AST chưa hợp lệ.", {"findings": errors})
                    stalled, stall_hint = self._observe_stall("structural", draft.marlowe_contract, errors)
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
                semantic = self._call_llm_with_retry(
                    "node_2_semantic_verification", "semantic_verify",
                    partial(self.node_2.run, current_prompt, draft),
                )
                self.track("node_2_semantic_verification", "pass" if semantic.passed else "fail",
                           "Đã kiểm semantic.", {"findings": semantic.findings,
                                                  "reasoning_narrative": semantic.reasoning_narrative})
                if empty_contract and semantic.passed:
                    self._record_semantic(iterations, current_prompt, draft, semantic)
                    self.track("node_3_logic_graph_verification", "skipped", "Chưa có AST để kiểm logic graph.")
                    return self._result(draft, semantic, logic, iterations, "blocked", "semantic_not_passed")
                if not semantic.passed:
                    stalled, _ = self._observe_stall("semantic", draft.marlowe_contract,
                                                     semantic.findings + semantic.questions)
                    if stalled:
                        self._record_semantic(iterations, current_prompt, draft, semantic)
                        return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                    if self._limit_reached(iterations):
                        self._record_semantic(iterations, current_prompt, draft, semantic)
                        return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
                    outcome = self.node_1.clarify_prompt(
                        current_prompt, semantic, allow_no_action=not self.require_semantic_pass and not empty_contract,
                    )
                    self._record_semantic(iterations, current_prompt, draft, semantic, outcome.user_answered)
                    if outcome.user_answered:
                        self._reset_semantic_after_answer()
                    if outcome.action is ClarificationAction.REGENERATE:
                        current_prompt = outcome.prompt
                        continue
                    if outcome.action is ClarificationAction.BLOCK_NO_INPUT:
                        self.track("node_3_logic_graph_verification", "skipped", "Semantic chưa đạt.")
                        return self._result(draft, semantic, logic, iterations, "blocked", "no_user_input")
                else:
                    self._record_semantic(iterations, current_prompt, draft, semantic)

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
                stalled, stall_hint = self._observe_stall("logic", draft.marlowe_contract, logic.findings)
                if stalled:
                    return self._result(draft, semantic, logic, iterations, "blocked", "stalled")
                if self._limit_reached(iterations):
                    return self._result(draft, semantic, logic, iterations, "blocked", "max_iterations")
                outcome = self.node_1.clarify_logic_prompt(current_prompt, draft, logic, stall_hint)
                if outcome.user_answered:
                    self._reset_semantic_after_answer()
                if outcome.action is ClarificationAction.BLOCK_NO_INPUT:
                    return self._result(draft, semantic, logic, iterations, "blocked", "no_user_input")
                self.track("node_1_prompt_to_draft", "done", "Đã nhận phản hồi từ Node 3.",
                           {"reasoning_narrative": self.node_1.last_clarification_audit})
                current_prompt = outcome.prompt

        except LLMError as exc:
            self.track("pipeline", "error", "Lời gọi LLM thất bại.", {"error": str(exc)})
            return self._result(draft, semantic, logic, iterations, "blocked", "llm_error")
        except KeyboardInterrupt:
            self.track("pipeline", "warn", "Đã dừng theo yêu cầu người dùng.")
            return self._result(draft, semantic, logic, iterations, "blocked", "interrupted")
