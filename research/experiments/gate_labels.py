"""E5 label oracle: bounded differential testing against the reference contract.

Independent of the gates under test: it runs the Python interpreter in
`dataset/marlowe_sim.py`, not the pinned Haskell reference executor. See
docs/archive/E5-Evidence-Gates.md, section 4.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from dataset.marlowe_sim import NotEvaluable, SimState
from research.analysis.marlowe_validator import validate_contract

DAY_MS = 86_400_000
MAX_NODES = 200_000
WRONG, RIGHT, UNEVALUABLE = "WRONG", "RIGHT", "NOT_EVALUABLE"
COMPARISONS = ("ge_than", "gt", "lt", "le_than", "equal_to")


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def deadlines(contract: Any) -> list[int]:
    return sorted({node["timeout"] for node in _walk(contract)
                   if isinstance(node, dict) and "when" in node and type(node.get("timeout")) is int})


def when_depth(contract: Any) -> int:
    if not isinstance(contract, dict):
        return 0
    if "when" in contract:
        return 1 + max([when_depth(b["then"]) for b in contract["when"]]
                       + [when_depth(contract["timeout_continuation"])])
    if "if" in contract:
        return max(when_depth(contract["then"]), when_depth(contract["else"]))
    return when_depth(contract.get("then"))


def _constants(contract: Any) -> set[int]:
    return {node[key] for node in _walk(contract) if isinstance(node, dict)
            for key in COMPARISONS if type(node.get(key)) is int}


def normalize_roles(contract: Any) -> Any:
    """Role names compared after trimming and case folding (no permutation of parties)."""
    if isinstance(contract, dict):
        return {key: (value.strip().casefold() if key == "role_token" and isinstance(value, str)
                      else normalize_roles(value)) for key, value in contract.items()}
    if isinstance(contract, list):
        return [normalize_roles(item) for item in contract]
    return contract


def time_points(reference: Any, candidate: Any) -> list[int]:
    dates = deadlines(reference) or deadlines(candidate)
    if not dates:
        return [0]
    # One day either side of every deadline, plus the midpoint between neighbours.
    points = {d + offset for d in dates for offset in (-DAY_MS, DAY_MS)}
    points |= {(left + right) // 2 for left, right in zip(dates, dates[1:])}
    return sorted(points)


def _state(contract: Any, start: int) -> SimState:
    state = SimState(deepcopy(contract), start)
    state.reduce()
    return state


def _enabled(state: SimState, time: int, values: set[int]) -> list[dict[str, Any]]:
    probe = deepcopy(state)
    probe.time = time
    probe.reduce()
    node = probe.contract
    if not isinstance(node, dict) or "when" not in node:
        return []
    steps = []
    for branch in node["when"]:
        action = branch["case"]
        if "deposits" in action:
            steps.append({"kind": "deposit", "party": action["party"].get("role_token"),
                          "amount": probe.value(action["deposits"]),
                          "token": action["of_token"].get("token_name", "")})
        elif "for_choice" in action:
            choice = action["for_choice"]
            for bound in action["choose_between"]:
                low, high = bound["from"], bound["to"]
                options = {low, high, (low + high) // 2} | {
                    v + d for v in values for d in (-1, 0, 1) if low <= v + d <= high}
                steps += [{"kind": "choice", "party": choice["choice_owner"].get("role_token"),
                           "name": choice["choice_name"], "value": value}
                          for value in sorted(options)]
        elif "notify_if" in action:
            steps.append({"kind": "notify"})
    return steps


def _key(step: dict[str, Any]) -> tuple:
    # A choice is identified by owner and value; its name may differ between contracts.
    return tuple(sorted((k, v) for k, v in step.items() if k not in {"name", "time"}))


def _snapshot(state: SimState) -> tuple:
    received = tuple(sorted((party, tuple(sorted(tokens.items())))
                            for party, tokens in state.received.items()))
    # A payment larger than the balance is a defect even when the payout ends up equal.
    return received, state.contract == "close" and not state.accounts, state.partial_pay


def _outcome(state: SimState, checkpoints: list[int]) -> tuple:
    """What has been paid by each later checkpoint when nobody acts again (timing matters)."""
    final = deepcopy(state)
    seen = []
    for time in checkpoints:
        if time >= final.time:
            final.apply({"kind": "advance", "time": time})
        seen.append(_snapshot(final))
    return tuple(seen)


def label(candidate: Any, reference: Any, *, max_nodes: int = MAX_NODES) -> dict[str, Any]:
    """WRONG with a witness trace, RIGHT within the bound, or NOT_EVALUABLE."""
    if validate_contract(candidate):
        return {"label": WRONG, "reason": "structurally_invalid", "witness": None}
    candidate, reference = normalize_roles(candidate), normalize_roles(reference)
    ref_dates, cand_dates = deadlines(reference), deadlines(candidate)
    if len(ref_dates) == len(cand_dates) and any(
            abs(a - b) >= DAY_MS for a, b in zip(ref_dates, cand_dates)):
        timing_note = "deadline_shift_ge_1_day"
    else:
        timing_note = None
    points = time_points(reference, candidate)
    end = max(points + cand_dates + ref_dates) + 2 * DAY_MS
    checkpoints = [*points, end]
    values = _constants(reference) | _constants(candidate)
    depth = max(when_depth(reference), when_depth(candidate)) + 1
    start = points[0] - DAY_MS
    visited = 0
    try:
        root = (_state(reference, start), _state(candidate, start))
        stack = [(root, 0, [])]
        while stack:
            (ref, cand), point, trace = stack.pop()
            visited += 1
            if visited > max_nodes:
                return {"label": RIGHT, "reason": "bound_reached", "witness": None,
                        "nodes": visited, "timing_note": timing_note}
            if _outcome(ref, checkpoints) != _outcome(cand, checkpoints):
                return {"label": WRONG, "reason": "outcome_differs", "witness": trace,
                        "nodes": visited, "timing_note": timing_note}
            if len(trace) >= depth:
                continue
            for index in range(point, len(points)):
                time = points[index]
                steps = {_key(s): s for s in _enabled(ref, time, values) + _enabled(cand, time, values)}
                for step in steps.values():
                    step = {**step, "time": time}
                    next_ref, next_cand = deepcopy(ref), deepcopy(cand)
                    next_ref.apply(step)
                    next_cand.apply(step)
                    if next_ref.rejected and next_cand.rejected:
                        continue
                    if next_ref.rejected != next_cand.rejected:
                        return {"label": WRONG, "reason": "input_accepted_by_one_only",
                                "witness": trace + [step], "nodes": visited,
                                "timing_note": timing_note}
                    stack.append(((next_ref, next_cand), index, trace + [step]))
    except NotEvaluable as exc:
        return {"label": UNEVALUABLE, "reason": str(exc), "witness": None, "nodes": visited}
    return {"label": RIGHT, "reason": "no_difference_within_bound", "witness": None,
            "nodes": visited, "timing_note": timing_note}
