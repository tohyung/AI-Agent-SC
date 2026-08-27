from __future__ import annotations

from typing import Any
from collections.abc import Callable

from .logic_graph import LogicGraphVerifier
from .models import ContractDraft, LogicGraphResult, PipelineResult, TraceEvent, VerificationResult


class PromptToDraftNode:
    def __init__(self, reasoner: Any, interactive: bool = False) -> None:
        self.reasoner = reasoner
        self.interactive = interactive
        self.last_clarification_audit = ""

    def run(self, prompt: str) -> ContractDraft:
        return self.reasoner.draft_from_prompt(prompt)

    def clarify_prompt(self, prompt: str, verification: VerificationResult) -> str:
        if verification.passed:
            return prompt
        self.last_clarification_audit = verification.reasoning_narrative
        return self.ask_for_clarifications(
            prompt,
            _unique_strings(verification.questions or verification.findings)[:4],
            "Thong tin bo sung tu nguoi dung",
        )

    def clarify_logic_prompt(self, prompt: str, draft: ContractDraft, logic: LogicGraphResult) -> str:
        if logic.passed:
            return prompt
        clarification = self.reasoner.logic_feedback_to_clarification(prompt, draft, logic)
        self.last_clarification_audit = str(clarification.get("reasoning_narrative") or "")

        internal_instruction = str(clarification.get("internal_instruction") or "").strip()
        questions = _unique_strings(clarification.get("questions") or [])[:4]

        if clarification.get("needs_user_input") and questions:
            next_prompt = self.ask_for_clarifications(
                prompt,
                questions,
                "Thong tin bo sung tu nguoi dung sau kiem logic graph",
            )
            if next_prompt != prompt:
                return self.append_internal_feedback(next_prompt, internal_instruction)

        if internal_instruction:
            return self.append_internal_feedback(prompt, internal_instruction)

        return self.append_internal_feedback(
            prompt,
            (
                "Node 3 phat hien loi logic/AST trong ban draft truoc. "
                "Hay sinh lai marlowe_contract hop le ve cau truc, co du nhanh Close, "
                "khong tao case trung lap, khong tao Pay voi so tien <= 0, va giu nguyen y dinh nghiep vu cua nguoi dung."
            ),
        )

    def ask_for_clarifications(self, prompt: str, prompts: list[str], heading: str) -> str:
        if not self.interactive or not prompts:
            return prompt

        additions: list[str] = []
        for index, question in enumerate(prompts, start=1):
            answer = input(f"Cau hoi {index}: {question}\n> ").strip()
            if answer:
                additions.append(f"- {question}\n  Tra loi: {answer}")
        if not additions:
            return prompt
        return prompt + f"\n\n{heading}:\n" + "\n".join(additions)

    def append_internal_feedback(self, prompt: str, instruction: str) -> str:
        if not instruction.strip():
            return prompt
        prompt = prompt.split("\n\nPhan hoi noi bo tu Node 3 de Node 1 sinh lai draft:\n", 1)[0]
        return (
            prompt
            + "\n\nPhan hoi noi bo tu Node 3 de Node 1 sinh lai draft:\n"
            + instruction.strip()
        )


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
        nodes_count = len(logic.graph.get("nodes", []))
        edges_count = len(logic.graph.get("edges", []))
        if logic.passed:
            return (
                "Node 3 đã dựng logic graph từ AST Marlowe và không thấy lỗi cấu trúc hoặc nhánh xử lý bất thường. "
                f"Graph có {nodes_count} node và {edges_count} cạnh, nên hợp đồng được xem là qua cổng kiểm logic."
            )
        findings = "; ".join(logic.findings[:3])
        suffix = "..." if len(logic.findings) > 3 else ""
        return (
            "Node 3 đã dựng logic graph và phát hiện hợp đồng chưa an toàn để chốt. "
            f"Các vấn đề chính: {findings}{suffix} "
            "Pipeline sẽ đưa các phát hiện này về Node 1 để hỏi bổ sung và sinh lại draft."
        )


TraceCallback = Callable[[TraceEvent], None]


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = " ".join(text.split()).casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


