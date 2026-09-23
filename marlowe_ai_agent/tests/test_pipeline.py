from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
from conftest import make_draft
from marlowe_agent import cli, openai_reasoner
from marlowe_agent.marlowe_ast import pay
from marlowe_agent.models import LLMError, VerificationResult
from marlowe_agent.nodes import AgentPipeline
from marlowe_agent.openai_reasoner import OpenAIReasoner, parse_json_text
from tools.fake_reasoner import FakeReasoner


def invalid_contract(index: int) -> dict:
    return {"when": [], "timeout": 1_893_456_000_000,
            "timeout_continuation": "close", "bad_key": index}


def test_happy_path_done() -> None:
    result = AgentPipeline(FakeReasoner([make_draft()])).run("escrow")
    assert result.status == "done"
    assert result.stop_reason == "ok"
    assert result.iterations == 1
    assert result.to_dict()["marlowe_contract"] == result.draft.marlowe_contract


def test_always_invalid_ast_stops_at_max_iterations() -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(index)) for index in range(3)])
    result = AgentPipeline(reasoner, max_iterations=3).run("escrow")
    assert result.status == "blocked"
    assert result.stop_reason == "max_iterations"
    assert reasoner.calls.count("draft") <= 3
    assert "semantic" not in reasoner.calls


def test_stall_detection_stops_when_same_fingerprint_repeats() -> None:
    reasoner = FakeReasoner([make_draft(invalid_contract(1))])
    result = AgentPipeline(reasoner).run("escrow")
    assert result.stop_reason == "stalled"
    assert result.iterations == 2


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
    with pytest.raises(LLMError, match="Cấu hình số cho LLM không hợp lệ"):
        OpenAIReasoner()


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
    with pytest.raises(LLMError):
        reasoner._json_response("system", "user")
    assert len(calls) == 1


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
