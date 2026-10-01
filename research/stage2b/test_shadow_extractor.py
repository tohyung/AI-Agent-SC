"""Shadow transport and CLI tests using only fake models."""

from __future__ import annotations

import json
import sys

import pytest

from marlowe_ai_agent.marlowe_agent.models import LLMConfigError, LLMTransientError
from research.stage2b import intent_spec, run_shadow, shadow_extractor
from research.stage2b.test_intent_spec import simple_payment


class FakeModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, system, user):
        self.calls.append((system, user))
        return self.response


def test_fake_extractor_separates_prompt_transport_parse_and_validation():
    spec = intent_spec.extract_core_view(simple_payment())
    model = FakeModel(spec)
    result = shadow_extractor.IntentShadowExtractor(model).extract(spec["requirement_history"])
    assert result.to_dict() == spec
    assert result.validation_errors(expected_history=spec["requirement_history"]) == []
    assert len(model.calls) == 1
    system, user = model.calls[0]
    assert "Do NOT generate Marlowe AST" in system
    assert "transaction_submitter" in system
    assert "10 ADA" in user
    assert "transaction_submitter" not in user
    assert "value=null" in user and "evidence=[]" in user
    assert "normalization_basis" in user and "ShadowSemanticCore" in system


def test_prompt_contract_tracks_validator_enums(monkeypatch):
    contract = intent_spec.core_prompt_schema_contract()
    fields = {
        "statuses": (contract["claim"]["statuses"], intent_spec.CLAIM_STATUSES),
        "criticalities": (contract["claim"]["criticalities"], intent_spec.CRITICALITIES),
        "resolutions": (contract["resolution"]["values"], intent_spec.RESOLUTIONS),
        "scope_types": (contract["scope"]["types"], intent_spec.SCOPE_TYPES),
        "evidence": (contract["evidence"]["relations"], intent_spec.EVIDENCE_RELATIONS),
    }
    assert all(actual == sorted(expected) for actual, expected in fields.values())
    _, user = shadow_extractor.build_prompt(simple_payment()["requirement_history"])
    embedded = json.loads(user.split("Validator schema contract (closed enum/field vocabulary):\n", 1)[1]
                          .split("\n", 1)[0])
    assert embedded == contract
    for key, value in (("CLAIM_STATUSES", "new-status"),
                       ("RESOLUTIONS", "new-resolution"),
                       ("SCOPE_TYPES", "new-scope"),
                       ("CRITICALITIES", "new-criticality"),
                       ("EVIDENCE_RELATIONS", "new-relation")):
        monkeypatch.setattr(intent_spec, key, getattr(intent_spec, key) | {value})
    updated = intent_spec.core_prompt_schema_contract()
    assert "new-status" in updated["claim"]["statuses"]
    assert "new-resolution" in updated["resolution"]["values"]
    assert "new-scope" in updated["scope"]["types"]
    assert "new-criticality" in updated["claim"]["criticalities"]
    assert "new-relation" in updated["evidence"]["relations"]
    spec = intent_spec.extract_core_view(simple_payment())
    spec["claims"][0]["criticality"] = "new-criticality"
    assert not any("invalid criticality" in error for error in intent_spec.validate_shadow_semantic_core(spec))
    spec = intent_spec.extract_core_view(simple_payment())
    spec["claims"][0]["evidence"][0]["relation"] = "new-relation"
    assert not any("invalid evidence target/span" in error
                   for error in intent_spec.validate_shadow_semantic_core(spec))


def test_prompt_contract_covers_scope_and_rich_shapes():
    contract = intent_spec.prompt_schema_contract()
    assert contract["scope"]["allowed_fields_by_type"] == {
        key: sorted(value) for key, value in intent_spec.SCOPE_FIELDS.items()}
    assert contract["rich_fields"] == {
        key: sorted(value) for key, value in intent_spec.RICH_FIELDS.items()}
    assert contract["state_ids"] == sorted(intent_spec.STATE_IDS)
    assert contract["outcome_recipient_kinds"] == {
        key: sorted(value) for key, value in intent_spec.OUTCOME_RECIPIENT_KINDS.items()}


def test_parser_rejects_non_object_output():
    with pytest.raises(ValueError, match="JSON object"):
        shadow_extractor.parse_model_output(["not-an-object"])


def test_dry_run_default_loads_development_canonical_without_model(tmp_path, monkeypatch):
    def forbid_model(*_args, **_kwargs):
        raise AssertionError("dry-run must not instantiate live transport")

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", forbid_model)
    output = tmp_path / "dry-run.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--output", str(output)])
    assert run_shadow.main() == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10
    assert all(row["split"] == "development" for row in rows)
    assert all(row["prediction"] is None and "prompt" in row for row in rows)
    assert all(row["source_corpus_version"] == "stage2a-v1" for row in rows)


def test_validation_split_is_explicit(tmp_path, monkeypatch):
    output = tmp_path / "validation-prompts.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--split", "validation",
                                          "--output", str(output)])
    assert run_shadow.main() == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10
    assert all(row["split"] == "validation" for row in rows)


def test_live_requires_explicit_output_and_never_runs_by_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--case-id", "pay-d1"])
    with pytest.raises(SystemExit, match="2"):
        run_shadow.main()


