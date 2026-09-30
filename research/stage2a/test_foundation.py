"""Research-corpus validation regression tests."""

from __future__ import annotations

from copy import deepcopy

from research.stage2a import foundation


EXPECTED_CASE_IDS = {
    "pay-d1", "pay-d1-m-recipient", "refund-d1", "refund-d1-m-missing",
    "choice-d1", "choice-d1-m-owner", "escrow-d1", "escrow-d1-m-party",
    "double-d1", "double-d1-m-deadline", "conditional-d1", "conditional-d1-m-token",
    "choice-d2-correction", "pay-d2-clarify", "escrow-d2-clarify", "double-d2-conflict",
    "pay-e1", "pay-e1-m-unit", "refund-e1", "refund-e1-m-account",
    "choice-e1", "choice-e1-m-unauthorized", "escrow-e1", "escrow-e1-m-timeout",
    "double-e1", "double-e1-m-amount", "conditional-e1", "conditional-e1-m-double",
    "refund-e2-conflict", "escrow-e2-unsupported", "choice-e2-clarify",
    "conditional-e2-conflict",
}
NEWLY_CLARIFIED = {
    "refund-d1", "choice-d1", "escrow-d1", "conditional-d1",
    "choice-d2-correction", "refund-e1", "conditional-e1",
}


def corpus():
    records = foundation.load_corpus()
    assert not foundation.validate(records)
    return deepcopy(records)


def error_with(records, text):
    assert any(text in error for error in foundation.validate(records))


def by_id(records, case_id):
    return next(record for record in records if record["case_id"] == case_id)


def test_candidate_corpus_validates_without_claiming_gold():
    records = corpus()
    assert len(records) == 32
    assert {record["annotation"]["status"] for record in records} == {"draft"}
    assert all(record["annotation"]["reviewed_by"] is None for record in records)
    assert all(record["annotation"]["adjudicated_by"] is None for record in records)


def test_duplicate_case_id_fails():
    records = corpus()
    records[1]["case_id"] = records[0]["case_id"]
    error_with(records, "duplicate case_id")


def test_invalid_split_and_group_leakage_fail():
    records = corpus()
    by_id(records, "pay-e1")["group_id"] = "pay-d1"
    error_with(records, "leaks across splits")
    by_id(records, "pay-e1")["split"] = "unknown"
    error_with(records, "invalid split")


def test_public_validation_split_and_requirement_leakage():
    records = corpus()
    assert foundation.statistics(records)["by_split"] == {
        "development": 16, "validation": 16}
    by_id(records, "pay-e1")["requirement_history"] = deepcopy(
        by_id(records, "pay-d1")["requirement_history"])
    error_with(records, "identical requirement leaks across splits")


def test_versioning_and_evidence_targets_fail():
    records = corpus()
    record = by_id(records, "choice-d2-correction")
    record["requirement_history"][1]["version"] = 3
    error_with(records, "consecutive")
    record["claims"][0]["evidence"][0]["requirement_version"] = 99
    error_with(records, "evidence target does not exist")


def test_evidence_span_must_exist_in_message():
    records = corpus()
    by_id(records, "pay-d1")["claims"][0]["evidence"][0]["span"] = "not in source"
    error_with(records, "evidence span not in message")


def test_supersession_must_have_current_later_successor():
    records = corpus()
    record = by_id(records, "choice-d2-correction")
    record["claims"][0]["superseded_by"] = "missing"
    error_with(records, "lacks current successor")
    record["claims"][0]["superseded_by"] = "new-owner"
    record["claims"][1]["evidence"][0]["requirement_version"] = 1
    error_with(records, "supersession must follow requirement chronology")


def test_accepted_critical_unresolved_claim_fails():
    records = corpus()
    by_id(records, "pay-d1")["claims"][0]["status"] = "unresolved"
    error_with(records, "accepted case has unresolved critical claim")


def test_clarification_case_must_ask_a_question():
    records = corpus()
    by_id(records, "pay-d2-clarify")["required_clarifications"] = []
    error_with(records, "clarification case has no required clarification")


def test_conflict_case_requires_conflicted_claim():
    records = corpus()
    record = by_id(records, "refund-e2-conflict")
    for claim in record["claims"]:
        claim["status"] = "explicit"
    error_with(records, "conflict case has no conflicted claim evidence")


def test_mutation_parent_and_split_relationships():
    records = corpus()
    record = by_id(records, "pay-e1-m-unit")
    record["mutation"]["parent_case_id"] = "missing"
    error_with(records, "mutation parent missing")
    record["mutation"]["parent_case_id"] = "pay-d1"
    error_with(records, "mutation parent leaks across split/group")


