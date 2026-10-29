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


DELETION_HISTORY = [{"version": 1, "messages": [
    MESSAGE + " Xong việc thì xóa toàn bộ lịch sử giao dịch trên chain."]}]


def test_ledger_history_deletion_is_the_v4_unsupported_signal():
    draft = milestone_draft()
    draft["notes"] = {"unsupported": [{
        "kind": "ledger_history_deletion", "text": "erase on-chain history",
        "evidence": ev("xóa toàn bộ lịch sử giao dịch trên chain")}]}
    core = build_core(draft, DELETION_HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=DELETION_HISTORY) == []
    assert core["predicted_resolution"] == "unsupported_for_current_study"
    assert core["required_clarifications"] == []


def test_out_of_scope_request_without_steps_still_builds():
    draft = {"schema_version": FACT_DRAFT_VERSION, "notes": {"unsupported": [{
        "kind": "ledger_history_deletion", "text": "erase on-chain history",
        "evidence": ev("xóa toàn bộ lịch sử giao dịch trên chain")}]}}
    core = build_core(draft, DELETION_HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=DELETION_HISTORY) == []
    assert core["predicted_resolution"] == "unsupported_for_current_study"


def test_dynamic_value_is_an_observation_and_a_question_in_phase_1():
    draft = milestone_draft()
    draft["quantities"][1]["expr"] = {"dynamic": "amount Lan decides when approving"}
    core = build_core(draft, HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=HISTORY) == []
    assert core["predicted_resolution"] == "clarification_required"
    assert [item["reason"] for item in core["unscored_observations"]] == [
        "outside_stage2b_v4_claim_taxonomy"]
    assert core["required_clarifications"]


def test_empty_draft_is_a_draft_error():
    with pytest.raises(DraftError, match="expected one first step"):
        build_core({"schema_version": FACT_DRAFT_VERSION}, HISTORY)


POLICY = "ab" * 28
SWAP = ("Minh đổi 20 ADA lấy 5 điểm GOLD của Hoa. Minh nạp 20 ADA trước 00:00 ngày "
        "05/04/2027 (UTC+7); sau đó Hoa nạp 5 GOLD trước 00:00 ngày 06/04/2027 (UTC+7). "
        "Khi đủ, Minh nhận 5 GOLD, Hoa nhận 20 ADA. Nếu Hoa không nạp, hoàn 20 ADA cho Minh. "
        f"GOLD có policy {POLICY}.")
SWAP_HISTORY = [{"version": 1, "messages": [SWAP]}]


def swap_draft(native):
    deadline = {"y": 2027, "m": 4, "h": 0, "min": 0, "tz": "+07:00"}
    return {
        "schema_version": FACT_DRAFT_VERSION,
        "parties": [{"id": "p_minh", "name": "Minh", "evidence": ev("Minh đổi 20 ADA")},
                    {"id": "p_hoa", "name": "Hoa", "evidence": ev("5 điểm GOLD của Hoa")}],
        "assets": [{"id": "a_ada", "ada": True, "evidence": ev("Minh đổi 20 ADA")},
                   {"id": "a_gold", "name": "GOLD", "native": native,
                    "evidence": ev("5 điểm GOLD", f"GOLD có policy {POLICY}")}],
        "quantities": [
            {"id": "q_ada", "expr": {"ada": "20"}, "evidence": ev("Minh nạp 20 ADA")},
            {"id": "q_gold", "expr": {"tokens": "5", "asset": "a_gold"},
             "evidence": ev("Hoa nạp 5 GOLD")}],
        "instants": [
            {"id": "i1", "expr": {"date": {**deadline, "d": 5}},
             "evidence": ev("00:00 ngày 05/04/2027 (UTC+7)")},
            {"id": "i2", "expr": {"date": {**deadline, "d": 6}},
             "evidence": ev("00:00 ngày 06/04/2027 (UTC+7)")}],
        "steps": [
            {"id": "s1", "kind": "deposit", "by": "p_minh", "into": "p_minh",
             "amount": "q_ada", "deadline": "i1", "on_timeout": "end", "then": "s2",
             "evidence": ev("Minh nạp 20 ADA")},
            {"id": "s2", "kind": "deposit", "by": "p_hoa", "into": "p_hoa",
             "amount": "q_gold", "deadline": "i2", "on_timeout": ["o_refund"],
             "then": ["o_gold", "o_ada"], "evidence": ev("Hoa nạp 5 GOLD")}],
        "outcomes": [
            {"id": "o_gold", "kind": "payment", "from_account": "p_hoa", "to": "p_minh",
             "amount": "q_gold", "evidence": ev("Minh nhận 5 GOLD")},
            {"id": "o_ada", "kind": "payment", "from_account": "p_minh", "to": "p_hoa",
             "amount": "q_ada", "evidence": ev("Hoa nhận 20 ADA")},
            {"id": "o_refund", "kind": "refund", "from_account": "p_minh", "to": "p_minh",
             "amount": "remaining", "evidence": ev("hoàn 20 ADA cho Minh")}],
        "notes": {},
    }


