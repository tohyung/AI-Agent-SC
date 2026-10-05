"""Source-grounded two-approval fixture; no live candidate is rewritten."""

from copy import deepcopy
from pathlib import Path
import shutil
import subprocess

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2, validate_intent_spec
from research.stage2b.projector import project_intent_spec
from research.stage3.compiler import CompilerPort
from research.stage3.comparison import SemanticComparisonPort
from research.experiments.batch_scenarios import (SyntheticExpectationPolicy,
                                                 scenario_from_intent)
from research.stage3.models import ProfileMatchStatus
from research.stage3.profile_compilers.funded_choice_v1 import FUNDED_CHOICE_PROFILE
from research.stage3.profile_compilers.sequential_approval_v1 import (
    SEQUENTIAL_APPROVAL_PROFILE, compile_sequential_approval_v1,
)
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import PinnedMarloweReference, ReferenceRequest
from research.stage4.explorer import ExplorationBounds, ExplorationPort
from research.stage4.oracles import NoWarningsOracle, OraclePort
from research.stage3.test_funded_choice_v1 import funded_choice_core


T1 = 1799280000000
T2 = 1799884800000
T3 = 1800489600000
MESSAGE = (
    "Alice deposits 32 ADA into Alice's contract account before 2027-01-07T00:00:00Z. "
    "Alice approves stage one before 2027-01-14T00:00:00Z; then pay Bob 16 ADA "
    "from Alice's account. If stage one is not approved, refund Alice 32 ADA. "
    "After stage one, Alice approves stage two before 2027-01-21T00:00:00Z; "
    "then pay Bob 16 ADA from Alice's account. If stage two is not approved, "
    "refund Alice the remaining 16 ADA."
)


def evidence(span):
    assert span in MESSAGE
    return [{"requirement_version": 1, "message_index": 0,
             "span": span, "relation": "supports"}]


def claim(claim_id, kind, value, scope_id, span, *, derived=False):
    item = {"claim_id": claim_id, "kind": kind, "value": value,
            "criticality": "financial", "status": "derived" if derived else "explicit",
            "scope_id": scope_id, "evidence": evidence(span)}
    if derived:
        item["normalization_basis"] = "source amount converted to integer lovelace"
    return item


def approval_core():
    return {
        "schema_version": CORE_SCHEMA_VERSION_V2,
        "requirement_history": [{"version": 1, "messages": [MESSAGE]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "fund", "scope_type": "transition", "transition_kind": "deposit",
             "continuation_scope_id": "first"},
            {"scope_id": "first", "scope_type": "transition", "transition_kind": "choice",
             "choice_bounds": {"from": 1, "to": 1,
                               "source_evidence": evidence("Alice approves stage one")}},
            {"scope_id": "first:approved", "scope_type": "branch", "decision_id": "first",
             "branch_id": "approved", "choice_guard": {
                 "operator": "eq", "value": 1,
                 "source_evidence": evidence("Alice approves stage one")},
             "continuation_scope_id": "first:pay"},
            {"scope_id": "first:timeout", "scope_type": "timeout", "decision_id": "first",
             "timeout_id": "first:timeout", "deadline_claim_id": "first:deadline",
             "continuation_scope_id": "first:refund"},
            {"scope_id": "first:pay", "scope_type": "terminal_outcome",
             "outcome_id": "first:pay", "parent_scope_id": "first:approved",
             "continuation_scope_id": "second"},
            {"scope_id": "first:refund", "scope_type": "terminal_outcome",
             "outcome_id": "first:refund", "parent_scope_id": "first:timeout"},
            {"scope_id": "second", "scope_type": "transition", "transition_kind": "choice",
             "choice_bounds": {"from": 1, "to": 1,
                               "source_evidence": evidence("Alice approves stage two")}},
            {"scope_id": "second:approved", "scope_type": "branch", "decision_id": "second",
             "branch_id": "approved", "choice_guard": {
                 "operator": "eq", "value": 1,
                 "source_evidence": evidence("Alice approves stage two")},
             "continuation_scope_id": "second:pay"},
            {"scope_id": "second:timeout", "scope_type": "timeout", "decision_id": "second",
             "timeout_id": "second:timeout", "deadline_claim_id": "second:deadline",
             "continuation_scope_id": "second:refund"},
            {"scope_id": "second:pay", "scope_type": "terminal_outcome",
             "outcome_id": "second:pay", "parent_scope_id": "second:approved"},
            {"scope_id": "second:refund", "scope_type": "terminal_outcome",
             "outcome_id": "second:refund", "parent_scope_id": "second:timeout"},
        ],
        "claims": [
            claim("asset", "asset", "ADA", "global", "32 ADA"),
            claim("total", "amount_lovelace", 32000000, "global", "32 ADA", derived=True),
            claim("depositor", "depositing_party", "Alice", "fund", "Alice deposits"),
            claim("account", "destination_account_owner", "Alice", "fund",
                  "Alice's contract account"),
            claim("fund:deadline", "deposit_deadline_ms", T1, "fund",
                  "2027-01-07T00:00:00Z"),
            claim("first:owner", "choice_owner", "Alice", "first",
                  "Alice approves stage one"),
            claim("first:deadline", "choice_deadline_ms", T2, "first",
                  "2027-01-14T00:00:00Z"),
            claim("first:amount", "amount_lovelace", 16000000, "first:pay",
                  "pay Bob 16 ADA", derived=True),
            claim("first:recipient", "payment_recipient", "Bob", "first:pay",
                  "pay Bob 16 ADA"),
            claim("first:source", "payment_source_account_owner", "Alice", "first:pay",
                  "from Alice's account"),
            claim("first:refund:amount", "amount_lovelace", 32000000, "first:refund",
                  "refund Alice 32 ADA", derived=True),
            claim("first:refund:recipient", "refund_recipient", "Alice", "first:refund",
                  "refund Alice 32 ADA"),
            claim("second:owner", "choice_owner", "Alice", "second",
                  "Alice approves stage two"),
            claim("second:deadline", "choice_deadline_ms", T3, "second",
                  "2027-01-21T00:00:00Z"),
            claim("second:amount", "amount_lovelace", 16000000, "second:pay",
                  "pay Bob 16 ADA", derived=True),
            claim("second:recipient", "payment_recipient", "Bob", "second:pay",
                  "pay Bob 16 ADA"),
            claim("second:source", "payment_source_account_owner", "Alice", "second:pay",
                  "from Alice's account"),
            claim("second:refund:amount", "amount_lovelace", 16000000, "second:refund",
                  "remaining 16 ADA", derived=True),
            claim("second:refund:recipient", "refund_recipient", "Alice", "second:refund",
                  "refund Alice the remaining 16 ADA"),
        ],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }


