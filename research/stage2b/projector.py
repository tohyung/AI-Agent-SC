"""Conservative, deterministic projection from Stage 2B semantic authority."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from research.stage2b.intent_spec import (
    BACKING_STATUSES, DEADLINE_KINDS, IntentSpec,
    OUTCOME_RECIPIENT_KINDS, PARTY_KINDS, SCHEMA_VERSION, SCHEMA_VERSION_V2,
    CORE_SCHEMA_VERSION_V2,
    TRANSITION_ACTOR_KINDS, TRANSITION_DEADLINE_KINDS,
    validate_shadow_semantic_core,
)


PARAMETER_KINDS = {"amount_lovelace": "amount", "asset": "asset",
                   **{kind: "deadline" for kind in DEADLINE_KINDS}}
UNITS = {"amount_lovelace": "lovelace", **{kind: "posix_ms" for kind in DEADLINE_KINDS}}
OUTCOMES = {kind: outcome for outcome, kinds in OUTCOME_RECIPIENT_KINDS.items()
            for kind in kinds}
CATEGORIES = ("participant", "asset", "account", "parameter", "transition",
              "transition_actor", "deadline", "outcome", "conflict", "assumption")


@dataclass
class ProjectionResult:
    intent_spec: IntentSpec
    projection_diagnostics: dict[str, Any]


def classify_projection(core_errors: list[str], full_errors: list[str],
                        diagnostics: dict[str, Any]) -> str:
    if core_errors:
        return "CORE_INVALID"
    if full_errors or not diagnostics.get("complete", False):
        return "PROJECTOR_BUG"
    return "PASS"


def _identity(value: Any) -> str:
    """Hex-encoded canonical JSON is injective for the supported JSON identities."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8").hex()


def _backed(claim: dict[str, Any]) -> bool:
    return claim.get("status") in BACKING_STATUSES and claim.get("value") is not None


def _new_spec(core: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": (SCHEMA_VERSION_V2 if core.get("schema_version") == CORE_SCHEMA_VERSION_V2
                           else SCHEMA_VERSION),
        "requirement_history": core.get("requirement_history"),
        "participants": [],
        "assets_and_accounts": {"assets": [], "accounts": [], "funding_relations": []},
        "parameters": [], "states": [{"state_id": "initial", "claim_refs": []}],
        "transitions": [], "obligations_and_outcomes": [],
        "behavior_scopes": core.get("behavior_scopes"),
        "claims": core.get("claims"),
        "required_clarifications": core.get("required_clarifications"),
        "conflicts": [], "assumptions_and_provenance": [],
        "unscored_observations": core.get("unscored_observations"),
        "predicted_resolution": core.get("predicted_resolution"),
    }