def test_native_token_swap_with_policy_in_source_is_accepted():
    core = build_core(swap_draft(f"native:{POLICY}/474f4c44"), SWAP_HISTORY)
    errors = validate_shadow_semantic_core(core, expected_history=SWAP_HISTORY)
    assert errors == []
    projection = project_intent_spec(core, expected_history=SWAP_HISTORY)
    full = validate_intent_spec(projection.intent_spec.to_dict(),
                                expected_history=SWAP_HISTORY, projected_core=core)
    assert classify_projection(errors, full, projection.projection_diagnostics) == "PASS"
    assert core["predicted_resolution"] == "accepted_interpretation"
    assert _values(core, "amount_token_units") == {"t_s2": 5, "o_o_gold": 5}
    assert _values(core, "amount_lovelace") == {"t_s1": 20_000_000, "o_o_ada": 20_000_000,
                                                "o_o_refund": 20_000_000}


def test_token_without_source_policy_asks_for_it():
    core = build_core(swap_draft(None), SWAP_HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=SWAP_HISTORY) == []
    assert core["predicted_resolution"] == "clarification_required"
    assert any("policy ID" in question for question in core["required_clarifications"])


def test_native_id_not_in_source_and_unit_mixing_are_draft_errors():
    draft = swap_draft("native:" + "cd" * 28 + "/474f4c44")
    draft["quantities"].append({"id": "q_mix", "expr": {"sum": ["q_ada", "q_gold"]},
                                "evidence": ev("Minh đổi 20 ADA")})
    draft["outcomes"][1]["amount"] = "q_mix"
    with pytest.raises(DraftError) as raised:
        build_core(draft, SWAP_HISTORY)
    assert {item for item, _ in raised.value.problems} == {"a_gold", "q_mix"}


RELEASE = ("Lan nạp 60 ADA cho Tú trước 00:00 ngày 02/03/2027 (UTC+7). Từ 00:00 ngày "
           "10/03/2027 (UTC+7) Tú nhận 60 ADA. Nếu có thông báo hoàn tất trước 00:00 ngày "
           "05/03/2027 (UTC+7) thì Tú nhận ngay; không thì hoàn cho Lan.")
RELEASE_HISTORY = [{"version": 1, "messages": [RELEASE]}]


def _instant(iid, day, span):
    return {"id": iid, "expr": {"date": {"y": 2027, "m": 3, "d": day, "h": 0, "min": 0,
                                         "tz": "+07:00"}}, "evidence": ev(span)}


def _release_base():
    return {
        "schema_version": FACT_DRAFT_VERSION,
        "parties": [{"id": "p_lan", "name": "Lan", "evidence": ev("Lan nạp 60 ADA cho Tú")},
                    {"id": "p_tu", "name": "Tú", "evidence": ev("Lan nạp 60 ADA cho Tú")}],
        "asset": {"ada": True, "evidence": ev("Lan nạp 60 ADA")},
        "quantities": [{"id": "q", "expr": {"ada": "60"}, "evidence": ev("Lan nạp 60 ADA")}],
        "outcomes": [{"id": "o_pay", "kind": "payment", "from_account": "p_lan", "to": "p_tu",
                      "amount": "remaining", "evidence": ev("Tú nhận 60 ADA")}],
        "notes": {},
    }


