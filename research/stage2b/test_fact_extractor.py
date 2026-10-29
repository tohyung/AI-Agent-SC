"""A2 extraction loop: atomic repairs reach the model, builder output never does."""

from copy import deepcopy

from research.stage2b import fact_extractor
from research.stage2b.fact_builder import build_core
from research.stage2b.fact_extractor import (
    EXAMPLE_DRAFT,
    EXAMPLE_REQUEST,
    build_prompt,
    extract_fact_core,
)

HISTORY = [{"version": 1, "messages": [EXAMPLE_REQUEST]}]


class ScriptedModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.users = []
        self.llm_calls = 0

    def generate(self, system, user):
        self.llm_calls += 1
        self.users.append(user)
        return deepcopy(self.outputs.pop(0))


def test_prompt_example_is_synthetic_and_builds():
    core = build_core(EXAMPLE_DRAFT, HISTORY)
    assert core["predicted_resolution"] == "accepted_interpretation"
    system, user = build_prompt([{"version": 1, "messages": ["Other request"]}])
    assert "Other request" in user and "POSIX" in system


def test_valid_first_draft_needs_one_call():
    model = ScriptedModel([EXAMPLE_DRAFT])
    result = extract_fact_core(model, HISTORY)
    assert model.llm_calls == 1 and result["projection_classification"] == "PASS"
    assert result["attempts"][0]["problems"] == []


def test_draft_error_is_repaired_by_item_id():
    broken = deepcopy(EXAMPLE_DRAFT)
    broken["quantities"][0]["expr"]["ada"] = "70"
    model = ScriptedModel([broken, EXAMPLE_DRAFT])
    result = extract_fact_core(model, HISTORY)
    assert model.llm_calls == 2 and result["projection_classification"] == "PASS"
    assert "- q_total: literal 70 ada not in evidence" in model.users[1]
    assert result["attempts"][0]["problems"]


def test_repairs_stop_at_the_budget():
    broken = deepcopy(EXAMPLE_DRAFT)
    broken["parties"][0]["evidence"][0]["span"] = "invented"
    model = ScriptedModel([broken] * 4)
    result = extract_fact_core(model, HISTORY, max_repairs=3)
    assert model.llm_calls == 4 and result["semantic_core"] is None
    assert result["projection_classification"] == "DRAFT_INVALID"


def test_builder_bug_is_reported_not_sent_to_the_model(monkeypatch):
    def broken_builder(draft, history):
        core = build_core(draft, history)
        core["predicted_resolution"] = "unsupported_for_current_study"
        return core

    monkeypatch.setattr(fact_extractor, "build_core", broken_builder)
    model = ScriptedModel([EXAMPLE_DRAFT])
    result = extract_fact_core(model, HISTORY)
    assert model.llm_calls == 1 and result["builder_bug"] is True
