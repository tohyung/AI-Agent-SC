from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from threading import Lock
from time import sleep
from types import SimpleNamespace

import pytest

from marlowe_agent import node3_smt


def _process(status="Valid", *, warnings=None, counterexample=None, notes=None,
             stderr="", returncode=0):
    return SimpleNamespace(
        stdout=json.dumps({"status": status, "warnings": warnings or [],
                           "counterexample": counterexample, "analysis_notes": notes or []}),
        stderr=stderr, returncode=returncode,
    )


def test_backend_uses_argv_stdin_and_measured_timeouts(monkeypatch):
    captured = {}

    def run(command, **kwargs):
        captured.update(command=command, options=kwargs)
        return _process()

    monkeypatch.setattr(node3_smt.subprocess, "run", run)
    result = node3_smt.MarloweSMTBackend().analyze("close")
    assert result.status == "valid"
    assert captured["command"][:2] == [node3_smt.sys.executable, str(node3_smt.WRAPPER)]
    assert captured["command"][2:] == ["--hard-timeout", "90.0", "--solver-timeout-ms", "60000"]
    assert captured["options"]["input"] == '"close"'
    assert captured["options"]["timeout"] == 95.0
    assert captured["options"]["capture_output"] is True
    assert captured["options"]["cwd"] == node3_smt.WRAPPER.parents[2]


@pytest.mark.parametrize(("process", "expected"), [
    (SimpleNamespace(stdout="", stderr="", returncode=1), "unavailable"),
    (SimpleNamespace(stdout="not-json", stderr="", returncode=0), "unavailable"),
    (SimpleNamespace(stdout="[]", stderr="", returncode=0), "unavailable"),
    (_process("FutureStatus"), "unavailable"),
    (_process(warnings=[{"value": 1}]), "unavailable"),
    (_process(counterexample=[1]), "unavailable"),
    (SimpleNamespace(stdout='{"status":"Valid","warnings":[],"analysis_notes":"bad"}',
                     stderr="", returncode=0), "unavailable"),
    (_process(returncode=2), "unavailable"),
    (_process("InvalidInput", returncode=1), "invalid_input"),
    (_process("Timeout", returncode=124), "timeout"),
])
def test_backend_normalizes_process_and_schema_failures(monkeypatch, process, expected):
    monkeypatch.setattr(node3_smt.subprocess, "run", lambda *args, **kwargs: process)
    assert node3_smt.MarloweSMTBackend().analyze("close").status == expected


def test_backend_omits_raw_stderr(monkeypatch):
    monkeypatch.setattr(node3_smt.subprocess, "run", lambda *args, **kwargs: _process(stderr="secret"))
    result = node3_smt.MarloweSMTBackend().analyze("close")
    assert result.status == "valid"
    assert result.analysis_notes == ["SMT wrapper wrote stderr; raw stderr omitted."]
    assert "secret" not in str(result)


@pytest.mark.parametrize(("error", "status"), [
    (OSError("missing executable"), "unavailable"),
    (subprocess.TimeoutExpired("driver", 95), "timeout"),
])
def test_backend_launch_and_outer_timeout_are_inconclusive(monkeypatch, error, status):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(node3_smt.subprocess, "run", fail)
    assert node3_smt.MarloweSMTBackend().analyze("close").status == status


def test_backend_process_wide_concurrency_cap(monkeypatch):
    active = maximum = 0
    lock = Lock()

    def run(*args, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        sleep(0.03)
        with lock:
            active -= 1
        return _process()

    monkeypatch.setattr(node3_smt.subprocess, "run", run)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(node3_smt.MarloweSMTBackend().analyze, ["close"] * 6))
    assert maximum == 2
    assert all(result.status == "valid" for result in results)
