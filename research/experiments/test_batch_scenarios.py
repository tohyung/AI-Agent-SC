"""Scenario values are sourced from simulated intent, not compiled Marlowe AST."""

import pytest
from copy import deepcopy

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.experiments.batch_scenarios import (SyntheticExpectationPolicy,
                                                 scenario_from_intent)
from research.stage2b.projector import project_intent_spec
from research.stage3.test_direct_payment_v1 import direct_payment_spec
from research.stage3.test_funded_choice_v1 import (
    _shared_scope_core, funded_choice_core, split_payout_core,
)
from research.stage3.test_funded_swap_v1 import swap_core
from research.stage3.test_linear_time_release_v1 import release_core


def _accepted(spec):
    return ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.NO_AUTHORITY,
                            {"accepted_spec": spec, "simulation_only": True})


@pytest.mark.parametrize("profile_id", ["direct-payment", "funded-choice"])
def test_synthetic_scenario_is_intent_sourced_and_no_authority(profile_id):
    spec = (direct_payment_spec() if profile_id == "direct-payment" else
            project_intent_spec(funded_choice_core()).intent_spec.to_dict())
    scenario = scenario_from_intent(_accepted(spec), profile_id)
    payload = scenario.expectation.payload
    assert SyntheticExpectationPolicy().authorize(scenario.expectation)
    assert scenario.expectation.authority_level == AuthorityLevel.NO_AUTHORITY
    assert payload["simulation_only"] is True
    assert payload["source_artifact_id"] == _accepted(spec).artifact_id
    amount = 10000000 if profile_id == "direct-payment" else 20000000
    assert payload["expected_payments"][0]["amount"] == amount
    assert len(payload["request"]["transactions"]) == (1 if profile_id == "direct-payment" else 2)


def test_funded_choice_domain_selects_declared_inputs_but_not_ast_values():
    spec = project_intent_spec(funded_choice_core()).intent_spec.to_dict()
    scenario = scenario_from_intent(_accepted(spec), "funded-choice")
    deposit = {"when": [{"case": {"deposits": 1}}]}
    choice = {"when": [{"case": {"for_choice": {"choice_name": "wrong"}}}]}
    assert scenario.domain.transactions({}, deposit)[0]["inputs"][0]["amount"] == 20000000
    assert scenario.domain.transactions({}, choice)[0]["inputs"][0]["choice_id"]["choice_name"] == "choice"
    assert scenario.domain.transactions({}, "close") == []


def test_synthetic_scenario_accepts_parent_scoped_payout_recipient():
    spec = project_intent_spec(_shared_scope_core()).intent_spec.to_dict()
    scenario = scenario_from_intent(_accepted(spec), "funded-choice")
    assert scenario.expectation.payload["expected_payments"][0]["payee"] == {
        "party": {"role_token": "Carol"}}


def test_split_payout_expectation_is_sourced_from_intent_claims():
    spec = project_intent_spec(split_payout_core()).intent_spec.to_dict()
    scenario = scenario_from_intent(_accepted(spec), "funded-choice")
    payments = scenario.expectation.payload["expected_payments"]
    assert [(item["payee"]["party"]["role_token"], item["amount"]) for item in payments] == [
        ("Carol", 3000000), ("Bob", 17000000)]


def test_scenario_rejects_unreviewed_human_authority_claim():
    spec = direct_payment_spec()
    forged = ArtifactEnvelope("accepted-intent", "v1", "test",
                              ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                              AuthorityLevel.USER_ACCEPTED_INTENT,
                              {"accepted_spec": spec, "simulation_only": True})
    with pytest.raises(ValueError, match="simulated accepted intent"):
        scenario_from_intent(forged, "direct-payment")


def test_funded_swap_scenario_is_intent_sourced_and_uses_both_assets():
    spec = project_intent_spec(swap_core()).intent_spec.to_dict()
    scenario = scenario_from_intent(_accepted(spec), "funded-swap")
    request = scenario.expectation.payload["request"]
    assert [tx["inputs"][0]["amount"] for tx in request["transactions"]] == [29000000, 13]
    assert [item["amount"] for item in scenario.expectation.payload["expected_payments"]] == [
        29000000, 13]
    assert scenario.expectation.payload["simulation_only"] is True
    contract = {"when": [{"case": {"party": {"role_token": "Lan"},
                                      "into_account": {"role_token": "Lan"},
                                      "of_token": {"currency_symbol": "11" * 28,
                                                   "token_name": "GOLD"},
                                      "deposits": 999}}]}
    selected = scenario.domain.transactions({}, contract)
    assert len(selected) == 1
    assert selected[0]["inputs"][0]["amount"] == 13


def test_funded_swap_scenario_follows_sequential_payout_continuation():
    core = deepcopy(swap_core())
    next(item for item in core["behavior_scopes"]
         if item["scope_id"] == "pay-gold")["parent_scope_id"] = "pay-ada"
    spec = project_intent_spec(core).intent_spec.to_dict()
    scenario = scenario_from_intent(_accepted(spec), "funded-swap")
    payments = scenario.expectation.payload["expected_payments"]
    assert [item["amount"] for item in payments] == [29000000, 13]


def test_linear_time_release_scenario_uses_intent_deadlines_not_ast_values():
    spec = project_intent_spec(release_core()).intent_spec.to_dict()
    scenario = scenario_from_intent(_accepted(spec), "linear-time-release")
    transactions = scenario.expectation.payload["request"]["transactions"]
    assert len(transactions) == 3
    assert transactions[0]["inputs"][0]["amount"] == 35000000
    assert [item["amount"] for item in scenario.expectation.payload["expected_payments"]] == [
        17500000, 17500000]
    first_deadline = transactions[1]["interval"]["from"]
    second_deadline = transactions[2]["interval"]["from"]
    assert first_deadline < second_deadline
    assert scenario.domain.transactions({}, {"when": [], "timeout": first_deadline}) == [
        transactions[1]]
    assert scenario.domain.transactions({}, {"when": [], "timeout": second_deadline}) == [
        transactions[2]]
    assert scenario.domain.transactions({}, {"when": [], "timeout": first_deadline + 1}) == []
