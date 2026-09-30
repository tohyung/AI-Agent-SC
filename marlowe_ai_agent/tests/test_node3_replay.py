from __future__ import annotations

import json

import pytest

from bench import node3_replay
from conftest import FakeSMTBackend


@pytest.mark.parametrize(("truth", "old_pass", "decision", "expected"), [
    (True, True, "pass", "both_correct"),
    (True, True, "fail", "old_only_correct"),
    (True, False, "pass", "new_only_correct"),
    (True, False, "fail", "both_wrong"),
    (False, True, "pass", "both_wrong"),
    (False, True, "fail", "new_only_correct"),
    (False, False, "pass", "old_only_correct"),
    (False, False, "fail", "both_correct"),
])
def test_disagreement_truth_table(truth, old_pass, decision, expected):
    assert node3_replay._disagreement(truth, old_pass, decision) == expected


def test_disagreement_special_states():
    assert node3_replay._disagreement(None, True, "pass") == "ground_truth_unavailable"
    assert node3_replay._disagreement(True, None, "pass") == "ground_truth_unavailable"
    assert node3_replay._disagreement(None, True, "inconclusive") == "ground_truth_unavailable"
    assert node3_replay._disagreement(True, True, "inconclusive") == "inconclusive"


@pytest.mark.parametrize("filename", [
    "vi-rental_deposit-L3-003-full.json",
    "vi-milestone-L4-003-full.json",
])
def test_stale_audit_truth_is_recomputed_with_current_evaluator(filename):
    row, detail = node3_replay.replay(node3_replay.AUDIT / filename,
                                      node3_replay._case_index(), FakeSMTBackend(["valid"]))

    assert row["persisted_ground_truth"] == "false"
    assert row["ground_truth"] == "true"
    assert row["ground_truth_changed"] == "true"
    assert row["current_scenario_accuracy"] == 1.0
    assert row["current_overall_accuracy"] == 1.0
    assert row["choice_name_fallback_count"] == 2
    assert row["disagreement_type"] == "both_correct"
    assert detail["ground_truth"] is True

    record = json.loads((node3_replay.AUDIT / filename).read_text(encoding="utf-8"))
    evaluation = node3_replay.evaluate(
        node3_replay._case_index()[record["case_id"]], record["contract"],
        status=record["status"],
    )
    assert evaluation["strict_correct"] is True
    assert evaluation["false_convergence"] is False


def test_replay_uses_current_evaluator_not_persisted_truth(monkeypatch, tmp_path):
    def current_evaluation(case, contract, status):
        assert status == "blocked"
        return {"strict_correct": True, "scenario_accuracy": 1.0, "overall_accuracy": 1.0,
                "diagnostics": {"choice_name_fallback_count": 0}}

    monkeypatch.setattr(node3_replay, "evaluate", current_evaluation)
    case = next(iter(node3_replay._case_index().values()))
    path = tmp_path / "current-evaluator-full.json"
    path.write_text(json.dumps({"case_id": case.id, "contract": "close", "status": "blocked",
                                "evaluation": {"strict_correct": False}}), encoding="utf-8")

    row, _ = node3_replay.replay(path, {case.id: case}, FakeSMTBackend(["valid"]))
    assert row["persisted_ground_truth"] == "false"
    assert row["ground_truth"] == "true"
    assert row["ground_truth_changed"] == "true"
    assert row["disagreement_type"] == "both_correct"
    assert node3_replay._confusion([row], "new_decision")["true_accept"] == 1
    assert node3_replay._confusion([row], "new_decision")["false_accept"] == 0


def test_missing_contract_never_falls_back_to_persisted_truth(tmp_path):
    path = tmp_path / "missing-full.json"
    path.write_text(json.dumps({"case_id": "missing", "contract": None,
                                "evaluation": {"strict_correct": True}}), encoding="utf-8")

    row, detail = node3_replay.replay(path, {})
    assert row["ground_truth"] == ""
    assert row["persisted_ground_truth"] == "true"
    assert row["ground_truth_changed"] == ""
    assert row["current_scenario_accuracy"] == ""
    assert row["current_overall_accuracy"] == ""
    assert row["choice_name_fallback_count"] == ""
    assert row["disagreement_type"] == "ground_truth_unavailable"
    assert detail["ground_truth"] is None


def test_missing_case_id_with_contract_fails_loudly(tmp_path):
    path = tmp_path / "unknown-full.json"
    path.write_text(json.dumps({"case_id": "not-in-dataset", "contract": "close",
                                "evaluation": {"strict_correct": True}}), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown-full.json.*not-in-dataset"):
        node3_replay.replay(path, {})


def test_duplicate_case_ids_fail_loudly(monkeypatch):
    case = next(iter(node3_replay._case_index().values()))
    monkeypatch.setattr(node3_replay, "load_cases", lambda: [case, case])
    with pytest.raises(ValueError, match="Duplicate case ID.*" + case.id):
        node3_replay._case_index()
