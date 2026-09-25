"""Independent static and behavioral scoring; never uses Node 2's verdict."""

from __future__ import annotations

from itertools import permutations
from typing import Any

from marlowe_agent.marlowe_validator import validate_contract

from .config import WEIGHTS
from .marlowe_sim import run_scenario, timeouts, token_id


def _walk(node: Any) -> list[Any]:
    result = [node]
    if isinstance(node, dict):
        for value in node.values():
            result.extend(_walk(value))
    elif isinstance(node, list):
        for value in node:
            result.extend(_walk(value))
    return result


def _parties(contract: Any) -> set[str]:
    return {node["role_token"] for node in _walk(contract)
            if isinstance(node, dict) and "role_token" in node}


def _tokens(contract: Any) -> set[str]:
    return {token_id(node) for node in _walk(contract)
            if isinstance(node, dict) and "token_name" in node and "currency_symbol" in node}


def _amounts(contract: Any) -> set[int]:
    return {node[key] for node in _walk(contract) if isinstance(node, dict)
            for key in ("deposits", "pay") if type(node.get(key)) is int}


def _time(label: str, dates: list[int]) -> int:
    if not dates:
        raise ValueError("no_timeouts")
    if label == "before_t1":
        return dates[0] - 1000
    if label == "after_t1_before_t2" and len(dates) >= 2:
        return (dates[0] + dates[1]) // 2
    if label == "after_t2_before_t3" and len(dates) >= 3:
        return (dates[1] + dates[2]) // 2
    if label == "after_all":
        return dates[-1] + 1000
    raise ValueError(f"missing_timepoint:{label}")


def _run(contract: Any, scenario: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    dates = timeouts(contract)
    steps = []
    for raw in scenario["steps"]:
        step = raw.copy()
        step["time"] = _time(step.pop("at"), dates)
        if "party" in step:
            step["party"] = mapping[step["party"]]
        steps.append(step)
    result = run_scenario(contract, steps, dates[0] - 86400000 if dates else 0)
    reverse = {candidate: reference for reference, candidate in mapping.items()}
    result["received"] = {reverse.get(party, party): tokens for party, tokens in result["received"].items()}
    return result


def evaluate(case: Any, contract: Any, status: str = "done") -> dict[str, Any]:
    if case.expected_behavior == "should_not_converge_silently":
        return {"strict_correct": status != "done", "false_convergence": status == "done",
                "overall_accuracy": None, "checks": [], "mapping": {}}
    errors = validate_contract(contract)
    if errors:
        return {"strict_correct": False, "false_convergence": status == "done",
                "overall_accuracy": 0.0, "structure_accuracy": 0.0, "timing_accuracy": 0.0,
                "scenario_accuracy": 0.0, "checks": [{"group": "structure", "passed": False,
                                                     "reason": "invalid_contract", "details": errors[:3]}],
                "mapping": {}, "diagnostics": ["invalid_contract"]}
    checks: list[dict[str, Any]] = []
    reference = case.reference_contract
    expected_parties = _parties(reference)
    actual_parties = _parties(contract)
    expected_tokens = _tokens(reference)
    actual_tokens = _tokens(contract)
    checks.append({"group": "structure", "name": "party_count", "passed": len(actual_parties) >= len(expected_parties)})
    for token in sorted(expected_tokens):
        checks.append({"group": "structure", "name": f"token:{token}", "passed": token.lower() in {t.lower() for t in actual_tokens}})
    actual_amounts = _amounts(contract)
    diagnostics = []
    if any(actual != expected and (actual * 1000000 == expected or expected * 1000000 == actual)
           for actual in actual_amounts for expected in _amounts(reference)):
        diagnostics.append("lovelace_unit_error")
    for amount in sorted(_amounts(reference)):
        passed = amount in actual_amounts
        checks.append({"group": "structure", "name": f"amount:{amount}", "passed": passed})
        if not passed and (amount * 1000000 in actual_amounts or amount // 1000000 in actual_amounts):
            diagnostics.append("lovelace_unit_error")
    expected_dates, actual_dates = timeouts(reference), timeouts(contract)
    checks.append({"group": "timing", "name": "distinct_deadlines",
                   "passed": len(actual_dates) >= len(expected_dates)})
    for left, right in zip(expected_dates, expected_dates[1:]):
        gap = right - left
        passed = any(abs((b - a) - gap) <= gap * 0.1
                     for a, b in zip(actual_dates, actual_dates[1:]))
        checks.append({"group": "timing", "name": f"gap:{gap}", "passed": passed})
    if "absolute_date" in case.challenges and expected_dates:
        checks.append({"group": "timing", "name": "absolute_date",
                       "passed": any(abs(actual - expected_dates[0]) <= 86400000 for actual in actual_dates)})
    if actual_dates and actual_dates[0] <= __import__("time").time() * 1000:
        diagnostics.append("timeouts_in_future_at_run_time:false")
    scenarios = case.checks["scenarios"]
    references = sorted(expected_parties)
    candidates = sorted(actual_parties)
    best: tuple[int, int, dict[str, str], list[dict[str, Any]]] | None = None
    if len(candidates) >= len(references) and len(references) <= 4 and len(candidates) <= 6:
        for perm in permutations(candidates, len(references)):
            mapping = dict(zip(references, perm))
            results = []
            for scenario in scenarios:
                try:
                    outcome = _run(contract, scenario, mapping)
                    passed = (not outcome["not_evaluable"] and not outcome["input_rejected"]
                              and outcome["received"] == scenario["received"]
                              and outcome["closed"] == scenario["closed"])
                    if outcome["not_evaluable"]:
                        diagnostics.append("not_evaluable")
                    reason = "not_evaluable" if outcome["not_evaluable"] else (
                        "input_rejected" if outcome["input_rejected"] else "behavior_mismatch")
                except ValueError as exc:
                    passed, reason = False, str(exc)
                results.append({"group": "scenarios", "name": scenario["name"],
                                "passed": passed, "reason": "ok" if passed else reason})
            metric = (sum(x["passed"] for x in results), sum(a.lower() == b.lower() for a, b in mapping.items()))
            if best is None or metric > best[:2]:
                best = (*metric, mapping, results)
    if best is None:
        mapping = {}
        checks.extend({"group": "scenarios", "name": s["name"], "passed": False,
                       "reason": "missing_parties"} for s in scenarios)
    else:
        mapping = best[2]
        checks.extend(best[3])
    scores = {}
    for group in WEIGHTS:
        group_checks = [item for item in checks if item["group"] == group and item.get("reason") != "not_evaluable"]
        scores[group] = (sum(item["passed"] for item in group_checks) / len(group_checks)) if group_checks else None
    weight_total = sum(WEIGHTS[group] for group, score in scores.items() if score is not None)
    overall = sum(WEIGHTS[group] * score for group, score in scores.items() if score is not None) / weight_total
    strict = bool(checks) and all(item["passed"] for item in checks)
    return {"structure_accuracy": scores["structure"], "timing_accuracy": scores["timing"],
            "scenario_accuracy": scores["scenarios"], "overall_accuracy": overall,
            "strict_correct": strict, "false_convergence": status == "done" and not strict,
            "checks": checks, "mapping": mapping, "diagnostics": sorted(set(diagnostics))}
