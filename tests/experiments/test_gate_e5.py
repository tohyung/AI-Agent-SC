"""E5 variants, label oracle, policy ladder and scoring (no pinned binaries needed)."""

from __future__ import annotations

from research.experiments import gate_labels, gate_mutants, gate_policy, gate_score

ADA = {"currency_symbol": "", "token_name": ""}
DEADLINE = 1_800_000_000_000


def _escrow(payee: str = "Seller", amount: int = 10_000_000, timeout: int = DEADLINE) -> dict:
    return {"when": [{"case": {"deposits": amount, "into_account": {"role_token": "Buyer"},
                               "of_token": ADA, "party": {"role_token": "Buyer"}},
                      "then": {"pay": amount, "from_account": {"role_token": "Buyer"},
                               "to": {"party": {"role_token": payee}}, "token": ADA,
                               "then": "close"}}],
            "timeout": timeout, "timeout_continuation": "close"}


def test_reference_is_right_and_wrong_payee_has_a_witness():
    reference = _escrow()
    assert gate_labels.label(reference, reference)["label"] == "RIGHT"
    result = gate_labels.label(_escrow(payee="Buyer"), reference)
    assert result["label"] == "WRONG" and result["witness"]


def test_deadline_shift_of_days_is_wrong_but_hours_are_tolerated():
    reference = _escrow()
    assert gate_labels.label(_escrow(timeout=DEADLINE + 3 * 86_400_000), reference)["label"] == "WRONG"
    assert gate_labels.label(_escrow(timeout=DEADLINE + 3 * 3_600_000), reference)["label"] == "RIGHT"


def test_overpaying_an_account_is_wrong_even_if_payouts_match():
    reference = _escrow()
    over = _escrow()
    over["when"][0]["then"]["pay"] = 20_000_000
    assert gate_labels.label(over, reference)["label"] == "WRONG"


def test_role_names_are_compared_after_trimming_and_case_folding():
    reference = _escrow()
    renamed = gate_labels.normalize_roles(_escrow())
    assert gate_labels.label(renamed, reference)["label"] == "RIGHT"


def test_variants_start_with_the_reference_and_are_distinct():
    found = gate_mutants.variants(_escrow())
    assert found[0].operator == "reference"
    contracts = [v.contract for v in found]
    assert all(contracts.count(c) == 1 for c in contracts)
    operators = {v.operator for v in found}
    assert {"payee", "pay_half", "deadline_earlier", "split_pay", "ada_token_name"} <= operators


def test_split_pay_is_labelled_right():
    split = next(v for v in gate_mutants.variants(_escrow()) if v.operator == "split_pay")
    assert gate_labels.label(split.contract, _escrow())["label"] == "RIGHT"


def test_ladder_rejects_first_then_abstains():
    gates = {"structural": "PASS", "lint": "PASS", "smt": "ABSTAIN",
             "scenarios": "REJECT", "exploration": "PASS"}
    assert gate_policy.ladder(gates) == {"B0": "ACCEPT", "B1": "ACCEPT", "B2": "ABSTAIN",
                                         "B3": "REJECT", "B4": "REJECT"}


def _record(case: int, label: str, b0: str, b4: str) -> dict:
    decisions = {"B0": b0, "B1": b0, "B2": b0, "B3": b4, "B4": b4}
    gates = dict.fromkeys(("structural", "lint", "smt", "scenarios", "exploration"), "PASS")
    return {"candidate_id": f"c{case}{label}{b4}", "case_index": case, "operator": "x",
            "label": {"label": label}, "decisions": decisions, "gates": gates,
            "reference_calls": 1, "smt_calls": 1, "seconds": 0.1}


def test_score_reports_false_accept_coverage_and_rule():
    records = ([_record(i, "WRONG", "ACCEPT", "REJECT") for i in range(10)]
               + [_record(i, "RIGHT", "ACCEPT", "ACCEPT") for i in range(10)])
    result = gate_score.score(records)
    assert result["rungs"]["B0"]["false_accept"]["rate"] == 1.0
    assert result["rungs"]["B4"]["false_accept"]["rate"] == 0.0
    assert result["rungs"]["B4"]["coverage"]["rate"] == 1.0
    assert result["B0_vs_B4_on_wrong"]["mcnemar_p"] < 0.05
    assert result["decision_rule"]["all"] is True