def compile_core(core):
    spec = project_intent_spec(core).intent_spec.to_dict()
    assert validate_intent_spec(spec, projected_core=core) == []
    accepted = accepted_core(spec)
    registry = ProfileRegistry([FUNDED_CHOICE_PROFILE, SEQUENTIAL_APPROVAL_PROFILE])
    port = CompilerPort(registry, {("sequential-approval", "v1"): compile_sequential_approval_v1})
    return port.execute([accepted], StageContext("test", {"allow_simulated_intent": True}))


def accepted_core(spec):
    return ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.NO_AUTHORITY,
                            {"accepted_spec": spec, "simulation_only": True})


def test_two_approval_profile_matches_without_ambiguity_and_compiles():
    result = compile_core(approval_core())
    assert result.result.run_status == StageRunStatus.SUCCEEDED, result.result.diagnostics
    artifact = next(item for item in result.artifacts if item.artifact_type == "contract-candidate")
    contract = artifact.payload["contract"]
    assert contract["when"][0]["then"]["when"][0]["then"]["pay"] == 16000000
    assert contract["when"][0]["then"]["timeout_continuation"]["pay"] == 32000000
    assert contract["when"][0]["then"]["when"][0]["then"]["then"]["timeout"] == T3
    assert artifact.payload["profile"]["profile_id"] == "sequential-approval"


def test_transition_counts_separate_one_and_two_choice_profiles():
    registry = ProfileRegistry([FUNDED_CHOICE_PROFILE, SEQUENTIAL_APPROVAL_PROFILE])
    one = project_intent_spec(funded_choice_core()).intent_spec.to_dict()
    two = project_intent_spec(approval_core()).intent_spec.to_dict()
    assert registry.match(one)[:2] == (ProfileMatchStatus.EXACT_SUPPORTED_PROFILE,
                                       FUNDED_CHOICE_PROFILE)
    assert registry.match(two)[:2] == (ProfileMatchStatus.EXACT_SUPPORTED_PROFILE,
                                       SEQUENTIAL_APPROVAL_PROFILE)


def test_nearest_profile_diagnostic_names_blocking_observation_without_accepting_it():
    core = approval_core()
    core["unscored_observations"] = [{
        "observation_id": "missing-proof", "text": "External proof not represented",
        "reason": "outside_stage2b_v2_claim_taxonomy",
        "source_evidence": evidence("Alice approves stage one"),
    }]
    spec = project_intent_spec(core).intent_spec.to_dict()
    match, profile, diagnostics = ProfileRegistry([
        FUNDED_CHOICE_PROFILE, SEQUENTIAL_APPROVAL_PROFILE]).match(spec)
    assert match == ProfileMatchStatus.UNSUPPORTED_PROFILE and profile is None
    assert diagnostics == [
        "sequential-approval: unrepresented contract behavior cannot be compiled: "
        "observation missing-proof"
    ]


