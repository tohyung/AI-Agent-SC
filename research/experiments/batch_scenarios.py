"""Synthetic, intent-sourced reference scenarios for the tuning corridor.

Transaction inputs come from the accepted spec, never from the compiler AST.
The AST is inspected only to select which already-declared action is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.stage3.comparison import BehaviorExpectation
from research.stage3.reference import ReferenceRequest


ADA = {"currency_symbol": "", "token_name": ""}
EMPTY_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}
SYNTHETIC_REVIEWER = "batch-simulated-customer"


def _role(name: str) -> dict[str, str]:
    return {"role_token": name}


def _claim(spec: dict[str, Any], kind: str, scope_id: str | None = None) -> Any:
    matches = [item["value"] for item in spec["claims"]
               if item["kind"] == kind and (scope_id is None or item["scope_id"] == scope_id)
               and item["status"] in {"explicit", "derived", "user_confirmed"}]
    if len(matches) != 1:
        raise ValueError(f"scenario requires one active {kind} claim")
    return matches[0]


def _scope(spec: dict[str, Any], scope_type: str, transition_kind: str | None = None) -> dict:
    matches = [item for item in spec["behavior_scopes"]
               if item["scope_type"] == scope_type
               and (transition_kind is None or item.get("transition_kind") == transition_kind)]
    if len(matches) != 1:
        raise ValueError(f"scenario requires one {scope_type}/{transition_kind} scope")
    return matches[0]


def _transaction(kind: str, input_value: dict | None = None) -> dict:
    return {"interval": {"from": 0, "to": 0},
            "inputs": [] if input_value is None else [input_value]}


@dataclass(frozen=True)
class IntentTransactionDomain:
    """Choose a declared input by AST action kind, without deriving its values."""

    domain_id: str
    actions: dict[str, dict[str, Any]]
    finite: bool = True

    def transactions(self, state: dict[str, Any], contract: Any) -> list[dict[str, Any]]:
        if contract == "close":
            return []
        if isinstance(contract, dict) and "pay" in contract:
            return [self.actions["NoInput"]] if "NoInput" in self.actions else []
        if not isinstance(contract, dict) or not isinstance(contract.get("when"), list):
            return []
        kinds = {"deposits": "Deposit", "for_choice": "Choice", "notify_if": "Notify"}
        enabled = {kinds[key] for case in contract["when"] if isinstance(case, dict)
                   and isinstance(case.get("case"), dict)
                   for key in case["case"] if key in kinds}
        return [self.actions[kind] for kind in sorted(enabled) if kind in self.actions]


@dataclass(frozen=True)
class BatchScenario:
    expectation: ArtifactEnvelope
    domain: IntentTransactionDomain
    initial_state: dict[str, Any]


class SyntheticExpectationPolicy:
    def authorize(self, artifact: ArtifactEnvelope) -> bool:
        return (artifact.artifact_type == "behavior-expectation"
                and artifact.producer_stage == "batch_synthetic_scenario"
                and artifact.authority_level == AuthorityLevel.NO_AUTHORITY
                and artifact.payload.get("simulation_only") is True
                and artifact.payload.get("reviewer_id") == SYNTHETIC_REVIEWER
                and artifact.payload.get("source_kind") == "accepted_intent")


def scenario_from_intent(accepted: ArtifactEnvelope, profile_id: str) -> BatchScenario:
    if (accepted.artifact_type != "accepted-intent"
            or accepted.payload.get("simulation_only") is not True
            or accepted.authority_level != AuthorityLevel.NO_AUTHORITY):
        raise ValueError("batch scenario requires simulated accepted intent")
    spec = accepted.payload["accepted_spec"]
    if _claim(spec, "asset") != "ADA":
        raise ValueError("only ADA scenario supported")
    if profile_id == "direct-payment":
        source = _claim(spec, "payment_source_account_owner")
        recipient = _claim(spec, "payment_recipient")
        amount = _claim(spec, "amount_lovelace")
        state = {**EMPTY_STATE, "accounts": [[[_role(source), ADA], amount]]}
        transactions = (_transaction("NoInput"),)
        actions = {"NoInput": transactions[0]}
        expected_payments = ({"source_account": _role(source),
                              "payee": {"party": _role(recipient)},
                              "token": ADA, "amount": amount},)
    elif profile_id == "funded-choice":
        deposit = _scope(spec, "transition", "deposit")
        choice = _scope(spec, "transition", "choice")
        outcome_by_id = {item["scope_id"]: item for item in spec["behavior_scopes"]
                         if item["scope_type"] == "terminal_outcome"}
        payout = next((item for item in spec["behavior_scopes"]
                       if item["scope_type"] == "branch"
                       and item.get("decision_id") == choice["scope_id"]
                       and any(claim["kind"] in {"payment_recipient", "release_recipient"}
                               and claim["scope_id"] in {
                                   item["scope_id"], item.get("continuation_scope_id")}
                               for claim in spec["claims"])), None)
        if payout is None or payout.get("continuation_scope_id") not in outcome_by_id:
            raise ValueError("scenario needs one payout branch")
        lower, upper = (choice["choice_bounds"][key] for key in ("from", "to"))
        guard = payout["choice_guard"]
        def matches(value: int) -> bool:
            operator, boundary = guard["operator"], guard["value"]
            return {"ge": value >= boundary, "gt": value > boundary,
                    "le": value <= boundary, "lt": value < boundary,
                    "eq": value == boundary}[operator]
        chosen = next((value for value in (lower, upper) if matches(value)), None)
        if chosen is None:
            raise ValueError("payout guard does not include either bound endpoint")
        source = _claim(spec, "destination_account_owner", deposit["scope_id"])
        depositor = _claim(spec, "depositing_party", deposit["scope_id"])
        chooser = _claim(spec, "choice_owner", choice["scope_id"])
        funding_amounts = [item["value"] for item in spec["claims"]
                           if item["kind"] == "amount_lovelace"
                           and item["scope_id"] in {deposit["scope_id"], "global"}
                           and item["status"] in {"explicit", "derived", "user_confirmed"}]
        if len(funding_amounts) != 1 or type(funding_amounts[0]) is not int:
            raise ValueError("scenario requires one funding amount")
        amount = funding_amounts[0]
        outcomes = [item for item in spec["behavior_scopes"]
                    if item["scope_type"] == "terminal_outcome"
                    and item.get("parent_scope_id") == payout["scope_id"]]
        if (not outcomes or len(outcomes) > 2
                or payout["continuation_scope_id"] != outcomes[0]["scope_id"]):
            raise ValueError("scenario needs an explicit first payout outcome")
        expected_payments_list = []
        for outcome in outcomes:
            scope_id = outcome["scope_id"]
            recipient_claims = [item for item in spec["claims"]
                                if item["kind"] in {"payment_recipient", "release_recipient",
                                                       "refund_recipient"}
                                and item["scope_id"] in {scope_id, payout["scope_id"]}
                                and item["status"] in {"explicit", "derived", "user_confirmed"}]
            if len(recipient_claims) != 1:
                raise ValueError("scenario requires one recipient per payout")
            payout_amounts = [item["value"] for item in spec["claims"]
                              if item["kind"] == "amount_lovelace"
                              and item["scope_id"] == scope_id
                              and item["status"] in {"explicit", "derived", "user_confirmed"}]
            if len(payout_amounts) > 1 or (len(outcomes) > 1 and not payout_amounts):
                raise ValueError("scenario requires distinct payout amounts")
            payout_amount = payout_amounts[0] if payout_amounts else amount
            payout_source = [item["value"] for item in spec["claims"]
                             if item["kind"] == "payment_source_account_owner"
                             and item["scope_id"] == scope_id
                             and item["status"] in {"explicit", "derived", "user_confirmed"}]
            if (len(payout_source) > 1 or (payout_source and payout_source[0] != source)
                    or type(payout_amount) is not int or payout_amount <= 0):
                raise ValueError("scenario payout funding is inconsistent")
            expected_payments_list.append({
                "source_account": _role(source),
                "payee": {"party": _role(recipient_claims[0]["value"])},
                "token": ADA, "amount": payout_amount})
        if sum(item["amount"] for item in expected_payments_list) != amount:
            raise ValueError("scenario payouts do not conserve deposit")
        expected_payments = tuple(expected_payments_list)
        deposit_tx = _transaction("Deposit", {
            "type": "Deposit", "account": _role(source), "party": _role(depositor),
            "token": ADA, "amount": amount})
        choice_tx = _transaction("Choice", {
            "type": "Choice", "choice_id": {"choice_name": choice["scope_id"],
                                           "choice_owner": _role(chooser)}, "chosen": chosen})
        transactions = (deposit_tx, choice_tx)
        actions = {"Deposit": deposit_tx, "Choice": choice_tx}
        state = dict(EMPTY_STATE)
    else:
        raise ValueError("no synthetic scenario for this profile")
    expectation = BehaviorExpectation(
        accepted.artifact_id, "accepted_intent",
        ReferenceRequest(None, state, transactions), "Success", "close",
        SYNTHETIC_REVIEWER, expected_warnings=(), expected_payments=expected_payments)
    payload = {**expectation.to_dict(), "simulation_only": True,
               "scenario_basis": "accepted_intent_claims_not_compiler_ast"}
    artifact = ArtifactEnvelope("behavior-expectation", "batch-v1", "batch_synthetic_scenario",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY, payload)
    return BatchScenario(artifact, IntentTransactionDomain(
        f"batch-{profile_id}-declared-actions-v1", actions), state)
