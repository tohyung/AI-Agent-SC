"""Machine scoring of a delivered contract against a dataset v3 case (E7 conventions, Q-CHẤM 1).

Each `checks.scenarios` entry is replayed on the pinned Haskell reference, step by step:
a scenario step is bound to the action the contract enables at that point (deposit by party,
amount and token; choice by owner and value, any choice name; notify), with party names matched
by `fold_name`. A scenario passes when every step is enabled, every party receives what the
scenario says, and the contract is closed when the scenario says so.

Deadlines are checked separately against `spec` (Q-GIỜ 1): every deadline the case states must
have a contract timeout within one minute, and every contract timeout must be within one minute of
a stated deadline. Scenario times sit hours away from deadlines, so they cannot see an hour's error.

The machine verdict is RIGHT only when all scenarios pass and the deadline check is clean;
anything else is REVIEW, with the reasons, for the adjudicator (Q-CHẤM 2). No contract is NONE.

  python -m research.experiments.e7_score --arm pipeline|baseline --cases 30-100 --out FILE
      [--dataset v3|v4|v5] [--pipeline-dir DIR] [--baseline-dir DIR] [--time-tolerance-minutes M]
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from research.formalization.party_names import fold_name
from research.synthesis.reference import ReferenceRequest

ROOT = Path(__file__).resolve().parents[2]
DATASET_V3 = ROOT / "dataset" / "v3" / "cases.jsonl"
DATASETS = {"v3": DATASET_V3, "v4": ROOT / "dataset" / "v4" / "cases.jsonl",
            "v5": ROOT / "dataset" / "v5" / "cases.jsonl"}
EMPTY_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}
TIME_TOLERANCE_MS = 60_000


def _enabled_cases(contract: Any) -> list[dict[str, Any]]:
    if not isinstance(contract, dict) or not isinstance(contract.get("when"), list):
        return []
    return [item["case"] for item in contract["when"]
            if isinstance(item, dict) and isinstance(item.get("case"), dict)]


def _token_key(token: Any) -> str:
    return token.get("token_name", "") if isinstance(token, dict) else ""


def _role(value: Any) -> str | None:
    return value.get("role_token") if isinstance(value, dict) else None


def bind_step(step: dict[str, Any], current: Any) -> dict[str, Any] | None:
    """The Marlowe input for a scenario step in the contract's current continuation, or None
    when the contract does not enable it. An advance has no input."""
    kind = step["kind"]
    if kind == "advance":
        return {}
    matches = []
    for action in _enabled_cases(current):
        if kind == "deposit" and "deposits" in action:
            if (fold_name(_role(action.get("party")) or "") == fold_name(step["party"])
                    and action.get("deposits") == step["amount"]
                    and _token_key(action.get("of_token")) == step.get("token", "")):
                matches.append({"type": "Deposit", "party": action["party"],
                                "account": action["into_account"], "token": action["of_token"],
                                "amount": step["amount"]})
        elif kind == "choice" and "for_choice" in action:
            choice = action["for_choice"]
            if (fold_name(_role(choice.get("choice_owner")) or "") == fold_name(step["party"])
                    and any(isinstance(bound, dict) and bound.get("from", 1) <= step["value"]
                            <= bound.get("to", 0) for bound in action.get("choose_between", []))):
                matches.append({"type": "Choice", "choice_id": choice, "chosen": step["value"]})
        elif kind == "notify" and "notify_if" in action:
            matches.append({"type": "Notify"})
    distinct = {json.dumps(item, sort_keys=True, ensure_ascii=False): item for item in matches}
    return next(iter(distinct.values())) if len(distinct) == 1 else None


def _payments(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for step in raw.get("steps", []) or [] if isinstance(step, dict)
            and step.get("status") == "Success" for item in step.get("payments", []) or []]


def received_by_party(payments: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Folded party name -> token key -> amount paid to that party (not to an account)."""
    totals: dict[str, dict[str, int]] = {}
    for item in payments:
        party = _role((item.get("payee") or {}).get("party"))
        if party is None or type(item.get("amount")) is not int:
            continue
        per_token = totals.setdefault(fold_name(party), {})
        key = _token_key(item.get("token"))
        per_token[key] = per_token.get(key, 0) + item["amount"]
    return {party: {key: amount for key, amount in tokens.items() if amount}
            for party, tokens in totals.items() if any(tokens.values())}


