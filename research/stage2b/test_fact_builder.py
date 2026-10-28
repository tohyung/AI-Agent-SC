"""A2 spike: a synthetic FactDraft v5 builds a core the unchanged v4 validator accepts."""

from copy import deepcopy

import pytest

from research.stage2b.fact_builder import FACT_DRAFT_VERSION, DraftError, build_core
from research.stage2b.intent_spec import (
    validate_intent_spec,
    validate_shadow_semantic_core,
)
from research.stage2b.projector import classify_projection, project_intent_spec

# Synthetic example from the design doc, section 7; not a dataset case.
MESSAGE = (
    "Lan thuê Tú làm hai giai đoạn, tổng 60 ADA, Lan nạp trước 00:00 ngày 02/03/2027 "
    "(UTC+7). Lan duyệt giai đoạn một trong năm ngày sau hạn nạp thì Tú nhận một nửa; "
    "duyệt phần còn lại trong mười ngày sau hạn nạp thì nhận nốt. "
    "Phần chưa duyệt hoàn cho Lan."
)
HISTORY = [{"version": 1, "messages": [MESSAGE]}]
D1 = 1803920400000  # 2027-03-02T00:00+07:00 == 2027-03-01T17:00Z
DAY = 86_400_000


def ev(*spans):
    return [{"requirement_version": 1, "message_index": 0, "span": span, "relation": "supports"}
            for span in spans]


def milestone_draft():
    return {
        "schema_version": FACT_DRAFT_VERSION,
        "parties": [{"id": "p_lan", "name": "Lan", "evidence": ev("Lan thuê Tú")},
                    {"id": "p_tu", "name": "Tú", "evidence": ev("Lan thuê Tú")}],
        "asset": {"ada": True, "evidence": ev("tổng 60 ADA")},
        "quantities": [
            {"id": "q_total", "expr": {"ada": "60"}, "evidence": ev("tổng 60 ADA")},
            {"id": "q_half", "expr": {"fraction": {"of": "q_total", "num": 1, "den": 2}},
             "evidence": ev("Tú nhận một nửa")},
            {"id": "q_rest", "expr": {"subtract": {"from": "q_total", "minus": ["q_half"]}},
             "evidence": ev("duyệt phần còn lại")},
        ],
        "instants": [
            {"id": "i_d1", "expr": {"date": {"y": 2027, "m": 3, "d": 2, "h": 0, "min": 0,
                                             "tz": "+07:00"}},
             "evidence": ev("00:00 ngày 02/03/2027 (UTC+7)")},
            {"id": "i_d2", "expr": {"offset": {"from": "i_d1", "days": 5}},
             "evidence": ev("trong năm ngày sau hạn nạp")},
            {"id": "i_d3", "expr": {"offset": {"from": "i_d1", "days": 10}},
             "evidence": ev("trong mười ngày sau hạn nạp")},
        ],
        "steps": [
            {"id": "s1", "kind": "deposit", "by": "p_lan", "into": "p_lan",
             "amount": "q_total", "deadline": "i_d1", "on_timeout": "end", "then": "s2",
             "evidence": ev("Lan nạp trước 00:00 ngày 02/03/2027")},
            {"id": "s2", "kind": "choice", "by": "p_lan", "deadline": "i_d2",
             "bounds": {"from": 1, "to": 1},
             "branches": [{"guard": {"op": "eq", "value": 1}, "then": ["o_pay1", "s3"]}],
             "on_timeout": ["o_refund_all"], "evidence": ev("Lan duyệt giai đoạn một")},
            {"id": "s3", "kind": "choice", "by": "p_lan", "deadline": "i_d3",
             "bounds": {"from": 1, "to": 1},
             "branches": [{"guard": {"op": "eq", "value": 1}, "then": ["o_pay2"]}],
             "on_timeout": ["o_refund_rest"], "evidence": ev("duyệt phần còn lại")},
        ],
        "outcomes": [
            {"id": "o_pay1", "kind": "payment", "from_account": "p_lan", "to": "p_tu",
             "amount": "q_half", "evidence": ev("Tú nhận một nửa")},
            {"id": "o_pay2", "kind": "payment", "from_account": "p_lan", "to": "p_tu",
             "amount": "q_rest", "evidence": ev("nhận nốt")},
            {"id": "o_refund_all", "kind": "refund", "from_account": "p_lan", "to": "p_lan",
             "amount": "remaining", "evidence": ev("Phần chưa duyệt hoàn cho Lan")},
            {"id": "o_refund_rest", "kind": "refund", "from_account": "p_lan", "to": "p_lan",
             "amount": "remaining", "evidence": ev("Phần chưa duyệt hoàn cho Lan")},
        ],
        "notes": {},
    }


def _values(core, kind):
    return {claim["scope_id"]: claim["value"] for claim in core["claims"]
            if claim["kind"] == kind}


