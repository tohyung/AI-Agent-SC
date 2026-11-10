"""E5 scoring: false acceptance, coverage and per-gate effect (docs/E5-Evidence-Gates.md, 6-7).

    python -m research.experiments.gate_score runs/e5/E5-Round2-Variants [--final-only]
        [--labels docs/E5-Adjudication.json] [--output FILE]
Reads E5-Round1 records too: their rungs B0-B4 map to Structure, Lint, SMT, Scenario, Oracle,
and Alignment (not run in Round 1) takes the SMT decision.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from math import comb, sqrt
from pathlib import Path
import random
from typing import Any

from research.experiments.gate_policy import GATES, ROUND1_GATES, ROUND1_RUNGS, RUNGS

WRONG, RIGHT = "WRONG", "RIGHT"
BOOTSTRAP = 10_000


def wilson(successes: int, total: int, z: float = 1.959964) -> list[float] | None:
    if total == 0:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(centre - half, 4), round(centre + half, 4)]


def mcnemar(only_first: int, only_second: int) -> float:
    n = only_first + only_second
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(only_first, only_second) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _modern(record: dict[str, Any]) -> dict[str, Any]:
    if "B0" not in record["decisions"]:
        return record
    decisions = {ROUND1_RUNGS[key]: value for key, value in record["decisions"].items()}
    decisions["Alignment"] = decisions["SMT"]
    gates = {ROUND1_GATES[key]: value for key, value in record["gates"].items()}
    gates["Alignment"] = "N/A"
    return {**record, "decisions": decisions, "gates": gates}


def load(directory: Path, *, final_only: bool = False,
         labels: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Records of one run; `labels` (adjudicated verdicts) replace the machine label."""
    records = [_modern(json.loads(path.read_text(encoding="utf-8")))
               for path in sorted(directory.glob("case-*.json"))]
    if labels is not None:
        for record in records:
            verdict = labels.get(record["candidate_id"])
            if verdict is not None:
                record["machine_label"] = record["label"]
                record["label"] = {**record["label"], "label": verdict[0],
                                   "reason": "adjudicated: " + verdict[1]}
    return [r for r in records if not final_only or r.get("is_final")]


def _rate(records: list[dict[str, Any]], rung: str, decision: str) -> dict[str, Any]:
    hits = sum(r["decisions"][rung] == decision for r in records)
    return {"count": hits, "total": len(records),
            "rate": round(hits / len(records), 4) if records else None,
            "wilson95": wilson(hits, len(records))}


def _cluster_ci(records: list[dict[str, Any]], rung: str, decision: str,
                seed: int = 20261109) -> list[float] | None:
    by_case: dict[int, list[int]] = defaultdict(list)
    for r in records:
        by_case[r["case_index"]].append(r["decisions"][rung] == decision)
    if not by_case:
        return None
    cases = list(by_case)
    rng = random.Random(seed)
    estimates = []
    for _ in range(BOOTSTRAP):
        sample = [by_case[rng.choice(cases)] for _ in cases]
        hits, total = sum(sum(s) for s in sample), sum(len(s) for s in sample)
        estimates.append(hits / total)
    estimates.sort()
    return [round(estimates[int(0.025 * BOOTSTRAP)], 4), round(estimates[int(0.975 * BOOTSTRAP)], 4)]


def score(records: list[dict[str, Any]]) -> dict[str, Any]:
    labels = Counter(r["label"]["label"] for r in records)
    wrong = [r for r in records if r["label"]["label"] == WRONG]
    right = [r for r in records if r["label"]["label"] == RIGHT]
    rungs = {}
    for rung in RUNGS:
        rungs[rung] = {
            "false_accept": {**_rate(wrong, rung, "ACCEPT"),
                             "cluster95": _cluster_ci(wrong, rung, "ACCEPT")},
            "coverage": {**_rate(right, rung, "ACCEPT"),
                         "cluster95": _cluster_ci(right, rung, "ACCEPT")},
            "false_reject": _rate(right, rung, "REJECT"),
            "abstain_wrong": _rate(wrong, rung, "ABSTAIN"),
            "abstain_right": _rate(right, rung, "ABSTAIN"),
        }
    b0 = [r["decisions"]["Structure"] == "ACCEPT" for r in wrong]
    b4 = [r["decisions"]["Oracle"] == "ACCEPT" for r in wrong]
    only_b0 = sum(a and not b for a, b in zip(b0, b4))
    only_b4 = sum(b and not a for a, b in zip(b0, b4))
    per_operator: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        per_operator[r["operator"]][f"{r['label']['label']}:{r['decisions']['Oracle']}"] += 1
    gate_rejects = {gate: Counter(r["gates"][gate] for r in records) for gate in GATES}
    escaped = [{"candidate_id": r["candidate_id"], "operator": r["operator"],
                "witness": r["label"].get("witness")}
               for r in wrong if r["decisions"]["Oracle"] == "ACCEPT"]
    full = rungs["Oracle"]
    rule = {
        "full_FA_below_Structure_p<0.05": (mcnemar(only_b0, only_b4) < 0.05 and only_b0 > only_b4),
        "full_coverage>=0.80": (full["coverage"]["rate"] is not None
                                and full["coverage"]["rate"] >= 0.80),
        "full_false_reject<=0.10": (full["false_reject"]["rate"] is not None
                                    and full["false_reject"]["rate"] <= 0.10),
    }
    return {
        "candidates": len(records), "cases": len({r["case_index"] for r in records}),
        "labels": dict(labels), "rungs": rungs,
        "Structure_vs_Oracle_on_wrong": {"only_Structure_accepts": only_b0,
                                         "only_Oracle_accepts": only_b4,
                                         "mcnemar_p": mcnemar(only_b0, only_b4)},
        "decision_rule": {**rule, "all": all(rule.values())},
        "gate_outcomes": {gate: dict(counts) for gate, counts in gate_rejects.items()},
        "per_operator_label_B4": {op: dict(c) for op, c in sorted(per_operator.items())},
        "escaped_wrong_full": escaped,
        "cost": {"reference_calls": sum(r["reference_calls"] for r in records),
                 "smt_calls": sum(r["smt_calls"] for r in records),
                 "seconds": round(sum(r["seconds"] for r in records), 1)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--final-only", action="store_true",
                        help="only the last model contract of each case (R-final)")
    parser.add_argument("--labels", type=Path, help="adjudicated verdicts (docs/E5-Adjudication.json)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    labels = (json.loads(args.labels.read_text(encoding="utf-8"))["verdicts"]
              if args.labels else None)
    result = score(load(args.directory, final_only=args.final_only, labels=labels))
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    summary = {key: result[key] for key in ("candidates", "cases", "labels", "decision_rule")}
    summary["Structure_vs_Oracle_on_wrong"] = result["Structure_vs_Oracle_on_wrong"]
    summary["FA"] = {rung: result["rungs"][rung]["false_accept"]["rate"] for rung in RUNGS}
    summary["coverage"] = {rung: result["rungs"][rung]["coverage"]["rate"] for rung in RUNGS}
    summary["false_reject"] = {rung: result["rungs"][rung]["false_reject"]["rate"] for rung in RUNGS}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
