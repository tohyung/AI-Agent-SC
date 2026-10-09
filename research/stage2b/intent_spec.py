"""Deterministic validation for research-only IntentSpec shadow predictions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import re
from typing import Any

from research.stage2a.foundation import CLAIM_KINDS, CLAIM_STATUSES, RESOLUTIONS, SCOPE_TYPES


SCHEMA_VERSION = "stage2b-shadow-v1"
CORE_SCHEMA_VERSION = "stage2b-shadow-core-v1"
SCHEMA_VERSION_V2 = "stage2b-shadow-v2"
CORE_SCHEMA_VERSION_V2 = "stage2b-shadow-core-v2"
SCHEMA_VERSION_V3 = "stage2b-shadow-v3"
CORE_SCHEMA_VERSION_V3 = "stage2b-shadow-core-v3"
CLAIM_KINDS_V3 = CLAIM_KINDS | {"amount_token_units", "ledger_history_deletion"}
NATIVE_ASSET_ID = re.compile(r"native:([0-9a-f]{56})/([0-9a-f]{2,64})\Z")


def parse_native_asset_id(value: str) -> tuple[str, str] | None:
    match = NATIVE_ASSET_ID.fullmatch(value)
    return match.groups() if match else None
CORE_FIELDS = {
    "schema_version", "requirement_history", "behavior_scopes", "claims",
    "required_clarifications", "unscored_observations", "predicted_resolution",
}
REQUIRED_FIELDS = {
    "schema_version", "requirement_history", "participants", "assets_and_accounts",
    "parameters", "states", "transitions", "obligations_and_outcomes",
    "behavior_scopes", "claims", "required_clarifications", "conflicts",
    "assumptions_and_provenance", "unscored_observations", "predicted_resolution",
}
ACTIVE_STATUSES = {"explicit", "derived", "assumed", "user_confirmed", "conflicted"}
CRITICALITIES = {"financial", "nonfinancial"}
PARAMETER_KINDS = {"amount", "deadline", "asset"}
EVIDENCE_RELATIONS = {"supports", "contradicts"}
EVIDENCE_FIELDS = {"requirement_version", "message_index", "span", "relation"}
SUPPORTING_EVIDENCE_STATUSES = {"explicit", "user_confirmed", "superseded", "conflicted", "derived"}
UNSAFE_ACCEPT_STATUSES = {"unresolved", "conflicted", "assumed"}
RESOLUTION_REQUIRED = {"clarification_required", "conflict_requires_resolution"}
DERIVED_SOURCE_STATUSES = {"explicit", "user_confirmed"}
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
TRANSITION_KINDS = {"choice", "deposit", "notify", "payment"}
# Stage 2B core-v1 only; a future unsupported feature needs a versioned signal.
UNSUPPORTED_SIGNALS_V1 = frozenset({("autonomous_execution", True)})
UNSUPPORTED_SIGNALS_V3 = frozenset({("ledger_history_deletion", True)})
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
SCOPE_FIELDS_V2 = {
    **SCOPE_FIELDS,
    "transition": SCOPE_FIELDS["transition"] | {"choice_bounds", "continuation_scope_id"},
    "branch": SCOPE_FIELDS["branch"] | {"choice_guard", "continuation_scope_id"},
    "timeout": SCOPE_FIELDS["timeout"] | {"continuation_scope_id"},
    "terminal_outcome": SCOPE_FIELDS["terminal_outcome"] |
                        {"parent_scope_id", "continuation_scope_id"},
}
CHOICE_GUARD_OPERATORS = {"ge", "gt", "le", "lt", "eq"}
DECISION_TARGET_SCOPE_TYPE = "transition"
UNSCORED_OBSERVATION_FIELDS = {"observation_id", "text", "reason", "source_evidence"}
UNSCORED_OBSERVATION_REASON = "outside_stage2b_v1_claim_taxonomy"
UNSCORED_OBSERVATION_REASONS_V2 = {
    "irrelevant_context", "outside_stage2b_v2_claim_taxonomy",
}
UNSCORED_OBSERVATION_REASONS_V3 = {
    "irrelevant_context", "outside_stage2b_v3_claim_taxonomy",
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
OUTCOME_KINDS = set(OUTCOME_RECIPIENT_KINDS)
STATE_IDS = {"initial"} | set(STATE_CLAIM_KINDS)
ACCOUNT_OWNER_KINDS = {"destination_account_owner", "payment_source_account_owner"}
PARAMETER_CLAIM_KINDS = {
    "amount": {"amount_lovelace", "amount_token_units"},
    "deadline": DEADLINE_KINDS, "asset": {"asset"},
}
TRANSITION_ACTOR_KINDS = {"choice": {"choice_owner"}, "deposit": {"depositing_party"}}
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


def prompt_schema_contract(*, core_version: str = CORE_SCHEMA_VERSION) -> dict[str, Any]:
    """Expose the validator's closed vocabulary to the shadow model."""
    return {
        "schema_version": {CORE_SCHEMA_VERSION: SCHEMA_VERSION,
                           CORE_SCHEMA_VERSION_V2: SCHEMA_VERSION_V2,
                           CORE_SCHEMA_VERSION_V3: SCHEMA_VERSION_V3}[core_version],
        "required_top_level_fields": sorted(REQUIRED_FIELDS),
        "claim": {
            "fields": sorted(CLAIM_FIELDS),
            "kinds": sorted(CLAIM_KINDS_V3 if core_version == CORE_SCHEMA_VERSION_V3
                            else CLAIM_KINDS),
            "statuses": sorted(CLAIM_STATUSES),
            "criticalities": sorted(CRITICALITIES),
            "active_statuses": sorted(ACTIVE_STATUSES),
            "backing_statuses": sorted(BACKING_STATUSES),
            "supporting_evidence_statuses": sorted(SUPPORTING_EVIDENCE_STATUSES),
        },
        "evidence": {
            "fields": sorted(EVIDENCE_FIELDS),
            "relations": sorted(EVIDENCE_RELATIONS),
        },
        "resolution": {
            "values": sorted(RESOLUTIONS),
            "requires_user_resolution": sorted(RESOLUTION_REQUIRED),
        },
        "scope": {
            "types": sorted(SCOPE_TYPES),
            "allowed_fields_by_type": {key: sorted(value) for key, value in
                                       (SCOPE_FIELDS_V2 if core_version in {
                                           CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3}
                                        else SCOPE_FIELDS).items()},
        },
        "assets_and_accounts_fields": sorted(ASSETS_ACCOUNTS_FIELDS),
        "rich_fields": {key: sorted(value) for key, value in RICH_FIELDS.items()},
        "parameter_kinds": sorted(PARAMETER_KINDS),
        "outcome_kinds": sorted(OUTCOME_KINDS),
        "state_ids": sorted(STATE_IDS),
        "state_claim_kinds": {key: sorted(value) for key, value in STATE_CLAIM_KINDS.items()},
        "outcome_recipient_kinds": {key: sorted(value) for key, value in OUTCOME_RECIPIENT_KINDS.items()},
        "deadline_kinds": sorted(DEADLINE_KINDS),
        "transition_deadline_kinds": {
            key: sorted(value) for key, value in TRANSITION_DEADLINE_KINDS.items()},
        "party_kinds": sorted(PARTY_KINDS),
        "account_owner_kinds": sorted(ACCOUNT_OWNER_KINDS),
        "parameter_claim_kinds": {
            key: sorted(value) for key, value in PARAMETER_CLAIM_KINDS.items()},
        "transition_actor_kinds": {
            key: sorted(value) for key, value in TRANSITION_ACTOR_KINDS.items()},
        "derived_source_statuses": sorted(DERIVED_SOURCE_STATUSES),
        "unsafe_accept_statuses": sorted(UNSAFE_ACCEPT_STATUSES),
    }


