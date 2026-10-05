"""Opt-in real Haskell reference integration for the tuning scenario adapter."""

from pathlib import Path
import shutil
import subprocess

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.experiments.batch_scenarios import (SyntheticExpectationPolicy,
                                                 scenario_from_intent)
from research.stage2b.projector import project_intent_spec
from research.stage3.comparison import SemanticComparisonPort
from research.stage3.compiler import CompilerPort
from research.stage3.profile_compilers.funded_choice_v1 import (
    FUNDED_CHOICE_PROFILE, compile_funded_choice_v1,
)
from research.stage3.profile_compilers.funded_swap_v1 import (
    FUNDED_SWAP_PROFILE, compile_funded_swap_v1,
)
from research.stage3.profile_compilers.linear_time_release_v1 import (
    LINEAR_TIME_RELEASE_PROFILE, compile_linear_time_release_v1,
)
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import PinnedMarloweReference
from research.stage3.reference import ReferenceRequest
from research.stage3.test_funded_choice_v1 import funded_choice_core, split_payout_core
from research.stage3.test_funded_swap_v1 import swap_core
from research.stage3.test_linear_time_release_v1 import release_core
from research.stage4.explorer import ExplorationBounds, ExplorationPort
from research.stage4.oracles import NoWarningsOracle, OraclePort


DRIVER_ROOT = Path(__file__).resolve().parents[2] / "tools/marlowe_smt"


@pytest.fixture(scope="module")
def real_binary():
    if shutil.which("cabal") is None or shutil.which("ghc") is None:
        pytest.skip("Cabal/GHC not available; real reference not exercised")
    result = subprocess.run(["cabal", "list-bin", "exe:marlowe-reference"],
                            cwd=DRIVER_ROOT, capture_output=True, text=True, check=True)
    binary = result.stdout.strip()
    if not Path(binary).is_file():
        pytest.fail("pinned reference binary missing")
    return binary


@pytest.mark.parametrize("core_factory", [funded_choice_core, split_payout_core])
def test_funded_choice_synthetic_intent_compiler_reference_and_oracle(real_binary,
                                                                      core_factory):
    spec = project_intent_spec(core_factory()).intent_spec.to_dict()
    accepted = ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"accepted_spec": spec, "simulation_only": True})
    compiled = CompilerPort(ProfileRegistry([FUNDED_CHOICE_PROFILE]), {
        (FUNDED_CHOICE_PROFILE.profile_id, FUNDED_CHOICE_PROFILE.version):
            compile_funded_choice_v1,
    }).execute([accepted], StageContext("integration", {"allow_simulated_intent": True}))
    assert compiled.result.run_status == StageRunStatus.SUCCEEDED
    contract = next(item for item in compiled.artifacts if item.artifact_type == "contract-candidate")
    scenario = scenario_from_intent(accepted, "funded-choice")
    reference = PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10)
    comparison = SemanticComparisonPort(reference, SyntheticExpectationPolicy()).execute(
        [accepted, contract, scenario.expectation], StageContext("integration"))
    assert comparison.result.run_status == StageRunStatus.SUCCEEDED, comparison.result.diagnostics
    assert comparison.result.semantic_status == "SATISFIED"
    assert comparison.artifacts[0].payload["reference_identity"] == (
        "7b5b1e900ec53a8eb18747992bec73470704dfcb:0.1.0")
    exploration = ExplorationPort(scenario.domain, reference, scenario.initial_state,
                                  ExplorationBounds(max_depth=2, max_traces=3)).execute(
                                      [contract], StageContext("integration"))
    assert exploration.result.run_status == StageRunStatus.SUCCEEDED
    traces = exploration.artifacts[0].payload["traces"]
    assert len(traces) == 2
    assert all(item["status"] == "Success" for item in traces)
    oracle = OraclePort([NoWarningsOracle()]).execute(exploration.artifacts,
                                                      StageContext("integration"))
    assert oracle.result.run_status == StageRunStatus.SUCCEEDED
    assert all(item["verdict"] == "SATISFIED" for item in oracle.artifacts[0].payload["findings"])


