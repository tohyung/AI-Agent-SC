"""Roleplay case runner must reuse the same model candidate after a restart."""

from copy import deepcopy
import json

import pytest

from research.experiments import roleplay_main_case
from research.integrations.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V3
from research.stage3.test_funded_choice_v1 import funded_choice_core


def test_remaining_cases_preserve_frozen_batch_identity():
    _, first = roleplay_main_case.load_batch()
    assert roleplay_main_case._case_at(20) == first[-1]
    assert roleplay_main_case._case_at(21)["id"] == "vi-vesting-L2-003"
    assert roleplay_main_case._case_at(100)["id"] == "vi-infeasible-L3-005"
    with pytest.raises(ValueError, match="outside frozen"):
        roleplay_main_case._case_at(101)


def test_roleplay_resume_keeps_only_requirement_answers():
    history = [{"version": 1, "messages": ["Initial"]},
               {"version": 2, "messages": ["Bình sẽ nạp 20 ADA."]}]
    transcript = [{"question": "Ai nạp?", "answer": "Bình sẽ nạp 20 ADA.",
                   "synthetic_assumption": True},
                  {"question": "Review trace?", "answer": "dong y",
                   "synthetic_assumption": True}]
    assert roleplay_main_case._source_transcript(history, transcript) == transcript[:1]


def test_interrupted_outbound_attempt_number_is_never_reused(tmp_path):
    (tmp_path / "attempt-001.json").write_text("{}", encoding="utf-8")
    (tmp_path / "outbound-attempts.jsonl").write_text(
        '{"attempt": 2, "phase": "generation"}\n', encoding="utf-8")
    assert roleplay_main_case._next_attempt(tmp_path) == 3


@pytest.mark.parametrize("needs_repair", [False, True])
def test_restarting_reviewed_case_replays_candidate_without_new_calls(
        monkeypatch, tmp_path, needs_repair):
    core = funded_choice_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V3
    prompt = core["requirement_history"][0]["messages"][0]
    monkeypatch.setattr(roleplay_main_case, "load_batch", lambda: ({}, [{"id": "case-1",
                                                                     "prompt": prompt}]))
    monkeypatch.setattr(roleplay_main_case, "config_from_environment", lambda: None)
    monkeypatch.setattr("research.integrations.smt_gate.analyze", lambda *_a, **_k: {
        "status": "Valid", "warnings": [], "analysis_notes": [],
        "meta": {"upstream_commit": UPSTREAM_COMMIT, "driver_version": DRIVER_VERSION},
    })

    class FakeTransport:
        model = "fake"
        total_calls = 0
        core_calls = 0

        def __init__(self, *, before_request, **_kwargs):
            self.before_request = before_request
            self.llm_calls = 0
            self.call_log = []

        def set_call_budget(self, _limit):
            pass

        def generate(self, system, _user):
            self.before_request("generation")
            self.llm_calls += 1
            FakeTransport.total_calls += 1
            if "Generate one canonical Marlowe" in system:
                return {"contract": "close", "mapping_evidence": []}
            FakeTransport.core_calls += 1
            if needs_repair and FakeTransport.core_calls == 1:
                invalid = deepcopy(core)
                invalid["claims"] = None
                return invalid
            return deepcopy(core)

        def usage_summary(self):
            return {"api_calls": self.llm_calls}

    monkeypatch.setattr(roleplay_main_case, "ModelTransport", FakeTransport)
    first = roleplay_main_case.run_case(
        1, repair_attempts=int(needs_repair), run_dir=tmp_path)
    candidate_id = first["stages"]["intent_extraction"]["output_artifacts"][0]
    assert first["status"] == "WAITING_RESEARCH_REVIEW"
    first_calls = 2 if needs_repair else 1
    assert FakeTransport.total_calls == first_calls
    assert bool(first["candidate"]["initial_core_validation_errors"]) is needs_repair

    second = roleplay_main_case.run_case(1, reviewed_candidate_id=candidate_id,
                                         run_dir=tmp_path)
    assert second["status"] == "SIMULATED_CANDIDATE_ONLY"
    assert second["stages"]["intent_extraction"]["output_artifacts"][0] == candidate_id
    assert second["model_usage_this_attempt"]["api_calls"] == 1
    assert FakeTransport.total_calls == first_calls + 1
    contract_id = second["stages"]["compile"]["output_artifacts"][0]

    third = roleplay_main_case.run_case(1, reviewed_candidate_id=candidate_id,
                                        replay_contract_id=contract_id,
                                        run_dir=tmp_path)
    assert third["status"] == "SIMULATED_CANDIDATE_ONLY"
    assert third["stages"]["compile"]["output_artifacts"] == [contract_id]
    assert third["model_usage_this_attempt"]["api_calls"] == 0
    assert FakeTransport.total_calls == first_calls + 1


def test_repair_reuses_exact_invalid_candidate_without_rewriting_it(monkeypatch, tmp_path):
    core = funded_choice_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V3
    prompt = core["requirement_history"][0]["messages"][0]
    monkeypatch.setattr(roleplay_main_case, "load_batch", lambda: ({}, [
        {"id": "case-1", "prompt": prompt}]))
    monkeypatch.setattr(roleplay_main_case, "config_from_environment", lambda: None)

    class FakeTransport:
        model = "fake-repair"

        def __init__(self, *, before_request, **_kwargs):
            self.before_request = before_request
            self.llm_calls = 0
            self.call_log = []

        def set_call_budget(self, _limit):
            pass

        def generate(self, _system, _user):
            self.before_request("generation")
            self.llm_calls += 1
            return deepcopy(core)

        def usage_summary(self):
            return {"api_calls": self.llm_calls}

    monkeypatch.setattr(roleplay_main_case, "ModelTransport", FakeTransport)
    invalid = deepcopy(core)
    invalid["claims"] = None
    case_dir = tmp_path / "case-01"
    case_dir.mkdir()
    invalid_id = "intent-candidate:test-invalid"
    first = {"case_id": "case-1", "requirement_history": core["requirement_history"],
             "simulation_transcript": [],
             "candidate": {"semantic_core": invalid,
                           "initial_core_validation_errors": ["claims must be a list"]},
             "stages": {"intent_extraction": {"output_artifacts": [invalid_id]}},
             "artifacts": {invalid_id: {"payload": None}}}
    first["artifacts"][invalid_id]["payload"] = first["candidate"]
    roleplay_main_case._write_exclusive(case_dir / "attempt-001.json", first)
    repaired = roleplay_main_case.run_case(
        1, repair_candidate_id=invalid_id, repair_attempts=1, run_dir=tmp_path)
    assert repaired["status"] == "WAITING_RESEARCH_REVIEW"
    assert repaired["replayed_core_candidate_id"] == invalid_id
    assert repaired["model_usage_this_attempt"]["api_calls"] == 1
    assert repaired["stages"]["intent_extraction"]["output_artifacts"] != [invalid_id]
    assert first == json.loads(
        (case_dir / "attempt-001.json").read_text(encoding="utf-8"))
