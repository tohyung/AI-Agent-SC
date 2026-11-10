"""E5 label audit: replay the label oracle's evidence on the pinned Haskell reference executor.

A WRONG label is confirmed when its witness trace also separates the two contracts on the
Haskell executor. A RIGHT label is challenged by random traces from the same action space;
any trace that separates them on Haskell flags the label for review. Run inside WSL:
    python -m research.experiments.gate_label_audit runs/e5/dev-M --out runs/e5/audit-dev-M.json
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import random
from typing import Any

from research.experiments import gate_labels as L
from research.experiments.gate_eval import cases, mutant_candidates, real_candidates
from research.synthesis.reference import PinnedMarloweReference, ReferenceRequest

EMPTY = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}
RANDOM_TRACES = 10


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _token(contract: Any, name: str) -> dict[str, str]:
    for node in _walk(contract):
        if isinstance(node, dict) and node.get("token_name") == name and "currency_symbol" in node:
            return {"currency_symbol": node["currency_symbol"], "token_name": name}
    return {"currency_symbol": "", "token_name": name}


def _input(contract: Any, step: dict[str, Any]) -> list[dict[str, Any]]:
    kind = step["kind"]
    if kind == "deposit":
        token = _token(contract, step["token"])
        account = {"role_token": step["party"]}
        for node in _walk(contract):
            if (isinstance(node, dict) and "deposits" in node
                    and node["party"].get("role_token") == step["party"]
                    and node["of_token"].get("token_name") == step["token"]):
                account = node["into_account"]
                if node["deposits"] == step["amount"]:
                    break
        return [{"type": "Deposit", "party": {"role_token": step["party"]}, "account": account,
                 "token": token, "amount": step["amount"]}]
    if kind == "choice":
        owner = {"role_token": step["party"]}
        name = step["name"]
        return [{"type": "Choice", "choice_id": {"choice_name": name, "choice_owner": owner},
                 "chosen": step["value"]}]
    if kind == "notify":
        return [{"type": "Notify"}]
    return []


def _resolved(contract: Any, trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give each choice the name of the case it matches in the When the contract is waiting in."""
    state = L._state(contract, trace[0]["time"] - L.DAY_MS) if trace else None
    out = []
    for step in trace:
        if step["kind"] == "choice" and state is not None:
            probe = deepcopy(state)
            probe.time = step["time"]
            probe.reduce()
            node = probe.contract
            cases = [b["case"]["for_choice"] for b in (node.get("when", []) if isinstance(node, dict) else [])
                     if "for_choice" in b["case"]
                     and b["case"]["for_choice"]["choice_owner"].get("role_token") == step["party"]
                     and any(x["from"] <= step["value"] <= x["to"] for x in b["case"]["choose_between"])]
            names = {c["choice_name"] for c in cases}
            if step["name"] not in names and len(cases) == 1:
                step = {**step, "name": cases[0]["choice_name"]}
        out.append(step)
        if state is not None:
            state.apply(step)
            if state.rejected:
                state = None
    return out


def observe(executor: Any, contract: Any, trace: list[dict[str, Any]],
            checkpoints: list[int]) -> tuple:
    """Accepted prefix, payouts and closure after it and at each later checkpoint, warnings."""
    trace = _resolved(contract, trace)
    transactions = [{"interval": {"from": s["time"], "to": s["time"]}, "inputs": _input(contract, s)}
                    for s in trace]
    raw = executor.execute(ReferenceRequest(contract, deepcopy(EMPTY), tuple(transactions)))
    steps = raw.get("steps", [])
    ok = [s for s in steps if s.get("status") == "Success"]
    if raw.get("status") not in {"Success", "TransactionError"}:
        return ("UNAVAILABLE", raw.get("status"))
    accepted = len(ok)
    prefix = transactions[:accepted]
    last_time = trace[accepted - 1]["time"] if accepted else -1

    def paid(items: list[dict[str, Any]]) -> tuple:
        totals: dict[tuple[str, str], int] = {}
        for step in items:
            for payment in step.get("payments", []):
                party = payment.get("payee", {}).get("party")
                if party:
                    key = (json.dumps(party, sort_keys=True), payment["token"]["token_name"])
                    totals[key] = totals.get(key, 0) + payment["amount"]
        return tuple(sorted(totals.items()))

    warn = any(w for s in ok for w in s.get("warnings", []))
    closed = ok[-1].get("contract") == "close" if ok else contract == "close"
    seen = [(paid(ok), closed)]
    for time in checkpoints:
        if time < last_time:
            continue
        advance = {"interval": {"from": time, "to": time}, "inputs": []}
        out = executor.execute(ReferenceRequest(contract, deepcopy(EMPTY), (*prefix, advance)))
        out_ok = [s for s in out.get("steps", []) if s.get("status") == "Success"]
        if len(out_ok) == accepted + 1:
            warn = warn or any(w for s in out_ok for w in s.get("warnings", []))
            seen.append((paid(out_ok), out_ok[-1].get("contract") == "close"))
        else:
            seen.append(seen[-1])
    return (accepted == len(trace), tuple(seen), warn)


