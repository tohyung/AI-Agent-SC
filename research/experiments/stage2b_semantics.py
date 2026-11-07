"""Compare what an A2 draft means with what the dataset's reference contract does.

⟦D⟧ (`fact_semantics.denote`) gives the contract a resolved draft means. Each
path of it is compared with the paths of the case's `reference_contract`: the
inputs in order, the deadlines met and who receives how much. Choice names and
numbers are ignored, because a draft may number its options differently. Dev
cases only; this reads evaluator fields and no model is called.

With `--fill-withheld`, facts no prompt states are filled in the way the
dataset assumes (12:00 UTC, a token policy), since a draft must leave them open.
Records that needed filling show only that the rest of the draft is right.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from research.experiments.online_tuning_batch01 import DATASET
from research.stage2b.fact_builder import normalize_draft
from research.stage2b.fact_semantics import NotDenotable, denote, paths

PLACEHOLDER_POLICY = "00" * 28


def fill_withheld(draft: dict[str, Any]) -> dict[str, Any]:
    """The draft with open times at 12:00 UTC and open token policies filled."""
    filled = deepcopy(draft)
    for item in filled.get("instants") or []:
        for holder in [item, *(item.get("alternatives") or [])]:
            spec = (holder.get("expr") or {}).get("date") if isinstance(holder, dict) else None
            if isinstance(spec, dict) and (spec.get("h") is None or spec.get("tz") is None):
                spec.update({"h": 12, "min": 0, "tz": "+00:00"})
    for asset in filled.get("assets") or []:
        if not asset.get("ada") and not asset.get("native"):
            name = str(asset.get("name", "token")).encode().hex()
            asset["native"] = f"native:{PLACEHOLDER_POLICY}/{name}"
    return filled


def inline_lets(node: Any, bound: dict[str, Any] | None = None) -> Any:
    """The contract without `Let`: each `UseValue` replaced by the bound value."""
    bound = bound or {}
    if isinstance(node, list):
        return [inline_lets(item, bound) for item in node]
    if not isinstance(node, dict):
        return node
    if "let" in node:
        return inline_lets(node["then"], {**bound, node["let"]: inline_lets(node["be"], bound)})
    if "use_value" in node:
        return bound[node["use_value"]]
    return {key: inline_lets(value, bound) for key, value in node.items()}


def _signature(run: Any) -> tuple:
    inputs: list[tuple] = []
    for transaction in run.transactions:
        for item in transaction["inputs"] or [{"type": "Timeout"}]:
            if item["type"] == "Deposit":
                inputs.append(("deposit", item["party"]["role_token"], item["amount"],
                               item["token"]["currency_symbol"] == ""))
            elif item["type"] == "Choice":
                inputs.append(("choice", item["choice_id"]["choice_owner"]["role_token"]))
            else:
                inputs.append((item["type"].lower(),))
    received: Counter[str] = Counter()
    for _source, payee, amount in run.payments:
        received[payee] += amount
    return tuple(inputs), tuple(run.deadlines), tuple(sorted(received.items()))


def behaviors(contract: Any) -> set[tuple]:
    return {_signature(run) for run in paths(contract)}


def compare_draft(draft: Any, reference: Any, *, fill: bool = False) -> dict[str, Any]:
    canonical = normalize_draft(draft)[0]
    if fill:
        canonical = fill_withheld(canonical)
    try:
        meaning = behaviors(denote(canonical))
    except NotDenotable as exc:
        return {"verdict": "NOT_DENOTABLE", "reason": str(exc)}
    expected = behaviors(inline_lets(reference))
    # SUBSET: nothing the draft does is wrong, but a path the reference has is absent.
    verdict = ("MATCH" if meaning == expected else
               "SUBSET" if meaning < expected else "DIFFERENT")
    return {"verdict": verdict,
            "paths": len(expected), "only_draft": len(meaning - expected),
            "only_reference": len(expected - meaning),
            "first_only_draft": repr(next(iter(sorted(meaning - expected)), None)),
            "first_only_reference": repr(next(iter(sorted(expected - meaning)), None))}


def compare_arm(arm_dir: Path, *, fill: bool = False) -> dict[str, Any]:
    with DATASET.open(encoding="utf-8") as source:
        cases = {case["id"]: case for case in map(json.loads, source.read().splitlines()[:56])}
    rows = []
    for path in sorted(arm_dir.glob("case-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        attempts = record.get("fact_draft_attempts") or []
        case = cases[record["case_id"]]
        row = {"case_index": record["case_index"], "info_mode": case["info_mode"]}
        if not record.get("final_valid") or not attempts:
            rows.append({**row, "verdict": "NO_VALID_DRAFT"})
        else:
            rows.append({**row, **compare_draft(attempts[-1]["draft"],
                                                case["reference_contract"], fill=fill)})
    complete = [row for row in rows if row["info_mode"] == "complete"]
    return {"fill_withheld": fill, "complete_cases": len(complete),
            "complete_verdicts": dict(Counter(row["verdict"] for row in complete)),
            "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare A2 drafts with reference contracts")
    parser.add_argument("arm_dir", type=Path)
    parser.add_argument("--fill-withheld", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare_arm(args.arm_dir, fill=args.fill_withheld)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("fill_withheld", "complete_cases",
                                                   "complete_verdicts")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