def core_prompt_schema_contract(*, version: str = CORE_SCHEMA_VERSION) -> dict[str, Any]:
    if version not in {CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3}:
        raise ValueError("unsupported core schema version")
    contract = prompt_schema_contract(core_version=version)
    contract["schema_version"] = version
    contract["required_top_level_fields"] = sorted(CORE_FIELDS)
    contract["transition_kinds"] = sorted(TRANSITION_KINDS)
    contract["scope"]["scope_id_unique"] = True
    contract["scope"]["global_scope_id"] = "global"
    contract["scope"]["references"] = {
        "decision_id": {
            "target_collection": "behavior_scopes",
            "target_id_field": "scope_id",
            "target_scope_type": DECISION_TARGET_SCOPE_TYPE,
            "required_for": ["branch"],
            "optional_for": ["timeout"],
        },
        "deadline_claim_id": {
            "target_collection": "claims",
            "target_id_field": "claim_id",
            "allowed_kinds": sorted(DEADLINE_KINDS),
            "optional_for": ["timeout"],
        },
    }
    contract["unsupported_signals"] = [
        {"kind": kind, "value": value, "requires_supporting_evidence": True}
        for kind, value in sorted(
            UNSUPPORTED_SIGNALS_V3 if version == CORE_SCHEMA_VERSION_V3
            else UNSUPPORTED_SIGNALS_V1
        )
    ]
    if version in {CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3}:
        contract["scope"]["choice_bounds"] = {
            "fields": ["from", "to", "source_evidence"],
            "required_for": "choice transition", "integer_inclusive": True,
            "source_evidence_type": "nonempty_array_of_evidence_objects",
            "source_evidence_item_fields": sorted(EVIDENCE_FIELDS),
        }
        contract["scope"]["choice_guard"] = {
            "fields": ["operator", "value", "source_evidence"],
            "required_for": "branch of choice transition",
            "operators": sorted(CHOICE_GUARD_OPERATORS),
            "value_type": "integer", "source_evidence_required": True,
            "source_evidence_type": "nonempty_array_of_evidence_objects",
            "source_evidence_item_fields": sorted(EVIDENCE_FIELDS),
        }
        contract["scope"]["terminal_outcome_parent"] = {
            "field": "parent_scope_id", "required": True,
            "target_collection": "behavior_scopes", "target_id_field": "scope_id",
            "target_scope_types": (["branch", "timeout", "transition", "terminal_outcome"]
                                   if version == CORE_SCHEMA_VERSION_V3 else
                                   ["branch", "timeout", "transition"]),
        }
        contract["scope"]["continuation"] = {
            "field": "continuation_scope_id", "optional": True,
            "target_collection": "behavior_scopes", "target_id_field": "scope_id",
            "target_scope_types": ["transition", "terminal_outcome"],
            "meaning": "the next action or outcome on this path; never infer from list order",
        }
    contract["unscored_observation"] = {
        "fields": sorted(UNSCORED_OBSERVATION_FIELDS),
        "reason": (sorted(UNSCORED_OBSERVATION_REASONS_V3)
                   if version == CORE_SCHEMA_VERSION_V3 else
                   sorted(UNSCORED_OBSERVATION_REASONS_V2)
                   if version == CORE_SCHEMA_VERSION_V2 else UNSCORED_OBSERVATION_REASON),
        "source_evidence": {
            "fields": sorted(EVIDENCE_FIELDS),
            "relations": sorted(EVIDENCE_RELATIONS),
            "nonempty": True,
            "exact_source_span": True,
        },
        "authoritative_financial_facts_belong_in_claims": True,
    }
    for key in ("assets_and_accounts_fields", "rich_fields", "parameter_kinds",
                "outcome_kinds", "state_ids", "state_claim_kinds",
                "outcome_recipient_kinds", "transition_deadline_kinds",
                "party_kinds", "account_owner_kinds", "parameter_claim_kinds",
                "transition_actor_kinds"):
        contract.pop(key)
    return contract


