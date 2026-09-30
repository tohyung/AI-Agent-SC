from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
from conftest import FakeSMTBackend, make_draft

from marlowe_agent import cli, openai_reasoner
from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.marlowe_ast import pay, prompt_contract_examples
from marlowe_agent.marlowe_validator import (
    ACTION_VARIANTS,
    CONTRACT_VARIANTS,
    OBSERVATION_VARIANTS,
    VALUE_VARIANTS,
    describe_marlowe_grammar,
    validate_contract,
)
from marlowe_agent.models import (
    LLMBudgetError,
    LLMConfigError,
    LLMError,
    LLMTransientError,
    VerificationResult,
)
from marlowe_agent.nodes import AgentPipeline
from marlowe_agent.node3_policy import StructuredWarning
from marlowe_agent.node3_smt import SMTAnalysis
from marlowe_agent.openai_reasoner import OpenAIReasoner, parse_json_text
from tools.fake_reasoner import FakeReasoner


def invalid_contract(index: int) -> dict:
    return {"when": [], "timeout": 1_893_456_000_000,
            "timeout_continuation": "close", "bad_key": index}


def empty_draft(questions: list[str] | None = None):
    draft = make_draft()
    draft.marlowe_contract = {}
    draft.clarification_questions = questions or []
    return draft


def test_empty_contract_with_questions_asks_user(monkeypatch) -> None:
    reasoner = FakeReasoner([empty_draft(["Ai nhận tiền?"]), make_draft()])
    monkeypatch.setattr("builtins.input", lambda _: "Bob")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.status == "done"
    assert "Bob" in result.draft.original_prompt
    assert reasoner.calls == ["draft", "draft", "semantic"]


def test_empty_contract_with_questions_noninteractive_blocks_no_user_input() -> None:
    reasoner = FakeReasoner([empty_draft(["Ai nhận tiền?"])])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.stop_reason == "no_user_input"
    assert reasoner.calls == ["draft"]


def test_empty_contract_without_questions_goes_to_semantic() -> None:
    reasoner = FakeReasoner([empty_draft()], [VerificationResult(False, 0, ["Thiếu bên nhận"], ["Ai nhận?"])])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.stop_reason == "no_user_input"
    assert reasoner.calls == ["draft", "semantic"]
    assert not any(event.node == "structural_gate" and event.status == "fail" for event in result.trace)


def test_empty_contract_blank_user_answers_blocks_no_user_input(monkeypatch) -> None:
    reasoner = FakeReasoner([empty_draft(["Ai nhận tiền?"])])
    monkeypatch.setattr("builtins.input", lambda _: "  ")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.stop_reason == "no_user_input"
    assert reasoner.calls == ["draft"]


def test_empty_contract_semantic_pass_never_reaches_node3() -> None:
    reasoner = FakeReasoner([empty_draft()])
    result = AgentPipeline(reasoner, require_semantic_pass=False).run("escrow")
    assert result.stop_reason == "semantic_not_passed"
    assert reasoner.calls == ["draft", "semantic"]
    assert not any(event.node == "node_3_logic_graph_verification" and event.status == "start" for event in result.trace)


def test_empty_contract_semantic_fail_never_reaches_node3_with_override() -> None:
    semantic = VerificationResult(False, 0.0, ["Thiếu điều kiện"], ["Ai quyết định?"])
    reasoner = FakeReasoner([empty_draft()], [semantic])
    result = AgentPipeline(reasoner, require_semantic_pass=False).run("escrow")
    assert result.stop_reason == "no_user_input"
    assert not any(event.node == "node_3_logic_graph_verification" and event.status == "start" for event in result.trace)


def test_logic_stall_hint_keeps_current_findings() -> None:
    invalid = make_draft(pay("Alice", "Bob", 10))
    reasoner = FakeReasoner([invalid, invalid, make_draft()], clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "Sửa nhánh Pay.",
    }])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "done"
    assert "nhưng chỉ trả được 0" in result.draft.original_prompt
    assert "Không lặp lại cách sửa cũ" in result.draft.original_prompt


def test_logic_repeated_same_instruction_does_not_become_no_user_input() -> None:
    invalid = make_draft(pay("Alice", "Bob", 10))
    reasoner = FakeReasoner([invalid for _ in range(6)] + [make_draft()], clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "Sửa nhánh Pay.",
    }])
    pipeline = AgentPipeline(reasoner)
    result = pipeline.run("escrow")
    assert (result.status, result.stop_reason, result.iterations) == ("done", "ok", 7)
    assert pipeline.stall_count >= 4
    assert reasoner.calls.count("clarification") == 6


def test_logic_real_missing_user_answer_blocks_no_user_input(monkeypatch) -> None:
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10))], clarifications=[{
        "needs_user_input": True, "questions": ["Ai nhận tiền?"], "internal_instruction": "",
    }])
    monkeypatch.setattr("builtins.input", lambda _: " ")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert (result.status, result.stop_reason) == ("blocked", "no_user_input")


def test_logic_blank_user_answer_with_internal_instruction_can_regenerate(monkeypatch) -> None:
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10)), make_draft()], clarifications=[{
        "needs_user_input": True, "questions": ["Ai nhận tiền?"], "internal_instruction": "Sửa nhánh Pay.",
    }])
    monkeypatch.setattr("builtins.input", lambda _: " ")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.status == "done"
    assert result.iterations == 2


def test_logic_no_questions_no_instruction_still_regenerates() -> None:
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10)), make_draft()], clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "",
    }])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "done"
    assert "Lỗi logic hiện tại" in result.draft.original_prompt


