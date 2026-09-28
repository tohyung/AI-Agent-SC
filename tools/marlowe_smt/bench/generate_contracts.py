#!/usr/bin/env python3
"""Generate linear-depth Marlowe contracts for SMT stress measurements."""

from __future__ import annotations

import argparse
import json
from typing import Any


TIMEOUT_BASE = 1_900_000_000_000


def role(name: str) -> dict[str, str]:
    return {"role_token": name}


def choice(name: str) -> dict[str, Any]:
    return {"choice_name": name, "choice_owner": role("Stress")}


def generate(n: int, k: int, nested_if: bool) -> Any:
    if n < 1 or k < 1:
        raise ValueError("n and k must be positive")
    continuation: Any = {"assert": False, "then": "close"}
    for depth in reversed(range(n)):
        if nested_if:
            continuation = {
                "if": {"value": "time_interval_start", "le_than": "time_interval_end"},
                "then": continuation,
                "else": "close",
            }
        cases = []
        for branch in range(k):
            cases.append(
                {
                    "case": {
                        "for_choice": choice(f"d{depth}-b{branch}"),
                        "choose_between": [{"from": 0, "to": 1}],
                    },
                    "then": continuation if branch == 0 else "close",
                }
            )
        continuation = {
            "when": cases,
            "timeout": TIMEOUT_BASE + depth,
            "timeout_continuation": "close",
        }
    return continuation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--nested-if", action="store_true")
    args = parser.parse_args()
    print(json.dumps(generate(args.n, args.k, args.nested_if), separators=(",", ":")))


if __name__ == "__main__":
    main()
