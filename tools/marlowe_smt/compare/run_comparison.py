#!/usr/bin/env python3
"""Run LogicGraphVerifier and the packaged SMT analyzer on one corpus."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any


COMPARE = Path(__file__).resolve().parent
CORPUS = COMPARE / "corpus"
REPO = COMPARE.parents[2]
AGENT = REPO / "marlowe_ai_agent"
SMT = REPO / "tools" / "marlowe_smt"
sys.path.insert(0, str(AGENT))
sys.path.insert(0, str(SMT))
sys.setrecursionlimit(max(sys.getrecursionlimit(), 10_000))

from marlowe_agent.logic_graph import LogicGraphVerifier  # noqa: E402
from marlowe_agent.models import ContractDraft, PartySpec  # noqa: E402
from run_smt import analyze  # noqa: E402


OUTPUT = COMPARE / "results.csv"
FIELDS = [
    "name", "source", "intentional_error", "logic_graph_passed",
    "logic_graph_errors", "logic_graph_warning_count", "smt_status",
    "smt_warnings", "agreement",
]


def role_names(value: Any) -> set[str]:
    names: set[str] = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            role = item.get("role_token")
            if isinstance(role, str):
                names.add(role)
            stack.extend(item.values())
    return names


def draft_for(contract: Any, override: dict[str, Any] | None) -> ContractDraft:
    if override:
        parties = [PartySpec(**party) for party in override.get("parties", [])]
        amount = override.get("amount")
        deposit_timeout = override.get("deposit_timeout")
        decision_timeout = override.get("decision_timeout")
    else:
        parties = [PartySpec(role=name, name=name) for name in sorted(role_names(contract))]
        amount = None
        deposit_timeout = None
        decision_timeout = None
    return ContractDraft(
        original_prompt="Stage 0.8 comparison", intent="comparison fixture",
        parties=parties, amount=amount, deposit_timeout=deposit_timeout,
        decision_timeout=decision_timeout, marlowe_contract=contract,
    )


def compact_logic_errors(errors: list[str]) -> list[str]:
    mappings = (
        ("Deposit phải > 0", "NonPositiveDeposit"),
        ("Pay phải > 0", "NonPositivePay"),
        ("vượt số dư", "PartialPay"),
        ("action trùng hệt", "DuplicateAction"),
        ("khoảng Choice cùng ID chồng lấn", "OverlappingChoiceBounds"),
        ("chưa được Let định nghĩa", "UndefinedUseValue"),
        ("không có trong draft.parties", "DraftPartyMismatch"),
        ("merkleized_then", "UnsupportedMerkleizedCase"),
        ("thiếu field 'then'", "UnsupportedMerkleizedCase"),
    )
    result: list[str] = []
    for error in errors:
        kind = next((label for fragment, label in mappings if fragment in error), "ValidationError")
        if kind not in result:
            result.append(kind)
    return result


def agreement(intentional_error: str, logic_errors: list[str], smt: dict[str, Any]) -> str:
    if intentional_error == "draft_consistency":
        return "not_applicable"
    logic_catches = bool(logic_errors)
    smt_catches = smt.get("status") == "Counterexample" and bool(smt.get("warnings"))
    if logic_catches and smt_catches:
        return "both_catch"
    if logic_catches:
        return "only_logic_graph"
    if smt_catches:
        return "only_smt"
    return "neither"


def run_case(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = json.loads((CORPUS / item["file"]).read_text(encoding="utf-8"))
    draft = draft_for(contract, item.get("draft"))
    logic = LogicGraphVerifier().verify(contract, draft)
    request: Any = contract
    if "state" in item:
        request = {"contract": contract, "state": item["state"]}
    smt = analyze(request, hard_timeout_seconds=90, solver_timeout_ms=60_000)
    compact_errors = compact_logic_errors(logic.errors)
    warning_types = [warning["type"] for warning in smt.get("warnings", [])]
    row = {
        "name": item["name"], "source": item["source"],
        "intentional_error": item.get("intentional_error", ""),
        "logic_graph_passed": str(logic.passed).lower(),
        "logic_graph_errors": "|".join(compact_errors),
        "logic_graph_warning_count": len(logic.warnings),
        "smt_status": smt.get("status", ""),
        "smt_warnings": "|".join(warning_types),
        "agreement": agreement(item.get("intentional_error", ""), logic.errors, smt),
    }
    logic_output = logic.to_dict()
    graph = logic_output.pop("graph")
    logic_output["graph_nodes"] = len(graph.get("nodes", []))
    logic_output["graph_edges"] = len(graph.get("edges", []))
    detail = {
        "name": item["name"], "source": item["source"],
        "intentional_error": item.get("intentional_error", ""),
        "logic_graph": logic_output, "smt": smt, "row": row,
    }
    return row, detail


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=[], help="run only an exact corpus case name")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    manifest = json.loads((CORPUS / "MANIFEST.json").read_text(encoding="utf-8"))
    selected = [item for item in manifest if not args.only or item["name"] in args.only]
    missing = set(args.only) - {item["name"] for item in selected}
    if missing:
        raise SystemExit(f"unknown case(s): {sorted(missing)}")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(selected, start=1):
        row, detail = run_case(item)
        rows.append(row)
        print(json.dumps(detail, ensure_ascii=False, separators=(",", ":")), flush=True)
        print(f"progress {index}/{len(selected)}", file=sys.stderr, flush=True)
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
