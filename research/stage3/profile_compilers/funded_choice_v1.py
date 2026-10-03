"""Conservative lowering for one funded numeric Choice with explicit refunds."""

from __future__ import annotations

from typing import Any

from research.stage2b.intent_spec import SCHEMA_VERSION_V2
from research.stage3.models import (CompilationIR, CompileResult, CompileStatus,
                                    SupportedProfile)


FUNDED_CHOICE_PROFILE = SupportedProfile(
    profile_id="funded-choice", version="v1",
    compiler_id="deterministic-funded-choice", compiler_version="0.2.0",
    intent_schema_version=SCHEMA_VERSION_V2,
    claim_kinds=frozenset({
        "asset", "amount_lovelace", "depositing_party", "destination_account_owner",
        "payment_source_account_owner",
        "deposit_deadline_ms", "choice_owner", "choice_deadline_ms",
        "payment_recipient", "release_recipient", "refund_recipient",
    }),
    scope_types=frozenset({"global", "transition", "branch", "timeout", "terminal_outcome"}),
    transition_kinds=frozenset({"deposit", "choice"}),
    supported_assets=frozenset({"ADA"}), supports_branches=True, supports_timeouts=True,
)


def _unsupported(reason: str) -> CompileResult:
    return CompileResult(CompileStatus.UNSUPPORTED_FEATURE, diagnostics=(reason,))


def _guard_interval(guard: Any, lower: int, upper: int) -> tuple[int, int] | None:
    if not isinstance(guard, dict):
        return None
    operator, value = guard.get("operator"), guard.get("value")
    if type(value) is not int:
        return None
    if operator == "ge":
        interval = (max(lower, value), upper)
    elif operator == "gt":
        interval = (max(lower, value + 1), upper)
    elif operator == "le":
        interval = (lower, min(upper, value))
    elif operator == "lt":
        interval = (lower, min(upper, value - 1))
    elif operator == "eq":
        interval = (value, value)
    else:
        return None
    return interval if lower <= interval[0] <= interval[1] <= upper else None


def _observation(guard: dict[str, Any], choice_id: dict[str, Any]) -> dict[str, Any]:
    value = {"value_of_choice": choice_id}
    constant = guard["value"]
    key = {"ge": "ge_than", "gt": "gt", "le": "le_than",
           "lt": "lt", "eq": "equal_to"}[guard["operator"]]
    return {"value": value, key: constant}


