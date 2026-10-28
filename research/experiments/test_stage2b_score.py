"""Scorer uses facts the reference contract actually uses, not unused template params."""

import json

from research.experiments import stage2b_score

REFERENCE = {"when": [{"case": {"party": {"role_token": "Bob"}, "deposits": 20000000,
                                "into_account": {"role_token": "Bob"},
                                "of_token": {"currency_symbol": "", "token_name": ""}},
                       "then": {"pay": 20000000, "from_account": {"role_token": "Bob"},
                                "to": {"party": {"role_token": "Carol"}},
                                "token": {"currency_symbol": "", "token_name": ""},
                                "then": "close"}}],
             "timeout": 1799150400000, "timeout_continuation": "close"}


def _claim(kind, value, status="explicit"):
    return {"kind": kind, "value": value, "status": status}


def _record(tmp_path, index, case_id, core, **extra):
    record = {"case_index": index, "case_id": case_id, "physical_calls": 2,
              "semantic_core": core, **extra}
    (tmp_path / f"case-{index:02d}.json").write_text(json.dumps(record), encoding="utf-8")


def test_reference_facts_ignore_expressions_and_collect_used_values():
    facts = stage2b_score.reference_facts(REFERENCE)
    assert facts == {"roles": {"Bob", "Carol"}, "amounts": {20000000},
                     "deadlines": {1799150400000}}


def test_unresolved_or_non_integer_claims_do_not_count_as_facts():
    core = {"claims": [_claim("depositing_party", "Bob"),
                       _claim("amount_lovelace", "20 ADA"),
                       _claim("deposit_deadline_ms", 1799150400000, status="unresolved")]}
    assert stage2b_score.extracted_facts(core) == {
        "roles": {"Bob"}, "amounts": set(), "deadlines": set()}


def test_arm_metrics_and_decision_expectation_by_info_mode(tmp_path):
    cases = {"a": {"info_mode": "complete", "reference_contract": REFERENCE},
             "b": {"info_mode": "missing", "reference_contract": REFERENCE}}
    good = {"claims": [_claim("depositing_party", "Bob"), _claim("payment_recipient", "Carol"),
                       _claim("amount_lovelace", 20000000),
                       _claim("deposit_deadline_ms", 1799150400000)]}
    _record(tmp_path, 1, "a", good, first_pass_valid=True, final_valid=True,
            predicted_resolution="accepted_interpretation")
    _record(tmp_path, 2, "b", {"claims": []}, first_pass_valid=False, final_valid=False,
            predicted_resolution="accepted_interpretation")
    summary = stage2b_score.score_arm(tmp_path, cases)["summary"]
    assert summary["M1_first_pass_valid"] == 0.5 and summary["M2_final_valid"] == 0.5
    assert summary["M2_calls_per_valid_intent"] == 4.0
    assert summary["M3_complete_cases"] == 1
    assert summary["M3_fact_agreement"]["roles"] == {"recall": 1.0, "precision": 1.0}
    assert summary["M4_by_info_mode"] == {"complete": 1.0, "missing": 0.0}


def test_adjusted_deadline_identified_by_date_or_relative_phrase_without_time():
    noon_jan_3, noon_jan_10 = 1798977600000, 1799582400000  # 2027-01-03/10 12:00 UTC
    core = {"claims": [
        {"kind": "deposit_deadline_ms", "value": None, "status": "unresolved",
         "evidence": [{"span": "trước ngày 03/01/2027"}]},
        {"kind": "choice_deadline_ms", "value": None, "status": "unresolved",
         "evidence": [{"span": "bảy ngày sau hạn nạp"}]},
        {"kind": "timeout_ms", "value": None, "status": "unresolved",
         "evidence": [{"span": "khi nào tiện"}]}]}
    assert stage2b_score.identified_deadlines(core, {noon_jan_3, noon_jan_10}) == (2, 2)


def test_adjusted_m4_accepts_complete_case_that_only_asks_about_time():
    deadline_only = {"predicted_resolution": "clarification_required", "semantic_core": {
        "claims": [_claim("deposit_deadline_ms", None, "unresolved") | {"criticality": "financial"}],
        "unscored_observations": []}}
    amount_open = {"predicted_resolution": "clarification_required", "semantic_core": {
        "claims": [_claim("amount_lovelace", None, "unresolved") | {"criticality": "financial"}],
        "unscored_observations": []}}
    assert stage2b_score.time_only_open(deadline_only) is True
    assert stage2b_score.time_only_open(amount_open) is False


def test_adjusted_m4_ignores_side_context_but_not_unrepresented_behavior():
    def record(reason):
        return {"predicted_resolution": "clarification_required", "semantic_core": {
            "claims": [_claim("deposit_deadline_ms", None, "unresolved")
                       | {"criticality": "financial"}],
            "unscored_observations": [{"reason": reason}]}}
    assert stage2b_score.time_only_open(record("irrelevant_context")) is True
    assert stage2b_score.time_only_open(record("outside_stage2b_v4_claim_taxonomy")) is False
