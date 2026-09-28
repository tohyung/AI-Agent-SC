#!/usr/bin/env python3
"""Deterministic Valid-side Marlowe generators.

The older generate_contracts.py deliberately ends in Assert False and measures
the Counterexample/SAT side.  This module generates warning-free contracts for
the Valid/UNSAT side, plus the matched C1 Counterexample control.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


TIMEOUT_BASE = 1_900_000_000_000
FAMILIES = ("F1", "F2", "F3", "F4", "F5", "C1")
ROOT = Path(__file__).resolve().parents[3]
MILESTONE = ROOT / "marlowe_ai_agent" / "bench" / "audit" / "vi-milestone-L4-003-full.json"


def role(name: str) -> dict[str, str]:
    return {"role_token": name}


def token() -> dict[str, str]:
    return {"currency_symbol": "", "token_name": ""}


def choice_id(name: str) -> dict[str, Any]:
    return {"choice_name": name, "choice_owner": role("Benchmark")}


def choice_value(name: str) -> dict[str, Any]:
    return {"value_of_choice": choice_id(name)}


def choice_action(name: str, low: int = 1, high: int = 20) -> dict[str, Any]:
    return {"for_choice": choice_id(name), "choose_between": [{"from": low, "to": high}]}


def symbolic_if(choice_name: str, continuation: Any) -> Any:
    return {
        "if": {"value": choice_value(choice_name), "le_than": 20},
        "then": continuation,
        "else": "close",
    }


def when(cases: list[Any], depth: int) -> dict[str, Any]:
    return {
        "when": cases,
        "timeout": TIMEOUT_BASE + depth * 10,
        "timeout_continuation": "close",
    }


def pay(account: dict[str, str], amount: Any, continuation: Any) -> dict[str, Any]:
    return {
        "pay": amount,
        "from_account": account,
        "to": {"party": role("Receiver")},
        "token": token(),
        "then": continuation,
    }


def deposit(account: dict[str, str], amount: Any) -> dict[str, Any]:
    return {"party": role("Depositor"), "deposits": amount, "of_token": token(), "into_account": account}


def _f1(n: int, k: int, nested_if: bool) -> Any:
    continuation: Any = "close"
    for depth in reversed(range(n)):
        cases = []
        for branch in range(k):
            name = f"f1-d{depth}-b{branch}"
            tail = continuation if branch == 0 else "close"
            if nested_if:
                tail = symbolic_if(name, tail)
            cases.append({"case": choice_action(name), "then": tail})
        continuation = when(cases, depth)
    return continuation


def _f2(n: int, k: int, nested_if: bool, faulty: bool) -> Any:
    continuation: Any = "close"
    for depth in reversed(range(n)):
        cases = []
        for branch in range(k):
            account = role(f"F2-{depth}-{branch}")
            amount = 10 + branch
            tail = continuation if branch == 0 else "close"
            if nested_if:
                name = f"f2-d{depth}-b{branch}"
                tail = symbolic_if(name, tail)
                action = choice_action(name)
                paid = amount + 1 if faulty and depth == n - 1 and branch == 0 else amount
                tail = {
                    "when": [{"case": deposit(account, amount), "then": pay(account, paid, tail)}],
                    "timeout": TIMEOUT_BASE + depth * 10 + 1,
                    "timeout_continuation": "close",
                }
            else:
                action = deposit(account, amount)
                paid = amount + 1 if faulty and depth == n - 1 and branch == 0 else amount
                tail = pay(account, paid, tail)
            cases.append({"case": action, "then": tail})
        continuation = when(cases, depth)
    return continuation


def _f3_tail(depth: int, branch: int, continuation: Any, nested_if: bool) -> tuple[Any, Any]:
    suffix = f"{depth}-{branch}"
    choice_name = f"f3-choice-{suffix}"
    account = role(f"F3-{suffix}")
    chosen = choice_value(choice_name)
    names = {kind: f"f3-{kind}-{suffix}" for kind in ("add", "sub", "mul", "div", "available", "cond")}
    conditioned = {
        "if": {"value": chosen, "ge_than": 1},
        "then": {"use_value": names["div"]},
        "else": 1,
    }
    tail: Any = pay(account, {"use_value": names["cond"]}, continuation)
    if nested_if:
        tail = symbolic_if(choice_name, tail)
    tail = {
        "assert": {"value": {"use_value": names["available"]}, "ge_than": {"use_value": names["cond"]}},
        "then": tail,
    }
    bindings = (
        (names["add"], {"add": chosen, "and": 1}),
        (names["sub"], {"value": {"use_value": names["add"]}, "minus": 1}),
        (names["mul"], {"multiply": {"use_value": names["sub"]}, "times": 2}),
        (names["div"], {"divide": {"use_value": names["mul"]}, "by": 2}),
        (names["available"], {"in_account": account, "amount_of_token": token()}),
        (names["cond"], conditioned),
    )
    for name, value in reversed(bindings):
        tail = {"let": name, "be": value, "then": tail}
    deposit_when = {
        "when": [{"case": deposit(account, {"add": chosen, "and": 1}), "then": tail}],
        "timeout": TIMEOUT_BASE + depth * 10 + 1,
        "timeout_continuation": "close",
    }
    return choice_action(choice_name), deposit_when


def _f3(n: int, k: int, nested_if: bool) -> Any:
    continuation: Any = "close"
    for depth in reversed(range(n)):
        cases = []
        for branch in range(k):
            action, tail = _f3_tail(depth, branch, continuation if branch == 0 else "close", nested_if)
            cases.append({"case": action, "then": tail})
        continuation = when(cases, depth)
    return continuation


def _f4(n: int, k: int, nested_if: bool) -> Any:
    continuation: Any = "close"
    for depth in reversed(range(n)):
        cases = []
        for branch in range(k):
            name = f"f4-d{depth}-b{branch}"
            tail = continuation if branch == 0 else "close"
            tail = {"assert": {"value": choice_value(name), "ge_than": 1}, "then": tail}
            if nested_if:
                tail = symbolic_if(name, tail)
            cases.append({"case": choice_action(name), "then": tail})
        continuation = when(cases, depth)
    return continuation


def _replace_first_close(node: Any, replacement: Any) -> tuple[Any, bool]:
    if node == "close":
        return copy.deepcopy(replacement), True
    if isinstance(node, list):
        result = []
        replaced = False
        for item in node:
            if replaced:
                result.append(copy.deepcopy(item))
            else:
                converted, replaced = _replace_first_close(item, replacement)
                result.append(converted)
        return result, replaced
    if isinstance(node, dict):
        result = {}
        replaced = False
        for key, value in node.items():
            if replaced:
                result[key] = copy.deepcopy(value)
            else:
                result[key], replaced = _replace_first_close(value, replacement)
        return result, replaced
    return copy.deepcopy(node), False


def _milestone_contract() -> Any:
    record = json.loads(MILESTONE.read_text(encoding="utf-8"))
    contract = record.get("contract")
    if record.get("status") != "done" or not contract:
        raise ValueError(f"usable completed milestone contract missing: {MILESTONE}")
    return contract


def _timeouts(node: Any) -> list[int]:
    if isinstance(node, list):
        return [value for item in node for value in _timeouts(item)]
    if isinstance(node, dict):
        own = [node["timeout"]] if type(node.get("timeout")) is int else []
        return own + [value for item in node.values() for value in _timeouts(item)]
    return []


def _shift_timeouts(node: Any, offset: int) -> Any:
    if isinstance(node, list):
        return [_shift_timeouts(item, offset) for item in node]
    if isinstance(node, dict):
        return {
            key: value + offset if key == "timeout" and type(value) is int else _shift_timeouts(value, offset)
            for key, value in node.items()
        }
    return copy.deepcopy(node)


def _f5(n: int, k: int, nested_if: bool) -> Any:
    base = _milestone_contract()
    deadlines = _timeouts(base)
    if not deadlines:
        raise ValueError("milestone template has no timeout")
    first_timeout = min(deadlines)
    span = max(deadlines) - first_timeout + 1_000_000
    continuation: Any = "close"
    for depth in reversed(range(n)):
        target_start = TIMEOUT_BASE + depth * span + 1
        shifted = _shift_timeouts(base, target_start - first_timeout)
        expanded, replaced = _replace_first_close(shifted, continuation)
        if not replaced:
            raise ValueError("milestone template has no Close continuation")
        cases = []
        for branch in range(k):
            name = f"f5-d{depth}-b{branch}"
            tail = expanded if branch == 0 else copy.deepcopy(shifted)
            if nested_if:
                tail = symbolic_if(name, tail)
            cases.append({"case": choice_action(name), "then": tail})
        continuation = {
            "when": cases,
            "timeout": target_start - 1,
            "timeout_continuation": "close",
        }
    return continuation


def generate(family: str, n: int, k: int, nested_if: bool) -> Any:
    family = family.upper()
    if family not in FAMILIES:
        raise ValueError(f"unknown family {family!r}; expected one of {FAMILIES}")
    if n < 1 or k < 1:
        raise ValueError("n and k must be positive")
    if family == "F1":
        return _f1(n, k, nested_if)
    if family == "F2":
        return _f2(n, k, nested_if, False)
    if family == "F3":
        return _f3(n, k, nested_if)
    if family == "F4":
        return _f4(n, k, nested_if)
    if family == "F5":
        return _f5(n, k, nested_if)
    return _f2(n, k, nested_if, True)


def canonical_bytes(contract: Any) -> bytes:
    return json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def count_cases(node: Any) -> int:
    if isinstance(node, list):
        return sum(count_cases(item) for item in node)
    if isinstance(node, dict):
        return (len(node.get("when", [])) if isinstance(node.get("when"), list) else 0) + sum(
            count_cases(value) for value in node.values()
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=FAMILIES, required=True)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--nested-if", action="store_true")
    args = parser.parse_args()
    print(canonical_bytes(generate(args.family, args.n, args.k, args.nested_if)).decode("utf-8"))


if __name__ == "__main__":
    main()
