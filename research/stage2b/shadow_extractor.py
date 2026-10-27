"""Prompt, transport, parsing, and validation for shadow intent extraction."""

from __future__ import annotations

from copy import deepcopy
import json
from datetime import date
import re
from typing import Any, Protocol

from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3,
    CORE_SCHEMA_VERSION_V4,
    ShadowSemanticCore,
    UNSCORED_OBSERVATION_FIELDS,
    _evidence_valid,
    core_prompt_schema_contract,
    explicit_utc_instants,
)
from research.stage2b.core_draft import (DRAFT_FIELDS, collapse_automatic_success_branches,
                                         connect_skipped_terminal_outcomes,
                                         drop_dangling_amount_derivations,
                                         drop_decision_to_own_branch_or_timeout,
                                         derive_unambiguous_token_assets,
                                         materialize_core_draft,
                                         drop_explicitly_absent_refund_recipient,
                                         drop_resolved_time_format_questions,
                                         normalize_clarification_question_aliases,
                                         normalize_choice_metadata,
                                         normalize_explicit_deadline_instants,
                                         normalize_grounded_numeric_amounts,
                                         normalize_actor_scoped_deadlines,
                                         normalize_dot_native_asset_ids,
                                         normalize_vietnamese_noon_deadlines,
                                         prune_unverifiable_evidence,
                                         prune_unreachable_duplicate_outcomes,
                                         retarget_unique_evidence_spans)
from research.stage2b.repair_policy import (
    REPAIR_POLICY_VERSION, diagnostic_codes, repair_progress,
)


class ShadowModel(Protocol):
    def generate(self, system: str, user: str) -> dict[str, Any]: ...


class InvalidModelOutput(ValueError):
    """The model returned a JSON value other than a semantic core object."""


def _repair_system(prompt: str) -> str:
    return f"Repair policy {REPAIR_POLICY_VERSION}.\n{prompt}"


SYSTEM_PROMPT = """Extract user intent only as one JSON ShadowSemanticCore object.
Do NOT generate Marlowe AST, compile, or invent missing business facts.
Output only the seven semantic core fields. Python deterministically projects
all rich sections. Never output participants, accounts, parameters, states,
transitions, outcomes, conflicts, or assumptions objects.
Follow this semantic order before selecting a resolution:
1. Read requirement history in order. A later explicit correction supersedes
   the earlier value; only simultaneously active incompatible values of the
   same kind and business scope form a conflict. A later explicit absolute
   deadline also resolves an earlier relative-date uncertainty for the same
   event; do not retain that old uncertainty as unscored contract behavior.
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
   to integer milliseconds. A date-only phrase does not establish a timezone
   or an exact POSIX instant: keep its deadline claim unresolved with value=null
   and ask a business-friendly question about the cutoff/timezone unless a
   later requirement supplies that exact instant. Never use a calendar hint
   to guess milliseconds or shift the cited year. Ask the user for a local
   calendar date, clock time and timezone; never ask them to calculate POSIX
   milliseconds, inspect an AST, or choose a timestamp encoding. Normalize
   the answer yourself once those facts are known. A converted amount_lovelace
   is status=derived with
   exact source evidence and normalization_basis, not status=explicit merely
   because the source states an ADA amount. Do not emit the raw ADA numeral
   as a second amount_lovelace claim: 20 ADA supports one normalized value
   20000000 lovelace, not both 20 and 20000000 lovelace in the same scope.
   Never duplicate that same normalized amount with different statuses in
   one scope; choose the one source-grounded claim and its correct status.
   A directly named asset may remain
   explicit. `derived_from` is optional and must prove the same kind of fact;
   asset=ADA does not prove an amount. `derived_from` is one claim_id string,
   never an array. Omit it entirely when there is no valid same-kind source
   claim; never emit `derived_from=[]`.
4. Keep distinct depositing_party, choice_owner, destination_account_owner,
   payment_source_account_owner, payment_recipient, refund_recipient, and
   release_recipient. A depositor does not establish a deposit account owner
   or payment source; a payment recipient does not establish either account
   owner. Never invent a funding source, actor, recipient, or success state.
   Copy named parties and account owners exactly from source evidence,
   preserving Unicode accents and case. Marlowe role names are identifiers;
   do not transliterate or silently substitute an ASCII spelling.
   A deposit into a Marlowe account is not a transfer to the borrower. If the
   source says a lender funds a loan and the contract disburses it to a
   borrower before repayment, represent the disbursement as a distinct Pay
   outcome between the funding Deposit and repayment Deposit. Do not label
   the borrower as destination_account_owner merely because they receive the
   disbursement; that claim needs source evidence for account ownership.
   When the source specifies the amount of a payout or refund, put one
   source-grounded amount_lovelace claim on EACH corresponding terminal
   outcome. Every terminal outcome with a positive payout amount also needs
   an active, source-grounded payment_recipient, refund_recipient, or
   release_recipient claim on that same scope. If the recipient is unknown,
   ask the user instead of omitting the claim or guessing the payee.
   A global amount or funding Deposit amount does not by itself
   state the amount paid on each branch; preserve distinct branch outcomes.
   When a branch or timeout returns the funded amount to its original payer,
   classify that outcome's recipient as refund_recipient, even if the return
   is selected by an explicit Choice. Use payment_recipient for a transfer
   to a different payee, not as a generic label for every outgoing payment.
   Preserve Notify as Notify: if its Observation condition is undefined, ask
   what makes it true, not who owns a Choice. transaction_submitter is not an
   authoritative claim kind and must not be inferred from a Choice owner or
   depositor.
   A scheduled release at fixed times is not a user Choice: represent its
   payment events and their deadlines without inventing a chooser or numeric
   choice bounds. Choice is reserved for an explicit business decision by an
   identified actor. Marlowe timeout paths need a transaction to advance;
   do not claim the ledger autonomously submits that transaction. This ordinary
   runtime limitation is not an unrepresented contract behavior. In particular,
   an explicit statement that the contract does not submit transactions itself
   confirms ordinary ledger operation; it does not imply a missing business
   trigger, oracle, approver, or named submitter for a time-based release.
   If the funding, recipients, amounts, and deadlines are known, do not ask
   who or what activates payment at those deadlines. Do not create
   Notify(True) as a placeholder for a time-based payment: that would allow
   the payment before its scheduled time. A staged payment outcome that leads
   to a later payment must name that next transition via continuation_scope_id.
   A stated contract account owner belongs in destination_account_owner and/or
   payment_source_account_owner claims at the relevant scopes; do not restate
   that supported fact as outside-taxonomy unscored behavior.
   A source-named actor approving a stage can be represented by that actor's
   Marlowe Choice input. Do not ask the business user to choose a wallet
   signature, oracle, or multisig mechanism merely to encode that approval;
   ask only if the source requires independent external proof, multi-party
   authorization, or leaves the approving actor/outcome genuinely unknown.
5. For genuinely missing critical business facts use value=null and
   status=unresolved. Ask only concrete, nonduplicate Vietnamese business
   questions that resolve those missing or conflicting facts. Ask which
   competing value governs a conflict. Do not ask for already stated facts,
   extra deadlines/recipients for paths not requested, AST/JSON details, or
   a transaction_submitter unless the requirement explicitly makes submitter
   identity business-relevant and the taxonomy can represent the issue.
   If clarification is justified by an unrepresented behavior observation,
   ask about that exact observed condition or event and how it is established.
   Do not substitute a question about an already supported amount or an
   optional hypothetical fee for the missing behavior. The question must
   be answerable by a business user without knowing Marlowe internals.
   Keep schema field names out of user-facing question text.
6. Choose predicted_resolution last: unsupported_for_current_study only for a
   valid versioned unsupported signal; otherwise conflict_requires_resolution
   for active same-kind/same-scope conflict; otherwise clarification_required
   only for remaining critical unresolved facts or a source-grounded
   unrepresented behavior observation that needs an answer. If neither exists,
   use accepted_interpretation, not clarification_required; do not copy the
   example resolution from the output shape.
   Unsupported autonomous execution is unsupported, not generic ambiguity.
Return JSON only, with all top-level fields shown in the user instruction.
"""