def test_milestone_draft_builds_a_core_the_v4_validator_and_projector_accept():
    core = build_core(milestone_draft(), HISTORY)
    errors = validate_shadow_semantic_core(core, expected_history=HISTORY)
    assert errors == []
    projection = project_intent_spec(core, expected_history=HISTORY)
    spec = projection.intent_spec.to_dict()
    full = validate_intent_spec(spec, expected_history=HISTORY, projected_core=core)
    assert classify_projection(errors, full, projection.projection_diagnostics) == "PASS"
    assert core["predicted_resolution"] == "accepted_interpretation"
    # Every number is computed by code, none is written by the model.
    assert _values(core, "amount_lovelace") == {
        "t_s1": 60_000_000, "o_o_pay1": 30_000_000, "o_o_pay2": 30_000_000,
        "o_o_refund_all": 60_000_000, "o_o_refund_rest": 30_000_000}
    assert _values(core, "deposit_deadline_ms") == {"t_s1": D1}
    assert _values(core, "choice_deadline_ms") == {"t_s2": D1 + 5 * DAY,
                                                    "t_s3": D1 + 10 * DAY}


def test_missing_timezone_is_unresolved_and_builder_asks():
    draft = milestone_draft()
    draft["instants"][0]["expr"]["date"]["tz"] = None
    core = build_core(draft, HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=HISTORY) == []
    assert core["predicted_resolution"] == "clarification_required"
    assert core["required_clarifications"]
    # The unknown base propagates to every offset deadline built on it.
    assert set(_values(core, "choice_deadline_ms").values()) == {None}


def test_inexact_division_becomes_a_rounding_question_not_a_quot():
    draft = milestone_draft()
    draft["quantities"][1]["expr"]["fraction"]["den"] = 7
    core = build_core(draft, HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=HISTORY) == []
    assert core["predicted_resolution"] == "clarification_required"
    assert any("rounded" in question for question in core["required_clarifications"])


def test_ungrounded_literal_and_span_are_draft_errors_by_item_id():
    draft = milestone_draft()
    draft["quantities"][0]["expr"]["ada"] = "70"
    draft["parties"][1]["evidence"] = ev("Tú ký hợp đồng")
    with pytest.raises(DraftError) as raised:
        build_core(draft, HISTORY)
    items = {item for item, _ in raised.value.problems}
    assert items == {"q_total", "p_tu"}


def test_overpayment_violates_money_conservation():
    draft = milestone_draft()
    draft["outcomes"][1]["amount"] = "q_total"
    with pytest.raises(DraftError, match="o_pay2: pays 60000000 but the account holds 30000000"):
        build_core(draft, HISTORY)


def test_v4_conflict_offset_deadline_cannot_cite_its_base_date():
    """Recorded v4 conflict (design 8.4): citing the base date span is rejected."""
    core = build_core(milestone_draft(), HISTORY)
    broken = deepcopy(core)
    claim = next(claim for claim in broken["claims"] if claim["claim_id"] == "t_s2:choice_deadline_ms")
    claim["evidence"] += ev("00:00 ngày 02/03/2027 (UTC+7)")
    errors = validate_shadow_semantic_core(broken, expected_history=HISTORY)
    assert errors == ["claim t_s2:choice_deadline_ms: deadline value contradicts cited calendar date"]


CONFLICT_HISTORY = [{"version": 1, "messages": [MESSAGE + " Tổng cộng 70 ADA nhé."]}]


def _with_total_readings(*readings):
    draft = milestone_draft()
    del draft["quantities"][0]["expr"]
    draft["quantities"][0]["alternatives"] = [
        {"expr": {"ada": amount}, "evidence": ev(span)} for amount, span in readings]
    return draft


def test_distinct_readings_become_conflicted_claims_and_a_conflict_resolution():
    draft = _with_total_readings(("60", "tổng 60 ADA"), ("70", "Tổng cộng 70 ADA"))
    core = build_core(draft, CONFLICT_HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=CONFLICT_HISTORY) == []
    assert core["predicted_resolution"] == "conflict_requires_resolution"
    assert core["required_clarifications"]
    deposit = [claim for claim in core["claims"]
               if claim["scope_id"] == "t_s1" and claim["kind"] == "amount_lovelace"]
    assert {(claim["status"], claim["value"]) for claim in deposit} == {
        ("conflicted", 60_000_000), ("conflicted", 70_000_000)}
    # Amounts computed from the disputed total stay open instead of picking a reading.
    assert _values(core, "amount_lovelace")["o_o_pay1"] is None


def test_equal_readings_are_not_a_conflict():
    draft = _with_total_readings(("60", "tổng 60 ADA"), ("60", "tổng 60 ADA"))
    core = build_core(draft, CONFLICT_HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=CONFLICT_HISTORY) == []
    assert core["predicted_resolution"] == "accepted_interpretation"


def test_two_parties_for_one_role_is_a_conflict():
    draft = milestone_draft()
    draft["steps"][1]["by"] = ["p_lan", "p_tu"]
    core = build_core(draft, HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=HISTORY) == []
    assert core["predicted_resolution"] == "conflict_requires_resolution"
    owners = {claim["value"] for claim in core["claims"]
              if claim["scope_id"] == "t_s2" and claim["kind"] == "choice_owner"}
    assert owners == {"Lan", "Tú"}