def test_mutation_inherits_exact_requirement_and_no_local_claims_or_scopes():
    records = corpus()
    mutation = by_id(records, "pay-e1-m-unit")
    mutation["requirement_history"][0]["messages"][0] += "!"
    error_with(records, "mutation requirement_history differs from parent")
    records = corpus()
    mutation = by_id(records, "pay-e1-m-unit")
    mutation["claims"] = deepcopy(by_id(records, "pay-e1")["claims"])
    error_with(records, "mutation must not define claims")
    records = corpus()
    mutation = by_id(records, "pay-e1-m-unit")
    mutation["behavior_scopes"] = deepcopy(by_id(records, "pay-e1")["behavior_scopes"])
    error_with(records, "mutation must not define behavior_scopes")


def test_mutation_must_have_canonical_parent_and_same_group_split_resolution():
    records = corpus()
    by_id(records, "pay-e1-m-unit")["mutation"]["parent_case_id"] = "choice-e1-m-unauthorized"
    error_with(records, "mutation parent must be canonical")
    records = corpus()
    by_id(records, "pay-e1-m-unit")["group_id"] = "other"
    error_with(records, "mutation parent leaks across split/group")
    records = corpus()
    by_id(records, "pay-e1-m-unit")["split"] = "development"
    error_with(records, "mutation parent leaks across split/group")
    records = corpus()
    by_id(records, "pay-e1-m-unit")["expected_resolution"] = "clarification_required"
    error_with(records, "mutation changes resolution")


def test_effective_interpretation_and_review_queue_show_inherited_derivation():
    records = corpus()
    by_case = {record["case_id"]: record for record in records}
    mutant = by_case["pay-e1-m-unit"]
    parent = by_case["pay-e1"]
    assert foundation.effective_claims(mutant, by_case) == parent["claims"]
    assert foundation.effective_scopes(mutant, by_case) == parent["behavior_scopes"]
    review = foundation.review_queue(records)
    section = review.split("## pay-e1-m-unit ", 1)[1].split("\n## ", 1)[0]
    assert "Critical claims (inherited from pay-e1)" in section
    assert "Assumptions/derivations (inherited from pay-e1)" in section
    assert "amount_lovelace=250000000" in section
    assert "scope=deposit-1" in section
    assert "wrong_unit_scaling" in section
    assert "expected_semantic_difference" in section


def test_claim_conflict_is_scoped_to_branch():
    records = corpus()
    case = by_id(records, "choice-e1")
    refund = next(claim for claim in case["claims"] if claim["claim_id"] == "c4-timeout")
    refund["value"] = "Bob"
    assert not foundation.validate(records)
    refund["scope_id"] = "decision-1:reject"
    error_with(records, "active claim values conflict for refund_recipient")


def test_scope_registry_rejects_missing_duplicate_and_malformed_references():
    records = corpus()
    by_id(records, "choice-e1")["claims"][0]["scope_id"] = "missing-scope"
    error_with(records, "scope_id not found")
    records = corpus()
    case = by_id(records, "choice-e1")
    case["behavior_scopes"].append(deepcopy(case["behavior_scopes"][0]))
    error_with(records, "duplicate scope_id")
    records = corpus()
    case = by_id(records, "choice-e1")
    branch = next(scope for scope in case["behavior_scopes"]
                  if scope["scope_type"] == "branch")
    branch.pop("decision_id")
    error_with(records, "branch requires decision_id")
    records = corpus()
    case = by_id(records, "choice-e1")
    timeout = next(scope for scope in case["behavior_scopes"]
                   if scope["scope_type"] == "timeout")
    timeout["deadline_claim_id"] = "missing-deadline"
    error_with(records, "deadline_claim_id does not reference a claim")
    timeout["deadline_claim_id"] = "c5"
    timeout.pop("timeout_id")
    error_with(records, "timeout_id is required")


def test_scope_type_and_supersession_identity_are_checked():
    records = corpus()
    by_id(records, "pay-d1")["behavior_scopes"][0]["scope_type"] = "invalid"
    error_with(records, "invalid scope_type")
    records = corpus()
    case = by_id(records, "choice-d2-correction")
    case["claims"][0]["scope_id"] = "decision-1:approve"
    error_with(records, "lacks current successor")


def test_global_scope_cannot_hide_a_local_payment_claim():
    records = corpus()
    case = by_id(records, "pay-d1")
    case["behavior_scopes"].append({"scope_id": "global", "scope_type": "global"})
    payment = next(claim for claim in case["claims"] if claim["kind"] == "payment_recipient")
    payment["scope_id"] = "global"
    error_with(records, "branch/transition fact cannot be global")


