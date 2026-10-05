"""Conservative two-asset atomic swap with sequential deposits and refund."""

from __future__ import annotations

from typing import Any

from research.stage2b.intent_spec import SCHEMA_VERSION_V3, parse_native_asset_id
from research.stage3.models import (CompilationIR, CompileResult, CompileStatus,
                                    SupportedProfile)


FUNDED_SWAP_PROFILE = SupportedProfile(
    profile_id="funded-swap", version="v1",
    compiler_id="deterministic-funded-swap", compiler_version="0.1.0",
    intent_schema_version=SCHEMA_VERSION_V3,
    claim_kinds=frozenset({
        "asset", "amount_lovelace", "amount_token_units", "depositing_party",
        "destination_account_owner", "payment_source_account_owner",
        "deposit_deadline_ms", "payment_recipient", "refund_recipient",
        "autonomous_execution",
    }),
    scope_types=frozenset({"global", "transition", "timeout", "terminal_outcome"}),
    transition_kinds=frozenset({"deposit"}),
    supported_assets=frozenset({"ADA", "native:*"}), supports_timeouts=True,
)


def _unsupported(reason: str) -> CompileResult:
    return CompileResult(CompileStatus.UNSUPPORTED_FEATURE, diagnostics=(reason,))


def _token(asset: str) -> dict[str, str] | None:
    if asset == "ADA":
        return {"currency_symbol": "", "token_name": ""}
    parsed = parse_native_asset_id(asset)
    if parsed is None:
        return None
    policy_id, name_hex = parsed
    try:
        name = bytes.fromhex(name_hex).decode("utf-8")
    except UnicodeDecodeError:
        return None
    return {"currency_symbol": policy_id, "token_name": name}