def build_prompt(requirement_history: list[dict[str, Any]], *,
                 core_schema_version: str = CORE_SCHEMA_VERSION) -> tuple[str, str]:
    if core_schema_version not in {CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2,
                                   CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4}:
        raise ValueError("unsupported core schema version")
    template = {
        "schema_version": core_schema_version,
        "requirement_history": requirement_history,
        "behavior_scopes": [], "claims": [],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "clarification_required",
    }
    if core_schema_version in {CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4}:
        template = {key: value for key, value in template.items() if key in DRAFT_FIELDS}
    user = (
        "Requirement history is the only source of user intent:\n"
        + json.dumps(requirement_history, ensure_ascii=False)
        + "\nDeterministic calendar hints from that history (date-only values do not "
          "establish a timezone):\n"
        + json.dumps(_calendar_hints(requirement_history), ensure_ascii=False)
        + "\nValidator schema contract (closed enum/field vocabulary):\n"
        + json.dumps(core_prompt_schema_contract(version=core_schema_version),
                     ensure_ascii=False, sort_keys=True)
        + ("\nOutput only these five internal draft fields; the runtime binds "
           "schema_version and requirement_history from trusted input:\n"
           if core_schema_version in {CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4} else
           "\nOutput all fields in this JSON shape (replace example values):\n")
        + json.dumps(template, ensure_ascii=False)
        + "\nEvery claim uses claim_id, kind, value, criticality, status, scope_id, "
          "evidence. Evidence items use requirement_version (integer), "
          "message_index (zero-based index within that requirement_version's messages), "
          "span (exact substring of that indexed source message), "
          "relation (supports or contradicts). Explicit, user_confirmed, "
          "conflicted, superseded and derived claims require exact supporting "
          "evidence. Unresolved claims use value=null and may use evidence=[]. "
          "Assumed claims require assumption_reason and should use evidence=[]; "
          "never fabricate a source span. Derived financial claims require "
          "normalization_basis; derived_from is an optional single claim_id string "
          "that must prove the same kind of fact, never an array. Omit derived_from "
          "when no source claim qualifies; "
          "do not emit derived_from=[]. Do not link amount_lovelace to asset evidence "
          "as proof of quantity. For an explicit source amount such as 47.5 ADA, "
          "value may be that exact quoted source phrase in the internal draft; "
          "the runtime converts it to 47500000 lovelace. Never guess a unit. "
          "Global scope uses scope_id=global and "
          "scope_type=global. A transition scope needs transition_kind; a "
          "branch needs decision_id and branch_id; a timeout needs timeout_id "
          "and may reference decision_id/deadline_claim_id. Every "
          "behavior_scopes.scope_id must be unique: do not reuse an ID for "
          "two scope objects. Every decision_id must equal the scope_id of an "
          "existing scope_type=transition object. When a later user answer explicitly "
          "corrects an earlier value for the same obligation, the earlier value is "
          "superseded, not an active conflict; use the corrected value for the "
          "accepted interpretation and preserve the old fact with its provenance. "
          "Do not create a branch/timeout "
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
    if core_schema_version in {CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4}:
        system = system.replace(
            "Output only the seven semantic core fields. Python deterministically projects",
            "Output only five internal draft fields: behavior_scopes, claims, "
            "required_clarifications, unscored_observations, predicted_resolution. "
            "The runtime attaches schema_version and exact requirement_history. "
            "Python deterministically projects")
        system = system.replace(
            "Convert 1 ADA to 1000000 integer lovelace and POSIX times\n"
            "   to integer milliseconds.",
            "For amount_lovelace, deadline and payment release time claims, prefer an exact quoted source "
            "expression as value; runtime normalizes source-backed ADA units and "
            "explicit timezone instants. An already explicit lovelace or POSIX value "
            "may be an integer. Never calculate or guess an unsupported value.")
        system = system.replace(
            "Normalize\n   the answer yourself once those facts are known.",
            "The runtime normalizes source-grounded values once those facts are known.")
    if core_schema_version in {CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3,
                               CORE_SCHEMA_VERSION_V4}:
        system += (
            "\nFor each numeric Choice, include inclusive choice_bounds with exact source "
            "evidence on its transition scope. Every branch of that Choice needs a "
            "choice_guard with operator and integer threshold plus exact source evidence. "
            "For both choice_bounds and choice_guard, source_evidence is a NONEMPTY "
            "JSON ARRAY of evidence objects, never a single object. Each item has "
            "requirement_version, message_index, span, and relation. "
            "For an explicit yes/no approval by an identified actor, a single "
            "approval event may use a Choice whose sole bound is from=1,to=1 "
            "and whose approval branch has choice_guard eq 1. This is a "
            "deterministic encoding of the source-stated approval event, not "
            "a source-stated numeric threshold. Cite the exact approval phrase "
            "as evidence for both fields. Absence of approval before its "
            "deadline is the timeout path, not an invented Choice value 0 or "
            "an invented rejection branch. Do not use this convention unless "
            "the source names the approving actor and the approval outcome. "
            "Preserve ranges and conditions such as price >= 50; do not convert them "
            "into unscored text or omit them. If a contract-defining condition is "
            "missing, ask a concrete business question rather than inventing it. "
            "Each terminal_outcome must include parent_scope_id pointing to its "
            "actual branch, timeout, or transition scope; never infer this link "
            "from names such as approve/reject. parent_scope_id describes ownership "
            "but does not make the outcome reachable: the predecessor must also "
            "name this outcome in continuation_scope_id. If that outcome is followed by "
            "another event, include continuation_scope_id to its next transition. "
            "If it is the final outcome on its path, omit continuation_scope_id. "
            "A scope must never use its own scope_id as continuation_scope_id. "
            "If one path refunds two distinct contributors, use two distinct "
            "terminal_outcome scopes in sequence, one refund recipient per scope; "
            "do not put both recipients into one outcome as conflicting claims. "
            "When one event leads to another, include continuation_scope_id on "
            "the predecessor scope to name the next transition or outcome. "
            "A branch decision belongs to Choice or Notify, not Deposit or Pay; "
            "Deposit success continues directly to its next transition while its "
            "timeout remains a separate timeout scope. "
            "A single contract has one entry transition. Every later transition "
            "must have an incoming continuation_scope_id from its predecessor; "
            "two unrelated root transitions do not encode sequential events. "
            "For example a funded deposit may continue to a Choice; array order "
            "alone never encodes control flow. A Choice transition does not "
            "continue to its timeout scope: branch and timeout scopes are "
            "alternative paths of that same Choice. Give each branch and its "
            "timeout its own continuation to the first outcome on that path. "
            "Omit continuation_scope_id on the Choice transition itself; its "
            "branch and timeout alternatives are linked by decision_id. "
            "Never use continuation_scope_id to point at a timeout or branch. "
            "Use unscored_observations reason=irrelevant_context only for source "
            "details that cannot affect contract behavior (for example, weather or "
            "biography). Any unrepresented contract behavior must use "
            "outside_stage2b_v2_claim_taxonomy and remain non-compilable.\n"
        )
    if core_schema_version in {CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4}:
        system = system.replace("outside_stage2b_v2_claim_taxonomy",
                                "outside_stage2b_v3_claim_taxonomy")
        system = system.replace(
            "Unsupported autonomous execution is unsupported, not generic ambiguity.",
            "In v3, autonomous_execution alone is not unsupported. A request to "
            "delete or rewrite a confirmed on-chain transaction or its history "
            "is unsupported only when the source explicitly asks for that behavior."
        )
        system += (
            "\nFor explicit deletion or rewrite of confirmed Cardano transaction "
            "history, record a source-backed global ledger_history_deletion=true "
            "claim and choose unsupported_for_current_study. Do not reinterpret "
            "deletion as refund, reversal, or a new contract; do not ask for amount, "
            "asset, deadline, or participants that cannot make deletion possible. "
            "Do not use this signal for ordinary cancellation before a transaction "
            "is confirmed, or for a requested compensating transaction. "
            "\nFor native-token obligations, never use amount_lovelace for token quantity. "
            "Use amount_token_units as a positive integer, with a same-scope asset "
            "claim whose value is the exact source-provided canonical identifier "
            "native:<56 lowercase policy hex>/<even-length token-name hex>. "
            "Do not invent a policy ID or infer one from a display name. ADA still "
            "uses amount_lovelace and asset=ADA. Keep asset and quantity on the "
            "same actual funding or payout scope; two different assets on two "
            "different obligations are not a conflict. "
            "A destination_account_owner claim must be scoped to its actual "
            "deposit transition, never global or inferred from seller identity. "
            "A negative ownership statement is not supporting evidence for a "
            "positive account-owner claim. "
            "An exchange that executes "
            "automatically after both deposits is sequential deposits and payments, "
            "not an invented user Choice. On a missing second deposit, refund only "
            "the asset actually funded; on a missing first deposit, no refund is due. "
            "A terminal payout may continue to another terminal payout; set the "
            "second payout's parent_scope_id to the first payout scope. Represent "
            "automatic payouts through terminal_outcome scopes, not redundant "
            "autonomous_execution claims. A timeout's deadline_claim_id should "
            "reference the existing deposit deadline claim; do not duplicate that "
            "deadline as a new claim on the timeout. Keep asset claims on their "
            "specific funding/payout scopes instead of adding an unrelated global "
            "asset claim. First-deposit timeout may close directly with no extra "
            "terminal outcome. Synthetic answers in requirement_history are "
            "accepted only for this simulation: do not ask to reconfirm the token "
            "identity there, but never present it as a verified real-world fact. "
            "Do not introduce a payment transition for an automatic swap; the "
            "second deposit continues directly to the first terminal payout, "
            "which continues to the second terminal payout. When both funded "
            "assets are paid in full, their AST execution order is a deterministic "
            "compiler convention, not a missing business decision. Do not ask "
            "which payout happens first. On a labeled simulation, the question "
            "whether the synthetic token exists or was minted in the real world "
            "is outside the simulated contract semantics; retain that caveat "
            "without turning it into a required clarification. Explicit absence "
            "of Choice, Notify, oracle, or fees is not an unrepresented behavior. "
            "Every claim_id must be unique across the whole core. Cite only exact "
            "contiguous source substrings with correct revision and message index. "
            "Repeat a same-scope asset claim for EACH funding and payout outcome, "
            "including the native-token payout; a deposit's asset claim does not "
            "satisfy a later payout's asset requirement. A simulated token that "
            "is assumed available for this test does not require minting or "
            "real-world deployment proof as a clarification in this simulation. "
            "unscored_observations with reason=outside_stage2b_v3_claim_taxonomy "
            "are reserved ONLY for contract behavior genuinely absent from all "
            "claims and behavior_scopes, and they block compilation. Never use "
            "that reason to restate an automatic payout already represented by "
            "terminal_outcome scopes, a negative statement that no Choice/Notify "
            "exists, or a simulation-only provenance caveat already recorded in "
            "simulation_transcript. Do not add redundant unscored observations "
            "for facts represented in scopes/claims; omit them entirely. "
            "An explicit later revision with a full UTC timestamp ending Z "
            "resolves the timezone ambiguity of an earlier date-only phrase "
            "for that same deadline. Cite the later timestamp and do not ask "
            "the simulated customer to reconfirm UTC versus local time. "
            "Within a labeled customer simulation, a concrete answer in a "
            "later requirement revision is source evidence for that simulated "
            "run; use explicit or user_confirmed claim status as appropriate, "
            "not assumed. The accepted artifact still has NO_AUTHORITY and "
            "simulation_only=true, so this never becomes a real-world fact. "
            "Do not require the name of a transaction submitter merely to "
            "model automatic Pay or timeout reduction; submitter/fees are "
            "ledger-operation concerns outside this contract-intent profile."
        )
    if core_schema_version == CORE_SCHEMA_VERSION_V4:
        system = system.replace("outside_stage2b_v3_claim_taxonomy",
                                "outside_stage2b_v4_claim_taxonomy")
        system += (
            "\nA depositing_party claim must name the actual depositor and scope "
            "that depositor's deposit transition. A statement that someone does "
            "not deposit is not a positive depositing_party claim; never put a "
            "negated sentence in a party value. "
            "\nFor v4, represent the earliest allowed payment execution time with a "
            "source-backed payment_release_time_ms claim scoped to that payment "
            "transition. This is a not-before time, not timeout_ms or a latest deadline. "
            "Do not create a timeout/failure branch unless the source states what happens "
            "when an action misses a deadline. Keep timeout_ms only for an actual "
            "latest-time boundary with source-stated timeout behavior.\n"
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
            exact = explicit_utc_instants(message)
            for start, end, value in exact:
                hints.append({"requirement_version": revision.get("version"),
                              "message_index": index, "source_span": message[start:end],
                              "exact_utc_milliseconds": value})
            for match in re.finditer(
                    r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", message):
                if any(start <= match.start() and match.end() <= end
                       for start, end, _ in exact):
                    continue
                day, month, year = match.groups()
                try:
                    calendar_date = date(int(year), int(month), int(day))
                except ValueError:
                    continue
                hints.append({"requirement_version": revision.get("version"),
                              "message_index": index,
                              "source_span": f"{day}/{month}/{year}",
                              "calendar_date": calendar_date.isoformat(),
                              "timezone_unresolved": True})
            month_names = {name: number for number, name in enumerate((
                "january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "december"), 1)}
            for match in re.finditer(
                    r"(?<!\w)(\d{1,2})\s+(January|February|March|April|May|June|July|"
                    r"August|September|October|November|December)\s+(\d{4})(?!\w)",
                    message, re.IGNORECASE):
                if any(start <= match.start() and match.end() <= end
                       for start, end, _ in exact):
                    continue
                day, month, year = match.groups()
                try:
                    calendar_date = date(int(year), month_names[month.lower()], int(day))
                except ValueError:
                    continue
                hints.append({"requirement_version": revision.get("version"),
                              "message_index": index, "source_span": match.group(),
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
        self.normalization_actions: list[dict[str, Any]] = []
        self.repair_trace: list[dict[str, Any]] = []

    def _materialize(self, output: Any,
                     history: list[dict[str, Any]]) -> ShadowSemanticCore:
        parsed = parse_model_output(output)
        data, actions = materialize_core_draft(
            parsed.to_dict(), history, self.core_schema_version)
        messages = {(revision["version"], index): message
                    for revision in history
                    for index, message in enumerate(revision["messages"])}
        actions.extend(normalize_explicit_deadline_instants(data, messages))
        actions.extend(normalize_actor_scoped_deadlines(data, history))
        actions.extend(normalize_dot_native_asset_ids(data))
        actions.extend(derive_unambiguous_token_assets(data))
        self.normalization_actions = actions
        return ShadowSemanticCore(data)

    def _normalize_questions(self, data: dict[str, Any]) -> bool:
        aliases = normalize_clarification_question_aliases(data)
        removed = drop_resolved_time_format_questions(data)
        if aliases:
            self.normalization_actions.append({
                "kind": "clarification_question_aliases", "normalized_count": aliases,
            })
        if removed:
            self.normalization_actions.append({
                "kind": "resolved_time_format_questions", "removed_count": removed,
            })
        return bool(aliases or removed)

    def extract(self, requirement_history: list[dict[str, Any]]) -> ShadowSemanticCore:
        system, user = build_prompt(requirement_history,
                                    core_schema_version=self.core_schema_version)
        return self._materialize(self.model.generate(system, user), requirement_history)

    def validation_errors(self, core: ShadowSemanticCore,
                          requirement_history: list[dict[str, Any]]) -> list[str]:
        errors = core.validation_errors(expected_history=requirement_history)
        if core.to_dict().get("schema_version") != self.core_schema_version:
            errors.insert(0, f"schema_version must equal {self.core_schema_version}")
        return errors

    def extract_with_validation_feedback(
        self, requirement_history: list[dict[str, Any]], *, max_repairs: int = 1
    ) -> tuple[ShadowSemanticCore, list[str]]:
        if type(max_repairs) is not int or not 0 <= max_repairs <= 3:
            raise ValueError("max_repairs must be an integer from 0 through 3")
        system, user = build_prompt(requirement_history,
                                    core_schema_version=self.core_schema_version)
        self.repair_trace = []
        core = self._materialize(self.model.generate(system, user), requirement_history)
        normalized_core = core.to_dict()
        messages = {(revision["version"], index): message
                    for revision in requirement_history
                    for index, message in enumerate(revision["messages"])}
        retarget_actions = retarget_unique_evidence_spans(normalized_core, messages)
        choice_actions = normalize_choice_metadata(normalized_core, messages)
        evidence_actions = prune_unverifiable_evidence(normalized_core, messages)
        amount_actions = normalize_grounded_numeric_amounts(normalized_core, messages)
        derivation_actions = drop_dangling_amount_derivations(normalized_core, messages)
        self.normalization_actions.extend(retarget_actions + choice_actions
                                          + evidence_actions + amount_actions
                                          + derivation_actions)
        normalized_deadlines = normalize_vietnamese_noon_deadlines(normalized_core, messages)
        self.normalization_actions.extend(normalized_deadlines)
        collapsed_branches = collapse_automatic_success_branches(normalized_core)
        self.normalization_actions.extend({
            "scope_id": scope_id, "kind": "automatic_success_branch",
        } for scope_id in collapsed_branches)
        removed_branch_links = drop_decision_to_own_branch_or_timeout(normalized_core)
        self.normalization_actions.extend({
            "scope_id": scope_id, "kind": "decision_to_own_branch",
        } for scope_id in removed_branch_links)
        connected_outcomes = connect_skipped_terminal_outcomes(normalized_core)
        self.normalization_actions.extend({
            "scope_id": scope_id, "kind": "skipped_terminal_outcome",
        } for scope_id in connected_outcomes)
        questions_changed = self._normalize_questions(normalized_core)
        removed_refunds = drop_explicitly_absent_refund_recipient(normalized_core, messages)
        if (removed_refunds or questions_changed or normalized_deadlines
                or removed_branch_links or collapsed_branches or connected_outcomes
                or retarget_actions or choice_actions or evidence_actions or amount_actions
                or derivation_actions):
            core = parse_model_output(normalized_core)
        if removed_refunds:
            self.normalization_actions.extend({
                "claim_id": claim_id, "kind": "absent_refund_recipient",
                "reason": "source explicitly negates refund; none is not a party",
            } for claim_id in removed_refunds)
        initial_errors = self.validation_errors(core, requirement_history)
        if not initial_errors or max_repairs == 0:
            return core, initial_errors
        best_core = core
        best_error_count = len(set(initial_errors))
        seen = {json.dumps(core.to_dict(), sort_keys=True, ensure_ascii=False)}
        no_progress = 0
        full_regeneration_fallback_used = False
        force_full_regeneration = False

        def full_regenerate(current_core: ShadowSemanticCore,
                            current_errors: list[str]) -> ShadowSemanticCore:
            guidance = _repair_guidance(
                current_core.to_dict(), current_errors, requirement_history)
            feedback = (
                "The previous semantic core failed deterministic validation. "
                "Regenerate the complete seven-field core from the original requirement only. "
                "Do not infer new facts, omit financial claims, or change the resolution "
                "merely to satisfy validation. Fix only errors justified by the original text. "
                "Keep source spans verbatim and case-sensitive; never use ellipses. "
                "If derived_from points to a different claim kind, omit derived_from "
                "unless a valid same-kind source exists. Return JSON only.\n"
                "Validation errors:\n" + json.dumps(current_errors, ensure_ascii=False)
                + "\nTyped diagnostics (diagnosis only; regenerate from source):\n"
                + json.dumps(_group_repair_guidance(guidance), ensure_ascii=False)
            )
            return self._materialize(
                self.model.generate(_repair_system(system), user + "\n" + feedback),
                requirement_history)

        for repair_index in range(max_repairs):
            current_errors = self.validation_errors(core, requirement_history)
            if not current_errors:
                break
            target_ids = _evidence_repair_targets(core.to_dict(), current_errors)
            deadline_ids = {
                error[len("claim "):-len(": deadline value contradicts cited calendar date")]
                for error in current_errors
                if error.startswith("claim ")
                and error.endswith(": deadline value contradicts cited calendar date")
            }
            if force_full_regeneration:
                repair_kind = "FULL_REGENERATION_FALLBACK"
                core = full_regenerate(core, current_errors)
                force_full_regeneration = False
                full_regeneration_fallback_used = True
            elif deadline_ids:
                repair_kind = "NORMALIZATION"
                deadline_request = {
                    "requirement_history": requirement_history,
                    "claims": [claim for claim in core.to_dict()["claims"]
                               if claim.get("claim_id") in deadline_ids],
                    "calendar_hints": _calendar_hints(requirement_history),
                    "validation_errors": current_errors,
                }
                proposed = self.model.generate(
                    _repair_system("Repair only numeric POSIX millisecond values for the listed deadline "
                    "claims. Return exactly one JSON object with deadline_values mapping "
                    "each listed claim_id to one integer. Derive the instant from the "
                    "cited date, clock time, and timezone; never change the business "
                    "deadline or invent a timezone. Do not return a new semantic core."),
                    json.dumps(deadline_request, ensure_ascii=False),
                )
                values = proposed.get("deadline_values") if isinstance(proposed, dict) else None
                if (not isinstance(proposed, dict)
                        or set(proposed) != {"deadline_values"} or not isinstance(values, dict)
                        or set(values) != deadline_ids
                        or any(type(value) is not int for value in values.values())):
                    break
                patched = deepcopy(core.to_dict())
                for claim in patched["claims"]:
                    if claim.get("claim_id") in deadline_ids:
                        claim["value"] = values[claim["claim_id"]]
                core = parse_model_output(patched)
            elif any(error.startswith("claim ") and
                     error.endswith(": invalid derived_from source claim")
                     for error in current_errors):
                repair_kind = "PROVENANCE_LINK"
                link_ids = {
                    error[len("claim "):-len(": invalid derived_from source claim")]
                    for error in current_errors
                    if error.startswith("claim ") and
                    error.endswith(": invalid derived_from source claim")
                }
                proposed = self.model.generate(
                    _repair_system("Repair only invalid derived_from references. Return exactly one JSON "
                    "object with derived_from mapping every listed claim_id to either one "
                    "valid source claim_id string or null to omit the link. A source must "
                    "have the same claim kind and a supporting source span accepted by the "
                    "validator. Never change claim values, evidence, status, scopes, or "
                    "business facts. A calculation explained by normalization_basis does "
                    "not justify an invalid provenance link; use null if no valid link exists."),
                    json.dumps({"requirement_history": requirement_history,
                                "claims": core.to_dict()["claims"],
                                "claim_ids": sorted(link_ids),
                                "validation_errors": current_errors},
                               ensure_ascii=False),
                )
                links = None
                if isinstance(proposed, dict):
                    if set(proposed) == {"derived_from"}:
                        links = proposed["derived_from"]
                    elif set(proposed) == link_ids:
                        links = proposed
                if (not isinstance(links, dict) or set(links) != link_ids
                        or any(value is not None and not isinstance(value, str)
                               for value in links.values())):
                    break
                patched = deepcopy(core.to_dict())
                for claim in patched["claims"]:
                    claim_id = claim.get("claim_id")
                    if claim_id in link_ids:
                        if links[claim_id] is None:
                            claim.pop("derived_from", None)
                        else:
                            claim["derived_from"] = links[claim_id]
                core = parse_model_output(patched)
            elif any(error.endswith(": terminal outcome has no incoming continuation")
                   for error in current_errors):
                repair_kind = "SCOPE_GRAPH"
                outcome_request = {
                    "requirement_history": requirement_history,
                    "behavior_scopes": core.to_dict()["behavior_scopes"],
                    "claims": core.to_dict()["claims"],
                    "scope_schema_contract": core_prompt_schema_contract(
                        version=self.core_schema_version)["scope"],
                    "validation_errors": current_errors,
                }
                proposed = self.model.generate(
                    _repair_system("Repair orphan terminal outcomes only. Return exactly one JSON object "
                    "with behavior_scopes and claims. parent_scope_id alone does not "
                    "establish reachability: the predecessor branch, timeout, or transition "
                    "must name the outcome in continuation_scope_id. An outcome must be "
                    "reached by a source-supported continuation. If it has no valid path, remove that "
                    "outcome and only its dependent claims; otherwise add the actual "
                    "continuation. Deposit success is not a branch decision: remove a "
                    "redundant success branch under a Deposit and put its actual next "
                    "transition or outcome on the Deposit continuation directly. Keep "
                    "the separate Deposit timeout path. A payout outcome after a "
                    "payment event may continue to the next source-stated deposit; "
                    "do not leave it orphaned or erase the payout. Preserve all "
                    "unrelated scopes and claims. Do not "
                    "invent a payment, refund, or user fact to satisfy validation."),
                    json.dumps(outcome_request, ensure_ascii=False),
                )
                if (not isinstance(proposed, dict)
                        or set(proposed) != {"behavior_scopes", "claims"}
                        or not isinstance(proposed["behavior_scopes"], list)
                        or not isinstance(proposed["claims"], list)):
                    break
                patched = core.to_dict().copy()
                patched["behavior_scopes"] = proposed["behavior_scopes"]
                patched["claims"] = proposed["claims"]
                core = parse_model_output(patched)
            elif any(error.startswith("multiple root transitions without predecessor:")
                   for error in current_errors):
                repair_kind = "SCOPE_GRAPH"
                scope_request = {
                    "requirement_history": requirement_history,
                    "behavior_scopes": core.to_dict()["behavior_scopes"],
                    "scope_schema_contract": core_prompt_schema_contract(
                        version=self.core_schema_version)["scope"],
                    "validation_errors": current_errors,
                }
                proposed = self.model.generate(
                    _repair_system("Repair only behavior_scopes in this semantic core. Return exactly one "
                    "JSON object with behavior_scopes. Keep existing scope IDs and semantic "
                    "roles except a redundant terminal_outcome with no dependent claims "
                    "that incorrectly interrupts a source-stated sequence; it may be "
                    "removed. Add only source-supported causal continuation_scope_id links. "
                    "A continuation_scope_id may target only a transition or terminal_outcome, "
                    "never a timeout; a transition may not point to its timeout scope. "
                    "Do not preserve any invalid continuation_scope_id listed by validation. "
                    "When a transition incorrectly points to its timeout scope, redirect its "
                    "continuation to the next source-stated transition or terminal outcome; "
                    "the timeout's decision_id already identifies the deciding transition. "
                    "Connect source-stated sequential actions directly, transition to the "
                    "next transition or terminal outcome. A payment becoming available on "
                    "or after a date is not a timeout or failure deadline; do not create a "
                    "timeout scope for it unless the source states timeout behavior. "
                    "A single Marlowe contract has one entry transition. Do not infer "
                    "control flow from array order alone or invent a business event. "
                    "If source text says a deposit is followed by a buyer approval, "
                    "link that deposit to the approval Choice. If the source also "
                    "specifies no deposit by its deadline, preserve a separate deposit "
                    "timeout continuation for that outcome; the success continuation "
                    "must not point into its own timeout. "
                    "If source text states that a funding deposit is followed by a "
                    "repayment deposit, link the funding transition to the repayment "
                    "transition. If a first payment is followed by a second payment, "
                    "link the first payment to the second; the first is not terminal. "
                    "Resolve every listed multiple-root error by naming "
                    "the actual predecessor in continuation_scope_id; returning the "
                    "same disconnected scopes is not a repair."),
                    json.dumps(scope_request, ensure_ascii=False),
                )
                if (not isinstance(proposed, dict)
                        or set(proposed) != {"behavior_scopes"}
                        or not isinstance(proposed["behavior_scopes"], list)):
                    break
                patched = core.to_dict().copy()
                patched["behavior_scopes"] = proposed["behavior_scopes"]
                core = parse_model_output(patched)
            elif current_errors and all(error.startswith("scope ") and error.endswith(
                    ": deposit amount claim missing") for error in current_errors):
                repair_kind = "CLAIM_COMPLETENESS"
                missing_scopes = {
                    error[len("scope "):-len(": deposit amount claim missing")]
                    for error in current_errors
                }
                original = core.to_dict()
                proposed = self.model.generate(
                    _repair_system(
                        "Repair only missing source-backed deposit amounts. Return exactly "
                        "one JSON object with new_claims, a list containing one amount_lovelace "
                        "or amount_token_units claim for each listed deposit scope. Include a "
                        "unique claim_id, integer value in the token's smallest unit, "
                        "scope_id, status, criticality, exact source evidence and "
                        "normalization_basis when derived. 1 ADA = 1000000 lovelace. "
                        "Do not invent an amount absent from requirement_history. "
                        "Do not return or change existing claims, graph, or resolution."),
                    json.dumps({
                        "requirement_history": requirement_history,
                        "missing_deposit_scopes": [scope for scope in original["behavior_scopes"]
                                                   if scope.get("scope_id") in missing_scopes],
                        "existing_claims": original["claims"],
                        "validation_errors": current_errors,
                    }, ensure_ascii=False))
                new_claims = proposed.get("new_claims") if isinstance(proposed, dict) else None
                if (not isinstance(proposed, dict) or set(proposed) != {"new_claims"}
                        or not isinstance(new_claims, list)
                        or len(new_claims) != len(missing_scopes)
                        or any(not isinstance(item, dict)
                               or item.get("kind") not in {"amount_lovelace", "amount_token_units"}
                               or type(item.get("value")) is not int
                               or not isinstance(item.get("claim_id"), str)
                               or not item["claim_id"]
                               for item in new_claims)
                        or {item["scope_id"] for item in new_claims
                            if isinstance(item.get("scope_id"), str)} != missing_scopes
                        or len({item["claim_id"] for item in new_claims}) != len(new_claims)
                        or {item["claim_id"] for item in new_claims} & {
                            item.get("claim_id") for item in original["claims"]}):
                    break
                patched = original.copy()
                patched["claims"] = [*original["claims"], *new_claims]
                core = parse_model_output(patched)
            elif current_errors and all(
                    error == "invalid unscored_observation"
                    or (error.startswith("claim ") and error.endswith(
                        ": explicit recipient absent from cited evidence"))
                    for error in current_errors):
                repair_kind = "SOURCE_EVIDENCE"
                recipient_ids = {
                    error[len("claim "):-len(": explicit recipient absent from cited evidence")]
                    for error in current_errors if error.startswith("claim ")
                }
                original = core.to_dict()
                observation_contract = core_prompt_schema_contract(
                    version=self.core_schema_version)["unscored_observation"]
                messages = {(revision["version"], index): message
                            for revision in requirement_history
                            for index, message in enumerate(revision["messages"])}
                invalid_observations = {
                    item.get("observation_id") for item in original["unscored_observations"]
                    if isinstance(item, dict) and isinstance(item.get("observation_id"), str)
                    and (not UNSCORED_OBSERVATION_FIELDS <= item.keys()
                         or not item.get("text")
                         or item.get("reason") not in observation_contract["reason"]
                         or not _evidence_valid(item.get("source_evidence"), messages))
                }
                if ("invalid unscored_observation" in current_errors
                        and not invalid_observations):
                    break
                request = {
                    "requirement_history": requirement_history,
                    "recipient_claims": [item for item in original["claims"]
                                         if item.get("claim_id") in recipient_ids],
                    "invalid_observations": [item for item in original["unscored_observations"]
                                             if item.get("observation_id") in invalid_observations],
                    "allowed_observation_reasons": observation_contract["reason"],
                    "validation_errors": current_errors,
                }
                for retry in range(2):
                    proposed = self.model.generate(
                        _repair_system(
                        "Return exactly one JSON object with claim_evidence_or_drop and "
                        "observation_or_drop maps. Include every listed target ID exactly once. "
                        "For a recipient claim, return null if the source does not actually "
                        "name that recipient for that action. A claim whose value is the "
                        "literal string 'none' MUST map to null; it is not a party. "
                        "Otherwise return a replacement array of evidence OBJECTS, each "
                        "with requirement_version (integer), message_index (integer), "
                        "span (one verbatim substring), and relation='supports'. "
                        "For an observation, return null if redundant/irrelevant, or its "
                        "corrected full object with a contiguous verbatim source span. "
                        "Never combine text from different messages or revisions. "
                        "Do not change any other claim, observation, graph, amount, or deadline. "
                        "Example shape: {\"claim_evidence_or_drop\":{\"claim-id\":null},"
                        "\"observation_or_drop\":{\"observation-id\":null}}."),
                        json.dumps(request, ensure_ascii=False))
                    if (not isinstance(proposed, dict)
                        or set(proposed) != {"claim_evidence_or_drop", "observation_or_drop"}
                        or not isinstance(proposed["claim_evidence_or_drop"], dict)
                        or not isinstance(proposed["observation_or_drop"], dict)
                        or set(proposed["claim_evidence_or_drop"]) != recipient_ids
                        or set(proposed["observation_or_drop"]) != invalid_observations):
                        break
                    claim_changes = proposed["claim_evidence_or_drop"]
                    observation_changes = proposed["observation_or_drop"]
                    original_claims_by_id = {item["claim_id"]: item for item in original["claims"]
                                             if isinstance(item, dict) and "claim_id" in item}
                    valid = not (
                        any(value is not None and not isinstance(value, list)
                            for value in claim_changes.values())
                        or any(value is not None and not _evidence_valid(value, messages)
                               for value in claim_changes.values())
                        or any(original_claims_by_id.get(claim_id, {}).get("value") == "none"
                               and value is not None
                               for claim_id, value in claim_changes.items())
                        or any(value is not None and (not isinstance(value, dict)
                            or value.get("observation_id") != observation_id
                            or not UNSCORED_OBSERVATION_FIELDS <= value.keys()
                            or not value.get("text")
                            or value.get("reason") not in observation_contract["reason"]
                            or not _evidence_valid(value.get("source_evidence"), messages))
                            for observation_id, value in observation_changes.items()))
                    if valid:
                        break
                    request["rejected_repair"] = proposed
                    request["retry_reason"] = (
                        "A proposed evidence span is not an exact case-sensitive "
                        "substring of its indexed source message. Copy a valid "
                        "contiguous span or use null for an irrelevant observation.")
                else:
                    break
                if not valid:
                    break
                patched = original.copy()
                patched["claims"] = []
                for item in original["claims"]:
                    claim_id = item.get("claim_id")
                    if claim_id not in recipient_ids:
                        patched["claims"].append(item)
                    elif claim_changes[claim_id] is not None:
                        patched["claims"].append({**item, "evidence": claim_changes[claim_id]})
                patched["unscored_observations"] = [
                    item if item.get("observation_id") not in invalid_observations else
                    observation_changes[item["observation_id"]]
                    for item in original["unscored_observations"]
                    if (item.get("observation_id") not in invalid_observations
                        or observation_changes[item["observation_id"]] is not None)]
                core = parse_model_output(patched)
            elif target_ids:
                repair_kind = "SOURCE_EVIDENCE"
                repair_request = {
                    "requirement_history": requirement_history,
                    "claims": [claim for claim in core.to_dict()["claims"]
                               if claim["claim_id"] in target_ids],
                    "verbatim_source_messages": _verbatim_source_messages(
                        core.to_dict(), target_ids, requirement_history),
                    "validation_errors": current_errors,
                }
                repair_system = _repair_system(
                    "Repair only the evidence of the listed claims. Return one JSON object "
                    "with exactly evidence_by_claim mapping each listed claim_id to its "
                    "replacement evidence array. Each evidence item must have "
                    "requirement_version, message_index, span, relation. Copy only exact "
                    "contiguous source spans from requirement_history, with no ellipses. "
                    "Use verbatim_source_messages to copy the exact text at each claim's "
                    "source index. If a date, time, and shared timezone are separated "
                    "within one message, cite that entire message verbatim rather than "
                    "joining fragments into a phrase the user never wrote. "
                    "A span must actually support that claim and role. Do not invent facts "
                    "or return a new semantic core."
                )
                proposed = self.model.generate(
                    repair_system, json.dumps(repair_request, ensure_ascii=False))
                patched = _apply_evidence_repair(core.to_dict(), proposed, target_ids)
                if patched is None:
                    break
                core = parse_model_output(patched)
            elif (self.core_schema_version == CORE_SCHEMA_VERSION_V4
                  and current_errors and all(
                      error.startswith("scope ") and error.endswith((
                          ": invalid choice_guard", ": invalid choice_bounds"))
                      for error in current_errors)):
                repair_kind = "CHOICE_EVIDENCE"
                original = core.to_dict()
                targets = {error.split(": invalid choice_", 1)[0].removeprefix("scope "):
                           "choice_guard" if error.endswith("choice_guard")
                           else "choice_bounds" for error in current_errors}
                if (set(targets) != {scope.get("scope_id") for scope in original["behavior_scopes"]
                                     if scope.get("scope_id") in targets}
                        or any(not isinstance(scope.get(targets[scope["scope_id"]]), dict)
                               for scope in original["behavior_scopes"]
                               if scope.get("scope_id") in targets)):
                    break
                request = {"requirement_history": requirement_history,
                           "target_scopes": [scope for scope in original["behavior_scopes"]
                                             if scope.get("scope_id") in targets],
                           "validation_errors": current_errors}
                for retry in range(2):
                    proposed = self.model.generate(
                        _repair_system(
                            "Repair only source_evidence for the listed Choice scopes. Return one "
                            "JSON object with evidence_by_scope mapping each listed scope_id to "
                            "a nonempty array of evidence objects. Each span must be one exact "
                            "contiguous substring of its indexed requirement message and must "
                            "support that scope's existing bound or guard value. Preserve every "
                            "operator, numeric value, claim, graph edge, and business fact."),
                        json.dumps(request, ensure_ascii=False))
                    evidence = (proposed.get("evidence_by_scope")
                                if isinstance(proposed, dict) else None)
                    valid = (isinstance(proposed, dict)
                             and set(proposed) == {"evidence_by_scope"}
                             and isinstance(evidence, dict) and set(evidence) == set(targets)
                             and all(isinstance(items, list) and items
                                     and _evidence_valid(items, messages)
                                     and all(item.get("relation") == "supports" for item in items)
                                     for items in evidence.values()))
                    if valid:
                        break
                    if retry == 0:
                        request["rejected_evidence_by_scope"] = evidence
                        request["retry_reason"] = (
                            "The previous span was not an exact contiguous substring of "
                            "the indexed source message. Copy only a shorter exact span "
                            "that contains the existing guard or bound value.")
                else:
                    break
                patched = deepcopy(original)
                for scope in patched["behavior_scopes"]:
                    if scope.get("scope_id") in targets:
                        scope[targets[scope["scope_id"]]]["source_evidence"] = evidence[scope["scope_id"]]
                core = parse_model_output(patched)
            elif current_errors and all(
                    error.startswith("claim ") and error.endswith(
                        ": depositing party must scope a deposit transition")
                    for error in current_errors):
                repair_kind = "PARTY_SCOPE"
                original = core.to_dict()
                target_ids = {
                    error[len("claim "):-len(": depositing party must scope a deposit transition")]
                    for error in current_errors
                }
                deposit_scopes = {
                    scope["scope_id"] for scope in original["behavior_scopes"]
                    if scope.get("scope_type") == "transition"
                    and scope.get("transition_kind") == "deposit"
                }
                proposed = self.model.generate(
                    _repair_system(
                        "Repair only depositing_party claims listed in target_claims. "
                        "Return exactly one JSON object with scope_or_drop, mapping "
                        "each target claim_id to a deposit transition scope_id or null. "
                        "Use null when source evidence explicitly says that person "
                        "does not deposit; a negation is not a positive depositor. "
                        "Otherwise choose only the actual source-backed deposit "
                        "transition for that person. Do not change any other claim, "
                        "value, graph edge, or business fact."),
                    json.dumps({
                        "requirement_history": requirement_history,
                        "target_claims": [claim for claim in original["claims"]
                                          if claim.get("claim_id") in target_ids],
                        "deposit_scopes": [scope for scope in original["behavior_scopes"]
                                           if scope.get("scope_id") in deposit_scopes],
                        "validation_errors": current_errors,
                    }, ensure_ascii=False))
                choices = proposed.get("scope_or_drop") if isinstance(proposed, dict) else None
                if (not isinstance(proposed, dict) or set(proposed) != {"scope_or_drop"}
                        or not isinstance(choices, dict) or set(choices) != target_ids
                        or any(value is not None and value not in deposit_scopes
                               for value in choices.values())):
                    break
                patched = original.copy()
                patched["claims"] = [
                    ({**claim, "scope_id": choices[claim["claim_id"]]}
                     if claim.get("claim_id") in target_ids else claim)
                    for claim in original["claims"]
                    if claim.get("claim_id") not in target_ids
                    or choices[claim["claim_id"]] is not None
                ]
                core = parse_model_output(patched)
            elif current_errors == [
                    "clarification prediction requires an unresolved claim or "
                    "unrepresented behavior observation"]:
                repair_kind = "BUSINESS_DECISION"
                original = core.to_dict()
                proposed = self.model.generate(
                    _repair_system(
                        "Review only the business decision against requirement_history "
                        "and the existing semantic core. Return exactly one JSON object "
                        "with predicted_resolution and required_clarifications. "
                        "Use clarification_required only if a specific critical fact "
                        "remains unresolved or a source-grounded behavior observation "
                        "requires an answer. An already supplied answer is not missing. "
                        "If the source fully resolves those matters, use "
                        "accepted_interpretation with an empty question list. "
                        "Do not change claims, evidence, scopes, amounts, deadlines, or "
                        "invent a fact merely to obtain acceptance."),
                    json.dumps({
                        "requirement_history": requirement_history,
                        "semantic_core": original,
                        "validation_errors": current_errors,
                    }, ensure_ascii=False))
                if (not isinstance(proposed, dict)
                        or set(proposed) != {"predicted_resolution", "required_clarifications"}
                        or not isinstance(proposed["predicted_resolution"], str)
                        or not isinstance(proposed["required_clarifications"], list)):
                    break
                patched = original.copy()
                patched.update(proposed)
                core = parse_model_output(patched)
            else:
                repair_kind = "FULL_REGENERATION"
                core = full_regenerate(core, current_errors)
            repaired = core.to_dict()
            retarget_actions = retarget_unique_evidence_spans(repaired, messages)
            choice_actions = normalize_choice_metadata(repaired, messages)
            evidence_actions = prune_unverifiable_evidence(repaired, messages)
            amount_actions = normalize_grounded_numeric_amounts(repaired, messages)
            derivation_actions = drop_dangling_amount_derivations(repaired, messages)
            self.normalization_actions.extend(retarget_actions + choice_actions
                                              + evidence_actions + amount_actions
                                              + derivation_actions)
            if (retarget_actions or choice_actions or evidence_actions
                    or amount_actions or derivation_actions):
                core = parse_model_output(repaired)
            normalized_deadlines = normalize_vietnamese_noon_deadlines(repaired, messages)
            self.normalization_actions.extend(normalized_deadlines)
            if normalized_deadlines:
                core = parse_model_output(repaired)
            collapsed_branches = collapse_automatic_success_branches(repaired)
            if collapsed_branches:
                core = parse_model_output(repaired)
                self.normalization_actions.extend({
                    "scope_id": scope_id, "kind": "automatic_success_branch",
                } for scope_id in collapsed_branches)
            removed_branch_links = drop_decision_to_own_branch_or_timeout(repaired)
            if removed_branch_links:
                core = parse_model_output(repaired)
                self.normalization_actions.extend({
                    "scope_id": scope_id, "kind": "decision_to_own_branch",
                } for scope_id in removed_branch_links)
            connected_outcomes = connect_skipped_terminal_outcomes(repaired)
            if connected_outcomes:
                core = parse_model_output(repaired)
                self.normalization_actions.extend({
                    "scope_id": scope_id, "kind": "skipped_terminal_outcome",
                } for scope_id in connected_outcomes)
            removed_outcomes = prune_unreachable_duplicate_outcomes(repaired)
            if removed_outcomes:
                core = parse_model_output(repaired)
                self.normalization_actions.extend({
                    "scope_id": scope_id, "kind": "unreachable_duplicate_outcome",
                    "reason": "no references; parent already continues to same successor",
                } for scope_id in removed_outcomes)
            if self._normalize_questions(repaired):
                core = parse_model_output(repaired)
            removed_refunds = drop_explicitly_absent_refund_recipient(repaired, messages)
            if removed_refunds:
                core = parse_model_output(repaired)
                self.normalization_actions.extend({
                    "claim_id": claim_id, "kind": "absent_refund_recipient",
                    "reason": "source explicitly negates refund; none is not a party",
                } for claim_id in removed_refunds)
            after_errors = self.validation_errors(core, requirement_history)
            progressed = repair_progress(current_errors, after_errors)
            if len(set(after_errors)) < best_error_count:
                best_core = core
                best_error_count = len(set(after_errors))
            self.repair_trace.append({
                "repair_kind": repair_kind,
                "before_error_count": len(set(current_errors)),
                "after_error_count": len(set(after_errors)),
                "before_codes": diagnostic_codes(current_errors),
                "after_codes": diagnostic_codes(after_errors),
                "progressed": progressed,
            })
            no_progress = 0 if progressed else no_progress + 1
            fingerprint = json.dumps(core.to_dict(), sort_keys=True, ensure_ascii=False)
            if fingerprint in seen:
                if (repair_kind != "FULL_REGENERATION"
                        and not full_regeneration_fallback_used
                        and repair_index + 1 < max_repairs):
                    force_full_regeneration = True
                    continue
                break
            if no_progress >= 2:
                break
            seen.add(fingerprint)
        return best_core, initial_errors


def _verbatim_source_messages(core: dict[str, Any], target_ids: set[str],
                              history: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    messages = {(revision.get("version"), index): message
                for revision in history if isinstance(revision, dict)
                for index, message in enumerate(revision.get("messages", []))
                if isinstance(message, str)}
    result: dict[str, list[dict[str, Any]]] = {}
    for claim in core.get("claims", []):
        if not isinstance(claim, dict) or claim.get("claim_id") not in target_ids:
            continue
        cited: list[dict[str, Any]] = []
        for item in claim.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            version, index = item.get("requirement_version"), item.get("message_index")
            if type(version) is not int or type(index) is not int:
                continue
            message = messages.get((version, index))
            if message is not None and not any(
                    old["requirement_version"] == version and old["message_index"] == index
                    for old in cited):
                cited.append({"requirement_version": version, "message_index": index,
                              "message": message})
        result[claim["claim_id"]] = cited
    return result


def _evidence_repair_targets(core: dict[str, Any], errors: list[str]) -> set[str]:
    if not errors:
        return set()
    claims = core.get("claims")
    if not isinstance(claims, list):
        return set()
    claim_ids = {claim.get("claim_id") for claim in claims if isinstance(claim, dict)}
    targets = set()
    for error in errors:
        if error == "invalid unscored_observation":
            continue
        if not (error.startswith("claim ") and (error.endswith(": invalid evidence target/span")
                or error.endswith(": supporting evidence required"))):
            return set()
        claim_id = error.split(":", 1)[0].removeprefix("claim ")
        if claim_id not in claim_ids:
            return set()
        targets.add(claim_id)
    return targets


def _apply_evidence_repair(core: dict[str, Any], proposed: Any,
                           target_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(proposed, dict) or set(proposed) != {"evidence_by_claim"}:
        return None
    replacements = proposed["evidence_by_claim"]
    if not isinstance(replacements, dict) or set(replacements) != target_ids:
        return None
    if any(not isinstance(items, list) or not items
           or any(not isinstance(item, dict) for item in items)
           for items in replacements.values()):
        return None
    patched = deepcopy(core)
    for claim in patched["claims"]:
        if claim["claim_id"] in target_ids:
            claim["evidence"] = deepcopy(replacements[claim["claim_id"]])
    return patched


def _group_repair_guidance(guidance: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Share repeated instructions while retaining every diagnosed error and detail."""
    grouped: list[dict[str, Any]] = []
    by_rule: dict[str, dict[str, Any]] = {}
    for item in guidance:
        rule = item["rule"]
        group = by_rule.get(rule)
        if group is None:
            group = {"rule": rule, "diagnostics": []}
            by_rule[rule] = group
            grouped.append(group)
        group["diagnostics"].append({key: value for key, value in item.items()
                                     if key != "rule"})
    return grouped


def _repair_guidance(core: dict[str, Any], errors: list[str],
                     history: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
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
            scope_id = error.rsplit(" in ", 1)[-1]
            amount_claims = [item for item in core.get("claims", [])
                             if isinstance(item, dict)
                             and item.get("kind") == "amount_lovelace"
                             and item.get("scope_id") == scope_id] if isinstance(
                                 core.get("claims"), list) else []
            values = [item.get("value") for item in amount_claims]
            unit_duplicate = next(((small, large)
                                   for small in values for large in values
                                   if type(small) is int and type(large) is int
                                   and small > 0 and small * 1_000_000 == large), None)
            guidance.append({
                "error": error,
                "rule": (("A raw ADA numeral must not also be an amount_lovelace "
                          f"claim. For {unit_duplicate[0]} ADA keep one source-backed "
                          f"{unit_duplicate[1]}-lovelace claim at this scope; omit the "
                          f"unsupported {unit_duplicate[0]}-lovelace "
                          "duplicate and its derived_from link. Do not hide a real "
                          "business conflict.") if unit_duplicate else
                         ("First check the full requirement history: if a later answer "
                          "explicitly corrects the earlier value for this same obligation, "
                          "mark the earlier claim superseded and retain the corrected "
                          "claim with exact provenance; this is not a live conflict. "
                          "Otherwise check whether the values describe independent obligations. "
                          "If so, attach each claim to its actual funding or outcome scope; "
                          "if they are incompatible values for the same obligation, preserve "
                          "the conflict and request clarification. Do not delete a supported claim.")),
            })
        elif "invalid derived_from source claim" in error:
            guidance.append({
                "error": error,
                "rule": ("For this exact claim, remove the derived_from key when it "
                         "points to an asset claim or any other claim kind. An asset "
                         "claim cannot prove an amount_lovelace quantity. Keep this "
                         "amount_lovelace claim, its supported numeric value, exact "
                         "source evidence and normalization_basis unchanged. Do not "
                         "invent another claim or derived_from link. If a separate "
                         "raw ADA-unit duplicate exists, omit that raw duplicate."),
            })
        elif "invalid evidence target/span" in error or "supporting evidence required" in error:
            item: dict[str, Any] = {
                "error": error,
                "rule": ("Copy an exact contiguous substring from a supplied requirement "
                         "message that states this fact and role. If none exists, mark the "
                         "fact unresolved rather than fabricate source evidence."),
            }
            claim_id = error.split(":", 1)[0].removeprefix("claim ")
            claims = core.get("claims", [])
            claim = next((value for value in claims if isinstance(value, dict)
                          and value.get("claim_id") == claim_id), None) if isinstance(claims, list) else None
            if claim is not None and history is not None:
                matches = []
                for evidence in claim.get("evidence", []):
                    span = evidence.get("span") if isinstance(evidence, dict) else None
                    if not isinstance(span, str) or not span:
                        continue
                    for revision in history:
                        for index, message in enumerate(revision.get("messages", [])):
                            if span in message:
                                matches.append({"requirement_version": revision.get("version"),
                                                "message_index": index, "span": span})
                if matches:
                    item["exact_span_locations"] = matches
                    item["rule"] += (" The listed locations only establish where the quoted "
                                     "text occurs; independently verify that it supports the "
                                     "claimed fact and role.")
            guidance.append(item)
        elif error.endswith(": invalid choice_bounds") or error.endswith(": invalid choice_guard"):
            is_bounds = error.endswith(": invalid choice_bounds")
            guidance.append({
                "error": error,
                "rule": (("The Choice transition must include choice_bounds with "
                          "integer from and to (inclusive) plus source_evidence. "
                          "Do not omit choice_bounds or replace it with a claim. "
                          "Use only source-backed numeric bounds. ") if is_bounds else
                         ("Each Choice branch must include choice_guard with operator "
                          "and integer value plus source_evidence. Do not omit "
                          "choice_guard or replace it with a claim. The guard must "
                          "fit the parent Choice bounds and the source-stated outcome. "))
                        + ("source_evidence must be a nonempty JSON array of objects, "
                           "not one object. Each item needs requirement_version, "
                           "message_index, span, and relation. Use a contiguous, case-sensitive "
                           "quote from the referenced requirement message, including the "
                           "correct version and message index. A yes/no approval may use "
                           "the documented Choice value 1 encoding only when the source "
                           "explicitly names the approver and approval outcome; do not "
                           "invent a rejection branch."),
            })
        elif error == "required_clarifications must contain nonempty questions":
            guidance.append({
                "error": error,
                "rule": ("required_clarifications must be a JSON array of nonempty "
                         "question strings or objects with a nonempty question field. "
                         "Include a question only for a genuinely "
                         "unresolved critical fact; "
                         "otherwise use [] and select the source-supported resolution."),
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
            claim_id = error.split(":", 1)[0].removeprefix("claim ")
            claims = core.get("claims", [])
            claim = next((item for item in claims if isinstance(item, dict)
                          and item.get("claim_id") == claim_id), None) if isinstance(
                              claims, list) else None
            exact = sorted({value for item in (claim or {}).get("evidence", [])
                            if isinstance(item, dict) and item.get("relation") == "supports"
                            and isinstance(item.get("span"), str)
                            for _, _, value in explicit_utc_instants(item["span"])})
            if not exact and isinstance(history, list):
                messages = {(revision.get("version"), index): message
                            for revision in history if isinstance(revision, dict)
                            for index, message in enumerate(revision.get("messages", []))
                            if isinstance(message, str)}
                instants = set()
                for evidence in (claim or {}).get("evidence", []):
                    if (not isinstance(evidence, dict)
                            or evidence.get("relation") != "supports"
                            or not isinstance(evidence.get("span"), str)):
                        continue
                    source = messages.get((evidence.get("requirement_version"),
                                           evidence.get("message_index")))
                    if source is None:
                        continue
                    clock_dates = re.findall(
                        r"\d{1,2}:\d{2}\s+(?:(?:ngày|on)\s+)?"
                        r"\d{1,2}/\d{1,2}/\d{4}", evidence["span"], re.IGNORECASE)
                    for start, end, value in explicit_utc_instants(source):
                        if any(fragment.lower() in source[start:end].lower()
                               for fragment in clock_dates):
                            instants.add(value)
                exact = sorted(instants)
            item = {
                "error": error,
                "rule": (("The cited local clock and UTC offset determine an exact "
                          "instant. Use only the source-backed millisecond value listed "
                          "here; do not shift the cited month/year or mark it unresolved.")
                         if exact else
                         ("Do not guess POSIX milliseconds from a date-only source. "
                          "If the requirement gives no timezone/cutoff, set the deadline "
                          "claim value=null and status=unresolved, then ask a concrete "
                          "cutoff question. Only derive milliseconds from an exact "
                          "source-backed instant or labeled later revision. Never shift "
                          "the cited year to make an integer fit.")),
            }
            if exact:
                item["source_backed_utc_milliseconds"] = exact
            guidance.append(item)
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
