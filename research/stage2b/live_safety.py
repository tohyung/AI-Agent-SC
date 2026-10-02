"""Preflight controls shared by research-only live experiments."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from urllib.parse import urlsplit

EXPERIMENT_VERSION = "live-stage2b-corridor-v1"
STAGE2A_AGGREGATE_SHA256 = "897249e3d355121e7cf8304e8b336dc0a4118515b4bf847f7fb8b8efad587a46"


@dataclass(frozen=True)
class LiveBudget:
    requested_calls: int
    hard_cap: int
    max_spend_usd: Decimal
    per_request_cost_ceiling_usd: Decimal
    money_limited_calls: int
    effective_calls: int

    def to_dict(self) -> dict:
        return {
            "requested_physical_calls": self.requested_calls,
            "hard_physical_call_cap": self.hard_cap,
            "max_spend_usd": str(self.max_spend_usd),
            "per_request_cost_ceiling_usd": str(self.per_request_cost_ceiling_usd),
            "money_limited_calls": self.money_limited_calls,
            "effective_physical_calls": self.effective_calls,
            "maximum_declared_spend_usd": str(
                self.effective_calls * self.per_request_cost_ceiling_usd),
        }


def make_live_budget(requested: int, hard_cap: int, maximum: str, ceiling: str) -> LiveBudget:
    if requested < 1 or requested > hard_cap:
        raise ValueError(f"physical-call limit must be between 1 and {hard_cap}")
    try:
        max_spend = Decimal(maximum)
        per_request = Decimal(ceiling)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("USD limits must be Decimal-compatible") from exc
    if not max_spend.is_finite() or not per_request.is_finite() or max_spend <= 0 or per_request <= 0:
        raise ValueError("USD limits must be finite and positive")
    money_calls = int((max_spend / per_request).to_integral_value(rounding=ROUND_FLOOR))
    effective = min(requested, hard_cap, money_calls)
    if effective < 1:
        raise ValueError("monetary budget allows zero physical calls")
    return LiveBudget(requested, hard_cap, max_spend, per_request, money_calls, effective)


def safe_transport_metadata(reasoner) -> dict:
    base_url = getattr(reasoner, "base_url", None)
    return {"api_style": getattr(reasoner, "api_style", None),
            "provider_host": urlsplit(base_url).hostname if isinstance(base_url, str) else None,
            "timeout_seconds": getattr(reasoner, "timeout_seconds", None),
            "max_tokens": getattr(reasoner, "max_tokens", None),
            "retry_attempts": getattr(reasoner, "retry_attempts", None)}