def _allowed(value: Any, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


@dataclass
class IntentSpec:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def validation_errors(self, *, expected_history: list[dict[str, Any]] | None = None) -> list[str]:
        return validate_intent_spec(self.data, expected_history=expected_history)


@dataclass
class ShadowSemanticCore:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def validation_errors(self, *, expected_history: list[dict[str, Any]] | None = None) -> list[str]:
        return validate_shadow_semantic_core(self.data, expected_history=expected_history)


def extract_core_view(spec: dict[str, Any]) -> dict[str, Any]:
    core_version = {SCHEMA_VERSION: CORE_SCHEMA_VERSION,
                    SCHEMA_VERSION_V2: CORE_SCHEMA_VERSION_V2,
                    SCHEMA_VERSION_V3: CORE_SCHEMA_VERSION_V3}.get(
                        spec.get("schema_version"), CORE_SCHEMA_VERSION)
    return {key: (core_version if key == "schema_version" else spec[key])
            for key in CORE_FIELDS if key in spec}


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
        and _allowed(item.get("relation"), EVIDENCE_RELATIONS)
        for item in items
    )


def valid_supporting_evidence(claim: dict[str, Any], messages: dict[tuple[int, int], str]) -> bool:
    if claim.get("status") == "assumed":
        return False
    evidence = claim.get("evidence")
    return _evidence_valid(evidence, messages) and any(
        item["relation"] == "supports" for item in evidence)


