"""LLM contract candidate generation from immutable, accepted intent."""

from __future__ import annotations

import json
from typing import Any

from research.marlowe_core.marlowe_validator import (
    describe_marlowe_grammar, validate_contract,
)
from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import validate_intent_spec
from research.stage2b.model_errors import sanitized_model_error


def _noncanonical_ada_paths(contract: Any, path: str = "$") -> list[str]:
    if isinstance(contract, list):
        return [item for index, value in enumerate(contract)
                for item in _noncanonical_ada_paths(value, f"{path}[{index}]")]
    if not isinstance(contract, dict):
        return []
    invalid = []
    for key, value in contract.items():
        child_path = f"{path}.{key}"
        if key in {"token", "of_token"} and isinstance(value, dict):
            if value != {"currency_symbol": "", "token_name": ""}:
                invalid.append(child_path)
        else:
            invalid.extend(_noncanonical_ada_paths(value, child_path))
    return invalid


class LLMContractGeneratorPort:
    """Produce an untrusted AST candidate; verification owns all authority."""

    def __init__(self, model: Any | None = None) -> None:
        self.model = model

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        accepted = latest_artifact(artifacts, "accepted-intent")
        if accepted is None or self.model is None:
            return StageExecution(StageResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.NOT_EVALUATED,
                diagnostics=["accepted intent or contract model unavailable"],
            ))
        simulated = accepted.payload.get("simulation_only") is True
        simulation_allowed = context.options.get("allow_simulated_intent") is True
        if ((simulated and (not simulation_allowed
                            or accepted.authority_level != AuthorityLevel.NO_AUTHORITY))
                or (not simulated and
                    accepted.authority_level != AuthorityLevel.USER_ACCEPTED_INTENT)):
            return StageExecution(StageResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.BLOCKED, input_artifacts=[accepted.artifact_id],
                diagnostics=["LLM contract generation requires user-accepted intent "
                             "or explicit simulation-only research mode"],
            ))
        spec = accepted.payload["accepted_spec"]
        errors = validate_intent_spec(spec, expected_history=spec.get("requirement_history"))
        if errors:
            return StageExecution(StageResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.BLOCKED, input_artifacts=[accepted.artifact_id],
                diagnostics=errors,
            ))
        feedback = context.options.get("generation_feedback", [])
        if not isinstance(feedback, list) or any(not isinstance(item, str) for item in feedback):
            raise ValueError("generation_feedback must be a list of strings")
        system = (
            "Generate one canonical Marlowe Core V1 JSON contract from the accepted IntentSpec. "
            "Never alter parties, amounts, assets, accounts, branch outcomes or deadlines. "
            "Never invent missing business facts or turn an unsupported behavior into a different one. "
            "Return JSON with contract, mapping_evidence and reasoning_narrative. "
            "Each mapping item has source_kind ('claim' or 'scope'), source_id and ast_path. "
            "An ast_path must start at root or $ and identify an existing location in the returned AST. "
            "Do not claim that the AST is verified; all mappings will be checked independently. "
            "Use Vietnamese for the short reasoning_narrative, not raw chain-of-thought. "
            "For ADA, every of_token/token object must be exactly "
            '{"currency_symbol":"","token_name":""}; never use token_name="ADA". '
            "Return JSON only.\n" + describe_marlowe_grammar()
        )
        user = json.dumps({
            "accepted_intent": spec,
            "accepted_intent_id": accepted.artifact_id,
            "generation_feedback": feedback,
        }, ensure_ascii=False)
        try:
            output = self.model.generate(system, user)
        except (RuntimeError, ValueError) as exc:
            safe_error = sanitized_model_error(exc)
            return StageExecution(StageResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.FAILED, semantic_status="MODEL_ERROR",
                input_artifacts=[accepted.artifact_id],
                diagnostics=[f"contract model failed: {safe_error['code']}"],
                safe_error=safe_error,
            ))
        if not isinstance(output, dict):
            diagnostics = ["contract model did not return a JSON object"]
        elif not isinstance(output.get("mapping_evidence"), list):
            diagnostics = ["mapping_evidence must be a list"]
        elif any(not isinstance(item, dict) or set(item) != {
                "source_kind", "source_id", "ast_path"} or not all(
                    isinstance(value, str) and value for value in item.values())
                 for item in output["mapping_evidence"]):
            diagnostics = ["mapping_evidence items must contain source_kind, source_id and ast_path"]
        else:
            diagnostics = validate_contract(output.get("contract"))
            assets = [claim.get("value") for claim in spec.get("claims", [])
                      if claim.get("kind") == "asset"
                      and claim.get("status") != "superseded"]
            if not diagnostics and assets and set(assets) == {"ADA"}:
                diagnostics.extend(
                    f"{path}: accepted intent has only ADA; use empty currency_symbol "
                    "and empty token_name"
                    for path in _noncanonical_ada_paths(output["contract"]))
        if diagnostics:
            return StageExecution(StageResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.FAILED, semantic_status="INVALID_CONTRACT_CANDIDATE",
                input_artifacts=[accepted.artifact_id], diagnostics=diagnostics,
            ))
        candidate = ArtifactEnvelope(
            "contract-candidate", "core-v1", "compile",
            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            AuthorityLevel.MODEL_CANDIDATE,
            {"contract": output["contract"], "source_intent_id": accepted.artifact_id,
             "mapping_evidence": output["mapping_evidence"],
             "generation_mode": ("llm_from_simulated_intent_v1" if simulated else
                                 "llm_from_accepted_intent_v1"),
             "simulation_only": simulated,
             "reasoning_narrative": str(output.get("reasoning_narrative") or "")[:700]},
        )
        return StageExecution(StageResult(
            "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StageRunStatus.SUCCEEDED, semantic_status="CANDIDATE_GENERATED",
            input_artifacts=[accepted.artifact_id],
            authority_level=AuthorityLevel.MODEL_CANDIDATE,
            limitations=["structural validity and model mapping claims are not intent conformance"],
        ), [candidate])
