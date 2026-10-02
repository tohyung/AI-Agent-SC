"""Offline safety and classification regressions; no provider calls."""

from copy import deepcopy
import json

import pytest

from marlowe_ai_agent.marlowe_agent.models import LLMConfigError, LLMPhaseError
from marlowe_ai_agent.marlowe_agent.openai_reasoner import summarize_call_log
from research.experiments import live_stage2b_corridor as corridor
from research.stage2b import live_safety
from research.stage2b.live_safety import make_live_budget
from research.stage2b.model_errors import sanitized_model_error
from research.stage2b.profile_diagnostic import direct_payment_profile_match
from research.stage2b.projector import project_intent_spec
from research.stage2b.report_shadow_run import build_report, profile_diagnostic
from research.stage2b import report_shadow_run
from research.stage2b.scoring import FrozenCandidateAdapter


@pytest.fixture(autouse=True)
def clean_git_for_offline_cli(monkeypatch):
    monkeypatch.setattr(corridor, "require_clean_worktree", lambda _root: "a" * 40)
from research.architecture.test_stage2bc_compiler_reference_path import semantic_core
from research.architecture.test_compiler_reference_integration import real_binary as real_binary


def test_monetary_budget_is_decimal_and_global():
    budget = make_live_budget(60, 60, "3.00", "0.50")
    assert budget.money_limited_calls == budget.effective_calls == 6
    assert budget.to_dict()["maximum_declared_spend_usd"] == "3.00"
    with pytest.raises(ValueError):
        make_live_budget(60, 60, "0.49", "0.50")
    with pytest.raises(ValueError):
        make_live_budget(61, 60, "100", "1")


def test_missing_telemetry_is_null_and_windows_are_independent():
    entries = [
        {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.01, "latency_seconds": 0.1},
        {"prompt_tokens": None, "completion_tokens": 60, "cost": None, "latency_seconds": 0.2},
    ]
    whole = summarize_call_log(entries)
    assert whole["prompt_tokens"] is None
    assert whole["prompt_tokens_known_subtotal"] == 100
    assert whole["prompt_tokens_observed_calls"] == 1
    assert whole["completion_tokens"] == 110
    assert whole["cost"] is None and whole["cost_known_subtotal"] == 0.01
    later = summarize_call_log(entries[1:] + [{"prompt_tokens": 12, "completion_tokens": 3,
                                                 "cost": 0.02, "latency_seconds": 0.1}])
    assert later["prompt_tokens"] is None
    assert summarize_call_log(entries[2:] + [{"prompt_tokens": 12, "completion_tokens": 3,
                                               "cost": 0.02, "latency_seconds": 0.1}])["prompt_tokens"] == 12


def test_model_error_classifier_never_serializes_exception_text():
    secret = "SUPER_SECRET_SENTINEL"
    safe = sanitized_model_error(RuntimeError(f"Authorization=Bearer {secret}"))
    assert safe["code"] == "provider_error"
    assert secret not in json.dumps(safe)


@pytest.mark.parametrize(("change", "expected"), [
    ({"stages": {"intent_extraction": {"run_status": "FAILED"}}}, "MODEL_ERROR"),
    ({"core_validation_errors": ["bad"]}, "CORE_INVALID"),
    ({"projection_classification": "PROJECTOR_BUG"}, "PROJECTOR_BUG"),
    ({"stages": {"intent_acceptance": {"semantic_status": "NEEDS_CLARIFICATION"}}},
     "STAGE2C_UNRESOLVED"),
    ({"profile_match": "UNSUPPORTED_PROFILE"}, "PROFILE_UNSUPPORTED"),
    ({"stages": {"compile": {"semantic_status": "UNSUPPORTED_FEATURE"}}}, "COMPILER_UNSUPPORTED"),
    ({"stages": {"semantic_comparison": {"semantic_status": "VIOLATED",
                                            "run_status": "SUCCEEDED"}}}, "SEMANTIC_VIOLATION"),
])
def test_first_failure_classifier(change, expected):
    record = {"stages": {name: {"run_status": "SUCCEEDED", "semantic_status": status}
                         for name, status in (
                             ("intent_extraction", "PASS"), ("intent_acceptance", "ACCEPTED"),
                             ("compile", "SUPPORTED"), ("semantic_comparison", "SATISFIED"),
                             ("compiler_authority", "CANDIDATE_ONLY"),
                             ("exploration", "BOUNDED"), ("oracle_evaluation", "SATISFIED"))},
              "core_validation_errors": [], "projection_classification": "PASS",
              "profile_match": "EXACT_SUPPORTED_PROFILE", "oracle_verdict": "SATISFIED"}
    for key, value in change.items():
        if key == "stages":
            record["stages"].update(value)
        else:
            record[key] = value
    assert corridor.classify_first_failure(record) == expected