def explicit_utc_instants(text: str) -> list[tuple[int, int, int]]:
    """Locate exact source instants; date-only phrases remain intentionally unknown."""
    found: list[tuple[int, int, int]] = []
    iso = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z(?!\d)")
    local = re.compile(
        r"(?<!\d)(?P<hour>\d{1,2}):(?P<minute>\d{2})\s+(?:(?:ngày|on)\s+)?"
        r"(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})"
        r"[^.;\n]{0,80}?\bUTC(?P<sign>[+-])(?P<offset_hour>\d{1,2})"
        r"(?::(?P<offset_minute>\d{2}))?\b",
        re.IGNORECASE,
    )
    for match in iso.finditer(text):
        try:
            instant = datetime.fromisoformat(match.group().replace("Z", "+00:00"))
        except ValueError:
            continue
        found.append((match.start(), match.end(), int(instant.timestamp() * 1000)))
    for match in local.finditer(text):
        parts = {name: int(match.group(name)) for name in (
            "hour", "minute", "day", "month", "year", "offset_hour")}
        offset_minute = int(match.group("offset_minute") or 0)
        if parts["offset_hour"] > 23 or offset_minute > 59:
            continue
        sign = 1 if match.group("sign") == "+" else -1
        offset = timezone(sign * timedelta(hours=parts["offset_hour"],
                                           minutes=offset_minute))
        try:
            instant = datetime(parts["year"], parts["month"], parts["day"],
                               parts["hour"], parts["minute"], tzinfo=offset)
        except ValueError:
            continue
        found.append((match.start(), match.end(), int(instant.timestamp() * 1000)))
    offsets = list(re.finditer(r"\bUTC(?P<sign>[+-])(?P<hour>\d{1,2})"
                               r"(?::(?P<minute>\d{2}))?\b", text, re.IGNORECASE))
    if len(offsets) == 1:
        offset_match = offsets[0]
        offset_hour = int(offset_match.group("hour"))
        offset_minute = int(offset_match.group("minute") or 0)
        if offset_hour <= 23 and offset_minute <= 59:
            sign = 1 if offset_match.group("sign") == "+" else -1
            shared_offset = timezone(sign * timedelta(hours=offset_hour,
                                                      minutes=offset_minute))
            shared = re.compile(
                r"(?<!\d)(?P<hour>\d{1,2}):(?P<minute>\d{2})\s+"
                r"(?:(?:ngày|on)\s+)?(?P<day>\d{1,2})/(?P<month>\d{1,2})/"
                r"(?P<year>\d{4})[^.;\n]{0,80}?\b(?:same timezone|cùng múi giờ)\b",
                re.IGNORECASE,
            )
            for match in shared.finditer(text):
                if match.start() <= offset_match.end():
                    continue
                try:
                    instant = datetime(int(match.group("year")), int(match.group("month")),
                                       int(match.group("day")), int(match.group("hour")),
                                       int(match.group("minute")), tzinfo=shared_offset)
                except ValueError:
                    continue
                found.append((match.start(), match.end(), int(instant.timestamp() * 1000)))
    return sorted(found)


