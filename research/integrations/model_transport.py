"""OpenAI-compatible JSON transport shared by live intent and contract generation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any


class ModelTransportError(RuntimeError):
    def __init__(self, code: str, phase: str, *, content_received: bool = False,
                 repair_attempted: bool = False) -> None:
        self.code = code
        self.phase = phase
        self.model_content_received = content_received
        self.repair_attempted = repair_attempted
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
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


class ModelTransport:
    def __init__(self, model: str | None = None, *, client: Any | None = None) -> None:
        _load_env()
        self.model = model or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
        key = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.api_style = os.getenv("LLM_API_STYLE") or ("chat" if self.base_url else "responses")
        try:
            self.max_tokens = int(os.getenv("LLM_MAX_TOKENS") or "8000")
            self.retries = int(os.getenv("LLM_RETRY_ATTEMPTS") or "3")
            self.retry_delay = float(os.getenv("LLM_RETRY_BASE_DELAY") or "2")
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS") or "90")
        except ValueError as exc:
            raise ModelTransportError("invalid_configuration", "configuration") from exc
        if not self.model or not key or self.max_tokens < 1 or self.retries < 1 or timeout <= 0:
            raise ModelTransportError("missing_or_invalid_configuration", "configuration")
        if self.api_style not in {"chat", "responses"}:
            raise ModelTransportError("invalid_api_style", "configuration")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ModelTransportError("sdk_unavailable", "configuration") from exc
            kwargs: dict[str, Any] = {"api_key": key, "timeout": timeout}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            try:
                client = OpenAI(**kwargs)
            except (TypeError, ValueError) as exc:
                raise ModelTransportError("invalid_client_configuration", "configuration") from exc
        self.client = client
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
                response = self.client.chat.completions.create(**kwargs)
                choices = getattr(response, "choices", None)
                content = choices[0].message.content if choices else None
            else:
                kwargs = {"model": self.model, "input": messages,
                          "max_output_tokens": self.max_tokens}
                if json_mode:
                    kwargs["text"] = {"format": {"type": "json_object"}}
                response = self.client.responses.create(**kwargs)
                content = getattr(response, "output_text", None)
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
                return self._request(system, user, phase=phase)
            except ModelTransportError:
                raise
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                message = str(exc).lower()
                if status == 400 and ("response_format" in message or "json_object" in message):
                    try:
                        return self._request(system, user, phase=phase, json_mode=False)
                    except Exception as fallback_exc:
                        raise ModelTransportError("provider_request_failed", phase) from fallback_exc
                if status in {408, 429, 500, 502, 503, 504} and attempt + 1 < self.retries:
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue
                raise ModelTransportError("provider_request_failed", phase) from exc
        raise ModelTransportError("provider_request_failed", phase)

    def generate(self, system: str, user: str) -> dict[str, Any]:
        content = self._retry_request(system, user, phase="generation")
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            repair = self._retry_request(
                "Return only one complete JSON object. Preserve the original task and meaning.",
                f"Original system:\n{system}\nOriginal user:\n{user}\nInvalid response:\n{content[:3500]}",
                phase="json_repair",
            )
            try:
                result = json.loads(repair)
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