def test_cross_split_identical_requirement_fails():
    records = corpus()
    by_id(records, "pay-e1")["requirement_history"] = deepcopy(
        by_id(records, "pay-d1")["requirement_history"])
    error_with(records, "identical requirement leaks across splits")


def test_annotation_review_cannot_be_fabricated():
    records = corpus()
    by_id(records, "pay-d1")["annotation"]["status"] = "reviewed"
    error_with(records, "non-draft annotation lacks reviewer")
    by_id(records, "pay-d1")["annotation"]["status"] = "draft"
    by_id(records, "pay-d1")["annotation"]["reviewed_by"] = "unknown"
    error_with(records, "draft annotation cannot claim human review")


def test_ground_truth_source_tracks_annotation_status():
    records = corpus()
    annotation = by_id(records, "pay-d1")["annotation"]
    annotation["ground_truth_source"] = "expert_adjudicated"
    error_with(records, "ground_truth_source does not match annotation status")
    annotation["ground_truth_source"] = "arbitrary"
    error_with(records, "ground_truth_source does not match annotation status")
    annotation["status"] = "reviewed"
    annotation["reviewed_by"] = "fixture-reviewer"
    annotation["ground_truth_source"] = "reviewed_research_annotation"
    assert not foundation.validate(records)


def test_malformed_json_types_report_validation_errors():
    records = corpus()
    by_id(records, "pay-d1")["claims"][0]["status"] = []
    error_with(records, "invalid status")
    records = corpus()
    by_id(records, "pay-d1")["case_id"] = []
    error_with(records, "invalid case_id")


def test_derived_financial_claim_requires_normalization_basis():
    records = corpus()
    by_id(records, "pay-d1")["claims"][2].pop("normalization_basis")
    error_with(records, "financial derivation lacks basis")


def test_stats_and_review_queue_are_deterministic():
    records = corpus()
    stats = foundation.statistics(records)
    assert stats["by_split"] == {"development": 16, "validation": 16}
    assert stats["by_annotation_status"] == {"draft": 32}
    first = foundation.review_queue(records)
    assert first == foundation.review_queue(list(reversed(records)))
    assert first.count("[ ] Approve") == 32
    assert "Inherits canonical interpretation from: `pay-d1`" in first


def test_adjudication_preserves_all_cases_and_draft_metadata():
    records = corpus()
    assert {record["case_id"] for record in records} == EXPECTED_CASE_IDS
    assert foundation.statistics(records)["by_split"] == {
        "development": 16, "validation": 16}
    assert foundation.statistics(records)["by_resolution"] == {
        "accepted_interpretation": 12,
        "clarification_required": 16,
        "conflict_requires_resolution": 3,
        "unsupported_for_current_study": 1,
    }
    assert all(record["annotation"] == {
        "status": "draft", "authored_by": "codex", "reviewed_by": None,
        "adjudicated_by": None,
        "ground_truth_source": "candidate_research_annotation",
        "notes": record["annotation"]["notes"],
    } for record in records)
    assert all(record["expected_resolution"] != "rejected" for record in records)


def test_seven_canonical_cases_are_clarification_required_without_invented_answers():
    records = corpus()
    for case_id in NEWLY_CLARIFIED:
        record = by_id(records, case_id)
        assert record["mutation"] is None
        assert record["expected_resolution"] == "clarification_required"
        assert record["required_clarifications"]
        assert record["annotation"]["status"] == "draft"
    assert any("giải ngân" in q for q in by_id(records, "refund-d1")["required_clarifications"])
    assert any("không approve" in q for q in by_id(records, "choice-d1")["required_clarifications"])
    assert any("nạp" in q for q in by_id(records, "escrow-d1")["required_clarifications"])
    assert any("Notify" in q for q in by_id(records, "refund-e1")["required_clarifications"])


def test_all_mutations_inherit_updated_parent_and_remain_partial_checks():
    records = corpus()
    by_case = {record["case_id"]: record for record in records}
    mutations = [record for record in records if record["mutation"] is not None]
    assert len(mutations) == 12
    for record in mutations:
        parent = by_case[record["mutation"]["parent_case_id"]]
        assert parent["mutation"] is None
        assert record["requirement_history"] == parent["requirement_history"]
        assert record["expected_resolution"] == parent["expected_resolution"]
        assert record["required_clarifications"] == parent["required_clarifications"]
        assert record["claims"] == []
        assert record["behavior_scopes"] == []
        assert foundation.effective_claims(record, by_case) == parent["claims"]
        assert foundation.effective_scopes(record, by_case) == parent["behavior_scopes"]
    assert "Observation unresolved" in " ".join(
        by_case["conditional-e1-m-double"]["behavior_expectations"]["terminal_outcomes"])
    assert "disbursement/success path unresolved" in " ".join(
        by_case["refund-d1-m-missing"]["behavior_expectations"]["terminal_outcomes"])


