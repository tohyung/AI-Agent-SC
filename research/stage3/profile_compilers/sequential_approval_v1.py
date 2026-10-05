"""Conservative two-stage funded approval with branch-local refunds."""

from __future__ import annotations

from typing import Any

from research.stage2b.intent_spec import SCHEMA_VERSION_V2
from research.stage3.contract_plan import (Case, Choice, ClaimValue, Close, Deposit,
                                           Pay, PlanError, When, lower_contract_plan)
from research.stage3.models import (CompilationIR, CompileResult, CompileStatus,
                                    SupportedProfile)


SEQUENTIAL_APPROVAL_PROFILE = SupportedProfile(
    profile_id="sequential-approval", version="v1",
    compiler_id="deterministic-sequential-approval", compiler_version="0.1.0",
    intent_schema_version=SCHEMA_VERSION_V2,
    claim_kinds=frozenset({
        "asset", "amount_lovelace", "depositing_party", "destination_account_owner",
        "deposit_deadline_ms", "choice_owner", "choice_deadline_ms",
        "payment_source_account_owner", "payment_recipient", "refund_recipient",
    }),
    scope_types=frozenset({"global", "transition", "branch", "timeout", "terminal_outcome"}),
    transition_kinds=frozenset({"deposit", "choice"}),
    supported_assets=frozenset({"ADA"}), supports_branches=True, supports_timeouts=True,
    transition_counts=(("deposit", 1), ("choice", 2)),
)


def _unsupported(reason: str) -> CompileResult:
    return CompileResult(CompileStatus.UNSUPPORTED_FEATURE, diagnostics=(reason,))


