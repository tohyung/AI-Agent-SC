"""Exact feature matching; unknown and unrepresented fields never disappear."""

from __future__ import annotations

from typing import Any

from .models import ProfileMatchStatus, SupportedProfile


class ProfileRegistry:
    def __init__(self, profiles: list[SupportedProfile] | None = None) -> None:
        self.profiles = list(profiles or [])

    def match(self, spec: dict[str, Any]) -> tuple[ProfileMatchStatus, SupportedProfile | None, list[str]]:
        matches: list[SupportedProfile] = []
        diagnostics: list[str] = []
        for profile in self.profiles:
            errors = profile_mismatches(spec, profile)
            if not errors:
                matches.append(profile)
            else:
                diagnostics.extend(f"{profile.profile_id}: {error}" for error in errors)
        if len(matches) == 1:
            return ProfileMatchStatus.EXACT_SUPPORTED_PROFILE, matches[0], []
        if len(matches) > 1:
            return ProfileMatchStatus.AMBIGUOUS_PROFILE, None, ["multiple exact profiles match"]
        return ProfileMatchStatus.UNSUPPORTED_PROFILE, None, diagnostics or ["no profile registered"]


def profile_mismatches(spec: dict[str, Any], profile: SupportedProfile) -> list[str]:
    errors: list[str] = []
    if spec.get("schema_version") != profile.intent_schema_version:
        errors.append("intent schema version unsupported")
    for claim in spec.get("claims", []):
        if claim.get("kind") not in profile.claim_kinds:
            errors.append(f"claim kind {claim.get('kind')} unsupported")
        if claim.get("status") not in {"explicit", "derived", "user_confirmed", "superseded"}:
            errors.append(f"claim {claim.get('claim_id')} unresolved or unsupported")
    for scope in spec.get("behavior_scopes", []):
        kind = scope.get("scope_type")
        if kind not in profile.scope_types:
            errors.append(f"scope type {kind} unsupported")
        if kind == "transition" and scope.get("transition_kind") not in profile.transition_kinds:
            errors.append(f"transition {scope.get('transition_kind')} unsupported")
        if kind == "branch" and not profile.supports_branches:
            errors.append("branch unsupported")
        if kind == "timeout" and not profile.supports_timeouts:
            errors.append("timeout unsupported")
    accounts = spec.get("assets_and_accounts", {})
    if not isinstance(accounts, dict):
        return errors + ["assets_and_accounts invalid"]
    if accounts.get("funding_relations") and not profile.supports_funding_relations:
        errors.append("funding relations unsupported")
    if any(scope.get("transition_kind") == "notify" for scope in spec.get("behavior_scopes", [])):
        if not profile.supports_observations:
            errors.append("Notify observation unsupported")
    if spec.get("unscored_observations"):
        errors.append("unscored observations cannot be compiled")
    if spec.get("required_clarifications") or spec.get("conflicts") or spec.get("assumptions_and_provenance"):
        errors.append("open clarification, conflict or assumption cannot be compiled")
    for asset in accounts.get("assets", []):
        if asset.get("symbol") not in profile.supported_assets:
            errors.append(f"asset {asset.get('symbol')} unsupported")
    return errors
