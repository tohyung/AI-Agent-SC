"""Offline tests for request accounting and phase-safe shadow errors."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from marlowe_ai_agent.marlowe_agent.models import LLMPhaseError, LLMTransientError
from marlowe_ai_agent.marlowe_agent.openai_reasoner import OpenAIReasoner
from research.stage2b import run_shadow, shadow_extractor


SECRET = "sk-test-secret-never-log"


def reasoner() -> OpenAIReasoner:
    model = OpenAIReasoner.__new__(OpenAIReasoner)
    model.model = "fake"
    model.call_log = []
    model.max_llm_calls = None
    model.llm_calls = 0
    model.max_tokens = 100
    model.retry_attempts = 1
    model.retry_base_delay = 0
    model.base_url = None
    return model


def sdk_decode_failure(**_kwargs):
    try:
        raise json.JSONDecodeError(SECRET, SECRET, 0)
    except json.JSONDecodeError as exc:
        raise RuntimeError(SECRET) from exc


def assert_transport_decode(error: LLMPhaseError) -> None:
    assert isinstance(error, LLMTransientError)
    assert error.phase == "transport_response_decode"
    assert error.code == "transport_response_decode_error"
    assert error.model_content_received is False
    assert error.repair_attempted is False
    assert SECRET not in str(error)


def test_failed_request_still_records_one_invocation_without_usage():
    model = reasoner()

    def fail(**_kwargs):
        raise RuntimeError(SECRET)

    with pytest.raises(RuntimeError):
        model._request(fail, prompt=SECRET)
    assert len(model.call_log) == 1
    assert model.usage_summary()["calls"] == 1
    assert model.call_log[0]["prompt_tokens"] is None
    assert model.call_log[0]["completion_tokens"] is None
    assert model.call_log[0]["cost"] is None
    assert model.usage_summary()["cost"] is None
    assert SECRET not in str(model.call_log)


def test_request_tags_nested_sdk_decode_failure_at_boundary():
    model = reasoner()
    with pytest.raises(LLMPhaseError) as caught:
        model._request(sdk_decode_failure)
    assert_transport_decode(caught.value)
    assert len(model.call_log) == 1
    assert model.usage_summary()["calls"] == 1


@pytest.mark.parametrize("route", ["responses", "chat", "chat_fallback"])
def test_transport_phase_survives_reasoner_routes(route):
    model = reasoner()
    model.client = SimpleNamespace(
        responses=SimpleNamespace(create=sdk_decode_failure),
        chat=SimpleNamespace(completions=SimpleNamespace(create=sdk_decode_failure)),
    )
    model.api_style = "chat" if route != "responses" else "responses"
    with pytest.raises(LLMPhaseError) as caught:
        if route == "chat_fallback":
            model._raw_chat_response("system", "user")
        else:
            model._raw_response("system", "user")
    assert_transport_decode(caught.value)
    assert len(model.call_log) == (1 if route == "responses" else 2)


def test_chat_json_mode_fallback_still_runs_after_sdk_decode_error():
    model = reasoner()
    model.api_style = "chat"
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return sdk_decode_failure()
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"ok": true}'))])

    model.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert model._json_response("system", "user") == {"ok": True}
    assert len(calls) == len(model.call_log) == 2
    assert "response_format" in calls[0] and "response_format" not in calls[1]


def test_model_content_repair_failure_has_parse_phase():
    model = reasoner()
    calls = []

    def raw(system, user):
        calls.append((system, user))
        return "not JSON" if len(calls) == 1 else "{broken"

    model._raw_response = raw
    with pytest.raises(LLMPhaseError) as caught:
        model._json_response("system", "user")
    error = caught.value
    assert error.phase == "model_output_parse"
    assert error.code == "model_output_invalid_after_repair"
    assert error.model_content_received is True
    assert error.repair_attempted is True
    assert len(calls) == 2
    assert calls[1][0].startswith("You repair invalid JSON")


def test_model_content_repair_success_is_unchanged():
    model = reasoner()
    calls = []

    def raw(system, user):
        calls.append((system, user))
        return "not JSON" if len(calls) == 1 else '{"ok": true}'

    model._raw_response = raw
    assert model._json_response("system", "user") == {"ok": True}
    assert len(calls) == 2
    assert calls[1][0].startswith("You repair invalid JSON")


def generic_with_json_cause() -> LLMTransientError:
    error = LLMTransientError(SECRET)
    error.__cause__ = json.JSONDecodeError(SECRET, SECRET, 0)
    return error


@pytest.mark.parametrize(("failure", "phase", "code", "content", "repair"), [
    (LLMPhaseError(phase="transport_response_decode",
                   code="transport_response_decode_error",
                   model_content_received=False, repair_attempted=False),
     "transport_response_decode", "transport_response_decode_error", False, False),
    (LLMPhaseError(phase="model_output_parse",
                   code="model_output_invalid_after_repair",
                   model_content_received=True, repair_attempted=True),
     "model_output_parse", "model_output_invalid_after_repair", True, True),
    (json.JSONDecodeError(SECRET, SECRET, 0),
     "model_output_parse", "model_output_invalid_json", True, False),
    (shadow_extractor.InvalidModelOutput(SECRET),
     "model_output_schema", "invalid_model_output", True, False),
    (TimeoutError(SECRET), "transport_request", "provider_timeout", False, False),
    (LLMTransientError(SECRET), "unknown", "provider_error", None, None),
    (generic_with_json_cause(), "unknown", "provider_error", None, None),
])
def test_runner_sanitizes_each_failure_phase_without_secret(
        tmp_path, monkeypatch, capsys, failure, phase, code, content, repair):
    failure.__cause__ = failure.__cause__ or RuntimeError(SECRET)

    class FakeTransport:
        def __init__(self, _model):
            self.reasoner = SimpleNamespace(model="fake")
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            raise failure

        def usage(self):
            return {"calls": self.calls, "latency_seconds": None,
                    "prompt_tokens": None, "completion_tokens": None,
                    "cost": None}

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "error.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--case-id", "pay-d1",
                                          "--output", str(output)])
    assert run_shadow.main() == 2
    recorded = output.read_text(encoding="utf-8")
    row = json.loads(recorded)
    assert row["run_status"] == "model_error"
    assert row["model_error"] == {
        "code": code, "phase": phase,
        "message": run_shadow._sanitized_model_error(failure)["message"],
        "model_content_received": content, "repair_attempted": repair,
    }
    assert row["usage"]["calls"] == 1
    captured = capsys.readouterr()
    assert SECRET not in recorded + captured.out + captured.err


def test_generic_json_cause_does_not_determine_phase():
    result = run_shadow._sanitized_model_error(generic_with_json_cause())
    assert result["phase"] == "unknown"
    assert result["code"] == "provider_error"