def test_semantic_no_action_with_allow_unverified_proceeds_to_node3() -> None:
    semantic = VerificationResult(False, 0.0, ["Thiếu điều kiện"], ["Ai nhận tiền?"])
    result = AgentPipeline(FakeReasoner([make_draft()], [semantic]), require_semantic_pass=False).run("escrow")
    assert result.stop_reason == "semantic_not_passed"
    assert any(event.node == "node_3_logic_graph_verification" and event.status == "start" for event in result.trace)


def test_semantic_stall_resets_after_new_user_answer(monkeypatch) -> None:
    failure = VerificationResult(False, 0.0, ["Thiếu điều kiện"], ["Ai quyết định?"])
    reasoner = FakeReasoner([make_draft() for _ in range(3)], semantics=[
        failure, failure, VerificationResult(True, 1.0, []),
    ])
    answers = iter(["Alice", "Bob"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    pipeline = AgentPipeline(reasoner, interactive=True, stop_on_stall=2)
    result = pipeline.run("escrow")
    assert result.status == "done"
    assert [entry.semantic_generation for entry in result.semantic_history] == [0, 1, 2]
    assert pipeline.stall_count == 0


def test_semantic_stop_on_stall_counts_only_current_generation(monkeypatch) -> None:
    failure = VerificationResult(False, 0.0, ["Thiếu điều kiện"], ["Ai quyết định?"])
    invalid_logic = make_draft(pay("Alice", "Bob", 10))
    reasoner = FakeReasoner([make_draft(), invalid_logic, invalid_logic], semantics=[failure],
                            clarifications=[{"needs_user_input": False, "questions": [],
                                             "internal_instruction": "Sửa Pay."}])
    answers = iter(["Alice", " "])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    result = AgentPipeline(reasoner, interactive=True, require_semantic_pass=False,
                           stop_on_stall=2).run("escrow")
    assert result.stop_reason == "stalled"
    assert result.iterations == 3
    assert [entry.semantic_generation for entry in result.semantic_history] == [0, 1, 1]


def test_semantic_history_survives_stall_reset(monkeypatch) -> None:
    failure = VerificationResult(False, 0.0, ["Thiếu điều kiện"], ["Ai quyết định?"])
    reasoner = FakeReasoner([make_draft(), make_draft()], semantics=[failure, VerificationResult(True, 1.0, [])])
    monkeypatch.setattr("builtins.input", lambda _: "Alice")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    history = result.to_dict()["semantic_history"]
    assert len(history) == 2
    assert [entry["semantic_generation"] for entry in history] == [0, 1]
    assert [entry["user_answered"] for entry in history] == [True, False]
    assert all(len(entry["prompt_fingerprint"]) == 64 for entry in history)
    resets = [event for event in result.trace if event.status == "semantic_reset"]
    assert len(resets) == 1
    assert resets[0].data["history_entries"] == 1
    assert resets[0].data["answered_questions_count"] == 1


def test_logic_user_answer_marks_current_semantic_history_entry(monkeypatch) -> None:
    reasoner = FakeReasoner(
        [make_draft(pay("Alice", "Bob", 10)), make_draft()],
        clarifications=[{"needs_user_input": True, "questions": ["Ai nhận tiền?"],
                         "internal_instruction": ""}],
    )
    monkeypatch.setattr("builtins.input", lambda _: "Bob")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.status == "done"
    assert len(result.semantic_history) == 2
    assert result.semantic_history[0].user_answered is True
    assert result.semantic_history[0].semantic_generation == 0
    assert result.semantic_history[0].answer_source == "logic"
    assert result.semantic_history[1].semantic_generation == 1
    assert result.semantic_history[1].user_answered is False
    assert result.to_dict()["semantic_history"][0]["answer_source"] == "logic"


def test_empty_contract_answer_does_not_mark_previous_history_entry(monkeypatch) -> None:
    reasoner = FakeReasoner(
        [make_draft(pay("Alice", "Bob", 10)), empty_draft(["Ai nhận tiền?"]), make_draft()],
        clarifications=[{"needs_user_input": False, "questions": [],
                         "internal_instruction": "Sửa nhánh Pay."}],
    )
    monkeypatch.setattr("builtins.input", lambda _: "Bob")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.status == "done"
    assert result.semantic_history[0].iteration == 1
    assert result.semantic_history[0].user_answered is False
    assert result.semantic_history[0].answer_source is None
    assert result.semantic_history[1].iteration == 3
    resets = [event for event in result.trace if event.status == "semantic_reset"]
    assert len(resets) == 1
    assert resets[0].data["answer_source"] == "empty_contract"


def test_semantic_answer_records_source_semantic(monkeypatch) -> None:
    failure = VerificationResult(False, 0.0, ["Thiếu điều kiện"], ["Ai quyết định?"])
    reasoner = FakeReasoner([make_draft(), make_draft()],
                            semantics=[failure, VerificationResult(True, 1.0, [])])
    monkeypatch.setattr("builtins.input", lambda _: "Alice")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.status == "done"
    assert result.semantic_history[0].user_answered is True
    assert result.semantic_history[0].answer_source == "semantic"
    assert result.semantic_history[0].semantic_generation == 0
    resets = [event for event in result.trace if event.status == "semantic_reset"]
    assert resets[0].data["answer_source"] == "semantic"


def test_blank_user_answer_does_not_reset_semantic_stall(monkeypatch) -> None:
    failure = VerificationResult(False, 0.0, ["Thiếu điều kiện"], ["Ai quyết định?"])
    invalid_logic = make_draft(pay("Alice", "Bob", 10))
    reasoner = FakeReasoner([invalid_logic], semantics=[failure], clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "Sửa Pay.",
    }])
    monkeypatch.setattr("builtins.input", lambda _: " ")
    pipeline = AgentPipeline(reasoner, interactive=True, require_semantic_pass=False, stop_on_stall=2)
    result = pipeline.run("escrow")
    assert result.stop_reason == "stalled"
    assert [entry.semantic_generation for entry in result.semantic_history] == [0, 0]
    assert pipeline.stall_tracker.semantic_generation == 0
    assert not any(event.status == "semantic_reset" for event in result.trace)


