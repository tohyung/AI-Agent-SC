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
from research.stage2b.intent_spec import parse_native_asset_id
from research.stage4.declared_domain import DeclaredActionDomain


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


def _transaction(kind: str, input_value: dict | None = None, *, at: int = 0) -> dict:
    return {"interval": {"from": at, "to": at},
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
class SwapTransactionDomain:
    """Select an intent-declared deposit by action identity, not AST quantity."""

    domain_id: str
    deposits: tuple[dict[str, Any], ...]
    finite: bool = True

    def transactions(self, state: dict[str, Any], contract: Any) -> list[dict[str, Any]]:
        if contract == "close":
            return []
        if isinstance(contract, dict) and "pay" in contract:
            return [_transaction("NoInput")]
        if not isinstance(contract, dict) or not isinstance(contract.get("when"), list):
            return []
        enabled = [case["case"] for case in contract["when"]
                   if isinstance(case, dict) and isinstance(case.get("case"), dict)
                   and "deposits" in case["case"]]
        return [tx for tx in self.deposits for action in enabled
                if all(action.get(field) == tx["inputs"][0][key]
                       for field, key in (("party", "party"),
                                          ("into_account", "account"),
                                          ("of_token", "token")))]


@dataclass(frozen=True)
class BatchScenario:
    expectation: ArtifactEnvelope
    domain: IntentTransactionDomain | SwapTransactionDomain | DeclaredActionDomain
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
    if profile_id in {"direct-payment", "funded-choice"} and _claim(spec, "asset") != "ADA":
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
    elif profile_id == "linear-time-release":
        if _claim(spec, "asset", "global") != "ADA":
            raise ValueError("scenario requires a source-grounded ADA asset")
        deposit = _scope(spec, "transition", "deposit")
        payments = [item for item in spec["behavior_scopes"]
                    if item.get("transition_kind") == "payment"]
        if len(payments) != 2:
            raise ValueError("scenario requires exactly two payment transitions")
        first = next((item for item in payments
                      if item["scope_id"] == deposit.get("continuation_scope_id")), None)
        second = (next((item for item in payments
                        if item["scope_id"] == first.get("continuation_scope_id")), None)
                  if first is not None else None)
        if first is None or second is None or second.get("continuation_scope_id") is not None:
            raise ValueError("scenario requires an explicit ordered payment chain")
        account = _claim(spec, "destination_account_owner", deposit["scope_id"])
        depositor = _claim(spec, "depositing_party", deposit["scope_id"])
        funding = [item["value"] for item in spec["claims"]
                   if item["kind"] == "amount_lovelace"
                   and item["scope_id"] in {deposit["scope_id"], "global"}
                   and item["status"] in {"explicit", "derived", "user_confirmed"}]
        deposit_deadline = _claim(spec, "deposit_deadline_ms", deposit["scope_id"])
        if (len(funding) != 1 or type(funding[0]) is not int or funding[0] <= 0
                or type(deposit_deadline) is not int or deposit_deadline <= 0):
            raise ValueError("scenario requires one positive funding amount and deadline")
        transactions_list = [_transaction("Deposit", {
            "type": "Deposit", "account": _role(account), "party": _role(depositor),
            "token": ADA, "amount": funding[0]}, at=deposit_deadline - 1)]
        expected_payments_list = []
        previous_deadline = deposit_deadline
        for payment in (first, second):
            scope_id = payment["scope_id"]
            amount = _claim(spec, "amount_lovelace", scope_id)
            recipient = _claim(spec, "payment_recipient", scope_id)
            source = _claim(spec, "payment_source_account_owner", scope_id)
            deadline = _claim(spec, "timeout_ms", scope_id)
            if (source != account or type(amount) is not int or amount <= 0
                    or type(deadline) is not int or deadline <= previous_deadline):
                raise ValueError("scenario payment amount, source, or timing is inconsistent")
            expected_payments_list.append({
                "source_account": _role(account), "payee": {"party": _role(recipient)},
                "token": ADA, "amount": amount})
            transactions_list.append(_transaction("NoInput", at=deadline))
            previous_deadline = deadline
        if sum(item["amount"] for item in expected_payments_list) != funding[0]:
            raise ValueError("scenario releases do not conserve funded amount")
        expected_payments = tuple(expected_payments_list)
        transactions = tuple(transactions_list)
        state = dict(EMPTY_STATE)
        domain = DeclaredActionDomain("batch-timed-release-declared-actions-v1", transactions)
    elif profile_id == "funded-swap":
        deposits = [item for item in spec["behavior_scopes"]
                    if item["scope_type"] == "transition"
                    and item.get("transition_kind") == "deposit"]
        if len(deposits) != 2:
            raise ValueError("scenario requires two deposit transitions")
        first = next((item for item in deposits
                      if item.get("continuation_scope_id") in {
                          other["scope_id"] for other in deposits
                          if other["scope_id"] != item["scope_id"]}), None)
        if first is None:
            raise ValueError("scenario requires ordered deposit transitions")
        second = next(item for item in deposits if item is not first)
        declared = []
        funding = {}
        for deposit in (first, second):
            scope_id = deposit["scope_id"]
            asset = _claim(spec, "asset", scope_id)
            parsed = parse_native_asset_id(asset) if isinstance(asset, str) else None
            if asset == "ADA":
                token = ADA
                amount = _claim(spec, "amount_lovelace", scope_id)
            elif parsed is not None:
                policy, name_hex = parsed
                token = {"currency_symbol": policy,
                         "token_name": bytes.fromhex(name_hex).decode("utf-8")}
                amount = _claim(spec, "amount_token_units", scope_id)
            else:
                raise ValueError("scenario requires identified ADA/native assets")
            depositor = _claim(spec, "depositing_party", scope_id)
            owner = _claim(spec, "destination_account_owner", scope_id)
            if type(amount) is not int or amount <= 0:
                raise ValueError("scenario requires positive deposit quantity")
            funding[asset] = {"amount": amount, "party": depositor,
                              "owner": owner, "token": token}
            declared.append(_transaction("Deposit", {
                "type": "Deposit", "account": _role(owner), "party": _role(depositor),
                "token": token, "amount": amount}))
        if len(funding) != 2 or "ADA" not in funding:
            raise ValueError("scenario requires distinct ADA/native assets")
        scopes_by_id = {item["scope_id"]: item for item in spec["behavior_scopes"]}
        first_payout = scopes_by_id.get(second.get("continuation_scope_id"))
        second_payout = (scopes_by_id.get(first_payout.get("continuation_scope_id"))
                         if isinstance(first_payout, dict) else None)
        if (not isinstance(first_payout, dict) or not isinstance(second_payout, dict)
                or first_payout.get("scope_type") != "terminal_outcome"
                or second_payout.get("scope_type") != "terminal_outcome"
                or first_payout.get("parent_scope_id") != second["scope_id"]
                or second_payout.get("parent_scope_id") not in {
                    second["scope_id"], first_payout["scope_id"]}
                or second_payout.get("continuation_scope_id") is not None):
            raise ValueError("scenario requires two linked swap payouts")
        expected_payments = []
        for outcome in (first_payout, second_payout):
            scope_id = outcome["scope_id"]
            asset = _claim(spec, "asset", scope_id)
            if asset not in funding:
                raise ValueError("scenario payout asset is not funded")
            origin = funding[asset]
            amount_kind = "amount_lovelace" if asset == "ADA" else "amount_token_units"
            amount = _claim(spec, amount_kind, scope_id)
            recipient = _claim(spec, "payment_recipient", scope_id)
            if amount != origin["amount"]:
                raise ValueError("scenario payout does not conserve funding")
            expected_payments.append({
                "source_account": _role(origin["owner"]),
                "payee": {"party": _role(recipient)},
                "token": origin["token"], "amount": amount})
        if len(expected_payments) != 2:
            raise ValueError("scenario requires both swap payouts")
        expected_payments = tuple(expected_payments)
        transactions = tuple(declared)
        state = dict(EMPTY_STATE)
        domain = SwapTransactionDomain("batch-funded-swap-declared-deposits-v1",
                                       transactions)
    elif profile_id == "sequential-approval":
        scopes = {item["scope_id"]: item for item in spec["behavior_scopes"]}
        deposits = [item for item in scopes.values()
                    if item.get("transition_kind") == "deposit"]
        if len(deposits) != 1 or _claim(spec, "asset", "global") != "ADA":
            raise ValueError("scenario requires one ADA deposit")
        deposit = deposits[0]
        first = scopes.get(deposit.get("continuation_scope_id"))
        if not isinstance(first, dict) or first.get("transition_kind") != "choice":
            raise ValueError("scenario requires a first approval after deposit")
        first_branch = [item for item in scopes.values() if item.get("scope_type") == "branch"
                        and item.get("decision_id") == first["scope_id"]]
        if len(first_branch) != 1:
            raise ValueError("scenario requires one first-approval branch")
        first_outcome = scopes.get(first_branch[0].get("continuation_scope_id"))
        second = (scopes.get(first_outcome.get("continuation_scope_id"))
                  if isinstance(first_outcome, dict) else None)
        if not isinstance(second, dict) or second.get("transition_kind") != "choice":
            raise ValueError("scenario requires a second approval after first payout")
        second_branch = [item for item in scopes.values() if item.get("scope_type") == "branch"
                         and item.get("decision_id") == second["scope_id"]]
        if len(second_branch) != 1:
            raise ValueError("scenario requires one second-approval branch")
        second_outcome = scopes.get(second_branch[0].get("continuation_scope_id"))
        if (not isinstance(first_outcome, dict) or not isinstance(second_outcome, dict)
                or first_outcome.get("scope_type") != "terminal_outcome"
                or second_outcome.get("scope_type") != "terminal_outcome"):
            raise ValueError("scenario requires two explicit payout outcomes")
        account = _claim(spec, "destination_account_owner", deposit["scope_id"])
        depositor = _claim(spec, "depositing_party", deposit["scope_id"])
        amount = _claim(spec, "amount_lovelace", "global")
        if type(amount) is not int or amount <= 0:
            raise ValueError("scenario requires positive source-grounded funding")
        declared = [_transaction("Deposit", {
            "type": "Deposit", "account": _role(account), "party": _role(depositor),
            "token": ADA, "amount": amount})]
        expected_payments = []
        for choice, outcome in ((first, first_outcome), (second, second_outcome)):
            bounds = choice.get("choice_bounds")
            owner = _claim(spec, "choice_owner", choice["scope_id"])
            if not isinstance(bounds, dict) or (bounds.get("from"), bounds.get("to")) != (1, 1):
                raise ValueError("scenario requires source-backed approval encoding")
            declared.append(_transaction("Choice", {
                "type": "Choice", "choice_id": {
                    "choice_name": choice["scope_id"], "choice_owner": _role(owner)},
                "chosen": 1}))
            scope_id = outcome["scope_id"]
            payout = _claim(spec, "amount_lovelace", scope_id)
            recipient = _claim(spec, "payment_recipient", scope_id)
            source = _claim(spec, "payment_source_account_owner", scope_id)
            if source != account or type(payout) is not int or payout <= 0:
                raise ValueError("scenario payout source or amount invalid")
            expected_payments.append({
                "source_account": _role(account), "payee": {"party": _role(recipient)},
                "token": ADA, "amount": payout})
        if sum(item["amount"] for item in expected_payments) != amount:
            raise ValueError("scenario payouts do not conserve funded amount")
        expected_payments = tuple(expected_payments)
        transactions = tuple(declared)
        state = dict(EMPTY_STATE)
        domain = DeclaredActionDomain("batch-sequential-approval-declared-actions-v1",
                                      transactions)
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
    if profile_id not in {"funded-swap", "linear-time-release", "sequential-approval"}:
        domain = IntentTransactionDomain(f"batch-{profile_id}-declared-actions-v1", actions)
    return BatchScenario(artifact, domain, state)
