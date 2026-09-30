from __future__ import annotations

import pytest

from marlowe_agent.marlowe_ast import ada, case, choice_action, deposit, pay, role, when
from marlowe_agent.node3_mapper import Interval, ReplayState, map_counterexample, value_of
from marlowe_agent.node3_policy import StructuredWarning


TIMEOUT = 1_893_456_000_000


def trace(*transactions, start_time="0"):
    return {"start_time": start_time, "transactions": list(transactions)}


def tx(*inputs, low="0", high="0"):
    return {"interval": {"from": low, "to": high}, "inputs": list(inputs)}


def deposit_input(amount, account="Alice", party="Alice"):
    return {"type": "Deposit", "account": role(account), "party": role(party),
            "token": ada(), "amount": amount}


def warning(kind, **fields):
    return StructuredWarning(kind, fields)


def partial(amount, paid, account="Alice", payee="Bob"):
    return warning("TransactionPartialPay", account=role(account),
                   payee={"party": role(payee)}, paid=paid, expected=amount)


def mapped(contract, warnings, counterexample):
    return map_counterexample(contract, warnings, counterexample)


def test_nonpositive_pay_exact_path() -> None:
    contract = pay("Alice", "Bob", 0)
    found = mapped(contract, [warning("TransactionNonPositivePay", account=role("Alice"),
                                      payee={"party": role("Bob")}, amount=0)], trace(tx()))
    assert [(item.ast_path, item.path_status) for item in found] == [("root.pay", "verified")]


def test_partial_pay_exact_path() -> None:
    contract = when([case(deposit("Alice", "Alice", 5), pay("Alice", "Bob", 6))], TIMEOUT)
    found = mapped(contract, [partial(6, 5)], trace(tx(deposit_input(5))))
    assert found[0].ast_path == "root.when[0].then.pay"
    assert found[0].path_status == "verified"


def test_account_payee_updates_balance() -> None:
    contract = when([case(deposit("Alice", "Alice", 5), {
        "pay": 3, "from_account": role("Alice"), "to": {"account": role("Bob")},
        "token": ada(), "then": pay("Bob", "Alice", 4),
    })], TIMEOUT)
    found = mapped(contract, [partial(4, 3, "Bob", "Alice")], trace(tx(deposit_input(5))))
    assert found[0].ast_path == "root.when[0].then.then.pay"
    assert found[0].path_status == "verified"


def test_self_account_transfer_preserves_balance() -> None:
    contract = when([case(deposit("Alice", "Alice", 5), {
        "pay": 3, "from_account": role("Alice"), "to": {"account": role("Alice")},
        "token": ada(), "then": pay("Alice", "Bob", 6),
    })], TIMEOUT)
    found = mapped(contract, [partial(6, 5)], trace(tx(deposit_input(5))))
    assert found[0].ast_path == "root.when[0].then.then.pay"
    assert found[0].path_status == "verified"


def test_second_let_shadowing_path() -> None:
    contract = {"let": "x", "be": 1, "then": {"let": "x", "be": 2, "then": "close"}}
    found = mapped(contract, [warning("TransactionShadowing", value_id="x",
                                      old_value=1, new_value=2)], trace(tx()))
    assert found[0].ast_path == "root.then.let"
    assert found[0].path_status == "verified"


def test_false_assert_path() -> None:
    contract = {"assert": False, "then": "close"}
    found = mapped(contract, [warning("TransactionAssertionFailed")], trace(tx()))
    assert found[0].ast_path == "root.assert"
    assert found[0].path_status == "verified"


def test_nonpositive_deposit_exact_case_path() -> None:
    contract = when([case(deposit("Alice", "Alice", 0), "close")], TIMEOUT)
    found = mapped(contract, [warning("TransactionNonPositiveDeposit", party=role("Alice"),
                                      account=role("Alice"), amount=0)],
                   trace(tx(deposit_input(0))))
    assert found[0].ast_path == "root.when[0].case.deposits"
    assert found[0].path_status == "verified"


def test_first_matching_case_wins() -> None:
    action = deposit("Alice", "Alice", 1)
    contract = when([case(action, pay("Alice", "Bob", 2)),
                     case(action, pay("Alice", "Bob", 3))], TIMEOUT)
    found = mapped(contract, [partial(2, 1)], trace(tx(deposit_input(1))))
    assert found[0].ast_path == "root.when[0].then.pay"
    assert found[0].path_status == "verified"


def test_choice_updates_symbolic_pay() -> None:
    choice = choice_action("amount", "Alice", 6, 10)
    contract = when([case(deposit("Alice", "Alice", 5), when([
        case(choice, {"pay": {"value_of_choice": choice["for_choice"]},
                      "from_account": role("Alice"), "to": {"party": role("Bob")},
                      "token": ada(), "then": "close"}),
    ], TIMEOUT))], TIMEOUT)
    choice_input = {"type": "Choice", "choice_id": choice["for_choice"], "chosen": 6}
    found = mapped(contract, [partial(6, 5)],
                   trace(tx(deposit_input(5)), tx(choice_input)))
    assert found[0].ast_path == "root.when[0].then.when[0].then.pay"
    assert found[0].path_status == "verified"


