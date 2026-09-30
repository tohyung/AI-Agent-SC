from __future__ import annotations

import json
from pathlib import Path

from conftest import AMOUNT, DECISION_TIMEOUT, DEPOSIT_TIMEOUT, make_draft
from marlowe_agent import logic_graph
from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.marlowe_ast import assert_, choice_action, deposit, escrow_contract, if_, let, pay, when


def verify(contract, draft=None):
    return LogicGraphVerifier().verify(contract, draft)


def test_same_choice_in_different_whens_is_not_duplicate() -> None:
    action = choice_action("approve", "Alice", 1, 1)
    contract = when([{"case": action, "then": when([{"case": action, "then": "close"}],
                                                     DECISION_TIMEOUT)}], DEPOSIT_TIMEOUT)
    result = verify(contract)
    assert result.passed, result.errors


def test_duplicate_action_in_same_when_is_error() -> None:
    action = choice_action("approve", "Alice", 1, 1)
    contract = when([{"case": action, "then": "close"},
                     {"case": action, "then": "close"}], DEPOSIT_TIMEOUT)
    assert any("trùng hệt" in error for error in verify(contract).errors)


def test_overlapping_choice_bounds_same_id_is_error() -> None:
    contract = when([{"case": choice_action("approve", "Alice", 1, 2), "then": "close"},
                     {"case": choice_action("approve", "Alice", 2, 3), "then": "close"}], DEPOSIT_TIMEOUT)
    assert any("chồng lấn" in error for error in verify(contract).errors)


def test_partial_pay_is_error() -> None:
    assert any("vượt số dư" in error for error in verify(pay("Alice", "Bob", 10)).errors)


def test_nonpositive_pay_and_deposit_are_errors() -> None:
    assert any("Pay phải > 0" in error for error in verify(pay("Alice", "Bob", 0)).errors)
    contract = when([{"case": deposit("Alice", "Alice", 0), "then": "close"}], DEPOSIT_TIMEOUT)
    assert any("Deposit phải > 0" in error for error in verify(contract).errors)


def test_nested_timeout_not_increasing_is_warning_without_time_proof() -> None:
    contract = when([{"case": {"notify_if": True},
                     "then": when([], DEPOSIT_TIMEOUT)}], DEPOSIT_TIMEOUT)
    result = verify(contract)
    assert result.passed
    assert result.errors == []
    assert any("chưa mô hình hóa" in warning for warning in result.warnings)


def test_nested_earlier_timeout_is_not_unconditionally_unreachable() -> None:
    inner = when([{"case": {"notify_if": True}, "then": "close"}], DEPOSIT_TIMEOUT - 1_000)
    contract = when([{"case": {"notify_if": True}, "then": inner}], DEPOSIT_TIMEOUT)
    result = verify(contract)
    assert result.passed
    assert not result.errors
    assert any("chưa mô hình hóa" in warning for warning in result.warnings)


def test_empty_when_is_warning_only() -> None:
    result = verify(when([], DEPOSIT_TIMEOUT))
    assert result.passed
    assert any("When rỗng" in warning for warning in result.warnings)


def test_unbound_use_value_is_error() -> None:
    contract = {"let": "x", "be": {"use_value": "missing"}, "then": "close"}
    assert any("chưa được Let" in error for error in verify(contract).errors)


def test_close_with_residual_balance_is_warning() -> None:
    contract = when([{"case": deposit("Alice", "Alice", 10), "then": "close"}], DEPOSIT_TIMEOUT)
    result = verify(contract)
    assert result.passed
    assert any("Close còn dư" in warning for warning in result.warnings)


def test_path_cap_adds_warning(monkeypatch) -> None:
    monkeypatch.setattr(logic_graph, "MAX_PATHS", 1)
    contract = when([{"case": {"notify_if": True}, "then": "close"}], DEPOSIT_TIMEOUT)
    result = verify(contract)
    assert result.paths_explored == 1
    assert any("cắt bớt" in warning for warning in result.warnings)


def test_draft_consistency_role_mismatch() -> None:
    contract = when([{"case": deposit("Carol", "Carol", 10), "then": "close"}], DEPOSIT_TIMEOUT)
    result = verify(contract, make_draft(contract))
    assert any("Carol" in error for error in result.errors)


def test_draft_consistency_amount_and_timeouts() -> None:
    contract = when([{"case": deposit("Alice", "Alice", 10), "then": "close"}], DEPOSIT_TIMEOUT)
    result = verify(contract, make_draft(contract))
    assert any("lovelace" in warning for warning in result.warnings)
    assert any("decision_timeout" in warning for warning in result.warnings)


def test_valid_escrow_passes_with_zero_errors() -> None:
    contract = escrow_contract("Alice", "Bob", AMOUNT, DEPOSIT_TIMEOUT, DECISION_TIMEOUT)
    result = verify(contract, make_draft(contract))
    assert result.passed
    assert result.errors == []
    assert result.warnings == []
    assert result.paths_explored == 4


def test_lint_only_retains_blocking_structural_checks() -> None:
    verifier = LogicGraphVerifier()
    action = choice_action("approve", "Alice", 1, 1)
    duplicate = when([{"case": action, "then": "close"},
                      {"case": action, "then": "close"}], DEPOSIT_TIMEOUT)
    assert any("trùng hệt" in error for error in verifier.lint(duplicate).errors)
    overlap = when([{"case": choice_action("approve", "Alice", 1, 2), "then": "close"},
                    {"case": choice_action("approve", "Alice", 2, 3), "then": "close"}], DEPOSIT_TIMEOUT)
    assert any("chồng lấn" in error for error in verifier.lint(overlap).errors)
    undefined = let("x", {"use_value": "missing"}, "close")
    assert any("chưa được Let" in error for error in verifier.lint(undefined).errors)
    wrong_role = when([{"case": deposit("Carol", "Carol", 10), "then": "close"}], DEPOSIT_TIMEOUT)
    assert any("Carol" in error for error in verifier.lint(wrong_role, make_draft(wrong_role)).errors)


def test_lint_only_retains_nonblocking_warnings() -> None:
    verifier = LogicGraphVerifier()
    small = when([{"case": deposit("Alice", "Alice", 10), "then": "close"}], DEPOSIT_TIMEOUT)
    result = verifier.lint(small, make_draft(small))
    assert result.passed
    assert any("lovelace" in warning for warning in result.warnings)
    assert any("decision_timeout" in warning for warning in result.warnings)
    assert any("When rỗng" in warning for warning in verifier.lint(when([], DEPOSIT_TIMEOUT)).warnings)
    assert any("nhánh chết" in warning for warning in verifier.lint(if_(True, "close", "close")).warnings)


def test_lint_only_does_not_block_smt_semantic_checks() -> None:
    verifier = LogicGraphVerifier()
    contracts = [
        pay("Alice", "Bob", 0),
        pay("Alice", "Bob", 10),
        when([{"case": deposit("Alice", "Alice", 0), "then": "close"}], DEPOSIT_TIMEOUT),
        let("x", 1, let("x", 2, "close")),
        assert_(False, "close"),
    ]
    for contract in contracts:
        result = verifier.lint(contract)
        assert result.passed, result.errors


def test_infeasible_symbolic_if_is_lint_clean_but_old_verifier_fails() -> None:
    path = (Path(__file__).resolve().parents[2] / "tools" / "marlowe_smt" / "compare"
            / "corpus" / "hand-written" / "11-infeasible-if-partial-pay.json")
    contract = json.loads(path.read_text(encoding="utf-8"))
    verifier = LogicGraphVerifier()
    assert not verifier.verify(contract).passed
    assert verifier.lint(contract).passed
