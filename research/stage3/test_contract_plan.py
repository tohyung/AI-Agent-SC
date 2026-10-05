"""Offline checks for deterministic, source-linked Core V1 construction."""

import pytest

from marlowe_ai_agent.marlowe_agent.marlowe_validator import validate_contract
from research.stage3.contract_plan import (Case, Choice, ChoiceGuard, ClaimValue,
                                           Close, Deposit, IfChoice, Pay,
                                           PlanError, When, lower_contract_plan)


T1 = 1799000000000
T2 = T1 + 600000


def claim(value, source):
    return ClaimValue(value, source)


def pay(scope, recipient, amount, then=None, asset="ADA"):
    return Pay(scope, claim("Alice", "account"), claim(recipient, scope + ":recipient"),
               claim(asset, scope + ":asset"), claim(amount, scope + ":amount"),
               then or Close(scope + ":close"))


def funded_choice():
    decision = IfChoice(
        "decision", ChoiceGuard("vote", claim("Bob", "chooser"), "ge", 1),
        pay("release", "Bob", 7), pay("refund", "Alice", 7))
    return When("deposit-wait", (
        Case(Deposit("deposit", claim("Alice", "depositor"), claim("Alice", "account"),
                     claim("ADA", "asset"), claim(7, "funding")),
             When("choice-wait", (
                 Case(Choice("vote", claim("Bob", "chooser"), 0, 1), decision),
             ), claim(T2, "choice-deadline"), pay("choice-timeout", "Alice", 7))),
    ), claim(T1, "deposit-deadline"), Close("deposit-timeout"))


def test_funded_choice_lowers_to_canonical_ast_with_source_paths():
    lowered = lower_contract_plan(funded_choice())
    assert validate_contract(lowered.contract) == []
    assert lowered.contract["when"][0]["then"]["when"][0]["then"]["if"] == {
        "value": {"value_of_choice": {"choice_name": "vote",
                                       "choice_owner": {"role_token": "Bob"}}},
        "ge_than": 1,
    }
    assert {item["source_id"] for item in lowered.mapping_evidence
            if item["source_kind"] == "claim"} >= {
                "funding", "depositor", "account", "asset", "choice-deadline",
                "chooser", "release:amount", "refund:recipient"}


def test_choice_guard_must_have_matching_owner_and_preceding_choice_on_same_path():
    bare = IfChoice("decision", ChoiceGuard("vote", claim("Bob", "chooser"), "ge", 1),
                    Close("yes"), Close("no"))
    with pytest.raises(PlanError, match="absent from this path"):
        lower_contract_plan(bare)
    wrong_owner = When("w", (
        Case(Choice("vote", claim("Alice", "owner"), 0, 1), bare),
    ), claim(T1, "deadline"), Close("timeout"))
    with pytest.raises(PlanError, match="absent from this path"):
        lower_contract_plan(wrong_owner)
    wrong_branch = When("w", (
        Case(Choice("vote", claim("Bob", "chooser"), 0, 1), Close("chosen")),
    ), claim(T1, "deadline"), bare)
    with pytest.raises(PlanError, match="absent from this path"):
        lower_contract_plan(wrong_branch)


@pytest.mark.parametrize("root, message", [
    (pay("p", "Bob", 0), "positive"),
    (pay("p", "Bob", 1, asset="GOLD"), "canonical native"),
    (When("w", (Case(Choice("vote", claim("Bob", "owner"), 2, 1), Close("c")),),
          claim(T1, "deadline"), Close("timeout")), "ordered integers"),
    (When("w", (), claim(10, "deadline"), Close("timeout")), "structurally invalid"),
])
def test_invalid_plan_fails_closed(root, message):
    with pytest.raises(PlanError, match=message):
        lower_contract_plan(root)


def test_native_asset_uses_canonical_identifier_and_preserves_source():
    token = "native:" + "ab" * 28 + "/474f4c44"
    root = pay("release", "Bob", 13, asset=token)
    lowered = lower_contract_plan(root)
    assert lowered.contract["token"] == {"currency_symbol": "ab" * 28,
                                          "token_name": "GOLD"}
    assert any(item["source_id"] == "release:asset" and item["ast_path"] == "$.token"
               for item in lowered.mapping_evidence)


def test_cycle_is_rejected_before_ast_validation():
    node = Pay("p", claim("Alice", "account"), claim("Bob", "recipient"),
               claim("ADA", "asset"), claim(1, "amount"), Close("c"))
    object.__setattr__(node, "then", node)
    with pytest.raises(PlanError, match="cycle"):
        lower_contract_plan(node)
