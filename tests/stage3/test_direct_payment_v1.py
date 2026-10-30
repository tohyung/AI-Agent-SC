"""Offline direct-payment-v1 compiler/profile regressions."""

from copy import deepcopy
from dataclasses import replace

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import validate_intent_spec
from research.stage3.compiler import CompilerPort
from research.stage3.models import (CompileStatus, FundingRelationIR, ProfileMatchStatus)
from research.stage3.profile_compilers.direct_payment_v1 import (
    DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1)
from research.stage3.profiles import ProfileRegistry


def direct_payment_spec(recipient="Bob"):
    message = f"Pay 10 ADA from Alice account to {recipient}."

    def claim(claim_id, kind, value, scope, span, status="explicit"):
        item = {"claim_id": claim_id, "kind": kind, "value": value,
                "criticality": "financial", "status": status, "scope_id": scope,
                "evidence": [{"requirement_version": 1, "message_index": 0,
                              "span": span, "relation": "supports"}]}
        if status == "derived":
            item["normalization_basis"] = "1 ADA = 1000000 lovelace"
        return item

    return {
        "schema_version": "stage2b-shadow-v1",
        "requirement_history": [{"version": 1, "messages": [message]}],
        "participants": [
            {"participant_id": "party:Alice", "name": "Alice", "claim_refs": ["source"]},
            {"participant_id": f"party:{recipient}", "name": recipient,
             "claim_refs": ["recipient"]}],
        "assets_and_accounts": {
            "assets": [{"asset_id": "asset:ADA", "symbol": "ADA", "claim_refs": ["asset"]}],
            "accounts": [{"account_id": "account:Alice", "owner": "Alice",
                          "claim_refs": ["source"]}],
            "funding_relations": []},
        "parameters": [{"parameter_id": "payment-amount", "kind": "amount",
                        "normalized_value": 10000000, "unit": "lovelace",
                        "claim_refs": ["amount"]}],
        "states": [{"state_id": "initial", "claim_refs": []}],
        "transitions": [{"transition_id": "payment-1", "kind": "payment",
                         "actor": None, "deadline_parameter_id": None,
                         "transaction_submitter": None, "claim_refs": []}],
        "obligations_and_outcomes": [
            {"outcome_id": "payment-outcome", "kind": "payment", "recipient": recipient,
             "scope_id": "payment-1", "claim_refs": ["recipient"]}],
        "behavior_scopes": [{"scope_id": "global", "scope_type": "global"},
                            {"scope_id": "payment-1", "scope_type": "transition",
                             "transition_kind": "payment"}],
        "claims": [
            claim("source", "payment_source_account_owner", "Alice", "payment-1",
                  "Alice account"),
            claim("asset", "asset", "ADA", "global", "10 ADA"),
            claim("amount", "amount_lovelace", 10000000, "payment-1", "10 ADA", "derived"),
            claim("recipient", "payment_recipient", recipient, "payment-1", recipient)],
        "required_clarifications": [], "conflicts": [],
        "assumptions_and_provenance": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }


def accepted_artifact(spec):
    return ArtifactEnvelope("accepted-intent", "v1", "integration_fixture",
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.USER_ACCEPTED_INTENT,
                            {"accepted_spec": spec, "integration_only": True})


def compile_spec(spec, plugin=compile_direct_payment_v1):
    registry = ProfileRegistry([DIRECT_PAYMENT_PROFILE])
    return CompilerPort(registry, {("direct-payment", "v1"): plugin}).execute(
        [accepted_artifact(spec)], StageContext("integration-test"))


def _valid_ir():
    seen = []

    def capture(ir):
        seen.append(ir)
        return compile_direct_payment_v1(ir)

    result = compile_spec(direct_payment_spec(), capture)
    assert result.result.run_status == StageRunStatus.SUCCEEDED
    return seen[0]


def _replace_claim(ir, kind, **changes):
    return replace(ir, claims=tuple(replace(item, **changes) if item.kind == kind else item
                                    for item in ir.claims))


