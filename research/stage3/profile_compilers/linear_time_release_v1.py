"""Conservative two-installment ADA release from one funded account."""

from __future__ import annotations

from typing import Any

from research.stage2b.intent_spec import SCHEMA_VERSION_V2
from research.stage3.contract_plan import (Case, ClaimValue, Close, Deposit, Pay,
                                           PlanError, When, lower_contract_plan)
from research.stage3.models import (CompilationIR, CompileResult, CompileStatus,
                                    SupportedProfile)


LINEAR_TIME_RELEASE_PROFILE = SupportedProfile(
    profile_id="linear-time-release", version="v1",
    compiler_id="deterministic-linear-time-release", compiler_version="0.1.0",
    intent_schema_version=SCHEMA_VERSION_V2,
    claim_kinds=frozenset({
        "asset", "amount_lovelace", "depositing_party", "destination_account_owner",
        "deposit_deadline_ms", "payment_source_account_owner", "payment_recipient",
        "timeout_ms",
    }),
    scope_types=frozenset({"global", "transition"}),
    transition_kinds=frozenset({"deposit", "payment"}),
    supported_assets=frozenset({"ADA"}),
)


def _unsupported(reason: str) -> CompileResult:
    return CompileResult(CompileStatus.UNSUPPORTED_FEATURE, diagnostics=(reason,))