def test_new_timeout_refund_scopes_and_exact_evidence():
    records = corpus()
    for case_id in ("escrow-d2-clarify", "choice-e2-clarify"):
        record = by_id(records, case_id)
        scopes = {scope["scope_id"]: scope for scope in record["behavior_scopes"]}
        timeout = scopes["decision-1:timeout"]
        assert timeout["scope_type"] == "timeout"
        assert timeout["deadline_claim_id"] == "choice-deadline"
        refund = next(c for c in record["claims"] if c["claim_id"] == "refund-recipient")
        assert refund["scope_id"] == "decision-1:timeout"
        evidence = refund["evidence"][0]
        source = record["requirement_history"][evidence["requirement_version"] - 1][
            "messages"][evidence["message_index"]]
        assert evidence["span"] in source


def test_missing_account_owner_and_notify_observation_are_not_invented():
    records = corpus()
    for case_id in ("pay-d2-clarify", "escrow-d2-clarify", "choice-e2-clarify"):
        record = by_id(records, case_id)
        assert not any(c["kind"] == "destination_account_owner" for c in record["claims"])
        assert any("account" in q for q in record["required_clarifications"])
    assert not any(c["kind"] == "depositing_party"
                   for c in by_id(records, "pay-d2-clarify")["claims"])
    for case_id in ("conditional-d1", "conditional-e1"):
        record = by_id(records, case_id)
        assert not any("observation" in c["kind"].lower() for c in record["claims"])
        assert any("Observation" in q for q in record["required_clarifications"])
        assert record["behavior_expectations"]["accepted_traces"] == []
    escrow = by_id(records, "escrow-d1")
    assert not any(c["kind"] == "deposit_deadline_ms" for c in escrow["claims"])
    assert next(c["value"] for c in escrow["claims"]
                if c["kind"] == "choice_deadline_ms") == 6000


def test_new_claim_values_and_scopes_are_source_grounded():
    records = corpus()
    expectations = {
        "choice-d1": {"amount": (12000000, "deposit-1"),
                      "choice-deadline": (4000, "decision-1")},
        "double-d1": {"account-owner": ("Alice", "deposit-1"),
                      "amount": (7000000, "deposit-1"),
                      "release-recipient": ("Bob", "decision-1:approve")},
        "choice-d2-correction": {"amount": (2000000, "decision-1:approve")},
        "escrow-e1": {"amount": (11000000, "deposit-1"),
                      "deposit-deadline": (16000, "deposit-1"),
                      "choice-deadline": (16000, "decision-1")},
        "escrow-e2-unsupported": {"amount": (3000000, "auto-refund-timeout-1"),
                                  "refund-recipient": ("Lan", "auto-refund-timeout-1")},
        "conditional-e2-conflict": {"amount": (17000000, "notify-1:success")},
    }
    for case_id, claims in expectations.items():
        record = by_id(records, case_id)
        by_claim = {claim["claim_id"]: claim for claim in record["claims"]}
        scope_ids = {scope["scope_id"] for scope in record["behavior_scopes"]}
        for claim_id, (value, scope_id) in claims.items():
            claim = by_claim[claim_id]
            assert (claim["value"], claim["scope_id"]) == (value, scope_id)
            assert scope_id in scope_ids
            assert all(item["span"] in record["requirement_history"][
                item["requirement_version"] - 1]["messages"][item["message_index"]]
                for item in claim["evidence"])


def test_review_queue_shows_updated_clarification_and_inherited_mutation():
    records = corpus()
    review = foundation.review_queue(records)
    parent = review.split("## choice-d1 ", 1)[1].split("\n## ", 1)[0]
    mutant = review.split("## choice-d1-m-owner ", 1)[1].split("\n## ", 1)[0]
    assert "Proposed resolution: `clarification_required`" in parent
    assert "không approve hoặc reject trước POSIX 4000" in parent
    assert "amount_lovelace=12000000" in parent
    assert "choice_deadline_ms=4000" in parent
    assert "Critical claims (inherited from choice-d1)" in mutant
    assert "Proposed resolution: `clarification_required`" in mutant
    assert "không approve hoặc reject trước POSIX 4000" in mutant
    assert "Decision: [ ] Approve  [ ] Edit  [ ] Reject" in parent
    assert "Decision: [ ] Approve  [ ] Edit  [ ] Reject" in mutant
