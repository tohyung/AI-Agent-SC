"""Fail-closed Marlowe CLI transaction-size analysis, with no signing or submission."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus


@dataclass(frozen=True)
class MarloweCliSizeConfig:
    binary: Path
    socket: Path
    initialized_template: Path
    expected_binary_sha256: str
    source_commit: str
    expected_template_sha256: str
    testnet_magic: int | None = None
    timeout_seconds: float = 120.0
    node_cli_binary: Path | None = None
    minimum_sync_percent: float = 99.0

    def __post_init__(self) -> None:
        if self.testnet_magic is not None and self.testnet_magic < 0:
            raise ValueError("testnet_magic must be nonnegative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 < self.minimum_sync_percent <= 100:
            raise ValueError("minimum_sync_percent must be within (0, 100]")
        for label, digest in (("expected_binary_sha256", self.expected_binary_sha256),
                              ("expected_template_sha256", self.expected_template_sha256)):
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
        if not self.source_commit.strip():
            raise ValueError("source_commit must identify the pinned tool source")


def config_from_environment() -> MarloweCliSizeConfig | None:
    names = ("MARLOWE_LEDGER_BINARY", "MARLOWE_LEDGER_NODE_CLI",
             "MARLOWE_LEDGER_SOCKET", "MARLOWE_LEDGER_TEMPLATE",
             "MARLOWE_LEDGER_BINARY_SHA256", "MARLOWE_LEDGER_SOURCE_COMMIT",
             "MARLOWE_LEDGER_TEMPLATE_SHA256", "MARLOWE_LEDGER_TESTNET_MAGIC")
    values = {name: os.getenv(name) for name in names}
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"incomplete ledger configuration: {', '.join(missing)}")
    return MarloweCliSizeConfig(
        binary=Path(values["MARLOWE_LEDGER_BINARY"]),
        node_cli_binary=Path(values["MARLOWE_LEDGER_NODE_CLI"]),
        socket=Path(values["MARLOWE_LEDGER_SOCKET"]),
        initialized_template=Path(values["MARLOWE_LEDGER_TEMPLATE"]),
        expected_binary_sha256=values["MARLOWE_LEDGER_BINARY_SHA256"],
        source_commit=values["MARLOWE_LEDGER_SOURCE_COMMIT"],
        expected_template_sha256=values["MARLOWE_LEDGER_TEMPLATE_SHA256"],
        testnet_magic=int(values["MARLOWE_LEDGER_TESTNET_MAGIC"]),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_report(output: str) -> dict[str, Any]:
    try:
        report = json.loads(output)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("PyYAML required to parse marlowe-cli YAML output") from exc
        try:
            report = yaml.safe_load(output)
        except yaml.YAMLError as exc:
            raise ValueError("invalid marlowe-cli YAML output") from exc
    if not isinstance(report, list) or len(report) != 1 or not isinstance(report[0], dict):
        raise ValueError("unexpected marlowe-cli analysis envelope")
    section = report[0].get("Transaction size")
    if not isinstance(section, dict):
        raise ValueError("transaction-size analysis section missing")
    return section


class MarloweCliSizeAnalysisPort:
    def __init__(self, config: MarloweCliSizeConfig) -> None:
        self.config = config

    def _result(self, contract: ArtifactEnvelope, status: StageRunStatus,
                semantic: str, evidence: dict[str, Any], diagnostic: str) -> StageExecution:
        artifact = ArtifactEnvelope("ledger-size-analysis", "v1", "ledger_validation",
                                    ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                    AuthorityLevel.NO_AUTHORITY, evidence)
        result = StageResult("ledger_validation", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                             status, semantic_status=semantic,
                             input_artifacts=[contract.artifact_id],
                             diagnostics=[diagnostic],
                             limitations=["transaction-size analysis only; no signing, submission, "
                                          "full ledger validation, or production safety claim"])
        return StageExecution(result, [artifact])

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        contract = latest_artifact(artifacts, "contract-candidate")
        if contract is None:
            return StageExecution(StageResult(
                "ledger_validation", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.NOT_EVALUATED, diagnostics=["compiled contract unavailable"]))
        config = self.config
        evidence: dict[str, Any] = {
            "contract_artifact_id": contract.artifact_id,
            "contract_content_hash": contract.content_hash,
            "simulation_only": contract.payload.get("simulation_only") is True,
            "network": "mainnet" if config.testnet_magic is None else f"testnet:{config.testnet_magic}",
            "protocol_parameter_source": "local_node_socket",
            "socket_path": str(config.socket),
            "declared_tool_source_commit": config.source_commit,
            "analyzer_mode": "run analyze --transaction-size --best",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        if (not config.binary.is_file() or not config.socket.is_socket()
                or not config.initialized_template.is_file()
                or config.node_cli_binary is None or not config.node_cli_binary.is_file()):
            return self._result(contract, StageRunStatus.UNAVAILABLE,
                                "LEDGER_INFRASTRUCTURE_UNAVAILABLE", evidence,
                                "binary, node CLI, live node socket, or initialized template unavailable")
        binary_sha = _sha256(config.binary)
        evidence["tool_sha256"] = binary_sha
        template_sha = _sha256(config.initialized_template)
        evidence["template_sha256"] = template_sha
        if binary_sha != config.expected_binary_sha256:
            return self._result(contract, StageRunStatus.UNAVAILABLE,
                                "LEDGER_INFRASTRUCTURE_UNAVAILABLE", evidence,
                                "marlowe-cli binary does not match pinned SHA-256")
        if template_sha != config.expected_template_sha256:
            return self._result(contract, StageRunStatus.UNAVAILABLE,
                                "LEDGER_INFRASTRUCTURE_UNAVAILABLE", evidence,
                                "initialized template does not match pinned SHA-256")
        try:
            tip_command = [str(config.node_cli_binary), "query", "tip", "--socket-path",
                           str(config.socket)]
            tip_command.extend(["--mainnet"] if config.testnet_magic is None
                               else ["--testnet-magic", str(config.testnet_magic)])
            tip_response = subprocess.run(tip_command, capture_output=True, text=True,
                                          check=True, timeout=10)
            tip = json.loads(tip_response.stdout)
            if not isinstance(tip, dict):
                raise ValueError("node tip is not an object")
            block = tip.get("block")
            slot = tip.get("slot")
            raw_progress = tip.get("syncProgress")
            if not isinstance(raw_progress, (str, int, float)) or isinstance(raw_progress, bool):
                raise ValueError("node tip has invalid sync progress")
            progress = float(raw_progress)
            if (not isinstance(block, int) or isinstance(block, bool) or block < 1
                    or not isinstance(slot, int) or isinstance(slot, bool) or slot < 0
                    or not 0 <= progress <= 100):
                raise ValueError("node tip has invalid block, slot, or sync progress")
            evidence["node_tip"] = {"block": block, "slot": slot,
                                    "era": tip.get("era"),
                                    "sync_progress": f"{progress:.2f}"}
            if progress < config.minimum_sync_percent:
                return self._result(contract, StageRunStatus.UNAVAILABLE,
                                    "LEDGER_INFRASTRUCTURE_UNAVAILABLE", evidence,
                                    "node is not synchronized with current chain time")
            version = subprocess.run([str(config.binary), "--version"],
                                     capture_output=True, text=True, check=True,
                                     timeout=10).stdout.strip()
            evidence["tool_version"] = version
            template = json.loads(config.initialized_template.read_text(encoding="utf-8"))
            if not isinstance(template, dict) or not isinstance(template.get("tx"), dict):
                raise ValueError("invalid initialized Marlowe transaction envelope")
            transaction = template["tx"]
            if (not isinstance(transaction.get("state"), dict)
                    or transaction.get("inputs") != []
                    or transaction.get("payments") != []
                    or transaction.get("continuations") != []
                    or transaction.get("range") is not None):
                raise ValueError("initialized template contains prior transaction data")
            envelope = deepcopy(template)
            envelope["tx"]["contract"] = contract.payload["contract"]
            envelope["tx"]["state"] = {
                "accounts": [], "choices": [], "boundValues": [], "minTime": 0,
            }
            evidence["initial_state_source"] = "adapter_empty_state_v1"
            command = [str(config.binary), "run", "analyze"]
            command.extend(["--mainnet"] if config.testnet_magic is None
                           else ["--testnet-magic", str(config.testnet_magic)])
            command.extend(["--socket-path", str(config.socket), "--marlowe-file"])
            with tempfile.TemporaryDirectory(prefix="marlowe-ledger-size-") as directory:
                path = Path(directory) / "contract.json"
                path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
                command.extend([str(path), "--transaction-size", "--best"])
                response = subprocess.run(command, capture_output=True, text=True,
                                          check=False, timeout=config.timeout_seconds)
            evidence["analyzer_command_mode"] = "run analyze --transaction-size --best"
            if response.returncode != 0:
                if "TEUselessTransaction" in response.stderr:
                    return self._result(contract, StageRunStatus.INCONCLUSIVE,
                                        "REACHED_LEDGER_INCONCLUSIVE", evidence,
                                        "analyzer found no transaction to size")
                return self._result(contract, StageRunStatus.UNAVAILABLE,
                                    "LEDGER_INFRASTRUCTURE_UNAVAILABLE", evidence,
                                    "marlowe-cli analyzer or protocol query failed")
            section = _decode_report(response.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return self._result(contract, StageRunStatus.UNAVAILABLE,
                                "LEDGER_INFRASTRUCTURE_UNAVAILABLE", evidence,
                                "marlowe-cli setup, execution, or report parsing failed")
        actual, maximum, invalid = (section.get("Actual"), section.get("Maximum"),
                                    section.get("Invalid"))
        if (not isinstance(actual, int) or isinstance(actual, bool)
                or not isinstance(maximum, int) or isinstance(maximum, bool)
                or maximum <= 0 or not isinstance(invalid, bool)
                or invalid != (actual > maximum)):
            return self._result(contract, StageRunStatus.INCONCLUSIVE,
                                "REACHED_LEDGER_INCONCLUSIVE", evidence,
                                "analyzer returned an inconsistent transaction-size result")
        evidence.update({"actual_tx_bytes": actual, "maxTxSize": maximum,
                         "invalid": invalid})
        if invalid:
            return self._result(contract, StageRunStatus.FAILED, "REACHED_LEDGER_FAIL",
                                evidence, "analyzer measured transaction above maxTxSize")
        return self._result(contract, StageRunStatus.SUCCEEDED, "REACHED_LEDGER_PASS",
                            evidence, "analyzer found no maxTxSize violation in checked paths")