def project_intent_spec(core: dict[str, Any] | Any, *,
                        expected_history: list[dict[str, Any]] | None = None) -> ProjectionResult:
    source = core.to_dict() if hasattr(core, "to_dict") else core
    if not isinstance(source, dict):
        raise TypeError("semantic core must be an object")
    errors = validate_shadow_semantic_core(source, expected_history=expected_history)
    spec = _new_spec(source)
    facts: list[dict[str, Any]] = []

    def record(category: str, source_id: str, *, mandatory: bool, projected: bool,
               reason: str | None = None) -> None:
        facts.append({"category": category, "source_id": source_id,
                      "mandatory": mandatory, "projected": projected,
                      "not_projected_reason": reason})

    if errors:
        return ProjectionResult(IntentSpec(spec), {
            "core_status": "invalid", "core_validation_errors": errors,
            "facts": [], "coverage": {category: {"eligible_count": 0,
                "projected_count": 0, "omitted_count": 0} for category in CATEGORIES},
            "mandatory_eligible_count": 0, "mandatory_projected_count": 0,
            "complete": False,
        })

    claims = sorted(source["claims"], key=lambda item: item["claim_id"])
    scopes = sorted(source["behavior_scopes"], key=lambda item: item["scope_id"])
    backed = [claim for claim in claims if _backed(claim)]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for claim in backed:
        grouped.setdefault((claim["kind"], claim["scope_id"]), []).append(claim)

    parties: dict[str, list[str]] = {}
    assets: dict[str, list[str]] = {}
    accounts: dict[tuple[str, str], list[str]] = {}
    outcomes: dict[tuple[str, str, str], list[str]] = {}
    for claim in backed:
        kind, value, claim_id = claim["kind"], claim["value"], claim["claim_id"]
        if kind in PARTY_KINDS and isinstance(value, str):
            parties.setdefault(value, []).append(claim_id)
            record("participant", claim_id, mandatory=True, projected=True)
        if kind == "asset" and isinstance(value, str):
            assets.setdefault(value, []).append(claim_id)
            record("asset", claim_id, mandatory=True, projected=True)
        if kind in {"destination_account_owner", "payment_source_account_owner"} and isinstance(value, str):
            accounts.setdefault((kind, value), []).append(claim_id)
            record("account", claim_id, mandatory=True, projected=True)
        if kind in PARAMETER_KINDS and kind != "asset":
            parameter_id = f"parameter:{claim_id}"
            spec["parameters"].append({"parameter_id": parameter_id,
                "kind": PARAMETER_KINDS[kind], "normalized_value": value,
                "unit": UNITS[kind], "claim_refs": [claim_id]})
            record("parameter", claim_id, mandatory=True, projected=True)
        if kind in OUTCOMES and isinstance(value, str):
            outcomes.setdefault((OUTCOMES[kind], claim["scope_id"], value), []).append(claim_id)
            record("outcome", claim_id, mandatory=True, projected=True)

    spec["participants"] = [{"participant_id": f"participant:{_identity(value)}",
                             "name": value, "claim_refs": sorted(set(refs))}
                            for value, refs in sorted(parties.items())]
    spec["assets_and_accounts"]["assets"] = [
        {"asset_id": f"asset:{_identity(value)}", "symbol": value,
         "claim_refs": sorted(set(refs))} for value, refs in sorted(assets.items())]
    spec["assets_and_accounts"]["accounts"] = [
        {"account_id": f"account:{kind}:{_identity(value)}", "owner": value,
         "claim_refs": sorted(set(refs))}
        for (kind, value), refs in sorted(accounts.items())]
    spec["obligations_and_outcomes"] = [
        {"outcome_id": f"outcome:{min(refs)}", "kind": kind,
         "recipient": value, "scope_id": scope_id,
         "claim_refs": sorted(set(refs))}
        for (kind, scope_id, value), refs in sorted(outcomes.items())]

    for scope in scopes:
        if scope["scope_type"] != "transition":
            continue
        scope_id, kind = scope["scope_id"], scope["transition_kind"]
        actor = None
        actor_refs: list[str] = []
        actor_kinds = TRANSITION_ACTOR_KINDS.get(kind, set())
        actor_claims = [claim for actor_kind in actor_kinds
                        for claim in grouped.get((actor_kind, scope_id), [])]
        actor_values = {_identity(claim["value"]) for claim in actor_claims}
        conflicted_actors = [claim for claim in claims
                             if claim["kind"] in actor_kinds and claim["scope_id"] == scope_id
                             and claim["status"] == "conflicted"]
        if len(actor_values) == 1:
            actor = actor_claims[0]["value"]
            actor_refs = sorted({claim["claim_id"] for claim in actor_claims})
            record("transition_actor", scope_id, mandatory=False, projected=True)
        elif actor_claims or conflicted_actors:
            record("transition_actor", scope_id, mandatory=False, projected=False,
                   reason="ambiguous_actor")
        else:
            record("transition_actor", scope_id, mandatory=False, projected=False,
                   reason="no_compatible_same_scope_actor")
        deadline_claims = [claim for deadline_kind in TRANSITION_DEADLINE_KINDS.get(kind, set())
                           for claim in grouped.get((deadline_kind, scope_id), [])]
        deadline_id = None
        if len(deadline_claims) == 1:
            deadline_id = f"parameter:{deadline_claims[0]['claim_id']}"
            record("deadline", scope_id, mandatory=False, projected=True)
        elif deadline_claims:
            record("deadline", scope_id, mandatory=False, projected=False,
                   reason="ambiguous_deadline")
        else:
            record("deadline", scope_id, mandatory=False, projected=False,
                   reason="no_compatible_same_scope_deadline")
        spec["transitions"].append({"transition_id": scope_id, "kind": kind,
            "actor": actor, "deadline_parameter_id": deadline_id,
            "transaction_submitter": None,
            "claim_refs": sorted(set(actor_refs + ([deadline_claims[0]["claim_id"]]
                                  if deadline_id is not None else [])))})
        record("transition", scope_id, mandatory=True, projected=True)
        if kind == "deposit":
            record("funding_relation", scope_id, mandatory=False, projected=False,
                   reason="insufficient_relational_evidence")

    conflicts: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for claim in claims:
        if claim["status"] == "conflicted":
            conflicts.setdefault((claim["kind"], claim["scope_id"]), []).append(claim)
        if claim["status"] == "assumed":
            spec["assumptions_and_provenance"].append({
                "assumption_id": f"assumption:{claim['claim_id']}",
                "text": claim["assumption_reason"], "claim_refs": [claim["claim_id"]]})
            record("assumption", claim["claim_id"], mandatory=True, projected=True)
    for (kind, scope_id), group in sorted(conflicts.items()):
        if len({_identity(claim["value"]) for claim in group}) < 2:
            continue
        spec["conflicts"].append({"conflict_id": f"conflict:{kind}:{scope_id}",
            "kind": kind, "scope_id": scope_id,
            "claim_refs": sorted({claim["claim_id"] for claim in group})})
        record("conflict", f"{kind}:{scope_id}", mandatory=True, projected=True)

    for key in ("participants", "parameters", "transitions", "obligations_and_outcomes",
                "conflicts", "assumptions_and_provenance"):
        id_field = {"participants": "participant_id", "parameters": "parameter_id",
                    "transitions": "transition_id", "obligations_and_outcomes": "outcome_id",
                    "conflicts": "conflict_id",
                    "assumptions_and_provenance": "assumption_id"}[key]
        spec[key].sort(key=lambda item: item[id_field])
    for key, id_field in (("assets", "asset_id"), ("accounts", "account_id")):
        spec["assets_and_accounts"][key].sort(key=lambda item: item[id_field])
    facts.sort(key=lambda item: (item["category"], item["source_id"]))
    coverage = {category: {"eligible_count": sum(f["category"] == category for f in facts),
                           "projected_count": sum(f["category"] == category and f["projected"]
                                                  for f in facts),
                           "omitted_count": sum(f["category"] == category and not f["projected"]
                                                for f in facts)} for category in CATEGORIES}
    mandatory = [fact for fact in facts if fact["mandatory"]]
    return ProjectionResult(IntentSpec(spec), {
        "core_status": "valid", "facts": facts, "coverage": coverage,
        "mandatory_eligible_count": len(mandatory),
        "mandatory_projected_count": sum(fact["projected"] for fact in mandatory),
        "complete": all(fact["projected"] for fact in mandatory),
    })
