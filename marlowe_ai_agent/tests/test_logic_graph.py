from __future__ import annotations

from conftest import AMOUNT, DECISION_TIMEOUT, DEPOSIT_TIMEOUT, make_draft
from marlowe_agent import logic_graph
from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.marlowe_ast import choice_action, deposit, escrow_contract, pay, when


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
