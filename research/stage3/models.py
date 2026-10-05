"""Stage 3 outcomes are independent of implementation lifecycle and run status."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ProfileMatchStatus(StrEnum):
    EXACT_SUPPORTED_PROFILE = "EXACT_SUPPORTED_PROFILE"
    AMBIGUOUS_PROFILE = "AMBIGUOUS_PROFILE"
    UNSUPPORTED_PROFILE = "UNSUPPORTED_PROFILE"


class CompileStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"
    AMBIGUOUS_MAPPING = "AMBIGUOUS_MAPPING"


class CompilerAuthorityStatus(StrEnum):
    CANDIDATE_ONLY = "CANDIDATE_ONLY"
    AUTHORIZED_FOR_PROFILE = "AUTHORIZED_FOR_PROFILE"
    REVOKED = "REVOKED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class SupportedProfile:
    profile_id: str
    version: str
    compiler_id: str
    compiler_version: str
    intent_schema_version: str
    claim_kinds: frozenset[str]
    scope_types: frozenset[str]
    transition_kinds: frozenset[str]
    supported_assets: frozenset[str]
    supports_funding_relations: bool = False
    supports_observations: bool = False
    supports_branches: bool = False
    supports_timeouts: bool = False
    transition_counts: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {key: sorted(value) if isinstance(value, frozenset) else value
                   for key, value in vars(self).items() if key != "transition_counts"}
        payload["transition_counts"] = [
            {"transition_kind": kind, "count": count} for kind, count in self.transition_counts]
        return payload


@dataclass(frozen=True)
class ClaimIR:
    claim_id: str
    kind: str
    value: Any
    scope_id: str
    status: str
    source: dict[str, Any]


@dataclass(frozen=True)
class ScopeIR:
    scope_id: str
    scope_type: str
    transition_kind: str | None
    decision_id: str | None
    timeout_id: str | None
    deadline_claim_id: str | None
    source: dict[str, Any]


@dataclass(frozen=True)
class AssetIR:
    asset_id: str
    symbol: str
    source: dict[str, Any]


@dataclass(frozen=True)
class AccountIR:
    account_id: str
    owner: str
    source: dict[str, Any]


@dataclass(frozen=True)
class FundingRelationIR:
    relation_id: str
    scope_id: str
    party: str
    account_owner: str
    asset_id: str
    source: dict[str, Any]


@dataclass(frozen=True)
class ParticipantIR:
    participant_id: str
    name: str
    claim_refs: tuple[str, ...]
    source: dict[str, Any]


@dataclass(frozen=True)
class ParameterIR:
    parameter_id: str
    source: dict[str, Any]


@dataclass(frozen=True)
class StateIR:
    state_id: str
    source: dict[str, Any]


@dataclass(frozen=True)
class TransitionIR:
    transition_id: str
    source: dict[str, Any]


@dataclass(frozen=True)
class OutcomeIR:
    outcome_id: str
    source: dict[str, Any]


@dataclass(frozen=True)
class CompilationIR:
    profile_id: str
    profile_version: str
    claims: tuple[ClaimIR, ...]
    scopes: tuple[ScopeIR, ...]
    participants: tuple[ParticipantIR, ...]
    assets: tuple[AssetIR, ...]
    accounts: tuple[AccountIR, ...]
    funding_relations: tuple[FundingRelationIR, ...]
    parameters: tuple[ParameterIR, ...]
    states: tuple[StateIR, ...]
    transitions: tuple[TransitionIR, ...]
    outcomes: tuple[OutcomeIR, ...]
    source_intent_id: str

    def to_dict(self) -> dict[str, Any]:
        def items(values: tuple[Any, ...]) -> list[dict[str, Any]]:
            return [{key: list(value) if isinstance(value, tuple) else value
                     for key, value in vars(item).items()} for item in values]

        return {"profile_id": self.profile_id, "profile_version": self.profile_version,
                "claims": items(self.claims), "scopes": items(self.scopes),
                "participants": items(self.participants), "assets": items(self.assets),
                "accounts": items(self.accounts),
                "funding_relations": items(self.funding_relations),
                "parameters": items(self.parameters), "states": items(self.states),
                "transitions": items(self.transitions), "outcomes": items(self.outcomes),
                "source_intent_id": self.source_intent_id}


@dataclass(frozen=True)
class CompileResult:
    status: CompileStatus
    contract: Any = None
    mapping_evidence: tuple[dict[str, str], ...] = ()
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status.value, "contract": self.contract,
                "mapping_evidence": list(self.mapping_evidence),
                "diagnostics": list(self.diagnostics)}


@dataclass(frozen=True)
class CompilerAuthorityDecision:
    status: CompilerAuthorityStatus
    profile_id: str
    profile_version: str
    compiler_id: str
    compiler_version: str
    intent_schema_version: str
    core_format: str
    reference_identity: str
    evidence_policy_version: str
    evidence_ids: tuple[str, ...] = ()
    reviewer_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**vars(self), "status": self.status.value,
                "evidence_ids": list(self.evidence_ids)}
