"""Build dataset v4 from dataset v3 under the E7 conventions: python -m dataset.v4.build [--write]

v4 keeps every v3 prompt, spec and fact sheet, and adds what docs/E7-Conventions.md requires:

- Q-DỮ LIỆU 1: `spec.parties` gives each role a display name and a role token. The display name is
  the phrase the prompt or the fact sheet attaches to the token ("Công ty Sao Mai, role SaoMai");
  otherwise the token itself.
- Q-DỮ LIỆU 3: check scenarios cover at least two different members of an "any of" group. v3's
  first-come cases tested only the last listed buyer, so a contract that lets only that buyer buy
  passed (E6, case 61); v4 adds a scenario for every other buyer. Expected payouts come from the
  spec, as in v3, and every added scenario is checked on the reference contract with the simulator.
- Q-DỮ LIỆU 4: `split` is "dev" or "eval", stratified by family (about 30% dev in each family),
  in a fixed order given by the SHA-256 of the case id.

Because the prompts are v3's, which were used to fix the pipeline (E6 cases 1-29) and were read in
full during the E6 failure review, v4 is a development set. A clean evaluation needs new prompts
written under the same conventions; see dataset/v4/README.md.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from dataset.v3.build import sim_check
from dataset.v3.builders import add, before, dep, lovelace, ms, scenario

HERE = Path(__file__).resolve().parent
V3 = HERE.parent / "v3" / "cases.jsonl"
OUT = HERE / "cases.jsonl"
DEV_SHARE = 0.3
_DISPLAY = r"([^\n,;:()\-]{1,60}?)"


def display_name(token: str, texts: list[str]) -> str:
    """The phrase the conversation attaches to a role token, else the token."""
    escaped = re.escape(token)
    patterns = [rf"{_DISPLAY}\s*,\s*role:?\s*{escaped}\b", rf"{_DISPLAY}\s*\(\s*role:?\s*{escaped}\s*\)",
                rf"\(\s*{_DISPLAY}\s*,\s*role:?\s*{escaped}\s*\)"]
    for text in texts:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = _trim(match.group(1).strip(" .").split())
                if name:
                    return name
    return token


KINDS = {"công ty", "cty", "nhóm", "quỹ", "trường", "chùa", "cửa hàng", "bệnh viện", "nhà trường",
         "nhà tài trợ", "ban tổ chức", "company", "team", "fund", "school", "sponsor", "studio"}
STOP = {"chuyển", "cho", "chi", "là", "bên", "goes", "to", "payout", "the", "deduction", "tiền",
        "trả", "tài", "trợ", "gửi", "nhận", "của", "và", "and", "for", "of"}


def _trim(words: list[str]) -> str:
    """The name inside a phrase: its trailing capitalised words with a kind word before them
    ("chuyển cho quỹ Mầm Xanh" -> "quỹ Mầm Xanh"), else the phrase without leading filler words."""
    end = len(words)
    start = end
    while start > 0 and words[start - 1][:1].isupper():
        start -= 1
    if start < end:
        for width in (2, 1):
            kind = " ".join(words[max(start - width, 0):start]).lower()
            if start - width >= 0 and kind in KINDS:
                start -= width
                break
        return " ".join(words[start:end])
    words = words[-3:]
    while words and words[0].lower() in STOP:
        words = words[1:]
    return " ".join(words)


def parties(case: dict[str, Any]) -> dict[str, dict[str, str]]:
    texts = [case["prompt"], *(item["answer"] for item in case.get("fact_sheet", []))]
    return {key: {"name": display_name(value, texts), "role": value}
            for key, value in (case["spec"].get("roles") or {}).items()}


def first_come_scenarios(case: dict[str, Any]) -> list[dict[str, Any]]:
    """One scenario per buyer other than the last listed one (v3 already has that)."""
    spec = case["spec"]
    roles = spec["roles"]
    seller, buyers = roles["seller"], [roles[key] for key in spec["buyers"]]
    price, until = lovelace(spec["price"]), ms(spec["offer_until"])
    got: dict[str, dict[str, int]] = {}
    add(got, seller, "", price)
    return [scenario(f"buyer_{number}_first", [dep(buyer, price, "", before(until))], deepcopy(got))
            for number, buyer in enumerate(buyers[:-1], 1)]


def split_of(cases: list[dict[str, Any]]) -> dict[str, str]:
    by_family: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        by_family[case["family"]].append(case["id"])
    split = {}
    for ids in by_family.values():
        ordered = sorted(ids, key=lambda case_id: hashlib.sha256(case_id.encode()).hexdigest())
        dev = max(1, round(len(ordered) * DEV_SHARE)) if len(ordered) > 1 else 0
        for position, case_id in enumerate(ordered):
            split[case_id] = "dev" if position < dev else "eval"
    return split


def assemble() -> tuple[list[dict[str, Any]], list[str]]:
    source = [json.loads(line) for line in V3.read_text(encoding="utf-8").splitlines()]
    split = split_of(source)
    cases, errors = [], []
    for old in source:
        case = deepcopy(old)
        case["id"] = "v4-" + old["id"][len("v3-"):]
        case["origin"] = old["id"]
        case["split"] = split[old["id"]]
        case["spec"]["parties"] = parties(old)
        if case["family"] == "first_come":
            added = first_come_scenarios(old)
            for item in added:
                problem = sim_check(case["reference_contract"], item)
                if problem:
                    errors.append(f"{case['id']} {item['name']}: {problem}")
            case["checks"]["scenarios"].extend(added)
        cases.append(case)
    return cases, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    cases, errors = assemble()
    for error in errors:
        print("ERROR", error)
    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        counts[case["split"]] += 1
    print(f"{len(cases)} cases, split {dict(counts)}")
    named = {case["id"]: {key: value["name"] for key, value in case["spec"]["parties"].items()
                          if value["name"] != value["role"]}
             for case in cases}
    print("display names differing from the token:",
          sum(len(value) for value in named.values()))
    if errors:
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
