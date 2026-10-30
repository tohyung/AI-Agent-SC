"""Real pinned Marlowe reference seam integration.

These tests execute the repository's Haskell marlowe-reference binary in the
same environment as Python. They do not establish compiler faithfulness,
universal safety, ledger validity, testnet behavior, or production readiness.
"""

from pathlib import Path
import os
import shutil
import subprocess
from unittest.mock import patch

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage3.comparison import BehaviorExpectation, SemanticComparisonPort
from research.stage3.reference import PinnedMarloweReference, ReferenceRequest
from research.stage4.domains import ExplicitTransactionDomain, TransactionTemplate
from research.stage4.explorer import ExplorationBounds, ExplorationPort
from research.stage4.oracles import NoWarningsOracle, OraclePort


DRIVER_ROOT = Path(__file__).resolve().parents[2] / "tools" / "marlowe_smt"
UPSTREAM_COMMIT = "7b5b1e900ec53a8eb18747992bec73470704dfcb"
DRIVER_VERSION = "0.1.0"
REFERENCE_IDENTITY = f"{UPSTREAM_COMMIT}:{DRIVER_VERSION}"
NOTIFY_CONTRACT = {
    "when": [{"case": {"notify_if": True}, "then": "close"}],
    "timeout": 100, "timeout_continuation": "close",
}
NOTIFY_TRANSACTION = {"interval": {"from": 0, "to": 0},
                      "inputs": [{"type": "Notify"}]}
EMPTY_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}


@pytest.fixture(scope="module")
def real_binary() -> str:
    if shutil.which("cabal") is None:
        pytest.skip("cabal unavailable in the Python test environment")
    if shutil.which("ghc") is None:
        pytest.skip("GHC unavailable in the Python test environment")
    resolved = subprocess.run(["cabal", "list-bin", "exe:marlowe-reference"],
                              cwd=DRIVER_ROOT, capture_output=True, text=True, check=False)
    if resolved.returncode != 0:
        pytest.fail(f"cabal list-bin failed ({resolved.returncode}): {resolved.stderr.strip()}")
    binary = resolved.stdout.strip()
    if not binary or not Path(binary).is_file():
        pytest.fail(f"cabal list-bin returned missing binary: {binary!r}")
    if not os.access(binary, os.X_OK):
        pytest.fail(f"reference binary is not executable: {binary}")
    return binary


def _request(state=EMPTY_STATE):
    return ReferenceRequest(NOTIFY_CONTRACT, state, (NOTIFY_TRANSACTION,))


def _envelope(artifact_type, stage, payload):
    return ArtifactEnvelope(artifact_type, "v1", stage,
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.NO_AUTHORITY, payload)


def test_adapter_configuration_is_unit_level_only():
    assert PinnedMarloweReference().binary is None
    for timeout in (0, -1):
        with pytest.raises(ValueError, match="positive"):
            PinnedMarloweReference(hard_timeout_seconds=timeout)
    with patch("research.integrations.reference_driver.execute", return_value={"status": "unit"}) as mocked:
        reference = PinnedMarloweReference(binary="unit-binary", hard_timeout_seconds=10.0)
        assert reference.execute(_request()) == {"status": "unit"}
        mocked.assert_called_once_with(_request().to_dict(), binary="unit-binary",
                                       hard_timeout_seconds=10.0)


def test_pinned_reference_executes_notify_trace_with_real_driver(real_binary):
    result = PinnedMarloweReference(binary=real_binary,
                                    hard_timeout_seconds=10.0).execute(_request())
    assert result["status"] == "Success"
    assert result["meta"] == {"upstream_commit": UPSTREAM_COMMIT,
                              "reference_driver_version": DRIVER_VERSION}
    assert result["steps"] and result["steps"][0]["status"] == "Success"
    assert result["steps"][0]["warnings"] == []
    assert result["final_contract"] == "close"
    assert set(result["final_state"]) == set(EMPTY_STATE)
    assert result["final_state"]["minTime"] == 0


def test_real_driver_rejects_incomplete_state(real_binary):
    result = PinnedMarloweReference(binary=real_binary,
                                    hard_timeout_seconds=10.0).execute(_request({}))
    assert result["status"] == "InvalidInput"
    assert result["detail"]["reason"]


def test_semantic_comparison_consumes_real_reference_response(real_binary):
    accepted = _envelope("accepted-intent", "integration_review",
                         {"integration_only": True})
    contract = _envelope("contract-candidate", "integration_fixture",
                         {"contract": NOTIFY_CONTRACT})
    expectation = _envelope(
        "behavior-expectation", "integration_review",
        BehaviorExpectation(accepted.artifact_id, "accepted_intent",
                            ReferenceRequest(None, EMPTY_STATE, (NOTIFY_TRANSACTION,)),
                            "Success", expected_final_contract="close",
                            reviewer_id="pinned-reference-integration-reviewer").to_dict())

    class IntegrationExpectationPolicy:
        def authorize(self, artifact):
            return (artifact.artifact_id == expectation.artifact_id
                    and artifact.payload["reviewer_id"] == "pinned-reference-integration-reviewer")

    execution = SemanticComparisonPort(
        PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10.0),
        IntegrationExpectationPolicy()).execute(
            [accepted, contract, expectation], StageContext("integration-test"))
    assert execution.result.run_status == StageRunStatus.SUCCEEDED
    assert execution.result.semantic_status == "SATISFIED"
    comparison = execution.artifacts[0].payload
    assert comparison["reference_identity"] == REFERENCE_IDENTITY
    assert comparison["reference_result"]["status"] == "Success"
    assert comparison["reference_result"]["final_contract"] == "close"


@pytest.fixture(scope="module")
def explored(real_binary):
    contract = _envelope("contract-candidate", "integration_fixture",
                         {"contract": NOTIFY_CONTRACT})
    domain = ExplicitTransactionDomain(
        "pinned-reference-integration-domain",
        [TransactionTemplate("Notify", 0, 0, ({"type": "Notify"},))])
    execution = ExplorationPort(
        domain, PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10.0),
        EMPTY_STATE, ExplorationBounds(max_depth=1, max_traces=1)).execute(
            [contract], StageContext("integration-test"))
    return execution


def test_exploration_consumes_real_reference_trace(explored):
    assert explored.result.run_status == StageRunStatus.SUCCEEDED
    graph = explored.artifacts[0].payload
    assert graph["coverage"] == "BOUNDED"
    assert len(graph["traces"]) == 1
    trace = graph["traces"][0]
    assert trace["status"] == "Success"
    assert trace["steps"][0]["meta"] == {
        "upstream_commit": UPSTREAM_COMMIT,
        "reference_driver_version": DRIVER_VERSION,
    }


def test_no_warnings_oracle_evaluates_observed_real_trace(explored):
    execution = OraclePort([NoWarningsOracle()]).execute(
        explored.artifacts, StageContext("integration-test"))
    assert execution.result.run_status == StageRunStatus.SUCCEEDED
    findings = execution.artifacts[0].payload["findings"]
    assert len(findings) == 1
    assert findings[0]["oracle_id"] == "no-transaction-warning-v1"
    assert findings[0]["verdict"] == "SATISFIED"
