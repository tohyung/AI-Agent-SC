"""Offline live-CLI preflight and request-accounting tests."""

import json
import subprocess
import sys

import pytest

from marlowe_ai_agent.marlowe_agent.models import LLMConfigError, LLMTransientError
from marlowe_ai_agent.marlowe_agent.openai_reasoner import summarize_call_log
from research.architecture.bootstrap import build_research_pipeline
from research.architecture.models import StageResult
from research.architecture.status import ImplementationStatus, StageRunStatus
from research.stage2b import run_shadow
from research.stage2b import live_safety
from research.stage2b.test_intent_spec import simple_payment
from research.stage2b.intent_spec import extract_core_view


FLAGS = ["--live", "--all-canonical", "--model", "fake", "--max-physical-calls", "60",
         "--max-spend-usd", "3.00", "--per-request-cost-ceiling-usd", "0.50"]


@pytest.fixture(autouse=True)
def clean_git_for_offline_cli(monkeypatch):
    monkeypatch.setattr(run_shadow, "require_clean_worktree", lambda _root: "a" * 40)


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
    summary = json.loads(live_safety.summary_path(output).read_text(encoding="utf-8"))
    assert summary["experiment_status"] == "BUDGET_EXHAUSTED"
    assert summary["requested_cases"] == 2 and summary["completed_cases"] == 1
    assert summary["raw_output_sha256"] == live_safety.raw_sha256(output)
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
    assert run.stages["intent_extraction"].semantic_status == "MODEL_ERROR"
    assert run.stages["intent_extraction"].safe_error["code"] == "provider_error"
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


def test_git_gate_requires_sha_and_empty_porcelain(monkeypatch, tmp_path):
    monkeypatch.setattr(live_safety, "_git",
                        lambda _root, *args: "a" * 40 if args[0] == "rev-parse" else "")
    assert live_safety.require_clean_worktree(tmp_path) == "a" * 40
    monkeypatch.setattr(live_safety, "_git",
                        lambda _root, *args: "a" * 40 if args[0] == "rev-parse" else "?? untracked")
    with pytest.raises(live_safety.LivePreflightError, match="DIRTY_WORKTREE"):
        live_safety.require_clean_worktree(tmp_path)
    monkeypatch.setattr(live_safety, "_git",
                        lambda _root, *args: (_ for _ in ()).throw(
                            live_safety.LivePreflightError("LIVE_EXECUTION_BLOCKED_GIT_UNAVAILABLE")))
    with pytest.raises(live_safety.LivePreflightError, match="GIT_UNAVAILABLE"):
        live_safety.require_clean_worktree(tmp_path)


def test_real_git_gate_detects_tracked_and_untracked_changes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)
    source = repo / "source.txt"
    source.write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True,
                   stdin=subprocess.DEVNULL, capture_output=True)
    subprocess.run(["git", "-c", "user.name=Offline Test", "-c",
                    "user.email=offline@example.invalid", "commit", "-q", "-m", "baseline"],
                   cwd=repo, check=True, stdin=subprocess.DEVNULL, capture_output=True)
    assert len(live_safety.require_clean_worktree(repo)) == 40
    (repo / "untracked.txt").write_text("new", encoding="utf-8")
    with pytest.raises(live_safety.LivePreflightError, match="DIRTY_WORKTREE"):
        live_safety.require_clean_worktree(repo)
    (repo / "untracked.txt").unlink()
    source.write_text("changed\n", encoding="utf-8")
    with pytest.raises(live_safety.LivePreflightError, match="DIRTY_WORKTREE"):
        live_safety.require_clean_worktree(repo)


def test_stage_result_safe_error_is_optional_and_closed():
    result = StageResult("intent_extraction", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                         StageRunStatus.SUCCEEDED)
    assert "safe_error" not in result.to_dict()
    result.safe_error = {"code": "provider_error", "phase": "unknown",
                         "message": "Model request failed.", "model_content_received": None,
                         "repair_attempted": None, "exception_type": "RuntimeError"}
    assert result.to_dict()["safe_error"]["code"] == "provider_error"
    result.safe_error["raw_exception"] = "SUPER_SECRET_SENTINEL"
    with pytest.raises(ValueError, match="closed normalized schema"):
        result.to_dict()


