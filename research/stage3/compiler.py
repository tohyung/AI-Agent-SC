"""Only explicit profile plugins may lower accepted intent to Marlowe Core V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import validate_intent_spec
from marlowe_ai_agent.marlowe_agent.marlowe_validator import validate_contract

from .models import (AccountIR, AssetIR, ClaimIR, CompilationIR, CompileResult,
                     CompileStatus, FundingRelationIR, ProfileMatchStatus, ScopeIR)
from .profiles import ProfileRegistry


CompilerPlugin = Callable[[CompilationIR], CompileResult]


class CompilerPort:
    def __init__(self, registry: ProfileRegistry | None = None,
                 plugins: dict[tuple[str, str], CompilerPlugin] | None = None) -> None:
        self.registry = registry or ProfileRegistry()
        self.plugins = plugins or {}

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        accepted = latest_artifact(artifacts, "accepted-intent")
        if accepted is None:
            return StageExecution(StageResult("compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                              StageRunStatus.NOT_EVALUATED,
                                              diagnostics=["accepted intent unavailable"]))
        spec: dict[str, Any] = accepted.payload["accepted_spec"]
        validation = validate_intent_spec(spec, expected_history=spec.get("requirement_history"))
        if validation:
            return self._outcome(accepted, CompileResult(CompileStatus.UNSUPPORTED_FEATURE,
                                                         diagnostics=tuple(validation)),
                                 StageRunStatus.UNSUPPORTED)
        match, profile, diagnostics = self.registry.match(spec)
        if match != ProfileMatchStatus.EXACT_SUPPORTED_PROFILE or profile is None:
            status = (CompileStatus.AMBIGUOUS_MAPPING if match == ProfileMatchStatus.AMBIGUOUS_PROFILE
                      else CompileStatus.UNSUPPORTED_FEATURE)
            return self._outcome(accepted, CompileResult(status, diagnostics=tuple(diagnostics)),
                                 StageRunStatus.UNSUPPORTED)
        plugin = self.plugins.get((profile.profile_id, profile.version))
        if plugin is None:
            return self._outcome(accepted, CompileResult(CompileStatus.UNSUPPORTED_FEATURE,
                                                         diagnostics=("profile compiler not configured",)),
                                 StageRunStatus.UNSUPPORTED)
        ir = CompilationIR(profile.profile_id, profile.version,
                           tuple(ClaimIR(item["claim_id"], item["kind"], item.get("value"),
                                         item["scope_id"], item["status"], dict(item))
                                 for item in spec["claims"]),
                           tuple(ScopeIR(item["scope_id"], item["scope_type"],
                                         item.get("transition_kind"), item.get("decision_id"),
                                         item.get("timeout_id"), item.get("deadline_claim_id"),
                                         dict(item)) for item in spec["behavior_scopes"]),
                           tuple(AssetIR(item["asset_id"], item["symbol"])
                                 for item in spec["assets_and_accounts"]["assets"]),
                           tuple(AccountIR(item["account_id"], item["owner"])
                                 for item in spec["assets_and_accounts"]["accounts"]),
                           tuple(FundingRelationIR(item["relation_id"], item["scope_id"],
                                                   item["party"], item["account_owner"], item["asset_id"])
                                 for item in spec["assets_and_accounts"]["funding_relations"]),
                           accepted.artifact_id)
        result = plugin(ir)
        if result.status != CompileStatus.SUPPORTED:
            return self._outcome(accepted, result, StageRunStatus.UNSUPPORTED)
        if result.contract is None:
            raise ValueError("SUPPORTED compiler result has no contract")
        structural_errors = validate_contract(result.contract)
        if structural_errors:
            return self._outcome(accepted, CompileResult(CompileStatus.AMBIGUOUS_MAPPING,
                                                         diagnostics=tuple(structural_errors)),
                                 StageRunStatus.FAILED)
        mapped = {(item.get("source_kind"), item.get("source_id"))
                  for item in result.mapping_evidence if item.get("ast_path")}
        expected = {("claim", item.claim_id) for item in ir.claims if item.status != "superseded"}
        expected |= {("scope", item.scope_id) for item in ir.scopes}
        for section, id_field in (("participants", "participant_id"), ("parameters", "parameter_id"),
                                  ("states", "state_id"), ("transitions", "transition_id"),
                                  ("obligations_and_outcomes", "outcome_id")):
            expected |= {(section, item[id_field]) for item in spec[section]}
        for section, id_field in (("assets", "asset_id"), ("accounts", "account_id"),
                                  ("funding_relations", "relation_id")):
            expected |= {(section, item[id_field])
                         for item in spec["assets_and_accounts"][section]}
        if not expected <= mapped:
            return self._outcome(accepted, CompileResult(
                CompileStatus.AMBIGUOUS_MAPPING,
                diagnostics=(f"missing mapping evidence: {sorted(expected - mapped)}",)),
                StageRunStatus.UNSUPPORTED)
        contract = ArtifactEnvelope("contract-candidate", "core-v1", "compile",
                                    ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                    AuthorityLevel.DETERMINISTIC_COMPILER_CANDIDATE,
                                    {"contract": result.contract, "source_intent_id": accepted.artifact_id,
                                     "profile": profile.to_dict(),
                                     "mapping_evidence": list(result.mapping_evidence)})
        outcome = self._outcome(accepted, result, StageRunStatus.SUCCEEDED)
        outcome.artifacts.append(contract)
        return outcome

    @staticmethod
    def _outcome(accepted: ArtifactEnvelope, result: CompileResult,
                 status: StageRunStatus) -> StageExecution:
        artifact = ArtifactEnvelope("compile-result", "v1", "compile",
                                    ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                    AuthorityLevel.NO_AUTHORITY, result.to_dict())
        return StageExecution(StageResult(
            "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED, status,
            semantic_status=result.status.value, input_artifacts=[accepted.artifact_id],
            diagnostics=list(result.diagnostics),
            limitations=["structural validity is not intent or ledger validity"]), [artifact])
