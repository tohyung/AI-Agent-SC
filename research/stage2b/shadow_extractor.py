"""Prompt, transport, parsing, and validation for shadow intent extraction."""

from __future__ import annotations

import json
from typing import Any, Protocol

from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2, ShadowSemanticCore,
    core_prompt_schema_contract,
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
   When one branch has multiple monetary obligations (for example, one party
   retains a fee and another receives the remainder), give each obligation a
   distinct terminal_outcome scope and attach its amount and recipient there.
   Distinct amounts for distinct recipients in one branch are not a conflict.
   Do not merge them into one branch-level amount or invent an extra payment.
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


def build_prompt(requirement_history: list[dict[str, Any]], *,
                 core_schema_version: str = CORE_SCHEMA_VERSION) -> tuple[str, str]:
    if core_schema_version not in {CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2}:
        raise ValueError("unsupported core schema version")
    template = {
        "schema_version": core_schema_version,
        "requirement_history": requirement_history,
        "behavior_scopes": [], "claims": [],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "clarification_required",
    }
    user = (
        "Requirement history is the only source of user intent:\n"
        + json.dumps(requirement_history, ensure_ascii=False)
        + "\nValidator schema contract (closed enum/field vocabulary):\n"
        + json.dumps(core_prompt_schema_contract(version=core_schema_version),
                     ensure_ascii=False, sort_keys=True)
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
    system = SYSTEM_PROMPT
    if core_schema_version == CORE_SCHEMA_VERSION_V2:
        system += (
            "\nFor each numeric Choice, include inclusive choice_bounds with exact source "
            "evidence on its transition scope. Every branch of that Choice needs a "
            "choice_guard with operator and integer threshold plus exact source evidence. "
            "Preserve ranges and conditions such as price >= 50; do not convert them "
            "into unscored text or omit them. If a contract-defining condition is "
            "missing, ask a concrete business question rather than inventing it. "
            "Each terminal_outcome must include parent_scope_id pointing to its "
            "actual branch, timeout, or transition scope; never infer this link "
            "from names such as approve/reject. "
            "When one event leads to another, include continuation_scope_id on "
            "the predecessor scope to name the next transition or outcome. "
            "For example a funded deposit may continue to a Choice; array order "
            "alone never encodes control flow. A Choice transition does not "
            "continue to its timeout scope: branch and timeout scopes are "
            "alternative paths of that same Choice. Give each branch and its "
            "timeout its own continuation to the first outcome on that path. "
            "Never use continuation_scope_id to point at a timeout or branch. "
            "Use unscored_observations reason=irrelevant_context only for source "
            "details that cannot affect contract behavior (for example, weather or "
            "biography). Any unrepresented contract behavior must use "
            "outside_stage2b_v2_claim_taxonomy and remain non-compilable.\n"
        )
    return system, user


def parse_model_output(data: Any) -> ShadowSemanticCore:
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise InvalidModelOutput("shadow model must return a JSON object")
    return ShadowSemanticCore(data)


class IntentShadowExtractor:
    def __init__(self, model: ShadowModel, *,
                 core_schema_version: str = CORE_SCHEMA_VERSION) -> None:
        self.model = model
        self.core_schema_version = core_schema_version

    def extract(self, requirement_history: list[dict[str, Any]]) -> ShadowSemanticCore:
        system, user = build_prompt(requirement_history,
                                    core_schema_version=self.core_schema_version)
        return parse_model_output(self.model.generate(system, user))

    def extract_with_validation_feedback(
        self, requirement_history: list[dict[str, Any]], *, max_repairs: int = 1
    ) -> tuple[ShadowSemanticCore, list[str]]:
        if max_repairs not in (0, 1):
            raise ValueError("max_repairs must be 0 or 1")
        system, user = build_prompt(requirement_history,
                                    core_schema_version=self.core_schema_version)
        core = parse_model_output(self.model.generate(system, user))
        initial_errors = core.validation_errors(expected_history=requirement_history)
        if not initial_errors or max_repairs == 0:
            return core, initial_errors
        feedback = (
            "The previous semantic core failed deterministic validation. "
            "Regenerate the complete seven-field core from the original requirement only. "
            "Do not infer new facts, omit financial claims, or change the resolution "
            "merely to satisfy validation. Fix only errors justified by the original text. "
            "Keep source spans verbatim; never use ellipses. If derived_from points "
            "to a different claim kind, omit derived_from unless a valid same-kind "
            "source exists. Return JSON only.\nValidation errors:\n"
            + json.dumps(initial_errors, ensure_ascii=False)
            + "\nPrevious core:\n"
            + json.dumps(core.to_dict(), ensure_ascii=False)
        )
        return parse_model_output(self.model.generate(system, user + "\n" + feedback)), initial_errors


class LegacyReasonerTransport:
    """Research-only JSON transport; this does not grant production authority."""

    def __init__(self, model: str | None = None) -> None:
        from marlowe_ai_agent.marlowe_agent.openai_reasoner import OpenAIReasoner

        self.reasoner = OpenAIReasoner(model=model)

    def generate(self, system: str, user: str) -> dict[str, Any]:
        return self.reasoner._json_response(system, user)

    def usage(self) -> dict[str, Any]:
        return self.reasoner.usage_summary()

    def request_count(self) -> int:
        return len(self.reasoner.call_log)

    def usage_window(self, start_index: int, end_index: int | None = None) -> dict[str, Any]:
        from marlowe_ai_agent.marlowe_agent.openai_reasoner import summarize_call_log

        return summarize_call_log(self.reasoner.call_log[start_index:end_index])