def test_semantic_reset_does_not_clear_logic_or_structural_history(monkeypatch) -> None:
    reasoner = FakeReasoner([
        make_draft(invalid_contract(1)), make_draft(pay("Alice", "Bob", 10)), make_draft(),
    ], clarifications=[{"needs_user_input": True, "questions": ["Ai nhận tiền?"],
                       "internal_instruction": "Sửa Pay."}])
    monkeypatch.setattr("builtins.input", lambda _: "Bob")
    pipeline = AgentPipeline(reasoner, interactive=True)
    result = pipeline.run("escrow")
    assert result.status == "done"
    assert pipeline.stall_tracker.semantic_generation == 1
    assert len(pipeline.stall_tracker.structural_seen) == 1
    assert len(pipeline.stall_tracker.logic_seen) == 1
    assert result.semantic_history[0].iteration == 2
    assert result.semantic_history[0].user_answered is True
    assert result.semantic_history[0].answer_source == "logic"
    assert result.semantic_history[1].user_answered is False


def test_happy_path_done() -> None:
    result = AgentPipeline(FakeReasoner([make_draft()])).run("escrow")
    assert result.status == "done"
    assert result.stop_reason == "ok"
    assert result.iterations == 1
    assert result.to_dict()["marlowe_contract"] == result.draft.marlowe_contract


def test_default_max_iterations_and_max_llm_calls_are_none() -> None:
    reasoner = FakeReasoner([make_draft()])
    pipeline = AgentPipeline(reasoner)
    assert pipeline.max_iterations is None
    assert pipeline.max_llm_calls is None
    assert reasoner.max_llm_calls is None


def test_default_pipeline_can_converge_after_25_iterations() -> None:
    drafts = [make_draft(invalid_contract(index)) for index in range(25)] + [make_draft()]
    result = AgentPipeline(FakeReasoner(drafts)).run("escrow")
    assert result.status == "done"
    assert result.iterations == 26


def test_default_pipeline_can_exceed_40_llm_calls() -> None:
    drafts = [make_draft(pay("Alice", "Bob", index + 1)) for index in range(21)] + [make_draft()]
    reasoner = FakeReasoner(drafts, clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "Sửa nhánh Pay.",
    }])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "done"
    assert len(reasoner.calls) > 40


def test_explicit_max_iterations_still_blocks() -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(index)) for index in range(8)])
    result = AgentPipeline(reasoner, max_iterations=8).run("escrow")
    assert result.stop_reason == "max_iterations"
    assert reasoner.calls.count("draft") == 8


def test_explicit_llm_call_cap_still_blocks() -> None:
    reasoner = FakeReasoner([make_draft()])
    result = AgentPipeline(reasoner, max_llm_calls=1).run("escrow")
    assert result.stop_reason == "llm_error"
    assert reasoner.calls == ["draft"]


@pytest.mark.parametrize("kwargs", [
    {"max_iterations": 0}, {"max_iterations": -1},
    {"max_llm_calls": 0}, {"max_llm_calls": -1},
])
def test_invalid_explicit_limits_raise_value_error(kwargs) -> None:
    with pytest.raises(ValueError):
        AgentPipeline(FakeReasoner([make_draft()]), **kwargs)


def test_cli_defaults_are_unlimited() -> None:
    args = cli.build_parser().parse_args(["--prompt", "escrow"])
    assert args.max_iterations is None
    assert args.max_llm_calls is None


def test_always_invalid_ast_stops_at_max_iterations() -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(index)) for index in range(3)])
    result = AgentPipeline(reasoner, max_iterations=3).run("escrow")
    assert result.status == "blocked"
    assert result.stop_reason == "max_iterations"
    assert reasoner.calls.count("draft") <= 3
    assert "semantic" not in reasoner.calls


def test_stall_detection_stops_when_same_fingerprint_repeats() -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(1))])
    result = AgentPipeline(reasoner, stop_on_stall=2).run("escrow")
    assert result.stop_reason == "stalled"
    assert result.iterations == 2


def test_stall_is_warning_by_default() -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(1)) for _ in range(3)] + [make_draft()])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "done"
    assert result.iterations == 4
    warnings = [event for event in result.trace if event.status == "warn" and event.data.get("reason") == "stalled"]
    assert [event.data["occurrences"] for event in warnings] == [2, 3]


def test_stall_hint_keeps_original_errors() -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(1)), make_draft(invalid_contract(1)), make_draft()])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "done"
    assert "tổ hợp field không hợp lệ" in result.draft.original_prompt
    assert "Không lặp lại cách sửa cũ" in result.draft.original_prompt


def test_stop_on_stall_blocks_when_configured() -> None:
    result = AgentPipeline(FakeReasoner([make_draft(invalid_contract(1))]), stop_on_stall=3).run("escrow")
    assert result.stop_reason == "stalled"
    assert result.iterations == 3


def test_semantic_fail_non_interactive_blocks_with_no_user_input() -> None:
    semantic = VerificationResult(False, 0.2, ["Thiếu điều kiện"], ["Điều kiện giải ngân là gì?"])
    result = AgentPipeline(FakeReasoner([make_draft()], [semantic])).run("escrow")
    assert result.stop_reason == "no_user_input"
    assert not any(event.status == "start" and event.node == "node_3_logic_graph_verification" for event in result.trace)


