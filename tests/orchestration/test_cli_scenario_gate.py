"""The CLI scenario gate: situations in words, read back, then run (E7, Q-KỊCH BẢN 2-3)."""

import sys
from pathlib import Path

from research.adapters.model_transport import ModelTransportError
from research.orchestration.cli_runner import scenario_gate
from research.synthesis.example_scenarios import to_expectation
from tests.synthesis.test_example_scenarios import CORE

ROOT = Path(__file__).resolve().parents[2]
REPLY = {"scenarios": [
    {"name": "paid", "steps": [{"do": "deposit", "party": "Ngọc", "ada": "40", "before": "D1"},
                               {"do": "press", "before": "D2"}],
     "receive": [{"party": "Lâm", "ada": "40"}]},
    {"name": "nobody", "steps": [{"do": "deposit", "party": "Ngọc", "ada": "40", "before": "D1"},
                                 {"do": "wait", "past": "D2"}],
     "receive": [{"party": "Ngọc", "ada": "40"}]}]}


class ScenarioModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, system, user):
        self.prompts.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _run(model, answers):
    shown, asked = [], []
    replies = iter(answers)

    def ask(question):
        asked.append(question)
        return next(replies)

    result = scenario_gate(CORE, {"claims": []}, model, ask, shown.append)
    return result, "\n".join(shown), asked


def test_situations_in_words_become_confirmed_expectations():
    model = ScenarioModel(REPLY)
    (expectations, stop), shown, asked = _run(
        model, ["Ngọc nạp 40 ADA rồi có người bấm thì Lâm nhận 40 ADA; không ai bấm thì Ngọc "
                "lấy lại tiền.", "dong y"])
    assert stop is None and len(expectations) == 2
    assert "xin mô tả 2 đến 4 tình huống" in shown
    assert "Tôi sẽ kiểm tra hợp đồng bằng các tình huống bạn mô tả:" in shown
    assert "Kết quả: Lâm 40 ADA." in shown and "{" not in shown
    assert "Ngọc nạp 40 ADA rồi" in model.prompts[0]
    assert expectations[0]["expected_payments"][0]["amount"] == 40_000_000
    assert expectations[1]["request"]["transactions"][-1]["inputs"] == []


def test_a_correction_is_added_to_the_examples_and_converted_again():
    model = ScenarioModel(REPLY, REPLY)
    (expectations, stop), _shown, _asked = _run(
        model, ["Ngọc nạp, có người bấm.", "Lâm phải nhận đủ 40 ADA", "dong y"])
    assert stop is None and len(expectations) == 2
    assert "Lâm phải nhận đủ 40 ADA" in model.prompts[1]


def test_an_empty_answer_skips_the_gate_without_a_model_call():
    model = ScenarioModel()
    (expectations, stop), _shown, asked = _run(model, [""])
    assert (expectations, stop) == ([], None) and model.prompts == [] and len(asked) == 1


def test_unconvertible_situations_stop_after_two_rounds():
    model = ScenarioModel({"x": 1}, {"x": 1})
    (expectations, stop), shown, _asked = _run(model, ["abc", "def"])
    assert expectations is None and stop == "scenarios_not_confirmed"
    assert "chưa chuyển được" in shown


def test_a_model_error_is_reported_not_turned_into_a_pass():
    model = ScenarioModel(ModelTransportError("provider_limit", "generation"))
    (expectations, stop), _shown, _asked = _run(model, ["Ngọc nạp 40 ADA."])
    assert expectations is None and stop == "llm_error"


def test_to_expectation_matches_the_e6_expect_tool():
    sys.path.insert(0, str(ROOT / "tools" / "e6"))
    try:
        from expect import build
    finally:
        sys.path.pop(0)
    compact = {"tx": [["2027-02-01T13:00:00.000+00:00", [["deposit", "Ngoc", "Ngọc", 40.0]]],
                      ["2027-02-02T13:00:00.000+00:00", [["choice", "Ngoc", 1], ["notify"]]],
                      ["2027-02-03T13:00:00.000+00:00", []]],
               "pay": [["Ngọc", "Lâm", 40.0], ["Ngọc", "Ngọc", 0, ["abc", "TOK", 3]]]}
    assert to_expectation(compact) == build(compact)
