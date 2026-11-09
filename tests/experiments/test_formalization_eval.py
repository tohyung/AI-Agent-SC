"""The live eval arm sends only the prompt, records M1/M2 inputs, and resumes."""

import json

import pytest

from research.experiments import formalization_eval
from research.adapters.model_transport import ModelTransportError
from research.formalization.intent_spec import CORE_SCHEMA_VERSION_V4
from tests.synthesis.test_funded_choice_v1 import funded_choice_core as _v2_core


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
    monkeypatch.setattr(formalization_eval, "dev_prompts", lambda selected: [
        (index, f"case-{index}", prompt if index == 1 else f"{prompt} #{index}")
        for index in selected])
    created = []

    def factory(before_request):
        created.append(FakeModel(outputs, before_request))
        return created[0]

    lines = []
    code = formalization_eval.run_arm(tmp_path, factory, arm="DCF", indices=indices,
                                emit=lines.append)
    return code, created[0], lines


def test_valid_first_output_counts_for_m1_and_m2(tmp_path, monkeypatch):
    core = funded_choice_core()
    code, model, _ = _arm(tmp_path, [core], monkeypatch)
    record = json.loads((tmp_path / "case-01.json").read_text(encoding="utf-8"))
    assert code == 0 and model.llm_calls == 1
    assert record["first_pass_valid"] is True and record["final_valid"] is True
    assert record["arm"] == "DCF" and record["physical_calls"] == 1


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
        formalization_eval.dev_prompts((57,))
    with pytest.raises(ValueError):
        formalization_eval.dev_prompts((58,))
    index, case_id, prompt = formalization_eval.dev_prompts((1,))[0]
    assert index == 1 and case_id and isinstance(prompt, str)


def test_test_prompts_accept_only_the_closed_cases():
    with pytest.raises(ValueError):
        formalization_eval.test_prompts((56,))
    with pytest.raises(ValueError):
        formalization_eval.test_prompts((57,))
    assert [row[0] for row in formalization_eval.test_prompts((58, 100))] == [58, 100]


@pytest.mark.parametrize("flag", [["--test"], ["--supplement", "unused.jsonl"]])
def test_one_shot_sets_refuse_a_checkout_that_is_not_frozen(tmp_path, monkeypatch, flag):
    monkeypatch.setattr(formalization_eval, "freeze_problem", lambda: "HEAD is not tagged")
    monkeypatch.setattr(formalization_eval, "run_arm", lambda *a, **k: pytest.fail("must not run"))
    monkeypatch.setattr("sys.argv", ["eval", "--arm", "AFF", "--out-dir", str(tmp_path), *flag])
    assert formalization_eval.main() == 5


@pytest.mark.parametrize(("tags", "status", "expected"), [
    ("other\n", "", "not tagged"), ("a2-test-freeze\n", " M x.py\n", "not clean"),
    ("a2-test-freeze\n", "", None)])
def test_freeze_problem_needs_the_tag_and_a_clean_tree(monkeypatch, tags, status, expected):
    class Done:
        def __init__(self, stdout):
            self.stdout = stdout

    def run(command, **_):
        return Done(tags if "tag" in command else status)

    monkeypatch.setattr(formalization_eval.subprocess, "run", run)
    problem = formalization_eval.freeze_problem()
    assert problem is None if expected is None else expected in problem


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


def test_a2_arm_records_draft_attempts_with_the_same_metrics(tmp_path, monkeypatch):
    from research.formalization.fact_extractor import EXAMPLE_DRAFT, EXAMPLE_REQUEST

    monkeypatch.setattr(formalization_eval, "dev_prompts", lambda selected: [
        (index, f"case-{index}", EXAMPLE_REQUEST) for index in selected])
    created = []

    def factory(before_request):
        created.append(FakeModel([EXAMPLE_DRAFT], before_request))
        return created[0]

    code = formalization_eval.run_arm(tmp_path, factory, arm="AFF", indices=(1,), emit=lambda _: None)
    record = json.loads((tmp_path / "case-01.json").read_text(encoding="utf-8"))
    assert code == 0 and record["arm"] == "AFF"
    assert record["first_pass_valid"] is True and record["final_valid"] is True
    assert record["predicted_resolution"] == "accepted_interpretation"
    assert record["fact_draft_attempts"][0]["problems"] == []


def test_arm_directory_refuses_a_second_model(tmp_path, monkeypatch):
    code, _model, _lines = _arm(tmp_path, [funded_choice_core()], monkeypatch)
    assert code == 0
    record = json.loads((tmp_path / "case-01.json").read_text(encoding="utf-8"))
    assert record["model"] == "fake-model" and record["provider"] == "default"

    class OtherModel(FakeModel):
        model = "other-model"

    lines = []
    code = formalization_eval.run_arm(tmp_path, lambda before: OtherModel([], before), arm="DCF",
                                indices=(1, 2), emit=lines.append)
    assert code == 4
    assert "refusing to add other-model" in lines[0]
    assert not (tmp_path / "case-02.json").exists()


def test_state_withheld_adds_time_always_and_policy_only_for_gold():
    from research.experiments.formalization_eval import SYNTHETIC_POLICY, state_withheld
    assert state_withheld("vi-loan-L1-001", "Lan cho Tú vay 5 ADA.") == (
        "Lan cho Tú vay 5 ADA. Mọi hạn đều vào 12:00 UTC của ngày được nêu.")
    stated = state_withheld("en-swap-L1-001", "Swap 5 ADA for 2 GOLD.")
    assert "12:00 UTC" in stated and SYNTHETIC_POLICY in stated and len(SYNTHETIC_POLICY) == 56
