"""OpenAI-compatible JSON transport shared by live intent and contract generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from collections.abc import Callable
from typing import Any


class ModelTransportError(RuntimeError):
    def __init__(self, code: str, phase: str, *, content_received: bool = False,
                 repair_attempted: bool = False, status_code: int | None = None) -> None:
        self.code = code
        self.phase = phase
        self.model_content_received = content_received
        self.repair_attempted = repair_attempted
        self.status_code = status_code
        super().__init__(f"Model transport failed: {code}")


def _load_env() -> None:
    project = Path(__file__).resolve().parents[2] / "marlowe_ai_agent" / ".env"
    for path in (Path.cwd() / ".env", project):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key.isidentifier() and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")
        break


def _usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    return {
        "prompt_tokens": prompt if prompt is not None else getattr(usage, "input_tokens", None),
        "completion_tokens": (completion if completion is not None else
                              getattr(usage, "output_tokens", None)),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _parse_json_content(content: str) -> Any:
    source = content.strip().lstrip("\ufeff")
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", source,
                          flags=re.DOTALL | re.IGNORECASE)
    if fenced is not None:
        source = fenced.group(1)
    return json.loads(source)


class ModelTransport:
    def __init__(self, model: str | None = None, *, client: Any | None = None,
                 before_request: Callable[[str], None] | None = None,
                 api_style: str | None = None, max_tokens: int | None = None,
                 disable_reasoning: bool = False, retry_empty: bool = True,
                 request_json_object: bool = True) -> None:
        _load_env()
        self.model = model or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
        key = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.api_style = api_style or os.getenv("LLM_API_STYLE") or (
            "chat" if self.base_url else "responses")
        try:
            self.max_tokens = (max_tokens if max_tokens is not None else
                               int(os.getenv("LLM_MAX_TOKENS") or "8000"))
            self.retries = int(os.getenv("LLM_RETRY_ATTEMPTS") or "3")
            self.retry_delay = float(os.getenv("LLM_RETRY_BASE_DELAY") or "2")
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS") or "90")
        except ValueError as exc:
            raise ModelTransportError("invalid_configuration", "configuration") from exc
        if (not self.model or not key or type(self.max_tokens) is not int
                or self.max_tokens < 1 or self.retries < 1 or timeout <= 0):
            raise ModelTransportError("missing_or_invalid_configuration", "configuration")
        if self.api_style not in {"chat", "responses"}:
            raise ModelTransportError("invalid_api_style", "configuration")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ModelTransportError("sdk_unavailable", "configuration") from exc
            kwargs: dict[str, Any] = {"api_key": key, "timeout": timeout,
                                      "max_retries": 0}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            try:
                client = OpenAI(**kwargs)
            except (TypeError, ValueError) as exc:
                raise ModelTransportError("invalid_client_configuration", "configuration") from exc
        elif hasattr(client, "with_options"):
            client = client.with_options(max_retries=0)
        self.client = client
        self.before_request = before_request
        self.disable_reasoning = disable_reasoning
        self.retry_empty = retry_empty
        self.request_json_object = request_json_object
        self.max_llm_calls: int | None = None
        self.llm_calls = 0
        self.call_log: list[dict[str, Any]] = []

    def set_call_budget(self, limit: int | None) -> None:
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("call budget must be a positive integer")
        self.max_llm_calls = limit
        self.llm_calls = 0

    def _request(self, system: str, user: str, *, phase: str,
                 json_mode: bool = True) -> str:
        if self.max_llm_calls is not None and self.llm_calls >= self.max_llm_calls:
            raise ModelTransportError("physical_call_budget_exhausted", "budget")
        if self.before_request is not None:
            try:
                self.before_request(phase)
            except OSError as exc:
                raise ModelTransportError("request_journal_unavailable", "local_audit") from exc
        self.llm_calls += 1
        entry: dict[str, Any] = {"phase": phase, "model": self.model,
                                 "status": "error", "prompt_tokens": None,
                                 "completion_tokens": None, "total_tokens": None}
        self.call_log.append(entry)
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        try:
            if self.api_style == "chat":
                kwargs: dict[str, Any] = {"model": self.model, "messages": messages,
                                          "max_tokens": self.max_tokens}
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                if self.disable_reasoning:
                    kwargs["extra_body"] = {
                        "reasoning": {"enabled": False},
                        "chat_template_kwargs": {"enable_thinking": False},
                    }
                response = self.client.chat.completions.create(**kwargs)
                choices = getattr(response, "choices", None)
                entry["choices_count"] = len(choices) if isinstance(choices, list) else None
                extra = getattr(response, "model_extra", None)
                provider_error = extra.get("error") if isinstance(extra, dict) else None
                entry["provider_error_present"] = bool(provider_error)
                if isinstance(provider_error, dict):
                    code = provider_error.get("code")
                    if type(code) is int or (isinstance(code, str) and code.isdecimal()):
                        entry["provider_error_code"] = int(code)
                if provider_error:
                    code = entry.get("provider_error_code")
                    raise ModelTransportError(
                        "provider_limit" if code in {402, 429} else "provider_reported_error",
                        phase, status_code=code)
                content = choices[0].message.content if choices else None
                entry["finish_reason"] = getattr(choices[0], "finish_reason", None) if choices else None
            else:
                kwargs = {"model": self.model, "input": messages,
                          "max_output_tokens": self.max_tokens}
                if json_mode:
                    kwargs["text"] = {"format": {"type": "json_object"}}
                response = self.client.responses.create(**kwargs)
                content = getattr(response, "output_text", None)
                entry["response_status"] = getattr(response, "status", None)
        except ModelTransportError:
            raise
        except Exception as exc:
            entry["exception_type"] = type(exc).__name__
            raise
        entry.update(_usage(response))
        if not isinstance(content, str) or not content.strip():
            entry["status"] = "empty"
            raise ModelTransportError("empty_model_output", phase)
        entry["status"] = "ok"
        return content

    def _retry_request(self, system: str, user: str, *, phase: str) -> str:
        for attempt in range(self.retries):
            try:
                return self._request(system, user, phase=phase,
                                     json_mode=self.request_json_object)
            except ModelTransportError as exc:
                if (exc.code == "empty_model_output" and self.retry_empty
                        and attempt + 1 < self.retries):
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                if (exc.code == "provider_reported_error"
                        and exc.status_code in {408, 500, 502, 503, 504}
                        and attempt + 1 < self.retries):
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if status in {402, 429}:
                    raise ModelTransportError("provider_limit", phase,
                                              status_code=status) from None
                message = str(exc).lower()
                if status == 400 and ("response_format" in message or "json_object" in message):
                    try:
                        return self._request(system, user, phase=phase, json_mode=False)
                    except Exception as fallback_exc:
                        fallback_status = getattr(fallback_exc, "status_code", None)
                        if fallback_status in {402, 429}:
                            raise ModelTransportError("provider_limit", phase,
                                                      status_code=fallback_status) from None
                        raise ModelTransportError("provider_request_failed", phase) from fallback_exc
                if status in {408, 429, 500, 502, 503, 504} and attempt + 1 < self.retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise ModelTransportError("provider_request_failed", phase) from exc
        raise ModelTransportError("provider_request_failed", phase)

    def generate(self, system: str, user: str) -> dict[str, Any]:
        content = self._retry_request(system, user, phase="generation")
        try:
            result = _parse_json_content(content)
        except json.JSONDecodeError:
            repair = self._retry_request(
                "Return only one complete JSON object. Preserve the original task and meaning.",
                f"Original system:\n{system}\nOriginal user:\n{user}\nInvalid response:\n{content[:3500]}",
                phase="json_repair",
            )
            try:
                result = _parse_json_content(repair)
            except json.JSONDecodeError as exc:
                raise ModelTransportError("invalid_json_after_repair", "model_output_parse",
                                          content_received=True, repair_attempted=True) from exc
        if not isinstance(result, dict):
            raise ModelTransportError("non_object_model_output", "model_output_schema",
                                      content_received=True)
        return result

    def usage_summary(self) -> dict[str, Any]:
        return {"api_calls": self.llm_calls,
                "prompt_tokens": sum(item["prompt_tokens"] or 0 for item in self.call_log),
                "completion_tokens": sum(item["completion_tokens"] or 0 for item in self.call_log),
                "total_tokens": sum(item["total_tokens"] or 0 for item in self.call_log)}
