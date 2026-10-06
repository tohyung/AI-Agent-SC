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


def test_request_journal_runs_before_outbound_call_and_limit_stops_retry(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_API_STYLE", "chat")
    events = []

    class ProviderLimit(Exception):
        status_code = 429

    def create(**_kwargs):
        events.append("outbound")
        raise ProviderLimit("provider body is not for logs")

    client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create)))
    model = ModelTransport("offline-test", client=client,
                           before_request=lambda phase: events.append(phase))
    with pytest.raises(ModelTransportError) as caught:
        model.generate("system", "user")
    assert events == ["generation", "outbound"]
    assert caught.value.code == "provider_limit"
    assert caught.value.status_code == 429
    assert model.llm_calls == 1
    assert "provider body" not in str(caught.value)


def test_chat_transport_can_disable_reasoning_without_exposing_keys(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    observed = []

    def create(**kwargs):
        observed.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'),
                                     finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = ModelTransport("offline-test", client=client, api_style="chat",
                           max_tokens=16000, disable_reasoning=True)
    assert model.generate("system", "user") == {"ok": True}
    assert observed[0]["max_tokens"] == 16000
    assert observed[0]["extra_body"]["reasoning"] == {"enabled": False}
    assert observed[0]["extra_body"]["chat_template_kwargs"] == {
        "enable_thinking": False}
    assert model.call_log[0]["finish_reason"] == "stop"
    assert "test-secret" not in str(model.call_log)


def test_prompt_only_json_mode_omits_unsupported_response_format(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    observed = []

    def create(**kwargs):
        observed.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = ModelTransport("offline-test", client=client, api_style="chat",
                           request_json_object=False)
    assert model.generate("system", "user") == {"ok": True}
    assert "response_format" not in observed[0]


def test_empty_output_retry_is_counted_and_journal_failure_sends_nothing(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_API_STYLE", "chat")
    monkeypatch.setattr("research.integrations.model_transport.time.sleep", lambda _s: None)
    phases = []
    model = ModelTransport("offline-test", client=_client(["", '{"ok":true}']),
                           before_request=phases.append)
    assert model.generate("system", "user") == {"ok": True}
    assert phases == ["generation", "generation"]
    assert model.llm_calls == 2

    phases.clear()
    model = ModelTransport("offline-test", client=_client(["", '{"ok":true}']),
                           before_request=phases.append, retry_empty=False)
    with pytest.raises(ModelTransportError) as caught:
        model.generate("system", "user")
    assert caught.value.code == "empty_model_output"
    assert phases == ["generation"]
    assert model.llm_calls == 1

    def unavailable(_phase):
        raise OSError("journal unavailable")

    model = ModelTransport("offline-test", client=_client(['{"ok":true}']),
                           before_request=unavailable)
    with pytest.raises(ModelTransportError) as caught:
        model.generate("system", "user")
    assert caught.value.code == "request_journal_unavailable"
    assert model.llm_calls == 0


def test_empty_chat_response_records_only_safe_shape_metadata(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")

    def create(**_kwargs):
        return SimpleNamespace(choices=[], model_extra={
            "error": {"code": 429, "message": "secret and sensitive provider details"}})

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = ModelTransport("offline-test", client=client, api_style="chat", retry_empty=False)
    with pytest.raises(ModelTransportError, match="provider_limit") as caught:
        model.generate("system", "user")
    assert caught.value.status_code == 429
    assert model.call_log[0]["choices_count"] == 0
    assert model.call_log[0]["provider_error_present"] is True
    assert model.call_log[0]["provider_error_code"] == 429
    assert "sensitive provider details" not in str(model.call_log)


def test_embedded_provider_503_retries_and_journals_each_physical_call(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-secret-not-for-output")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setattr("research.integrations.model_transport.time.sleep", lambda _s: None)
    phases = []
    responses = iter([
        SimpleNamespace(choices=[], model_extra={"error": {
            "code": 503, "message": "sensitive provider body"}}),
        SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"ok":true}'))],
            model_extra={}, usage=SimpleNamespace(
                prompt_tokens=1, completion_tokens=1, total_tokens=2)),
    ])
    client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **_kwargs: next(responses))))
    model = ModelTransport("offline-test", client=client, api_style="chat",
                           before_request=phases.append)
    assert model.generate("system", "user") == {"ok": True}
    assert phases == ["generation", "generation"]
    assert model.llm_calls == 2
    assert [item.get("provider_error_code") for item in model.call_log] == [503, None]
    assert "sensitive provider body" not in str(model.call_log)
