"""Concrete, diagnostic-only replay of SMT counterexamples against Core V1 JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .marlowe_ast import walk_contract
from .node3_policy import Node3Finding, StructuredWarning
from .node3_renderer import render_warning_safe


class ReplayError(ValueError):
    def __init__(self, reason: str = "replay_invalid") -> None:
        super().__init__(reason)
        self.reason = reason


def _integer(value: Any) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    raise ReplayError()


def _machine(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ReplayError() from exc


def _key(value: Any) -> str:
    if not isinstance(value, dict):
        raise ReplayError()
    return _machine(value)


@dataclass
class ReplayState:
    accounts: dict[tuple[str, str], int] = field(default_factory=dict)
    choices: dict[str, int] = field(default_factory=dict)
    bound_values: dict[str, int] = field(default_factory=dict)
    min_time: int = 0


@dataclass(frozen=True)
class Interval:
    low: int
    high: int


def value_of(value: Any, state: ReplayState, interval: Interval) -> int:
    if type(value) is int:
        return value
    if value == "time_interval_start":
        return interval.low
    if value == "time_interval_end":
        return interval.high
    if not isinstance(value, dict):
        raise ReplayError()
    if set(value) == {"in_account", "amount_of_token"}:
        return state.accounts.get((_key(value["in_account"]), _key(value["amount_of_token"])), 0)
    if set(value) == {"negate"}:
        return -value_of(value["negate"], state, interval)
    for shape, left, right, operation in (
        ({"add", "and"}, "add", "and", "add"),
        ({"value", "minus"}, "value", "minus", "sub"),
        ({"multiply", "times"}, "multiply", "times", "mul"),
        ({"divide", "by"}, "divide", "by", "div"),
    ):
        if set(value) == shape:
            a = value_of(value[left], state, interval)
            b = value_of(value[right], state, interval)
            if operation == "add":
                return a + b
            if operation == "sub":
                return a - b
            if operation == "mul":
                return a * b
            if b == 0:
                return 0
            return (1 if a * b >= 0 else -1) * (abs(a) // abs(b))
    if set(value) == {"value_of_choice"}:
        return state.choices.get(_key(value["value_of_choice"]), 0)
    if set(value) == {"use_value"} and isinstance(value["use_value"], str):
        return state.bound_values.get(value["use_value"], 0)
    if set(value) == {"if", "then", "else"}:
        branch = "then" if observation_of(value["if"], state, interval) else "else"
        return value_of(value[branch], state, interval)
    raise ReplayError()


def observation_of(observation: Any, state: ReplayState, interval: Interval) -> bool:
    if type(observation) is bool:
        return observation
    if not isinstance(observation, dict):
        raise ReplayError()
    if set(observation) == {"both", "and"}:
        return (observation_of(observation["both"], state, interval)
                and observation_of(observation["and"], state, interval))
    if set(observation) == {"either", "or"}:
        return (observation_of(observation["either"], state, interval)
                or observation_of(observation["or"], state, interval))
    if set(observation) == {"not"}:
        return not observation_of(observation["not"], state, interval)
    if set(observation) == {"chose_something_for"}:
        return _key(observation["chose_something_for"]) in state.choices
    for shape, other, comparison in (
        ({"value", "ge_than"}, "ge_than", "ge"),
        ({"value", "gt"}, "gt", "gt"),
        ({"value", "lt"}, "lt", "lt"),
        ({"value", "le_than"}, "le_than", "le"),
        ({"value", "equal_to"}, "equal_to", "eq"),
    ):
        if set(observation) == shape:
            a = value_of(observation["value"], state, interval)
            b = value_of(observation[other], state, interval)
            return {"ge": a >= b, "gt": a > b, "lt": a < b,
                    "le": a <= b, "eq": a == b}[comparison]
    raise ReplayError()


def _account_key(party: Any, token: Any) -> tuple[str, str]:
    return _key(party), _key(token)


def _put_money(state: ReplayState, key: tuple[str, str], amount: int) -> None:
    if amount > 0:
        state.accounts[key] = amount
    else:
        state.accounts.pop(key, None)


def _warning(kind: str, path: str, **fields: Any) -> tuple[StructuredWarning, str]:
    return StructuredWarning(kind, fields), path


def _reduce(contract: Any, path: str, state: ReplayState, interval: Interval,
            warnings: list[tuple[StructuredWarning, str]]) -> tuple[Any, str, bool]:
    changed = False
    for _ in range(100_000):
        if contract == "close":
            if not state.accounts:
                return contract, path, changed
            state.accounts.pop(min(state.accounts))
            changed = True
            continue
        if not isinstance(contract, dict):
            raise ReplayError()
        if "pay" in contract:
            amount = value_of(contract["pay"], state, interval)
            account = contract["from_account"]
            payee = contract["to"]
            token = contract["token"]
            if amount <= 0:
                warnings.append(_warning("TransactionNonPositivePay", f"{path}.pay",
                                         account=account, payee=payee, amount=amount))
            else:
                key = _account_key(account, token)
                balance = state.accounts.get(key, 0)
                paid = min(balance, amount)
                _put_money(state, key, balance - paid)
                if paid < amount:
                    warnings.append(_warning("TransactionPartialPay", f"{path}.pay",
                                             account=account, payee=payee, paid=paid, expected=amount))
                if "account" in payee:
                    destination = _account_key(payee["account"], token)
                    _put_money(state, destination, state.accounts.get(destination, 0) + paid)
                elif "party" not in payee:
                    raise ReplayError()
            contract, path = contract["then"], f"{path}.then"
        elif "if" in contract:
            branch = "then" if observation_of(contract["if"], state, interval) else "else"
            contract, path = contract[branch], f"{path}.{branch}"
        elif "when" in contract:
            timeout = _integer(contract["timeout"])
            if interval.high < timeout:
                return contract, path, changed
            if timeout <= interval.low:
                contract, path = contract["timeout_continuation"], f"{path}.timeout_continuation"
            else:
                raise ReplayError()
        elif "let" in contract:
            identifier = contract["let"]
            new_value = value_of(contract["be"], state, interval)
            if identifier in state.bound_values:
                warnings.append(_warning("TransactionShadowing", f"{path}.let",
                                         value_id=identifier, old_value=state.bound_values[identifier],
                                         new_value=new_value))
            state.bound_values[identifier] = new_value
            contract, path = contract["then"], f"{path}.then"
        elif "assert" in contract:
            if not observation_of(contract["assert"], state, interval):
                warnings.append(_warning("TransactionAssertionFailed", f"{path}.assert"))
            contract, path = contract["then"], f"{path}.then"
        else:
            raise ReplayError()
        changed = True
    raise ReplayError()


def _apply(contract: Any, path: str, transaction_input: Any, state: ReplayState,
           interval: Interval, warnings: list[tuple[StructuredWarning, str]]) -> tuple[Any, str]:
    if not isinstance(contract, dict) or "when" not in contract or not isinstance(transaction_input, dict):
        raise ReplayError()
    if "merkleized_continuation" in transaction_input:
        raise ReplayError("unsupported_merkleized")
    kind = transaction_input.get("type")
    expected = {"Deposit": {"type", "account", "party", "token", "amount"},
                "Choice": {"type", "choice_id", "chosen"}, "Notify": {"type"}}.get(kind)
    if expected is None or set(transaction_input) != expected:
        raise ReplayError()
    for index, item in enumerate(contract["when"]):
        action = item["case"]
        matched = False
        if kind == "Deposit" and "deposits" in action:
            amount = value_of(action["deposits"], state, interval)
            matched = (_machine(transaction_input["account"]) == _machine(action["into_account"])
                       and _machine(transaction_input["party"]) == _machine(action["party"])
                       and _machine(transaction_input["token"]) == _machine(action["of_token"])
                       and type(transaction_input["amount"]) is int and transaction_input["amount"] == amount)
            if matched:
                if amount <= 0:
                    warnings.append(_warning("TransactionNonPositiveDeposit",
                                             f"{path}.when[{index}].case.deposits",
                                             party=action["party"], account=action["into_account"], amount=amount))
                else:
                    key = _account_key(action["into_account"], action["of_token"])
                    _put_money(state, key, state.accounts.get(key, 0) + amount)
        elif kind == "Choice" and "for_choice" in action:
            chosen = transaction_input["chosen"]
            matched = (type(chosen) is int
                       and _machine(transaction_input["choice_id"]) == _machine(action["for_choice"])
                       and any(bound["from"] <= chosen <= bound["to"]
                               for bound in action["choose_between"]))
            if matched:
                state.choices[_key(action["for_choice"])] = chosen
        elif kind == "Notify" and "notify_if" in action:
            matched = observation_of(action["notify_if"], state, interval)
        if matched:
            if "merkleized_then" in item or "then" not in item:
                raise ReplayError("unsupported_merkleized")
            return item["then"], f"{path}.when[{index}].then"
    raise ReplayError()


def _replay(contract: Any, counterexample: dict[str, Any]) -> list[tuple[StructuredWarning, str]]:
    if not isinstance(counterexample, dict) or set(counterexample) != {"start_time", "transactions"}:
        raise ReplayError()
    transactions = counterexample["transactions"]
    if not isinstance(transactions, list):
        raise ReplayError()
    # The live driver receives a bare contract, so its initial accounts/choices/bindings are empty.
    state = ReplayState(min_time=_integer(counterexample["start_time"]))
    current, path = contract, "root"
    warnings: list[tuple[StructuredWarning, str]] = []
    for transaction in transactions:
        if not isinstance(transaction, dict) or set(transaction) != {"interval", "inputs"}:
            raise ReplayError()
        time = transaction["interval"]
        if not isinstance(time, dict) or set(time) != {"from", "to"}:
            raise ReplayError()
        low, high = _integer(time["from"]), _integer(time["to"])
        if high < low or high < state.min_time:
            raise ReplayError()
        interval = Interval(max(low, state.min_time), high)
        state.min_time = interval.low
        inputs = transaction["inputs"]
        if not isinstance(inputs, list):
            raise ReplayError()
        changed = False
        for transaction_input in inputs:
            current, path, reduced = _reduce(current, path, state, interval, warnings)
            changed |= reduced
            current, path = _apply(current, path, transaction_input, state, interval, warnings)
            changed = True
        current, path, reduced = _reduce(current, path, state, interval, warnings)
        changed |= reduced
        if not changed:
            raise ReplayError()
    return warnings


def _candidate_count(contract: Any, warning_type: str) -> int:
    counts = {"TransactionNonPositivePay": "pay", "TransactionPartialPay": "pay",
              "TransactionShadowing": "let", "TransactionAssertionFailed": "assert"}
    if warning_type == "TransactionNonPositiveDeposit":
        return sum(1 for _, node in walk_contract(contract) if isinstance(node, dict)
                   for item in node.get("when", []) if "deposits" in item["case"])
    constructor = counts.get(warning_type)
    if constructor is None:
        return 0
    return sum(1 for _, node in walk_contract(contract) if isinstance(node, dict) and constructor in node)


def unmapped_findings(contract: Any, warnings: list[StructuredWarning],
                      reason: str) -> list[Node3Finding]:
    result = []
    for warning in warnings:
        try:
            multiple = _candidate_count(contract, warning.type) > 1
        except (KeyError, TypeError, ValueError):
            multiple = False
        result.append(Node3Finding(
            "smt", warning.type, warning.fields, render_warning_safe(warning), None,
            "ambiguous" if multiple else "unmapped",
            "multiple_structural_candidates" if multiple else reason,
        ))
    return result


def map_counterexample(contract: Any, warnings: list[StructuredWarning],
                       counterexample: dict[str, Any] | None) -> list[Node3Finding]:
    if counterexample is None:
        return unmapped_findings(contract, warnings, "counterexample_missing")
    try:
        replayed = _replay(contract, counterexample)
        if [_machine(warning.to_dict()) for warning, _ in replayed] != [
            _machine(warning.to_dict()) for warning in warnings
        ]:
            return unmapped_findings(contract, warnings, "warning_mismatch")
    except ReplayError as exc:
        return unmapped_findings(contract, warnings, exc.reason)
    return [Node3Finding("smt", warning.type, warning.fields, render_warning_safe(warning), path,
                         "verified", "counterexample_replay")
            for warning, path in replayed]
