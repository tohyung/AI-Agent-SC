"""Export or check dataset/rq2_variants.jsonl: every RQ2 (E5) candidate with its contract and label.

RQ2 does not use hand-written cases. Each candidate is a deterministic edit of a dataset v2 reference
contract (`research.experiments.gate_mutants.variants`: the reference itself, then 17 operators applied
at every matching site). The truth label comes from comparing behaviour with the reference
(`gate_labels`), not from the operator's name; the gate decisions come from the frozen E5 runs.

    python -m dataset.rq2_variants --export   # needs the local runs/e5 records (not in git)
    python -m dataset.rq2_variants --check    # regenerates every contract from dataset/cases.jsonl

`--check` needs no run data: it rebuilds each contract from the reference and compares it with the file,
and checks the label counts of the published results (dev 948 wrong / 344 right, test 686 / 281).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "rq2_variants.jsonl"
RUNS = {"dev": ROOT / "runs/e5/E5-Round2-Variants", "test": ROOT / "runs/e5/E5-Freeze-Holdout-Variants"}
EXPECTED = {"dev": {"cases": 56, "WRONG": 948, "RIGHT": 344}, "test": {"cases": 43, "WRONG": 686, "RIGHT": 281}}
GATES = ("Structure", "Lint", "SMT", "Alignment", "Scenario", "Oracle")


def contract_sha256(contract: Any) -> str:
    """The hash gate_eval stored for each candidate."""
    return hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()


def regenerate() -> dict[str, Any]:
    """Every candidate contract, keyed by candidate id, rebuilt from the v2 references."""
    from research.experiments.gate_eval import EXCLUDED, cases, mutant_candidates

    contracts = {}
    for index, case in enumerate(cases(), start=1):
        if index in EXCLUDED:
            continue
        for candidate in mutant_candidates(case, index):
            contracts[candidate.candidate_id] = candidate.contract
    return contracts


def export() -> str:
    """Return the text of rq2_variants.jsonl, built from the frozen run records."""
    data = [json.loads(line) for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    contracts = regenerate()
    lines = []
    for split, run_dir in RUNS.items():
        records = [json.loads(path.read_text(encoding="utf-8")) for path in run_dir.glob("*.json")]
        for record in sorted(records, key=lambda r: (r["case_index"], r["candidate_id"])):
            contract = contracts[record["candidate_id"]]
            if contract_sha256(contract) != record["contract_sha256"]:
                raise ValueError(f"{record['candidate_id']}: regenerated contract differs from the run")
            case = data[record["case_index"] - 1]
            truth = record["label"]
            lines.append(json.dumps({
                "split": split, "case_index": record["case_index"], "case_id": case["id"],
                "family": record["case_type"], "info_mode": record["info_mode"],
                "candidate_id": record["candidate_id"], "operator": record["operator"],
                "operator_intent": record["operator_intent"], "label": truth["label"],
                "label_reason": truth.get("reason"), "timing_note": truth.get("timing_note"),
                "decisions": {gate: record["decisions"][gate] for gate in GATES},
                "contract_sha256": record["contract_sha256"], "contract": contract,
            }, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + "\n"


def check() -> list[str]:
    """Return problems: contracts that no longer regenerate, or counts that differ from the results."""
    if not OUT.exists():
        return ["dataset/rq2_variants.jsonl is missing; run python -m dataset.rq2_variants --export"]
    rows = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    contracts = regenerate()
    problems = []
    for row in rows:
        contract = contracts.get(row["candidate_id"])
        if contract != row["contract"] or contract_sha256(row["contract"]) != row["contract_sha256"]:
            problems.append(f"{row['candidate_id']}: contract does not regenerate from its reference")
    for split, expected in EXPECTED.items():
        part = [row for row in rows if row["split"] == split]
        found = {"cases": len({row["case_index"] for row in part}),
                 "WRONG": sum(row["label"] == "WRONG" for row in part),
                 "RIGHT": sum(row["label"] == "RIGHT" for row in part)}
        if found != expected:
            problems.append(f"{split}: found {found}, the results report {expected}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export", action="store_true", help="write the file from runs/e5")
    group.add_argument("--check", action="store_true", help="check the file against the references")
    args = parser.parse_args(argv)
    if args.export:
        text = export()
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT.relative_to(ROOT)}: {text.count(chr(10))} candidates")
    problems = check()
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("ok: every contract regenerates from its reference; label counts match the results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
