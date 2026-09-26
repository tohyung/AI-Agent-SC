"""Small Core V1 interpreter for benchmark scenarios.

The transition order follows reduceContractUntilQuiescent, applyInput and
computeTransaction in Language.Marlowe.Core.V1.Semantics. A scenario uses point
intervals; ambiguous intervals, merkleized cases and DivValue are unsupported.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


class NotEvaluable(ValueError):
    pass


def identity(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("role_token", value.get("address", value)))
    return str(value)


def token_id(value: Any) -> str:
    return str(value.get("token_name", "")) if isinstance(value, dict) else str(value)


@dataclass
class SimState:
    contract: Any
    time: int
    accounts: dict[tuple[str, str], int] = field(default_factory=dict)
    choices: dict[tuple[str, str], int] = field(default_factory=dict)
    bound_values: dict[str, int] = field(default_factory=dict)
    received: dict[str, dict[str, int]] = field(default_factory=dict)
    partial_pay: bool = False
    warnings: list[str] = field(default_factory=list)
    rejected: bool = False

    def receive(self, party: str, token: str, amount: int) -> None:
        if amount > 0:
            bucket = self.received.setdefault(party, {})
            bucket[token] = bucket.get(token, 0) + amount

    def value(self, expr: Any) -> int:
        if type(expr) is int:
            return expr
        if expr == "time_interval_start" or expr == "time_interval_end":
            return self.time
        if not isinstance(expr, dict):
            raise NotEvaluable(f"Unsupported value: {expr!r}")
        if "divide" in expr:
            raise NotEvaluable("DivValue")
        if "in_account" in expr:
            return self.accounts.get((identity(expr["in_account"]), token_id(expr["amount_of_token"])), 0)
        if "negate" in expr:
            return -self.value(expr["negate"])
        if "add" in expr:
            return self.value(expr["add"]) + self.value(expr["and"])
        if "minus" in expr:
            return self.value(expr["value"]) - self.value(expr["minus"])
        if "multiply" in expr:
            return self.value(expr["multiply"]) * self.value(expr["times"])
        if "value_of_choice" in expr:
            choice = expr["value_of_choice"]
            return self.choices.get((choice["choice_name"], identity(choice["choice_owner"])), 0)
        if "use_value" in expr:
            return self.bound_values.get(expr["use_value"], 0)
        if "if" in expr:
            return self.value(expr["then"] if self.observe(expr["if"]) else expr["else"])
        raise NotEvaluable(f"Unsupported value: {expr!r}")

    def observe(self, expr: Any) -> bool:
        if type(expr) is bool:
            return expr
        if not isinstance(expr, dict):
            raise NotEvaluable(f"Unsupported observation: {expr!r}")
        if "both" in expr:
            return self.observe(expr["both"]) and self.observe(expr["and"])
        if "either" in expr:
            return self.observe(expr["either"]) or self.observe(expr["or"])
        if "not" in expr:
            return not self.observe(expr["not"])
        if "chose_something_for" in expr:
            choice = expr["chose_something_for"]
            return (choice["choice_name"], identity(choice["choice_owner"])) in self.choices
        for key, op in (("ge_than", lambda a, b: a >= b), ("gt", lambda a, b: a > b),
                        ("lt", lambda a, b: a < b), ("le_than", lambda a, b: a <= b),
                        ("equal_to", lambda a, b: a == b)):
            if key in expr:
                return op(self.value(expr["value"]), self.value(expr[key]))
        raise NotEvaluable(f"Unsupported observation: {expr!r}")

    def reduce(self) -> None:
        for _ in range(10000):
            node = self.contract
            if node == "close":
                if not self.accounts:
                    return
                account, amount = next(iter(self.accounts.items()))
                del self.accounts[account]
                self.receive(*account, amount)
            elif not isinstance(node, dict):
                raise NotEvaluable("Unsupported contract")
            elif "pay" in node:
                requested = self.value(node["pay"])
                account = (identity(node["from_account"]), token_id(node["token"]))
                balance = self.accounts.get(account, 0)
                amount = min(max(requested, 0), balance)
                if requested <= 0 or amount < requested:
                    self.partial_pay = True
                self.accounts.pop(account, None)
                if balance > amount:
                    self.accounts[account] = balance - amount
                to = node["to"]
                if "party" in to:
                    self.receive(identity(to["party"]), account[1], amount)
                else:
                    target = (identity(to["account"]), account[1])
                    self.accounts[target] = self.accounts.get(target, 0) + amount
                self.contract = node["then"]
            elif "if" in node:
                self.contract = node["then"] if self.observe(node["if"]) else node["else"]
            elif "let" in node:
                if node["let"] in self.bound_values:
                    self.warnings.append("shadowed_let")
                self.bound_values[node["let"]] = self.value(node["be"])
                self.contract = node["then"]
            elif "assert" in node:
                if not self.observe(node["assert"]):
                    self.warnings.append("assertion_failed")
                self.contract = node["then"]
            elif "when" in node:
                if self.time >= node["timeout"]:
                    self.contract = node["timeout_continuation"]
                else:
                    return
            else:
                raise NotEvaluable("Unsupported contract")
        raise NotEvaluable("Reduction limit")

    def apply(self, step: dict[str, Any]) -> None:
        self.time = int(step["time"])
        self.reduce()
        if step["kind"] == "advance":
            return
        node = self.contract
        if not isinstance(node, dict) or "when" not in node:
            self.rejected = True
            return
        kind = step["kind"]
        if kind == "choice":
            number = step["value"]
            fallback_candidates = []
            for branch in node["when"]:
                action = branch["case"]
                if "for_choice" not in action:
                    continue
                choice = action["for_choice"]
                owner_and_bound_match = (
                    identity(choice["choice_owner"]) == step["party"]
                    and any(bound["from"] <= number <= bound["to"]
                            for bound in action["choose_between"])
                )
                if choice["choice_name"] == step["name"] and owner_and_bound_match:
                    self.choices[(choice["choice_name"], step["party"])] = number
                    self.contract = branch["then"]
                    self.reduce()
                    return
                if owner_and_bound_match:
                    fallback_candidates.append((branch, choice))

            # Only cases in the current When are considered, never another case's continuation.
            # After exact matching, a unique owner/bound match may fall back to its contract name.
            if len(fallback_candidates) == 1:
                branch, choice = fallback_candidates[0]
                actual_name = choice["choice_name"]
                self.choices[(actual_name, step["party"])] = number
                self.warnings.append(f"choice_name_fallback:{step['name']}->{actual_name}")
                self.contract = branch["then"]
                self.reduce()
                return
            self.rejected = True
            return
        for branch in node["when"]:
            action = branch["case"]
            if kind == "deposit" and "deposits" in action:
                amount = self.value(action["deposits"])
                if (identity(action["party"]) == step["party"]
                        and token_id(action["of_token"]) == step.get("token", "")
                        and amount == step["amount"] and amount > 0):
                    account = (identity(action["into_account"]), token_id(action["of_token"]))
                    self.accounts[account] = self.accounts.get(account, 0) + amount
                    self.contract = branch["then"]
                    self.reduce()
                    return
            if kind == "notify" and "notify_if" in action and self.observe(action["notify_if"]):
                self.contract = branch["then"]
                self.reduce()
                return
        self.rejected = True


def run_scenario(contract: Any, steps: list[dict[str, Any]], start_time: int) -> dict[str, Any]:
    state = SimState(deepcopy(contract), start_time)
    try:
        state.reduce()
        for step in steps:
            state.apply(step)
            if state.rejected:
                break
        return {"received": state.received, "closed": state.contract == "close" and not state.accounts,
                "input_rejected": state.rejected, "partial_pay": state.partial_pay,
                "warnings": state.warnings, "not_evaluable": False}
    except NotEvaluable as exc:
        return {"received": state.received, "closed": False, "input_rejected": False,
                "partial_pay": state.partial_pay, "warnings": state.warnings,
                "not_evaluable": True, "reason": str(exc)}


def timeouts(contract: Any) -> list[int]:
    found: set[int] = set()

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if "when" in node:
            found.add(node["timeout"])
            for branch in node["when"]:
                walk(branch["then"])
            walk(node["timeout_continuation"])
        elif "if" in node:
            walk(node["then"])
            walk(node["else"])
        elif "then" in node:
            walk(node["then"])

    walk(contract)
    return sorted(found)