def run_scenario(contract: Any, scenario: dict[str, Any], executor: Any) -> list[str]:
    """Problems found replaying one check scenario; empty when it passes."""
    transactions: list[dict[str, Any]] = []
    current = contract
    for number, step in enumerate(scenario["steps"], 1):
        bound = bind_step(step, current)
        if bound is None:
            return [f"{scenario['name']}: step {number} ({step['kind']}"
                    f"{' ' + step['party'] if 'party' in step else ''}) is not enabled"]
        at = step["time"]
        transactions.append({"interval": {"from": at, "to": at},
                             "inputs": [bound] if bound else []})
        raw = executor.execute(ReferenceRequest(contract, dict(EMPTY_STATE), tuple(transactions)))
        if raw.get("status") != "Success":
            return [f"{scenario['name']}: step {number} fails ({raw.get('status')})"]
        current = raw.get("final_contract", raw.get("finalContract"))
    problems = []
    observed = received_by_party(_payments(raw))
    expected = {fold_name(party): {key: amount for key, amount in tokens.items() if amount}
                for party, tokens in scenario.get("received", {}).items()}
    expected = {party: tokens for party, tokens in expected.items() if tokens}
    if observed != expected:
        problems.append(f"{scenario['name']}: received {observed}, expected {expected}")
    if scenario.get("closed") is True and current != "close":
        problems.append(f"{scenario['name']}: contract not closed")
    return problems


def _spec_instants(value: Any) -> set[int]:
    found: set[int] = set()
    if isinstance(value, dict):
        for item in value.values():
            found |= _spec_instants(item)
    elif isinstance(value, list):
        for item in value:
            found |= _spec_instants(item)
    elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}.*", value):
        found.add(int(datetime.fromisoformat(value).timestamp() * 1000))
    return found


def _timeouts(contract: Any) -> set[int]:
    found: set[int] = set()
    if isinstance(contract, dict):
        if type(contract.get("timeout")) is int:
            found.add(contract["timeout"])
        for item in contract.values():
            found |= _timeouts(item)
    elif isinstance(contract, list):
        for item in contract:
            found |= _timeouts(item)
    return found


def deadline_problems(contract: Any, spec: dict[str, Any]) -> list[str]:
    stated, used = _spec_instants(spec), _timeouts(contract)
    problems = []
    for instant in sorted(stated):
        if not any(abs(instant - timeout) <= TIME_TOLERANCE_MS for timeout in used):
            problems.append(f"no timeout at stated deadline {instant}")
    for timeout in sorted(used):
        if not any(abs(timeout - instant) <= TIME_TOLERANCE_MS for instant in stated):
            problems.append(f"timeout {timeout} is not a stated deadline")
    return problems


def machine_verdict(contract: Any, case: dict[str, Any], executor: Any) -> dict[str, Any]:
    if contract is None:
        return {"verdict": "NONE", "problems": []}
    problems = []
    for scenario in case["checks"].get("scenarios", []):
        try:
            problems += run_scenario(contract, scenario, executor)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
            problems.append(f"{scenario.get('name')}: could not run ({type(exc).__name__}: {exc})")
    problems += deadline_problems(contract, case.get("spec", {}))
    return {"verdict": "REVIEW" if problems else "RIGHT", "problems": problems}


def _parse_range(text: str) -> list[int]:
    first, _, last = text.partition("-")
    return list(range(int(first), int(last or first) + 1))


def main() -> int:
    from research.experiments.e6_score import BASELINE_DIR, PIPELINE_DIR, baseline_outcome, \
        pipeline_outcome
    from research.synthesis.reference import PinnedMarloweReference

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--arm", choices=("pipeline", "baseline"), required=True)
    parser.add_argument("--cases", default="30-100")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="v3",
                        help="whose checks to replay (v4 adds first-come buyers)")
    parser.add_argument("--pipeline-dir", type=Path, default=PIPELINE_DIR)
    parser.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    parser.add_argument("--time-tolerance-minutes", type=float, default=1.0,
                        help="deadline tolerance; 1 minute is the frozen rule (Q-GIỜ 1), larger "
                             "values only feed the sensitivity table (Q-GIỜ 6)")
    args = parser.parse_args()
    global TIME_TOLERANCE_MS
    TIME_TOLERANCE_MS = int(args.time_tolerance_minutes * 60_000)
    cases = [json.loads(line) for line in DATASETS[args.dataset].read_text(encoding="utf-8").splitlines()]
    executor = PinnedMarloweReference(binary=os.getenv("MARLOWE_REFERENCE_BINARY"))
    results = {}
    for index in _parse_range(args.cases):
        if args.arm == "pipeline":
            outcome = pipeline_outcome(args.pipeline_dir / f"case-{index:03d}")
        else:
            outcome = baseline_outcome(args.baseline_dir / f"case-{index:03d}")
        results[index] = machine_verdict(outcome["contract"], cases[index - 1], executor)
        print(index, results[index]["verdict"], "; ".join(results[index]["problems"])[:200])
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