def _random_traces(reference: Any, candidate: Any, seed: int) -> list[list[dict[str, Any]]]:
    rng = random.Random(seed)
    points = L.time_points(reference, candidate)
    values = L._constants(reference) | L._constants(candidate)
    depth = max(L.when_depth(reference), L.when_depth(candidate)) + 1
    traces = []
    for _ in range(RANDOM_TRACES):
        ref, cand = L._state(reference, points[0] - L.DAY_MS), L._state(candidate, points[0] - L.DAY_MS)
        trace: list[dict[str, Any]] = []
        index = 0
        for _ in range(rng.randint(1, depth)):
            index = rng.randint(index, len(points) - 1)
            time = points[index]
            options = {L._key(s): s for s in L._enabled(ref, time, values) + L._enabled(cand, time, values)}
            if not options:
                break
            step = {**rng.choice(list(options.values())), "time": time}
            trace.append(step)
            ref.apply(step)
            cand.apply(step)
            if ref.rejected or cand.rejected:
                break
        traces.append(trace)
    return traces


def audit_one(executor: Any, candidate: Any, reference: Any, record: dict[str, Any]) -> dict[str, Any]:
    candidate, reference = L.normalize_roles(candidate), L.normalize_roles(reference)
    points = L.time_points(reference, candidate)
    end = max(points + L.deadlines(candidate) + L.deadlines(reference)) + 2 * L.DAY_MS
    checkpoints = [*points, end]
    label = record["label"]
    if label["label"] == L.WRONG and label.get("witness") is not None:
        a = observe(executor, reference, label["witness"], checkpoints)
        b = observe(executor, candidate, label["witness"], checkpoints)
        return {"check": "witness", "agrees": a != b, "reference": repr(a), "candidate": repr(b)}
    if label["label"] == L.WRONG:
        return {"check": "structural", "agrees": True}
    if label["label"] != L.RIGHT:
        return {"check": "not_evaluable", "agrees": None}
    for number, trace in enumerate(_random_traces(reference, candidate, hash(record["candidate_id"]) % 2**32)):
        a = observe(executor, reference, trace, checkpoints)
        b = observe(executor, candidate, trace, checkpoints)
        if a != b:
            return {"check": "random", "agrees": False, "trace": trace, "trace_number": number,
                    "reference": repr(a), "candidate": repr(b)}
    return {"check": "random", "agrees": True, "traces": RANDOM_TRACES}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    executor = PinnedMarloweReference(binary=os.getenv("MARLOWE_REFERENCE_BINARY"))
    data = cases()
    pools: dict[int, dict[str, Any]] = {}
    results = []
    for path in sorted(args.directory.glob("case-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        index = record["case_index"]
        if index not in pools:
            pool = (mutant_candidates(data[index - 1], index) + real_candidates(index))
            pools[index] = {c.candidate_id: c.contract for c in pool}
        contract = pools[index][record["candidate_id"]]
        result = audit_one(executor, contract, data[index - 1]["reference_contract"], record)
        results.append({"candidate_id": record["candidate_id"], "label": record["label"]["label"],
                        "operator": record["operator"], **result})
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    disagree = [r for r in results if r["agrees"] is False]
    print(f"{len(results)} audited, {len(disagree)} disagree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
