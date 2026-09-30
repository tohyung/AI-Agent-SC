"""Offline replay of old Logic Graph and live Node 3 decisions."""

from __future__ import annotations

import argparse
import csv
from dataclasses import fields
import hashlib
import json
from pathlib import Path
from typing import Any

from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.models import ContractDraft, PartySpec
from marlowe_agent.node3_policy import Node3Result
from marlowe_agent.nodes import Node3VerificationNode

from .cases import Case, load_cases
from .config import DATASET
from .evaluator import evaluate


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
AUDIT = HERE / "audit"
DEFAULT_OUTPUT = HERE / "node3-replay-results.csv"
FIELDS = [
    "case_id", "audit_file", "ground_truth", "persisted_ground_truth",
    "ground_truth_changed", "current_scenario_accuracy", "current_overall_accuracy",
    "choice_name_fallback_count", "old_pass", "new_decision",
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


def _persisted_truth(record: dict[str, Any]) -> bool | None:
    """Retain the historical label only for evaluator-drift telemetry."""
    value = (record.get("evaluation") or {}).get("strict_correct")
    return value if type(value) is bool else None


def _case_index() -> dict[str, Case]:
    cases_by_id: dict[str, Case] = {}
    for case in load_cases():
        if case.id in cases_by_id:
            raise ValueError(f"Duplicate case ID in current dataset {DATASET}: {case.id}")
        cases_by_id[case.id] = case
    return cases_by_id


def _disagreement(truth: bool | None, old_pass: bool | None, decision: str) -> str:
    if truth is None or old_pass is None:
        return "ground_truth_unavailable"
    if decision == "inconclusive":
        return "inconclusive"
    new_pass = decision == "pass"
    old_correct = old_pass == truth
    new_correct = new_pass == truth
    if old_correct and new_correct:
        return "both_correct"
    if old_correct:
        return "old_only_correct"
    if new_correct:
        return "new_only_correct"
    return "both_wrong"


def replay(path: Path, cases_by_id: dict[str, Case],
           backend: Any | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    record = json.loads(path.read_text(encoding="utf-8"))
    contract = record.get("contract")
    case_id = record.get("case_id", path.stem)
    persisted_truth = _persisted_truth(record)
    current_evaluation: dict[str, Any] | None = None
    if contract in (None, {}):
        node3 = Node3Result(
            [], [], "unavailable", [], None,
            ["Audit record không có contract để replay."], None, contract=contract,
        )
        old_pass: bool | None = None
        old_errors: list[str] = []
        smt_seconds: float | None = None
    else:
        if case_id not in cases_by_id:
            raise ValueError(f"Current dataset {DATASET} has no case for {path.name}: {case_id}")
        current_evaluation = evaluate(
            cases_by_id[case_id], contract, status=record.get("status", "done"),
        )
        draft = _draft(record.get("draft"), contract)
        logic = LogicGraphVerifier().verify(contract, draft)
        old_pass = logic.passed
        old_errors = logic.errors
        node3 = Node3VerificationNode(backend).run(contract, draft)
        smt_seconds = node3.smt_elapsed_seconds
    truth = current_evaluation["strict_correct"] if current_evaluation is not None else None
    changed = (persisted_truth != truth
               if type(persisted_truth) is bool and type(truth) is bool else None)
    disagreement = _disagreement(truth, old_pass, node3.decision)
    row = {
        "case_id": case_id,
        "audit_file": path.name,
        "ground_truth": "" if truth is None else str(truth).lower(),
        "persisted_ground_truth": "" if persisted_truth is None else str(persisted_truth).lower(),
        "ground_truth_changed": "" if changed is None else str(changed).lower(),
        "current_scenario_accuracy": (
            "" if current_evaluation is None or current_evaluation.get("scenario_accuracy") is None
            else current_evaluation["scenario_accuracy"]
        ),
        "current_overall_accuracy": (
            "" if current_evaluation is None or current_evaluation.get("overall_accuracy") is None
            else current_evaluation["overall_accuracy"]
        ),
        "choice_name_fallback_count": (
            "" if current_evaluation is None else
            current_evaluation["diagnostics"].get("choice_name_fallback_count", 0)
        ),
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
        "persisted_ground_truth": persisted_truth, "ground_truth_changed": changed,
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
    cases_by_id = _case_index()
    rows: list[dict[str, Any]] = []
    for path in sorted(AUDIT.glob("*-full.json")):
        row, detail = replay(path, cases_by_id)
        rows.append(row)
        print(json.dumps(detail, ensure_ascii=False, separators=(",", ":")), flush=True)
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "dataset_path": str(DATASET),
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "logic_graph": _confusion(rows, "old_pass"),
        "node3_policy": _confusion(rows, "new_decision"),
        "cross": {
            label: sum(row["disagreement_type"] == label for row in rows)
            for label in ("both_correct", "old_only_correct", "new_only_correct", "both_wrong")
        },
        "inconclusive": [row["audit_file"] for row in rows if row["new_decision"] == "inconclusive"],
        "ground_truth_unavailable": [
            row["audit_file"] for row in rows if row["ground_truth"] == ""
        ],
        "ground_truth_drift": [
            {"audit_file": row["audit_file"],
             "persisted": row["persisted_ground_truth"] == "true",
             "current": row["ground_truth"] == "true"}
            for row in rows if row["ground_truth_changed"] == "true"
        ],
    }
    summary["ground_truth_drift_count"] = len(summary["ground_truth_drift"])
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
