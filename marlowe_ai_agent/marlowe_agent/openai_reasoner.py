from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .marlowe_ast import escrow_contract, normalize_marlowe_ast
from .models import (
    ContractDraft,
    LLMError,
    LogicGraphResult,
    PartySpec,
    VerificationResult,
)
from .utils import unique_strings


class OpenAIReasoner:
    """LLM-only reasoner for prompt understanding and semantic verification."""

    def __init__(self, model: str | None = None) -> None:
        loaded_env = load_env_file()
        self.model = model or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Chua cai package openai. Hay chay: pip install -r requirements.txt") from exc

        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.api_style = os.getenv("LLM_API_STYLE") or ("chat" if self.base_url else "responses")
        try:
            self.timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS") or "90")
            self.max_tokens = int(os.getenv("LLM_MAX_TOKENS") or "8000")
            self.retry_attempts = int(os.getenv("LLM_RETRY_ATTEMPTS") or "3")
            self.retry_base_delay = float(os.getenv("LLM_RETRY_BASE_DELAY") or "2")
        except ValueError as exc:
            raise LLMError(f"Cấu hình số cho LLM không hợp lệ: {exc}") from exc
        self.max_llm_calls: int | None = None
        self.llm_calls = 0

        if not api_key:
            raise RuntimeError(
                "Chua co API key. Hay set LLM_API_KEY, OPENROUTER_API_KEY, hoac OPENAI_API_KEY.\n"
                f"Da tim file .env tai: {', '.join(str(path) for path in env_search_paths())}\n"
                f"File .env da doc: {loaded_env if loaded_env else 'khong co'}"
            )
        if not self.model:
            raise RuntimeError("Chua co model. Hay set LLM_MODEL trong .env hoac truyen --model.")

        client_kwargs: dict[str, Any] = {"api_key": api_key, "timeout": self.timeout_seconds}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        self.client = OpenAI(**client_kwargs)

    def draft_from_prompt(self, prompt: str) -> ContractDraft:
        extracted = self._extract_contract_config(prompt)
        normalized, notes = normalize_marlowe_ast(extracted.get("marlowe_contract") or {})
        parties = [
            PartySpec(str(party.get("role") or ""), str(party.get("name") or ""))
            for party in extracted.get("parties") or []
            if isinstance(party, dict)
        ]

        return ContractDraft(
            original_prompt=prompt,
            intent=str(extracted.get("intent") or ""),
            parties=parties,
            amount=_optional_int(extracted.get("amount")),
            token=extracted.get("token"),
            deposit_timeout=_optional_int(extracted.get("deposit_timeout")),
            decision_timeout=_optional_int(extracted.get("decision_timeout")),
            clauses=list(extracted.get("clauses") or []),
            assumptions=list(extracted.get("assumptions") or []),
            clarification_questions=list(extracted.get("clarification_questions") or extracted.get("questions") or []),
            reasoning_summary=str(extracted.get("reasoning_summary") or ""),
            reasoning_narrative=str(extracted.get("reasoning_narrative") or ""),
            contract_plan=dict(extracted.get("contract_plan") or {}),
            marlowe_contract=normalized,
            normalization_notes=notes,
        )

    def set_call_budget(self, limit: int | None) -> None:
        self.max_llm_calls = limit
        self.llm_calls = 0

    def _consume_call(self) -> None:
        if self.max_llm_calls is not None and self.llm_calls >= self.max_llm_calls:
            raise LLMError(f"Đã đạt giới hạn {self.max_llm_calls} lời gọi LLM.")
        self.llm_calls += 1

    def semantic_verify(self, prompt: str, draft: ContractDraft) -> VerificationResult:
        payload = {"prompt": _compact_text(prompt, 6000), "draft": _compact_draft_for_semantic(draft)}
        system = (
            "You are the semantic verification node of a Marlowe smart-contract AI agent. "
            "All user-facing fields MUST be written in Vietnamese. Reason from the user prompt, "
            "draft.contract_plan, and draft.marlowe_contract. Do not add facts not present in the input. "
            "Marlowe Close is the string 'close'; values are integer lovelace and timeouts are POSIX milliseconds. "
            "Check unit conversion: 250 ADA equals 250000000 lovelace. "
            "If important business information is missing, passed must be false and questions must contain "
            "specific Vietnamese business questions for the user. Do not ask vague questions about AST/JSON "
            "unless the user explicitly asks technical questions. "
            "reasoning_summary is short. reasoning_narrative is a natural intermediate explanation in Vietnamese, "
            "varied by context and not a rigid template, but not detailed chain-of-thought. "
            "Keep reasoning_narrative under 900 Vietnamese characters. Return only valid JSON."
        )
        user = (
            "Return valid JSON with this schema: "
            '{"passed": boolean, "score": number, '
            '"reasoning_summary": "short Vietnamese summary", '
            '"reasoning_narrative": "natural Vietnamese explanation under 900 characters", '
            '"findings": ["..."], "questions": ["..."]}. '
            f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        try:
            data = self._json_response(system, user)
        except LLMError:
            raise
        except RuntimeError as exc:
            raise LLMError(f"Semantic verification failed: {exc}") from exc
        questions = list(data.get("questions") or [])
        return VerificationResult(
            passed=bool(data.get("passed")) and not questions,
            score=float(data.get("score", 0.0)),
            findings=list(data.get("findings") or []),
            questions=questions,
            reasoning_summary=str(data.get("reasoning_summary") or ""),
            reasoning_narrative=str(data.get("reasoning_narrative") or ""),
        )

    def logic_feedback_to_clarification(
        self,
        prompt: str,
        draft: ContractDraft,
        logic: LogicGraphResult,
    ) -> dict[str, Any]:
        payload = {
            "prompt": prompt,
            "draft_summary": {
                "intent": draft.intent,
                "parties": [party.to_dict() for party in draft.parties],
                "amount": draft.amount,
                "token": draft.token,
                "deposit_timeout": draft.deposit_timeout,
                "decision_timeout": draft.decision_timeout,
                "clauses": draft.clauses,
                "assumptions": draft.assumptions,
            },
            "logic_findings": logic.findings,
        }
        system = (
            "You are Node 1 of a Marlowe smart-contract AI agent. "
            "Node 3 has returned logic/AST findings. Convert them into a small number of clear Vietnamese "
            "The AST uses standard Marlowe Core V1 JSON: Close is 'close', Choice uses for_choice/choose_between, "
            "amounts are lovelace and timeouts are POSIX milliseconds. "
            "business questions only when the user truly needs to decide business behavior. "
            "Never ask the user to fix AST, JSON, constructor names, fields, graph nodes, or Marlowe internals. "
            "If the findings are purely technical AST/JSON/constructor/schema errors, needs_user_input must be false "
            "and internal_instruction must tell the draft generator how to fix the Marlowe AST while preserving the user's intent. "
            "Deduplicate repeated findings. Ask at most 4 concise questions. "
            "reasoning_narrative must be a short Vietnamese explanation of what is missing or what will be fixed, "
            "not detailed chain-of-thought. Return only valid JSON."
        )
        user = (
            "Return valid JSON with this schema: "
            '{"needs_user_input": boolean, "questions": ["..."], '
            '"internal_instruction": "Vietnamese instruction for Node 1 draft regeneration", '
            '"reasoning_narrative": "Vietnamese explanation under 700 characters"}. '
            f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        data = self._json_response(system, user)
        questions = unique_strings(data.get("questions") or [])[:4]
        return {
            "needs_user_input": bool(data.get("needs_user_input")) and bool(questions),
            "questions": questions,
            "internal_instruction": str(data.get("internal_instruction") or ""),
            "reasoning_narrative": str(data.get("reasoning_narrative") or ""),
        }

    def _extract_contract_config(self, prompt: str) -> dict[str, Any]:
        system = (
            "You are the prompt-understanding node of a Marlowe smart-contract AI agent. "
            "All user-facing fields MUST be written in Vietnamese. Every judgment, assumption, clause, question, "
            "reasoning_summary, and reasoning_narrative must be inferred by you from the user's prompt, not from canned answers. "
            "Do not invent missing information. If important information is missing, set unknown fields to null or empty, "
            "write assumptions, and produce specific Vietnamese clarification_questions. "
            "If there is not enough information to safely create a contract, keep marlowe_contract as an empty object. "
            "When there is enough information, produce a Marlowe AST JSON using Close, Pay, If, When, Let, Assert; "
            "actions Deposit, Choice, Notify; and suitable values/observations. "
            "Use standard Core V1 JSON: Close is the string 'close', Constant is a bare integer, "
            "Choice uses for_choice/choose_between, timeouts are POSIX milliseconds, "
            "ADA amounts are lovelace (250 ADA = 250000000), and role_token equals party name. "
            "reasoning_summary is short. reasoning_narrative is a natural intermediate explanation in Vietnamese, "
            "varied by context and not a rigid template, but not detailed chain-of-thought. "
            "Keep reasoning_narrative under 900 Vietnamese characters. Return only valid JSON."
        )
        user = (
            "Return valid JSON with this schema: "
            '{"intent": string, "parties": [{"role": string, "name": string}], '
            '"amount": number|null, "token": string|null, "deposit_timeout": number|null, '
            '"decision_timeout": number|null, "reasoning_summary": string, "reasoning_narrative": string, '
            '"clauses": [string], "assumptions": [string], "clarification_questions": [string], '
            '"contract_plan": {"nodes": [], "edges": [], "notes": []}, "marlowe_contract": object|string}. '
            "Reference escrow JSON: "
            + json.dumps(escrow_contract("Alice", "Bob", 250000000, 1893456000000, 1893542400000),
                         ensure_ascii=False, separators=(",", ":"))
            + ". "
            f"Prompt: {prompt}"
        )
        return self._json_response(system, user)

    def _json_response(self, system: str, user: str) -> dict[str, Any]:
        content = self._raw_response(system, user)
        try:
            return parse_json_text(content)
        except json.JSONDecodeError as exc:
            error_text = str(exc)
            if not content.strip():
                retry_user = (
                    "The previous response was empty. Return only one valid JSON object for this task. "
                    "No markdown, no prose outside JSON.\n\n"
                    f"Original task:\n{user}"
                )
                content = self._raw_response(system, retry_user)
                try:
                    return parse_json_text(content)
                except json.JSONDecodeError as retry_exc:
                    error_text = str(retry_exc)

            repair_system = (
                "You repair invalid JSON produced by a model. Return only valid minified JSON. "
                "Do not add markdown. Preserve the same schema and meaning when possible. "
                "All user-facing text remains Vietnamese. Keep narrative fields short."
            )
            repair_user = (
                f"The previous JSON was invalid with error: {error_text}. "
                "Regenerate a complete valid JSON response for the original task. "
                "Use shorter strings if needed to avoid truncation.\n\n"
                f"Original system instruction:\n{system}\n\n"
                f"Original user instruction:\n{user}\n\n"
                f"Invalid response preview:\n{content[:3500] or '<empty response>'}"
            )
            repaired = self._raw_response(repair_system, repair_user)
            try:
                return parse_json_text(repaired)
            except json.JSONDecodeError as repair_exc:
                raise LLMError(
                    "Model tra ve JSON khong hop le ngay ca sau khi yeu cau sua. "
                    "Hay tang LLM_MAX_TOKENS hoac doi model co JSON mode on dinh hon. "
                    f"Loi ban dau: {error_text}. Loi sau sua: {repair_exc}. "
                    f"Do dai response goc: {len(content)}. Do dai response sua: {len(repaired)}."
                ) from repair_exc

    def _raw_response(self, system: str, user: str) -> str:
        if self.api_style == "chat":
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            last_debug = ""
            for attempt in range(1, self.retry_attempts + 1):
                try:
                    try:
                        self._consume_call()
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                            response_format={"type": "json_object"},
                            max_tokens=self.max_tokens,
                        )
                    except LLMError:
                        raise
                    except Exception:  # noqa: BLE001 - providers may reject JSON mode with different errors
                        self._consume_call()
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=messages,
                            max_tokens=self.max_tokens,
                        )
                except Exception as exc:
                    last_debug = repr(exc)
                    if attempt < self.retry_attempts and _is_retryable_error(exc):
                        time.sleep(self.retry_base_delay * attempt)
                        continue
                    raise LLMError(f"LLM request failed: {exc}") from exc

                choices = getattr(response, "choices", None)
                if choices:
                    content = choices[0].message.content
                    if content:
                        return content
                    last_debug = _safe_response_debug(response)
                else:
                    last_debug = _safe_response_debug(response)

                if _should_try_responses_api(response):
                    return self._raw_responses_response(system, user)

                if attempt < self.retry_attempts and _is_retryable_response(response):
                    time.sleep(self.retry_base_delay * attempt)
                    continue

                break

            raise LLMError(
                "Model khong tra ve choices/content sau khi retry. "
                "Day thuong la loi tam thoi tu provider/model nhu 502/504/524. "
                f"Response cuoi: {last_debug}"
            )

        return self._raw_responses_response(system, user)

    def _raw_responses_response(self, system: str, user: str) -> str:
        try:
            self._consume_call()
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                text={"format": {"type": "json_object"}},
                max_output_tokens=self.max_tokens,
            )
        except Exception as exc:
            raise LLMError(f"Responses API request failed: {exc}") from exc
        content = response.output_text or ""
        if content.strip():
            return content

        if self.base_url:
            return self._raw_chat_response(system, user)

        debug = _safe_response_debug(response)
        raise LLMError(f"Responses API tra ve noi dung rong. Response: {debug}")

    def _raw_chat_response(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            try:
                self._consume_call()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    max_tokens=self.max_tokens,
                )
            except LLMError:
                raise
            except Exception:  # noqa: BLE001 - providers may reject JSON mode with different errors
                self._consume_call()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                )
        except Exception as exc:
            raise LLMError(f"Chat completions request failed: {exc}") from exc
        choices = getattr(response, "choices", None)
        if choices and choices[0].message.content:
            return choices[0].message.content
        raise LLMError(f"Chat completions API tra ve noi dung rong. Response: {_safe_response_debug(response)}")


