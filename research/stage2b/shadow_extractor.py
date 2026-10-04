"""Prompt, transport, parsing, and validation for shadow intent extraction."""

from __future__ import annotations

import json
from datetime import date, datetime
import re
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
   payment transition. Use global only for genuinely branch-independent facts.
   A single asset spanning every monetary obligation may be global; when
   obligations use different assets or amounts, scope each fact to its own
   funding event or outcome. Distinct obligations are not a conflict merely
   because their values differ. Reward points are not automatically an
   on-chain token: ask for token identity or a conversion mechanism if
   executable behavior depends on that distinction.
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
   A scheduled release at fixed times is not a user Choice: represent its
   payment events and their deadlines without inventing a chooser or numeric
   choice bounds. Choice is reserved for an explicit business decision by an
   identified actor. Marlowe timeout paths need a transaction to advance;
   do not claim the ledger autonomously submits that transaction. This ordinary
   runtime limitation is not an unrepresented contract behavior. Do not create
   Notify(True) as a placeholder for a time-based payment: that would allow
   the payment before its scheduled time. A staged payment outcome that leads
   to a later payment must name that next transition via continuation_scope_id.
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
        + "\nDeterministic calendar hints from that history (date-only values do not "
          "establish a timezone):\n"
        + json.dumps(_calendar_hints(requirement_history), ensure_ascii=False)
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
            "from names such as approve/reject. If that outcome is followed by "
            "another event, include continuation_scope_id to its next transition. "
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


def _calendar_hints(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for revision in history:
        if not isinstance(revision, dict):
            continue
        for index, message in enumerate(revision.get("messages", [])):
            if not isinstance(message, str):
                continue
            for span in re.findall(r"(?<!\d)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z(?!\d)",
                                   message):
                try:
                    instant = datetime.fromisoformat(span.replace("Z", "+00:00"))
                except ValueError:
                    continue
                hints.append({"requirement_version": revision.get("version"),
                              "message_index": index, "source_span": span,
                              "exact_utc_milliseconds": int(instant.timestamp() * 1000)})
            for day, month, year in re.findall(
                    r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", message):
                try:
                    calendar_date = date(int(year), int(month), int(day))
                except ValueError:
                    continue
                hints.append({"requirement_version": revision.get("version"),
                              "message_index": index,
                              "source_span": f"{day}/{month}/{year}",
                              "calendar_date": calendar_date.isoformat(),
                              "timezone_unresolved": True})
    return hints


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
        guidance = _repair_guidance(core.to_dict(), initial_errors)
        feedback = (
            "The previous semantic core failed deterministic validation. "
            "Regenerate the complete seven-field core from the original requirement only. "
            "Do not infer new facts, omit financial claims, or change the resolution "
            "merely to satisfy validation. Fix only errors justified by the original text. "
            "Keep source spans verbatim; never use ellipses. If derived_from points "
            "to a different claim kind, omit derived_from unless a valid same-kind "
            "source exists. Return JSON only.\nValidation errors:\n"
            + json.dumps(initial_errors, ensure_ascii=False)
            + "\nTyped diagnostics (diagnosis only; regenerate from source):\n"
            + json.dumps(guidance, ensure_ascii=False)
            + "\nPrevious core:\n"
            + json.dumps(core.to_dict(), ensure_ascii=False)
        )
        return parse_model_output(self.model.generate(system, user + "\n" + feedback)), initial_errors


def _repair_guidance(core: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    """Explain validator failures without changing or authorizing model output."""
    scopes = {
        scope["scope_id"]: scope for scope in core.get("behavior_scopes", [])
        if isinstance(scope, dict) and isinstance(scope.get("scope_id"), str)
    } if isinstance(core.get("behavior_scopes"), list) else {}
    guidance: list[dict[str, Any]] = []
    for error in errors:
        if error.startswith("scope ") and error.endswith(": invalid continuation_scope_id"):
            source_id = error[len("scope "):-len(": invalid continuation_scope_id")]
            source = scopes.get(source_id, {})
            target_id = source.get("continuation_scope_id")
            target = scopes.get(target_id, {}) if isinstance(target_id, str) else {}
            guidance.append({
                "error": error,
                "source_scope_type": source.get("scope_type"),
                "source_transition_kind": source.get("transition_kind"),
                "target_scope_id": target_id,
                "target_scope_type": target.get("scope_type"),
                "rule": ("A continuation is a causal successor, never a branch or timeout "
                         "alternative. If no successor exists, omit this optional field; "
                         "retain branch decision_id, timeout decision_id, and path-specific "
                         "continuations. Otherwise reference an existing transition or "
                         "terminal_outcome. Do not invent a transition to silence this error."),
            })
        elif "conflicting values for " in error or "active claim conflict" in error:
            guidance.append({
                "error": error,
                "rule": ("Check whether the values describe independent obligations. "
                         "If so, attach each claim to its actual funding or outcome scope; "
                         "if they are incompatible values for the same obligation, preserve "
                         "the conflict and request clarification. Do not delete a supported claim."),
            })
        elif "invalid evidence target/span" in error or "supporting evidence required" in error:
            guidance.append({
                "error": error,
                "rule": ("Copy an exact contiguous substring from a supplied requirement "
                         "message that states this fact and role. If none exists, mark the "
                         "fact unresolved rather than fabricate source evidence."),
            })
        elif "unresolved value must be null" in error:
            guidance.append({
                "error": error,
                "rule": ("An unresolved claim must have value=null. If the proposed "
                         "non-null value is established by an exact source span, use the "
                         "appropriate supported status and evidence instead. Never keep "
                         "a known value marked unresolved merely to justify a question."),
            })
        elif "deadline value contradicts cited calendar date" in error:
            guidance.append({
                "error": error,
                "rule": ("Recompute POSIX milliseconds from the cited source date and "
                         "an explicit timezone assumption. Preserve the date in the "
                         "requirement; do not shift its year to make the integer fit. "
                         "Relative deadlines must use the corrected absolute anchor."),
            })
        elif error.startswith("clarification prediction requires an unresolved claim"):
            guidance.append({
                "error": error,
                "rule": ("Do not ask for optional implementation details or facts already "
                         "established by the requirement. If a critical business fact is "
                         "genuinely missing, represent that specific claim as unresolved "
                         "and ask only about it. If an essential behavior is outside the "
                         "taxonomy, record a source-grounded unrepresented behavior "
                         "observation. Otherwise choose the supported resolution without "
                         "inventing an ambiguity."),
            })
    return guidance


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
