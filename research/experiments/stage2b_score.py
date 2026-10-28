"""Score one evaluation arm (M1-M4) after its run; evaluator fields stay here.

Fact ground truth is what the dataset reference contract actually uses: role
tokens, integer deposit/pay amounts and integer timeouts. Template parameters
are not used directly because every case carries all of them, used or not.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.experiments.online_tuning_batch01 import DATASET
from research.stage2b.intent_spec import DEADLINE_KINDS, PARTY_KINDS


BACKED = {"explicit", "derived", "user_confirmed"}
EXPECTED_DECISION = {
    "complete": {"accepted_interpretation"},
    "missing": {"clarification_required", "conflict_requires_resolution"},
    "ambiguous": {"clarification_required", "conflict_requires_resolution"},
    "infeasible": {"unsupported_for_current_study"},
}
FACT_KINDS = ("roles", "amounts", "deadlines")


def reference_facts(contract: Any) -> dict[str, set]:
    facts: dict[str, set] = {kind: set() for kind in FACT_KINDS}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key == "role_token" and isinstance(value, str):
                facts["roles"].add(value)
            elif key in {"deposits", "pay"} and type(value) is int:
                facts["amounts"].add(value)
            elif key == "timeout" and type(value) is int:
                facts["deadlines"].add(value)
            visit(value)

    visit(contract)
    return facts


def extracted_facts(core: dict[str, Any]) -> dict[str, set]:
    facts: dict[str, set] = {kind: set() for kind in FACT_KINDS}
    for claim in core.get("claims") or []:
        if not isinstance(claim, dict) or claim.get("status") not in BACKED:
            continue
        kind, value = claim.get("kind"), claim.get("value")
        if kind in PARTY_KINDS and isinstance(value, str):
            facts["roles"].add(value)
        elif kind == "amount_lovelace" and type(value) is int:
            facts["amounts"].add(value)
        elif kind in DEADLINE_KINDS and type(value) is int:
            facts["deadlines"].add(value)
    return facts


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _dataset() -> dict[str, dict[str, Any]]:
    with DATASET.open(encoding="utf-8") as source:
        cases = [json.loads(line) for line in source]
    return {case["id"]: case for case in cases[:56]}


def score_arm(arm_dir: Path, cases: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else _dataset()
    records = [json.loads(path.read_text(encoding="utf-8"))
               for path in sorted(arm_dir.glob("case-*.json"))]
    rows = []
    for record in records:
        case = cases[record["case_id"]]
        core = record.get("semantic_core") or {}
        expected = reference_facts(case["reference_contract"])
        found = extracted_facts(core)
        row = {
            "case_index": record["case_index"], "case_id": record["case_id"],
            "info_mode": case["info_mode"],
            "first_pass_valid": record.get("first_pass_valid") is True,
            "final_valid": record.get("final_valid") is True,
            "physical_calls": record["physical_calls"],
            "decision_correct": (record.get("predicted_resolution")
                                 in EXPECTED_DECISION[case["info_mode"]]),
            "facts": {kind: {"expected": len(expected[kind]), "found": len(found[kind]),
                             "matched": len(expected[kind] & found[kind])}
                      for kind in FACT_KINDS},
        }
        rows.append(row)
    total = len(rows)
    valid = [row for row in rows if row["final_valid"]]
    complete = [row for row in rows if row["info_mode"] == "complete"]
    m3 = {}
    for kind in FACT_KINDS:
        matched = sum(row["facts"][kind]["matched"] for row in complete)
        m3[kind] = {
            "recall": _ratio(matched, sum(row["facts"][kind]["expected"] for row in complete)),
            "precision": _ratio(matched, sum(row["facts"][kind]["found"] for row in complete)),
        }
    summary = {
        "cases_scored": total,
        "M1_first_pass_valid": _ratio(sum(row["first_pass_valid"] for row in rows), total),
        "M2_final_valid": _ratio(len(valid), total),
        "M2_calls_per_valid_intent": _ratio(sum(row["physical_calls"] for row in rows),
                                            len(valid)),
        "M3_complete_cases": len(complete),
        "M3_fact_agreement": m3,
        "M4_decision_correct": _ratio(sum(row["decision_correct"] for row in rows), total),
        "M4_by_info_mode": {
            mode: _ratio(sum(row["decision_correct"] for row in rows
                             if row["info_mode"] == mode),
                         sum(row["info_mode"] == mode for row in rows))
            for mode in sorted({row["info_mode"] for row in rows})},
    }
    return {"summary": summary, "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a Stage 2B evaluation arm")
    parser.add_argument("arm_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = score_arm(args.arm_dir)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