def _safe_response_debug(response: Any) -> str:
    if hasattr(response, "model_dump_json"):
        try:
            return response.model_dump_json(indent=2)[:2000]
        except Exception:  # noqa: BLE001 - debug rendering must never hide the request error
            return repr(response)[:2000]
    return repr(response)[:2000]


def _is_retryable_response(response: Any) -> bool:
    error = getattr(response, "error", None)
    if isinstance(error, dict):
        code = str(error.get("code", ""))
        message = str(error.get("message", ""))
    else:
        code = str(getattr(error, "code", ""))
        message = str(getattr(error, "message", ""))

    retry_markers = ["502", "503", "504", "524", "timeout", "timed out", "resourceexhausted"]
    text = f"{code} {message}".lower()
    return any(marker in text for marker in retry_markers)


def _should_try_responses_api(response: Any) -> bool:
    error = getattr(response, "error", None)
    if isinstance(error, dict):
        code = str(error.get("code", ""))
        message = str(error.get("message", ""))
    else:
        code = str(getattr(error, "code", ""))
        message = str(getattr(error, "message", ""))
    text = f"{code} {message}".lower()
    return "404" in text and "provider returned error" in text


def _is_retryable_error(error: Exception) -> bool:
    text = repr(error).lower()
    retry_markers = ["502", "503", "504", "524", "timeout", "timed out", "resourceexhausted"]
    return any(marker in text for marker in retry_markers)


def parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
        else:
            raise
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected a JSON object", cleaned, 0)
    return parsed


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is int:
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _compact_draft_for_semantic(draft: ContractDraft) -> dict[str, Any]:
    return {
        "original_prompt": _compact_text(draft.original_prompt, 1500),
        "intent": draft.intent,
        "parties": [party.to_dict() for party in draft.parties],
        "amount": draft.amount,
        "token": draft.token,
        "deposit_timeout": draft.deposit_timeout,
        "decision_timeout": draft.decision_timeout,
        "clauses": draft.clauses[:12],
        "assumptions": draft.assumptions[:12],
        "clarification_questions": draft.clarification_questions[:8],
        "reasoning_summary": _compact_text(draft.reasoning_summary, 800),
        "contract_plan": draft.contract_plan,
        "marlowe_contract": _compact_contract(draft.marlowe_contract),
    }


def _compact_contract(contract: Any) -> Any:
    text = json.dumps(contract, ensure_ascii=False)
    if len(text) <= 12000:
        return contract
    return {
        "_truncated": True,
        "root": next(iter(contract), None) if isinstance(contract, dict) else contract,
        "preview": text[:12000],
    }


def _compact_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def load_env_file() -> Path | None:
    for env_path in env_search_paths():
        if env_path.exists():
            _load_one_env_file(env_path)
            return env_path
    return None


def env_search_paths() -> list[Path]:
    project_root = Path(__file__).resolve().parents[1]
    candidates = [Path.cwd() / ".env", project_root / ".env"]
    unique: list[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def _load_one_env_file(env_path: Path) -> None:
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
