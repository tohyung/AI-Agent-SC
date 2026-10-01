"""Prompt, transport, parsing, and validation for shadow intent extraction."""

from __future__ import annotations

import json
from typing import Any, Protocol

from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION, ShadowSemanticCore, core_prompt_schema_contract,
)


class ShadowModel(Protocol):
    def generate(self, system: str, user: str) -> dict[str, Any]: ...


class InvalidModelOutput(ValueError):
    """The model returned a JSON value other than a semantic core object."""


SYSTEM_PROMPT = """Extract user intent only as one JSON ShadowSemanticCore object.
Do NOT generate Marlowe AST, compile, or invent missing business facts.
Output only the seven semantic core fields. Python deterministically projects
all rich sections. Never output participants, accounts, parameters, states,
transitions, outcomes, conflicts, or assumptions objects.
Preserve requirement chronology and explicit corrections. Every financial claim
must have exact source provenance; deterministic financial derivations need
exact source evidence and a normalization basis. `derived_from` is optional;
never point an amount to `asset=ADA` as if the asset claim proved quantity.
An assumption is not evidence. Use only the supplied
claim taxonomy. If a fact is outside it, record a non-authoritative
unscored_observation, never a new claim kind.
Use stable case-local business scope IDs such as global, deposit-1,
decision-1:approve, and notify-1:timeout. Every scope must include its valid
scope_type and required fields from the schema contract. Do not use AST paths.
Distinguish choice_owner, depositing_party,
destination_account_owner, payment_source_account_owner, payment_recipient,
refund_recipient, release_recipient, and transaction_submitter. Never infer
transaction_submitter from Choice owner or Deposit party. There is no
authoritative submitter claim kind. Never invent a
funding source, account owner, transition actor, payout source, or success state.
Preserve party and asset spelling and case exactly: Alice != alice; ADA != ada.
1 ADA = 1000000 lovelace; amount_lovelace is integer lovelace and POSIX
deadlines are integer milliseconds. Never guess unknown business entities.
For missing critical finance facts use value=null and status=unresolved, then
ask a concrete Vietnamese business question, not an AST/JSON question.
Do not infer payment source from the party depositing. Preserve Notify as
Notify: missing Observation semantics requires clarification, not an invented
Choice owner. Two conflicting active values of the same kind/scope require
both claims marked conflicted and conflict_requires_resolution; do not
downgrade conflicts to generic ambiguity. Conflicts require user resolution;
unsupported autonomous execution is unsupported, not merely ambiguous.
Return JSON only, with all top-level fields shown in the user instruction.
"""


def build_prompt(requirement_history: list[dict[str, Any]]) -> tuple[str, str]:
    template = {
        "schema_version": CORE_SCHEMA_VERSION,
        "requirement_history": requirement_history,
        "behavior_scopes": [], "claims": [],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "clarification_required",
    }
    user = (
        "Requirement history is the only source of user intent:\n"
        + json.dumps(requirement_history, ensure_ascii=False)
        + "\nValidator schema contract (closed enum/field vocabulary):\n"
        + json.dumps(core_prompt_schema_contract(), ensure_ascii=False, sort_keys=True)
        + "\nOutput all fields in this JSON shape (replace example values):\n"
        + json.dumps(template, ensure_ascii=False)
        + "\nEvery claim uses claim_id, kind, value, criticality, status, scope_id, "
          "evidence. Evidence items use requirement_version (integer), "
          "message_index (integer), span (exact substring of source message), "
          "relation (supports or contradicts). Explicit, user_confirmed, "
          "conflicted, superseded and derived claims require exact supporting "
          "evidence. Unresolved claims use value=null and may use evidence=[]. "
          "Assumed claims require assumption_reason and should use evidence=[]; "
          "never fabricate a source span. Derived financial claims require "
          "normalization_basis; derived_from is optional and must prove the "
          "same kind of fact. Do not link amount_lovelace to asset evidence "
          "as proof of quantity. Global scope uses scope_id=global and "
          "scope_type=global. A transition scope needs transition_kind; a "
          "branch needs decision_id and branch_id; a timeout needs timeout_id "
          "and may reference decision_id/deadline_claim_id. Every "
          "behavior_scopes.scope_id must be unique: do not reuse an ID for "
          "two scope objects. Every decision_id must equal the scope_id of an "
          "existing scope_type=transition object. Do not create a branch/timeout "
          "reference before creating its referenced transition scope. If present, "
          "deadline_claim_id must refer to an existing claim whose kind is in "
          "deadline_kinds. A terminal_outcome scope needs outcome_id. Each "
          "unscored_observations item must be an object "
          "with observation_id, text, reason, and source_evidence as specified "
          "in the schema contract, never a plain string. Use a nonempty stable "
          "local observation_id and nonempty source-grounded text. Its source_evidence "
          "must be nonempty with exact source spans. Authoritative financial "
          "facts must go in claims, not unscored_observations."
    )
    return SYSTEM_PROMPT, user


def parse_model_output(data: Any) -> ShadowSemanticCore:
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise InvalidModelOutput("shadow model must return a JSON object")
    return ShadowSemanticCore(data)


class IntentShadowExtractor:
    def __init__(self, model: ShadowModel) -> None:
        self.model = model

    def extract(self, requirement_history: list[dict[str, Any]]) -> ShadowSemanticCore:
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