def test_semantic_fail_interactive_uses_answers(monkeypatch) -> None:
    semantic = VerificationResult(False, 0.2, ["Thiếu điều kiện"], ["Điều kiện giải ngân là gì?"])
    reasoner = FakeReasoner([make_draft(), make_draft()], [semantic, VerificationResult(True, 1.0, [])])
    monkeypatch.setattr("builtins.input", lambda _: "Alice xác nhận")
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.status == "done"
    assert "Alice xác nhận" in result.draft.original_prompt
    assert reasoner.calls.count("semantic") == 2


def test_logic_fail_technical_error_regenerates_without_asking_user(monkeypatch) -> None:
    reasoner = FakeReasoner(
        [make_draft(pay("Alice", "Bob", 10)), make_draft()],
        clarifications=[{"needs_user_input": False, "questions": [],
                         "internal_instruction": "Sinh escrow có Deposit trước Pay.",
                         "reasoning_narrative": "Thiếu tiền trong account."}],
    )
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("No user question expected"))
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "done"
    assert reasoner.calls.count("clarification") == 1
    assert "Sinh escrow" in result.draft.original_prompt


def test_draft_llm_error_is_caught_and_reported(capsys) -> None:
    result = AgentPipeline(FakeReasoner([LLMError("provider unavailable")])).run("escrow")
    assert result.status == "blocked"
    assert result.stop_reason == "llm_error"
    assert result.semantic_verification.questions == []
    assert any(event.status == "error" for event in result.trace)
    assert "Traceback" not in capsys.readouterr().err


def test_semantic_llm_error_is_caught_and_reported(capsys) -> None:
    reasoner = FakeReasoner([make_draft()], semantics=[LLMError("provider unavailable")])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "blocked"
    assert result.stop_reason == "llm_error"
    assert result.semantic_verification.questions == []
    assert reasoner.calls == ["draft", "semantic"]
    assert "Traceback" not in capsys.readouterr().err


def test_semantic_runtime_failure_is_not_business_clarification(monkeypatch) -> None:
    model = OpenAIReasoner.__new__(OpenAIReasoner)

    def fail_response(system: str, user: str) -> dict:
        raise RuntimeError("provider/parser failure")

    monkeypatch.setattr(model, "_json_response", fail_response)
    reasoner = FakeReasoner([make_draft()])
    monkeypatch.setattr(reasoner, "semantic_verify", model.semantic_verify)
    result = AgentPipeline(reasoner).run("escrow")
    assert result.status == "blocked"
    assert result.stop_reason == "llm_error"
    assert result.semantic_verification.questions == []
    assert all("xác nhận lại" not in str(event.data).lower() for event in result.trace)


def test_invalid_numeric_llm_configuration_is_domain_error(monkeypatch) -> None:
    fake_openai = ModuleType("openai")
    fake_openai.OpenAI = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setattr(openai_reasoner, "load_env_file", lambda: None)
    monkeypatch.setenv("LLM_MODEL", "fake")
    monkeypatch.setenv("LLM_API_KEY", "fake")
    monkeypatch.setenv("LLM_MAX_TOKENS", "invalid")
    with pytest.raises(LLMConfigError, match="Cấu hình số cho LLM không hợp lệ"):
        OpenAIReasoner()


def test_semantic_retries_transient_error_then_continues() -> None:
    delays = []
    reasoner = FakeReasoner([make_draft()], semantics=[
        LLMTransientError("temporary 502"), LLMTransientError("temporary 503"),
        VerificationResult(True, 1.0, []),
    ])
    result = AgentPipeline(reasoner, retry_sleep=delays.append).run("escrow")
    assert result.status == "done"
    assert reasoner.calls == ["draft", "semantic", "semantic", "semantic"]
    assert delays == [0.5, 1.0]
    assert len([event for event in result.trace if event.status == "retry"]) == 2
    assert all(event.data["operation"] == "semantic_verify" for event in result.trace if event.status == "retry")
    assert result.semantic_verification.questions == []


def test_draft_retries_transient_error_then_continues() -> None:
    delays = []
    reasoner = FakeReasoner([LLMTransientError("502"), LLMTransientError("503"), make_draft()])
    result = AgentPipeline(reasoner, retry_sleep=delays.append).run("escrow")
    assert result.status == "done"
    assert reasoner.calls == ["draft", "draft", "draft", "semantic"]
    assert delays == [0.5, 1.0]
    retries = [event for event in result.trace if event.status == "retry"]
    assert len(retries) == 2
    assert all(event.data["operation"] == "draft_from_prompt" for event in retries)


@pytest.mark.parametrize("error", [LLMBudgetError("cap"), LLMConfigError("config")])
def test_draft_budget_and_config_errors_are_not_retried(error) -> None:
    reasoner = FakeReasoner([error])
    result = AgentPipeline(reasoner, retry_sleep=lambda _: pytest.fail("No retry expected")).run("escrow")
    assert result.stop_reason == "llm_error"
    assert reasoner.calls == ["draft"]


def test_logic_feedback_retries_transient_error_then_continues() -> None:
    delays = []
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10)), make_draft()], clarifications=[
        LLMTransientError("502"), LLMTransientError("503"),
        {"needs_user_input": False, "questions": [], "internal_instruction": "Sửa Pay."},
    ])
    result = AgentPipeline(reasoner, retry_sleep=delays.append).run("escrow")
    assert result.status == "done"
    assert reasoner.calls.count("clarification") == 3
    assert delays == [0.5, 1.0]
    retries = [event for event in result.trace if event.status == "retry"]
    assert len(retries) == 2
    assert all(event.data["operation"] == "logic_feedback_to_clarification" for event in retries)


