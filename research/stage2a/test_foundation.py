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
    assert stats["by_split"] == {"development": 16, "evaluation": 16}
    assert stats["by_annotation_status"] == {"draft": 32}
    first = foundation.review_queue(records)
    assert first == foundation.review_queue(list(reversed(records)))
    assert first.count("[ ] Approve") == 32
    assert "Inherits canonical interpretation from: `pay-d1`" in first