def test_timeout_continuation_path() -> None:
    contract = when([], TIMEOUT, pay("Alice", "Bob", 0))
    found = mapped(contract, [warning("TransactionNonPositivePay", account=role("Alice"),
                                      payee={"party": role("Bob")}, amount=0)],
                   trace(tx(low=str(TIMEOUT), high=str(TIMEOUT))))
    assert found[0].ast_path == "root.timeout_continuation.pay"
    assert found[0].path_status == "verified"


@pytest.mark.parametrize(("observation", "branch"), [(True, "then"), (False, "else")])
def test_if_uses_concrete_observation(observation, branch) -> None:
    contract = {"if": observation, "then": pay("Alice", "Bob", 0),
                "else": {"assert": False, "then": "close"}}
    expected = ([warning("TransactionNonPositivePay", account=role("Alice"),
                         payee={"party": role("Bob")}, amount=0)] if observation
                else [warning("TransactionAssertionFailed")])
    found = mapped(contract, expected, trace(tx()))
    assert found[0].ast_path == f"root.{branch}.{'pay' if observation else 'assert'}"
    assert found[0].path_status == "verified"


@pytest.mark.parametrize(("numerator", "denominator", "expected"), [
    (-5, 2, -2), (5, -2, -2), (-5, -2, 2), (5, 0, 0),
])
def test_divvalue_uses_haskell_quot(numerator, denominator, expected) -> None:
    assert value_of({"divide": numerator, "by": denominator}, ReplayState(), Interval(0, 0)) == expected


def test_trimmed_interval_start_and_high_end() -> None:
    start_contract = pay("Alice", "Bob", "time_interval_start")
    end_contract = pay("Alice", "Bob", "time_interval_end")
    counterexample = trace(tx(low="1", high="7"), start_time="5")
    assert mapped(start_contract, [partial(5, 0)], counterexample)[0].path_status == "verified"
    assert mapped(end_contract, [partial(7, 0)], counterexample)[0].path_status == "verified"


def test_undefined_values_and_missing_account_evaluate_to_zero() -> None:
    state, interval = ReplayState(), Interval(0, 0)
    assert value_of({"use_value": "missing"}, state, interval) == 0
    assert value_of({"value_of_choice": {"choice_name": "x", "choice_owner": role("Alice")}},
                    state, interval) == 0
    assert value_of({"in_account": role("Alice"), "amount_of_token": ada()}, state, interval) == 0


def test_warning_mismatch_revokes_all_verified_paths() -> None:
    contract = {"pay": 0, "from_account": role("Alice"), "to": {"party": role("Bob")},
                "token": ada(), "then": {"assert": False, "then": "close"}}
    warnings = [warning("TransactionNonPositivePay", account=role("Alice"),
                        payee={"party": role("Bob")}, amount=0),
                warning("TransactionAssertionFailed", wrong_field=1)]
    found = mapped(contract, warnings, trace(tx()))
    assert len(found) == 2
    assert all(item.ast_path is None and item.path_status != "verified" for item in found)
    assert all(item.mapping_reason == "warning_mismatch" for item in found)


@pytest.mark.parametrize(("contract", "expected_status"), [
    (pay("Alice", "Bob", 6), "unmapped"),
    ({"if": True, "then": pay("Alice", "Bob", 6), "else": pay("Alice", "Bob", 6)}, "ambiguous"),
])
def test_invalid_replay_never_fabricates_path(contract, expected_status) -> None:
    found = mapped(contract, [partial(6, 0)], {"start_time": "broken", "transactions": []})
    assert found[0].ast_path is None
    assert found[0].path_status == expected_status


def test_unknown_warning_is_unmapped() -> None:
    found = mapped(pay("Alice", "Bob", 0), [warning("FutureWarning")], trace(tx()))
    assert found[0].path_status == "unmapped"
    assert found[0].ast_path is None
    assert found[0].message == "SMT phát hiện FutureWarning."


def test_merkleized_input_is_never_verified() -> None:
    contract = when([case(deposit("Alice", "Alice", 0), "close")], TIMEOUT)
    item = {**deposit_input(0), "merkleized_continuation": "hash"}
    found = mapped(contract, [warning("TransactionNonPositiveDeposit", party=role("Alice"),
                                      account=role("Alice"), amount=0)], trace(tx(item)))
    assert found[0].ast_path is None
    assert found[0].mapping_reason == "unsupported_merkleized"


def test_useless_followup_transaction_revokes_prior_verified_path() -> None:
    contract = pay("Alice", "Bob", 0)
    found = mapped(contract, [warning("TransactionNonPositivePay", account=role("Alice"),
                                      payee={"party": role("Bob")}, amount=0)],
                   trace(tx(), tx()))
    assert found[0].ast_path is None
    assert found[0].path_status == "unmapped"