def compile_funded_swap_v1(ir: CompilationIR) -> CompileResult:
    if (ir.profile_id, ir.profile_version) != ("funded-swap", "v1"):
        return _unsupported("wrong funded-swap profile")
    scopes = {item.scope_id: item for item in ir.scopes}
    deposits = [item for item in ir.scopes if item.scope_type == "transition"
                and item.transition_kind == "deposit"]
    timeouts = [item for item in ir.scopes if item.scope_type == "timeout"]
    outcomes = [item for item in ir.scopes if item.scope_type == "terminal_outcome"]
    if (len(scopes) != len(ir.scopes) or len(deposits) != 2 or len(timeouts) != 2
            or len(outcomes) not in {3, 4} or len(ir.scopes) not in {8, 9}
            or "global" not in scopes or scopes["global"].scope_type != "global"):
        return _unsupported("exactly two deposits, two timeouts and three outcomes required")
    first = next((item for item in deposits
                  if item.source.get("continuation_scope_id") in {
                      other.scope_id for other in deposits if other.scope_id != item.scope_id}), None)
    if first is None:
        return _unsupported("explicit first-to-second deposit continuation required")
    second = next(item for item in deposits if item.scope_id != first.scope_id)
    first_timeout = next((item for item in timeouts if item.decision_id == first.scope_id), None)
    second_timeout = next((item for item in timeouts if item.decision_id == second.scope_id), None)
    if first_timeout is None or second_timeout is None:
        return _unsupported("both deposit timeouts required")
    close_outcomes = [item for item in outcomes
                      if item.source.get("parent_scope_id") == first_timeout.scope_id]
    if (len(close_outcomes) > 1 or
            first_timeout.source.get("continuation_scope_id") != (
                close_outcomes[0].scope_id if close_outcomes else None) or
            (len(outcomes) == 4) != bool(close_outcomes)):
        return _unsupported("first timeout must close without payout")
    success = [item for item in outcomes if item not in close_outcomes
               and item.source.get("parent_scope_id") != second_timeout.scope_id]
    refunds = [item for item in outcomes
               if item.source.get("parent_scope_id") == second_timeout.scope_id]
    if len(success) != 2 or len(refunds) != 1:
        return _unsupported("two swap payouts and one second-timeout refund required")
    first_pay = scopes.get(second.source.get("continuation_scope_id"))
    if first_pay not in success or first_pay.source.get("parent_scope_id") != second.scope_id:
        return _unsupported("second deposit must continue to first payout")
    second_pay = next(item for item in success if item.scope_id != first_pay.scope_id)
    if (first_pay.source.get("continuation_scope_id") != second_pay.scope_id
            or second_pay.source.get("parent_scope_id") not in {
                second.scope_id, first_pay.scope_id}
            or second_pay.source.get("continuation_scope_id") is not None
            or second_timeout.source.get("continuation_scope_id") != refunds[0].scope_id
            or refunds[0].source.get("continuation_scope_id") is not None):
        return _unsupported("payout and refund continuations must be explicit")

    claims: dict[tuple[str, str], list[Any]] = {}
    for item in ir.claims:
        if item.status not in {"explicit", "derived", "user_confirmed"}:
            return _unsupported("unresolved or non-authoritative claim")
        claims.setdefault((item.scope_id, item.kind), []).append(item)
    used: set[str] = set()
    paths: dict[str, str] = {}

    def one(scope_id: str, kind: str, path: str) -> Any | None:
        matches = claims.get((scope_id, kind), [])
        if len(matches) != 1:
            return None
        item = matches[0]
        used.add(item.claim_id)
        paths[item.claim_id] = path
        return item

    def optional_true(scope_id: str, path: str) -> bool:
        matches = claims.get((scope_id, "autonomous_execution"), [])
        if not matches:
            return True
        item = one(scope_id, "autonomous_execution", path)
        return item is not None and item.value is True

    root = "$"
    second_path = "$.when[0].then"
    success_path = second_path + ".when[0].then"
    refund_path = second_path + ".timeout_continuation"
    scope_paths = {
        "global": root, first.scope_id: root, second.scope_id: second_path,
        first_timeout.scope_id: "$.timeout_continuation",
        second_timeout.scope_id: refund_path,
        first_pay.scope_id: success_path,
        second_pay.scope_id: success_path + ".then",
        refunds[0].scope_id: refund_path,
    }
    if close_outcomes:
        close_outcome = close_outcomes[0]
        if close_outcome.source.get("continuation_scope_id") is not None:
            return _unsupported("first timeout close cannot continue")
        scope_paths[close_outcome.scope_id] = "$.timeout_continuation"
        if not optional_true(close_outcome.scope_id, "$.timeout_continuation"):
            return _unsupported("first timeout close must be automatic")

    funding: dict[str, dict[str, Any]] = {}
    asset_by_scope: dict[str, str] = {}
    for deposit, path in ((first, root), (second, second_path)):
        asset = one(deposit.scope_id, "asset", path + ".when[0].case.of_token")
        if asset is None or not isinstance(asset.value, str):
            return _unsupported("each deposit needs one identified asset")
        token = _token(asset.value)
        if token is None:
            return _unsupported("native asset ID or UTF-8 token name unsupported")
        amount_kind = "amount_lovelace" if asset.value == "ADA" else "amount_token_units"
        amount = one(deposit.scope_id, amount_kind, path + ".when[0].case.deposits")
        depositor = one(deposit.scope_id, "depositing_party", path + ".when[0].case.party")
        owner = one(deposit.scope_id, "destination_account_owner",
                    path + ".when[0].case.into_account")
        deadline = one(deposit.scope_id, "deposit_deadline_ms", path + ".timeout")
        for kind, item in ((amount_kind, amount), ("depositing_party", depositor),
                           ("destination_account_owner", owner),
                           ("deposit_deadline_ms", deadline)):
            if item is None:
                return _unsupported(f"deposit {deposit.scope_id}: one {kind} claim required")
        if (type(amount.value) is not int or amount.value <= 0
                or type(deadline.value) is not int or deadline.value <= 0
                or not isinstance(depositor.value, str) or not depositor.value
                or not isinstance(owner.value, str) or not owner.value):
            return _unsupported(f"deposit {deposit.scope_id}: invalid value or quantity")
        funding[asset.value] = {"asset": asset, "amount": amount, "party": depositor,
                                "owner": owner, "deadline": deadline, "token": token}
        asset_by_scope[deposit.scope_id] = asset.value
    if (len(funding) != 2 or "ADA" not in funding
            or first_timeout.deadline_claim_id != funding[
                asset_by_scope[first.scope_id]]["deadline"].claim_id
            or second_timeout.deadline_claim_id != funding[
                asset_by_scope[second.scope_id]]["deadline"].claim_id):
        return _unsupported("distinct ADA/native assets and timeout deadlines required")
    first_asset, second_asset = asset_by_scope[first.scope_id], asset_by_scope[second.scope_id]
    if funding[first_asset]["deadline"].value >= funding[second_asset]["deadline"].value:
        return _unsupported("second deposit deadline must follow first deadline")

    def payout(outcome: Any, path: str, *, refund: bool) -> tuple[dict[str, Any], str] | None:
        if not optional_true(outcome.scope_id, path):
            return None
        asset = one(outcome.scope_id, "asset", path + ".token")
        if asset is None or asset.value not in funding:
            return None
        origin = funding[asset.value]
        amount = one(outcome.scope_id, origin["amount"].kind, path + ".pay")
        recipient = one(outcome.scope_id, "refund_recipient" if refund else
                        "payment_recipient", path + ".to.party")
        source = one(outcome.scope_id, "payment_source_account_owner",
                     path + ".from_account")
        if (amount is None or recipient is None or amount.value != origin["amount"].value
                or not isinstance(recipient.value, str) or not recipient.value
                or (source is not None and source.value != origin["owner"].value)):
            return None
        if refund:
            if asset.value != first_asset or recipient.value != origin["party"].value:
                return None
        elif recipient.value != funding[second_asset if asset.value == first_asset
                                        else first_asset]["party"].value:
            return None
        return ({"pay": amount.value,
                 "token": origin["token"],
                 "from_account": {"role_token": origin["owner"].value},
                 "to": {"party": {"role_token": recipient.value}},
                 "then": "close"}, asset.value)

    first_result = payout(first_pay, success_path, refund=False)
    second_result = payout(second_pay, success_path + ".then", refund=False)
    refund_result = payout(refunds[0], refund_path, refund=True)
    if (first_result is None or second_result is None or refund_result is None
            or {first_result[1], second_result[1]} != {first_asset, second_asset}):
        return _unsupported("swap payouts or refund do not conserve each funded asset")
    first_contract, _ = first_result
    second_contract, _ = second_result
    refund_contract, _ = refund_result
    first_contract["then"] = second_contract
    first_funding, second_funding = funding[first_asset], funding[second_asset]

    def deposit_case(item: dict[str, Any]) -> dict[str, Any]:
        return {"party": {"role_token": item["party"].value},
                "deposits": item["amount"].value,
                "of_token": item["token"],
                "into_account": {"role_token": item["owner"].value}}

    contract = {
        "when": [{"case": deposit_case(first_funding),
                  "then": {"when": [{"case": deposit_case(second_funding),
                                      "then": first_contract}],
                           "timeout": second_funding["deadline"].value,
                           "timeout_continuation": refund_contract}}],
        "timeout": first_funding["deadline"].value,
        "timeout_continuation": "close",
    }
    if used != {item.claim_id for item in ir.claims}:
        return _unsupported("extra or duplicate claim outside funded-swap profile")
    if {item.symbol for item in ir.assets} != {first_asset, second_asset}:
        return _unsupported("projected assets differ from funded assets")
    mapping = [{"source_kind": "claim", "source_id": claim_id, "ast_path": path}
               for claim_id, path in paths.items()]
    mapping += [{"source_kind": "scope", "source_id": scope_id, "ast_path": path}
                for scope_id, path in scope_paths.items()]
    for section, items, id_field in (
        ("participants", ir.participants, "participant_id"),
        ("assets", ir.assets, "asset_id"),
        ("accounts", ir.accounts, "account_id"),
        ("parameters", ir.parameters, "parameter_id"),
        ("transitions", ir.transitions, "transition_id"),
        ("obligations_and_outcomes", ir.outcomes, "outcome_id"),
    ):
        for item in items:
            refs = item.source.get("claim_refs", [])
            path = next((paths[ref] for ref in refs if ref in paths), None)
            if section == "transitions":
                path = scope_paths.get(item.transition_id)
            elif section == "obligations_and_outcomes":
                path = scope_paths.get(item.source.get("scope_id"))
            if path is None:
                return _unsupported(f"{section} has no mapped source")
            mapping.append({"source_kind": section,
                            "source_id": getattr(item, id_field), "ast_path": path})
    for item in ir.states:
        if item.state_id != "initial":
            return _unsupported("additional state outside funded-swap profile")
        mapping.append({"source_kind": "states", "source_id": item.state_id,
                        "ast_path": root})
    if ir.funding_relations:
        return _unsupported("funding relation projection unsupported")
    return CompileResult(CompileStatus.SUPPORTED, contract, tuple(mapping))