def compile_sequential_approval_v1(ir: CompilationIR) -> CompileResult:
    if (ir.profile_id, ir.profile_version) != (
            SEQUENTIAL_APPROVAL_PROFILE.profile_id, SEQUENTIAL_APPROVAL_PROFILE.version):
        return _unsupported("profile identity unsupported")
    if (ir.funding_relations or any(item.kind not in SEQUENTIAL_APPROVAL_PROFILE.claim_kinds
                                   or item.status not in {"explicit", "derived", "user_confirmed"}
                                   for item in ir.claims)):
        return _unsupported("unsupported claim, status, or funding relation")
    scopes = {item.scope_id: item for item in ir.scopes}
    if len(scopes) != len(ir.scopes):
        return _unsupported("duplicate scope ID")
    grouped = {kind: [item for item in ir.scopes if item.scope_type == kind]
               for kind in SEQUENTIAL_APPROVAL_PROFILE.scope_types}
    deposits = [item for item in grouped["transition"] if item.transition_kind == "deposit"]
    choices = {item.scope_id: item for item in grouped["transition"]
               if item.transition_kind == "choice"}
    if (len(grouped["global"]) != 1 or grouped["global"][0].scope_id != "global"
            or len(deposits) != 1 or len(choices) != 2
            or len(grouped["branch"]) != 2 or len(grouped["timeout"]) != 2
            or len(grouped["terminal_outcome"]) != 4 or len(ir.scopes) != 12):
        return _unsupported("requires one deposit, two approvals and four terminal outcomes")
    deposit = deposits[0]
    first = choices.get(deposit.source.get("continuation_scope_id"))
    if first is None:
        return _unsupported("deposit must continue to the first approval")
    second = next(item for item in choices.values() if item.scope_id != first.scope_id)
    branches: dict[str, Any] = {}
    timeouts: dict[str, Any] = {}
    approvals: dict[str, Any] = {}
    refunds: dict[str, Any] = {}
    for choice in (first, second):
        branch = [item for item in grouped["branch"] if item.decision_id == choice.scope_id]
        timeout = [item for item in grouped["timeout"] if item.decision_id == choice.scope_id]
        if len(branch) != 1 or len(timeout) != 1:
            return _unsupported("each approval needs one approve case and one timeout")
        approved = scopes.get(branch[0].source.get("continuation_scope_id"))
        refunded = scopes.get(timeout[0].source.get("continuation_scope_id"))
        if (approved is None or refunded is None
                or approved.scope_type != "terminal_outcome"
                or refunded.scope_type != "terminal_outcome"
                or approved.source.get("parent_scope_id") != branch[0].scope_id
                or refunded.source.get("parent_scope_id") != timeout[0].scope_id
                or timeout[0].deadline_claim_id is None):
            return _unsupported("approval and timeout must lead to explicit outcomes")
        bounds = choice.source.get("choice_bounds")
        guard = branch[0].source.get("choice_guard")
        if (not isinstance(bounds, dict) or (bounds.get("from"), bounds.get("to")) != (1, 1)
                or not isinstance(guard, dict)
                or (guard.get("operator"), guard.get("value")) != ("eq", 1)):
            return _unsupported("approval encoding must be the single source-backed Choice 1")
        branches[choice.scope_id] = branch[0]
        timeouts[choice.scope_id] = timeout[0]
        approvals[choice.scope_id] = approved
        refunds[choice.scope_id] = refunded
    if (approvals[first.scope_id].source.get("continuation_scope_id") != second.scope_id
            or any(item.source.get("continuation_scope_id") is not None for item in (
                approvals[second.scope_id], refunds[first.scope_id], refunds[second.scope_id]))
            or any(item.source.get("continuation_scope_id") is not None
                   for item in (first, second))):
        return _unsupported("approval sequence or terminal continuation unsupported")

    def one(kind: str, scope_id: str) -> Any | None:
        matches = [item for item in ir.claims if item.kind == kind and item.scope_id == scope_id]
        return matches[0] if len(matches) == 1 else None

    asset = one("asset", "global")
    total = one("amount_lovelace", "global") or one("amount_lovelace", deposit.scope_id)
    depositor = one("depositing_party", deposit.scope_id)
    account = one("destination_account_owner", deposit.scope_id)
    deposit_deadline = one("deposit_deadline_ms", deposit.scope_id)
    required = (asset, total, depositor, account, deposit_deadline)
    if any(item is None for item in required):
        return _unsupported("deposit source, account, amount, asset or deadline missing")
    if (asset.value != "ADA" or asset.status not in {"explicit", "user_confirmed"}
            or type(total.value) is not int or total.value <= 0
            or type(deposit_deadline.value) is not int or deposit_deadline.value <= 0
            or any(not isinstance(item.value, str) or not item.value
                   for item in (depositor, account))):
        return _unsupported("invalid funded ADA deposit")
    used_claims = {item.claim_id for item in required}
    stages: list[dict[str, Any]] = []
    for choice in (first, second):
        owner = one("choice_owner", choice.scope_id)
        deadline = one("choice_deadline_ms", choice.scope_id)
        pay_scope = approvals[choice.scope_id].scope_id
        refund_scope = refunds[choice.scope_id].scope_id
        payout = one("amount_lovelace", pay_scope)
        recipient = one("payment_recipient", pay_scope) or one("release_recipient", pay_scope)
        source = one("payment_source_account_owner", pay_scope)
        refund_amount = one("amount_lovelace", refund_scope)
        refund_recipient = one("refund_recipient", refund_scope)
        refund_source = one("payment_source_account_owner", refund_scope)
        essential = (owner, deadline, payout, recipient, source, refund_amount, refund_recipient)
        if any(item is None for item in essential):
            return _unsupported("each approval requires owner, deadline, payout and refund facts")
        if (type(deadline.value) is not int or deadline.value <= 0
                or timeouts[choice.scope_id].deadline_claim_id != deadline.claim_id
                or type(payout.value) is not int or payout.value <= 0
                or type(refund_amount.value) is not int or refund_amount.value <= 0
                or not isinstance(owner.value, str) or not owner.value
                or not isinstance(recipient.value, str) or not recipient.value
                or not isinstance(refund_recipient.value, str) or not refund_recipient.value
                or source.value != account.value
                or (refund_source is not None and refund_source.value != account.value)):
            return _unsupported("approval deadline, source account, or payout invalid")
        used_claims.update(item.claim_id for item in essential)
        if refund_source is not None:
            used_claims.add(refund_source.claim_id)
        stages.append({"choice": choice, "owner": owner, "deadline": deadline,
                       "pay_scope": pay_scope, "payout": payout, "recipient": recipient,
                       "source": source, "refund_scope": refund_scope,
                       "refund_amount": refund_amount, "refund_recipient": refund_recipient,
                       "refund_source": refund_source})
    first_stage, second_stage = stages
    if (not deposit_deadline.value < first_stage["deadline"].value
            < second_stage["deadline"].value
            or first_stage["payout"].value + second_stage["payout"].value != total.value
            or first_stage["refund_amount"].value != total.value
            or second_stage["refund_amount"].value != second_stage["payout"].value):
        return _unsupported("deadlines must increase and every branch must conserve funding")
    if used_claims != {item.claim_id for item in ir.claims}:
        return _unsupported("extra or duplicate claim outside sequential approval profile")
    if (len(ir.assets) != 1 or ir.assets[0].symbol != "ADA"
            or asset.claim_id not in ir.assets[0].source.get("claim_refs", [])
            or not ir.accounts or any(item.owner != account.value for item in ir.accounts)):
        return _unsupported("projected asset or account inconsistent with funding")

    def cv(item: Any) -> ClaimValue:
        return ClaimValue(item.value, item.claim_id)

    def payment(scope_id: str, recipient: Any, amount: Any, source: Any | None,
                continuation: Any) -> Pay:
        return Pay(scope_id, cv(source if source is not None else account), cv(recipient),
                   cv(asset), cv(amount), continuation)

    second_plan = When(second.scope_id, (
        Case(Choice(second.scope_id, cv(second_stage["owner"]), 1, 1),
             payment(second_stage["pay_scope"], second_stage["recipient"],
                     second_stage["payout"], second_stage["source"], Close("done"))),
    ), cv(second_stage["deadline"]),
        payment(second_stage["refund_scope"], second_stage["refund_recipient"],
                second_stage["refund_amount"], second_stage["refund_source"], Close("done")))
    first_plan = When(first.scope_id, (
        Case(Choice(first.scope_id, cv(first_stage["owner"]), 1, 1),
             payment(first_stage["pay_scope"], first_stage["recipient"],
                     first_stage["payout"], first_stage["source"], second_plan)),
    ), cv(first_stage["deadline"]),
        payment(first_stage["refund_scope"], first_stage["refund_recipient"],
                first_stage["refund_amount"], first_stage["refund_source"], Close("done")))
    plan = When(deposit.scope_id, (
        Case(Deposit(deposit.scope_id, cv(depositor), cv(account), cv(asset), cv(total)),
             first_plan),
    ), cv(deposit_deadline), Close("unfunded"))
    try:
        lowered = lower_contract_plan(plan)
    except PlanError as exc:
        return _unsupported(f"contract plan invalid: {exc}")

    path_first = "$.when[0].then"
    path_first_pay = path_first + ".when[0].then"
    path_first_refund = path_first + ".timeout_continuation"
    path_second = path_first_pay + ".then"
    path_second_pay = path_second + ".when[0].then"
    path_second_refund = path_second + ".timeout_continuation"
    scope_paths = {
        "global": "$.when[0].case.of_token", deposit.scope_id: "$",
        first.scope_id: path_first, second.scope_id: path_second,
        branches[first.scope_id].scope_id: path_first_pay,
        branches[second.scope_id].scope_id: path_second_pay,
        timeouts[first.scope_id].scope_id: path_first_refund,
        timeouts[second.scope_id].scope_id: path_second_refund,
        first_stage["pay_scope"]: path_first_pay,
        second_stage["pay_scope"]: path_second_pay,
        first_stage["refund_scope"]: path_first_refund,
        second_stage["refund_scope"]: path_second_refund,
    }
    records = list(lowered.mapping_evidence)
    claim_paths = {item["source_id"]: item["ast_path"] for item in records
                   if item["source_kind"] == "claim"}
    for scope_id, path in scope_paths.items():
        records.append({"source_kind": "scope", "source_id": scope_id, "ast_path": path})
    if used_claims - claim_paths.keys():
        return _unsupported("source claim has no lowered AST path")

    def add(kind: str, source_id: str, path: str) -> None:
        records.append({"source_kind": kind, "source_id": source_id, "ast_path": path})

    for item in ir.participants:
        path = next((claim_paths[ref] for ref in item.claim_refs if ref in claim_paths), None)
        if path is None:
            return _unsupported("participant has no mapped claim")
        add("participants", item.participant_id, path)
    add("assets", ir.assets[0].asset_id, "$.when[0].case.of_token")
    for kind, items, id_field in (
        ("accounts", ir.accounts, "account_id"),
        ("parameters", ir.parameters, "parameter_id"),
        ("states", ir.states, "state_id"),
        ("transitions", ir.transitions, "transition_id"),
        ("obligations_and_outcomes", ir.outcomes, "outcome_id"),
    ):
        for item in items:
            if kind == "states":
                path = "$" if item.state_id == "initial" else path_first
            elif kind == "transitions":
                path = scope_paths.get(item.transition_id)
            elif kind == "obligations_and_outcomes":
                path = scope_paths.get(item.source.get("scope_id"))
            else:
                path = next((claim_paths[ref] for ref in item.source.get("claim_refs", [])
                             if ref in claim_paths), None)
            if path is None:
                return _unsupported(f"{kind} has no mapped AST path")
            add(kind, getattr(item, id_field), path)
    return CompileResult(CompileStatus.SUPPORTED, lowered.contract, tuple(records))