def _absolute_deadline_mismatch(claim: dict[str, Any]) -> bool:
    """Reject a date claim whose cited calendar year/day contradicts its POSIX value."""
    value = claim.get("value")
    if type(value) is not int:
        return False
    cited_dates: list[date] = []
    exact_instants: list[int] = []
    for item in claim.get("evidence", []) if isinstance(claim.get("evidence"), list) else []:
        if not isinstance(item, dict) or item.get("relation") != "supports":
            continue
        span = item.get("span")
        if not isinstance(span, str):
            continue
        exact_instants.extend(value for _, _, value in explicit_utc_instants(span))
        for day, month, year in re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", span):
            try:
                cited_dates.append(date(int(year), int(month), int(day)))
            except ValueError:
                continue
        for year, month, day in re.findall(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", span):
            try:
                cited_dates.append(date(int(year), int(month), int(day)))
            except ValueError:
                continue
    if exact_instants:
        if value in exact_instants:
            return False
        if len(set(cited_dates)) == 1:
            return True
        # A shared timezone after several dates may attach to a date the parser missed.
        # In that case only a calendar contradiction is provable from this span.
    if not cited_dates:
        return False
    try:
        actual = datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return True
    return all(abs((actual - cited).days) > 1 for cited in cited_dates)


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
    return bool(source and _allowed(source.get("status"), DERIVED_SOURCE_STATUSES)
                and source.get("kind") == claim.get("kind")
                and _same_source_span(claim, source))


def validate_shadow_semantic_core(spec: Any, *,
                                  expected_history: list[dict[str, Any]] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["ShadowSemanticCore must be an object"]
    missing = CORE_FIELDS - spec.keys()
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    extra = spec.keys() - CORE_FIELDS
    if extra:
        errors.append(f"unknown top-level fields: {sorted(extra)}")
    if "mutation" in spec or "parent_case_id" in spec:
        errors.append("mutation-specific knowledge is not allowed in IntentSpec")
    version = spec.get("schema_version")
    if version not in {CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3}:
        errors.append("invalid schema_version")
    v2 = version in {CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3}
    v3 = version == CORE_SCHEMA_VERSION_V3
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
            allowed = SCOPE_FIELDS_V2 if v2 else SCOPE_FIELDS
            unknown = scope.keys() - allowed[scope_type]
            if unknown:
                errors.append(f"scope {scope_id}: unsupported scope fields {sorted(unknown)}")
        if scope.get("scope_type") == "global" and scope_id != "global":
            errors.append(f"scope {scope_id}: global scope_id must be global")
        if scope_id == "global" and scope_type != "global":
            errors.append("scope global: scope_type must be global")
        if scope_type == "transition" and not _allowed(
                scope.get("transition_kind"), TRANSITION_KINDS):
            errors.append(f"scope {scope_id}: unsupported transition_kind")
        if scope.get("scope_type") == "branch" and not scope.get("branch_id"):
            errors.append(f"scope {scope_id}: branch_id required")
        if scope.get("scope_type") == "timeout" and not scope.get("timeout_id"):
            errors.append(f"scope {scope_id}: timeout_id required")
        if scope_type == "terminal_outcome" and not scope.get("outcome_id"):
            errors.append(f"scope {scope_id}: outcome_id required")
    for scope_id, scope in scopes.items():
        decision = scope.get("decision_id")
        if v2 and "continuation_scope_id" in scope:
            successor_id = scope["continuation_scope_id"]
            successor = scopes.get(successor_id) if isinstance(successor_id, str) else None
            if (successor is None or successor_id == scope_id or
                    successor.get("scope_type") not in {"transition", "terminal_outcome"}):
                errors.append(f"scope {scope_id}: invalid continuation_scope_id")
        if decision is not None and (not isinstance(decision, str) or decision not in scopes or
                                     scopes[decision].get("scope_type") != DECISION_TARGET_SCOPE_TYPE):
            errors.append(f"scope {scope_id}: decision_id does not reference transition")
        if scope.get("scope_type") == "branch" and decision is None:
            errors.append(f"scope {scope_id}: branch requires decision_id")
        if v2 and scope.get("scope_type") == "terminal_outcome":
            parent_id = scope.get("parent_scope_id")
            parent = scopes.get(parent_id) if isinstance(parent_id, str) else None
            allowed_parents = {"branch", "timeout", "transition"}
            if v3:
                allowed_parents.add("terminal_outcome")
            if parent is None or parent.get("scope_type") not in allowed_parents:
                errors.append(f"scope {scope_id}: invalid parent_scope_id")
        if v2 and scope.get("scope_type") == "transition" and scope.get("transition_kind") == "choice":
            bounds = scope.get("choice_bounds")
            if (not isinstance(bounds, dict) or set(bounds) != {"from", "to", "source_evidence"}
                    or not isinstance(bounds.get("from"), int) or isinstance(bounds.get("from"), bool)
                    or not isinstance(bounds.get("to"), int) or isinstance(bounds.get("to"), bool)
                    or bounds["from"] > bounds["to"]
                    or not _evidence_valid(bounds.get("source_evidence"), messages)):
                errors.append(f"scope {scope_id}: invalid choice_bounds")
        if v2 and scope.get("scope_type") == "branch" and isinstance(decision, str):
            parent = scopes.get(decision)
            if parent and parent.get("transition_kind") == "choice":
                guard = scope.get("choice_guard")
                bounds = parent.get("choice_bounds")
                if (not isinstance(guard, dict)
                        or set(guard) != {"operator", "value", "source_evidence"}
                        or not _allowed(guard.get("operator"), CHOICE_GUARD_OPERATORS)
                        or not isinstance(guard.get("value"), int)
                        or isinstance(guard.get("value"), bool)
                        or not _evidence_valid(guard.get("source_evidence"), messages)):
                    errors.append(f"scope {scope_id}: invalid choice_guard")
                elif (isinstance(bounds, dict) and isinstance(bounds.get("from"), int)
                      and isinstance(bounds.get("to"), int)
                      and not bounds["from"] <= guard["value"] <= bounds["to"]):
                    errors.append(f"scope {scope_id}: choice_guard outside choice_bounds")

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
        if not _allowed(claim.get("kind"), CLAIM_KINDS_V3 if v3 else CLAIM_KINDS):
            errors.append(f"claim {claim_id}: unknown claim kind")
        if not _allowed(claim.get("status"), CLAIM_STATUSES):
            errors.append(f"claim {claim_id}: invalid status")
        if not isinstance(claim.get("scope_id"), str) or claim["scope_id"] not in scopes:
            errors.append(f"claim {claim_id}: scope_id not found")
        if not _allowed(claim.get("criticality"), CRITICALITIES):
            errors.append(f"claim {claim_id}: invalid criticality")
        status = claim.get("status")
        kind = claim.get("kind")
        value = claim.get("value")
        if status != "unresolved":
            if _allowed(kind, PARTY_KINDS | {"asset"}) and (
                    not isinstance(value, str) or not value):
                errors.append(f"claim {claim_id}: party/asset value must be nonempty text")
            if _allowed(kind, DEADLINE_KINDS | {"amount_lovelace", "amount_token_units"}) and (
                    not isinstance(value, int) or isinstance(value, bool)):
                errors.append(f"claim {claim_id}: numeric value must be integer")
            if v3 and kind == "amount_token_units" and type(value) is int and value <= 0:
                errors.append(f"claim {claim_id}: token quantity must be positive")
            if v3 and kind == "asset" and isinstance(value, str) and value.startswith("native:"):
                if parse_native_asset_id(value) is None:
                    errors.append(f"claim {claim_id}: invalid native asset id")
            if isinstance(kind, str) and kind in {
                "autonomous_execution", "ledger_history_deletion"
            } \
                    and not isinstance(value, bool):
                errors.append(f"claim {claim_id}: {kind} value must be boolean")
        evidence = claim.get("evidence")
        if evidence is not None and evidence != [] and not _evidence_valid(evidence, messages):
            errors.append(f"claim {claim_id}: invalid evidence target/span")
        if _allowed(status, SUPPORTING_EVIDENCE_STATUSES):
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
        if v2 and _allowed(kind, DEADLINE_KINDS) and _absolute_deadline_mismatch(claim):
            errors.append(f"claim {claim_id}: deadline value contradicts cited calendar date")
        if status == "derived":
            if claim.get("criticality") == "financial" and not claim.get("normalization_basis"):
                errors.append(f"claim {claim_id}: normalization_basis required")
    for claim in raw_claims:
        if not isinstance(claim, dict):
            continue
        if v3 and claim.get("kind") == "amount_token_units" and claim.get("status") in BACKING_STATUSES:
            matching_assets = [item for item in raw_claims if isinstance(item, dict)
                               and item.get("kind") == "asset"
                               and item.get("scope_id") == claim.get("scope_id")
                               and isinstance(item.get("value"), str)
                               and parse_native_asset_id(item["value"]) is not None
                               and item.get("status") in BACKING_STATUSES]
            if len(matching_assets) != 1:
                errors.append(f"claim {claim.get('claim_id')}: token quantity requires one "
                              "same-scope native asset id")
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
    supported_unsupported = any(
        isinstance(claim, dict)
        and claim.get("kind") == signal_kind and claim.get("value") is signal_value
        and _allowed(claim.get("status"), BACKING_STATUSES)
        and valid_supporting_evidence(claim, messages)
        for claim in raw_claims
        for signal_kind, signal_value in (
            UNSUPPORTED_SIGNALS_V3 if v3 else UNSUPPORTED_SIGNALS_V1
        )
    )
    if supported_unsupported and resolution != "unsupported_for_current_study" and not (
            resolution == "conflict_requires_resolution" and conflicting):
        errors.append("authoritative unsupported signal requires unsupported_for_current_study")
    if resolution == "unsupported_for_current_study" and not supported_unsupported:
        errors.append(
            "unsupported prediction requires authoritative "
            + ("v3 ledger-history-deletion" if v3 else "v1")
            + " unsupported signal"
        )
    clarifications = spec.get("required_clarifications")
    if not isinstance(clarifications, list):
        errors.append("required_clarifications must be a list")
    elif any(not ((isinstance(item, str) and item.strip()) or
                   (isinstance(item, dict) and isinstance(item.get("question"), str)
                    and item["question"].strip())) for item in clarifications):
        errors.append("required_clarifications must contain nonempty questions")
    elif _allowed(resolution, RESOLUTION_REQUIRED) and not clarifications:
        errors.append("clarification/conflict prediction requires a business question")
    if v2 and resolution == "clarification_required":
        has_unresolved_claim = any(
            isinstance(claim, dict) and claim.get("status") == "unresolved"
            for claim in raw_claims
        )
        has_unrepresented_behavior = isinstance(spec.get("unscored_observations"), list) and any(
            isinstance(item, dict) and
            item.get("reason") == ("outside_stage2b_v3_claim_taxonomy" if v3
                                   else "outside_stage2b_v2_claim_taxonomy")
            for item in spec["unscored_observations"]
        )
        if not has_unresolved_claim and not has_unrepresented_behavior:
            errors.append("clarification prediction requires an unresolved claim or "
                          "unrepresented behavior observation")
    if resolution == "accepted_interpretation":
        if any(claim.get("criticality") == "financial" and _allowed(
               claim.get("status"), UNSAFE_ACCEPT_STATUSES) for claim in raw_claims
               if isinstance(claim, dict)):
            errors.append("accepted prediction has unsafe critical claim")
        if clarifications:
            errors.append("accepted prediction still requests clarification")

    observations = spec.get("unscored_observations")
    if not isinstance(observations, list):
        errors.append("unscored_observations must be a list")
    else:
        for item in observations:
            if (not isinstance(item, dict) or not UNSCORED_OBSERVATION_FIELDS <= item.keys()
                    or not item.get("observation_id")
                    or not item.get("text") or
                    item.get("reason") not in (UNSCORED_OBSERVATION_REASONS_V3 if v3 else
                                               UNSCORED_OBSERVATION_REASONS_V2 if v2 else
                                               {UNSCORED_OBSERVATION_REASON})
                    or not _evidence_valid(item.get("source_evidence"), messages)):
                errors.append("invalid unscored_observation")
    return errors


def validate_intent_spec(spec: Any, *,
                         expected_history: list[dict[str, Any]] | None = None,
                         projected_core: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(spec, dict):
        return ["IntentSpec must be an object"]
    errors = validate_shadow_semantic_core(
        extract_core_view(spec), expected_history=expected_history)
    missing = REQUIRED_FIELDS - spec.keys()
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    extra = spec.keys() - REQUIRED_FIELDS
    if extra:
        errors.append(f"unknown top-level fields: {sorted(extra)}")
    if spec.get("schema_version") not in {SCHEMA_VERSION, SCHEMA_VERSION_V2,
                                          SCHEMA_VERSION_V3}:
        errors.append("invalid schema_version")
    scopes = {scope["scope_id"]: scope for scope in spec.get("behavior_scopes", [])
              if isinstance(scope, dict) and isinstance(scope.get("scope_id"), str)} if isinstance(
                  spec.get("behavior_scopes"), list) else {}
    claims = {claim["claim_id"]: claim for claim in spec.get("claims", [])
              if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)} if isinstance(
                  spec.get("claims"), list) else {}
    by_scope: dict[tuple[str, str], set[str]] = {}
    for claim in claims.values():
        if _allowed(claim.get("status"), ACTIVE_STATUSES):
            by_scope.setdefault((str(claim.get("kind")), str(claim.get("scope_id"))), set()).add(
                json.dumps(claim.get("value"), sort_keys=True))
    conflicting = {key for key, values in by_scope.items() if len(values) > 1}

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
                if not _backed(item["symbol"], refs, PARAMETER_CLAIM_KINDS["asset"]):
                    errors.append("asset symbol lacks matching claim_ref")
            if name == "accounts" and item.get("owner") is not None:
                if not _backed(item["owner"], refs, ACCOUNT_OWNER_KINDS):
                    errors.append("account owner lacks matching claim_ref")
            if name == "funding_relations":
                scope_id = item.get("scope_id")
                if (not isinstance(scope_id, str) or scope_id not in scopes or
                        scopes[scope_id].get("scope_type") != "transition"):
                    errors.append("funding relation scope_id must reference transition")
                if item.get("party") is not None and not _backed(
                    item["party"], refs, TRANSITION_ACTOR_KINDS["deposit"], scope_id):
                    errors.append("funding party lacks matching claim_ref")
                if item.get("account_owner") is not None and not _backed(
                    item["account_owner"], refs, ACCOUNT_OWNER_KINDS, scope_id):
                    errors.append("funding account owner lacks matching claim_ref")
                asset_id = item.get("asset_id")
                if asset_id is not None:
                    asset = assets.get(asset_id) if isinstance(asset_id, str) else None
                    if asset is None or not _backed(asset.get("symbol"), refs,
                                                    PARAMETER_CLAIM_KINDS["asset"]):
                        errors.append("funding asset_id lacks matching asset and claim_ref")
            if name == "parameters" and item.get("normalized_value") is not None:
                kinds = PARAMETER_CLAIM_KINDS.get(item.get("kind"), set())
                if not _backed(item["normalized_value"], refs, kinds):
                    errors.append("parameter value lacks matching claim_ref")
            if name == "parameters" and not _allowed(
                    item.get("kind"), PARAMETER_KINDS):
                errors.append("parameter kind is unsupported")
            if name == "states" and item.get("state_id") != "initial":
                state_id = item.get("state_id")
                kinds = STATE_CLAIM_KINDS.get(state_id) if isinstance(state_id, str) else None
                if state_id not in STATE_IDS or kinds is None:
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
                kind = item.get("kind")
                kinds = TRANSITION_ACTOR_KINDS.get(kind, set()) if isinstance(kind, str) else set()
                if not _backed(item["actor"], refs, kinds, item.get("transition_id")):
                    errors.append("transition actor lacks matching claim_ref")
            if name == "obligations_and_outcomes" and item.get("recipient") is not None:
                outcome_kind = item.get("kind")
                recipient_kinds = OUTCOME_RECIPIENT_KINDS.get(outcome_kind, set()) if isinstance(
                    outcome_kind, str) else set()
                if not _backed(item["recipient"], refs, recipient_kinds, item.get("scope_id")):
                    errors.append("outcome recipient lacks matching scoped claim_ref")
            if name == "obligations_and_outcomes" and not _allowed(
                    item.get("kind"), OUTCOME_KINDS):
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
    for name, items in sections.items():
        if not isinstance(items, list):
            continue
        id_field = {"participants": "participant_id", "assets": "asset_id",
                    "accounts": "account_id", "funding_relations": "relation_id",
                    "parameters": "parameter_id", "states": "state_id",
                    "transitions": "transition_id", "obligations_and_outcomes": "outcome_id",
                    "conflicts": "conflict_id", "assumptions_and_provenance": "assumption_id"}[name]
        ids = [item.get(id_field) for item in items if isinstance(item, dict)]
        if len(ids) != len(set(map(str, ids))):
            errors.append(f"{name}: duplicate semantic projection")
    if sections["funding_relations"]:
        errors.append("funding relation lacks explicit relational evidence in current taxonomy")
    for claim in claims.values():
        claim_id = claim.get("claim_id")
        kind = claim.get("kind")
        value = claim.get("value")
        status = claim.get("status")
        if status == "assumed":
            if not any(isinstance(item, dict) and item.get("claim_refs") == [claim_id]
                       and item.get("text") == claim.get("assumption_reason")
                       for item in (sections["assumptions_and_provenance"] or [])):
                errors.append(f"claim {claim_id}: missing assumption projection")
            continue
        if not _allowed(status, BACKING_STATUSES) or value is None:
            continue
        mandatory: list[tuple[str, str, Any]] = []
        if _allowed(kind, PARTY_KINDS):
            mandatory.append(("participants", "name", value))
        if kind == "asset":
            mandatory.append(("assets", "symbol", value))
        if _allowed(kind, ACCOUNT_OWNER_KINDS):
            mandatory.append(("accounts", "owner", value))
        if _allowed(kind, RECIPIENT_KINDS):
            mandatory.append(("obligations_and_outcomes", "recipient", value))
        if _allowed(kind, PARAMETER_CLAIM_KINDS["amount"] | DEADLINE_KINDS):
            mandatory.append(("parameters", "normalized_value", value))
        for section, field, expected in mandatory:
            if not any(isinstance(item, dict) and item.get(field) == expected
                       and isinstance(item.get("claim_refs"), list)
                       and claim_id in item["claim_refs"]
                       and (section != "obligations_and_outcomes"
                            or item.get("scope_id") == claim.get("scope_id"))
                       for item in (sections[section] or [])):
                errors.append(f"claim {claim_id}: missing mandatory {section} projection")
    for scope_id, scope in scopes.items():
        if scope.get("scope_type") == "transition" and not any(
                isinstance(item, dict) and item.get("transition_id") == scope_id
                for item in (sections["transitions"] or [])):
            errors.append(f"scope {scope_id}: missing mandatory transition projection")
    if projected_core is not None and not validate_shadow_semantic_core(
            projected_core, expected_history=expected_history):
        from research.stage2b.projector import project_intent_spec

        for field in CORE_FIELDS - {"schema_version"}:
            if spec.get(field) != projected_core.get(field):
                errors.append(f"{field}: authoritative core differs from model output")
        expected = project_intent_spec(projected_core,
                                       expected_history=expected_history).intent_spec.to_dict()
        for field in REQUIRED_FIELDS - CORE_FIELDS:
            if spec.get(field) != expected.get(field):
                errors.append(f"{field}: deterministic projection differs from semantic core")
    return errors
