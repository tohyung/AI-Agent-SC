"""Research-corpus validation regression tests."""

from __future__ import annotations

from copy import deepcopy

from research.stage2a import foundation


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