def test_two_approval_profile_rejects_nonconservation_and_wrong_linkage():
    core = approval_core()
    next(item for item in core["claims"] if item["claim_id"] == "second:amount")["value"] = 15000000
    result = compile_core(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED
    assert "conserve" in " ".join(result.result.diagnostics)
    core = deepcopy(approval_core())
    next(item for item in core["behavior_scopes"]
         if item["scope_id"] == "first:pay")["continuation_scope_id"] = "first"
    result = compile_core(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED


def test_two_approval_real_reference_traces():
    if shutil.which("cabal") is None or shutil.which("ghc") is None:
        pytest.skip("real Haskell reference toolchain unavailable")
    root = Path(__file__).resolve().parents[2] / "tools/marlowe_smt"
    resolved = subprocess.run(["cabal", "list-bin", "exe:marlowe-reference"],
                              cwd=root, capture_output=True, text=True, check=True)
    binary = resolved.stdout.strip()
    if not Path(binary).is_file():
        pytest.fail("pinned reference executable missing")
    execution = compile_core(approval_core())
    contract = next(item.payload["contract"] for item in execution.artifacts
                    if item.artifact_type == "contract-candidate")
    reference = PinnedMarloweReference(binary=binary, hard_timeout_seconds=15)
    role = {"role_token": "Alice"}
    token = {"currency_symbol": "", "token_name": ""}
    state = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}

    def tx(instant, inputs=()):
        return {"interval": {"from": instant, "to": instant}, "inputs": list(inputs)}

    fund = tx(T1 - 2, [{"type": "Deposit", "party": role, "account": role,
                        "token": token, "amount": 32000000}])
    choose_first = tx(T1 - 1, [{"type": "Choice", "choice_id": {
        "choice_name": "first", "choice_owner": role}, "chosen": 1}])
    choose_second = tx(T2 - 1, [{"type": "Choice", "choice_id": {
        "choice_name": "second", "choice_owner": role}, "chosen": 1}])
    for transactions, amounts in (
        ((fund, choose_first, choose_second), [16000000, 16000000]),
        ((fund, tx(T2)), [32000000]),
        ((fund, choose_first, tx(T3)), [16000000, 16000000]),
    ):
        result = reference.execute(ReferenceRequest(contract, state, transactions))
        assert result["status"] == "Success", result
        assert result["final_contract"] == "close"
        assert [payment["amount"] for step in result["steps"]
                for payment in step["payments"]] == amounts


def test_sequential_scenario_declares_distinct_choice_inputs_from_intent():
    spec = project_intent_spec(approval_core()).intent_spec.to_dict()
    scenario = scenario_from_intent(accepted_core(spec), "sequential-approval")
    transactions = scenario.expectation.payload["request"]["transactions"]
    assert [item["inputs"][0]["type"] for item in transactions] == [
        "Deposit", "Choice", "Choice"]
    assert [item["inputs"][0]["choice_id"]["choice_name"] for item in transactions[1:]] == [
        "first", "second"]
    contract = next(item.payload["contract"] for item in compile_core(approval_core()).artifacts
                    if item.artifact_type == "contract-candidate")
    assert scenario.domain.transactions({}, contract) == [transactions[0]]
    first_wait = contract["when"][0]["then"]
    assert scenario.domain.transactions({}, first_wait) == [transactions[1]]
    second_wait = first_wait["when"][0]["then"]["then"]
    assert scenario.domain.transactions({}, second_wait) == [transactions[2]]


def test_sequential_scenario_real_comparison_exploration_and_oracle():
    if shutil.which("cabal") is None or shutil.which("ghc") is None:
        pytest.skip("real Haskell reference toolchain unavailable")
    root = Path(__file__).resolve().parents[2] / "tools/marlowe_smt"
    resolved = subprocess.run(["cabal", "list-bin", "exe:marlowe-reference"],
                              cwd=root, capture_output=True, text=True, check=True)
    reference = PinnedMarloweReference(binary=resolved.stdout.strip(),
                                      hard_timeout_seconds=15)
    spec = project_intent_spec(approval_core()).intent_spec.to_dict()
    accepted = accepted_core(spec)
    contract = next(item for item in compile_core(approval_core()).artifacts
                    if item.artifact_type == "contract-candidate")
    scenario = scenario_from_intent(accepted, "sequential-approval")
    comparison = SemanticComparisonPort(reference, SyntheticExpectationPolicy()).execute(
        [accepted, contract, scenario.expectation], StageContext("test"))
    assert comparison.result.run_status == StageRunStatus.SUCCEEDED, comparison.result.diagnostics
    assert comparison.result.semantic_status == "SATISFIED"
    exploration = ExplorationPort(scenario.domain, reference, scenario.initial_state,
                                  ExplorationBounds(max_depth=3, max_traces=8)).execute(
                                      [contract], StageContext("test"))
    assert exploration.result.run_status == StageRunStatus.SUCCEEDED
    oracle = OraclePort([NoWarningsOracle()]).execute(exploration.artifacts,
                                                      StageContext("test"))
    assert oracle.result.run_status == StageRunStatus.SUCCEEDED
    assert all(item["verdict"] == "SATISFIED"
               for item in oracle.artifacts[0].payload["findings"])
