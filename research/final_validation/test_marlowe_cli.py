"""Offline contract-size adapter tests; no node or wallet is contacted."""

import json
import hashlib
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.final_validation.marlowe_cli import (MarloweCliSizeAnalysisPort,
                                                   MarloweCliSizeConfig, _decode_report)


def _contract():
    return ArtifactEnvelope("contract-candidate", "core-v1", "compile",
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.DETERMINISTIC_COMPILER_CANDIDATE,
                            {"contract": "close"})


def _template():
    return {"era": "babbage", "tx": {
        "contract": "close", "state": {"accounts": [{"stale": True}],
                                       "choices": [], "boundValues": [], "minTime": 99},
        "inputs": [], "payments": [], "continuations": [], "range": None,
    }}


def test_missing_socket_is_infrastructure_unavailable_not_contract_failure(tmp_path):
    config = MarloweCliSizeConfig(tmp_path / "missing-cli", tmp_path / "missing-socket",
                                  tmp_path / "missing-template", "0" * 64,
                                  "pinned-source", "0" * 64, testnet_magic=42)
    result = MarloweCliSizeAnalysisPort(config).execute([_contract()], StageContext("test"))
    assert result.result.run_status == StageRunStatus.UNAVAILABLE
    assert result.result.semantic_status == "LEDGER_INFRASTRUCTURE_UNAVAILABLE"
    assert result.artifacts[0].payload["contract_artifact_id"] == _contract().artifact_id


@pytest.mark.parametrize(("actual", "maximum", "invalid", "semantic", "status"), [
    (100, 200, False, "REACHED_LEDGER_PASS", StageRunStatus.SUCCEEDED),
    (201, 200, True, "REACHED_LEDGER_FAIL", StageRunStatus.FAILED),
    (100, 200, True, "REACHED_LEDGER_INCONCLUSIVE", StageRunStatus.INCONCLUSIVE),
])
def test_adapter_uses_analyzer_fields_not_json_length(
    tmp_path, monkeypatch, actual, maximum, invalid, semantic, status
):
    binary = tmp_path / "cli"
    binary.write_bytes(b"pinned cli")
    socket = tmp_path / "sock"
    socket.write_bytes(b"")
    template = tmp_path / "initialized.json"
    template.write_text(json.dumps(_template()),
                        encoding="utf-8")
    monkeypatch.setattr(Path, "is_socket", lambda self: self == socket)

    def fake_run(command, **kwargs):
        if command[1:3] == ["query", "tip"]:
            return CompletedProcess(command, 0, json.dumps({
                "block": 1, "slot": 10, "era": "Babbage", "syncProgress": "100.00",
            }), "")
        if command[-1] == "--version":
            return CompletedProcess(command, 0, "marlowe-cli 0.2.0.0", "")
        assert command[-2:] == ["--transaction-size", "--best"]
        assert "--testnet-magic" in command
        submitted = json.loads(Path(command[-3]).read_text(encoding="utf-8"))["tx"]
        assert submitted["contract"] == "close"
        assert submitted["state"] == {"accounts": [], "choices": [],
                                      "boundValues": [], "minTime": 0}
        report = [{"Transaction size": {"Actual": actual, "Maximum": maximum,
                                          "Invalid": invalid}}]
        return CompletedProcess(command, 0, json.dumps(report), "")

    monkeypatch.setattr("research.final_validation.marlowe_cli.subprocess.run", fake_run)
    config = MarloweCliSizeConfig(binary, socket, template,
                                  hashlib.sha256(binary.read_bytes()).hexdigest(),
                                  "pinned-source", hashlib.sha256(template.read_bytes()).hexdigest(),
                                  testnet_magic=42, node_cli_binary=binary)
    result = MarloweCliSizeAnalysisPort(config).execute([_contract()], StageContext("test"))
    assert result.result.run_status == status
    assert result.result.semantic_status == semantic
    evidence = result.artifacts[0].payload
    if semantic != "REACHED_LEDGER_INCONCLUSIVE":
        assert evidence["actual_tx_bytes"] == actual
        assert evidence["maxTxSize"] == maximum


def test_yaml_report_parser_uses_structured_parser(monkeypatch):
    yaml = pytest.importorskip("yaml")
    assert yaml is not None
    report = _decode_report("- Transaction size:\n    Actual: 200\n    Maximum: 300\n    Invalid: false\n")
    assert report == {"Actual": 200, "Maximum": 300, "Invalid": False}


