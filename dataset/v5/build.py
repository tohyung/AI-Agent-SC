"""Build and check dataset v5: python -m dataset.v5.build [--write] [--partial]

The checks are the style (V-*) and accuracy (C-*) standards of docs/E7-Dataset-v5-Design.md, plus
v3's structural checks (valid reference, scenarios on the simulator, coverage minimums).
--partial skips the whole-dataset distribution checks, for checking the parts while writing.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from dataset.v3.build import (BANNED, MIN_FEATURES, MIN_PHENOMENA, TARGET_MODES, TARGETS_DISTRIBUTION,
                              coverage, features, sim_check)
from dataset.v3.builders import add, before, build, dep, lovelace, ms, scenario
from dataset.v4.build import parties
from research.analysis.marlowe_validator import validate_contract
from research.formalization.number_words import digits_for_words
from research.formalization.party_names import fold_name

HERE = Path(__file__).resolve().parent
OUT = HERE / "cases.jsonl"
V3 = HERE.parent / "v3" / "cases.jsonl"
V2 = HERE.parent / "cases.jsonl"
# Marlowe or system terms a user would not write ("when", "close" are plain English words).
JARGON = re.compile(r"\b(notify|timeout|role token|posix|slot|lovelace|choice_owner|deposit_deadline)\b",
                    re.IGNORECASE)
REGISTER_MIN = {"chat": 40, "bullets": 20, "terse": 15, "document": 8}
BEHAVIOR = {"complete": {"converge"}, "missing": {"ask_then_converge"}, "ambiguous": {"ask_then_converge"},
            "conflict": {"flag_conflict_then_converge", "converge"},
            "extra_unsupported": {"converge_and_decline_extra"}, "infeasible": {"reject_unsupported"}}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
AMOUNT_KEYS = {"amount", "price", "principal", "repay", "amount_a", "amount_b", "collateral",
               "max_deduction", "cap", "keeper_share", "on_timeout"}


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _jaccard(first: str, second: str) -> float:
    a, b = _words(first), _words(second)
    return len(a & b) / max(1, len(a | b))


def _amounts(spec: Any, key: str | None = None) -> set[str]:
    found: set[str] = set()
    if isinstance(spec, dict):
        for name, value in spec.items():
            if name in {"roles", "tokens", "parties", "reason"}:
                continue
            found |= _amounts(value, name)
    elif isinstance(spec, list):
        for item in spec:
            found |= _amounts(item, key)
    elif key in AMOUNT_KEYS and type(spec) in {int, float, str} and not isinstance(spec, bool):
        text = str(spec)
        if re.fullmatch(r"\d+(\.\d+)?", text) and float(text) > 0:
            found.add(text)
    return found


def _instants(spec: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(spec, dict):
        for value in spec.values():
            found |= _instants(value)
    elif isinstance(spec, list):
        for item in spec:
            found |= _instants(item)
    elif isinstance(spec, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", spec):
        found.add(spec)
    return found


def _numbers_in(text: str) -> set[str]:
    texts = [text, digits_for_words(text), re.sub(r"(?<=\d)[.,  ](?=\d{3}(?!\d))", "", text),
             re.sub(r"(?<=\d),(?=\d{1,2}(?!\d))", ".", text)]
    found = set()
    for item in texts:
        for match in re.findall(r"\d+(?:\.\d+)?", item):
            found.add(match)
            if "." in match:
                found.add(match.rstrip("0").rstrip("."))
    return found


def _date_stated(instant: str, text: str) -> bool:
    moment = datetime.fromisoformat(instant)
    d, m, y = moment.day, moment.month, moment.year
    lower = text.lower()
    patterns = [rf"(?<!\d)0?{d}/0?{m}(?!\d)", rf"{y}-{m:02d}-{d:02d}", rf"(?<!\d){m:02d}-{d:02d}(?!\d)",
                rf"\b{MONTHS[m - 1]}\w*\.?\s+{d}(?!\d)", rf"(?<!\d){d}(?:st|nd|rd|th)?\s+{MONTHS[m - 1]}",
                rf"ngày\s+0?{d}\s+tháng\s+0?{m}(?!\d)", rf"mùng\s+0?{d}(?!\d)"]
    return any(re.search(pattern, lower) for pattern in patterns)


ZONE_WORDS = {7: r"giờ VN|gio VN|UTC\+7|Vietnam time|giờ Việt Nam", 0: r"\bUTC\b(?![ \t]*[+-][ \t]*\d)",
              2: r"UTC\+2"}


def _time_problems(instant: str, text: str) -> list[str]:
    """The hour of a deadline and its time zone must be stated somewhere in `text`."""
    moment = datetime.fromisoformat(instant)
    hour, minute = moment.hour, moment.minute
    clock = hour % 12 or 12
    patterns = [rf"(?<!\d){hour:02d}:{minute:02d}", rf"(?<!\d){hour}:{minute:02d}", rf"(?<!\d){hour}h(?!\d)",
                rf"(?<!\d){clock}(?::{minute:02d})?\s*(?:am|pm|giờ|h)\b", rf"(?<!\d){hour}\s*giờ"]
    problems = []
    if not any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
        problems.append(f"time {hour:02d}:{minute:02d} of {instant[:10]} not stated")
    offset = int(moment.utcoffset().total_seconds() // 3600)
    if offset in ZONE_WORDS and not re.search(ZONE_WORDS[offset], text, re.IGNORECASE):
        problems.append(f"time zone UTC{offset:+d} of {instant[:10]} not stated")
    return problems


def check_case(case: dict[str, Any], v3_names: set[str], old_prompts: list[str]) -> list[str]:
    problems = []
    cid = case["id"]
    prompt = case["prompt"]
    facts = " ".join(item["answer"] for item in case.get("fact_sheet", []))
    mode = case["info_mode"]
    if case["expected_behavior"] not in BEHAVIOR[mode]:
        problems.append(f"{cid}: behaviour {case['expected_behavior']} does not fit mode {mode}")
    if case.get("register") not in REGISTER_MIN:
        problems.append(f"{cid}: register missing")
    for pattern in BANNED:
        if re.search(pattern, prompt, flags=re.IGNORECASE | re.MULTILINE):
            problems.append(f"{cid}: V-1 storytelling opener /{pattern}/")
    if re.match(r"\s*(xin chào|chào bạn|hello|hi there|dear)\b", prompt, re.IGNORECASE):
        problems.append(f"{cid}: V-1 greeting opener")
    for match in JARGON.finditer(prompt):
        word = match.group(1).lower()
        if word == "lovelace" and "lovelace_units" in case["phenomena"]:
            continue
        problems.append(f"{cid}: V-2 jargon '{match.group(1)}'")
    for old in old_prompts:
        if _jaccard(prompt, old) > 0.5:
            problems.append(f"{cid}: V-6 too close to an older prompt")
            break
    spec = case.get("spec", {})
    roles = spec.get("roles", {})
    for name in roles.values():
        if fold_name(name) in v3_names:
            problems.append(f"{cid}: V-7 role name '{name}' is used in v3")
    if case["family"] == "infeasible":
        return problems
    where = prompt if mode == "complete" else prompt + " " + facts
    derived = {str(item) for item in case.get("derived", [])}
    for name in roles.values():
        if name.casefold() not in where.casefold():
            problems.append(f"{cid}: C-2 role '{name}' not stated")
    stated_numbers = _numbers_in(where)
    for amount in _amounts(spec):
        if amount not in stated_numbers and amount not in derived:
            problems.append(f"{cid}: C-3 amount {amount} not stated")
    for instant in _instants(spec):
        if not _date_stated(instant, where) and instant[:10] not in derived:
            problems.append(f"{cid}: C-3 date {instant[:10]} not stated")
        problems += [f"{cid}: C-3 {item}" for item in _time_problems(instant, where)]
    if mode in {"missing", "ambiguous"}:
        only_facts = (any(name.casefold() not in prompt.casefold() for name in roles.values())
                      or any(not _date_stated(instant, prompt) for instant in _instants(spec))
                      or any(amount not in _numbers_in(prompt) for amount in _amounts(spec))
                      or bool(case.get("fact_sheet")))
        if not only_facts or not case.get("fact_sheet"):
            problems.append(f"{cid}: C-5 nothing is left to the fact sheet")
    if mode == "extra_unsupported" and not re.search(r"\bbỏ\b|\bdrop", facts, re.IGNORECASE):
        problems.append(f"{cid}: C-6 no permission to drop the extra part")
    return problems


def first_come_extra(case: dict[str, Any]) -> list[dict[str, Any]]:
    """C-7: a scenario for every buyer but the last (the builder already tests the last)."""
    spec = case["spec"]
    seller, buyers = spec["roles"]["seller"], [spec["roles"][key] for key in spec["buyers"]]
    price, until = lovelace(spec["price"]), ms(spec["offer_until"])
    got: dict[str, dict[str, int]] = {}
    add(got, seller, "", price)
    return [scenario(f"buyer_{number}_first", [dep(buyer, price, "", before(until))], deepcopy(got))
            for number, buyer in enumerate(buyers[:-1], 1)]


def load_parts() -> list[dict[str, Any]]:
    import importlib

    cases = []
    for part in ("a", "b", "c", "d"):
        try:
            module = importlib.import_module(f"dataset.v5.authoring_{part}")
        except ModuleNotFoundError:
            continue
        cases += module.CASES
    return cases


def assemble() -> tuple[list[dict[str, Any]], list[str]]:
    v3 = [json.loads(line) for line in V3.read_text(encoding="utf-8").splitlines()]
    v3_names = {fold_name(name) for case in v3 for name in case["spec"].get("roles", {}).values()}
    old_prompts = [case["prompt"] for case in v3] + [
        json.loads(line)["prompt"] for line in V2.read_text(encoding="utf-8").splitlines()]
    cases, problems = [], []
    for raw in load_parts():
        case = deepcopy(raw)
        problems += check_case(case, v3_names, old_prompts)
        if case["family"] == "infeasible":
            case["reference_contract"], case["checks"] = None, {"scenarios": []}
        else:
            try:
                contract, scenarios = build(case["family"], case["spec"])
            except Exception as exc:  # noqa: BLE001 - report every broken spec
                problems.append(f"{case['id']}: build failed: {type(exc).__name__}: {exc}")
                continue
            if case["family"] == "first_come":
                scenarios += first_come_extra(case)
            errors = validate_contract(contract)
            if errors:
                problems.append(f"{case['id']}: invalid contract: {errors[:2]}")
            for item in scenarios:
                issue = sim_check(contract, item)
                if issue:
                    problems.append(f"{case['id']} / {item['name']}: {issue}")
            case["reference_contract"], case["checks"] = contract, {"scenarios": scenarios}
            case["marlowe_features"] = sorted(features(contract))
        for token in case.get("spec", {}).get("tokens", {}).values():
            if not re.fullmatch(r"[0-9a-f]{56}", token["policy"]):
                problems.append(f"{case['id']}: policy id is not 56 hex characters")
        case["spec"]["parties"] = parties(case) if case.get("spec", {}).get("roles") else {}
        case["split"] = "eval"
        cases.append(case)
    ids = Counter(case["id"] for case in cases)
    problems += [f"duplicate id {item}" for item, count in ids.items() if count > 1]
    for index, case in enumerate(cases):
        for other in cases[index + 1:]:
            if _jaccard(case["prompt"], other["prompt"]) > 0.6:
                problems.append(f"V-6 near-duplicate prompts {case['id']} / {other['id']}")
    return cases, problems


def style_report(cases: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    registers = Counter(case.get("register") for case in cases)
    lengths = [len(case["prompt"].split()) for case in cases]
    short, long_ = sum(1 for n in lengths if n < 25), sum(1 for n in lengths if n > 80)
    gaps = [f"V-3 register {name}: {registers[name]} < {need}" for name, need in REGISTER_MIN.items()
            if registers[name] < need]
    if short < 15:
        gaps.append(f"V-4 short prompts {short} < 15")
    if long_ < 10:
        gaps.append(f"V-4 long prompts {long_} < 10")
    return {"registers": dict(registers), "short_prompts": short, "long_prompts": long_}, gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    cases, problems = assemble()
    report, gaps = coverage(cases)
    style, style_gaps = style_report(cases)
    report["style"] = style
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if args.partial:
        gaps, style_gaps = [], []
    families = Counter((case["family"], case["language"]) for case in cases)
    v3 = Counter((json.loads(line)["family"], json.loads(line)["language"])
                 for line in V3.read_text(encoding="utf-8").splitlines())
    if not args.partial and families != v3:
        gaps.append(f"family/language counts differ from v3: {dict(families - v3)} / {dict(v3 - families)}")
    for line in problems + gaps + style_gaps:
        print("PROBLEM:", line)
    if problems or gaps or style_gaps:
        return 1
    if args.write:
        text = "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases)
        OUT.write_text(text, encoding="utf-8")
        print("wrote", OUT, "sha256", hashlib.sha256(text.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
