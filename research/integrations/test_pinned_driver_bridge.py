"""Optional integration smoke against the actual pinned Haskell drivers."""

import os
import shutil
import subprocess
from copy import deepcopy

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.integrations.reference_driver import execute
from research.integrations.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT, analyze
from research.integrations.smt_gate import SMTVerificationPort
from research.architecture.cli_runner import SessionOptions, run_session
from research.stage3.test_funded_choice_v1 import _compile, funded_choice_core


def _require_toolchain():
    if os.name == "nt":
        if shutil.which("wsl") is None:
            pytest.skip("WSL is unavailable on this Windows host")
        check = subprocess.run(["wsl", "bash", "-lc", "command -v cabal && command -v z3"],
                               stdin=subprocess.DEVNULL, capture_output=True, text=True,
                               timeout=10, check=False)
        if check.returncode:
            pytest.skip("pinned Haskell toolchain is unavailable in WSL")
    elif shutil.which("cabal") is None or shutil.which("z3") is None:
        pytest.skip("pinned Haskell toolchain is unavailable")


def test_pinned_smt_driver_process():
    _require_toolchain()
    result = analyze("close")
    assert result["status"] == "Valid"
    assert result["warnings"] == []
    assert result["meta"]["upstream_commit"] == UPSTREAM_COMMIT
    assert result["meta"]["driver_version"] == DRIVER_VERSION


def test_pinned_reference_driver_process():
    _require_toolchain()
    contract = {"when": [{"case": {"notify_if": True}, "then": "close"}],
                "timeout": 100, "timeout_continuation": "close"}
    result = execute({
        "contract": contract,
        "state": {"accounts": [], "choices": [], "boundValues": [], "minTime": 0},
        "transactions": [{"interval": {"from": 0, "to": 0},
                          "inputs": [{"type": "Notify"}]}],
    })
    assert result["status"] == "Success"
    assert result["final_contract"] == "close"
    assert result["meta"]["upstream_commit"] == UPSTREAM_COMMIT


def test_pinned_smt_counterexample_maps_to_vietnamese_ast_finding():
    _require_toolchain()
    contract = {"from_account": {"role_token": "Alice"},
                "to": {"party": {"role_token": "Bob"}},
                "token": {"currency_symbol": "", "token_name": ""},
                "pay": 5, "then": "close"}
    candidate = ArtifactEnvelope(
        "contract-candidate", "v1", "integration-test",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED, AuthorityLevel.MODEL_CANDIDATE,
        {"contract": contract},
    )
    outcome = SMTVerificationPort().execute([candidate], StageContext("integration-test"))
    assert outcome.result.run_status == StageRunStatus.FAILED
    assert outcome.result.semantic_status == "SMT_COUNTEREXAMPLE"
    finding = outcome.artifacts[0].payload["structured_findings"][0]
    assert finding["path_status"] == "verified"
    assert finding["ast_path"] == "root.pay"
    assert "chỉ trả được 0" in finding["message"]


def test_accepted_intent_to_generated_candidate_runs_real_smt():
    _require_toolchain()
    core = funded_choice_core()
    compiled = _compile(core)
    candidate = next(item for item in compiled.artifacts
                     if item.artifact_type == "contract-candidate")

    class OfflineModel:
        def generate(self, system, _user):
            if "Generate one canonical Marlowe" in system:
                return {"contract": deepcopy(candidate.payload["contract"]),
                        "mapping_evidence": deepcopy(candidate.payload["mapping_evidence"])}
            return deepcopy(core)

    answers = iter(["dong y", "Tester"])
    result = run_session(core["requirement_history"][0]["messages"][0], OfflineModel(),
                         options=SessionOptions(interactive=True),
                         ask=lambda _question: next(answers))
    assert result["stages"]["compile"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["smt_verification"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["semantic_comparison"]["run_status"] == "INCONCLUSIVE", result[
        "stages"]["semantic_comparison"]["diagnostics"]
    assert not any("ast_path_missing" in item for item in result[
        "stages"]["semantic_comparison"]["diagnostics"])
    assert result["blocking_stage"] == "semantic_comparison"