def test_binary_sha_mismatch_blocks_before_analyzer_execution(tmp_path, monkeypatch):
    binary = tmp_path / "cli"
    binary.write_bytes(b"different binary")
    socket = tmp_path / "sock"
    socket.write_bytes(b"")
    template = tmp_path / "initialized.json"
    template.write_text(json.dumps(_template()), encoding="utf-8")
    monkeypatch.setattr(Path, "is_socket", lambda self: self == socket)
    monkeypatch.setattr("research.final_validation.marlowe_cli.subprocess.run",
                        lambda *args, **kwargs: pytest.fail("analyzer must not run"))
    config = MarloweCliSizeConfig(binary, socket, template, "0" * 64,
                                  "pinned-source", hashlib.sha256(template.read_bytes()).hexdigest(),
                                  testnet_magic=42)
    result = MarloweCliSizeAnalysisPort(config).execute([_contract()], StageContext("test"))
    assert result.result.semantic_status == "LEDGER_INFRASTRUCTURE_UNAVAILABLE"
    assert result.result.run_status == StageRunStatus.UNAVAILABLE


def test_template_sha_mismatch_blocks_before_analyzer_execution(tmp_path, monkeypatch):
    binary = tmp_path / "cli"
    binary.write_bytes(b"pinned cli")
    socket = tmp_path / "sock"
    socket.write_bytes(b"")
    template = tmp_path / "initialized.json"
    template.write_text(json.dumps(_template()), encoding="utf-8")
    monkeypatch.setattr(Path, "is_socket", lambda self: self == socket)
    monkeypatch.setattr("research.final_validation.marlowe_cli.subprocess.run",
                        lambda *args, **kwargs: pytest.fail("analyzer must not run"))
    config = MarloweCliSizeConfig(binary, socket, template,
                                  hashlib.sha256(binary.read_bytes()).hexdigest(),
                                  "pinned-source", "0" * 64, testnet_magic=42)
    result = MarloweCliSizeAnalysisPort(config).execute([_contract()], StageContext("test"))
    assert result.result.run_status == StageRunStatus.UNAVAILABLE
    assert result.result.semantic_status == "LEDGER_INFRASTRUCTURE_UNAVAILABLE"


def test_useless_transaction_is_inconclusive_not_infrastructure_unavailable(tmp_path, monkeypatch):
    binary = tmp_path / "cli"
    binary.write_bytes(b"pinned cli")
    socket = tmp_path / "sock"
    socket.write_bytes(b"")
    template = tmp_path / "initialized.json"
    template.write_text(json.dumps(_template()), encoding="utf-8")
    monkeypatch.setattr(Path, "is_socket", lambda self: self == socket)

    def fake_run(command, **kwargs):
        if command[1:3] == ["query", "tip"]:
            return CompletedProcess(command, 0, json.dumps({
                "block": 1, "slot": 10, "era": "Babbage", "syncProgress": "100.00",
            }), "")
        if command[-1] == "--version":
            return CompletedProcess(command, 0, "marlowe-cli 0.2.0.0", "")
        return CompletedProcess(command, 1, "", "TEUselessTransaction")

    monkeypatch.setattr("research.final_validation.marlowe_cli.subprocess.run", fake_run)
    config = MarloweCliSizeConfig(binary, socket, template,
                                  hashlib.sha256(binary.read_bytes()).hexdigest(),
                                  "pinned-source", hashlib.sha256(template.read_bytes()).hexdigest(),
                                  testnet_magic=42, node_cli_binary=binary)
    result = MarloweCliSizeAnalysisPort(config).execute([_contract()], StageContext("test"))
    assert result.result.run_status == StageRunStatus.INCONCLUSIVE
    assert result.result.semantic_status == "REACHED_LEDGER_INCONCLUSIVE"


def test_stale_node_tip_blocks_before_analyzer(tmp_path, monkeypatch):
    binary = tmp_path / "cli"
    binary.write_bytes(b"pinned cli")
    socket = tmp_path / "sock"
    socket.write_bytes(b"")
    template = tmp_path / "initialized.json"
    template.write_text(json.dumps(_template()), encoding="utf-8")
    monkeypatch.setattr(Path, "is_socket", lambda self: self == socket)

    def fake_run(command, **kwargs):
        assert command[1:3] == ["query", "tip"]
        return CompletedProcess(command, 0, json.dumps({
            "block": 118, "slot": 2377, "era": "Babbage", "syncProgress": "14.85",
        }), "")

    monkeypatch.setattr("research.final_validation.marlowe_cli.subprocess.run", fake_run)
    config = MarloweCliSizeConfig(binary, socket, template,
                                  hashlib.sha256(binary.read_bytes()).hexdigest(),
                                  "pinned-source", hashlib.sha256(template.read_bytes()).hexdigest(),
                                  testnet_magic=42, node_cli_binary=binary)
    result = MarloweCliSizeAnalysisPort(config).execute([_contract()], StageContext("test"))
    assert result.result.run_status == StageRunStatus.UNAVAILABLE
    assert result.result.semantic_status == "LEDGER_INFRASTRUCTURE_UNAVAILABLE"
    assert result.artifacts[0].payload["node_tip"]["sync_progress"] == "14.85"