def test_corridor_classifier_passed():
    record = {"stages": {name: {"run_status": "SUCCEEDED", "semantic_status": status}
                         for name, status in (
                             ("intent_extraction", "PASS"), ("intent_acceptance", "ACCEPTED"),
                             ("compile", "SUPPORTED"), ("semantic_comparison", "SATISFIED"),
                             ("compiler_authority", "CANDIDATE_ONLY"),
                             ("exploration", "BOUNDED"), ("oracle_evaluation", "SATISFIED"))},
              "core_validation_errors": [], "projection_classification": "PASS",
              "profile_match": "EXACT_SUPPORTED_PROFILE", "oracle_verdict": "SATISFIED"}
    assert corridor.classify_first_failure(record) == "CORRIDOR_PASSED"


def test_canary_source_and_fixture_are_independent():
    assert corridor.HISTORY == [{"version": 1, "messages": [
        "Pay 10 ADA from Alice account to Bob."]}]
    scenario, expectation = corridor.independent_expectation()
    assert scenario.payload["initial_state"]["accounts"][0][1] == 10000000
    assert expectation.payload["expected_payments"][0]["amount"] == 10000000
    source = semantic_core()
    assert source["requirement_history"] == corridor.HISTORY
    assert deepcopy(source)["claims"] != []


def test_profile_diagnostic_requires_all_four_claim_kinds():
    spec = project_intent_spec(semantic_core(), expected_history=corridor.HISTORY).intent_spec.to_dict()
    assert direct_payment_profile_match(spec) == "EXACT_SUPPORTED_PROFILE"
    spec["claims"] = [claim for claim in spec["claims"]
                      if claim["kind"] != "payment_source_account_owner"]
    assert direct_payment_profile_match(spec) == "UNSUPPORTED_PROFILE"


def test_frozen_canonical_profile_diagnostic_and_native_scoring():
    candidates = FrozenCandidateAdapter().load(all_canonical=True)
    facts = profile_diagnostic(candidates)
    assert facts == {"canonical": 20, "development": 10, "public_validation": 10,
                     "mutations_excluded": 12, "source_owner_case_ids": [],
                     "exact_direct_payment_case_ids": []}
    report = build_report([], candidates)
    assert len(report["cases"]) == 20
    assert report["score"]["exploratory_metrics"]["exploratory_core_output_rate"] == {
        "numerator": 0, "denominator": 20, "value": 0.0}


