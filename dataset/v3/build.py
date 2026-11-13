"""Build and validate dataset v3: python -m dataset.v3.build [--write]

Builds every reference contract and scenario from the specs in authoring_a/b, then checks:
structure, scenario outcomes on the Python simulator against the spec-derived expectations,
unique and non-duplicate prompts (also against v2), banned storytelling phrases, policy ids,
role names present in the prompt or fact sheet, and the coverage minimums of
docs/archive/E6-Dataset-Design.md. With --write, writes dataset/v3/cases.jsonl and prints its SHA-256.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from dataset.marlowe_sim import run_scenario
from dataset.v3.authoring_a import CASES as CASES_A
from dataset.v3.authoring_b import CASES as CASES_B
from dataset.v3.builders import build
from research.analysis.marlowe_validator import validate_contract

HERE = Path(__file__).resolve().parent
OUT = HERE / "cases.jsonl"
V2 = HERE.parent / "cases.jsonl"
BANNED = [r"\bở [A-ZĐ][\wÀ-ỹ ]+ đây\b", r"\bơi\b", r"\bfrom \w+ here\b", r"^\w+ (here|đây)[;,]"]
TARGETS_DISTRIBUTION = {"vi": 60, "en": 40}
TARGET_MODES = {"complete": 40, "missing": 25, "ambiguous": 10, "conflict": 10, "extra_unsupported": 5,
                "infeasible": 10}
MIN_PHENOMENA = {"first_person": 50, "time_of_day": 30, "timezone": 30, "relative_time": 25, "percentage": 10,
                 "numbers_in_words": 8, "lovelace_units": 4, "typo": 8, "self_correction": 8,
                 "ambiguous_pronoun": 6, "no_diacritics": 10, "vi_en_mix": 8, "bullet_list": 20, "terse": 15,
                 "long_document": 8}
MIN_FEATURES = {"notify": 6, "race": 10, "account_transfer": 5, "choice_value_amount": 5, "if_or_let": 12,
                "nested_when_3": 20, "parties_4": 12, "multi_token": 8, "decimal": 8}


def walk(node: Any):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def when_depth(node: Any) -> int:
    if not isinstance(node, dict):
        return 0
    if "when" in node:
        return 1 + max([when_depth(b["then"]) for b in node["when"]] + [when_depth(node["timeout_continuation"])])
    if "if" in node:
        return max(when_depth(node["then"]), when_depth(node["else"]))
    return when_depth(node.get("then"))


def features(contract: Any) -> set[str]:
    nodes = [n for n in walk(contract) if isinstance(n, dict)]
    found = set()
    if any("notify_if" in n for n in nodes):
        found.add("notify")
    if any("when" in n and len(n["when"]) > 1 for n in nodes):
        found.add("race")
    if any(isinstance(n.get("to"), dict) and "account" in n["to"] for n in nodes if "pay" in n):
        found.add("account_transfer")
    if any("pay" in n and isinstance(n["pay"], dict) for n in nodes):
        found.add("choice_value_amount")
    if any("if" in n or "let" in n for n in nodes):
        found.add("if_or_let")
    if when_depth(contract) >= 3:
        found.add("nested_when_3")
    if len({n["role_token"] for n in nodes if "role_token" in n}) >= 4:
        found.add("parties_4")
    tokens = {json.dumps(n, sort_keys=True) for n in nodes if "token_name" in n and "currency_symbol" in n}
    if len(tokens) >= 2:
        found.add("multi_token")
    ada_amounts = [n[k] for n in nodes for k in ("pay", "deposits")
                   if type(n.get(k)) is int and (n.get("token") or n.get("of_token")) == {"currency_symbol": "", "token_name": ""}]
    if any(a % 1_000_000 for a in ada_amounts):
        found.add("decimal")
    return found


def sim_check(contract: Any, scenario: dict[str, Any]) -> str | None:
    steps = deepcopy(scenario["steps"])
    out = run_scenario(contract, steps, steps[0]["time"] - 86_400_000)
    if out.get("not_evaluable"):
        return f"not evaluable: {out.get('reason')}"
    if out["input_rejected"]:
        return "an input was rejected"
    if out["partial_pay"]:
        return "partial pay"
    received = {p: {t: a for t, a in toks.items() if a} for p, toks in out["received"].items()}
    received = {p: t for p, t in received.items() if t}
    if received != scenario["received"]:
        return f"received {received} != expected {scenario['received']}"
    if out["closed"] != scenario["closed"]:
        return f"closed {out['closed']} != expected {scenario['closed']}"
    return None


def _norm(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def assemble() -> tuple[list[dict[str, Any]], list[str]]:
    cases, problems = [], []
    for raw in CASES_A + CASES_B:
        case = deepcopy(raw)
        if case["family"] == "infeasible":
            case["reference_contract"], case["checks"] = None, {"scenarios": []}
        else:
            try:
                contract, scenarios = build(case["family"], case["spec"])
            except Exception as exc:  # noqa: BLE001 - report every broken spec
                problems.append(f"{case['id']}: build failed: {type(exc).__name__}: {exc}")
                continue
            errors = validate_contract(contract)
            if errors:
                problems.append(f"{case['id']}: invalid contract: {errors[:2]}")
            for sc in scenarios:
                issue = sim_check(contract, sc)
                if issue:
                    problems.append(f"{case['id']} / {sc['name']}: {issue}")
            case["reference_contract"], case["checks"] = contract, {"scenarios": scenarios}
            case["marlowe_features"] = sorted(features(contract))
        for tok in case.get("spec", {}).get("tokens", {}).values():
            if not re.fullmatch(r"[0-9a-f]{56}", tok["policy"]):
                problems.append(f"{case['id']}: policy id is not 56 hex characters")
        text = (case["prompt"] + " " + " ".join(f["answer"] for f in case["fact_sheet"])).casefold()
        for name in case.get("spec", {}).get("roles", {}).values():
            if name.casefold() not in text:
                problems.append(f"{case['id']}: role '{name}' not in prompt or fact sheet")
        for pattern in BANNED:
            if re.search(pattern, case["prompt"], flags=re.IGNORECASE | re.MULTILINE):
                problems.append(f"{case['id']}: storytelling phrase /{pattern}/")
        cases.append(case)
    ids = Counter(c["id"] for c in cases)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    v2 = [json.loads(line)["prompt"] for line in V2.read_text(encoding="utf-8").splitlines()]
    for i, case in enumerate(cases):
        words = _norm(case["prompt"])
        for other in cases[i + 1:]:
            ow = _norm(other["prompt"])
            if len(words & ow) / max(1, len(words | ow)) > 0.8:
                problems.append(f"near-duplicate prompts {case['id']} / {other['id']}")
        for prompt in v2:
            ow = _norm(prompt)
            if len(words & ow) / max(1, len(words | ow)) > 0.6:
                problems.append(f"{case['id']}: too close to a v2 prompt")
                break
    return cases, problems


DETECTED = {
    "time_of_day": r"\b\d{1,2}:\d{2}\b|\bnoon\b|\b\d{1,2}(:\d{2})? ?(AM|PM)\b|giờ trưa|12 giờ",
    "timezone": r"UTC|GMT|giờ VN|giờ Việt Nam|giờ Hà Nội|giờ Đà Nẵng|Vietnam time|Hanoi time|Berlin time|US Eastern|gio VN",
    "relative_time": (r"\bsau\b|trong vòng|kể từ|ke tu|hằng (tháng|tuần|năm)|hàng (tháng|năm)|mỗi (tháng|quý|kỳ)|"
                      r"\bwithin\b|\bafter\b|\bmonthly\b|\bquarterly\b|\bweekly\b|\bevery\b|\bthen has\b"),
    "bullet_list": r"^\s*(- |\(\w\) |\d\. )",
    "percentage": r"\d\s?%",
}


def detected(prompt: str) -> set[str]:
    return {k for k, pattern in DETECTED.items()
            if re.search(pattern, prompt, flags=re.IGNORECASE | re.MULTILINE)}


def coverage(cases: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    gaps = []
    for case in cases:
        case["phenomena"] = sorted(set(case["phenomena"]) | detected(case["prompt"]))
    langs = Counter(c["language"] for c in cases)
    modes = Counter(c["info_mode"] for c in cases)
    fams = Counter(c["family"] for c in cases)
    phen = Counter(p for c in cases for p in set(c["phenomena"]))
    feats = Counter(f for c in cases for f in c.get("marlowe_features", []))
    if dict(langs) != TARGETS_DISTRIBUTION:
        gaps.append(f"languages {dict(langs)} != {TARGETS_DISTRIBUTION}")
    if dict(modes) != TARGET_MODES:
        gaps.append(f"info modes {dict(modes)} != {TARGET_MODES}")
    gaps += [f"phenomenon {k}: {phen[k]} < {v}" for k, v in MIN_PHENOMENA.items() if phen[k] < v]
    gaps += [f"feature {k}: {feats[k]} < {v}" for k, v in MIN_FEATURES.items() if feats[k] < v]
    report = {"cases": len(cases), "languages": dict(langs), "info_modes": dict(modes), "families": dict(fams),
              "phenomena": dict(sorted(phen.items())), "marlowe_features": dict(sorted(feats.items()))}
    return report, gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    cases, problems = assemble()
    report, gaps = coverage(cases)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for line in problems + gaps:
        print("PROBLEM:", line)
    if problems or gaps:
        return 1
    if args.write:
        OUT.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")
        print("wrote", OUT, "sha256", hashlib.sha256(OUT.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
