"""One funded ADA role account pays one amount to one role recipient.

Names map to Marlowe role-token text only within this research profile. This
does not establish wallet identity, address ownership, or ledger authority.
"""

from __future__ import annotations

from typing import Any

from research.stage3.models import (CompilationIR, CompileResult, CompileStatus,
                                    SupportedProfile)


DIRECT_PAYMENT_PROFILE = SupportedProfile(
    profile_id="direct-payment", version="v1",
    compiler_id="deterministic-direct-payment", compiler_version="0.1.0",
    intent_schema_version="stage2b-shadow-v1",
    claim_kinds=frozenset({"payment_source_account_owner", "payment_recipient",
                           "amount_lovelace", "asset"}),
    scope_types=frozenset({"global", "transition"}),
    transition_kinds=frozenset({"payment"}),
    supported_assets=frozenset({"ADA"}),
)


def _unsupported(reason: str) -> CompileResult:
    return CompileResult(CompileStatus.UNSUPPORTED_FEATURE, diagnostics=(reason,))


def _mapping(ir: CompilationIR) -> tuple[dict[str, str], ...]:
    claim_paths = {"payment_source_account_owner": "$.from_account",
                   "payment_recipient": "$.to.party",
                   "amount_lovelace": "$.pay", "asset": "$.token"}
    records: list[dict[str, str]] = []

    def add(kind: str, source_id: str, path: str) -> None:
        records.append({"source_kind": kind, "source_id": source_id, "ast_path": path})

    for item in sorted(ir.claims, key=lambda value: value.claim_id):
        add("claim", item.claim_id, claim_paths[item.kind])
    for item in sorted(ir.scopes, key=lambda value: value.scope_id):
        add("scope", item.scope_id, "$.token" if item.scope_type == "global" else "$")
    source = next(item.value for item in ir.claims
                  if item.kind == "payment_source_account_owner")
    for item in sorted(ir.participants, key=lambda value: value.participant_id):
        add("participants", item.participant_id,
            "$.from_account" if item.name == source else "$.to.party")
    for item in sorted(ir.assets, key=lambda value: value.asset_id):
        add("assets", item.asset_id, "$.token")
    for item in sorted(ir.accounts, key=lambda value: value.account_id):
        add("accounts", item.account_id, "$.from_account")
    for item in sorted(ir.parameters, key=lambda value: value.parameter_id):
        add("parameters", item.parameter_id, "$.pay")
    for item in sorted(ir.states, key=lambda value: value.state_id):
        add("states", item.state_id, "$" if item.state_id == "initial" else "$.then")
    for item in sorted(ir.transitions, key=lambda value: value.transition_id):
        add("transitions", item.transition_id, "$")
    for item in sorted(ir.outcomes, key=lambda value: value.outcome_id):
        add("obligations_and_outcomes", item.outcome_id, "$.to.party")
    return tuple(records)