def test_valid_intent_profile_and_compiler_mapping_are_deterministic():
    spec = direct_payment_spec()
    assert validate_intent_spec(spec) == []
    match, profile, diagnostics = ProfileRegistry([DIRECT_PAYMENT_PROFILE]).match(spec)
    assert (match, profile, diagnostics) == (ProfileMatchStatus.EXACT_SUPPORTED_PROFILE,
                                             DIRECT_PAYMENT_PROFILE, [])
    first = compile_spec(spec)
    second = compile_spec(deepcopy(spec))
    assert first.result.run_status == StageRunStatus.SUCCEEDED
    assert first.result.semantic_status == CompileStatus.SUPPORTED.value
    contract = next(item for item in first.artifacts if item.artifact_type == "contract-candidate")
    repeated = next(item for item in second.artifacts if item.artifact_type == "contract-candidate")
    assert contract.artifact_id == repeated.artifact_id
    assert contract.payload["contract"] == {
        "pay": 10000000, "from_account": {"role_token": "Alice"},
        "to": {"party": {"role_token": "Bob"}},
        "token": {"currency_symbol": "", "token_name": ""}, "then": "close"}
    assert first.result.input_artifacts == [accepted_artifact(spec).artifact_id]
    ir = _valid_ir()
    assert compile_direct_payment_v1(ir).to_dict() == compile_direct_payment_v1(ir).to_dict()
    mapped = {(item["source_kind"], item["source_id"])
              for item in contract.payload["mapping_evidence"]}
    assert {"claim", "scope", "participants", "assets", "accounts", "parameters",
            "states", "transitions", "obligations_and_outcomes"} == {
                kind for kind, _ in mapped}
    assert len(mapped) == 14


@pytest.mark.parametrize(("mutation", "status"), [
    (lambda ir: replace(ir, claims=tuple(item for item in ir.claims
                                         if item.kind != "payment_recipient")),
     CompileStatus.UNSUPPORTED_FEATURE),
    (lambda ir: replace(ir, claims=ir.claims +
                        (replace(next(item for item in ir.claims
                                      if item.kind == "payment_recipient"),
                                 claim_id="recipient-2"),)), CompileStatus.AMBIGUOUS_MAPPING),
    (lambda ir: replace(ir, claims=ir.claims +
                        (replace(next(item for item in ir.claims
                                      if item.kind == "amount_lovelace"),
                                 claim_id="amount-2"),)), CompileStatus.AMBIGUOUS_MAPPING),
    (lambda ir: _replace_claim(ir, "amount_lovelace", value=0),
     CompileStatus.UNSUPPORTED_FEATURE),
    (lambda ir: _replace_claim(ir, "asset", value="OTHER"),
     CompileStatus.UNSUPPORTED_FEATURE),
    (lambda ir: replace(ir, accounts=(replace(ir.accounts[0], owner="Carol"),)),
     CompileStatus.UNSUPPORTED_FEATURE),
    (lambda ir: replace(ir, outcomes=(replace(ir.outcomes[0], source={
        **ir.outcomes[0].source, "recipient": "Carol"}),)),
     CompileStatus.UNSUPPORTED_FEATURE),
    (lambda ir: replace(ir, funding_relations=(FundingRelationIR(
        "funding-1", "payment-1", "Alice", "Alice", "asset:ADA", {}),)),
     CompileStatus.UNSUPPORTED_FEATURE),
    (lambda ir: replace(ir, states=ir.states + (replace(
        ir.states[0], state_id="paid", source={"state_id": "paid", "claim_refs": ["recipient"]}),)),
     CompileStatus.UNSUPPORTED_FEATURE),
])
def test_rejects_ambiguous_or_unsupported_ir(mutation, status):
    assert compile_direct_payment_v1(mutation(_valid_ir())).status == status


def test_wrong_asset_rejected_at_profile_boundary():
    spec = direct_payment_spec()
    spec["assets_and_accounts"]["assets"][0]["symbol"] = "OTHER"
    match, _, _ = ProfileRegistry([DIRECT_PAYMENT_PROFILE]).match(spec)
    assert match == ProfileMatchStatus.UNSUPPORTED_PROFILE


def test_recipient_change_changes_generated_contract():
    spec = direct_payment_spec("Carol")
    assert validate_intent_spec(spec) == []
    result = compile_spec(spec)
    assert result.result.run_status == StageRunStatus.SUCCEEDED
    contract = next(item for item in result.artifacts if item.artifact_type == "contract-candidate")
    assert contract.payload["contract"]["to"]["party"]["role_token"] == "Carol"


