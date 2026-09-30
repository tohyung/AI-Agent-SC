"""Prompt, transport, parsing, and validation for shadow intent extraction."""

from __future__ import annotations

import json
from typing import Any, Protocol

from research.stage2a.foundation import CLAIM_KINDS
from research.stage2b.intent_spec import IntentSpec, SCHEMA_VERSION


class ShadowModel(Protocol):
    def generate(self, system: str, user: str) -> dict[str, Any]: ...


SYSTEM_PROMPT = """Extract user intent only as one JSON IntentSpec object.
Do NOT generate Marlowe AST, compile, or invent missing business facts.
Preserve requirement chronology and explicit corrections. Every financial claim
must have exact source provenance; deterministic financial derivations need
exact source evidence and a normalization basis. `derived_from` is optional;
never point an amount to `asset=ADA` as if the asset claim proved quantity.
An assumption is not evidence. Use only the supplied
claim taxonomy. If a fact is outside it, record a non-authoritative
unscored_observation, never an authoritative rich field.
Use case-local business scopes: global, deposit-1, payout-1, decision-1,
decision-1:approve, decision-1:reject, decision-1:timeout, notify-1,
notify-1:success, notify-1:timeout, or another stable local ID where needed.
Every authoritative participant/account/parameter/transition/outcome fact must
reference matching claim IDs. Distinguish choice_owner, depositing_party,
destination_account_owner, payment_source_account_owner, payment_recipient,
refund_recipient, release_recipient, and transaction_submitter. Never infer
transaction_submitter from Choice owner or Deposit party. If unknown, leave it
null or ask a business clarification. Do not invent a new claim kind for it.
For missing critical finance facts ask a concrete business question, not an
AST, JSON, field, or constructor question. Conflicts require user resolution;
unsupported autonomous execution is unsupported, not merely ambiguous.
Return JSON only, with all top-level fields shown in the user instruction.
"""


def build_prompt(requirement_history: list[dict[str, Any]]) -> tuple[str, str]:
    template = {
        "schema_version": SCHEMA_VERSION,
        "requirement_history": requirement_history,
        "participants": [],
        "assets_and_accounts": {"assets": [], "accounts": [], "funding_relations": []},
        "parameters": [], "states": [], "transitions": [],
        "obligations_and_outcomes": [], "behavior_scopes": [], "claims": [],
        "required_clarifications": [], "conflicts": [],
        "assumptions_and_provenance": [], "unscored_observations": [],
        "predicted_resolution": "clarification_required",
    }
    user = (
        "Requirement history is the only source of user intent:\n"
        + json.dumps(requirement_history, ensure_ascii=False)
        + "\nAllowed claim kinds: " + ", ".join(sorted(CLAIM_KINDS))
        + "\nOutput all fields in this JSON shape (replace example values):\n"
        + json.dumps(template, ensure_ascii=False)
        + "\nClaim fields: claim_id, kind, value, criticality, status, scope_id, "
          "evidence; financial derived claims need normalization_basis, while "
          "derived_from is optional and must prove the same kind of fact; "
          "assumed claims need assumption_reason. "
          "Evidence items use requirement_version, message_index, exact span, "
          "and relation. Use value=null for unresolved facts."
    )
    return SYSTEM_PROMPT, user


def parse_model_output(data: Any) -> IntentSpec:
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError("shadow model must return a JSON object")
    return IntentSpec(data)


class IntentShadowExtractor:
    def __init__(self, model: ShadowModel) -> None:
        self.model = model

    def extract(self, requirement_history: list[dict[str, Any]]) -> IntentSpec:
        system, user = build_prompt(requirement_history)
        return parse_model_output(self.model.generate(system, user))


class LegacyReasonerTransport:
    """Research-only JSON transport; this does not grant production authority."""

    def __init__(self, model: str | None = None) -> None:
        from marlowe_ai_agent.marlowe_agent.openai_reasoner import OpenAIReasoner

        self.reasoner = OpenAIReasoner(model=model)

    def generate(self, system: str, user: str) -> dict[str, Any]:
        return self.reasoner._json_response(system, user)

    def usage(self) -> dict[str, Any]:
        return self.reasoner.usage_summary()