def test_wait_until_becomes_a_payment_release_time():
    draft = _release_base()
    draft["instants"] = [_instant("i1", 2, "00:00 ngày 02/03/2027 (UTC+7)"),
                         _instant("i_release", 10, "00:00 ngày 10/03/2027 (UTC+7)")]
    draft["steps"] = [
        {"id": "s1", "kind": "deposit", "by": "p_lan", "into": "p_lan", "amount": "q",
         "deadline": "i1", "on_timeout": "end", "then": "s2", "evidence": ev("Lan nạp 60 ADA")},
        {"id": "s2", "kind": "wait_until", "at": "i_release", "then": ["o_pay"],
         "evidence": ev("Từ 00:00 ngày 10/03/2027 (UTC+7) Tú nhận 60 ADA")}]
    core = build_core(draft, RELEASE_HISTORY)
    errors = validate_shadow_semantic_core(core, expected_history=RELEASE_HISTORY)
    assert errors == []
    projection = project_intent_spec(core, expected_history=RELEASE_HISTORY)
    full = validate_intent_spec(projection.intent_spec.to_dict(),
                                expected_history=RELEASE_HISTORY, projected_core=core)
    assert classify_projection(errors, full, projection.projection_diagnostics) == "PASS"
    assert set(_values(core, "payment_release_time_ms")) == {"t_s2"}


def test_notify_step_with_timeout_refund():
    draft = _release_base()
    draft["instants"] = [_instant("i1", 2, "00:00 ngày 02/03/2027 (UTC+7)"),
                         _instant("i_notice", 5, "00:00 ngày 05/03/2027 (UTC+7)")]
    draft["outcomes"].append({"id": "o_refund", "kind": "refund", "from_account": "p_lan",
                              "to": "p_lan", "amount": "remaining",
                              "evidence": ev("không thì hoàn cho Lan")})
    draft["steps"] = [
        {"id": "s1", "kind": "deposit", "by": "p_lan", "into": "p_lan", "amount": "q",
         "deadline": "i1", "on_timeout": "end", "then": "s2", "evidence": ev("Lan nạp 60 ADA")},
        {"id": "s2", "kind": "notify", "deadline": "i_notice", "then": ["o_pay"],
         "on_timeout": ["o_refund"], "evidence": ev("Nếu có thông báo hoàn tất")}]
    core = build_core(draft, RELEASE_HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=RELEASE_HISTORY) == []
    assert core["predicted_resolution"] == "accepted_interpretation"
    assert _values(core, "amount_lovelace")["o_o_refund"] == 60_000_000


def test_step_reached_by_two_paths_gets_one_scope_per_path():
    draft = milestone_draft()
    draft["steps"][1]["on_timeout"] = ["s3"]
    draft["outcomes"] = [item for item in draft["outcomes"] if item["id"] != "o_refund_all"]
    core = build_core(draft, HISTORY)
    assert validate_shadow_semantic_core(core, expected_history=HISTORY) == []
    scope_ids = {scope["scope_id"] for scope in core["behavior_scopes"]}
    assert {"t_s3", "t_s3#2", "to_s3", "to_s3#2"} <= scope_ids
    # Each path keeps its own balance: 30 ADA left after the first payout, 60 without it.
    refunds = {value for scope, value in _values(core, "amount_lovelace").items()
               if scope.startswith("o_o_refund_rest")}
    assert refunds == {30_000_000, 60_000_000}


def test_loop_between_steps_is_a_draft_error():
    draft = milestone_draft()
    draft["steps"][2]["branches"][0]["then"] = ["o_pay2", "s2"]
    with pytest.raises(DraftError, match="loops back"):
        build_core(draft, HISTORY)
