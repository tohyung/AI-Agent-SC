"""Offline AFF rebuild: exact when draft problems are unchanged, flagged otherwise."""

from copy import deepcopy

from research.experiments.formalization_eval import MAX_REPAIRS, aff_result_fields
from research.experiments.formalization_rebuild import _RecordedDrafts, rebuild_record
from research.formalization.fact_extractor import extract_fact_core
from tests.formalization import test_fact_builder as tb


def _record(drafts):
    result = extract_fact_core(_RecordedDrafts(drafts), tb.HISTORY, max_repairs=MAX_REPAIRS)
    return {"case_index": 1, "case_id": "c1", "physical_calls": len(drafts),
            **aff_result_fields(result)}


def test_rebuild_with_unchanged_builder_reproduces_the_record():
    broken = tb.milestone_draft()
    broken["outcomes"][1]["amount"] = "q_total"  # overpays: one repair round
    record = _record([broken, tb.milestone_draft()])
    assert len(record["fact_draft_attempts"]) == 2 and record["final_valid"]
    rebuilt = rebuild_record(record, tb.MESSAGE)
    assert rebuilt["rebuild_mismatch"] is False
    assert {key: rebuilt[key] for key in record} == record


def test_rebuild_flags_a_case_whose_draft_problems_would_differ():
    record = _record([tb.milestone_draft()])
    tampered = deepcopy(record)
    tampered["fact_draft_attempts"][0]["problems"] = [["q_total", "recorded otherwise"]]
    rebuilt = rebuild_record(tampered, tb.MESSAGE)
    assert rebuilt["rebuild_mismatch"] is True
    assert rebuilt["semantic_core"] == tampered["semantic_core"]


def test_model_error_records_are_copied_unchanged():
    record = {"case_index": 1, "semantic_status": "MODEL_ERROR", "safe_error": {"code": "x"}}
    assert rebuild_record(record, tb.MESSAGE) == record
