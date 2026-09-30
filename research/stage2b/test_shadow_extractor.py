"""Shadow transport and CLI tests using only fake models."""

from __future__ import annotations

import json
import sys

import pytest

from research.stage2b import run_shadow, shadow_extractor
from research.stage2b.test_intent_spec import simple_payment


class FakeModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, system, user):
        self.calls.append((system, user))
        return self.response


def test_fake_extractor_separates_prompt_transport_parse_and_validation():
    spec = simple_payment()
    model = FakeModel(spec)
    result = shadow_extractor.IntentShadowExtractor(model).extract(spec["requirement_history"])
    assert result.to_dict() == spec
    assert result.validation_errors(expected_history=spec["requirement_history"]) == []
    assert len(model.calls) == 1
    system, user = model.calls[0]
    assert "Do NOT generate Marlowe AST" in system
    assert "transaction_submitter" in system
    assert "10 ADA" in user


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

        def generate(self, system, user):
            calls.append((system, user))
            return simple_payment()

        def usage(self):
            return {"calls": 1}

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "live.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--case-id", "pay-d1",
                                          "--output", str(output)])
    assert run_shadow.main() == 0
    row = json.loads(output.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert row["model"] == "fake" and row["usage"] == {"calls": 1}
    assert row["prediction"]["schema_version"] == "stage2b-shadow-v1"
    assert "requirement_history differs from supplied source" in row["validation_errors"]
