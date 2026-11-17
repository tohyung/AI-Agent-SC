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
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "Alice pays Bob",
                                          "--no-run-log"])
    monkeypatch.setattr(cli, "ModelTransport", lambda _model: object())
    monkeypatch.setattr(cli, "config_from_environment", lambda: None)

    def fake_session(prompt, _model, *, options, ask, emit):
        calls.append((prompt, options.max_iterations, options.core_schema_version, ask, emit))
        return {"status": "WAITING_USER", "stop_reason": "explicit_acceptance_required"}

    monkeypatch.setattr(cli, "run_session", fake_session)
    assert cli.main() == 2
    assert calls == [("Alice pays Bob", 8, CORE_SCHEMA_VERSION_V4, None, None)]
    assert '"stop_reason": "explicit_acceptance_required"' in capsys.readouterr().out


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