def test_explicit_live_mode_uses_injected_fake_transport_only(tmp_path, monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, model):
            self.reasoner = type("Reasoner", (), {"model": model or "fake"})()
            self.calls = 0

        def generate(self, system, user):
            calls.append((system, user))
            self.calls += 1
            return intent_spec.extract_core_view(simple_payment())

        def usage(self):
            return {"calls": self.calls, "latency_seconds": self.calls * 0.5,
                    "prompt_tokens": self.calls * 10, "completion_tokens": self.calls * 20,
                    "cost": None}

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "live.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--case-id", "pay-d1",
                                          "--output", str(output)])
    assert run_shadow.main() == 0
    row = json.loads(output.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert row["model"] == "fake" and row["usage"] == {
        "calls": 1, "latency_seconds": 0.5, "prompt_tokens": 10,
        "completion_tokens": 20, "cost": None}
    assert row["run_status"] == "core_invalid"
    assert row["semantic_core"]["schema_version"] == "stage2b-shadow-core-v1"
    assert row["projection_diagnostics"]["core_status"] == "invalid"
    assert row["prediction"]["schema_version"] == "stage2b-shadow-v1"
    assert "requirement_history differs from supplied source" in row["validation_errors"]


def test_runner_records_valid_raw_core_projection_and_usage(tmp_path, monkeypatch):
    source = intent_spec.extract_core_view(simple_payment())

    class FakeAdapter:
        def load(self, **_kwargs):
            return [{"case_id": "synthetic", "split": "development",
                     "requirement_history": source["requirement_history"]}]

    class FakeTransport:
        def __init__(self, _model):
            self.reasoner = type("Reasoner", (), {"model": "fake"})()
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return source

        def usage(self):
            return {"calls": self.calls, "latency_seconds": self.calls * 0.1,
                    "prompt_tokens": self.calls * 10,
                    "completion_tokens": self.calls * 20, "cost": None}

    monkeypatch.setattr(run_shadow, "FrozenCandidateAdapter", FakeAdapter)
    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "native.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--output", str(output)])
    assert run_shadow.main() == 0
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["run_status"] == "ok" and row["projection_classification"] == "PASS"
    assert row["semantic_core"] == source and row["core_validation_errors"] == []
    assert row["validation_errors"] == []
    assert row["prediction"]["obligations_and_outcomes"][0]["recipient"] == "Bob"
    assert row["projection_diagnostics"]["mandatory_eligible_count"] > 0
    assert row["projection_diagnostics"]["complete"]
    assert row["usage"]["calls"] == 1


def test_model_failure_preserves_prior_rows_continues_and_sanitizes(tmp_path, monkeypatch, capsys):
    secret = "sk-test-secret-do-not-log"
    output = tmp_path / "partial.jsonl"

    class FakeTransport:
        def __init__(self, model):
            self.reasoner = type("Reasoner", (), {"model": "fake"})()
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            if self.calls == 2:
                completed = [json.loads(line) for line in
                             output.read_text(encoding="utf-8").splitlines()]
                assert len(completed) == 1 and completed[0]["run_status"] == "core_invalid"
                raise LLMTransientError(f"provider failed with key {secret}")
            return intent_spec.extract_core_view(simple_payment())

        def usage(self):
            return {"calls": self.calls, "latency_seconds": self.calls * 0.25,
                    "prompt_tokens": self.calls * 10, "completion_tokens": self.calls * 5,
                    "cost": self.calls * 0.01}

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--output", str(output)])
    assert run_shadow.main() == 2
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10
    assert rows[0]["run_status"] == "core_invalid"
    assert rows[1]["run_status"] == "model_error" and rows[1]["prediction"] is None
    assert rows[1]["model_error"]["code"] == "provider_error"
    assert rows[1]["usage"]["calls"] == 1
    assert rows[1]["usage"]["prompt_tokens"] == 10
    assert rows[2]["run_status"] == "core_invalid"
    assert secret not in output.read_text(encoding="utf-8")
    assert secret not in capsys.readouterr().out
    assert run_shadow._usage_total([row["usage"] for row in rows]) == {
        "calls": 10, "latency_seconds": 2.5, "prompt_tokens": 100,
        "completion_tokens": 50, "cost": pytest.approx(0.10)}


def test_unexpected_model_programming_error_propagates(tmp_path, monkeypatch):
    class BrokenTransport:
        def __init__(self, _model):
            self.reasoner = type("Reasoner", (), {"model": "fake"})()

        def generate(self, _system, _user):
            raise KeyError("programmer bug")

        def usage(self):
            return {"calls": 0}

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", BrokenTransport)
    output = tmp_path / "broken.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--case-id", "pay-d1",
                                          "--output", str(output)])
    with pytest.raises(KeyError, match="programmer bug"):
        run_shadow.main()


@pytest.mark.parametrize(("response", "code"), [
    ("not JSON", "invalid_model_json"),
    (["not-an-object"], "invalid_model_output"),
])
def test_model_parse_failures_are_recorded(tmp_path, monkeypatch, response, code):
    class FakeTransport:
        def __init__(self, _model):
            self.reasoner = type("Reasoner", (), {"model": "fake"})()

        def generate(self, _system, _user):
            return response

        def usage(self):
            return {"calls": 0}

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "parse-error.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--case-id", "pay-d1",
                                          "--output", str(output)])
    assert run_shadow.main() == 2
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["run_status"] == "model_error"
    assert row["model_error"]["code"] == code


def test_precheck_failures_do_not_truncate_existing_output(tmp_path, monkeypatch):
    output = tmp_path / "sentinel.jsonl"
    output.write_text("sentinel", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--output", str(output)])
    with monkeypatch.context() as patch:
        patch.setattr(run_shadow.verify_freeze, "verify_freeze",
                      lambda _: (_ for _ in ()).throw(ValueError("freeze failed")))
        assert run_shadow.main() == 2
    assert output.read_text(encoding="utf-8") == "sentinel"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--output", str(output)])
    with monkeypatch.context() as patch:
        patch.setattr(run_shadow, "LegacyReasonerTransport",
                      lambda _: (_ for _ in ()).throw(LLMConfigError("bad config")))
        assert run_shadow.main() == 2
    assert output.read_text(encoding="utf-8") == "sentinel"
