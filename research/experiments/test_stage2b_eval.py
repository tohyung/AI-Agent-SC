"""The live eval arm sends only the prompt, records M1/M2 inputs, and resumes."""

import json

import pytest

from research.experiments import stage2b_eval
from research.integrations.model_transport import ModelTransportError
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V4
from research.stage3.test_funded_choice_v1 import funded_choice_core as _v2_core


def funded_choice_core():
    core = _v2_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V4
    return core


class FakeModel:
    model = "fake-model"

    def __init__(self, outputs, before_request):
        self.outputs = list(outputs)
        self.before_request = before_request
        self.llm_calls = 0
        self.call_log = []
        self.users = []

    def set_call_budget(self, limit):
        pass

    def usage_summary(self):
        return {}

    def generate(self, system, user):
        self.before_request("generation")
        self.llm_calls += 1
        self.users.append(user)
        item = self.outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return json.loads(json.dumps(item))


def _arm(tmp_path, outputs, monkeypatch, indices=(1,)):
    prompt = funded_choice_core()["requirement_history"][0]["messages"][0]
    monkeypatch.setattr(stage2b_eval, "dev_prompts", lambda selected: [
        (index, f"case-{index}", prompt if index == 1 else f"{prompt} #{index}")
        for index in selected])
    created = []

    def factory(before_request):
        created.append(FakeModel(outputs, before_request))
        return created[0]

    lines = []
    code = stage2b_eval.run_arm(tmp_path, factory, arm="BASE", indices=indices,
                                emit=lines.append)
    return code, created[0], lines


def test_valid_first_output_counts_for_m1_and_m2(tmp_path, monkeypatch):
    core = funded_choice_core()
    code, model, _ = _arm(tmp_path, [core], monkeypatch)
    record = json.loads((tmp_path / "case-01.json").read_text(encoding="utf-8"))
    assert code == 0 and model.llm_calls == 1
    assert record["first_pass_valid"] is True and record["final_valid"] is True
    assert record["arm"] == "BASE" and record["physical_calls"] == 1


def test_invalid_first_output_is_not_m1_even_if_repaired(tmp_path, monkeypatch):
    broken = funded_choice_core()
    broken["claims"][0]["evidence"][0]["span"] = "fabricated span"
    code, model, _ = _arm(tmp_path, [broken, funded_choice_core()], monkeypatch)
    record = json.loads((tmp_path / "case-01.json").read_text(encoding="utf-8"))
    assert code == 0 and record["first_pass_valid"] is False
    assert record["first_pass_error_count"] >= 1 and record["physical_calls"] >= 2


def test_provider_limit_stops_without_record_and_resume_skips_done(tmp_path, monkeypatch):
    limit = ModelTransportError("provider_limit", "generation")
    code, _, lines = _arm(tmp_path, [funded_choice_core(), limit], monkeypatch, indices=(1, 2))
    assert code == 3 and (tmp_path / "case-01.json").exists()
    assert not (tmp_path / "case-02.json").exists()
    assert "provider_limit" in lines[-1]
    code, model, _ = _arm(tmp_path, [funded_choice_core()] * 4, monkeypatch, indices=(1, 2))
    assert code == 0 and (tmp_path / "case-02.json").exists()
    assert all("#2" in user for user in model.users)


def test_dev_prompts_reject_test_and_contaminated_cases():
    with pytest.raises(ValueError):
        stage2b_eval.dev_prompts((57,))
    with pytest.raises(ValueError):
        stage2b_eval.dev_prompts((58,))
    index, case_id, prompt = stage2b_eval.dev_prompts((1,))[0]
    assert index == 1 and case_id and isinstance(prompt, str)


def test_network_failure_stops_without_record(tmp_path, monkeypatch):
    failure = ModelTransportError("provider_request_failed", "generation")
    code, _, lines = _arm(tmp_path, [failure], monkeypatch)
    assert code == 3 and not (tmp_path / "case-01.json").exists()
    assert "provider_request_failed" in lines[-1]


def test_invalid_model_json_is_a_recorded_model_result(tmp_path, monkeypatch):
    failure = ModelTransportError("invalid_json_after_repair", "model_output_parse",
                                  content_received=True, repair_attempted=True)
    code, _, _ = _arm(tmp_path, [failure], monkeypatch)
    record = json.loads((tmp_path / "case-01.json").read_text(encoding="utf-8"))
    assert code == 0 and record["run_status"] == "FAILED"
