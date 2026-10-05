"""Offline guards for the adaptive batch; these tests never contact a provider."""

import json
import hashlib
import signal

import pytest

from marlowe_ai_agent.marlowe_agent.models import LLMBudgetError, LLMTransientError
from research.architecture.bootstrap import build_research_pipeline
from research.architecture.status import AuthorityLevel, StageRunStatus
from research.experiments.online_tuning_batch01 import (PhysicalCallJournal,
                                                        CompilerFeedbackModel,
                                                        ProviderLimitReached,
                                                        attach_global_budget, batch_wiring, load_batch,
                                                        load_compiler_feedback,
                                                        load_replay_core,
                                                        load_synthetic_input, next_attempt_paths,
                                                        model_request_deadline, physical_call_limit,
                                                        reusable_extraction,
                                                        run_one)
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2
from research.stage3.test_funded_choice_v1 import funded_choice_core
from research.stage3.test_funded_swap_v1 import swap_core


def test_batch_manifest_matches_only_first_twenty_physical_records():
    manifest, cases = load_batch()
    assert len(cases) == 20
    assert [case["id"] for case in cases] == manifest["case_ids"]
    assert manifest["max_physical_model_calls"] == 48


def test_attempts_are_persisted_before_network_and_not_reset(tmp_path):
    path = tmp_path / "attempts.jsonl"
    journal = PhysicalCallJournal(path, limit=2)
    journal.consume("first")
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["attempt"] == 1
    resumed = PhysicalCallJournal(path, limit=2)
    resumed.consume("second")
    with pytest.raises(LLMBudgetError, match="BATCH_MODEL_BUDGET_EXHAUSTED"):
        resumed.consume("third")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_unbounded_journal_resumes_after_historical_seventy_attempts(tmp_path):
    path = tmp_path / "attempts.jsonl"
    path.write_text("".join(json.dumps({"attempt": index, "case_id": "prior"}) + "\n"
                            for index in range(1, 71)), encoding="utf-8")
    journal = PhysicalCallJournal(path)
    journal.consume("current")
    assert journal.used == 71
    assert journal.entries[-1]["case_id"] == "current"


def test_compiler_feedback_requires_valid_same_case_evidence_and_does_not_edit_core(
        monkeypatch, tmp_path):
    core = swap_core()
    path = tmp_path / "case-04-attempt-11.json"
    record = {
        "case_id": "case-4", "core_schema_version": core["schema_version"],
        "requirement_history": core["requirement_history"],
        "candidate": {"semantic_core": core, "core_validation_errors": [],
                      "full_validation_errors": []},
        "stages": {"intent_acceptance": {"run_status": "SUCCEEDED"},
                   "compile": {"run_status": "UNSUPPORTED",
                               "diagnostics": ["missing deposit account owner"]}},
    }
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("research.experiments.online_tuning_batch01.RUN_DIR", tmp_path)
    loaded, diagnostics = load_compiler_feedback(
        path, case_id="case-4", history=core["requirement_history"],
        core_schema_version=core["schema_version"])
    assert loaded == core

    class Base:
        def generate(self, system, user):
            assert "missing deposit account owner" in user
            assert "Previous valid core" in user
            assert "superseded uncertainty" in user
            assert "actor's Choice" in user
            assert "obsolete uncertainty observation" in user
            assert "normal ledger operation" in user
            return {"generated": True}

    assert CompilerFeedbackModel(Base(), loaded, diagnostics).generate("system", "user") == {
        "generated": True}
    assert loaded == core
    with pytest.raises(ValueError, match="same-case valid core"):
        load_compiler_feedback(path, case_id="other", history=core["requirement_history"],
                               core_schema_version=core["schema_version"])


def test_explicit_core_replay_preserves_prior_valid_candidate_and_provenance(monkeypatch, tmp_path):
    core = swap_core()
    path = tmp_path / "case-04-prior.json"
    record = {
        "case_id": "case-4", "core_schema_version": core["schema_version"],
        "requirement_history": core["requirement_history"],
        "candidate": {"semantic_core": core, "core_validation_errors": [],
                      "full_validation_errors": []},
    }
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("research.experiments.online_tuning_batch01.RUN_DIR", tmp_path)
    loaded = load_replay_core(path, case_id="case-4", history=core["requirement_history"],
                              core_schema_version=core["schema_version"])
    assert loaded == core and loaded is not core
    assert json.loads(path.read_text(encoding="utf-8")) == record
    with pytest.raises(ValueError, match="same-case valid core"):
        load_replay_core(path, case_id="other", history=core["requirement_history"],
                         core_schema_version=core["schema_version"])


