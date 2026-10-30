"""Offline, source-grounded variants; production never loads this corpus."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from research.stage2b.core_draft import (DRAFT_FIELDS, collapse_automatic_success_branches,
                                         connect_skipped_terminal_outcomes,
                                         drop_dangling_amount_derivations,
                                         drop_decision_to_own_branch_or_timeout,
                                         drop_explicitly_absent_refund_recipient,
                                         drop_resolved_time_format_questions,
                                         normalize_clarification_question_aliases,
                                         normalize_choice_metadata,
                                         normalize_grounded_numeric_amounts,
                                         normalize_vietnamese_noon_deadlines,
                                         prune_unverifiable_evidence,
                                         materialize_core_draft,
                                         retarget_unique_evidence_spans)
from research.stage2b.intent_spec import (CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4,
                                         validate_shadow_semantic_core)
from research.stage2b.repair_policy import diagnostic_code, diagnostic_codes
from research.stage2b.shadow_extractor import (IntentShadowExtractor, _calendar_hints,
                                                build_prompt)


CORPUS = Path(__file__).parent / "fixtures" / "semantic_variants.jsonl"
VARIANTS = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines()]


def test_evidence_retarget_requires_a_unique_verbatim_source_message():
    wrong = {"requirement_version": 2, "message_index": 0,
             "span": "below 50", "relation": "supports"}
    ambiguous = {"requirement_version": 3, "message_index": 0,
                 "span": "ADA", "relation": "supports"}
    core = {"claims": [{"evidence": [ambiguous]}], "behavior_scopes": [{
        "choice_guard": {"source_evidence": [wrong]}}]}
    messages = {(1, 0): "below 50, refund ADA", (2, 0): "deposit ADA"}
    actions = retarget_unique_evidence_spans(core, messages)
    assert len(actions) == 1
    assert wrong["requirement_version"] == 1
    assert wrong["message_index"] == 0
    assert wrong["span"] == "below 50"
    assert ambiguous["requirement_version"] == 3


def test_evidence_case_only_difference_canonicalizes_unique_exact_source_span():
    evidence = {"requirement_version": 1, "message_index": 0,
                "span": "người này sends money", "relation": "supports"}
    core = {"claims": [{"evidence": [evidence]}], "behavior_scopes": []}
    messages = {(1, 0): "Người này sends money before the stated deadline."}

    actions = retarget_unique_evidence_spans(core, messages)

    assert len(actions) == 1
    assert actions[0]["kind"] == "unique_casefold_evidence_canonicalization"
    assert evidence["span"] == "Người này sends money"
    assert evidence["requirement_version"] == 1
    assert evidence["message_index"] == 0


def test_evidence_case_only_difference_is_not_guessed_when_source_match_is_ambiguous():
    evidence = {"requirement_version": 2, "message_index": 0,
                "span": "người gửi", "relation": "supports"}
    core = {"claims": [{"evidence": [evidence]}], "behavior_scopes": []}
    messages = {(1, 0): "Người gửi trước; Người gửi sau."}

    actions = retarget_unique_evidence_spans(core, messages)

    assert actions == []
    assert evidence == {"requirement_version": 2, "message_index": 0,
                        "span": "người gửi", "relation": "supports"}


def test_choice_metadata_normalization_requires_exact_source_and_matching_scope():
    evidence = {"requirement_version": 1, "message_index": 0,
                "span": "at least 50", "relation": "explicit"}
    core = {"behavior_scopes": [{"scope_id": "branch", "scope_type": "branch",
             "choice_guard": {"operator": "ge", "value": 50,
                              "source_evidence": [evidence]}}],
            "claims": [{"claim_id": "guard", "kind": "choice_guard", "scope_id": "branch",
                        "value": {"operator": "ge", "value": 50}},
                       {"claim_id": "different", "kind": "choice_guard", "scope_id": "branch",
                        "value": {"operator": "lt", "value": 50}}]}
    actions = normalize_choice_metadata(core, {(1, 0): "pay at least 50"})
    assert {item["kind"] for item in actions} == {
        "choice_evidence_relation", "redundant_choice_metadata_claim"}
    assert evidence["relation"] == "supports"
    assert [item["claim_id"] for item in core["claims"]] == ["different"]
    evidence["relation"] = "explicit"
    assert normalize_choice_metadata(core, {(1, 0): "unrelated"}) == []
    assert evidence["relation"] == "explicit"


def test_v4_unknown_structural_claim_is_dropped_only_when_metadata_matches():
    core = {"schema_version": CORE_SCHEMA_VERSION_V4,
            "behavior_scopes": [{"scope_id": "branch", "scope_type": "branch",
                                 "choice_guard": {"operator": "eq", "value": 1,
                                                  "source_evidence": []}}],
            "claims": [
                {"claim_id": "mirror", "kind": "branch_guard", "scope_id": "branch",
                 "value": {"operator": "eq", "value": 1}},
                {"claim_id": "different", "kind": "branch_guard", "scope_id": "branch",
                 "value": {"operator": "eq", "value": 0}},
            ]}
    assert normalize_choice_metadata(core, {}) == [
        {"kind": "redundant_choice_metadata_claim", "claim_id": "mirror"}]
    assert [claim["claim_id"] for claim in core["claims"]] == ["different"]


def test_v4_choice_guard_citation_can_drop_only_false_prefix():
    source = "An được chọn số nguyên 1 nếu hủy chuyến hoặc 0 nếu xác nhận đã đi xong."
    evidence = {"requirement_version": 2, "message_index": 0,
                "span": "số nguyên 0 nếu xác nhận đã đi xong", "relation": "supports"}
    core = {"schema_version": CORE_SCHEMA_VERSION_V4,
            "behavior_scopes": [{"scope_id": "confirm", "scope_type": "branch",
                                 "choice_guard": {"operator": "eq", "value": 0,
                                                  "source_evidence": [evidence]}}],
            "claims": []}
    assert normalize_choice_metadata(core, {(2, 0): source}) == [
        {"kind": "choice_guard_exact_suffix", "scope_id": "confirm"}]
    assert evidence["span"] == "0 nếu xác nhận đã đi xong"
    evidence["span"] = "số nguyên 0 nếu xác nhận đã đi xong"
    assert normalize_choice_metadata(core, {(2, 0): source + " " + source}) == []
    assert evidence["span"] == "số nguyên 0 nếu xác nhận đã đi xong"


def draft_for(row):
    return {
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        ],
        "claims": deepcopy(row["claims"]),
        "required_clarifications": [],
        "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }


@pytest.mark.parametrize("row", VARIANTS, ids=lambda row: row["id"])
def test_source_grounded_draft_corpus(row):
    draft = draft_for(row)
    original = deepcopy(draft)
    core, actions = materialize_core_draft(draft, row["history"], CORE_SCHEMA_VERSION_V3)
    assert draft == original
    assert set(draft) == DRAFT_FIELDS
    assert core["requirement_history"] == row["history"]
    assert core["claims"][0]["value"] == row["expected_value"]
    assert bool(actions) is (type(row["expected_value"]) is int)
    assert (len(validate_shadow_semantic_core(
        core, expected_history=row["history"])) == 0) is row["expected_valid"]


def test_compact_model_draft_materializes_without_second_model_call():
    row = VARIANTS[0]

    class DraftModel:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return draft_for(row)

    model = DraftModel()
    extractor = IntentShadowExtractor(model, core_schema_version=CORE_SCHEMA_VERSION_V3)
    core = extractor.extract(row["history"])
    assert model.calls == 1
    assert core.to_dict()["claims"][0]["value"] == 101_000_000
    assert extractor.normalization_actions[0]["claim_id"] == "principal"
    system, user = build_prompt(row["history"], core_schema_version=CORE_SCHEMA_VERSION_V3)
    assert "five internal draft fields" in system
    assert "five internal draft fields" in user


def test_legacy_full_core_and_unbacked_draft_are_never_rewritten():
    row = VARIANTS[1]
    full = {"schema_version": CORE_SCHEMA_VERSION_V3,
            "requirement_history": deepcopy(row["history"]), **draft_for(row)}
    result, actions = materialize_core_draft(full, row["history"], CORE_SCHEMA_VERSION_V3)
    assert result == full and actions == []
    compact, actions = materialize_core_draft(draft_for(row), row["history"],
                                              CORE_SCHEMA_VERSION_V3)
    assert compact["claims"][0]["value"] == "101 ADA" and actions == []


def test_normalization_preserves_source_backed_supersession():
    row = VARIANTS[0]
    draft = draft_for(row)
    draft["claims"] = [
        {"claim_id": "old", "kind": "amount_lovelace", "value": "102 ADA",
         "criticality": "financial", "status": "superseded", "scope_id": "deposit",
         "superseded_by": "principal",
         "evidence": [{"requirement_version": 1, "message_index": 0,
                       "span": "102 ADA", "relation": "supports"}]},
        {**draft["claims"][0], "status": "user_confirmed"},
    ]
    core, actions = materialize_core_draft(draft, row["history"], CORE_SCHEMA_VERSION_V3)
    assert [item["value"] for item in core["claims"]] == [102_000_000, 101_000_000]
    assert [item["status"] for item in core["claims"]] == ["superseded", "user_confirmed"]
    assert len(actions) == 2
    assert validate_shadow_semantic_core(core, expected_history=row["history"]) == []


def test_timezone_iso_deadline_requires_the_same_instant_in_source():
    span = "23:59 on 15 January 2027 in Vietnam time (ICT, UTC+7)"
    history = [{"version": 1, "messages": [f"Liam deposits by {span}."]}]
    draft = {
        "behavior_scopes": [{"scope_id": "global", "scope_type": "global"},
                            {"scope_id": "deposit", "scope_type": "transition",
                             "transition_kind": "deposit"}],
        "claims": [{"claim_id": "deadline", "kind": "deposit_deadline_ms",
                    "value": "2027-01-15T23:59:00+07:00", "criticality": "financial",
                    "status": "explicit", "scope_id": "deposit",
                    "evidence": [{"requirement_version": 1, "message_index": 0,
                                  "span": span, "relation": "supports"}]}],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }
    expected = int(datetime(2027, 1, 15, 23, 59,
                            tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
    core, actions = materialize_core_draft(draft, history, CORE_SCHEMA_VERSION_V3)
    assert core["claims"][0]["value"] == expected
    assert core["claims"][0]["status"] == "derived"
    assert actions[0]["source_literal"] == span
    assert validate_shadow_semantic_core(core, expected_history=history) == []
    wrong = deepcopy(draft)
    wrong["claims"][0]["value"] = "2027-01-16T23:59:00+07:00"
    core, actions = materialize_core_draft(wrong, history, CORE_SCHEMA_VERSION_V3)
    assert core["claims"][0]["value"] == wrong["claims"][0]["value"]
    assert actions == []


def test_repair_codes_are_invariants_not_case_specific_strings():
    errors = ["scope deposit-1: invalid continuation_scope_id",
              "scope deposit-2: invalid continuation_scope_id",
              "claim first: invalid evidence target/span",
              "claim second: invalid evidence target/span"]
    assert diagnostic_codes(errors) == ["SCOPE_GRAPH", "SOURCE_EVIDENCE"]
    assert diagnostic_code("claim amount: invalid derived_from source claim") == "PROVENANCE_LINK"


def test_compact_draft_prunes_only_unreachable_empty_duplicate_outcome():
    history = [{"version": 1, "messages": ["Deposit 1 ADA, then pay twice."]}]
    draft = {
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit",
             "continuation_scope_id": "pay-1"},
            {"scope_id": "pay-1", "scope_type": "transition", "transition_kind": "payment",
             "continuation_scope_id": "pay-2"},
            {"scope_id": "orphan", "scope_type": "terminal_outcome", "outcome_id": "paid-1",
             "parent_scope_id": "pay-1", "continuation_scope_id": "pay-2"},
            {"scope_id": "pay-2", "scope_type": "transition", "transition_kind": "payment",
             "continuation_scope_id": "final"},
            {"scope_id": "final", "scope_type": "terminal_outcome", "outcome_id": "paid-2",
             "parent_scope_id": "pay-2"},
        ],
        "claims": [{"claim_id": "deposit-amount", "kind": "amount_lovelace",
                    "value": 1_000_000, "criticality": "financial", "status": "explicit",
                    "scope_id": "deposit", "evidence": [{"requirement_version": 1,
                    "message_index": 0, "span": "Deposit 1 ADA", "relation": "supports"}]}],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }
    original = deepcopy(draft)
    core, actions = materialize_core_draft(draft, history, CORE_SCHEMA_VERSION_V4)
    assert draft == original
    assert "orphan" not in {scope["scope_id"] for scope in core["behavior_scopes"]}
    assert actions == [{"scope_id": "orphan", "kind": "unreachable_duplicate_outcome",
                        "reason": "no references; parent already continues to same successor"}]

    with_claim = deepcopy(draft)
    with_claim["claims"].append({"claim_id": "outcome-claim", "kind": "payment_recipient",
                                 "value": "Paul", "scope_id": "orphan"})
    retained, actions = materialize_core_draft(with_claim, history, CORE_SCHEMA_VERSION_V4)
    assert "orphan" in {scope["scope_id"] for scope in retained["behavior_scopes"]}
    assert actions == []

    with_reference = deepcopy(draft)
    with_reference["required_clarifications"] = [{"scope_id": "orphan"}]
    retained, actions = materialize_core_draft(with_reference, history, CORE_SCHEMA_VERSION_V4)
    assert "orphan" in {scope["scope_id"] for scope in retained["behavior_scopes"]}
    assert actions == []

    initial = deepcopy(draft)
    initial["behavior_scopes"][1].pop("continuation_scope_id")

    class RepairModel:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return (initial if self.calls == 1 else
                    {"behavior_scopes": draft["behavior_scopes"]})

    model = RepairModel()
    extractor = IntentShadowExtractor(model, core_schema_version=CORE_SCHEMA_VERSION_V4)
    repaired, initial_errors = extractor.extract_with_validation_feedback(
        history, max_repairs=1)
    assert initial_errors
    assert extractor.validation_errors(repaired, history) == []
    assert model.calls == 2
    assert extractor.normalization_actions[-1]["scope_id"] == "orphan"

    missing_amount = deepcopy(repaired.to_dict())
    missing_amount["claims"] = []
    assert "scope deposit: deposit amount claim missing" in validate_shadow_semantic_core(
        missing_amount, expected_history=history)


def test_deposit_success_cannot_invent_choice_branch():
    history = [{"version": 1, "messages": ["Maya deposits, then Paul is paid."]}]
    core = {
        "schema_version": CORE_SCHEMA_VERSION_V4, "requirement_history": history,
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit",
             "continuation_scope_id": "fake-branch"},
            {"scope_id": "fake-branch", "scope_type": "branch", "branch_id": "success",
             "decision_id": "deposit", "continuation_scope_id": "payment"},
            {"scope_id": "payment", "scope_type": "transition", "transition_kind": "payment"},
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }
    errors = validate_shadow_semantic_core(core, expected_history=history)
    assert "scope fake-branch: branch decision must be choice or notify" in errors
    assert "scope deposit: invalid continuation_scope_id" in errors
    system, _ = build_prompt(history, core_schema_version=CORE_SCHEMA_VERSION_V4)
    assert "Deposit success continues directly" in system


def test_english_named_dates_are_available_to_deadline_repair():
    history = [{"version": 1, "messages": [
        "Deposit before 10 February 2027, then release on 17 February 2027."]}]
    hints = _calendar_hints(history)
    assert [(item["source_span"], item["calendar_date"]) for item in hints] == [
        ("10 February 2027", "2027-02-10"),
        ("17 February 2027", "2027-02-17"),
    ]


def test_named_dates_with_explicit_shared_timezone_normalize_wrong_model_epoch():
    spans = ["before 10 February 2027 at 12:00 noon, Da Nang time (UTC+7)",
             "no earlier than 17 February 2027 at 12:00 noon",
             "no earlier than 24 February 2027 at 12:00 noon"]
    message = ". ".join(spans) + ". Both releases use the same timezone."
    history = [{"version": 1, "messages": [message]}]
    draft = {
        "behavior_scopes": [{"scope_id": "global", "scope_type": "global"}],
        "claims": [{"claim_id": f"time-{day}",
                    "kind": "deposit_deadline_ms" if day == 10 else "payment_release_time_ms",
                    "value": int(datetime(2024, 2, day, 5, tzinfo=timezone.utc).timestamp() * 1000),
                    "status": "explicit", "scope_id": "global",
                    "evidence": [{"requirement_version": 1, "message_index": 0,
                                  "span": span, "relation": "supports"}]}
                   for day, span in zip((10, 17, 24), spans)],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }
    core, actions = materialize_core_draft(draft, history, CORE_SCHEMA_VERSION_V4)
    assert [claim["value"] for claim in core["claims"]] == [
        int(datetime(2027, 2, day, 5, tzinfo=timezone.utc).timestamp() * 1000)
        for day in (10, 17, 24)]
    assert len(actions) == 3
    assert all(claim["status"] == "derived" for claim in core["claims"])

    ambiguous = deepcopy(history)
    ambiguous[0]["messages"][0] += " Another event uses UTC+8."
    ambiguous_draft = deepcopy(draft)
    ambiguous_draft["claims"] = [claim for claim in draft["claims"]
                                 if claim["claim_id"] == "time-17"]
    unchanged, actions = materialize_core_draft(ambiguous_draft, ambiguous,
                                                 CORE_SCHEMA_VERSION_V4)
    assert unchanged["claims"][0]["value"] == draft["claims"][1]["value"]
    assert actions == []


def test_only_grounded_resolved_posix_conversion_questions_are_removed():
    core = {
        "claims": [{"kind": "deposit_deadline_ms", "value": 1802235600000,
                    "status": "derived", "normalization_basis": "source-grounded instant"}],
        "required_clarifications": [
            {"question": "What is the exact POSIX millisecond deadline for the deposit?"}],
        "unscored_observations": [],
        "predicted_resolution": "clarification_required",
    }
    assert drop_resolved_time_format_questions(core) == 1
    assert core["required_clarifications"] == []
    assert core["predicted_resolution"] == "accepted_interpretation"

    unresolved = deepcopy(core)
    unresolved["claims"][0].pop("normalization_basis")
    unresolved["required_clarifications"] = [
        {"question": "What is the exact POSIX millisecond deadline for the deposit?"}]
    unresolved["predicted_resolution"] = "clarification_required"
    assert drop_resolved_time_format_questions(unresolved) == 0
    assert unresolved["predicted_resolution"] == "clarification_required"

    business = deepcopy(core)
    business["required_clarifications"] = [
        {"question": "Who receives the payment?"},
        {"question": "What is the exact POSIX millisecond deadline for the deposit?"},
    ]
    business["predicted_resolution"] = "clarification_required"
    assert drop_resolved_time_format_questions(business) == 1
    assert business["required_clarifications"] == [
        {"question": "Who receives the payment?"}]
    assert business["predicted_resolution"] == "clarification_required"


def test_posix_question_text_alias_is_normalized_and_resolved_without_model_repair():
    row = VARIANTS[0]
    core, _ = materialize_core_draft(draft_for(row), row["history"],
                                     CORE_SCHEMA_VERSION_V3)
    core["claims"][0]["kind"] = "deposit_deadline_ms"
    core["claims"][0]["value"] = 1800162000000
    core["claims"][0]["normalization_basis"] = "source-grounded instant"
    core["required_clarifications"] = [{
        "question_text": "Please confirm the exact POSIX millisecond timestamp for the deadline."}]
    core["predicted_resolution"] = "clarification_required"

    class Model:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return core

    model = Model()
    extractor = IntentShadowExtractor(model, core_schema_version=CORE_SCHEMA_VERSION_V3)
    result, _ = extractor.extract_with_validation_feedback(row["history"], max_repairs=0)
    assert model.calls == 1
    assert result.to_dict()["required_clarifications"] == []
    assert result.to_dict()["predicted_resolution"] == "accepted_interpretation"
    assert [action["kind"] for action in extractor.normalization_actions] == [
        "clarification_question_aliases", "resolved_time_format_questions"]


def test_question_alias_preserves_business_clarification():
    core = {"claims": [{"kind": "deposit_deadline_ms", "value": 1800162000000,
                        "status": "derived", "normalization_basis": "source-grounded instant"}],
            "required_clarifications": [{"question_text": "Who receives the payment?"}],
            "unscored_observations": [], "predicted_resolution": "clarification_required"}
    assert normalize_clarification_question_aliases(core) == 1
    assert drop_resolved_time_format_questions(core) == 0
    assert core["required_clarifications"] == [{"question": "Who receives the payment?"}]
    assert core["predicted_resolution"] == "clarification_required"


def test_resolved_time_does_not_require_user_to_convert_to_posix():
    core = {"claims": [{"claim_id": "deadline", "kind": "deposit_deadline_ms",
                        "value": 1800248400000, "status": "derived",
                        "normalization_basis": "source-grounded instant"}],
            "required_clarifications": [{
                "question": "Mốc chót nạp tiền tương ứng mốc POSIX mili-giây nào?",
                "linked_claim_ids": ["deadline"]}],
            "unscored_observations": [], "predicted_resolution": "clarification_required"}
    assert drop_resolved_time_format_questions(core) == 1
    assert core["predicted_resolution"] == "accepted_interpretation"


def test_resolved_actor_deadline_removes_its_linked_business_question():
    core = {
        "claims": [
            {"claim_id": "deadline", "kind": "deposit_deadline_ms",
             "value": 1800792000000, "status": "derived",
             "normalization_basis": "unique actor-scoped source deadline"},
            {"claim_id": "explicit-deadline", "kind": "deposit_deadline_ms",
             "value": 1800187200000, "status": "explicit"},
        ],
        "required_clarifications": [{
            "clarification_id": "clarify-deadline",
            "unresolved_claim_ids": ["deadline"],
            "question": ("Trang phải nạp trước giờ chót nào (giờ, ngày, múi giờ) "
                         "để đúng bảy ngày sau hạn đầu?")}],
        "unscored_observations": [{"reason": "irrelevant_context"}],
        "predicted_resolution": "clarification_required",
    }

    assert drop_resolved_time_format_questions(core) == 1
    assert core["required_clarifications"] == []
    assert core["predicted_resolution"] == "accepted_interpretation"


def test_irrelevant_observation_does_not_keep_resolved_format_question_open():
    core = {"claims": [{"kind": "deposit_deadline_ms", "value": 1800248400000,
                        "status": "derived", "normalization_basis": "source-grounded instant"}],
            "required_clarifications": [{"question": "What is the exact POSIX millisecond deadline?"}],
            "unscored_observations": [{"reason": "irrelevant_context"}],
            "predicted_resolution": "clarification_required"}
    assert drop_resolved_time_format_questions(core) == 1
    assert core["predicted_resolution"] == "accepted_interpretation"


def test_choice_branch_decision_link_makes_continuation_edge_redundant():
    core = {"behavior_scopes": [
        {"scope_id": "choice", "scope_type": "transition",
         "transition_kind": "choice", "continuation_scope_id": "approve"},
        {"scope_id": "approve", "scope_type": "branch", "decision_id": "choice",
         "continuation_scope_id": "paid"},
        {"scope_id": "paid", "scope_type": "terminal_outcome",
         "parent_scope_id": "approve"}]}
    assert drop_decision_to_own_branch_or_timeout(core) == ["choice"]
    assert "continuation_scope_id" not in core["behavior_scopes"][0]
    assert core["behavior_scopes"][1]["continuation_scope_id"] == "paid"


def test_choice_timeout_decision_link_is_not_success_continuation():
    core = {"schema_version": CORE_SCHEMA_VERSION_V4, "behavior_scopes": [
        {"scope_id": "choice", "scope_type": "transition", "transition_kind": "choice",
         "continuation_scope_id": "expiry"},
        {"scope_id": "cancel", "scope_type": "branch", "decision_id": "choice",
         "continuation_scope_id": "refund"},
        {"scope_id": "expiry", "scope_type": "timeout", "decision_id": "choice",
         "continuation_scope_id": "refund"},
        {"scope_id": "refund", "scope_type": "terminal_outcome"}]}
    assert drop_decision_to_own_branch_or_timeout(core) == ["choice"]
    assert "continuation_scope_id" not in core["behavior_scopes"][0]
    assert core["behavior_scopes"][2]["continuation_scope_id"] == "refund"


def test_deposit_to_own_timeout_is_not_silently_removed():
    core = {"behavior_scopes": [
        {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit",
         "continuation_scope_id": "expiry"},
        {"scope_id": "expiry", "scope_type": "timeout", "decision_id": "deposit"}]}
    assert drop_decision_to_own_branch_or_timeout(core) == []
    assert core["behavior_scopes"][0]["continuation_scope_id"] == "expiry"


def test_automatic_deposit_success_branch_collapses_but_timeout_remains():
    core = {"behavior_scopes": [
        {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        {"scope_id": "success", "scope_type": "branch", "decision_id": "deposit",
         "branch_id": "success", "continuation_scope_id": "paid"},
        {"scope_id": "timeout", "scope_type": "timeout", "decision_id": "deposit"},
        {"scope_id": "paid", "scope_type": "terminal_outcome",
         "parent_scope_id": "success"}], "claims": []}
    assert collapse_automatic_success_branches(core) == ["success"]
    assert core["behavior_scopes"][0]["continuation_scope_id"] == "paid"
    assert core["behavior_scopes"][1]["decision_id"] == "deposit"
    assert core["behavior_scopes"][2]["parent_scope_id"] == "deposit"

    dependent = {"behavior_scopes": [
        {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        {"scope_id": "success", "scope_type": "branch", "decision_id": "deposit",
         "branch_id": "success", "continuation_scope_id": "paid"},
        {"scope_id": "paid", "scope_type": "terminal_outcome",
         "parent_scope_id": "success"}],
        "claims": [{"scope_id": "success"}]}
    assert collapse_automatic_success_branches(dependent) == []


def test_sole_unguarded_deposit_branch_collapses_regardless_of_label():
    core = {"behavior_scopes": [
        {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        {"scope_id": "automatic", "scope_type": "branch", "decision_id": "deposit",
         "branch_id": "both-deposited", "continuation_scope_id": "paid"},
        {"scope_id": "paid", "scope_type": "terminal_outcome",
         "parent_scope_id": "automatic"}], "claims": []}
    assert collapse_automatic_success_branches(core) == ["automatic"]
    assert core["behavior_scopes"][0]["continuation_scope_id"] == "paid"
    assert core["behavior_scopes"][1]["parent_scope_id"] == "deposit"


def test_automatic_branch_without_successor_uses_its_unique_terminal_child():
    core = {"behavior_scopes": [
        {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        {"scope_id": "success", "scope_type": "branch", "decision_id": "deposit",
         "branch_id": "on-time"},
        {"scope_id": "paid", "scope_type": "terminal_outcome",
         "parent_scope_id": "success"}], "claims": []}

    assert collapse_automatic_success_branches(core) == ["success"]
    assert core["behavior_scopes"] == [
        {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit",
         "continuation_scope_id": "paid"},
        {"scope_id": "paid", "scope_type": "terminal_outcome",
         "parent_scope_id": "deposit"},
    ]


def test_guarded_deposit_branch_is_not_collapsed():
    core = {"behavior_scopes": [
        {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        {"scope_id": "conditional", "scope_type": "branch", "decision_id": "deposit",
         "branch_id": "success", "choice_guard": {"operator": "eq", "value": 1},
         "continuation_scope_id": "paid"},
        {"scope_id": "paid", "scope_type": "terminal_outcome",
         "parent_scope_id": "conditional"}], "claims": []}
    assert collapse_automatic_success_branches(core) == []


def test_skipped_payment_outcome_with_claims_is_connected():
    core = {"behavior_scopes": [
        {"scope_id": "payment", "scope_type": "transition", "transition_kind": "payment",
         "continuation_scope_id": "next"},
        {"scope_id": "outcome", "scope_type": "terminal_outcome",
         "parent_scope_id": "payment", "continuation_scope_id": "next"},
        {"scope_id": "next", "scope_type": "transition", "transition_kind": "choice"}],
        "claims": [{"claim_id": "recipient", "scope_id": "outcome"}]}
    assert connect_skipped_terminal_outcomes(core) == ["outcome"]
    assert core["behavior_scopes"][0]["continuation_scope_id"] == "outcome"
    assert connect_skipped_terminal_outcomes(core) == []


def test_terminal_outcome_with_one_child_connects_continuation():
    core = {"behavior_scopes": [
        {"scope_id": "first", "scope_type": "terminal_outcome",
         "outcome_id": "first"},
        {"scope_id": "second", "scope_type": "terminal_outcome",
         "outcome_id": "second", "parent_scope_id": "first"}],
        "claims": [{"claim_id": "second-recipient", "scope_id": "second"}]}

    assert connect_skipped_terminal_outcomes(core) == ["second"]
    assert core["behavior_scopes"][0]["continuation_scope_id"] == "second"
    assert connect_skipped_terminal_outcomes(core) == []


def test_skipped_unclaimed_or_nonpayment_outcome_is_not_connected():
    for transition_kind, claims in (("payment", []),
                                     ("deposit", [{"scope_id": "outcome"}])):
        core = {"behavior_scopes": [
            {"scope_id": "event", "scope_type": "transition",
             "transition_kind": transition_kind, "continuation_scope_id": "next"},
            {"scope_id": "outcome", "scope_type": "terminal_outcome",
             "parent_scope_id": "event", "continuation_scope_id": "next"},
            {"scope_id": "next", "scope_type": "transition", "transition_kind": "choice"}],
            "claims": claims}
        assert connect_skipped_terminal_outcomes(core) == []
        assert core["behavior_scopes"][0]["continuation_scope_id"] == "next"


def test_numeric_amount_string_requires_matching_source_ada_amount():
    messages = {(1, 0): "Trang nộp 119 ADA cho hợp đồng."}
    core = {"claims": [{"claim_id": "amount", "kind": "amount_lovelace",
                        "value": "119000000", "status": "explicit",
                        "evidence": [{"requirement_version": 1, "message_index": 0,
                                      "span": "119 ADA", "relation": "supports"}]}]}
    assert len(normalize_grounded_numeric_amounts(core, messages)) == 1
    assert core["claims"][0]["value"] == 119_000_000
    assert core["claims"][0]["status"] == "derived"
    wrong = deepcopy(core)
    wrong["claims"][0]["value"] = "120000000"
    assert normalize_grounded_numeric_amounts(wrong, messages) == []
    assert wrong["claims"][0]["value"] == "120000000"

    breakdown = deepcopy(core)
    breakdown["claims"][0]["value"] = "83000000"
    breakdown["claims"][0]["evidence"][0]["span"] = (
        "83 ADA, gồm 75 ADA gốc và 8 ADA thêm")
    breakdown_messages = {(1, 0): "Trả 83 ADA, gồm 75 ADA gốc và 8 ADA thêm."}
    assert len(normalize_grounded_numeric_amounts(breakdown, breakdown_messages)) == 1
    assert breakdown["claims"][0]["value"] == 83_000_000
    wrong_component = deepcopy(breakdown)
    wrong_component["claims"][0]["value"] = "75000000"
    assert normalize_grounded_numeric_amounts(wrong_component, breakdown_messages) == []


def test_dangling_amount_derivation_removed_only_with_direct_amount_evidence():
    messages = {(1, 0): "Chuyển 75 ADA cho Yến."}
    claim = {"claim_id": "payment", "kind": "amount_lovelace", "value": 75_000_000,
             "status": "derived", "derived_from": "missing",
             "evidence": [{"requirement_version": 1, "message_index": 0,
                           "span": "75 ADA", "relation": "supports"}]}
    core = {"claims": [claim]}
    assert len(drop_dangling_amount_derivations(core, messages)) == 1
    assert "derived_from" not in claim
    unsupported = deepcopy(claim)
    unsupported["derived_from"] = "missing"
    unsupported["value"] = 76_000_000
    assert drop_dangling_amount_derivations({"claims": [unsupported]}, messages) == []

    different_span = {"claim_id": "deposit", "kind": "amount_lovelace",
                      "value": 75_000_000, "status": "explicit",
                      "evidence": [{"requirement_version": 1, "message_index": 0,
                                    "span": "Tú nạp 75 ADA", "relation": "supports"}]}
    payout = deepcopy(claim)
    payout["derived_from"] = "deposit"
    payout["evidence"][0]["span"] = "Chuyển 75 ADA cho Yến"
    both_messages = {(1, 0): "Tú nạp 75 ADA. Chuyển 75 ADA cho Yến."}
    assert len(drop_dangling_amount_derivations(
        {"claims": [different_span, payout]}, both_messages)) == 1
    assert "derived_from" not in payout

    same_span = deepcopy(claim)
    same_span["derived_from"] = "deposit"
    same_span["evidence"][0]["span"] = "Tú nạp 75 ADA"
    assert drop_dangling_amount_derivations(
        {"claims": [different_span, same_span]}, both_messages) == []
    assert same_span["derived_from"] == "deposit"


def test_unverifiable_span_can_be_removed_only_with_other_valid_support():
    messages = {(1, 0): "Chuyển 119 ADA cho Vân."}
    valid = {"requirement_version": 1, "message_index": 0,
             "span": "cho Vân", "relation": "supports"}
    invalid = dict(valid, span="Vân nhận tiền")
    core = {"claims": [{"claim_id": "recipient", "kind": "payment_recipient",
                        "value": "Vân", "status": "explicit",
                        "evidence": [invalid, valid]}]}
    assert prune_unverifiable_evidence(core, messages) == [
        {"claim_id": "recipient", "kind": "unverifiable_evidence", "removed_count": 1}]
    assert core["claims"][0]["evidence"] == [valid]
    unsupported = deepcopy(core)
    unsupported["claims"][0]["evidence"] = [invalid]
    assert prune_unverifiable_evidence(unsupported, messages) == []
    assert unsupported["claims"][0]["evidence"] == [invalid]


def test_vietnamese_noon_deadlines_resolve_only_from_exact_cited_time_and_zone():
    message = ("Nộp trước 12 giờ trưa ngày 18/01/2027, giờ Đà Nẵng (UTC+7). "
               "Xác nhận trước 12 giờ trưa ngày 25/01/2027, cùng múi giờ đó.")
    spans = ["12 giờ trưa ngày 18/01/2027, giờ Đà Nẵng (UTC+7)",
             "12 giờ trưa ngày 25/01/2027, cùng múi giờ đó"]
    core = {"claims": [
        {"claim_id": str(index), "kind": "deposit_deadline_ms", "value": None,
         "status": "unresolved", "evidence": [{"requirement_version": 1,
         "message_index": 0, "span": span, "relation": "supports"}]}
        for index, span in enumerate(spans)]}
    actions = normalize_vietnamese_noon_deadlines(core, {(1, 0): message})
    assert len(actions) == 2
    assert [claim["value"] for claim in core["claims"]] == [
        int(datetime(2027, 1, day, 5, tzinfo=timezone.utc).timestamp() * 1000)
        for day in (18, 25)]
    assert all(claim["status"] == "derived" for claim in core["claims"])
    core["required_clarifications"] = [{
        "claim_id": "0", "question": "Khoảng thời gian nộp tiền kết thúc chính xác là lúc nào?"},
        {"claim_id": "1", "question": "Hạn chót xác nhận chính xác là lúc nào?"}]
    core["predicted_resolution"] = "clarification_required"
    core["unscored_observations"] = []
    assert drop_resolved_time_format_questions(core) == 2
    assert core["predicted_resolution"] == "accepted_interpretation"

    ungrounded = deepcopy(core)
    ungrounded["claims"][0]["value"] = None
    ungrounded["claims"][0]["evidence"][0]["span"] = "12 giờ trưa ngày 19/01/2027"
    assert normalize_vietnamese_noon_deadlines(ungrounded, {(1, 0): message}) == []
    assert ungrounded["claims"][0]["value"] is None

    seconds_span = "12:00:00 trưa ngày 19/01/2027 giờ Đà Nẵng (UTC+7)"
    seconds_core = {"claims": [{"claim_id": "deadline", "kind": "deposit_deadline_ms",
                                "value": "1737262800000", "status": "user_confirmed",
                                "evidence": [{"requirement_version": 1, "message_index": 0,
                                              "span": seconds_span, "relation": "supports"}]}]}
    assert len(normalize_vietnamese_noon_deadlines(
        seconds_core, {(1, 0): seconds_span})) == 1
    assert seconds_core["claims"][0]["value"] == int(
        datetime(2027, 1, 19, 5, tzinfo=timezone.utc).timestamp() * 1000)


def test_recipient_and_observation_repair_preserves_other_claims_and_graph():
    message = "Maya deposits. Without a deposit, close without paying Paul."
    history = [{"version": 1, "messages": [message]}]
    draft = {
        "behavior_scopes": [{"scope_id": "global", "scope_type": "global"}],
        "claims": [
            {"claim_id": "asset", "kind": "asset", "value": "ADA",
             "status": "explicit", "criticality": "financial", "scope_id": "global",
             "evidence": [{"requirement_version": 1, "message_index": 0,
                           "span": "Maya deposits", "relation": "supports"}]},
            {"claim_id": "refund", "kind": "refund_recipient", "value": "none",
             "status": "explicit", "criticality": "financial", "scope_id": "global",
             "evidence": [{"requirement_version": 1, "message_index": 0,
                           "span": "close without paying Paul", "relation": "supports"}]},
        ],
        "required_clarifications": [],
        "unscored_observations": [{"observation_id": "obs", "text": "No deposit",
                                   "reason": "irrelevant_context", "source_evidence": [
                                       {"requirement_version": 1, "message_index": 0,
                                        "span": "noncontiguous text", "relation": "supports"}]}],
        "predicted_resolution": "accepted_interpretation",
    }

    class RepairModel:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return draft if self.calls == 1 else {
                "claim_evidence_or_drop": {"refund": None},
                "observation_or_drop": {"obs": None}}

    model = RepairModel()
    extractor = IntentShadowExtractor(model, core_schema_version=CORE_SCHEMA_VERSION_V4)
    repaired, initial_errors = extractor.extract_with_validation_feedback(
        history, max_repairs=1)
    assert "invalid unscored_observation" in initial_errors
    assert "claim refund: explicit recipient absent from cited evidence" in initial_errors
    assert extractor.validation_errors(repaired, history) == []
    assert [claim["claim_id"] for claim in repaired.to_dict()["claims"]] == ["asset"]
    assert model.calls == 2
    assert extractor.repair_trace[0]["repair_kind"] == "SOURCE_EVIDENCE"


def test_absent_refund_sentinel_normalizes_only_with_explicit_negation():
    negative = "If no deposit arrives, close; do not create a refund payment or recipient."
    history = [{"version": 1, "messages": [negative]}]
    full = {
        "schema_version": CORE_SCHEMA_VERSION_V4, "requirement_history": history,
        "behavior_scopes": [{"scope_id": "global", "scope_type": "global"}],
        "claims": [{"claim_id": "refund", "kind": "refund_recipient", "value": "none",
                    "status": "explicit", "criticality": "financial", "scope_id": "global",
                    "evidence": [{"requirement_version": 1, "message_index": 0,
                                  "span": "do not create a refund payment or recipient",
                                  "relation": "supports"}]}],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }

    class FullModel:
        def generate(self, _system, _user):
            return full

    extractor = IntentShadowExtractor(FullModel(), core_schema_version=CORE_SCHEMA_VERSION_V4)
    core, errors = extractor.extract_with_validation_feedback(history, max_repairs=0)
    assert errors == []
    assert core.to_dict()["claims"] == []
    assert extractor.normalization_actions[-1]["claim_id"] == "refund"
    assert full["claims"][0]["value"] == "none"

    positive = deepcopy(full)
    positive["requirement_history"] = [{"version": 1, "messages": ["Refund Maya."]}]
    positive["claims"][0]["evidence"][0]["span"] = "Refund Maya"
    messages = {(1, 0): "Refund Maya."}
    assert drop_explicitly_absent_refund_recipient(positive, messages) == []
    assert len(positive["claims"]) == 1


def test_missing_deposit_amount_repairs_only_its_source_backed_claim():
    history = [{"version": 1, "messages": ["Maya deposits 113 ADA."]}]
    draft = {
        "behavior_scopes": [{"scope_id": "global", "scope_type": "global"},
                            {"scope_id": "deposit", "scope_type": "transition",
                             "transition_kind": "deposit"}],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }

    class AmountModel:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return draft if self.calls == 1 else {"new_claims": [{
                "claim_id": "deposit-amount", "kind": "amount_lovelace",
                "value": 113_000_000, "status": "derived", "criticality": "financial",
                "scope_id": "deposit", "normalization_basis": "113 ADA to lovelace",
                "evidence": [{"requirement_version": 1, "message_index": 0,
                              "span": "113 ADA", "relation": "supports"}],
            }]}

    model = AmountModel()
    extractor = IntentShadowExtractor(model, core_schema_version=CORE_SCHEMA_VERSION_V4)
    core, initial_errors = extractor.extract_with_validation_feedback(history, max_repairs=1)
    assert initial_errors == ["scope deposit: deposit amount claim missing"]
    assert extractor.validation_errors(core, history) == []
    assert core.to_dict()["claims"][0]["value"] == 113_000_000
    assert model.calls == 2
    assert extractor.repair_trace[0]["repair_kind"] == "CLAIM_COMPLETENESS"
