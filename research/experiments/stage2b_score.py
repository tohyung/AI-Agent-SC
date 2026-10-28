"""Score one evaluation arm (M1-M4) after its run; evaluator fields stay here.

Fact ground truth is what the dataset reference contract actually uses: role
tokens, integer deposit/pay amounts and integer timeouts. Template parameters
are not used directly because every case carries all of them, used or not.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from research.experiments.online_tuning_batch01 import DATASET
from research.stage2b.intent_spec import DEADLINE_KINDS, PARTY_KINDS

BACKED = {"explicit", "derived", "user_confirmed"}
TIME_KINDS = DEADLINE_KINDS | {"payment_release_time_ms"}
DAY_MS = 86_400_000
MONTHS = {name: index for index, name in enumerate((
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december"), 1)}
COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
               "seven": 7, "eight": 8, "nine": 9, "ten": 10,
               "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6,
               "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
RELATIVE = re.compile(
    r"(?<!\w)(\d+|" + "|".join(COUNT_WORDS) + r")\s+(ngày|days?|tuần|weeks?)\s+"
    r"(?:sau|after|kể từ|from)", re.IGNORECASE)
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


def _utc_date(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).date()


def cited_dates(text: str) -> set[date]:
    """Calendar dates written in a span; time of day and timezone are ignored."""
    found: set[date] = set()
    candidates = [(int(y), int(m), int(d)) for d, m, y in
                  re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", text)]
    candidates += [(int(y), int(m), int(d)) for y, m, d in
                   re.findall(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", text)]
    candidates += [(int(y), int(m), int(d)) for d, m, y in re.findall(
        r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", text, re.IGNORECASE)]
    month = "|".join(MONTHS)
    candidates += [(int(y), MONTHS[m.lower()], int(d)) for d, m, y in re.findall(
        rf"(?<!\d)(\d{{1,2}})\s+({month})\s+(\d{{4}})", text, re.IGNORECASE)]
    candidates += [(int(y), MONTHS[m.lower()], int(d)) for m, d, y in re.findall(
        rf"({month})\s+(\d{{1,2}}),?\s+(\d{{4}})", text, re.IGNORECASE)]
    for year, month_number, day in candidates:
        try:
            found.add(date(year, month_number, day))
        except ValueError:
            continue
    return found


def relative_days(text: str) -> set[int]:
    """Offsets such as "7 ngày sau" or "two weeks after", in days."""
    found: set[int] = set()
    for count, unit in ((match.group(1), match.group(2)) for match in RELATIVE.finditer(text)):
        number = int(count) if count.isdigit() else COUNT_WORDS[count.lower()]
        found.add(number * (7 if unit.lower().startswith(("tuần", "week")) else 1))
    return found


def identified_deadlines(core: dict[str, Any], reference: set[int]) -> tuple[int, int]:
    """Adjusted M3: (reference deadlines identified, extracted deadline claims matching one).

    A deadline counts when an extracted time claim, resolved or not, cites the
    reference deadline's calendar date, carries a value on that UTC date, or
    cites an "N days after" phrase equal to the gap from another reference
    deadline. The dataset's unstated 12:00 UTC time is therefore not required.
    """
    reference_dates = {_utc_date(ms): ms for ms in reference}
    identified: set[int] = set()
    matching_claims = 0
    for claim in core.get("claims") or []:
        if not isinstance(claim, dict) or claim.get("kind") not in TIME_KINDS:
            continue
        if claim.get("status") not in BACKED | {"unresolved"}:
            continue
        text = " ".join(item.get("span", "") for item in claim.get("evidence") or []
                        if isinstance(item, dict) and isinstance(item.get("span"), str))
        dates = cited_dates(text)
        if type(claim.get("value")) is int:
            dates.add(_utc_date(claim["value"]))
        hits = {reference_dates[day] for day in dates if day in reference_dates}
        for offset in relative_days(text):
            hits |= {later for later in reference for earlier in reference
                     if later - earlier == offset * DAY_MS}
        if hits:
            matching_claims += 1
            identified |= hits
    return len(identified), matching_claims


def time_only_open(record: dict[str, Any]) -> bool:
    """Adjusted M4: a complete case may ask only about deadline time or timezone."""
    core = record.get("semantic_core") or {}
    claims = [claim for claim in core.get("claims") or [] if isinstance(claim, dict)]
    unresolved = [claim for claim in claims if claim.get("status") == "unresolved"
                  and claim.get("criticality") == "financial"]
    return (record.get("predicted_resolution") == "clarification_required"
            and bool(unresolved) and all(claim.get("kind") in TIME_KINDS for claim in unresolved)
            and not any(claim.get("status") == "conflicted" for claim in claims)
            # Side context is not an open question; unrepresented behavior is.
            and not any(isinstance(item, dict) and item.get("reason") != "irrelevant_context"
                        for item in core.get("unscored_observations") or []))


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
        identified, matching = identified_deadlines(core, expected["deadlines"])
        decision_correct = (record.get("predicted_resolution")
                            in EXPECTED_DECISION[case["info_mode"]])
        row = {
            "case_index": record["case_index"], "case_id": record["case_id"],
            "info_mode": case["info_mode"],
            "first_pass_valid": record.get("first_pass_valid") is True,
            "final_valid": record.get("final_valid") is True,
            "physical_calls": record["physical_calls"],
            "decision_correct": decision_correct,
            "decision_correct_adjusted": decision_correct or (
                case["info_mode"] == "complete" and time_only_open(record)),
            "facts": {kind: {"expected": len(expected[kind]), "found": len(found[kind]),
                             "matched": len(expected[kind] & found[kind])}
                      for kind in FACT_KINDS},
            "deadlines_adjusted": {
                "expected": len(expected["deadlines"]), "identified": identified,
                "claims": sum(1 for claim in core.get("claims") or []
                              if isinstance(claim, dict) and claim.get("kind") in TIME_KINDS
                              and claim.get("status") in BACKED | {"unresolved"}),
                "matching_claims": matching},
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
        # Disclosed adjustments (protocol, 2026-10-29): the dataset's reference
        # deadlines use an unstated 12:00 UTC time that no prompt gives.
        "adjusted": {
            "M3_deadlines_identified": {
                "recall": _ratio(sum(row["deadlines_adjusted"]["identified"] for row in complete),
                                 sum(row["deadlines_adjusted"]["expected"] for row in complete)),
                "precision": _ratio(
                    sum(row["deadlines_adjusted"]["matching_claims"] for row in complete),
                    sum(row["deadlines_adjusted"]["claims"] for row in complete)),
            },
            "M4_decision_correct": _ratio(
                sum(row["decision_correct_adjusted"] for row in rows), total),
            "M4_complete": _ratio(sum(row["decision_correct_adjusted"] for row in complete),
                                  len(complete)),
        },
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
