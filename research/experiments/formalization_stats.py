"""Paired statistics for two scored Formalization arms (docs/archive/E4-Formalization-Comparison.md, Part II).

Both arms run the same cases, so every comparison is paired by case:
- binary metrics (M1, M2, M4): each arm's rate with a Wilson 95% interval, the
  discordant pairs, and an exact two-sided McNemar test; the primary metrics
  get a Holm correction;
- ratios (M2 calls per valid intent, M3 recall/precision): a paired bootstrap
  95% interval of the difference B - A, resampling cases with a fixed seed.

Input is the JSON `formalization_score` writes. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

PRIMARY = ("first_pass_valid", "final_valid", "decision_correct")
SECONDARY = ("decision_correct_adjusted", "decision_on_valid_core", "conflict_identified")
FACT_KINDS = ("roles", "amounts", "deadlines")
Z95 = 1.959963984540054


def wilson(successes: int, total: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for a binomial rate; None when there are no trials."""
    if total == 0:
        return None
    rate = successes / total
    centre = rate + z * z / (2 * total)
    spread = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total))
    scale = 1 + z * z / total
    return round(max(0.0, (centre - spread) / scale), 4), round(min(1.0, (centre + spread) / scale), 4)


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from the two discordant counts."""
    discordant = only_a + only_b
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(only_a, only_b) + 1))
    return min(1.0, 2 * tail / 2 ** discordant)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm–Bonferroni adjusted p-values (family-wise error control)."""
    ordered = sorted(pvalues.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * value))
        adjusted[name] = running
    return adjusted


def paired_bootstrap(pairs: Sequence[tuple[dict[str, Any], dict[str, Any]]],
                     statistic: Callable[[list[dict[str, Any]]], float | None], *,
                     iterations: int = 10_000, seed: int = 0) -> dict[str, Any]:
    """Point estimate and percentile 95% interval of statistic(B) - statistic(A)."""
    def difference(sample: Sequence[tuple[dict[str, Any], dict[str, Any]]]) -> float | None:
        a = statistic([pair[0] for pair in sample])
        b = statistic([pair[1] for pair in sample])
        return None if a is None or b is None else b - a

    estimate = difference(pairs)
    rng = random.Random(seed)
    draws = []
    for _ in range(iterations):
        value = difference([pairs[rng.randrange(len(pairs))] for _ in pairs])
        if value is not None:
            draws.append(value)
    draws.sort()
    interval = None
    if draws:
        interval = (round(draws[int(0.025 * (len(draws) - 1))], 4),
                    round(draws[int(0.975 * (len(draws) - 1))], 4))
    return {"difference": None if estimate is None else round(estimate, 4),
            "ci95": interval, "valid_resamples": len(draws)}


def _calls_per_valid(rows: list[dict[str, Any]]) -> float | None:
    valid = sum(row["final_valid"] for row in rows)
    return None if valid == 0 else sum(row["physical_calls"] for row in rows) / valid


def _fact_ratio(kind: str, numerator: str, denominator: str
                ) -> Callable[[list[dict[str, Any]]], float | None]:
    def ratio(rows: list[dict[str, Any]]) -> float | None:
        complete = [row for row in rows if row["info_mode"] == "complete"]
        total = sum(row["facts"][kind][denominator] for row in complete)
        return None if total == 0 else sum(row["facts"][kind][numerator]
                                           for row in complete) / total
    return ratio


def compare(score_a: dict[str, Any], score_b: dict[str, Any], *,
            iterations: int = 10_000, seed: int = 0) -> dict[str, Any]:
    """Paired comparison of arm B against arm A on the cases both scored."""
    rows_a = {row["case_id"]: row for row in score_a["cases"]}
    rows_b = {row["case_id"]: row for row in score_b["cases"]}
    shared = sorted(rows_a.keys() & rows_b.keys())
    pairs = [(rows_a[case], rows_b[case]) for case in shared]
    binary: dict[str, dict[str, Any]] = {}
    for metric in PRIMARY + SECONDARY:
        hits_a = sum(a.get(metric, False) for a, _ in pairs)
        hits_b = sum(b.get(metric, False) for _, b in pairs)
        only_a = sum(a.get(metric, False) and not b.get(metric, False) for a, b in pairs)
        only_b = sum(b.get(metric, False) and not a.get(metric, False) for a, b in pairs)
        binary[metric] = {
            "A": {"rate": round(hits_a / len(pairs), 4) if pairs else None,
                  "ci95": wilson(hits_a, len(pairs))},
            "B": {"rate": round(hits_b / len(pairs), 4) if pairs else None,
                  "ci95": wilson(hits_b, len(pairs))},
            "only_A": only_a, "only_B": only_b,
            "mcnemar_p": round(mcnemar_exact(only_a, only_b), 4)}
    for metric, value in holm({metric: binary[metric]["mcnemar_p"]
                               for metric in PRIMARY}).items():
        binary[metric]["holm_p"] = round(value, 4)
    ratios = {"calls_per_valid_intent": _calls_per_valid}
    for kind in FACT_KINDS:
        ratios[f"{kind}_recall"] = _fact_ratio(kind, "matched", "expected")
        ratios[f"{kind}_precision"] = _fact_ratio(kind, "matched", "found")
    return {"cases_paired": len(pairs),
            "unpaired": {"A_only": sorted(rows_a.keys() - rows_b.keys()),
                         "B_only": sorted(rows_b.keys() - rows_a.keys())},
            "binary": binary,
            "paired_bootstrap_B_minus_A": {
                name: paired_bootstrap(pairs, statistic, iterations=iterations, seed=seed)
                for name, statistic in ratios.items()},
            "method": {"binary": "Wilson 95% CI; exact two-sided McNemar; Holm over "
                                 + ", ".join(PRIMARY),
                       "ratios": f"paired case bootstrap, {iterations} resamples, seed {seed}"}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Paired statistics for two scored arms")
    parser.add_argument("score_a", type=Path, help="formalization_score output of arm A (baseline)")
    parser.add_argument("score_b", type=Path, help="formalization_score output of arm B")
    parser.add_argument("--iterations", type=int, default=10_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(json.loads(args.score_a.read_text(encoding="utf-8")),
                     json.loads(args.score_b.read_text(encoding="utf-8")),
                     iterations=args.iterations)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
