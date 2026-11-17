"""The supported CLI must not load the old Node 1/2/3 reasoner client."""

import subprocess
import sys

import pytest

from research.formalization.intent_spec import CORE_SCHEMA_VERSION_V4


def test_cli_import_does_not_load_legacy_pipeline():
    probe = (
        "import sys; from research.orchestration.cli import build_parser; "
        "build_parser(); "
        "assert 'research.adapters.openai_reasoner' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", probe], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            check=False)
    assert result.returncode == 0


def test_cli_has_no_legacy_mode():
    from research.orchestration.cli import build_parser

    names = {option for action in build_parser()._actions for option in action.option_strings}
    assert "--research-mode" not in names
    assert "--allow-unverified" not in names


def test_main_calls_only_assurance_session(monkeypatch, capsys):
    from research.orchestration import cli

    calls = []
    providers = []
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "Alice pays Bob",
                                          "--no-run-log", "--json"])
    monkeypatch.setattr(cli, "build_model",
                        lambda provider, _model: providers.append(provider) or object())
    monkeypatch.setattr(cli, "config_from_environment", lambda: None)

    def fake_session(prompt, _model, *, options, ask, emit):
        calls.append((prompt, options.max_iterations, options.core_schema_version, ask, emit))
        return {"status": "WAITING_USER", "stop_reason": "explicit_acceptance_required"}

    monkeypatch.setattr(cli, "run_session", fake_session)
    assert cli.main() == 2
    assert calls == [("Alice pays Bob", 8, CORE_SCHEMA_VERSION_V4, None, None)]
    assert providers == ["gemini"]
    assert '"stop_reason": "explicit_acceptance_required"' in capsys.readouterr().out


def test_gemini_is_built_like_the_e7_pipeline_arm(monkeypatch):
    from research.orchestration import cli

    seen = {}
    monkeypatch.setattr(cli, "ModelTransport",
                        lambda model, **kwargs: seen.update(model=model, **kwargs) or object())
    cli.build_model("gemini", None)
    assert seen["provider"] == "gemini" and seen["max_tokens"] == 16000
    assert seen["disable_reasoning"] is True and seen["request_json_object"] is False
    assert callable(seen["before_request"])


def test_session_end_is_a_plain_summary_not_json(monkeypatch, capsys, tmp_path):
    from research.orchestration import cli

    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "Alice pays Bob",
                                      "--run-log-dir", str(tmp_path)])
    monkeypatch.setattr(cli, "build_model", lambda *_args: object())
    monkeypatch.setattr(cli, "config_from_environment", lambda: None)
    monkeypatch.setattr(cli, "run_session", lambda *_a, **_k: {
        "status": "BLOCKED", "stop_reason": "generation_stalled", "blocking_step": "compile",
        "blocking_diagnostics": ["root.when[0]: field không được hỗ trợ 'timeout'."],
        "model_usage": {"api_calls": 4}})
    assert cli.main() == 2
    out = capsys.readouterr().out
    assert "Chưa sinh được hợp đồng: model sinh lại hợp đồng nhưng lặp lại đúng lỗi cũ." in out
    assert "Dừng ở bước: sinh hợp đồng Marlowe." in out
    assert "root.when[0]" in out and "Số lần gọi model: 4." in out
    assert "Toàn bộ chi tiết:" in out and '"status"' not in out
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_delivered_contract_is_saved_next_to_the_log(monkeypatch, capsys, tmp_path):
    from research.orchestration import cli

    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "Alice pays Bob",
                                      "--run-log-dir", str(tmp_path)])
    monkeypatch.setattr(cli, "build_model", lambda *_args: object())
    monkeypatch.setattr(cli, "config_from_environment", lambda: None)
    monkeypatch.setattr(cli, "run_session", lambda *_a, **_k: {
        "status": "LEDGER_SIZE_CHECKED", "stop_reason": "candidate_only",
        "contract_candidate": {"payload": {"contract": "close"}}})
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "Hợp đồng (Marlowe Core JSON):" in out and "chưa được triển khai" in out
    saved = list(tmp_path.glob("*-contract.json"))
    assert len(saved) == 1 and saved[0].read_text(encoding="utf-8").strip() == '"close"'


def test_candidate_without_scenario_says_why_later_checks_did_not_run():
    from research.orchestration.cli import describe_result

    text = describe_result({"status": "CANDIDATE_ONLY", "stop_reason": "candidate_only",
                            "blocking_step": "semantic_comparison"})
    assert "chưa có tình huống kiểm thử nào" in text and "testnet" in text
    assert "thiếu cấu hình ledger" not in text


def test_safe_input_asks_again_on_broken_bytes(monkeypatch, capsys):
    from research.orchestration import cli

    # "t\udcc3i": an input method erased one byte of "ô" and left the lead byte behind.
    lines = iter(["t\udcc3i là Hưng", "tôi là Hưng"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(lines))
    assert cli.safe_input("> ") == "tôi là Hưng"
    assert "nhập lại" in capsys.readouterr().err


def test_main_rejects_broken_prompt_argument(monkeypatch):
    from research.orchestration import cli

    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "t\udcc3i", "--no-run-log"])
    monkeypatch.setattr(cli, "run_session", lambda *a, **k: pytest.fail("must not run"))
    assert cli.main() == 2