def test_reporter_checks_lane_identity_and_raw_hash(tmp_path):
    candidates = FrozenCandidateAdapter().load(all_canonical=True)
    identity = {"experiment_version": corridor.EXPERIMENT_VERSION,
                "code_sha": "a" * 40, "model": "fake"}
    raw = tmp_path / "lane-b.jsonl"
    with raw.open("x", encoding="utf-8") as writer:
        for candidate in candidates:
            writer.write(json.dumps({**identity, "case_id": candidate["case_id"],
                                     "source_corpus_aggregate_sha256":
                                     live_safety.STAGE2A_AGGREGATE_SHA256,
                                     "run_status": "model_error", "prediction": None}) + "\n")
    live_safety.write_execution_summary(raw, identity)
    lane_a = tmp_path / "lane-a.summary.json"
    lane_a.write_text(json.dumps(identity), encoding="utf-8")
    score = tmp_path / "score.json"
    assert report_shadow_run.main(["--input", str(raw), "--lane-a-summary", str(lane_a),
                                   "--output", str(score)]) == 0
    assert score.is_file()
    lane_a.write_text(json.dumps({**identity, "model": "different"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="2"):
        report_shadow_run.main(["--input", str(raw), "--lane-a-summary", str(lane_a),
                                "--output", str(tmp_path / "blocked.json")])
    assert not (tmp_path / "blocked.json").exists()


def test_one_offline_repetition_traverses_corridor_without_reextracting():
    class Model:
        def __init__(self):
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return deepcopy(semantic_core())

        def request_count(self):
            return self.calls

        def usage_window(self, start):
            return {"calls": self.calls - start}

    class Reference:
        def __init__(self):
            self.calls = 0

        def execute(self, request):
            self.calls += 1
            return {"status": "Success", "steps": [{"status": "Success",
                                                      "payments": [corridor.EXPECTED_PAYMENT],
                                                      "warnings": []}],
                    "final_state": corridor.FINAL_STATE, "final_contract": "close",
                    "meta": {"upstream_commit": "7b5b1e900ec53a8eb18747992bec73470704dfcb",
                             "reference_driver_version": "0.1.0"}}

    model = Model()
    reference = Reference()
    result = corridor.run_repetition(model, "unused", 1, reference_executor=reference)
    assert model.calls == 1
    assert reference.calls == 2, (result["stages"], result["first_failure_class"])
    assert result["first_failure_class"] == "CORRIDOR_PASSED"
    assert result["reference_identity"] == corridor.REFERENCE_IDENTITY


def test_invalid_core_stops_before_stage2c():
    class Model:
        def __init__(self):
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            core = deepcopy(semantic_core())
            core["requirement_history"] = [{"version": 1, "messages": ["wrong source"]}]
            return core

        def request_count(self):
            return self.calls

        def usage_window(self, start):
            return {"calls": self.calls - start}

    model = Model()
    record = corridor.run_repetition(model, "unused", 1, reference_executor=object())
    assert model.calls == 1
    assert record["first_failure_class"] == "CORE_INVALID"
    assert list(record["stages"]) == ["intent_extraction"]


def test_one_offline_repetition_uses_real_pinned_reference(real_binary):
    class Model:
        def __init__(self):
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return deepcopy(semantic_core())

        def request_count(self):
            return self.calls

        def usage_window(self, start):
            return {"calls": self.calls - start}

    model = Model()
    record = corridor.run_repetition(model, real_binary, 1)
    assert model.calls == 1
    assert record["first_failure_class"] == "CORRIDOR_PASSED"
    assert record["reference_identity"] == corridor.REFERENCE_IDENTITY


def test_live_cli_requires_explicit_budget_before_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(corridor, "LegacyReasonerTransport",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("provider constructed")))
    binary = tmp_path / "reference"
    binary.write_bytes(b"fixture")
    output = tmp_path / "run.jsonl"
    with pytest.raises(SystemExit, match="2"):
        corridor.main(["--live", "--model", "fake", "--reference-binary", str(binary),
                       "--output", str(output)])
    assert not output.exists()


def test_live_cli_refuses_existing_output_before_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(corridor, "LegacyReasonerTransport",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("provider constructed")))
    binary = tmp_path / "reference"
    binary.write_bytes(b"fixture")
    output = tmp_path / "run.jsonl"
    output.write_text("preserve", encoding="utf-8")
    assert corridor.main(["--live", "--model", "fake", "--reference-binary", str(binary),
                          "--max-physical-calls", "9", "--max-spend-usd", "3",
                          "--per-request-cost-ceiling-usd", "0.5", "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "preserve"


def test_lane_a_budget_is_set_once_for_three_repetitions(tmp_path, monkeypatch):
    instances = []

    class Reasoner:
        def __init__(self):
            self.llm_calls = 0
            self.budgets = []

        def set_call_budget(self, value):
            self.budgets.append(value)
            self.llm_calls = 0

    class Transport:
        def __init__(self, _model):
            self.reasoner = Reasoner()
            instances.append(self)

        def usage(self):
            return {"calls": self.reasoner.llm_calls}

    def fake_run(model, _binary, repetition):
        model.reasoner.llm_calls += 1
        return {"repetition": repetition, "first_failure_class": "CORE_INVALID"}

    monkeypatch.setattr(corridor, "LegacyReasonerTransport", Transport)
    monkeypatch.setattr(corridor, "run_repetition", fake_run)
    binary = tmp_path / "reference"
    binary.write_bytes(b"fixture")
    output = tmp_path / "run.jsonl"
    assert corridor.main(["--live", "--model", "fake", "--reference-binary", str(binary),
                          "--max-physical-calls", "9", "--max-spend-usd", "3",
                          "--per-request-cost-ceiling-usd", "0.5", "--output", str(output)]) == 0
    assert len(instances) == 1
    assert instances[0].reasoner.budgets == [6]
    assert instances[0].reasoner.llm_calls == 3
    assert len(output.read_text(encoding="utf-8").splitlines()) == 3
    summary = json.loads(live_safety.summary_path(output).read_text(encoding="utf-8"))
    assert summary["experiment_status"] == "COMPLETED"
    assert summary["first_failure_class_counts"] == {"CORE_INVALID": 3}


@pytest.mark.parametrize("blocker", ["dirty", "inside_repo", "existing_summary"])
def test_lane_a_preflight_blocks_before_transport(tmp_path, monkeypatch, blocker):
    binary = tmp_path / "reference"
    binary.write_bytes(b"fixture")
    output = tmp_path / "run.jsonl"
    if blocker == "dirty":
        monkeypatch.setattr(corridor, "require_clean_worktree",
                            lambda _root: (_ for _ in ()).throw(
                                live_safety.LivePreflightError("LIVE_EXECUTION_BLOCKED_DIRTY_WORKTREE")))
    if blocker == "inside_repo":
        output = corridor.ROOT / "never-create-live-canary-test.jsonl"
    if blocker == "existing_summary":
        live_safety.summary_path(output).write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(corridor, "LegacyReasonerTransport",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("transport constructed")))
    assert corridor.main(["--live", "--model", "fake", "--reference-binary", str(binary),
                          "--max-physical-calls", "9", "--max-spend-usd", "3",
                          "--per-request-cost-ceiling-usd", "0.5", "--output", str(output)]) == 2
    assert not output.exists()
    if blocker == "existing_summary":
        assert live_safety.summary_path(output).read_text(encoding="utf-8") == "preserve"
    else:
        assert not live_safety.summary_path(output).exists()


def test_lane_a_constructor_failure_leaves_no_empty_files(tmp_path, monkeypatch):
    binary = tmp_path / "reference"
    binary.write_bytes(b"fixture")
    output = tmp_path / "run.jsonl"
    monkeypatch.setattr(corridor, "LegacyReasonerTransport",
                        lambda *_args: (_ for _ in ()).throw(LLMConfigError("bad config")))
    assert corridor.main(["--live", "--model", "fake", "--reference-binary", str(binary),
                          "--max-physical-calls", "9", "--max-spend-usd", "3",
                          "--per-request-cost-ceiling-usd", "0.5", "--output", str(output)]) == 2
    assert not output.exists() and not live_safety.summary_path(output).exists()


def test_lane_a_preserves_safe_phase_error_and_completes_zero_passes(
        tmp_path, monkeypatch, capsys):
    secret = "SUPER_SECRET_SENTINEL"
    instances = []

    class Transport:
        def __init__(self, _model):
            self.reasoner = type("Reasoner", (), {"model": "fake", "llm_calls": 0,
                                                  "call_log": [], "budgets": []})()
            self.reasoner.set_call_budget = self.reasoner.budgets.append
            instances.append(self)

        def generate(self, _system, _user):
            self.reasoner.llm_calls += 1
            self.reasoner.call_log.append({"latency_seconds": 0.1, "prompt_tokens": None,
                                           "completion_tokens": 2, "cost": None})
            if self.reasoner.llm_calls == 2:
                raise RuntimeError(f"Authorization=Bearer {secret}")
            error = LLMPhaseError(phase="model_output_parse",
                                  code="model_output_invalid_after_repair",
                                  model_content_received=True, repair_attempted=True)
            error.__cause__ = RuntimeError(secret)
            raise error

        def request_count(self):
            return len(self.reasoner.call_log)

        def usage_window(self, start):
            return summarize_call_log(self.reasoner.call_log[start:])

        def usage(self):
            return summarize_call_log(self.reasoner.call_log)

    monkeypatch.setattr(corridor, "LegacyReasonerTransport", Transport)
    binary = tmp_path / "reference"
    binary.write_bytes(b"fixture")
    output = tmp_path / "run.jsonl"
    assert corridor.main(["--live", "--model", "fake", "--reference-binary", str(binary),
                          "--max-physical-calls", "9", "--max-spend-usd", "3",
                          "--per-request-cost-ceiling-usd", "0.5", "--output", str(output)]) == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    summary = json.loads(live_safety.summary_path(output).read_text(encoding="utf-8"))
    assert len(rows) == 3
    assert rows[0]["model_error"]["code"] == "model_output_invalid_after_repair"
    assert rows[0]["model_error"]["phase"] == "model_output_parse"
    assert rows[0]["model_error"]["repair_attempted"] is True
    assert rows[1]["model_error"]["code"] == "provider_error"
    assert summary["experiment_status"] == "COMPLETED"
    assert summary["corridor_passed_count"] == 0
    assert summary["first_failure_class_counts"] == {"MODEL_ERROR": 3}
    assert summary["raw_output_sha256"] == live_safety.raw_sha256(output)
    assert summary["usage"]["prompt_tokens"] is None
    assert instances[0].reasoner.budgets == [6]
    captured = capsys.readouterr()
    assert secret not in (output.read_text(encoding="utf-8")
                          + live_safety.summary_path(output).read_text(encoding="utf-8")
                          + captured.out + captured.err)


def test_lane_a_budget_exhaustion_persists_partial_summary(tmp_path, monkeypatch):
    class Transport:
        def __init__(self, _model):
            self.reasoner = type("Reasoner", (), {"llm_calls": 0})()
            self.reasoner.set_call_budget = lambda limit: setattr(self.reasoner, "limit", limit)

        def usage(self):
            return {"calls": self.reasoner.llm_calls}

    def fake_run(model, _binary, repetition):
        model.reasoner.llm_calls += 1
        return {"repetition": repetition, "first_failure_class": "CORE_INVALID"}

    monkeypatch.setattr(corridor, "LegacyReasonerTransport", Transport)
    monkeypatch.setattr(corridor, "run_repetition", fake_run)
    binary = tmp_path / "reference"
    binary.write_bytes(b"fixture")
    output = tmp_path / "run.jsonl"
    assert corridor.main(["--live", "--model", "fake", "--reference-binary", str(binary),
                          "--max-physical-calls", "9", "--max-spend-usd", "1",
                          "--per-request-cost-ceiling-usd", "0.5", "--output", str(output)]) == 2
    summary = json.loads(live_safety.summary_path(output).read_text(encoding="utf-8"))
    assert summary["experiment_status"] == "BUDGET_EXHAUSTED"
    assert summary["repetitions_completed"] == 2
    assert len(output.read_text(encoding="utf-8").splitlines()) == 2