def test_funded_swap_synthetic_intent_reference_and_oracle(real_binary):
    spec = project_intent_spec(swap_core()).intent_spec.to_dict()
    accepted = ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"accepted_spec": spec, "simulation_only": True})
    compiled = CompilerPort(ProfileRegistry([FUNDED_SWAP_PROFILE]), {
        (FUNDED_SWAP_PROFILE.profile_id, FUNDED_SWAP_PROFILE.version):
            compile_funded_swap_v1,
    }).execute([accepted], StageContext("integration", {"allow_simulated_intent": True}))
    assert compiled.result.run_status == StageRunStatus.SUCCEEDED
    contract = next(item for item in compiled.artifacts if item.artifact_type == "contract-candidate")
    scenario = scenario_from_intent(accepted, "funded-swap")
    reference = PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10)
    comparison = SemanticComparisonPort(reference, SyntheticExpectationPolicy()).execute(
        [accepted, contract, scenario.expectation], StageContext("integration"))
    assert comparison.result.run_status == StageRunStatus.SUCCEEDED, comparison.result.diagnostics
    assert comparison.result.semantic_status == "SATISFIED"
    exploration = ExplorationPort(scenario.domain, reference, scenario.initial_state,
                                  ExplorationBounds(max_depth=2, max_traces=8)).execute(
                                      [contract], StageContext("integration"))
    assert exploration.result.run_status == StageRunStatus.SUCCEEDED
    oracle = OraclePort([NoWarningsOracle()]).execute(exploration.artifacts,
                                                      StageContext("integration"))
    assert oracle.result.run_status == StageRunStatus.SUCCEEDED
    assert all(item["verdict"] == "SATISFIED" for item in oracle.artifacts[0].payload["findings"])


def test_linear_time_release_intent_reference_and_oracle(real_binary):
    spec = project_intent_spec(release_core()).intent_spec.to_dict()
    accepted = ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"accepted_spec": spec, "simulation_only": True})
    compiled = CompilerPort(ProfileRegistry([LINEAR_TIME_RELEASE_PROFILE]), {
        (LINEAR_TIME_RELEASE_PROFILE.profile_id, LINEAR_TIME_RELEASE_PROFILE.version):
            compile_linear_time_release_v1,
    }).execute([accepted], StageContext("integration", {"allow_simulated_intent": True}))
    assert compiled.result.run_status == StageRunStatus.SUCCEEDED
    contract = next(item for item in compiled.artifacts if item.artifact_type == "contract-candidate")
    scenario = scenario_from_intent(accepted, "linear-time-release")
    reference = PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10)
    comparison = SemanticComparisonPort(reference, SyntheticExpectationPolicy()).execute(
        [accepted, contract, scenario.expectation], StageContext("integration"))
    assert comparison.result.run_status == StageRunStatus.SUCCEEDED, comparison.result.diagnostics
    assert comparison.result.semantic_status == "SATISFIED"
    exploration = ExplorationPort(scenario.domain, reference, scenario.initial_state,
                                  ExplorationBounds(max_depth=3, max_traces=8)).execute(
                                      [contract], StageContext("integration"))
    assert exploration.result.run_status == StageRunStatus.SUCCEEDED
    oracle = OraclePort([NoWarningsOracle()]).execute(exploration.artifacts,
                                                      StageContext("integration"))
    assert oracle.result.run_status == StageRunStatus.SUCCEEDED
    assert all(item["verdict"] == "SATISFIED" for item in oracle.artifacts[0].payload["findings"])


def test_funded_swap_timeout_paths_use_real_reference(real_binary):
    spec = project_intent_spec(swap_core()).intent_spec.to_dict()
    accepted = ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"accepted_spec": spec, "simulation_only": True})
    compiled = CompilerPort(ProfileRegistry([FUNDED_SWAP_PROFILE]), {
        (FUNDED_SWAP_PROFILE.profile_id, FUNDED_SWAP_PROFILE.version):
            compile_funded_swap_v1,
    }).execute([accepted], StageContext("integration", {"allow_simulated_intent": True}))
    contract = next(item.payload["contract"] for item in compiled.artifacts
                    if item.artifact_type == "contract-candidate")
    scenario = scenario_from_intent(accepted, "funded-swap")
    reference = PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10)
    first_deadline = contract["timeout"]
    second_deadline = contract["when"][0]["then"]["timeout"]
    first_expired = reference.execute(ReferenceRequest(contract, scenario.initial_state,
        ({"interval": {"from": first_deadline, "to": first_deadline}, "inputs": []},)))
    assert first_expired["status"] == "Success"
    assert first_expired["final_contract"] == "close"
    assert first_expired["steps"][0]["payments"] == []
    second_expired = reference.execute(ReferenceRequest(contract, scenario.initial_state,
        (scenario.expectation.payload["request"]["transactions"][0],
         {"interval": {"from": second_deadline, "to": second_deadline}, "inputs": []})))
    assert second_expired["status"] == "Success"
    assert second_expired["final_contract"] == "close"
    assert second_expired["steps"][1]["payments"] == [{
        "source_account": {"role_token": "Giang"},
        "payee": {"party": {"role_token": "Giang"}},
        "token": {"currency_symbol": "", "token_name": ""},
        "amount": 29000000,
    }]