def test_logic_feedback_budget_error_is_not_retried() -> None:
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10))], clarifications=[LLMBudgetError("cap")])
    result = AgentPipeline(reasoner, retry_sleep=lambda _: pytest.fail("No retry expected")).run("escrow")
    assert result.stop_reason == "llm_error"
    assert reasoner.calls == ["draft", "semantic", "clarification"]


def test_llm_call_counter_does_not_count_blocked_budget_attempt() -> None:
    real = OpenAIReasoner.__new__(OpenAIReasoner)
    real.set_call_budget(1)
    real._consume_call()
    with pytest.raises(LLMBudgetError):
        real._consume_call()
    assert real.llm_calls == 1

    fake = FakeReasoner([make_draft()])
    fake.set_call_budget(1)
    fake.draft_from_prompt("escrow")
    with pytest.raises(LLMBudgetError):
        fake.draft_from_prompt("escrow")
    assert fake.calls == ["draft"]


def test_semantic_transient_error_exhausted_blocks_llm_error() -> None:
    reasoner = FakeReasoner([make_draft()], semantics=[LLMTransientError("temporary")])
    result = AgentPipeline(reasoner, retry_sleep=lambda _: None).run("escrow")
    assert result.stop_reason == "llm_error"
    assert reasoner.calls == ["draft", "semantic", "semantic", "semantic"]
    assert result.semantic_verification.questions == []


@pytest.mark.parametrize("error", [LLMBudgetError("cap"), LLMConfigError("config")])
def test_semantic_budget_error_is_not_retried(error) -> None:
    reasoner = FakeReasoner([make_draft()], semantics=[error])
    result = AgentPipeline(reasoner, retry_sleep=lambda _: pytest.fail("No retry expected")).run("escrow")
    assert result.stop_reason == "llm_error"
    assert reasoner.calls == ["draft", "semantic"]


def test_logic_feedback_llm_error_is_caught_and_reported(monkeypatch, capsys) -> None:
    reasoner = FakeReasoner(
        [make_draft(pay("Alice", "Bob", 10))],
        clarifications=[LLMError("provider unavailable")],
    )
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("No user question expected"))
    result = AgentPipeline(reasoner, interactive=True).run("escrow")
    assert result.status == "blocked"
    assert result.stop_reason == "llm_error"
    assert result.semantic_verification.questions == []
    assert reasoner.calls == ["draft", "semantic", "clarification"]
    assert "Traceback" not in capsys.readouterr().err


def test_llm_call_cap() -> None:
    result = AgentPipeline(FakeReasoner([make_draft()]), max_llm_calls=1).run("escrow")
    assert result.stop_reason == "llm_error"


def test_final_iteration_does_not_request_logic_feedback() -> None:
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10))])
    result = AgentPipeline(reasoner, max_iterations=1).run("escrow")
    assert result.stop_reason == "max_iterations"
    assert "clarification" not in reasoner.calls


def test_json_array_is_rejected_as_model_response() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_json_text("[]")


def test_node1_prompt_contains_supported_marlowe_grammar(monkeypatch) -> None:
    reasoner = OpenAIReasoner.__new__(OpenAIReasoner)
    captured = {}

    def capture(system, user):
        captured["system"] = system
        captured["user"] = user
        return {}

    monkeypatch.setattr(reasoner, "_json_response", capture)
    reasoner._extract_contract_config("sample")
    assert describe_marlowe_grammar() in captured["system"]
    for variants in (CONTRACT_VARIANTS, ACTION_VARIANTS, VALUE_VARIANTS, OBSERVATION_VARIANTS):
        for name, spec in variants.items():
            assert name + ":" in captured["system"]
            if isinstance(spec, dict):
                assert all(f"{field}: {field_type}" in captured["system"]
                           for field, field_type in spec.items())
    for field in ("role_token", "address", "account", "currency_symbol", "token_name",
                  "choice_name", "choice_owner", "from", "to", "case", "time_interval_start",
                  "time_interval_end", "true", "false"):
        assert field in captured["system"]


def test_node1_prompt_contains_constructor_names_and_types(monkeypatch) -> None:
    reasoner = OpenAIReasoner.__new__(OpenAIReasoner)
    captured = {}
    monkeypatch.setattr(reasoner, "_json_response", lambda system, user: captured.update(system=system) or {})
    reasoner._extract_contract_config("sample")
    for name in ("Close", "Pay", "If", "When", "Let", "Assert", "Deposit", "Choice", "Notify"):
        assert name + ":" in captured["system"]
    for kind in ("Contract", "Action", "Value", "Observation", "Party", "Payee", "Token",
                 "ChoiceId", "Bound", "Case", "POSIXMilliseconds"):
        assert kind in captured["system"]
    assert "pay: Value" in captured["system"]
    assert "to: Payee" in captured["system"]


def test_typed_grammar_and_validator_share_one_source(monkeypatch) -> None:
    from marlowe_agent import marlowe_validator as grammar

    synthetic = {"temporary_role": "Alice"}
    baseline_errors = []
    grammar.validate_party(synthetic, "root", baseline_errors)
    assert baseline_errors
    monkeypatch.setitem(grammar.PARTY_VARIANTS, "TemporaryRole", {"temporary_role": "String"})
    assert "TemporaryRole: { temporary_role: String }" in grammar.describe_marlowe_grammar()
    updated_errors = []
    grammar.validate_party(synthetic, "root", updated_errors)
    assert updated_errors == []
    monkeypatch.delitem(grammar.PARTY_VARIANTS, "TemporaryRole")
    after_errors = []
    grammar.validate_party(synthetic, "root", after_errors)
    assert after_errors == baseline_errors
    assert "TemporaryRole:" not in grammar.describe_marlowe_grammar()


def test_prompt_examples_are_valid() -> None:
    examples = prompt_contract_examples()
    assert len(examples) >= 2
    for example in examples:
        assert validate_contract(example) == []
        assert LogicGraphVerifier().verify(example).errors == []


