"""Model replay must never spend a second call for the same exact input."""

import json

import pytest

from research.integrations.model_replay import JournaledModel


class CountingModel:
    model = "test-model"

    def __init__(self):
        self.calls = 0

    def generate(self, _system, user):
        self.calls += 1
        return {"value": user, "call": self.calls}

    def set_call_budget(self, _limit):
        pass

    @property
    def llm_calls(self):
        return self.calls

    @property
    def call_log(self):
        return []

    def usage_summary(self):
        return {"api_calls": self.calls}


def test_exact_logical_request_replays_after_restart_without_model_call(tmp_path):
    path = tmp_path / "outputs.jsonl"
    first = CountingModel()
    journal = JournaledModel(first, path)
    output = journal.generate("system", "user")
    output["value"] = "locally mutated"
    assert journal.generate("system", "user") == {"value": "user", "call": 1}
    assert first.calls == 1

    restarted = CountingModel()
    replay = JournaledModel(restarted, path)
    assert replay.generate("system", "user") == {"value": "user", "call": 1}
    assert restarted.calls == 0
    assert replay.generate("system", "different") == {"value": "different", "call": 1}
    assert restarted.calls == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_replay_rejects_invalid_or_conflicting_journal(tmp_path):
    path = tmp_path / "outputs.jsonl"
    path.write_text(json.dumps({"model": "other"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid logical model journal"):
        JournaledModel(CountingModel(), path)
