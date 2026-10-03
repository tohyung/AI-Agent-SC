"""Opt-in integration test against a live, local Cardano node and pinned CLI."""

import json
import os
from pathlib import Path

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.final_validation.marlowe_cli import MarloweCliSizeAnalysisPort, MarloweCliSizeConfig
from research.stage3.test_funded_choice_v1 import _compile, funded_choice_core


@pytest.mark.skipif(not os.environ.get("MARLOWE_LEDGER_BINARY"),
                    reason="live ledger integration is opt-in")
def test_real_marlowe_cli_analyzes_control_contract():
    config = MarloweCliSizeConfig(
        binary=Path(os.environ["MARLOWE_LEDGER_BINARY"]),
        socket=Path(os.environ["MARLOWE_LEDGER_SOCKET"]),
        initialized_template=Path(os.environ["MARLOWE_LEDGER_TEMPLATE"]),
        expected_binary_sha256=os.environ["MARLOWE_LEDGER_BINARY_SHA256"],
        source_commit=os.environ["MARLOWE_LEDGER_SOURCE_COMMIT"],
        expected_template_sha256=os.environ["MARLOWE_LEDGER_TEMPLATE_SHA256"],
        testnet_magic=int(os.environ["MARLOWE_LEDGER_TESTNET_MAGIC"]),
        node_cli_binary=Path(os.environ["MARLOWE_LEDGER_NODE_CLI"]),
    )
    contract = json.loads(Path(os.environ["MARLOWE_LEDGER_CONTROL_CONTRACT"])
                          .read_text(encoding="utf-8"))
    candidate = ArtifactEnvelope(
        "contract-candidate", "core-v1", "compile",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED,
        AuthorityLevel.DETERMINISTIC_COMPILER_CANDIDATE,
        {"contract": contract},
    )
    execution = MarloweCliSizeAnalysisPort(config).execute([candidate], StageContext("ledger-control"))
    assert execution.result.run_status == StageRunStatus.SUCCEEDED, execution.result.diagnostics
    assert execution.result.semantic_status == "REACHED_LEDGER_PASS"
    evidence = execution.artifacts[0].payload
    assert evidence["actual_tx_bytes"] > 0
    assert evidence["maxTxSize"] >= evidence["actual_tx_bytes"]
    assert evidence["invalid"] is False
    assert evidence["contract_artifact_id"] == candidate.artifact_id


@pytest.mark.skipif(not os.environ.get("MARLOWE_LEDGER_BINARY"),
                    reason="live ledger integration is opt-in")
def test_compiler_generated_funded_choice_reaches_live_size_analyzer():
    compilation = _compile(funded_choice_core())
    assert compilation.result.run_status == StageRunStatus.SUCCEEDED
    candidate = next(item for item in compilation.artifacts
                     if item.artifact_type == "contract-candidate")
    assert candidate.payload["simulation_only"] is True
    config = MarloweCliSizeConfig(
        binary=Path(os.environ["MARLOWE_LEDGER_BINARY"]),
        socket=Path(os.environ["MARLOWE_LEDGER_SOCKET"]),
        initialized_template=Path(os.environ["MARLOWE_LEDGER_TEMPLATE"]),
        expected_binary_sha256=os.environ["MARLOWE_LEDGER_BINARY_SHA256"],
        source_commit=os.environ["MARLOWE_LEDGER_SOURCE_COMMIT"],
        expected_template_sha256=os.environ["MARLOWE_LEDGER_TEMPLATE_SHA256"],
        testnet_magic=int(os.environ["MARLOWE_LEDGER_TESTNET_MAGIC"]),
        node_cli_binary=Path(os.environ["MARLOWE_LEDGER_NODE_CLI"]),
    )
    execution = MarloweCliSizeAnalysisPort(config).execute([candidate], StageContext("ledger-control"))
    assert execution.result.run_status == StageRunStatus.SUCCEEDED, execution.result.diagnostics
    assert execution.result.semantic_status == "REACHED_LEDGER_PASS"
    evidence = execution.artifacts[0].payload
    assert evidence["simulation_only"] is True
    assert evidence["contract_artifact_id"] == candidate.artifact_id
    assert evidence["actual_tx_bytes"] <= evidence["maxTxSize"]
