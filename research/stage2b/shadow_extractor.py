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
Follow this semantic order before selecting a resolution:
1. Read requirement history in order. A later explicit correction supersedes
   the earlier value; only simultaneously active incompatible values of the
   same kind and business scope form a conflict.
2. Identify the actual business event and outcome scopes. Use stable case-local
   IDs such as global, deposit-1, decision-1:approve, notify-1:timeout; include
   valid scope_type and required fields from the schema contract. Do not use
   AST paths. Put deposit roles/deadlines on the deposit event, Choice roles
   and deadlines on the Choice event, and outcome recipients on their actual
   Choice/Notify branch or timeout. Do not detach an outcome into an invented
   payment transition. Use global only for genuinely branch-independent facts,
   including a directly named asset spanning the monetary obligation.
3. Emit a minimal set of atomic claims: only facts stated by an active
   requirement, confirmed by correction, or supported by allowed deterministic
   derivation. A source span must express the claimed role/action relation;
   a party name alone does not prove who deposits, chooses, owns an account,
   or receives funds. An assumption is not evidence. Use only the supplied
   claim taxonomy; facts outside it may be non-authoritative
   unscored_observations, never new claim kinds. Preserve party/asset spelling
   and case exactly. Convert 1 ADA to 1000000 integer lovelace and POSIX times
   to integer milliseconds. A converted amount_lovelace is status=derived with
   exact source evidence and normalization_basis, not status=explicit merely
   because the source states an ADA amount. A directly named asset may remain
   explicit. `derived_from` is optional and must prove the same kind of fact;
   asset=ADA does not prove an amount.
4. Keep distinct depositing_party, choice_owner, destination_account_owner,
   payment_source_account_owner, payment_recipient, refund_recipient, and
   release_recipient. A depositor does not establish a deposit account owner
   or payment source; a payment recipient does not establish either account
   owner. Never invent a funding source, actor, recipient, or success state.
   Preserve Notify as Notify: if its Observation condition is undefined, ask
   what makes it true, not who owns a Choice. transaction_submitter is not an
   authoritative claim kind and must not be inferred from a Choice owner or
   depositor.
5. For genuinely missing critical business facts use value=null and
   status=unresolved. Ask only concrete, nonduplicate Vietnamese business
   questions that resolve those missing or conflicting facts. Ask which
   competing value governs a conflict. Do not ask for already stated facts,
   extra deadlines/recipients for paths not requested, AST/JSON details, or
   a transaction_submitter unless the requirement explicitly makes submitter
   identity business-relevant and the taxonomy can represent the issue.
   Keep schema field names out of user-facing question text.
6. Choose predicted_resolution last: unsupported_for_current_study only for a
   valid versioned unsupported signal; otherwise conflict_requires_resolution
   for active same-kind/same-scope conflict; otherwise clarification_required
   for remaining critical unresolved facts; otherwise accepted_interpretation.
   Unsupported autonomous execution is unsupported, not generic ambiguity.
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
