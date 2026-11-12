import json
from pathlib import Path

import pytest

from research.formalization.intent_summary import summarize
from research.synthesis.example_scenarios import build_prompt, describe, to_compact

CORE = {
    "requirement_history": [{"version": 1, "messages": [
        "Ngọc góp 40 ADA trước 20:00 ngày 01/02/2027 (giờ VN), bất kỳ ai bấm thì trả Lâm."]}],
    "behavior_scopes": [
        {"scope_id": "t_dep", "scope_type": "transition", "transition_kind": "deposit",
         "continuation_scope_id": "t_go"},
        {"scope_id": "to_dep", "scope_type": "timeout", "decision_id": "t_dep"},
        {"scope_id": "t_go", "scope_type": "transition", "transition_kind": "notify",
         "continuation_scope_id": "o_pay"},
        {"scope_id": "o_pay", "scope_type": "terminal_outcome", "parent_scope_id": "t_go"},
        {"scope_id": "to_go", "scope_type": "timeout", "decision_id": "t_go"},
        {"scope_id": "o_back", "scope_type": "terminal_outcome", "parent_scope_id": "to_go"}],
    "claims": [
        {"scope_id": "global", "kind": "asset", "value": "ADA"},
        {"scope_id": "t_dep", "kind": "depositing_party", "value": "Ngọc"},
        {"scope_id": "t_dep", "kind": "destination_account_owner", "value": "Ngọc"},
        {"scope_id": "t_dep", "kind": "amount_lovelace", "value": 40_000_000},
        {"scope_id": "t_dep", "kind": "deposit_deadline_ms", "value": 1_801_486_800_000},
        {"scope_id": "t_go", "kind": "timeout_ms", "value": 1_801_573_200_000},
        {"scope_id": "o_pay", "kind": "payment_source_account_owner", "value": "Ngọc"},
        {"scope_id": "o_pay", "kind": "payment_recipient", "value": "Lâm"},
        {"scope_id": "o_pay", "kind": "amount_lovelace", "value": 40_000_000},
        {"scope_id": "o_back", "kind": "payment_source_account_owner", "value": "Ngọc"},
        {"scope_id": "o_back", "kind": "refund_recipient", "value": "Ngọc"},
        {"scope_id": "o_back", "kind": "amount_lovelace", "value": 40_000_000}],
}


def test_summary_reads_the_core_in_the_request_language():
    text = summarize(CORE)
    assert "Ngọc nạp 40 ADA" in text and "20:00 ngày 01/02/2027 (UTC+7)" in text
    assert "Bất kỳ ai cũng có thể bấm xác nhận" in text
    assert "Ngọc trả 40 ADA cho Lâm." in text
    assert text.endswith("xin nói rõ chỗ đó.")


def test_examples_become_compact_scenarios_with_code_computed_times():
    system, user = build_prompt(CORE, "Ngọc góp xong, có người bấm thì Lâm nhận 40 ADA.")
    assert "D1: 20:00 ngày 01/02/2027 (UTC+7)" in user and "D2" in user
    reply = {"scenarios": [
        {"name": "paid", "steps": [{"do": "deposit", "party": "Ngoc", "ada": "40", "before": "D1"},
                                   {"do": "press", "before": "D2"}],
         "receive": [{"party": "Lâm", "ada": "40"}]},
        {"name": "nobody", "steps": [{"do": "deposit", "party": "Ngọc", "ada": "40",
                                      "before": "D1"}, {"do": "wait", "past": "D2"}],
         "receive": [{"party": "Ngọc", "ada": "40"}]},
        {"name": "bad", "steps": [{"do": "wait", "past": "D9"}], "receive": []}]}
    scenarios, problems = to_compact(CORE, reply)
    assert set(scenarios) == {"paid", "nobody"} and problems == ["bad: unknown deadline 'D9'"]
    assert scenarios["paid"]["tx"][0] == ["2027-02-01T13:00:00.000+00:00",
                                          [["deposit", "Ngoc", "Ngọc", 40.0]]]
    assert scenarios["paid"]["tx"][1][1] == [["notify"]]
    assert scenarios["nobody"]["tx"][1][1] == []
    text = describe(CORE, scenarios)
    assert "Ngoc nạp 40 ADA trước 20:00 ngày 01/02/2027 (UTC+7)" in text
    assert "Kết quả: Lâm 40 ADA." in text


def test_a_reply_without_scenarios_is_a_problem():
    assert to_compact(CORE, {"x": 1}) == ({}, ["reply has no scenarios"])
