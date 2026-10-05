"""The supported CLI must not load the archived Node 1/2/3 implementation."""

import subprocess
import sys


def test_cli_import_does_not_load_legacy_pipeline():
    probe = (
        "import sys; from marlowe_ai_agent.marlowe_agent.cli import build_parser; "
        "build_parser(); "
        "assert not any(name.startswith('research.legacy') for name in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-c", probe], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            check=False)
    assert result.returncode == 0


def test_cli_has_no_legacy_mode():
    from marlowe_ai_agent.marlowe_agent.cli import build_parser

    names = {option for action in build_parser()._actions for option in action.option_strings}
    assert "--research-mode" not in names
    assert "--allow-unverified" not in names


def test_main_calls_only_assurance_session(monkeypatch, capsys):
    from marlowe_ai_agent.marlowe_agent import cli

    calls = []
    monkeypatch.setattr(sys, "argv", ["main.py", "--prompt", "Alice pays Bob",
                                          "--no-run-log"])
    monkeypatch.setattr(cli, "ModelTransport", lambda _model: object())
    monkeypatch.setattr(cli, "config_from_environment", lambda: None)

    def fake_session(prompt, _model, *, options, ask, emit):
        calls.append((prompt, options.max_iterations, ask, emit))
        return {"status": "WAITING_USER", "stop_reason": "explicit_acceptance_required"}

    monkeypatch.setattr(cli, "run_session", fake_session)
    assert cli.main() == 2
    assert calls == [("Alice pays Bob", 8, None, None)]
    assert '"stop_reason": "explicit_acceptance_required"' in capsys.readouterr().out