def compile_linear_time_release_v1(ir: CompilationIR) -> CompileResult:
    if (ir.profile_id, ir.profile_version) != (LINEAR_TIME_RELEASE_PROFILE.profile_id,
                                                LINEAR_TIME_RELEASE_PROFILE.version):
        return _unsupported("profile identity unsupported")
    if ir.funding_relations or any(
            item.kind not in LINEAR_TIME_RELEASE_PROFILE.claim_kinds
            or item.status not in {"explicit", "derived", "user_confirmed"}
            for item in ir.claims):
        return _unsupported("unsupported claim, status, or funding relation")
    globals_ = [scope for scope in ir.scopes if scope.scope_type == "global"]
    deposits = [scope for scope in ir.scopes if scope.transition_kind == "deposit"]
    payments = [scope for scope in ir.scopes if scope.transition_kind == "payment"]
    if (len(ir.scopes) != 4 or len(globals_) != 1 or globals_[0].scope_id != "global"
            or len(deposits) != 1 or len(payments) != 2
            or any(scope.scope_type != "transition" for scope in (*deposits, *payments))):
        return _unsupported("requires one deposit and exactly two payment transitions")
    deposit = deposits[0]
    by_id = {scope.scope_id: scope for scope in payments}
    if len(by_id) != 2:
        return _unsupported("duplicate payment scope")
    first = by_id.get(deposit.source.get("continuation_scope_id"))
    second = by_id.get(first.source.get("continuation_scope_id")) if first else None
    if first is None or second is None or first.scope_id == second.scope_id or (
            second.source.get("continuation_scope_id") is not None):
        return _unsupported("payment sequence must be explicit and acyclic")

    def one(kind: str, scope_id: str) -> Any | None:
        matches = [item for item in ir.claims if item.kind == kind and item.scope_id == scope_id]
        return matches[0] if len(matches) == 1 else None

    asset = one("asset", "global")
    amount = one("amount_lovelace", deposit.scope_id) or one("amount_lovelace", "global")
    depositor = one("depositing_party", deposit.scope_id)
    account = one("destination_account_owner", deposit.scope_id)
    deposit_deadline = one("deposit_deadline_ms", deposit.scope_id)
    required = (asset, amount, depositor, account, deposit_deadline)
    if any(item is None for item in required):
        return _unsupported("deposit funding facts missing")
    if (asset.value != "ADA" or asset.status not in {"explicit", "user_confirmed"}
            or type(amount.value) is not int or amount.value <= 0
            or type(deposit_deadline.value) is not int or deposit_deadline.value <= 0
            or any(not isinstance(item.value, str) or not item.value
                   for item in (depositor, account))):
        return _unsupported("invalid deposit amount, deadline, asset or party")
    installments: list[tuple[Any, Any, Any, Any, Any]] = []
    for scope in (first, second):
        pieces = tuple(one(kind, scope.scope_id) for kind in (
            "amount_lovelace", "payment_recipient", "payment_source_account_owner", "timeout_ms"))
        if any(item is None for item in pieces):
            return _unsupported("each payment requires amount, recipient, source and timeout")
        payout, recipient, source, deadline = pieces
        if (type(payout.value) is not int or payout.value <= 0
                or type(deadline.value) is not int
                or not isinstance(recipient.value, str) or not recipient.value
                or source.value != account.value):
            return _unsupported("invalid payment value or source account")
        installments.append((scope, payout, recipient, source, deadline))
    if (deposit_deadline.value >= installments[0][4].value
            or installments[0][4].value >= installments[1][4].value
            or sum(item[1].value for item in installments) != amount.value):
        return _unsupported("payment deadlines must increase and payouts conserve funding")
    used_claim_ids = {item.claim_id for item in required}
    used_claim_ids.update(item.claim_id for installment in installments
                          for item in installment[1:])
    if used_claim_ids != {item.claim_id for item in ir.claims}:
        return _unsupported("extra or duplicate claim outside release profile")
    account_refs = [ref for item in ir.accounts for ref in item.source.get("claim_refs", [])]
    expected_account_refs = {account.claim_id} | {item[3].claim_id for item in installments}
    if (len(ir.assets) != 1 or ir.assets[0].symbol != "ADA"
            or not ir.accounts or any(item.owner != account.value for item in ir.accounts)
            or asset.claim_id not in ir.assets[0].source.get("claim_refs", [])
            or set(account_refs) != expected_account_refs
            or len(account_refs) != len(expected_account_refs)):
        return _unsupported("projected asset or account inconsistent with funding")

    claim_paths = {
        asset.claim_id: "$.when[0].case.of_token",
        amount.claim_id: "$.when[0].case.deposits",
        depositor.claim_id: "$.when[0].case.party",
        account.claim_id: "$.when[0].case.into_account",
        deposit_deadline.claim_id: "$.timeout",
    }
    payment_paths = ["$.when[0].then.timeout_continuation",
                     "$.when[0].then.timeout_continuation.then.timeout_continuation"]
    continuation = Close(second.scope_id)
    for position in (1, 0):
        scope, payout, recipient, source, deadline = installments[position]
        path = payment_paths[position]
        claim_paths[payout.claim_id] = path + ".pay"
        claim_paths[recipient.claim_id] = path + ".to.party"
        claim_paths[source.claim_id] = path + ".from_account"
        claim_paths[deadline.claim_id] = path.rsplit(".timeout_continuation", 1)[0] + ".timeout"
        continuation = When(scope.scope_id, (), ClaimValue(deadline.value, deadline.claim_id),
                            Pay(scope.scope_id, ClaimValue(source.value, source.claim_id),
                                ClaimValue(recipient.value, recipient.claim_id),
                                ClaimValue(asset.value, asset.claim_id),
                                ClaimValue(payout.value, payout.claim_id), continuation))
    plan = When("global", (
        Case(Deposit(deposit.scope_id, ClaimValue(depositor.value, depositor.claim_id),
                     ClaimValue(account.value, account.claim_id),
                     ClaimValue(asset.value, asset.claim_id),
                     ClaimValue(amount.value, amount.claim_id)), continuation),
    ), ClaimValue(deposit_deadline.value, deposit_deadline.claim_id), Close("global"))
    try:
        contract = lower_contract_plan(plan).contract
    except PlanError as exc:
        return _unsupported(f"contract plan invalid: {exc}")
    scope_paths = {"global": "$.when[0].case.of_token", deposit.scope_id: "$",
                   first.scope_id: payment_paths[0], second.scope_id: payment_paths[1]}
    records: list[dict[str, str]] = []

    def add(kind: str, source_id: str, path: str) -> None:
        records.append({"source_kind": kind, "source_id": source_id, "ast_path": path})

    for item in ir.claims:
        add("claim", item.claim_id, claim_paths[item.claim_id])
    for item in ir.scopes:
        add("scope", item.scope_id, scope_paths[item.scope_id])
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
                path = "$"
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
    return CompileResult(CompileStatus.SUPPORTED, contract, tuple(records))
