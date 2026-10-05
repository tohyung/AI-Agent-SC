"""Offline transport accounting and secret-safe errors."""

from types import SimpleNamespace

import pytest

from research.integrations.model_transport import ModelTransport, ModelTransportError


def _client(contents):
    responses = iter(contents)

    def create(**_kwargs):
        content = next(responses)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_json_repair_counts_physical_requests(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_API_STYLE", "chat")
    model = ModelTransport("offline-test", client=_client(["not json", '{"ok":true}']))
    model.set_call_budget(2)
    assert model.generate("system", "user") == {"ok": True}
    assert model.usage_summary() == {"api_calls": 2, "prompt_tokens": 20,
                                     "completion_tokens": 10, "total_tokens": 30}
    with pytest.raises(ModelTransportError) as caught:
        model.generate("system", "user")
    assert caught.value.code == "physical_call_budget_exhausted"
    assert "test-secret" not in str(caught.value)


def test_bad_json_after_repair_is_typed_without_raw_content(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_API_STYLE", "chat")
    model = ModelTransport("offline-test", client=_client(["{broken", "still broken"]))
    with pytest.raises(ModelTransportError) as caught:
        model.generate("system", "user")
    assert caught.value.code == "invalid_json_after_repair"
    assert caught.value.repair_attempted is True
    assert "broken" not in str(caught.value)
