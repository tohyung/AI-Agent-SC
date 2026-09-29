"""Offline replay of old Logic Graph and unwired Node 3 policy decisions."""

from __future__ import annotations

import argparse
import csv
from dataclasses import fields
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any

from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.models import ContractDraft, PartySpec
from marlowe_agent.node3_policy import Node3Result, StructuredWarning


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parent
AUDIT = HERE / "audit"
SMT_WRAPPER = REPO / "tools" / "marlowe_smt" / "run_smt.py"
DEFAULT_OUTPUT = HERE / "node3-replay-results.csv"
FIELDS = [
    "case_id", "audit_file", "ground_truth", "old_pass", "new_decision",
    "semantic_status", "smt_seconds", "old_errors", "new_errors",
    "disagreement_type",
]


def _draft(raw: dict[str, Any] | None, contract: Any) -> ContractDraft | None:
    if raw is None:
        return None
    allowed = {item.name for item in fields(ContractDraft)}
    values = {key: value for key, value in raw.items() if key in allowed}
    values["parties"] = [PartySpec(**party) for party in raw.get("parties", [])]
    values["marlowe_contract"] = contract
    return ContractDraft(**values)


def _run_smt(contract: Any) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    process = subprocess.run(
        [sys.executable, str(SMT_WRAPPER), "--hard-timeout", "90", "--solver-timeout-ms", "60000"],
        input=json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
        text=True, capture_output=True, check=False, timeout=95, cwd=REPO,
    )
    elapsed = perf_counter() - started
    try:
        output = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        output = {
            "status": "Indeterminate", "warnings": [], "counterexample": None,
            "analysis_notes": [f"SMT wrapper emitted invalid JSON: {error}"],
        }
    if process.stderr:
        output.setdefault("analysis_notes", []).append(
            "SMT wrapper wrote stderr; raw stderr is intentionally excluded from policy fingerprints."
        )
    return output, elapsed


def _warning(raw: dict[str, Any]) -> StructuredWarning:
    return StructuredWarning(
        str(raw["type"]), {key: value for key, value in raw.items() if key != "type"},
    )


def _truth(record: dict[str, Any]) -> bool | None:
    """Use evaluator.py's persisted ground-truth result, never status/converged."""
    value = (record.get("evaluation") or {}).get("strict_correct")
    return value if type(value) is bool else None


def _disagreement(truth: bool | None, old_pass: bool | None, decision: str) -> str:
    if truth is None or old_pass is None:
        return "ground_truth_unavailable"
    if decision == "inconclusive":
        return "inconclusive"
    new_pass = decision == "pass"
    if old_pass != new_pass:
        return "old_only_pass" if old_pass else "new_only_pass"
    return "both_correct" if old_pass == truth else "both_wrong"


def replay(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    record = json.loads(path.read_text(encoding="utf-8"))
    contract = record.get("contract")
    truth = _truth(record)
    if contract in (None, {}):
        node3 = Node3Result(
            [], [], "unavailable", [], None,
            ["Audit record không có contract để replay."], None, contract=contract,
        )
        old_pass: bool | None = None
        old_errors: list[str] = []
        smt_seconds: float | None = None
    else:
        draft = _draft(record.get("draft"), contract)
        logic = LogicGraphVerifier().verify(contract, draft)
        old_pass = logic.passed
        old_errors = logic.errors
        smt, smt_seconds = _run_smt(contract)
        node3 = Node3Result(
            lint_errors=list(logic.errors),
            lint_warnings=list(logic.warnings),
            semantic_status=str(smt.get("status", "unavailable")).lower(),
            semantic_warnings=[_warning(item) for item in smt.get("warnings", [])],
            counterexample=smt.get("counterexample"),
            analysis_notes=list(smt.get("analysis_notes", [])),
            smt_elapsed_seconds=smt_seconds,
            contract=contract,
        )
    disagreement = _disagreement(truth, old_pass, node3.decision)
    row = {
        "case_id": record.get("case_id", path.stem),
        "audit_file": path.name,
        "ground_truth": "" if truth is None else str(truth).lower(),
        "old_pass": "" if old_pass is None else str(old_pass).lower(),
        "new_decision": node3.decision,
        "semantic_status": node3.semantic_status,
        "smt_seconds": "" if smt_seconds is None else f"{smt_seconds:.6f}",
        "old_errors": json.dumps(old_errors, ensure_ascii=False, separators=(",", ":")),
        "new_errors": json.dumps(node3.errors, ensure_ascii=False, separators=(",", ":")),
        "disagreement_type": disagreement,
    }
    detail = {
        "case_id": row["case_id"], "ground_truth": truth,
        "old_pass": old_pass, "new_decision": node3.decision,
        "semantic_status": node3.semantic_status,
        "analysis_notes": node3.analysis_notes,
        "disagreement_type": disagreement,
    }
    return row, detail


def _confusion(rows: list[dict[str, Any]], prediction: str) -> dict[str, int]:
    result = {"true_accept": 0, "false_accept": 0, "true_reject": 0, "false_reject": 0}
    for row in rows:
        if row["ground_truth"] not in {"true", "false"}:
            continue
        if prediction == "new_decision" and row[prediction] == "inconclusive":
            continue
        accepted = row[prediction] == ("pass" if prediction == "new_decision" else "true")
        truth = row["ground_truth"] == "true"
        key = (
            "true_accept" if accepted and truth else
            "false_accept" if accepted else
            "false_reject" if truth else "true_reject"
        )
        result[key] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for path in sorted(AUDIT.glob("*-full.json")):
        row, detail = replay(path)
        rows.append(row)
        print(json.dumps(detail, ensure_ascii=False, separators=(",", ":")), flush=True)
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "logic_graph": _confusion(rows, "old_pass"),
        "node3_policy": _confusion(rows, "new_decision"),
        "cross": {
            label: sum(row["disagreement_type"] == label for row in rows)
            for label in ("both_correct", "old_only_pass", "new_only_pass", "both_wrong")
        },
        "inconclusive": [row["audit_file"] for row in rows if row["new_decision"] == "inconclusive"],
        "ground_truth_unavailable": [
            row["audit_file"] for row in rows if row["ground_truth"] == ""
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