def test_reasoner_counts_repair_requests_in_call_cap() -> None:
    reasoner = OpenAIReasoner.__new__(OpenAIReasoner)
    reasoner.api_style = "chat"
    reasoner.model = "fake"
    reasoner.max_tokens = 100
    reasoner.retry_attempts = 1
    reasoner.retry_base_delay = 0
    reasoner.base_url = None
    reasoner.set_call_budget(1)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))])

    reasoner.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(LLMBudgetError):
        reasoner._json_response("system", "user")
    assert len(calls) == 1
    assert reasoner.llm_calls == 1


def test_after_regenerate_always_reruns_semantic_before_logic() -> None:
    reasoner = FakeReasoner(
        [make_draft(pay("Alice", "Bob", 10)), make_draft()],
        clarifications=[{"needs_user_input": False, "questions": [], "internal_instruction": "Fix Pay"}],
    )
    result = AgentPipeline(reasoner).run("escrow")
    starts = [event.node for event in result.trace if event.status == "start" and event.node.startswith("node_")]
    assert starts == [
        "node_1_prompt_to_draft", "node_2_semantic_verification", "node_3_logic_graph_verification",
        "node_1_prompt_to_draft", "node_2_semantic_verification", "node_3_logic_graph_verification",
    ]


def test_cli_exit_code_2_when_blocked(monkeypatch) -> None:
    monkeypatch.setattr(cli, "OpenAIReasoner", lambda model=None: FakeReasoner([make_draft(invalid_contract(1))]))
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow", "--max-iterations", "1", "--trace-only"])
    assert cli.main() == 2


@pytest.mark.parametrize("error", [RuntimeError("missing API key"), LLMError("invalid configuration")])
def test_cli_reasoner_initialization_error_does_not_traceback(monkeypatch, capsys, error) -> None:
    def fail_initialization(model=None):
        raise error

    monkeypatch.setattr(cli, "OpenAIReasoner", fail_initialization)
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow"])
    assert cli.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == f"Lỗi khởi tạo LLM: {error}"
    assert "Traceback" not in captured.err


def test_cli_out_file_written(monkeypatch, tmp_path) -> None:
    target = tmp_path / "result.json"
    monkeypatch.setattr(cli, "OpenAIReasoner", lambda model=None: FakeReasoner([make_draft()]))
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow", "--out", str(target)])
    assert cli.main() == 0
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "done"


def test_progress_line_and_jsonl_log_written_each_iteration(monkeypatch, tmp_path, capsys) -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(1)), make_draft()])
    monkeypatch.setattr(cli, "OpenAIReasoner", lambda model=None: reasoner)
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow", "--run-log-dir", str(tmp_path)])
    assert cli.main() == 0
    lines = capsys.readouterr().out
    assert "Lượt 1 | structural=FAIL" in lines
    assert "Lượt 2 | structural=PASS | semantic=PASS | logic=PASS" in lines
    logs = list(tmp_path.glob("*.jsonl"))
    assert len(logs) == 1
    records = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    assert [item["iteration"] for item in records] == [1, 2]
    assert records[0]["structural"] == "fail"
    assert records[1]["llm_calls"] == 3


def test_run_log_write_failure_does_not_break_run(monkeypatch, tmp_path, capsys) -> None:
    target = tmp_path / "not_a_directory"
    target.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(cli, "OpenAIReasoner", lambda model=None: FakeReasoner([make_draft()]))
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow", "--run-log-dir", str(target)])
    assert cli.main() == 0
    assert "không ghi được run log" in capsys.readouterr().err


def test_keyboard_interrupt_returns_partial_result(monkeypatch, tmp_path, capsys) -> None:
    draft = make_draft()
    reasoner = FakeReasoner([draft], semantics=[KeyboardInterrupt()])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.stop_reason == "interrupted"
    assert result.draft.marlowe_contract == draft.marlowe_contract
    assert result.iterations == 1
    assert result.trace
    assert "Traceback" not in capsys.readouterr().err

    target = tmp_path / "partial.json"
    monkeypatch.setattr(cli, "OpenAIReasoner", lambda model=None: FakeReasoner([draft], semantics=[KeyboardInterrupt()]))
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow", "--out", str(target),
                                   "--run-log-dir", str(tmp_path)])
    assert cli.main() == 130
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["stop_reason"] == "interrupted"
    assert payload["draft"]["marlowe_contract"] == draft.marlowe_contract


def test_cli_exit_code_130_on_interrupt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    target = tmp_path / "empty_partial.json"
    monkeypatch.setattr(sys, "argv", ["main.py", "--out", str(target), "--no-run-log"])
    assert cli.main() == 130
    assert json.loads(target.read_text(encoding="utf-8"))["stop_reason"] == "interrupted"


def test_cli_reasoner_initialization_interrupt_writes_partial_result(monkeypatch, tmp_path) -> None:
    def interrupt(model=None):
        raise KeyboardInterrupt()

    target = tmp_path / "init_partial.json"
    monkeypatch.setattr(cli, "OpenAIReasoner", interrupt)
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow", "--out", str(target), "--no-run-log"])
    assert cli.main() == 130
    assert json.loads(target.read_text(encoding="utf-8"))["stop_reason"] == "interrupted"


