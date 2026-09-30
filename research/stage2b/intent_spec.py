"""Deterministic validation for research-only IntentSpec shadow predictions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from research.stage2a.foundation import CLAIM_KINDS, CLAIM_STATUSES, RESOLUTIONS, SCOPE_TYPES


SCHEMA_VERSION = "stage2b-shadow-v1"
REQUIRED_FIELDS = {
    "schema_version", "requirement_history", "participants", "assets_and_accounts",
    "parameters", "states", "transitions", "obligations_and_outcomes",
    "behavior_scopes", "claims", "required_clarifications", "conflicts",
    "assumptions_and_provenance", "unscored_observations", "predicted_resolution",
}
ACTIVE_STATUSES = {"explicit", "derived", "assumed", "user_confirmed", "conflicted"}
PARTY_KINDS = {
    "choice_owner", "depositing_party", "destination_account_owner",
    "payment_source_account_owner", "payment_recipient", "refund_recipient",
    "release_recipient",
}
DEADLINE_KINDS = {
    "choice_deadline_ms", "deposit_deadline_ms", "refund_deadline_ms", "timeout_ms",
}
TRANSITION_DEADLINE_KINDS = {
    "deposit": {"deposit_deadline_ms"},
    "choice": {"choice_deadline_ms", "timeout_ms"},
    "notify": {"timeout_ms"},
}
RECIPIENT_KINDS = {"payment_recipient", "refund_recipient", "release_recipient"}
BACKING_STATUSES = {"explicit", "derived", "user_confirmed"}
ASSETS_ACCOUNTS_FIELDS = {"assets", "accounts", "funding_relations"}
CLAIM_FIELDS = {
    "claim_id", "kind", "value", "criticality", "status", "scope_id", "evidence",
    "normalization_basis", "assumption_reason", "superseded_by", "derived_from",
}
SCOPE_FIELDS = {
    "global": {"scope_id", "scope_type"},
    "transition": {"scope_id", "scope_type", "transition_kind"},
    "branch": {"scope_id", "scope_type", "decision_id", "branch_id"},
    "timeout": {"scope_id", "scope_type", "timeout_id", "decision_id", "deadline_claim_id"},
    "terminal_outcome": {"scope_id", "scope_type", "outcome_id"},
}
STATE_CLAIM_KINDS = {
    "funded": {"depositing_party"},
    "awaiting_choice": {"choice_owner", "choice_deadline_ms"},
    "released": {"release_recipient"},
    "refunded": {"refund_recipient"},
    "paid": {"payment_recipient"},
}
OUTCOME_RECIPIENT_KINDS = {
    "payment": {"payment_recipient"},
    "refund": {"refund_recipient"},
    "release": {"release_recipient"},
}
RICH_FIELDS = {
    "participants": {"participant_id", "name", "claim_refs"},
    "assets": {"asset_id", "symbol", "claim_refs"},
    "accounts": {"account_id", "owner", "claim_refs"},
    "funding_relations": {"relation_id", "scope_id", "party", "account_owner",
                          "asset_id", "claim_refs"},
    "parameters": {"parameter_id", "kind", "normalized_value", "unit", "claim_refs"},
    "states": {"state_id", "claim_refs"},
    "transitions": {"transition_id", "kind", "actor", "deadline_parameter_id",
                    "transaction_submitter", "claim_refs"},
    "obligations_and_outcomes": {"outcome_id", "kind", "recipient", "scope_id", "claim_refs"},
    "conflicts": {"conflict_id", "kind", "scope_id", "claim_refs"},
    "assumptions_and_provenance": {"assumption_id", "text", "claim_refs"},
}


def _allowed(value: Any, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


@dataclass
class IntentSpec:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def validation_errors(self, *, expected_history: list[dict[str, Any]] | None = None) -> list[str]:
        return validate_intent_spec(self.data, expected_history=expected_history)


def _evidence_valid(items: Any, messages: dict[tuple[int, int], str]) -> bool:
    return isinstance(items, list) and bool(items) and all(
        isinstance(item, dict)
        and isinstance(item.get("requirement_version"), int)
        and not isinstance(item.get("requirement_version"), bool)
        and isinstance(item.get("message_index"), int)
        and not isinstance(item.get("message_index"), bool)
        and isinstance(item.get("span"), str)
        and bool(item["span"])
        and item["span"] in messages.get(
            (item["requirement_version"], item["message_index"]), "")
        and _allowed(item.get("relation"), {"supports", "contradicts"})
        for item in items
    )


def valid_supporting_evidence(claim: dict[str, Any], messages: dict[tuple[int, int], str]) -> bool:
    if claim.get("status") == "assumed":
        return False
    evidence = claim.get("evidence")
    return _evidence_valid(evidence, messages) and any(
        item["relation"] == "supports" for item in evidence)


def _messages(history: Any, errors: list[str]) -> dict[tuple[int, int], str]:
    messages: dict[tuple[int, int], str] = {}
    if not isinstance(history, list) or not history:
        errors.append("requirement_history must be nonempty")
        return messages
    for expected_version, version in enumerate(history, 1):
        if not isinstance(version, dict) or version.get("version") != expected_version:
            errors.append("requirement versions must be consecutive from 1")
            continue
        entries = version.get("messages")
        if not isinstance(entries, list) or not entries:
            errors.append("requirement messages must be nonempty")
            continue
        for index, message in enumerate(entries):
            if not isinstance(message, str) or not message.strip():
                errors.append("requirement message must be nonempty text")
            else:
                messages[(expected_version, index)] = message
    return messages


def _claim_refs(item: dict[str, Any], claims: dict[str, dict[str, Any]],
                label: str, errors: list[str]) -> list[dict[str, Any]]:
    refs = item.get("claim_refs", [])
    if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in claims
                                         for ref in refs):
        errors.append(f"{label}: broken claim_ref")
        return []
    return [claims[ref] for ref in refs]


def _backed(value: Any, refs: list[dict[str, Any]], kinds: set[str],
            scope_id: str | None = None) -> bool:
    return any(_allowed(claim.get("kind"), kinds) and claim.get("value") == value
               and _allowed(claim.get("status"), BACKING_STATUSES)
               and (scope_id is None or claim.get("scope_id") == scope_id)
               for claim in refs)


def _same_source_span(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_evidence = first.get("evidence")
    second_evidence = second.get("evidence")
    if not isinstance(first_evidence, list) or not isinstance(second_evidence, list):
        return False
    for left in first_evidence:
        for right in second_evidence:
            if not isinstance(left, dict) or not isinstance(right, dict):
                continue
            if not isinstance(left.get("span"), str) or not isinstance(right.get("span"), str):
                continue
            if (left.get("requirement_version") == right.get("requirement_version")
                    and left.get("message_index") == right.get("message_index")
                    and (left.get("span") in right.get("span") or
                         right.get("span") in left.get("span"))):
                return True
    return False


def valid_derived_source(claim: dict[str, Any], source: dict[str, Any] | None) -> bool:
    return bool(source and _allowed(source.get("status"), {"explicit", "user_confirmed"})
                and source.get("kind") == claim.get("kind")
                and _same_source_span(claim, source))


def validate_intent_spec(spec: Any, *,
                         expected_history: list[dict[str, Any]] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["IntentSpec must be an object"]
    missing = REQUIRED_FIELDS - spec.keys()
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    extra = spec.keys() - REQUIRED_FIELDS
    if extra:
        errors.append(f"unknown top-level fields: {sorted(extra)}")
    if "mutation" in spec or "parent_case_id" in spec:
        errors.append("mutation-specific knowledge is not allowed in IntentSpec")
    if spec.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid schema_version")
    resolution = spec.get("predicted_resolution")
    if not _allowed(resolution, RESOLUTIONS):
        errors.append("invalid predicted_resolution")
    messages = _messages(spec.get("requirement_history"), errors)
    if expected_history is not None and spec.get("requirement_history") != expected_history:
        errors.append("requirement_history differs from supplied source")

    scopes: dict[str, dict[str, Any]] = {}
    raw_scopes = spec.get("behavior_scopes")
    if not isinstance(raw_scopes, list):
        errors.append("behavior_scopes must be a list")
        raw_scopes = []
    for scope in raw_scopes:
        if not isinstance(scope, dict):
            errors.append("invalid behavior scope")
            continue
        scope_id = scope.get("scope_id")
        if not isinstance(scope_id, str) or not scope_id:
            errors.append("invalid scope_id")
            continue
        if scope_id in scopes:
            errors.append(f"duplicate scope_id {scope_id}")
        scopes[scope_id] = scope
        scope_type = scope.get("scope_type")
        if not _allowed(scope_type, SCOPE_TYPES):
            errors.append(f"scope {scope_id}: invalid scope_type")
        else:
            unknown = scope.keys() - SCOPE_FIELDS[scope_type]
            if unknown:
                errors.append(f"scope {scope_id}: unsupported scope fields {sorted(unknown)}")
        if scope.get("scope_type") == "global" and scope_id != "global":
            errors.append(f"scope {scope_id}: global scope_id must be global")
        if scope.get("scope_type") == "transition" and (not isinstance(
                scope.get("transition_kind"), str) or not scope["transition_kind"].strip()):
            errors.append(f"scope {scope_id}: transition_kind required")
        if scope.get("scope_type") == "branch" and not scope.get("branch_id"):
            errors.append(f"scope {scope_id}: branch_id required")
        if scope.get("scope_type") == "timeout" and not scope.get("timeout_id"):
            errors.append(f"scope {scope_id}: timeout_id required")
        if scope_type == "terminal_outcome" and not scope.get("outcome_id"):
            errors.append(f"scope {scope_id}: outcome_id required")
    for scope_id, scope in scopes.items():
        decision = scope.get("decision_id")
        if decision is not None and (not isinstance(decision, str) or decision not in scopes or
                                     scopes[decision].get("scope_type") != "transition"):
            errors.append(f"scope {scope_id}: decision_id does not reference transition")
        if scope.get("scope_type") == "branch" and decision is None:
            errors.append(f"scope {scope_id}: branch requires decision_id")

    claims: dict[str, dict[str, Any]] = {}
    raw_claims = spec.get("claims")
    if not isinstance(raw_claims, list):
        errors.append("claims must be a list")
        raw_claims = []
    for claim in raw_claims:
        if not isinstance(claim, dict):
            errors.append("invalid claim")
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            errors.append("invalid claim_id")
            continue
        if claim_id in claims:
            errors.append(f"duplicate claim_id {claim_id}")
        claims[claim_id] = claim
        unknown = claim.keys() - CLAIM_FIELDS
        if unknown:
            errors.append(f"claim {claim_id}: unsupported claim fields {sorted(unknown)}")
        if not _allowed(claim.get("kind"), CLAIM_KINDS):
            errors.append(f"claim {claim_id}: unknown claim kind")
        if not _allowed(claim.get("status"), CLAIM_STATUSES):
            errors.append(f"claim {claim_id}: invalid status")
        if not isinstance(claim.get("scope_id"), str) or claim["scope_id"] not in scopes:
            errors.append(f"claim {claim_id}: scope_id not found")
        if not _allowed(claim.get("criticality"), {"financial", "nonfinancial"}):
            errors.append(f"claim {claim_id}: invalid criticality")
        status = claim.get("status")
        evidence = claim.get("evidence")
        if evidence is not None and evidence != [] and not _evidence_valid(evidence, messages):
            errors.append(f"claim {claim_id}: invalid evidence target/span")
        if _allowed(status, {"explicit", "user_confirmed", "superseded", "conflicted", "derived"}):
            if not valid_supporting_evidence(claim, messages):
                errors.append(f"claim {claim_id}: supporting evidence required")
        evidence_items = evidence if isinstance(evidence, list) else []
        if status == "user_confirmed" and not any(
            isinstance(item, dict) and isinstance(item.get("requirement_version"), int)
            and item["requirement_version"] > 1 for item in evidence_items):
            errors.append(f"claim {claim_id}: user confirmation must follow initial requirement")
        if status == "assumed" and not isinstance(claim.get("assumption_reason"), str):
            errors.append(f"claim {claim_id}: assumption_reason required")
        elif status == "assumed" and not claim["assumption_reason"].strip():
            errors.append(f"claim {claim_id}: assumption_reason required")
        if status == "unresolved" and claim.get("value") is not None:
            errors.append(f"claim {claim_id}: unresolved value must be null")
        if status == "derived":
            if claim.get("criticality") == "financial" and not claim.get("normalization_basis"):
                errors.append(f"claim {claim_id}: normalization_basis required")
    for claim in raw_claims:
        if not isinstance(claim, dict):
            continue
        if claim.get("status") == "derived":
            source_id = claim.get("derived_from")
            if source_id is not None:
                source = claims.get(source_id) if isinstance(source_id, str) else None
                if not valid_derived_source(claim, source):
                    errors.append(f"claim {claim.get('claim_id')}: invalid derived_from source claim")
        if claim.get("status") == "superseded":
            successor_id = claim.get("superseded_by")
            successor = claims.get(successor_id) if isinstance(successor_id, str) else None
            old_evidence = claim.get("evidence")
            new_evidence = (successor or {}).get("evidence")
            old_versions = [item["requirement_version"] for item in
                            (old_evidence if isinstance(old_evidence, list) else [])
                            if isinstance(item, dict) and
                            isinstance(item.get("requirement_version"), int)]
            new_versions = [item["requirement_version"] for item in
                            (new_evidence if isinstance(new_evidence, list) else [])
                            if isinstance(item, dict) and
                            isinstance(item.get("requirement_version"), int)]
            if (successor is None or successor.get("status") == "superseded"
                    or successor.get("kind") != claim.get("kind")
                    or successor.get("scope_id") != claim.get("scope_id")
                    or not old_versions or not new_versions
                    or max(old_versions) >= max(new_versions)):
                errors.append(f"claim {claim.get('claim_id')}: invalid supersession")
    for scope_id, scope in scopes.items():
        deadline_id = scope.get("deadline_claim_id")
        if deadline_id is not None:
            deadline_claim = claims.get(deadline_id) if isinstance(deadline_id, str) else None
            if deadline_claim is None or not _allowed(deadline_claim.get("kind"), DEADLINE_KINDS):
                errors.append(f"scope {scope_id}: deadline_claim_id must reference deadline claim")
    by_scope: dict[tuple[str, str], set[str]] = {}
    for claim in raw_claims:
        if isinstance(claim, dict) and _allowed(claim.get("status"), ACTIVE_STATUSES):
            key = (str(claim.get("kind")), str(claim.get("scope_id")))
            by_scope.setdefault(key, set()).add(json.dumps(claim.get("value"), sort_keys=True))
    conflicting = {key for key, values in by_scope.items() if len(values) > 1}
    for kind, scope_id in conflicting:
        if resolution != "conflict_requires_resolution":
            errors.append(f"active claim conflict for {kind} in {scope_id}")
        if not all(claim.get("status") == "conflicted" for claim in raw_claims
                   if isinstance(claim, dict) and claim.get("kind") == kind
                   and claim.get("scope_id") == scope_id
                   and _allowed(claim.get("status"), ACTIVE_STATUSES)):
            errors.append(f"conflicting values for {kind} in {scope_id} must be marked conflicted")
    if resolution == "conflict_requires_resolution" and not conflicting:
        errors.append("conflict prediction requires two conflicting claims in one scope")
    for claim in raw_claims:
        if isinstance(claim, dict) and claim.get("status") == "conflicted":
            if (str(claim.get("kind")), str(claim.get("scope_id"))) not in conflicting:
                errors.append(f"claim {claim.get('claim_id')}: conflicted status needs distinct active values")
    clarifications = spec.get("required_clarifications")
    if not isinstance(clarifications, list):
        errors.append("required_clarifications must be a list")
    elif _allowed(resolution, {"clarification_required", "conflict_requires_resolution"}) and not clarifications:
        errors.append("clarification/conflict prediction requires a business question")
    if resolution == "accepted_interpretation":
        if any(claim.get("criticality") == "financial" and _allowed(
               claim.get("status"), {"unresolved", "conflicted", "assumed"}) for claim in raw_claims
               if isinstance(claim, dict)):
            errors.append("accepted prediction has unsafe critical claim")
        if clarifications:
            errors.append("accepted prediction still requests clarification")

    assets_accounts = spec.get("assets_and_accounts")
    if not isinstance(assets_accounts, dict):
        errors.append("assets_and_accounts must be an object")
        assets_accounts = {}
    unknown = assets_accounts.keys() - ASSETS_ACCOUNTS_FIELDS
    if unknown:
        errors.append(f"assets_and_accounts: unknown fields {sorted(unknown)}")
    missing = ASSETS_ACCOUNTS_FIELDS - assets_accounts.keys()
    if missing:
        errors.append(f"assets_and_accounts: missing fields {sorted(missing)}")
    sections = {
        "participants": spec.get("participants"),
        "assets": assets_accounts.get("assets"),
        "accounts": assets_accounts.get("accounts"),
        "funding_relations": assets_accounts.get("funding_relations"),
        "parameters": spec.get("parameters"),
        "states": spec.get("states"),
        "transitions": spec.get("transitions"),
        "obligations_and_outcomes": spec.get("obligations_and_outcomes"),
        "conflicts": spec.get("conflicts"),
        "assumptions_and_provenance": spec.get("assumptions_and_provenance"),
    }
    assets = {item.get("asset_id"): item for item in sections["assets"]
              if isinstance(item, dict) and isinstance(item.get("asset_id"), str)} if isinstance(
                  sections["assets"], list) else {}
    parameters = {item.get("parameter_id"): item for item in sections["parameters"]
                  if isinstance(item, dict) and isinstance(item.get("parameter_id"), str)} if isinstance(
                      sections["parameters"], list) else {}
    represented_conflicts: set[tuple[str, str]] = set()
    for name, items in sections.items():
        if not isinstance(items, list):
            errors.append(f"{name} must be a list")
            continue
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"{name}: item must be an object")
                continue
            unknown = item.keys() - RICH_FIELDS[name]
            if unknown:
                errors.append(f"{name}: unsupported rich fields {sorted(unknown)}")
            refs = _claim_refs(item, claims, name, errors)
            if name == "participants" and item.get("name") is not None:
                if not _backed(item["name"], refs, PARTY_KINDS):
                    errors.append("participant name lacks matching claim_ref")
            if name == "assets" and item.get("symbol") is not None:
                if not _backed(item["symbol"], refs, {"asset"}):
                    errors.append("asset symbol lacks matching claim_ref")
            if name == "accounts" and item.get("owner") is not None:
                if not _backed(item["owner"], refs, {
                    "destination_account_owner", "payment_source_account_owner"}):
                    errors.append("account owner lacks matching claim_ref")
            if name == "funding_relations":
                scope_id = item.get("scope_id")
                if (not isinstance(scope_id, str) or scope_id not in scopes or
                        scopes[scope_id].get("scope_type") != "transition"):
                    errors.append("funding relation scope_id must reference transition")
                if item.get("party") is not None and not _backed(
                    item["party"], refs, {"depositing_party"}, scope_id):
                    errors.append("funding party lacks matching claim_ref")
                if item.get("account_owner") is not None and not _backed(
                    item["account_owner"], refs, {"destination_account_owner",
                                                       "payment_source_account_owner"}, scope_id):
                    errors.append("funding account owner lacks matching claim_ref")
                asset_id = item.get("asset_id")
                if asset_id is not None:
                    asset = assets.get(asset_id) if isinstance(asset_id, str) else None
                    if asset is None or not _backed(asset.get("symbol"), refs, {"asset"}):
                        errors.append("funding asset_id lacks matching asset and claim_ref")
            if name == "parameters" and item.get("normalized_value") is not None:
                kinds = ({"amount_lovelace"} if item.get("kind") == "amount" else
                         DEADLINE_KINDS if item.get("kind") == "deadline" else {"asset"})
                if not _backed(item["normalized_value"], refs, kinds):
                    errors.append("parameter value lacks matching claim_ref")
            if name == "parameters" and not _allowed(
                    item.get("kind"), {"amount", "deadline", "asset"}):
                errors.append("parameter kind is unsupported")
            if name == "states" and item.get("state_id") != "initial":
                state_id = item.get("state_id")
                kinds = STATE_CLAIM_KINDS.get(state_id) if isinstance(state_id, str) else None
                if kinds is None:
                    errors.append("business state kind is unsupported")
                elif not any(_allowed(claim.get("kind"), kinds) and
                             _allowed(claim.get("status"), BACKING_STATUSES) for claim in refs):
                    errors.append("business state lacks matching claim_ref")
            if name == "transitions":
                transition_id = item.get("transition_id")
                if (not isinstance(transition_id, str) or transition_id not in scopes or
                        scopes[transition_id].get("scope_type") != "transition"):
                    errors.append("transition_id lacks matching business scope")
                elif item.get("kind") != scopes[transition_id].get("transition_kind"):
                    errors.append("transition.kind differs from scope.transition_kind")
                if item.get("transaction_submitter") is not None:
                    errors.append("transaction_submitter cannot be inferred from actor")
                if item.get("deadline_parameter_id") is not None:
                    parameter_id = item["deadline_parameter_id"]
                    parameter = parameters.get(parameter_id) if isinstance(parameter_id, str) else None
                    if parameter is None or parameter.get("kind") != "deadline":
                        errors.append("transition deadline_parameter_id must reference deadline")
                    elif not any(_allowed(
                                 claim.get("kind"), TRANSITION_DEADLINE_KINDS.get(
                                     item.get("kind"), set()) if isinstance(item.get("kind"), str)
                                     else set())
                                 and claim.get("scope_id") == transition_id
                                 and claim.get("value") == parameter.get("normalized_value")
                                 and isinstance(parameter.get("claim_refs"), list)
                                 and claim.get("claim_id") in parameter["claim_refs"]
                                 for claim in refs):
                        errors.append("transition deadline lacks matching scoped claim_ref")
            if name == "transitions" and item.get("actor") is not None:
                actor_kind = {"choice": {"choice_owner"}, "deposit": {"depositing_party"}}
                kind = item.get("kind")
                kinds = actor_kind.get(kind, set()) if isinstance(kind, str) else set()
                if not _backed(item["actor"], refs, kinds, item.get("transition_id")):
                    errors.append("transition actor lacks matching claim_ref")
            if name == "obligations_and_outcomes" and item.get("recipient") is not None:
                outcome_kind = item.get("kind")
                recipient_kinds = OUTCOME_RECIPIENT_KINDS.get(outcome_kind, set()) if isinstance(
                    outcome_kind, str) else set()
                if not _backed(item["recipient"], refs, recipient_kinds, item.get("scope_id")):
                    errors.append("outcome recipient lacks matching scoped claim_ref")
            if name == "obligations_and_outcomes" and not _allowed(
                    item.get("kind"), set(OUTCOME_RECIPIENT_KINDS)):
                errors.append("outcome kind is unsupported")
            if name == "obligations_and_outcomes" and (not isinstance(item.get("scope_id"), str)
                                                        or item["scope_id"] not in scopes):
                errors.append("outcome scope_id not found")
            if name == "conflicts":
                kind = item.get("kind")
                scope_id = item.get("scope_id")
                values = {json.dumps(claim.get("value"), sort_keys=True) for claim in refs
                          if claim.get("status") == "conflicted"
                          and claim.get("kind") == kind and claim.get("scope_id") == scope_id}
                if (not isinstance(scope_id, str) or scope_id not in scopes
                        or len(refs) < 2 or len(values) < 2 or len(values) != len(refs)):
                    errors.append("conflict object must reference distinct conflicted claims in one scope")
                else:
                    represented_conflicts.add((kind, scope_id))
    for kind, scope_id in conflicting - represented_conflicts:
        errors.append(f"conflict {kind} in {scope_id} lacks matching conflict object")
    observations = spec.get("unscored_observations")
    if not isinstance(observations, list):
        errors.append("unscored_observations must be a list")
    else:
        for item in observations:
            if (not isinstance(item, dict) or not item.get("observation_id")
                    or not item.get("text") or
                    item.get("reason") != "outside_stage2b_v1_claim_taxonomy"
                    or not _evidence_valid(item.get("source_evidence"), messages)):
                errors.append("invalid unscored_observation")
    return errors
