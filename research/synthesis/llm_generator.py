"""LLM contract candidate generation from immutable, accepted intent."""

from __future__ import annotations

import json
from typing import Any

from research.analysis.marlowe_validator import (
    describe_marlowe_grammar, validate_contract,
)
from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.models import StepResult
from research.orchestration.ports import StepContext, StepExecution, latest_artifact
from research.orchestration.status import AuthorityLevel, ImplementationStatus, StepRunStatus
from research.formalization.intent_spec import validate_intent_spec
from research.formalization.model_errors import sanitized_model_error


def _named_address_paths(contract: Any, names: set[str], path: str = "$") -> list[str]:
    """Parties written as {"address": <participant name>}: intent participants are roles."""
    if isinstance(contract, list):
        return [item for index, value in enumerate(contract)
                for item in _named_address_paths(value, names, f"{path}[{index}]")]
    if not isinstance(contract, dict):
        return []
    if set(contract) == {"address"} and contract["address"] in names:
        return [path]
    return [item for key, value in contract.items()
            for item in _named_address_paths(value, names, f"{path}.{key}")]


def _value_at(contract: Any, path: str) -> Any:
    node = contract
    for part in path.replace("]", "").replace("[", ".").split(".")[1:]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node["address"]


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

    def execute(self, artifacts: list[ArtifactEnvelope], context: StepContext) -> StepExecution:
        accepted = latest_artifact(artifacts, "accepted-intent")
        if accepted is None or self.model is None:
            return StepExecution(StepResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.NOT_EVALUATED,
                diagnostics=["accepted intent or contract model unavailable"],
            ))
        simulated = accepted.payload.get("simulation_only") is True
        simulation_allowed = context.options.get("allow_simulated_intent") is True
        if ((simulated and (not simulation_allowed
                            or accepted.authority_level != AuthorityLevel.NO_AUTHORITY))
                or (not simulated and
                    accepted.authority_level != AuthorityLevel.USER_ACCEPTED_INTENT)):
            return StepExecution(StepResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.BLOCKED, input_artifacts=[accepted.artifact_id],
                diagnostics=["LLM contract generation requires user-accepted intent "
                             "or explicit simulation-only research mode"],
            ))
        spec = accepted.payload["accepted_spec"]
        errors = validate_intent_spec(spec, expected_history=spec.get("requirement_history"))
        if errors:
            return StepExecution(StepResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.BLOCKED, input_artifacts=[accepted.artifact_id],
                diagnostics=errors,
            ))
        feedback = context.options.get("generation_feedback", [])
        if not isinstance(feedback, list) or any(not isinstance(item, str) for item in feedback):
            raise ValueError("generation_feedback must be a list of strings")
        system = (
            "Generate one canonical Marlowe Core V1 JSON contract from the accepted IntentSpec. "
            "Never alter parties, amounts, assets, accounts, branch outcomes or deadlines. "
            "Conserve funds per account and asset on every path. If two contributors "
            "deposit 47.5 ADA each and a recipient is owed 95 ADA in total, pay "
            "47.5 ADA from each funded account; never pay 95 ADA from each account. "
            "A refund can spend only the amount that was actually deposited in "
            "that account on that path. Do not invent a deposit to fund a payout. "
            "Never invent missing business facts or turn an unsupported behavior into a different one. "
            "Every participant of the IntentSpec is a role: write each party, account, payee and "
            'choice owner as {"role_token":"<participant name>"}, never as an address. '
            "Return JSON with contract, mapping_evidence and reasoning_narrative. "
            "Each mapping item has source_kind ('claim' or 'scope'), source_id and ast_path. "
            "An ast_path must start at root or $ and identify an existing location in the returned AST. "
            "Do not claim that the AST is verified; all mappings will be checked independently. "
            "Use Vietnamese for the short reasoning_narrative, not raw chain-of-thought. "
            "For ADA, every of_token/token object must be exactly "
            '{"currency_symbol":"","token_name":""}; never use token_name="ADA". '
            "Marlowe Constant Value is a bare JSON integer, e.g. deposits: 1 or "
            'pay: 1, never {"constant": 1}. '
            "Pay is one Contract object with exactly pay, from_account, to, token, "
            'then at the same level, e.g. {"pay":1,"from_account":{"role_token":"A"},'
            '"to":{"party":{"role_token":"B"}},'
            '"token":{"currency_symbol":"","token_name":""},"then":"close"}. '
            'Never wrap that Contract in {"pay": {...}}. '
            "A payment scheduled solely by a deadline needs no user input. "
            "Encode it on When.timeout_continuation at that deadline; for two "
            "scheduled payments, the first timeout continuation pays the first "
            "amount and continues to a second When whose timeout continuation "
            "pays the remainder. Never put a scheduled payment behind Notify, "
            "because reaching a timeout takes timeout_continuation and does not "
            "match a Notify case. Do not replace a source-stated approval or "
            "other required input with an automatic timeout payout. "
            "For a payment_release_time_ms claim, the time is an EARLIEST allowed "
            "release time, not a deadline/latest time. Never put an actionable "
            "payment case in a When whose timeout is that release time: cases are "
            "available before timeout and its timeout continuation runs at/after "
            "timeout. Instead use a time gate with an empty cases array and timeout "
            "equal to the release time; its timeout_continuation must lead to the "
            "post-release payment/action state. Any participant action required "
            "by the intent must be reachable only after this gate. Keep deposit, "
            "choice, and other latest deadlines as ordinary upper-bound When "
            "timeouts with the source-grounded timeout continuation. "
            "Return JSON only.\n" + describe_marlowe_grammar()
        )
        user = json.dumps({
            "accepted_intent": spec,
            "accepted_intent_id": accepted.artifact_id,
            "generation_feedback": feedback,
        }, ensure_ascii=False)
        call_start = getattr(self.model, "llm_calls", None)

        def usage() -> dict[str, int | None]:
            call_end = getattr(self.model, "llm_calls", None)
            return {"physical_calls": (call_end - call_start
                                       if type(call_start) is int and type(call_end) is int
                                       else None)}

        try:
            output = self.model.generate(system, user)
        except (RuntimeError, ValueError) as exc:
            safe_error = sanitized_model_error(exc)
            return StepExecution(StepResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, semantic_status="MODEL_ERROR",
                input_artifacts=[accepted.artifact_id],
                diagnostics=[f"contract model failed: {safe_error['code']}"],
                safe_error=safe_error,
                telemetry=usage(),
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
            names = {item.get("name") for item in spec.get("participants", [])
                     if isinstance(item, dict) and isinstance(item.get("name"), str)}
            if not diagnostics:
                diagnostics.extend(
                    f"{path}: participant {name!r} is a role; use "
                    f'{{"role_token": {json.dumps(name, ensure_ascii=False)}}}, not an address'
                    for path in _named_address_paths(output["contract"], names)
                    for name in [_value_at(output["contract"], path)])
            if not diagnostics and assets and set(assets) == {"ADA"}:
                diagnostics.extend(
                    f"{path}: accepted intent has only ADA; use empty currency_symbol "
                    "and empty token_name"
                    for path in _noncanonical_ada_paths(output["contract"]))
        if diagnostics:
            return StepExecution(StepResult(
                "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StepRunStatus.FAILED, semantic_status="INVALID_CONTRACT_CANDIDATE",
                input_artifacts=[accepted.artifact_id], diagnostics=diagnostics,
                telemetry=usage(),
            ))
        candidate = ArtifactEnvelope(
            "contract-candidate", "core-v1", "compile",
            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            AuthorityLevel.MODEL_CANDIDATE,
            {"contract": output["contract"], "source_intent_id": accepted.artifact_id,
             "mapping_evidence": output["mapping_evidence"],
             "generation_mode": ("Synthesis-LlmFromSimulatedIntent-v1" if simulated else
                                 "Synthesis-LlmFromAcceptedIntent-v1"),
             "simulation_only": simulated,
             "reasoning_narrative": str(output.get("reasoning_narrative") or "")[:700]},
        )
        return StepExecution(StepResult(
            "compile", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            StepRunStatus.SUCCEEDED, semantic_status="CANDIDATE_GENERATED",
            input_artifacts=[accepted.artifact_id],
            authority_level=AuthorityLevel.MODEL_CANDIDATE,
            telemetry=usage(),
            limitations=["structural validity and model mapping claims are not intent conformance"],
        ), [candidate])