def test_cross_lane_identity_rejects_different_sha_or_model():
    first = {"experiment_version": live_safety.EXPERIMENT_VERSION,
             "code_sha": "a" * 40, "model": "model-a"}
    live_safety.require_same_experiment_identity(first, dict(first))
    for key, changed in (("code_sha", "b" * 40), ("model", "model-b"),
                         ("experiment_version", "other")):
        second = {**first, key: changed}
        with pytest.raises(ValueError, match="experiment identity mismatch"):
            live_safety.require_same_experiment_identity(first, second)


@pytest.mark.parametrize("blocker", ["dirty", "inside_repo", "existing_summary"])
def test_lane_b_preflight_blocks_before_transport(tmp_path, monkeypatch, blocker):
    output = tmp_path / "run.jsonl"
    if blocker == "dirty":
        monkeypatch.setattr(run_shadow, "require_clean_worktree",
                            lambda _root: (_ for _ in ()).throw(
                                live_safety.LivePreflightError("LIVE_EXECUTION_BLOCKED_DIRTY_WORKTREE")))
    if blocker == "inside_repo":
        output = run_shadow.ROOT / "never-create-live-stage2b-test.jsonl"
    if blocker == "existing_summary":
        live_safety.summary_path(output).write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("transport constructed")))
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", *FLAGS, "--output", str(output)])
    assert run_shadow.main() == 2
    assert not output.exists()
    if blocker == "existing_summary":
        assert live_safety.summary_path(output).read_text(encoding="utf-8") == "preserve"
    else:
        assert not live_safety.summary_path(output).exists()


def test_lane_b_constructor_failure_leaves_no_empty_files(tmp_path, monkeypatch):
    output = tmp_path / "run.jsonl"
    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport",
                        lambda *_args: (_ for _ in ()).throw(LLMConfigError("bad config")))
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", *FLAGS, "--output", str(output)])
    assert run_shadow.main() == 2
    assert not output.exists() and not live_safety.summary_path(output).exists()


def test_lane_b_recorded_model_error_still_completes_and_has_safe_summary(
        tmp_path, monkeypatch, capsys):
    secret = "SUPER_SECRET_SENTINEL"
    source = extract_core_view(simple_payment())
    instances = []

    class Transport:
        def __init__(self, _model):
            self.reasoner = type("Reasoner", (), {"model": "fake", "llm_calls": 0,
                                                  "call_log": [], "budget_calls": []})()
            self.reasoner.set_call_budget = self.reasoner.budget_calls.append
            instances.append(self)

        def generate(self, _system, _user):
            self.reasoner.llm_calls += 1
            self.reasoner.call_log.append({"latency_seconds": 0.1, "prompt_tokens": None,
                                           "completion_tokens": 4, "cost": None})
            if self.reasoner.llm_calls == 2:
                raise LLMTransientError(f"Authorization=Bearer {secret}")
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
                     "requirement_history": source["requirement_history"]} for i in range(3)]

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", Transport)
    monkeypatch.setattr(run_shadow, "FrozenCandidateAdapter", Adapter)
    output = tmp_path / "run.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", *FLAGS, "--output", str(output)])
    assert run_shadow.main() == 0
    summary = json.loads(live_safety.summary_path(output).read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3 and summary["completed_cases"] == 3
    assert summary["experiment_status"] == "COMPLETED" and summary["model_error_cases"] == 1
    assert summary["raw_output_sha256"] == live_safety.raw_sha256(output)
    assert summary["usage"]["prompt_tokens"] is None
    assert instances[0].reasoner.budget_calls == [6]
    captured = capsys.readouterr()
    assert secret not in (output.read_text(encoding="utf-8")
                          + live_safety.summary_path(output).read_text(encoding="utf-8")
                          + captured.out + captured.err)