def compile_direct_payment_v1(ir: CompilationIR) -> CompileResult:
    """Lower only the exact direct-payment-v1 IR shape; reject all other shapes."""
    if (ir.profile_id, ir.profile_version) != (DIRECT_PAYMENT_PROFILE.profile_id,
                                                DIRECT_PAYMENT_PROFILE.version):
        return _unsupported("profile identity unsupported")
    kinds = DIRECT_PAYMENT_PROFILE.claim_kinds
    if any(item.kind not in kinds or item.status not in {"explicit", "derived", "user_confirmed"}
           for item in ir.claims):
        return _unsupported("claim kind or status outside direct-payment-v1")
    groups = {kind: [item for item in ir.claims if item.kind == kind] for kind in kinds}
    if any(len(items) > 1 for items in groups.values()):
        return CompileResult(CompileStatus.AMBIGUOUS_MAPPING,
                             diagnostics=("multiple active direct-payment claims",))
    if any(len(items) != 1 for items in groups.values()) or len(ir.claims) != 4:
        return _unsupported("exactly one claim of each supported kind is required")
    source_claim = groups["payment_source_account_owner"][0]
    recipient_claim = groups["payment_recipient"][0]
    amount_claim = groups["amount_lovelace"][0]
    asset_claim = groups["asset"][0]
    source, recipient, amount = source_claim.value, recipient_claim.value, amount_claim.value
    if (not isinstance(source, str) or not source or not isinstance(recipient, str)
            or not recipient or source == recipient):
        return _unsupported("distinct source and recipient role names required")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _unsupported("positive integer lovelace amount required")
    if asset_claim.value != "ADA" or asset_claim.status not in {"explicit", "user_confirmed"}:
        return _unsupported("explicit ADA asset required")
    if (len(ir.scopes) != 2
            or sum(item.scope_type == "global" and item.scope_id == "global"
                   for item in ir.scopes) != 1):
        return _unsupported("one global and one payment transition scope required")
    payment_scopes = [item for item in ir.scopes if item.scope_type == "transition"
                      and item.transition_kind == "payment"]
    if len(payment_scopes) != 1:
        return _unsupported("one payment transition scope required")
    scope_id = payment_scopes[0].scope_id
    if (any(item.scope_id != scope_id for item in
            (source_claim, recipient_claim, amount_claim))
            or asset_claim.scope_id != "global"
            or any(item.source.get("decision_id") or item.source.get("timeout_id")
                   or item.source.get("deadline_claim_id") for item in ir.scopes)):
        return _unsupported("claim scopes or transition semantics unsupported")
    if ir.funding_relations:
        return _unsupported("funding relations unsupported")
    if (len(ir.assets) != 1 or ir.assets[0].symbol != "ADA"
            or asset_claim.claim_id not in ir.assets[0].source.get("claim_refs", [])):
        return _unsupported("ADA asset projection inconsistent")
    if (len(ir.accounts) != 1 or ir.accounts[0].owner != source
            or source_claim.claim_id not in ir.accounts[0].source.get("claim_refs", [])):
        return _unsupported("source account owner projection inconsistent")
    if (len(ir.participants) != 2 or {item.name for item in ir.participants} != {source, recipient}
            or not any(item.name == source and source_claim.claim_id in item.claim_refs
                       for item in ir.participants)
            or not any(item.name == recipient and recipient_claim.claim_id in item.claim_refs
                       for item in ir.participants)):
        return _unsupported("participant projection inconsistent")
    if (len(ir.parameters) != 1 or ir.parameters[0].source.get("kind") != "amount"
            or ir.parameters[0].source.get("normalized_value") != amount
            or ir.parameters[0].source.get("unit") != "lovelace"
            or amount_claim.claim_id not in ir.parameters[0].source.get("claim_refs", [])):
        return _unsupported("amount parameter projection inconsistent")
    if (len(ir.states) != 2 or {item.state_id for item in ir.states} != {"initial", "paid"}
            or not any(item.state_id == "paid" and recipient_claim.claim_id in
                       item.source.get("claim_refs", []) for item in ir.states)):
        return _unsupported("state projection inconsistent")
    if (len(ir.transitions) != 1 or ir.transitions[0].transition_id != scope_id
            or ir.transitions[0].source.get("kind") != "payment"
            or any(ir.transitions[0].source.get(key) is not None for key in
                   ("actor", "deadline_parameter_id", "transaction_submitter"))
            or ir.transitions[0].source.get("claim_refs")):
        return _unsupported("payment transition projection inconsistent")
    if (len(ir.outcomes) != 1 or ir.outcomes[0].source.get("kind") != "payment"
            or ir.outcomes[0].source.get("scope_id") != scope_id
            or ir.outcomes[0].source.get("recipient") != recipient
            or recipient_claim.claim_id not in ir.outcomes[0].source.get("claim_refs", [])):
        return _unsupported("payment outcome projection inconsistent")

    # Direct-payment-v1 treats ADA as the empty currency/token pair and names as role text.
    role = lambda name: {"role_token": name}
    token: dict[str, Any] = {"currency_symbol": "", "token_name": ""}
    contract = {"pay": amount, "from_account": role(source),
                "to": {"party": role(recipient)}, "token": token, "then": "close"}
    return CompileResult(CompileStatus.SUPPORTED, contract, _mapping(ir))