def test_live_node3_serialization_and_trace_are_compatible() -> None:
    backend = FakeSMTBackend(["valid"])
    result = AgentPipeline(FakeReasoner([make_draft()]), node3_backend=backend).run("escrow")
    assert (result.status, result.stop_reason, result.iterations) == ("done", "ok", 1)
    payload = result.to_dict()["logic_verification"]
    assert {"passed", "findings", "errors", "warnings", "graph", "paths_explored",
            "verification_backend", "smt_status", "smt_warnings", "counterexample",
            "analysis_notes", "lint_errors", "lint_warnings"} <= payload.keys()
    assert "contract" not in payload
    event = next(event for event in result.trace if event.node == "node_3_logic_graph_verification"
                 and event.status == "pass")
    assert event.data["verification_backend"] == "marlowe-smt"
    assert event.data["findings"] == event.data["errors"] + event.data["warnings"]
    assert backend.call_count == 1


def test_blocking_lint_skips_smt_and_enters_repair_flow() -> None:
    draft = make_draft()
    draft.parties = [draft.parties[0]]
    backend = FakeSMTBackend(["valid"])
    reasoner = FakeReasoner([draft, make_draft()], clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "Sửa vai trò còn thiếu.",
    }])
    result = AgentPipeline(reasoner, node3_backend=backend).run("escrow")
    assert result.status == "done"
    first = next(event for event in result.trace if event.node == "node_3_logic_graph_verification"
                 and event.status == "fail")
    assert first.data["smt_status"] == "not_run"
    assert backend.call_count == 1
    assert reasoner.calls.count("clarification") == 1


@pytest.mark.parametrize(("statuses", "expected_status", "expected_calls"), [
    (["timeout", "valid"], "done", 2),
    (["timeout", "timeout"], "blocked", 2),
    (["indeterminate", "indeterminate"], "blocked", 2),
    (["unavailable"], "blocked", 1),
    (["invalid_input"], "blocked", 1),
])
def test_smt_inconclusive_policy(statuses, expected_status, expected_calls) -> None:
    backend = FakeSMTBackend(statuses)
    reasoner = FakeReasoner([make_draft()])
    pipeline = AgentPipeline(reasoner, node3_backend=backend, stop_on_stall=2)
    result = pipeline.run("escrow")
    assert result.status == expected_status
    assert result.stop_reason == ("ok" if expected_status == "done" else "logic_inconclusive")
    assert result.iterations == 1
    assert reasoner.calls == ["draft", "semantic"]
    assert backend.call_count == expected_calls
    assert pipeline.stall_count == 0
    assert pipeline.stall_tracker.logic_seen == {}
    assert result.semantic_history[0].semantic_generation == 0
    assert not any(event.status == "semantic_reset" for event in result.trace)
    node3_events = [event for event in result.trace if event.node == "node_3_logic_graph_verification"
                    and event.status in {"pass", "fail", "inconclusive"}]
    assert [event.data["smt_attempt"] for event in node3_events] == list(range(1, expected_calls + 1))
    assert next(event.data["logic"] for event in result.trace if event.status == "iteration") == (
        "pass" if expected_status == "done" else "inconclusive"
    )


def test_valid_with_analysis_note_blocks_without_retry() -> None:
    backend = FakeSMTBackend([SMTAnalysis("valid", [], None, ["Merkleized continuation incomplete"], 0.01)])
    reasoner = FakeReasoner([make_draft()])
    result = AgentPipeline(reasoner, node3_backend=backend).run("escrow")
    assert (result.status, result.stop_reason) == ("blocked", "logic_inconclusive")
    assert backend.call_count == 1
    assert reasoner.calls == ["draft", "semantic"]


def test_indeterminate_then_counterexample_repairs_after_second_attempt() -> None:
    backend = FakeSMTBackend(["indeterminate", "counterexample", "valid"])
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10)), make_draft()], clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "Sửa Pay.",
    }])
    result = AgentPipeline(reasoner, node3_backend=backend).run("escrow")
    assert result.status == "done"
    assert result.iterations == 2
    assert reasoner.calls == ["draft", "semantic", "clarification", "draft", "semantic"]
    assert backend.call_count == 3
    states = [event.status for event in result.trace if event.node == "node_3_logic_graph_verification"
              and event.status in {"pass", "fail", "inconclusive"}]
    assert states == ["inconclusive", "fail", "pass"]


def test_counterexample_fingerprint_ignores_timing_but_tracks_warning_fields() -> None:
    contract = pay("Alice", "Bob", 10)
    warning = StructuredWarning("TransactionAssertionFailed", {})
    backend = FakeSMTBackend([
        SMTAnalysis("counterexample", [warning], {}, [], 0.01),
        SMTAnalysis("counterexample", [warning], {}, [], 9.99),
    ])
    clarification = [{"needs_user_input": False, "questions": [], "internal_instruction": "Sửa Assert."}]
    pipeline = AgentPipeline(FakeReasoner([make_draft(contract), make_draft(contract)],
                                         clarifications=clarification),
                             node3_backend=backend, stop_on_stall=2)
    result = pipeline.run("escrow")
    assert (result.stop_reason, result.iterations) == ("stalled", 2)
    assert backend.call_count == 2
    assert pipeline.stall_count == 1

    changed = FakeSMTBackend([
        SMTAnalysis("counterexample", [StructuredWarning("FutureWarning", {"amount": 1})], {}, [], 0.01),
        SMTAnalysis("counterexample", [StructuredWarning("FutureWarning", {"amount": 2})], {}, [], 9.99),
        SMTAnalysis("valid", [], None, [], 0.01),
    ])
    changed_result = AgentPipeline(FakeReasoner([make_draft(contract), make_draft(contract), make_draft()],
                                                clarifications=clarification),
                                   node3_backend=changed, stop_on_stall=2).run("escrow")
    assert changed_result.status == "done"