def compile_funded_choice_v1(ir: CompilationIR) -> CompileResult:
    if (ir.profile_id, ir.profile_version) != (FUNDED_CHOICE_PROFILE.profile_id,
                                                FUNDED_CHOICE_PROFILE.version):
        return _unsupported("profile identity unsupported")
    if ir.funding_relations or any(item.status not in {"explicit", "derived", "user_confirmed"}
                                   or item.kind not in FUNDED_CHOICE_PROFILE.claim_kinds
                                   for item in ir.claims):
        return _unsupported("unsupported claim, status, or funding relation")
    scopes = {item.scope_id: item for item in ir.scopes}
    if len(scopes) != len(ir.scopes) or not any(
            item.scope_type == "global" and item.scope_id == "global" for item in ir.scopes):
        return _unsupported("one global scope and unique scope IDs required")
    deposits = [item for item in ir.scopes if item.scope_type == "transition"
                and item.transition_kind == "deposit"]
    choices = [item for item in ir.scopes if item.scope_type == "transition"
               and item.transition_kind == "choice"]
    branches = [item for item in ir.scopes if item.scope_type == "branch"]
    timeouts = [item for item in ir.scopes if item.scope_type == "timeout"]
    outcomes = [item for item in ir.scopes if item.scope_type == "terminal_outcome"]
    if (len(deposits) != 1 or len(choices) != 1 or len(branches) != 2
            or len(timeouts) != 1 or len(outcomes) not in {3, 4}
            or len(ir.scopes) != 6 + len(outcomes)):
        return _unsupported("requires one deposit, one Choice, two branches and timeout refund")
    deposit, choice, timeout = deposits[0], choices[0], timeouts[0]
    if (deposit.source.get("continuation_scope_id") != choice.scope_id
            or choice.source.get("continuation_scope_id") is not None
            or any(item.decision_id != choice.scope_id for item in (*branches, timeout))
            or timeout.source.get("continuation_scope_id") not in scopes):
        return _unsupported("deposit/Choice/timeout control-flow linkage unsupported")
    outcome_by_parent: dict[str, list[Any]] = {}
    for outcome in outcomes:
        parent_id = outcome.source.get("parent_scope_id")
        parent = scopes.get(parent_id)
        if parent is None or parent.scope_type not in {"branch", "timeout"}:
            return _unsupported("terminal outcome must have one explicit parent")
        outcome_by_parent.setdefault(parent_id, []).append(outcome)
    if set(outcome_by_parent) != {branches[0].scope_id, branches[1].scope_id, timeout.scope_id}:
        return _unsupported("each branch and timeout needs a terminal outcome")
    if (len(outcome_by_parent[timeout.scope_id]) != 1
            or any(len(outcome_by_parent[item.scope_id]) > 2 for item in branches)
            or any(scopes[parent_id].source.get("continuation_scope_id") != items[0].scope_id
                   for parent_id, items in outcome_by_parent.items())):
        return _unsupported("outcomes require an explicit first continuation and bounded payout chain")
    bounds = choice.source.get("choice_bounds")
    if (not isinstance(bounds, dict) or type(bounds.get("from")) is not int
            or type(bounds.get("to")) is not int or bounds["from"] > bounds["to"]):
        return _unsupported("numeric Choice bounds required")

    def claim(kind: str, scope_id: str) -> Any | None:
        matches = [item for item in ir.claims if item.kind == kind and item.scope_id == scope_id]
        return matches[0] if len(matches) == 1 else None

    asset = claim("asset", "global")
    amount = claim("amount_lovelace", deposit.scope_id) or claim("amount_lovelace", "global")
    depositor = claim("depositing_party", deposit.scope_id)
    account = claim("destination_account_owner", deposit.scope_id)
    source_account = claim("payment_source_account_owner", "global")
    deposit_deadline = claim("deposit_deadline_ms", deposit.scope_id)
    chooser = claim("choice_owner", choice.scope_id)
    choice_deadline = claim("choice_deadline_ms", choice.scope_id)
    required = (asset, amount, depositor, account, deposit_deadline, chooser, choice_deadline)
    if any(item is None for item in required):
        return _unsupported("required funding, account, Choice, or deadline claim missing")
    if (asset.value != "ADA" or asset.status not in {"explicit", "user_confirmed"}
            or type(amount.value) is not int or amount.value <= 0
            or type(deposit_deadline.value) is not int or deposit_deadline.value <= 0
            or type(choice_deadline.value) is not int
            or choice_deadline.value <= deposit_deadline.value
            or any(not isinstance(item.value, str) or not item.value for item in
                   (depositor, account, chooser))
            or (source_account is not None and source_account.value != account.value)
            or timeout.deadline_claim_id != choice_deadline.claim_id):
        return _unsupported("funded Choice values or timeout linkage invalid")
    payouts: dict[str, list[tuple[Any, Any, Any, Any | None]]] = {}
    for parent_id, children in outcome_by_parent.items():
        payouts[parent_id] = []
        for outcome in children:
            claim_scopes = {outcome.scope_id} | ({parent_id} if len(children) == 1 else set())
            recipients = [item for item in ir.claims if item.scope_id in claim_scopes
                          and item.kind in {"payment_recipient", "release_recipient",
                                            "refund_recipient"}]
            amounts = [item for item in ir.claims if item.scope_id in claim_scopes
                       and item.kind == "amount_lovelace"]
            sources = [item for item in ir.claims if item.scope_id in claim_scopes
                       and item.kind == "payment_source_account_owner"]
            if (len(recipients) != 1 or len(amounts) > 1 or len(sources) > 1
                    or not isinstance(recipients[0].value, str) or not recipients[0].value
                    or (len(children) > 1 and not amounts)
                    or (amounts and (type(amounts[0].value) is not int
                                     or amounts[0].value <= 0))
                    or (sources and sources[0].value != account.value)):
                return _unsupported("payout requires one recipient, positive amount and matching source")
            payouts[parent_id].append((outcome, recipients[0], amounts[0] if amounts else amount,
                                       sources[0] if sources else None))
        if sum(item[2].value for item in payouts[parent_id]) != amount.value:
            return _unsupported("each payout branch must conserve the funded amount")
    success = [item for item in branches if any(payout[1].kind in {
        "payment_recipient", "release_recipient"} for payout in payouts[item.scope_id])]
    refund = [item for item in branches if all(payout[1].kind == "refund_recipient"
              for payout in payouts[item.scope_id])]
    if (len(success) != 1 or len(refund) != 1
            or len(payouts[refund[0].scope_id]) != 1
            or payouts[timeout.scope_id][0][1].kind != "refund_recipient"):
        return _unsupported("exactly one payout branch, one refund branch, and refund timeout required")
    success_branch, refund_branch = success[0], refund[0]
    intervals = [_guard_interval(item.source.get("choice_guard", {}), bounds["from"], bounds["to"])
                 for item in (success_branch, refund_branch)]
    if None in intervals:
        return _unsupported("branch guard outside Choice bounds")
    ordered = sorted(intervals)
    if (ordered[0][0] != bounds["from"] or ordered[1][1] != bounds["to"]
            or ordered[0][1] + 1 != ordered[1][0]):
        return _unsupported("Choice guards must partition the entire integer bound without overlap")
    expected_claim_ids = {item.claim_id for item in required}
    for children in payouts.values():
        for _, recipient, payout_amount, payout_source in children:
            expected_claim_ids.update((recipient.claim_id, payout_amount.claim_id))
            if payout_source is not None:
                expected_claim_ids.add(payout_source.claim_id)
    if source_account is not None:
        expected_claim_ids.add(source_account.claim_id)
    if expected_claim_ids != {item.claim_id for item in ir.claims}:
        return _unsupported("additional or duplicate claim outside funded-Choice profile")
    if len(ir.assets) != 1 or ir.assets[0].symbol != "ADA" or not ir.accounts:
        return _unsupported("one ADA asset and one funded account owner required")
    account_claim_ids = {account.claim_id}
    if source_account is not None:
        account_claim_ids.add(source_account.claim_id)
    account_claim_ids.update(source.claim_id for children in payouts.values()
                             for _, _, _, source in children if source is not None)
    actual_account_refs = [ref for item in ir.accounts
                           for ref in item.source.get("claim_refs", [])]
    if (any(item.owner != account.value or not item.source.get("claim_refs")
            for item in ir.accounts)
            or set(actual_account_refs) != account_claim_ids
            or len(actual_account_refs) != len(account_claim_ids)
            or asset.claim_id not in ir.assets[0].source.get("claim_refs", [])):
        return _unsupported("projected account or asset inconsistent with claims")

    role = lambda name: {"role_token": name}
    token = {"currency_symbol": "", "token_name": ""}
    choice_id = {"choice_name": choice.scope_id, "choice_owner": role(chooser.value)}

    choice_path = "$.when[0].then"
    success_path = choice_path + ".when[0].then.then"
    refund_path = choice_path + ".when[0].then.else"
    timeout_path = choice_path + ".timeout_continuation"
    claim_paths = {
        asset.claim_id: "$.when[0].case.of_token",
        amount.claim_id: "$.when[0].case.deposits",
        depositor.claim_id: "$.when[0].case.party",
        account.claim_id: "$.when[0].case.into_account",
        deposit_deadline.claim_id: "$.timeout",
        chooser.claim_id: choice_path + ".when[0].case.for_choice.choice_owner",
        choice_deadline.claim_id: choice_path + ".timeout",
    }
    scope_paths = {"global": "$.when[0].case.of_token", deposit.scope_id: "$",
                   choice.scope_id: choice_path, success_branch.scope_id: success_path,
                   refund_branch.scope_id: refund_path, timeout.scope_id: timeout_path}

    def payment_chain(parent_id: str, base_path: str) -> dict[str, Any]:
        continuation: Any = "close"
        # A branch continuation identifies the first payout. Remaining sibling
        # outcomes follow source order only when their exact sum is fully funded.
        for position in reversed(range(len(payouts[parent_id]))):
            outcome, recipient, payout_amount, payout_source = payouts[parent_id][position]
            path = base_path + ".then" * position
            scope_paths[outcome.scope_id] = path
            claim_paths[recipient.claim_id] = path + ".to.party"
            if payout_amount.claim_id != amount.claim_id:
                claim_paths[payout_amount.claim_id] = path + ".pay"
            if payout_source is not None:
                claim_paths[payout_source.claim_id] = path + ".from_account"
            continuation = {"pay": payout_amount.value, "from_account": role(account.value),
                            "to": {"party": role(recipient.value)}, "token": token,
                            "then": continuation}
        return continuation

    success_contract = payment_chain(success_branch.scope_id, success_path)
    refund_contract = payment_chain(refund_branch.scope_id, refund_path)
    timeout_contract = payment_chain(timeout.scope_id, timeout_path)
    contract = {
        "when": [{"case": {"party": role(depositor.value), "deposits": amount.value,
                            "of_token": token, "into_account": role(account.value)},
                  "then": {"when": [{"case": {"for_choice": choice_id,
                                                "choose_between": [{"from": bounds["from"],
                                                                    "to": bounds["to"]}]},
                                     "then": {"if": _observation(success_branch.source["choice_guard"],
                                                                  choice_id),
                                              "then": success_contract,
                                              "else": refund_contract}}],
                           "timeout": choice_deadline.value,
                           "timeout_continuation": timeout_contract}}],
        "timeout": deposit_deadline.value, "timeout_continuation": "close",
    }
    if source_account is not None:
        claim_paths[source_account.claim_id] = success_path + ".from_account"
    records: list[dict[str, str]] = []

    def add(kind: str, source_id: str, path: str) -> None:
        records.append({"source_kind": kind, "source_id": source_id, "ast_path": path})

    for item in ir.claims:
        add("claim", item.claim_id, claim_paths[item.claim_id])
    for item in ir.scopes:
        add("scope", item.scope_id, scope_paths[item.scope_id])
    for item in ir.participants:
        paths = [claim_paths[ref] for ref in item.claim_refs if ref in claim_paths]
        if not paths:
            return _unsupported("participant has no mapped claim")
        add("participants", item.participant_id, paths[0])
    add("assets", ir.assets[0].asset_id, "$.when[0].case.of_token")
    for item in ir.accounts:
        source_ref = next((ref for ref in item.source.get("claim_refs", [])
                           if ref in account_claim_ids and ref != account.claim_id), None)
        path = claim_paths[source_ref] if source_ref is not None else "$.when[0].case.into_account"
        add("accounts", item.account_id, path)
    for kind, items, id_field in (
        ("parameters", ir.parameters, "parameter_id"),
        ("states", ir.states, "state_id"),
        ("transitions", ir.transitions, "transition_id"),
        ("obligations_and_outcomes", ir.outcomes, "outcome_id"),
    ):
        for item in items:
            if kind == "states":
                path = "$" if item.state_id == "initial" else choice_path
            elif kind == "transitions":
                path = scope_paths.get(item.transition_id)
            elif kind == "obligations_and_outcomes":
                path = scope_paths.get(item.source.get("scope_id"))
            else:
                refs = item.source.get("claim_refs", [])
                path = next((claim_paths[ref] for ref in refs if ref in claim_paths), None)
            if path is None:
                return _unsupported(f"{kind} has no mapped AST path")
            add(kind, getattr(item, id_field), path)
    return CompileResult(CompileStatus.SUPPORTED, contract, tuple(records))
