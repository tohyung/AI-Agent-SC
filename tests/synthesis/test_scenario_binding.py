"""Abstract reviewed Choice actions bind mechanically, never by guessed names."""

from copy import deepcopy

import pytest

from research.synthesis.scenario_binding import (ScenarioBindingError,
                                              bind_choice_transactions)
from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.status import AuthorityLevel, ImplementationStatus
from research.exploration.declared_domain import DeclaredActionDomain
from research.synthesis.reference import ReferenceRequest


OWNER = {"role_token": "Lan"}
CHOICE = {"for_choice": {"choice_name": "internal-price-id", "choice_owner": OWNER},
          "choose_between": [{"from": 0, "to": 100}]}
CONTRACT = {"when": [{"case": CHOICE, "then": "close"}],
            "timeout": 100, "timeout_continuation": "close"}
DECLARED = {"interval": {"from": 10, "to": 10},
            "inputs": [{"type": "Choice", "choice_owner": OWNER, "chosen": 60}]}


def test_choice_name_binding_preserves_independent_value_and_source():
    original = deepcopy(DECLARED)
    transactions, evidence = bind_choice_transactions(CONTRACT, (DECLARED,))
    assert DECLARED == original
    assert transactions[0]["inputs"] == [{"type": "Choice",
                                           "choice_id": CHOICE["for_choice"], "chosen": 60}]
    assert evidence[0]["binding_kind"] == "unique_choice_owner_and_bound"
    assert DeclaredActionDomain("reviewed", (DECLARED,)).transactions({}, CONTRACT) == [
        transactions[0]]


def test_choice_binding_rejects_missing_or_ambiguous_match():
    with pytest.raises(ScenarioBindingError, match="uniquely"):
        bind_choice_transactions("close", (DECLARED,))
    ambiguous = deepcopy(CONTRACT)
    ambiguous["when"].append({"case": {"for_choice": {
        "choice_name": "second-name", "choice_owner": OWNER},
        "choose_between": [{"from": 0, "to": 100}]}, "then": "close"})
    with pytest.raises(ScenarioBindingError, match="uniquely"):
        bind_choice_transactions(ambiguous, (DECLARED,))
    wrong_owner = deepcopy(DECLARED)
    wrong_owner["inputs"][0]["choice_owner"] = {"role_token": "Other"}
    with pytest.raises(ScenarioBindingError, match="uniquely"):
        bind_choice_transactions(CONTRACT, (wrong_owner,))


def test_actions_with_the_same_choice_id_bind_the_same_input():
    repeated = {"when": [{"case": CHOICE, "then": {
        "when": [{"case": deepcopy(CHOICE), "then": "close"}],
        "timeout": 200, "timeout_continuation": "close"}}],
        "timeout": 100, "timeout_continuation": "close"}
    transactions, _ = bind_choice_transactions(repeated, (DECLARED,))
    assert transactions[0]["inputs"][0]["choice_id"] == CHOICE["for_choice"]


def test_binding_accepts_immutable_artifact_payload_without_mutating_it():
    artifact = ArtifactEnvelope("scenario", "v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"transactions": [DECLARED]})
    original = artifact.to_dict()["payload"]
    bound, _ = bind_choice_transactions(CONTRACT, tuple(artifact.payload["transactions"]))
    assert bound[0]["inputs"][0]["choice_id"] == CHOICE["for_choice"]
    assert artifact.to_dict()["payload"] == original


def test_path_aware_binding_resolves_sequential_choices_with_same_owner_and_value():
    first = deepcopy(CONTRACT)
    second = deepcopy(CONTRACT)
    first["when"][0]["case"]["for_choice"]["choice_name"] = "first-approval"
    second["when"][0]["case"]["for_choice"]["choice_name"] = "second-approval"
    root = {"when": [{"case": {"party": OWNER, "deposits": 1,
                                 "of_token": {"currency_symbol": "", "token_name": ""},
                                 "into_account": OWNER}, "then": first}],
            "timeout": 100, "timeout_continuation": "close"}
    first["when"][0]["then"] = second
    deposit = {"interval": {"from": 1, "to": 1}, "inputs": [{"type": "Deposit"}]}
    approval_one = {"interval": {"from": 2, "to": 2},
                    "inputs": [{"type": "Choice", "choice_owner": OWNER, "chosen": 1}]}
    approval_two = {"interval": {"from": 3, "to": 3},
                    "inputs": [{"type": "Choice", "choice_owner": OWNER, "chosen": 1}]}

    class PrefixReference:
        def execute(self, request: ReferenceRequest):
            return {"status": "Success", "final_contract": (
                first if len(request.transactions) == 1 else second)}

    bound, evidence = bind_choice_transactions(
        root, (deposit, approval_one, approval_two),
        reference=PrefixReference(), initial_state={})
    assert bound[1]["inputs"][0]["choice_id"]["choice_name"] == "first-approval"
    assert bound[2]["inputs"][0]["choice_id"]["choice_name"] == "second-approval"
    assert [item["binding_kind"] for item in evidence] == [
        "enabled_choice_owner_and_bound", "enabled_choice_owner_and_bound"]


def test_path_aware_binding_fails_closed_on_bad_prefix():
    class BadReference:
        def execute(self, _request):
            return {"status": "TransactionError"}

    with pytest.raises(ScenarioBindingError, match="reliable continuation"):
        bind_choice_transactions(
            CONTRACT, ({"interval": {"from": 1, "to": 1}, "inputs": []}, DECLARED),
            reference=BadReference(), initial_state={})


def test_scenario_party_names_bind_to_the_contract_spelling():
    # E7 conventions Q-TÊN 3: "CongTy" in a scenario is "Công ty" in the contract.
    from research.synthesis.scenario_binding import bind_party_names

    contract = {"when": [{"case": {"party": {"role_token": "Công ty"},
                                   "into_account": {"role_token": "Công ty"}}, "then": "close"}]}
    transactions = ({"inputs": [{"type": "Deposit", "party": {"role_token": "CongTy"},
                                 "account": {"role_token": "CongTy"}}]},)
    payments = ({"source_account": {"role_token": "CongTy"},
                 "payee": {"party": {"role_token": "Thu"}}},)
    named, paid, mapping = bind_party_names(contract, transactions, payments)
    assert mapping == {"CongTy": "Công ty"}
    assert named[0]["inputs"][0]["party"] == {"role_token": "Công ty"}
    assert paid[0]["source_account"] == {"role_token": "Công ty"}
    assert paid[0]["payee"] == {"party": {"role_token": "Thu"}}


def test_two_contract_roles_with_one_folded_name_are_ambiguous():
    import pytest
    from research.synthesis.scenario_binding import ScenarioBindingError, bind_party_names

    contract = {"a": {"role_token": "Minh"}, "b": {"role_token": "Mình"}}
    with pytest.raises(ScenarioBindingError):
        bind_party_names(contract, ({"inputs": [{"party": {"role_token": "minh"}}]},), None)
