"""Safe, non-verbatim classifications for model transport failures."""

from __future__ import annotations

import json

from research.integrations.model_transport import ModelTransportError
from research.stage2b.shadow_extractor import InvalidModelOutput


def sanitized_model_error(exc: Exception) -> dict:
    if (isinstance(exc, ModelTransportError) and exc.phase == "budget"
            or type(exc).__name__ == "LLMBudgetError"):
        return {"code": "physical_call_budget_exhausted", "phase": "budget",
                "message": "Physical model-call budget exhausted.",
                "model_content_received": None, "repair_attempted": None,
                "exception_type": type(exc).__name__}
    if isinstance(exc, ModelTransportError) or (
            hasattr(exc, "code") and hasattr(exc, "phase")
            and hasattr(exc, "model_content_received")):
        messages = {
            "transport_response_decode_error": "Provider response could not be decoded.",
            "model_output_invalid_after_repair": "Model output remained invalid JSON after repair.",
            "invalid_json_after_repair": "Model output remained invalid JSON after repair.",
        }
        return {"code": exc.code, "phase": exc.phase,
                "message": messages.get(exc.code, "Model request failed."),
                "model_content_received": exc.model_content_received,
                "repair_attempted": exc.repair_attempted,
                "exception_type": type(exc).__name__}
    if isinstance(exc, json.JSONDecodeError):
        code, phase, message, content, repair = (
            "model_output_invalid_json", "model_output_parse", "Model output was invalid JSON.", True, False)
    elif isinstance(exc, InvalidModelOutput):
        code, phase, message, content, repair = (
            "invalid_model_output", "model_output_schema", "Model returned a non-object value.", True, False)
    elif isinstance(exc, TimeoutError):
        code, phase, message, content, repair = (
            "provider_timeout", "transport_request", "Model request timed out.", False, False)
    else:
        code, phase, message, content, repair = (
            "provider_error", "unknown", "Model request failed.", None, None)
    return {"code": code, "phase": phase, "message": message,
            "model_content_received": content, "repair_attempted": repair,
            "exception_type": type(exc).__name__}
