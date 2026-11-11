"""Check dataset v3 references on the pinned binaries (run inside WSL, see runs/e5/run_wsl.sh):

    E5_FULL=dataset.v3.check_reference bash runs/e5/run_wsl.sh

For each feasible case: SMT must report Valid, and every scenario must run on the Haskell
reference executor with every transaction succeeding and the payouts equal to the expected ones.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

from research.adapters import smt_driver
from research.synthesis.reference import PinnedMarloweReference, ReferenceRequest

CASES = Path(__file__).resolve().parent / "cases.jsonl"
EMPTY = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}


def _walk(node: Any):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _token(contract: Any, name: str) -> dict[str, str]:
    for node in _walk(contract):
        if isinstance(node, dict) and node.get("token_name") == name and "currency_symbol" in node:
            return {"currency_symbol": node["currency_symbol"], "token_name": name}
    return {"currency_symbol": "", "token_name": name}


def _account(contract: Any, party: str, token_name: str) -> dict[str, str]:
    for node in _walk(contract):
        if (isinstance(node, dict) and "deposits" in node and node["party"].get("role_token") == party
                and node["of_token"].get("token_name") == token_name):
            return node["into_account"]
    return {"role_token": party}


def transactions(contract: Any, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for step in steps:
        if step["kind"] == "deposit":
            inputs = [{"type": "Deposit", "party": {"role_token": step["party"]},
                       "account": _account(contract, step["party"], step["token"]),
                       "token": _token(contract, step["token"]), "amount": step["amount"]}]
        elif step["kind"] == "choice":
            inputs = [{"type": "Choice", "choice_id": {"choice_name": step["name"],
                                                       "choice_owner": {"role_token": step["party"]}},
                       "chosen": step["value"]}]
        elif step["kind"] == "notify":
            inputs = [{"type": "Notify"}]
        else:
            inputs = []
        out.append({"interval": {"from": step["time"], "to": step["time"]}, "inputs": inputs})
    return out


def check_case(case: dict[str, Any], executor: Any, smt_binary: str | None) -> list[str]:
    contract, problems = case["reference_contract"], []
    smt = smt_driver.analyze(contract, binary=smt_binary)
    if smt.get("status") != "Valid":
        problems.append(f"SMT {smt.get('status')}: {str(smt.get('warnings') or smt.get('analysis_notes'))[:160]}")
    for sc in case["checks"]["scenarios"]:
        raw = executor.execute(ReferenceRequest(contract, dict(EMPTY), tuple(transactions(contract, sc["steps"]))))
        steps = raw.get("steps", [])
        if raw.get("status") != "Success" or len(steps) != len(sc["steps"]):
            problems.append(f"{sc['name']}: status {raw.get('status')} {str(steps[-1:])[:200]}")
            continue
        got: dict[str, dict[str, int]] = {}
        for step in steps:
            for payment in step.get("payments", []):
                party = payment.get("payee", {}).get("party", {}).get("role_token")
                if party:
                    bucket = got.setdefault(party, {})
                    name = payment["token"]["token_name"]
                    bucket[name] = bucket.get(name, 0) + payment["amount"]
        if got != sc["received"]:
            problems.append(f"{sc['name']}: Haskell paid {got}, expected {sc['received']}")
        if any(step.get("warnings") for step in steps):
            problems.append(f"{sc['name']}: warnings {[s.get('warnings') for s in steps if s.get('warnings')]}")
        if sc["closed"] and steps[-1].get("contract") != "close":
            problems.append(f"{sc['name']}: did not close")
    return problems


def main() -> int:
    executor = PinnedMarloweReference(binary=os.getenv("MARLOWE_REFERENCE_BINARY"))
    smt_binary = os.getenv("MARLOWE_SMT_BIN")
    bad = 0
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    for case in cases:
        if case["reference_contract"] is None:
            continue
        problems = check_case(case, executor, smt_binary)
        if problems:
            bad += 1
            for line in problems:
                print(f"{case['id']}: {line}")
    checked = sum(c["reference_contract"] is not None for c in cases)
    print(f"{checked} references checked, {bad} with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