@pytest.mark.parametrize("status_code", [402, 429])
def test_provider_limit_is_sanitized_and_not_retried(tmp_path, status_code):
    class ProviderError(Exception):
        pass

    class Client:
        def with_options(self, *, max_retries):
            assert max_retries == 0
            return self

    class Reasoner:
        client = Client()

        def set_call_budget(self, limit):
            assert limit is None

        def _request(self, create, **kwargs):
            error = ProviderError("sensitive provider response")
            error.status_code = status_code
            raise error

        def _raw_response(self, system, user):
            return "{}"

    class Model:
        reasoner = Reasoner()

    model = Model()
    journal = PhysicalCallJournal(tmp_path / "attempts.jsonl")
    attach_global_budget(model, journal, "current")
    model.reasoner._consume_call()
    with pytest.raises(ProviderLimitReached, match=f"HTTP {status_code}") as error:
        model.reasoner._request(lambda: None, messages=[])
    assert "sensitive" not in str(error.value)
    assert model.provider_limit_status == status_code
    assert journal.used == 1


def test_budget_extension_preserves_prior_journal_and_caps_new_attempts(monkeypatch, tmp_path):
    original_entries = [{"attempt": index, "case_id": "prior"} for index in range(1, 49)]
    fingerprint = hashlib.sha256(json.dumps(
        original_entries, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    extension = tmp_path / "extension.json"
    extension.write_text(json.dumps({
        "batch_id": "online-tuning-batch01", "original_limit": 48,
        "journal_baseline_attempts": 48, "journal_baseline_sha256": fingerprint,
        "additional_attempts": 22,
    }), encoding="utf-8")
    monkeypatch.setattr("research.experiments.online_tuning_batch01.BUDGET_EXTENSION", extension)
    journal_path = tmp_path / "attempts.jsonl"
    manifest = {"batch_id": "online-tuning-batch01", "max_physical_model_calls": 48}
    assert physical_call_limit(manifest, journal_path) == 48
    baseline = "".join(json.dumps(item) + "\n" for item in original_entries)
    journal_path.write_text(baseline, encoding="utf-8")
    assert physical_call_limit(manifest, journal_path) == 70
    journal = PhysicalCallJournal(journal_path, limit=70)
    for _ in range(22):
        journal.consume("continued")
    with pytest.raises(LLMBudgetError, match="BATCH_MODEL_BUDGET_EXHAUSTED"):
        journal.consume("extra")
    assert journal_path.read_text(encoding="utf-8").startswith(baseline)
    assert journal.used == 70
    original_entries[0]["case_id"] = "tampered"
    journal_path.write_text("".join(json.dumps(item) + "\n" for item in original_entries),
                            encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        physical_call_limit(manifest, journal_path)


def test_sdk_hidden_retries_disabled_and_count_is_global(tmp_path):
    class Client:
        def with_options(self, *, max_retries):
            assert max_retries == 0
            return self

    class Reasoner:
        def __init__(self):
            self.client = Client()

        def set_call_budget(self, limit):
            self.max_llm_calls = limit
            self.llm_calls = 0

        def _raw_response(self, system, user):
            return '{"ok":true}'

        def _request(self, create, **kwargs):
            self.request_kwargs = kwargs
            return object()

    class Model:
        reasoner = Reasoner()

    journal = PhysicalCallJournal(tmp_path / "attempts.jsonl", limit=2)
    journal.consume("earlier")
    model = Model()
    attach_global_budget(model, journal, "current")
    assert model.reasoner.llm_calls == 1
    assert model.reasoner.max_tokens == 16000
    assert model.reasoner.api_style == "chat"
    model.reasoner._consume_call()
    assert model.reasoner.llm_calls == 2
    assert model.reasoner._raw_response("system", "user") == '{"ok":true}'
    assert model.response_diagnostics[0]["json_parse_status"] == "valid_object"
    model.reasoner._request(lambda: None, messages=[], response_format={"type": "json_object"})
    assert "response_format" not in model.reasoner.request_kwargs
    assert model.reasoner.request_kwargs["extra_body"] == {
        "reasoning": {"enabled": False},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    with pytest.raises(LLMBudgetError):
        model.reasoner._consume_call()


@pytest.mark.skipif(not hasattr(signal, "setitimer"), reason="POSIX request alarm")
def test_batch_request_deadline_is_restored_after_provider_failure():
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(LLMTransientError, match="wall-clock deadline"):
        with model_request_deadline(300):
            signal.raise_signal(signal.SIGALRM)
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def test_attempt_evidence_is_append_only(monkeypatch, tmp_path):
    monkeypatch.setattr("research.experiments.online_tuning_batch01.RUN_DIR", tmp_path)
    first, result, extraction = next_attempt_paths(1)
    assert (first, result.name, extraction.name) == (
        1, "case-01.json", "case-01-extraction.json")
    result.write_text("{}", encoding="utf-8")
    second, result, extraction = next_attempt_paths(1)
    assert (second, result.name, extraction.name) == (
        2, "case-01-attempt-02.json", "case-01-attempt-02-extraction.json")


def test_batch_wiring_reaches_compiler_without_granting_human_authority():
    core = funded_choice_core()

    class StaticModel:
        def generate(self, system, user):
            return core

    pipeline = build_research_pipeline(model=StaticModel(), wiring=batch_wiring())
    run = pipeline.run(core["requirement_history"], stop_after="compile", options={
        "core_schema_version": CORE_SCHEMA_VERSION_V2,
        "allow_simulated_intent": True,
        "simulation_transcript": [],
    })
    assert run.stages["intent_extraction"].run_status == StageRunStatus.SUCCEEDED
    assert run.stages["intent_acceptance"].run_status == StageRunStatus.SUCCEEDED
    assert run.stages["compile"].run_status == StageRunStatus.SUCCEEDED
    accepted = next(pipeline.store.get(item) for item in
                    run.stages["intent_acceptance"].output_artifacts
                    if item.startswith("accepted-intent:"))
    contract = next(pipeline.store.get(item) for item in
                    run.stages["compile"].output_artifacts
                    if item.startswith("contract-candidate:"))
    assert accepted.authority_level == AuthorityLevel.NO_AUTHORITY
    assert accepted.payload["simulation_only"] is True
    assert contract.payload["simulation_only"] is True


def test_failed_extraction_is_not_implicitly_retried_on_resume(monkeypatch, tmp_path):
    class FlakyModel:
        calls = 0

        def generate(self, system, user):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("provider failed")
            return funded_choice_core()

    model = FlakyModel()
    monkeypatch.setattr("research.experiments.online_tuning_batch01.RUN_DIR", tmp_path)
    monkeypatch.setattr("research.experiments.online_tuning_batch01.LegacyReasonerTransport",
                        lambda _: model)
    monkeypatch.setattr("research.experiments.online_tuning_batch01.attach_global_budget",
                        lambda *args: None)
    result = run_one(1, core_schema_version=CORE_SCHEMA_VERSION_V2)
    assert model.calls == 1
    assert result["stages"]["intent_extraction"]["run_status"] == "FAILED"
    assert "intent_acceptance" not in result["stages"]
    assert not (tmp_path / "case-01-extraction.json").exists()
    assert json.loads((tmp_path / "case-01.json").read_text(encoding="utf-8"))["candidate"] is None


def test_reuse_requires_same_history_schema_and_extraction_source(monkeypatch, tmp_path):
    core = funded_choice_core()
    monkeypatch.setattr("research.experiments.online_tuning_batch01.RUN_DIR", tmp_path)
    monkeypatch.setattr("research.experiments.online_tuning_batch01.extraction_source_sha256",
                        lambda: "current-source")
    path = tmp_path / "case-01-attempt-06-extraction.json"
    path.write_text(json.dumps({"case_id": "fixture", "source_sha256": "current-source",
                                "core_schema_version": CORE_SCHEMA_VERSION_V2,
                                "semantic_core": core}), encoding="utf-8")
    found = reusable_extraction(1, 7, "fixture", core["requirement_history"],
                                CORE_SCHEMA_VERSION_V2)
    assert found is not None and found[1] == path
    assert reusable_extraction(1, 7, "fixture", [{"version": 1, "messages": ["changed"]}],
                               CORE_SCHEMA_VERSION_V2) is None
    monkeypatch.setattr("research.experiments.online_tuning_batch01.extraction_source_sha256",
                        lambda: "new-source")
    assert reusable_extraction(1, 7, "fixture", core["requirement_history"],
                               CORE_SCHEMA_VERSION_V2) is None


def test_synthetic_input_preserves_answer_revisions_and_rejects_evaluator_fields(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"revisions": [["first"], ["second"]],
                                "simulation_transcript": []}), encoding="utf-8")
    assert load_synthetic_input(path) == ([["first"], ["second"]], [])
    path.write_text(json.dumps({"answers": ["first"], "simulation_transcript": [],
                                "checks": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_synthetic_input(path)
