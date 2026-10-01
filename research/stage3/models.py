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

    def to_dict(self) -> dict[str, Any]:
        return {key: sorted(value) if isinstance(value, frozenset) else value
                for key, value in vars(self).items()}


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


@dataclass(frozen=True)
class AccountIR:
    account_id: str
    owner: str


@dataclass(frozen=True)
class FundingRelationIR:
    relation_id: str
    scope_id: str
    party: str
    account_owner: str
    asset_id: str


@dataclass(frozen=True)
class CompilationIR:
    profile_id: str
    profile_version: str
    claims: tuple[ClaimIR, ...]
    scopes: tuple[ScopeIR, ...]
    assets: tuple[AssetIR, ...]
    accounts: tuple[AccountIR, ...]
    funding_relations: tuple[FundingRelationIR, ...]
    source_intent_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"profile_id": self.profile_id, "profile_version": self.profile_version,
                "claims": [vars(item) for item in self.claims],
                "scopes": [vars(item) for item in self.scopes],
                "assets": [vars(item) for item in self.assets],
                "accounts": [vars(item) for item in self.accounts],
                "funding_relations": [vars(item) for item in self.funding_relations],
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
