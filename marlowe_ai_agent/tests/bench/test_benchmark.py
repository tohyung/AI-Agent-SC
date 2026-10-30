from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from bench.cases import load_cases
from bench.evaluator import _run, evaluate
from bench.marlowe_sim import run_scenario
from bench.validate_dataset import validate
from marlowe_agent.marlowe_ast import (
    case,
    choice_action,
    close,
    deposit,
    escrow_contract,
    pay,
    when,
)

CASES = load_cases()


def _case(kind: str):
    return next(item for item in CASES if item.type == kind)


def _audit(case_id: str):
    path = Path(__file__).parents[2] / "bench" / "audit" / f"{case_id}-full.json"
    return json.loads(path.read_text(encoding="utf-8"))["contract"]


def test_every_reference_scores_100_and_passes_dataset_validation():
    assert validate(CASES) == []
    assert all(evaluate(item, item.reference_contract)["strict_correct"]
               for item in CASES if item.type != "infeasible")


def test_simulator_escrow_approve_and_timeout_by_hand():
    contract = escrow_contract("buyer", "seller", 10, 100, 200)
    approved = run_scenario(contract, [{"kind": "deposit", "party": "buyer", "amount": 10,
                                        "token": "", "time": 50},
                                       {"kind": "choice", "party": "buyer", "name": "approve",
                                        "value": 1, "time": 150}], 0)
    assert approved["received"] == {"seller": {"": 10}}
    expired = run_scenario(contract, [{"kind": "deposit", "party": "buyer", "amount": 10,
                                       "token": "", "time": 50},
                                      {"kind": "advance", "time": 201}], 0)
    assert expired["received"] == {"buyer": {"": 10}}
    no_deposit = run_scenario(contract, [{"kind": "advance", "time": 101}], 0)
    assert no_deposit["received"] == {}


def test_simulator_partial_pay_rejection_refund_and_divvalue():
    partial = run_scenario(pay("a", "b", 11), [], 0)
    assert partial["partial_pay"] and partial["received"] == {}
    contract = when([case(deposit("a", "a", 7), close())], 100)
    refund = run_scenario(contract, [{"kind": "deposit", "party": "a", "amount": 7,
                                     "token": "", "time": 50}], 0)
    assert refund["received"] == {"a": {"": 7}}
    rejected = run_scenario(contract, [{"kind": "deposit", "party": "b", "amount": 7,
                                       "token": "", "time": 50}], 0)
    assert rejected["input_rejected"]
    divided = pay("a", "b", {"divide": 8, "by": 2})
    assert run_scenario(divided, [], 0)["not_evaluable"]


def test_choice_exact_match_requires_owner_and_bound_not_just_name():
    contract = when([
        case(choice_action("decision", "alice", 0, 0), close()),
        case(choice_action("decision", "bob", 1, 1), close()),
    ], 100)
    wrong_bound_and_owner = {"kind": "choice", "party": "alice", "name": "decision",
                             "value": 1, "time": 50}
    assert run_scenario(contract, [wrong_bound_and_owner], 0)["input_rejected"]
    valid = {"kind": "choice", "party": "alice", "name": "decision", "value": 0, "time": 50}
    assert not run_scenario(contract, [valid], 0)["input_rejected"]


@pytest.mark.parametrize("case_id", ["vi-rental_deposit-L3-003", "vi-milestone-L4-003"])
def test_audit_choice_name_fallback_runs_original_scenarios(case_id):
    item = next(case for case in CASES if case.id == case_id)
    contract = _audit(case_id)
    mapping = evaluate(item, contract)["mapping"]
    for scenario in item.checks["scenarios"]:
        outcome = _run(contract, scenario, mapping)
        assert not outcome["input_rejected"]
        assert outcome["closed"] == scenario["closed"]
        assert outcome["received"] == scenario["received"]


def test_choice_name_fallback_rejects_ambiguous_and_unmatched_candidates():
    ambiguous = when([
        case(choice_action("first", "alice", 1, 1), close()),
        case(choice_action("second", "alice", 1, 1), close()),
    ], 100)
    unmatched_name = {"kind": "choice", "party": "alice", "name": "expected",
                      "value": 1, "time": 50}
    assert run_scenario(ambiguous, [unmatched_name], 0)["input_rejected"]

    no_candidate = when([case(choice_action("actual", "bob", 0, 0), close())], 100)
    assert run_scenario(no_candidate, [unmatched_name], 0)["input_rejected"]


def test_choice_name_fallback_never_looks_into_a_case_continuation():
    nested = when([case(choice_action("nested", "bob", 1, 1), close())], 200)
    contract = when([case(choice_action("outer", "alice", 0, 0), nested)], 100)
    step = {"kind": "choice", "party": "bob", "name": "expected", "value": 1, "time": 50}
    assert run_scenario(contract, [step], 0)["input_rejected"]


def test_choice_exact_match_does_not_emit_fallback_warning():
    contract = when([case(choice_action("decision", "alice", 1, 1), close())], 100)
    step = {"kind": "choice", "party": "alice", "name": "decision", "value": 1,
            "time": 50}
    outcome = run_scenario(contract, [step], 0)
    assert not outcome["input_rejected"]
    assert outcome["warnings"] == []

    fallback_step = {**step, "name": "expected"}
    fallback = run_scenario(contract, [fallback_step], 0)
    assert not fallback["input_rejected"]
    assert fallback["warnings"] == ["choice_name_fallback:expected->decision"]


def test_evaluator_counts_scenarios_using_choice_name_fallback():
    rental = next(case for case in CASES if case.id == "vi-rental_deposit-L3-003")
    milestone = next(case for case in CASES if case.id == "vi-milestone-L4-003")
    assert evaluate(rental, _audit(rental.id))["diagnostics"]["choice_name_fallback_count"] == 2
    assert evaluate(milestone, _audit(milestone.id))["diagnostics"]["choice_name_fallback_count"] == 2


def test_reference_scenarios_cover_swap_vesting_loan():
    for kind in ("swap", "vesting", "loan"):
        item = _case(kind)
        assert evaluate(item, item.reference_contract)["scenario_accuracy"] == 1


def test_mutated_amount_degrades_accuracy_and_unit_error_is_labeled():
    item = _case("escrow_2party")
    doubled = deepcopy(item.reference_contract)
    doubled["when"][0]["case"]["deposits"] *= 2
    assert evaluate(item, doubled)["overall_accuracy"] < 1
    wrong_unit = deepcopy(item.reference_contract)
    wrong_unit["when"][0]["case"]["deposits"] //= 1000000
    score = evaluate(item, wrong_unit)
    assert "lovelace_unit_error" in score["diagnostics"]


def test_shifted_deadline_gap_is_not_hidden_by_24h_tolerance():
    item = _case("escrow_2party")
    shifted = deepcopy(item.reference_contract)
    shifted["when"][0]["then"]["timeout"] += 86400000
    result = evaluate(item, shifted)
    assert result["timing_accuracy"] < 1


def test_dataset_validator_detects_duplicate_banned_word_and_drift():
    repeated = CASES.copy()
    repeated[1] = replace(repeated[1], prompt=repeated[0].prompt)
    assert "duplicate_prompts" in validate(repeated)
    banned = CASES.copy()
    banned[0] = replace(banned[0], prompt=banned[0].prompt + " smart contract")
    assert any(item.startswith("banned:") for item in validate(banned))
    drift = CASES.copy()
    drift[0] = replace(drift[0], reference_contract="close")
    assert any(item.startswith("ground_truth_drift:") for item in validate(drift))
