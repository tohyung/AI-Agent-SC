"""Paired statistics: known values and the paired comparison."""

import math

import pytest

from research.experiments.formalization_stats import (
    compare,
    holm,
    mcnemar_exact,
    paired_bootstrap,
    wilson,
)


def test_mcnemar_exact_matches_the_binomial_tail():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(0, 6) == pytest.approx(2 / 64)
    assert mcnemar_exact(6, 0) == mcnemar_exact(0, 6)
    # 2 vs 8 discordant: 2 * P(X <= 2), X ~ Bin(10, 1/2) = 2 * 56/1024.
    assert mcnemar_exact(2, 8) == pytest.approx(112 / 1024)
    assert mcnemar_exact(5, 5) == 1.0


def test_wilson_interval_stays_inside_zero_one_and_brackets_the_rate():
    assert wilson(0, 0) is None
    low, high = wilson(0, 20)
    assert low == 0.0 and 0.15 < high < 0.17
    low, high = wilson(10, 20)
    assert low < 0.5 < high and math.isclose(0.5 - low, high - 0.5, abs_tol=1e-3)


def test_holm_is_monotone_and_never_below_raw():
    adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == {"a": pytest.approx(0.03), "c": pytest.approx(0.06),
                        "b": pytest.approx(0.06)}


def test_paired_bootstrap_is_seeded_and_brackets_a_constant_shift():
    pairs = [({"x": value}, {"x": value + 1}) for value in range(30)]

    def mean(rows):
        return sum(row["x"] for row in rows) / len(rows)

    first = paired_bootstrap(pairs, mean, iterations=500, seed=3)
    assert first == paired_bootstrap(pairs, mean, iterations=500, seed=3)
    assert first["difference"] == 1.0 and first["ci95"] == (1.0, 1.0)


def _row(case, first, final, decision, calls, matched=1):
    return {"case_id": case, "info_mode": "complete", "first_pass_valid": first,
            "final_valid": final, "decision_correct": decision,
            "decision_correct_adjusted": decision, "physical_calls": calls,
            "facts": {kind: {"expected": 2, "found": 2, "matched": matched}
                      for kind in ("roles", "amounts", "deadlines")}}


def test_compare_pairs_cases_and_counts_discordance():
    a = {"cases": [_row(f"c{i}", False, i < 3, False, 4) for i in range(10)]
         + [_row("only-a", True, True, True, 1)]}
    b = {"cases": [_row(f"c{i}", True, True, i < 5, 1, matched=2) for i in range(10)]}
    result = compare(a, b, iterations=300)
    assert result["cases_paired"] == 10
    assert result["unpaired"] == {"A_only": ["only-a"], "B_only": []}
    first = result["binary"]["first_pass_valid"]
    assert (first["only_A"], first["only_B"]) == (0, 10)
    assert first["mcnemar_p"] == pytest.approx(2 / 1024, abs=1e-4)
    assert first["holm_p"] >= first["mcnemar_p"]
    calls = result["paired_bootstrap_B_minus_A"]["calls_per_valid_intent"]
    assert calls["difference"] == pytest.approx(1 - 40 / 3, abs=1e-3)
    recall = result["paired_bootstrap_B_minus_A"]["amounts_recall"]
    assert recall["difference"] == 0.5
