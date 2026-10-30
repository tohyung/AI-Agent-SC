"""Windows-to-WSL JSON transport must preserve non-ASCII Marlowe names."""

import json
from types import SimpleNamespace

import pytest

from research.integrations import wsl_driver


class FakeWindowsPath:
    drive = "D:"

    def resolve(self):
        return self

    @property
    def parents(self):
        return [self, self, self]

    def __truediv__(self, _part):
        return self

    def as_posix(self):
        return "D:/repo/tools/marlowe_smt/run_smt.py"


def test_wsl_json_round_trip_uses_utf8_bytes(monkeypatch):
    monkeypatch.setattr(wsl_driver, "Path", lambda _path: FakeWindowsPath())
    observed = {}

    def run(command, **kwargs):
        observed.update(kwargs)
        assert command[:3] == ["wsl", "bash", "-lc"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            {"status": "Valid", "choice_name": "Bình"},
            ensure_ascii=False).encode("utf-8"))

    monkeypatch.setattr(wsl_driver.subprocess, "run", run)
    result = wsl_driver.run_wrapper("run_smt.py", {"choice_name": "Bình"}, 5)
    assert result["choice_name"] == "Bình"
    assert isinstance(observed["input"], bytes)
    assert json.loads(observed["input"].decode("utf-8"))["choice_name"] == "Bình"
    assert "text" not in observed


def test_wsl_driver_without_output_is_typed_failure_not_raw_stderr(monkeypatch):
    monkeypatch.setattr(wsl_driver, "Path", lambda _path: FakeWindowsPath())
    monkeypatch.setattr(wsl_driver.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        returncode=1, stdout=b"", stderr=b"secret provider detail"))
    with pytest.raises(RuntimeError, match="produced no JSON output") as caught:
        wsl_driver.run_wrapper("run_smt.py", "close", 5)
    assert "secret" not in str(caught.value)