class AgentPipeline:
    def __init__(
        self,
        reasoner: Any,
        interactive: bool = False,
        max_iterations: int | None = None,
        require_semantic_pass: bool = True,
        trace_callback: TraceCallback | None = None,
    ) -> None:
        self.node_1 = PromptToDraftNode(reasoner, interactive=interactive)
        self.node_2 = SemanticVerificationNode(reasoner)
        self.node_3 = LogicGraphVerificationNode()
        self.max_iterations = max_iterations
        self.require_semantic_pass = require_semantic_pass
        self.trace_callback = trace_callback
        self.trace: list[TraceEvent] = []

    def track(self, node: str, status: str, message: str, data: dict | None = None) -> None:
        event = TraceEvent(node=node, status=status, message=message, data=data or {})
        self.trace.append(event)
        if self.trace_callback:
            self.trace_callback(event)

    def run_node_1(self, prompt: str, start_message: str, done_message: str) -> ContractDraft:
        self.track("node_1_prompt_to_draft", "start", start_message)
        draft = self.node_1.run(prompt)
        self.track(
            "node_1_prompt_to_draft",
            "done",
            done_message,
            {
                "intent": draft.intent,
                "parties": [party.to_dict() for party in draft.parties],
                "amount": draft.amount,
                "clauses_count": len(draft.clauses),
                "assumptions_count": len(draft.assumptions),
                "reasoning_summary": draft.reasoning_summary,
                "reasoning_narrative": draft.reasoning_narrative,
                "contract_root": next(iter(draft.marlowe_contract.keys()), None) if draft.marlowe_contract else None,
            },
        )
        return draft

    def run_node_2(self, prompt: str, draft: ContractDraft, start_message: str, done_message: str) -> VerificationResult:
        self.track("node_2_semantic_verification", "start", start_message)
        semantic = self.node_2.run(prompt, draft)
        self.track(
            "node_2_semantic_verification",
            "pass" if semantic.passed else "fail",
            done_message,
            {
                "score": semantic.score,
                "reasoning_summary": semantic.reasoning_summary,
                "reasoning_narrative": semantic.reasoning_narrative,
                "findings": semantic.findings,
                "questions": semantic.questions,
            },
        )
        return semantic

    def run(self, prompt: str) -> PipelineResult:
        current_prompt = prompt
        self.track(
            "pipeline",
            "start",
            "Đã nhận prompt của người dùng và bắt đầu chu trình agent.",
            {"prompt_preview": prompt[:240], "max_iterations": self.max_iterations},
        )

        draft = self.run_node_1(
            current_prompt,
            "Model đang đọc hiểu prompt và sinh bản phác thảo Marlowe.",
            "Model đã sinh bản phác thảo.",
        )
        semantic = self.run_node_2(
            current_prompt,
            draft,
            "Model đang kiểm chứng semantic giữa prompt và draft.",
            "Model đã hoàn tất kiểm chứng semantic.",
        )

        iterations = 1
        while not semantic.passed and (
            self.max_iterations is None or iterations < self.max_iterations
        ):
            self.track(
                "node_1_prompt_to_draft",
                "start",
                "Semantic chưa đạt; Node 1 đang hỏi bổ sung trước khi sinh lại draft.",
                {"iteration": iterations, "questions": semantic.questions, "findings": semantic.findings},
            )
            next_prompt = self.node_1.clarify_prompt(current_prompt, semantic)
            if next_prompt == current_prompt:
                self.track(
                    "node_1_prompt_to_draft",
                    "blocked",
                    "Không có thông tin bổ sung; workflow không thể tiếp tục an toàn.",
                )
                break
            current_prompt = next_prompt
            self.track(
                "node_1_prompt_to_draft",
                "done",
                "Đã ghép thông tin bổ sung vào prompt; yêu cầu model sinh lại draft.",
                {"iteration": iterations + 1},
            )

            draft = self.run_node_1(
                current_prompt,
                "Model đang sinh lại draft từ prompt đã bổ sung.",
                "Model đã sinh lại draft.",
            )
            semantic = self.run_node_2(
                current_prompt,
                draft,
                "Model đang kiểm chứng lại draft sau bổ sung.",
                "Model đã hoàn tất kiểm chứng semantic sau bổ sung.",
            )
            iterations += 1

        if self.require_semantic_pass and not semantic.passed:
            logic = LogicGraphResult(
                passed=False,
                findings=[
                    "Skipped logic graph verification because semantic verification did not pass.",
                    "Có thể tiếp tục bổ sung thông tin theo questions trước khi sinh hợp đồng Marlowe đáng tin.",
                ],
                graph={"nodes": [], "edges": []},
            )
            self.track(
                "node_3_logic_graph_verification",
                "skipped",
                "Cổng semantic chưa đạt; không chạy kiểm chứng logic graph.",
                {
                    "semantic_findings": semantic.findings,
                    "semantic_questions": semantic.questions,
                    "reasoning_narrative": (
                        "Node 3 chưa chạy vì Node 2 vẫn chưa xác nhận draft khớp yêu cầu người dùng. "
                        "Việc kiểm logic graph bị hoãn để tránh xác thực một hợp đồng chưa rõ nghĩa nghiệp vụ."
                    ),
                },
            )
            self.track(
                "pipeline",
                "blocked",
                "Workflow dừng trước bước kiểm chứng hợp đồng cuối.",
                {"iterations": iterations, "semantic_passed": semantic.passed, "logic_passed": logic.passed},
            )
            return PipelineResult(
                draft=draft,
                semantic_verification=semantic,
                logic_verification=logic,
                iterations=iterations,
                trace=self.trace,
            )

        while True:
            self.track("node_3_logic_graph_verification", "start", "Đang dựng graph nhánh và kiểm chứng logic hợp đồng.")
            logic = self.node_3.run(draft)
            self.track(
                "node_3_logic_graph_verification",
                "pass" if logic.passed else "fail",
                "Đã hoàn tất kiểm chứng logic graph.",
                {
                    "findings": logic.findings,
                    "nodes_count": len(logic.graph.get("nodes", [])),
                    "edges_count": len(logic.graph.get("edges", [])),
                    "reasoning_narrative": self.node_3.audit_narrative(logic),
                },
            )
            if logic.passed:
                break

            self.track(
                "node_1_prompt_to_draft",
                "start",
                "Logic graph chưa đạt; Node 1 đang hỏi bổ sung dựa trên findings của Node 3.",
                {"iteration": iterations, "logic_findings": logic.findings},
            )
            next_prompt = self.node_1.clarify_logic_prompt(current_prompt, draft, logic)
            if next_prompt == current_prompt:
                self.track(
                    "node_1_prompt_to_draft",
                    "blocked",
                    "Không có thông tin bổ sung từ lỗi logic; workflow không thể tiếp tục an toàn.",
                )
                break
            current_prompt = next_prompt
            iterations += 1
            self.track(
                "node_1_prompt_to_draft",
                "done",
                "Đã ghép thông tin bổ sung từ lỗi logic vào prompt; yêu cầu model sinh lại draft.",
                {
                    "iteration": iterations,
                    "reasoning_narrative": self.node_1.last_clarification_audit,
                },
            )

            draft = self.run_node_1(
                current_prompt,
                "Model đang sinh lại draft sau phản hồi logic graph.",
                "Model đã sinh lại draft sau phản hồi logic graph.",
            )
            semantic = self.run_node_2(
                current_prompt,
                draft,
                "Model đang kiểm chứng lại draft sau phản hồi logic graph.",
                "Model đã hoàn tất kiểm chứng semantic sau phản hồi logic graph.",
            )

            while not semantic.passed and (
                self.max_iterations is None or iterations < self.max_iterations
            ):
                self.track(
                    "node_1_prompt_to_draft",
                    "start",
                    "Semantic chưa đạt sau phản hồi logic; Node 1 đang hỏi bổ sung trước khi chạy lại Node 3.",
                    {"iteration": iterations, "questions": semantic.questions, "findings": semantic.findings},
                )
                next_prompt = self.node_1.clarify_prompt(current_prompt, semantic)
                if next_prompt == current_prompt:
                    self.track(
                        "node_1_prompt_to_draft",
                        "blocked",
                        "Không có thông tin bổ sung; workflow không thể tiếp tục an toàn.",
                    )
                    break
                current_prompt = next_prompt
                iterations += 1
                self.track(
                    "node_1_prompt_to_draft",
                    "done",
                    "Đã ghép thông tin semantic bổ sung vào prompt; yêu cầu model sinh lại draft.",
                    {"iteration": iterations},
                )

                draft = self.run_node_1(
                    current_prompt,
                    "Model đang sinh lại draft từ prompt đã bổ sung.",
                    "Model đã sinh lại draft.",
                )
                semantic = self.run_node_2(
                    current_prompt,
                    draft,
                    "Model đang kiểm chứng lại draft sau bổ sung.",
                    "Model đã hoàn tất kiểm chứng semantic sau bổ sung.",
                )

            if self.require_semantic_pass and not semantic.passed:
                logic = LogicGraphResult(
                    passed=False,
                    findings=[
                        "Skipped logic graph verification because semantic verification did not pass after logic feedback.",
                        "Có thể tiếp tục bổ sung thông tin theo questions trước khi sinh hợp đồng Marlowe đáng tin.",
                    ],
                    graph={"nodes": [], "edges": []},
                )
                self.track(
                    "node_3_logic_graph_verification",
                    "skipped",
                    "Cổng semantic chưa đạt sau phản hồi logic; không chạy lại kiểm chứng logic graph.",
                    {
                        "semantic_findings": semantic.findings,
                        "semantic_questions": semantic.questions,
                        "reasoning_narrative": (
                            "Node 3 chưa chạy lại vì bản draft mới sau phản hồi logic chưa pass semantic. "
                            "Pipeline ưu tiên làm rõ nghĩa hợp đồng ở Node 2 trước, rồi mới kiểm graph."
                        ),
                    },
                )
                break

        self.track(
            "pipeline",
            "done" if logic.passed else "blocked",
            "Workflow agent đã hoàn tất." if logic.passed else "Workflow dừng trước khi Node 3 pass.",
            {"iterations": iterations, "semantic_passed": semantic.passed, "logic_passed": logic.passed},
        )
        return PipelineResult(
            draft=draft,
            semantic_verification=semantic,
            logic_verification=logic,
            iterations=iterations,
            trace=self.trace,
        )
