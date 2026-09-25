from __future__ import annotations

import argparse
import hashlib
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.marlowe_validator import validate_contract

from .cases import Case, load_cases
from .config import (DATASET, DIFFICULTY_COUNTS, INFO_COUNTS, LANGUAGE_COUNTS,
                     TYPE_COUNTS)
from .evaluator import evaluate
from .templates import build

BANNED = ["smart contract", "hợp đồng thông minh", "Marlowe", "Cardano", "blockchain",
          "AST", "JSON", "lovelace", "POSIX", "timeout", "deposit", "role", "token",
          "escrow", "oracle", "vesting", "Pay", "Close"]


def _ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").replace("đ", "d")


def validate(cases: list[Case]) -> list[str]:
    errors = []
    if len(cases) != 100:
        errors.append(f"case_count:{len(cases)}")
    for key, expected in (("type", TYPE_COUNTS), ("difficulty", DIFFICULTY_COUNTS),
                          ("language", LANGUAGE_COUNTS), ("info_mode", INFO_COUNTS)):
        actual = Counter(getattr(case, key) for case in cases)
        if actual != expected:
            errors.append(f"distribution:{key}:{dict(actual)}")
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_ids")
    prompts = [_ascii(case.prompt).strip() for case in cases]
    if len(prompts) != len(set(prompts)):
        errors.append("duplicate_prompts")
    beginnings = [" ".join(prompt.split()[:6]) for prompt in prompts]
    if len(beginnings) != len(set(beginnings)):
        errors.append("duplicate_first_six_words")
    levels: dict[str, set[int]] = defaultdict(set)
    languages: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        levels[case.type].add(case.difficulty)
        languages[case.type].add(case.language)
        plain = _ascii(case.prompt)
        for term in BANNED:
            if re.search(r"(?<!\w)" + re.escape(_ascii(term)) + r"(?!\w)", plain):
                errors.append(f"banned:{case.id}:{term}")
        has_diacritic = bool(re.search(r"[à-ỹÀ-ỸđĐ]", case.prompt))
        if case.language == "vi" and not has_diacritic:
            errors.append(f"language_vi:{case.id}")
        if case.language == "en" and has_diacritic:
            errors.append(f"language_en:{case.id}")
        if case.info_mode in {"missing", "ambiguous"} and not case.hidden_facts:
            errors.append(f"missing_hidden_facts:{case.id}")
        if case.expected_behavior == "converge" and case.type == "infeasible":
            errors.append(f"infeasible_expected_behavior:{case.id}")
        rebuilt, scenarios = build(case.type, case.params)
        if rebuilt != case.reference_contract or scenarios != case.checks["scenarios"]:
            errors.append(f"ground_truth_drift:{case.id}")
        if validate_contract(case.reference_contract):
            errors.append(f"reference_structure:{case.id}")
        if not LogicGraphVerifier().verify(case.reference_contract).passed:
            errors.append(f"reference_logic:{case.id}")
        if case.type != "infeasible" and not evaluate(case, case.reference_contract)["strict_correct"]:
            errors.append(f"reference_score:{case.id}")
        if case.params.get("amount") == 250000000 and {"Alice", "Bob"}.issubset(set(case.params["roles"].values())):
            errors.append(f"agent_example_leak:{case.id}")
    for kind in TYPE_COUNTS:
        if kind != "infeasible" and len(levels[kind]) < 2:
            errors.append(f"difficulty_diversity:{kind}")
        if len(languages[kind]) < 2:
            errors.append(f"language_diversity:{kind}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args()
    cases = load_cases(args.dataset)
    errors = validate(cases)
    lengths = [len(case.prompt.split()) for case in cases]
    print(f"cases={len(cases)} words_min={min(lengths)} words_median={statistics.median(lengths)} "
          f"words_max={max(lengths)} sha256={hashlib.sha256(args.dataset.read_bytes()).hexdigest()}")
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("Dataset validation passed")


if __name__ == "__main__":
    main()