def test_fake_benchmark_does_not_spawn_smt(monkeypatch) -> None:
    from bench.cases import load_cases
    from bench.runner import run_case
    from marlowe_agent import node3_smt

    original_run = node3_smt.subprocess.run

    def reject_smt(*args, **kwargs):
        if "run_smt.py" in str(args[0]):
            pytest.fail("fake benchmark spawned SMT")
        return original_run(*args, **kwargs)

    monkeypatch.setattr(node3_smt.subprocess, "run", reject_smt)
    record = run_case(load_cases()[0], fake=True)
    assert record["error"] is None
    assert record["status"] == "done"


def test_cli_trace_only_success_with_live_node3_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "OpenAIReasoner", lambda model=None: FakeReasoner([make_draft()]))
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "escrow", "--trace-only", "--no-run-log"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "Node 3 - Verification" in output
    assert "logic_passed: True" in output


def test_timeout_retry_reuses_lint_result(monkeypatch) -> None:
    backend = FakeSMTBackend(["timeout", "valid"])
    reasoner = FakeReasoner([make_draft()])
    pipeline = AgentPipeline(reasoner, node3_backend=backend)
    lint_calls = []
    original = pipeline.node_3.verifier.lint

    def count_lint(*args, **kwargs):
        lint_calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline.node_3.verifier, "lint", count_lint)
    result = pipeline.run("escrow")
    assert result.status == "done"
    assert result.iterations == 1
    assert reasoner.calls == ["draft", "semantic"]
    assert backend.call_count == 2
    assert len(lint_calls) == 1


def test_mapper_exception_keeps_counterexample_failure(monkeypatch) -> None:
    from marlowe_agent import nodes

    monkeypatch.setattr(nodes, "map_counterexample", lambda *_args: (_ for _ in ()).throw(RuntimeError("bad")))
    backend = FakeSMTBackend(["counterexample"])
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10))])
    result = AgentPipeline(reasoner, node3_backend=backend, max_iterations=1).run("escrow")
    assert result.logic_verification.decision == "fail"
    assert result.logic_verification.errors
    assert result.logic_verification.structured_findings[0].path_status == "unmapped"
    assert result.logic_verification.structured_findings[0].mapping_reason == "mapper_internal_error"
    assert result.stop_reason == "max_iterations"


def test_node1_feedback_gets_verified_path_without_ast_fragments(monkeypatch) -> None:
    from pathlib import Path

    contract = json.loads((Path(__file__).resolve().parents[2] / "tools" / "marlowe_smt" /
                           "tests" / "partial_pay.json").read_text(encoding="utf-8"))
    counterexample = {"start_time": "0", "transactions": [{
        "interval": {"from": "0", "to": "0"},
        "inputs": [{"type": "Deposit", "account": {"role_token": "Alice"},
                    "party": {"role_token": "Alice"},
                    "token": {"currency_symbol": "", "token_name": ""}, "amount": 10}],
    }]}
    analysis = SMTAnalysis("counterexample", [StructuredWarning("TransactionPartialPay", {
        "account": {"role_token": "Alice"}, "payee": {"party": {"role_token": "Bob"}},
        "paid": 10, "expected": 20,
    })], counterexample, [], 0.01)
    backend = FakeSMTBackend([analysis, "valid"])
    reasoner = FakeReasoner([make_draft(contract), make_draft()])
    model = OpenAIReasoner.__new__(OpenAIReasoner)
    captured = {}

    def capture_response(system, user):
        captured["system"] = system
        captured["payload"] = json.loads(user.split("Input:\n", 1)[1])
        return {"needs_user_input": False, "questions": [],
                "internal_instruction": "Sửa Pay dựa trên path đã kiểm chứng."}

    monkeypatch.setattr(model, "_json_response", capture_response)
    monkeypatch.setattr(reasoner, "logic_feedback_to_clarification",
                        lambda prompt, draft, logic: model.logic_feedback_to_clarification(prompt, draft, logic))
    result = AgentPipeline(reasoner, node3_backend=backend).run("escrow")
    assert result.status == "done"
    first = next(event for event in result.trace if event.node == "node_3_logic_graph_verification"
                 and event.status == "fail")
    finding = first.data["structured_findings"][0]
    assert finding["path_status"] == "verified"
    assert finding["ast_path"] == "root.when[0].then.pay"
    assert finding["ast_path"] in first.data["errors"][0]
    assert captured["payload"]["structured_findings"][0]["ast_path"] == finding["ast_path"]
    assert {"marlowe_contract", "ast_fragment", "candidate_paths"}.isdisjoint(captured["payload"])
    assert finding["ast_path"] in result.draft.original_prompt
    assert "never invent an AST path" in captured["system"]


def test_timeout_then_counterexample_runs_mapper_only_on_second_attempt(monkeypatch) -> None:
    from marlowe_agent import nodes

    backend = FakeSMTBackend(["timeout", "counterexample", "valid"])
    reasoner = FakeReasoner([make_draft(pay("Alice", "Bob", 10)), make_draft()], clarifications=[{
        "needs_user_input": False, "questions": [], "internal_instruction": "Sửa Pay.",
    }])
    pipeline = AgentPipeline(reasoner, node3_backend=backend)
    mapping_calls = []
    lint_calls = []
    original_map = nodes.map_counterexample
    original_lint = pipeline.node_3.verifier.lint

    def count_map(*args):
        mapping_calls.append(1)
        return original_map(*args)

    def count_lint(*args):
        lint_calls.append(1)
        return original_lint(*args)

    monkeypatch.setattr(nodes, "map_counterexample", count_map)
    monkeypatch.setattr(pipeline.node_3.verifier, "lint", count_lint)
    result = pipeline.run("escrow")
    assert result.status == "done"
    assert reasoner.calls == ["draft", "semantic", "clarification", "draft", "semantic"]
    assert backend.call_count == 3
    assert len(mapping_calls) == 1
    assert len(lint_calls) == 2
