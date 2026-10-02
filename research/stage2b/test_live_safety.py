"""Offline live-CLI preflight and request-accounting tests."""

import json
import sys

import pytest

from marlowe_ai_agent.marlowe_agent.openai_reasoner import summarize_call_log
from research.architecture.bootstrap import build_research_pipeline
from research.stage2b import run_shadow
from research.stage2b.test_intent_spec import simple_payment
from research.stage2b.intent_spec import extract_core_view


FLAGS = ["--live", "--all-canonical", "--model", "fake", "--max-physical-calls", "60",
         "--max-spend-usd", "3.00", "--per-request-cost-ceiling-usd", "0.50"]


@pytest.mark.parametrize("omitted", ["--model", "--max-physical-calls", "--max-spend-usd",
                                    "--per-request-cost-ceiling-usd"])
def test_missing_live_field_rejected_before_provider(tmp_path, monkeypatch, omitted):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("provider constructed during invalid preflight")

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", forbidden)
    flags = FLAGS.copy()
    index = flags.index(omitted)
    del flags[index:index + 2]
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", *flags, "--output", str(tmp_path / "out.jsonl")])
    with pytest.raises(SystemExit, match="2"):
        run_shadow.main()


def test_existing_output_is_refused_without_constructing_provider(tmp_path, monkeypatch):
    output = tmp_path / "existing.jsonl"
    output.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("provider constructed")))
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", *FLAGS, "--output", str(output)])
    assert run_shadow.main() == 2
    assert output.read_text(encoding="utf-8") == "preserve"


def test_global_budget_set_once_across_cases(tmp_path, monkeypatch):
    source = extract_core_view(simple_payment())
    source["requirement_history"] = [{"version": 1, "messages": ["test"]}]
    instances = []

    class FakeReasoner:
        def __init__(self):
            self.model = "fake"
            self.call_log = []
            self.llm_calls = 0
            self.budgets = []

        def set_call_budget(self, budget):
            self.budgets.append(budget)
            self.llm_calls = 0

    class FakeTransport:
        def __init__(self, _model):
            self.reasoner = FakeReasoner()
            instances.append(self)

        def generate(self, _system, _user):
            self.reasoner.llm_calls += 1
            self.reasoner.call_log.append({"latency_seconds": 0.1, "prompt_tokens": 10,
                                           "completion_tokens": 5, "cost": None})
            return source

        def request_count(self):
            return len(self.reasoner.call_log)

        def usage_window(self, start):
            return summarize_call_log(self.reasoner.call_log[start:])

        def usage(self):
            return summarize_call_log(self.reasoner.call_log)

    class FakeAdapter:
        def load(self, **_kwargs):
            return [{"case_id": f"case-{i}", "split": "development",
                     "requirement_history": source["requirement_history"]} for i in range(2)]

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    monkeypatch.setattr(run_shadow, "FrozenCandidateAdapter", FakeAdapter)
    output = tmp_path / "run.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", *FLAGS, "--output", str(output)])
    assert run_shadow.main() == 0
    assert len(instances) == 1
    assert instances[0].reasoner.budgets == [6]
    assert instances[0].reasoner.llm_calls == 2
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["usage"]["calls"] for row in rows] == [1, 1]
    assert all(row["usage"]["cost"] is None for row in rows)


def test_lane_b_budget_exhaustion_preserves_completed_rows(tmp_path, monkeypatch, capsys):
    source = extract_core_view(simple_payment())

    class Transport:
        def __init__(self, _model):
            self.reasoner = type("Reasoner", (), {"model": "fake", "llm_calls": 0,
                                                  "call_log": []})()
            self.reasoner.set_call_budget = lambda limit: setattr(self.reasoner, "cap", limit)

        def generate(self, _system, _user):
            self.reasoner.llm_calls += 1
            self.reasoner.call_log.append({"latency_seconds": 0, "prompt_tokens": None,
                                           "completion_tokens": None, "cost": None})
            return source

        def request_count(self):
            return len(self.reasoner.call_log)

        def usage_window(self, start):
            return summarize_call_log(self.reasoner.call_log[start:])

        def usage(self):
            return summarize_call_log(self.reasoner.call_log)

    class Adapter:
        def load(self, **_kwargs):
            return [{"case_id": f"case-{i}", "split": "development",
                     "requirement_history": source["requirement_history"]} for i in range(2)]

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", Transport)
    monkeypatch.setattr(run_shadow, "FrozenCandidateAdapter", Adapter)
    output = tmp_path / "partial.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--model", "fake",
                                          "--max-physical-calls", "60", "--max-spend-usd", "0.5",
                                          "--per-request-cost-ceiling-usd", "0.5",
                                          "--output", str(output)])
    assert run_shadow.main() == 2
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1
    assert '"experiment_status": "BUDGET_EXHAUSTED"' in capsys.readouterr().out


def test_stage2b_port_does_not_persist_secret_exception():
    secret = "SUPER_SECRET_SENTINEL"

    class BadModel:
        def generate(self, _system, _user):
            raise RuntimeError(f"Authorization=Bearer {secret}")

    run = build_research_pipeline(model=BadModel()).run(
        [{"version": 1, "messages": ["Pay 10 ADA from Alice account to Bob."]}],
        stop_after="intent_extraction")
    assert run.stages["intent_extraction"].run_status.value == "FAILED"
    assert secret not in json.dumps(run.to_dict())


def test_projector_failure_is_separate_and_sanitized(monkeypatch):
    from research.stage2b import projector

    monkeypatch.setattr(projector, "project_intent_spec",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            RuntimeError("SUPER_SECRET_SENTINEL")))

    class Model:
        def generate(self, _system, _user):
            return extract_core_view(simple_payment())

    run = build_research_pipeline(model=Model()).run(
        [{"version": 1, "messages": ["test"]}], stop_after="intent_extraction")
    assert run.stages["intent_extraction"].semantic_status == "PROJECTOR_BUG"
    assert "SUPER_SECRET_SENTINEL" not in json.dumps(run.to_dict())
