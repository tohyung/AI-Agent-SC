"""Profile authority requires explicit scoped promotion; default is candidate-only."""

from __future__ import annotations

from typing import Protocol

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus

from .models import CompilerAuthorityDecision, CompilerAuthorityStatus


def decision_matches(decision: CompilerAuthorityDecision, profile: dict,
                     reference_identity: str, policy_version: str) -> bool:
    return (decision.status == CompilerAuthorityStatus.AUTHORIZED_FOR_PROFILE
            and decision.profile_id == profile["profile_id"]
            and decision.profile_version == profile["version"]
            and decision.compiler_id == profile["compiler_id"]
            and decision.compiler_version == profile["compiler_version"]
            and decision.intent_schema_version == profile["intent_schema_version"]
            and decision.core_format == "marlowe-core-v1"
            and decision.reference_identity == reference_identity
            and decision.evidence_policy_version == policy_version
            and bool(decision.evidence_ids) and bool(decision.reviewer_id))


class CompilerAuthorityPort:
    def __init__(self, promotion_policy: PromotionPolicy | None = None) -> None:
        self.promotion_policy = promotion_policy

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        contract = latest_artifact(artifacts, "contract-candidate")
        comparison = latest_artifact(artifacts, "reference-comparison")
        if contract is None:
            return StageExecution(StageResult("compiler_authority", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                              StageRunStatus.NOT_EVALUATED,
                                              diagnostics=["compiled contract unavailable"]))
        profile = contract.payload["profile"]
        raw_decision = context.options.get("compiler_authority_decision")
        decision = raw_decision if isinstance(raw_decision, CompilerAuthorityDecision) else None
        raw_configured_identity = context.options.get("reference_identity")
        configured_identity = (str(raw_configured_identity)
                               if raw_configured_identity is not None else None)
        comparison_matches_contract = (comparison is not None
                                       and comparison.payload.get("contract_artifact_id")
                                       == contract.artifact_id)
        observed_identity = (comparison.payload.get("reference_identity")
                             if comparison_matches_contract else None)
        reported_identity = observed_identity or configured_identity or "unavailable"
        policy_version = str(context.options.get("evidence_policy_version", "v1"))
        authorized = (self.promotion_policy is not None
                      and decision is not None and bool(configured_identity)
                      and contract.payload.get("simulation_only") is not True
                      and comparison_matches_contract
                      and comparison.payload.get("verdict") == "SATISFIED"
                      and observed_identity == configured_identity
                      and decision_matches(decision, profile, configured_identity, policy_version)
                      and self.promotion_policy.authorize(decision, contract, comparison))
        status = CompilerAuthorityStatus.AUTHORIZED_FOR_PROFILE if authorized else CompilerAuthorityStatus.CANDIDATE_ONLY
        authority = AuthorityLevel.PROFILE_COMPILER_AUTHORITY if authorized else AuthorityLevel.NO_AUTHORITY
        payload = {"status": status.value, "profile": profile,
                   "reference_identity": reported_identity,
                   "evidence_policy_version": policy_version,
                   "decision": decision.to_dict() if authorized else None,
                   "scope_limit": "deterministic profile mapping only; no Stage 4/5 or ledger authority"}
        output = ArtifactEnvelope("compiler-authority-decision", "v1", "compiler_authority",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED, authority, payload)
        return StageExecution(StageResult(
            "compiler_authority", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StageRunStatus.SUCCEEDED, semantic_status=status.value,
            input_artifacts=[contract.artifact_id] + ([comparison.artifact_id] if comparison else []),
            authority_level=authority,
            limitations=[payload["scope_limit"]]), [output])


class PromotionPolicy(Protocol):
    def authorize(self, decision: CompilerAuthorityDecision, contract: ArtifactEnvelope,
                  comparison: ArtifactEnvelope) -> bool: ...
