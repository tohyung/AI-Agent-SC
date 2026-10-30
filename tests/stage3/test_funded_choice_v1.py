"""Offline family-level lowering tests for funded numeric Choice contracts."""

from copy import deepcopy

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2, validate_intent_spec
from research.stage2b.projector import project_intent_spec
from research.stage3.compiler import CompilerPort
from research.stage3.profile_compilers.funded_choice_v1 import (
    FUNDED_CHOICE_PROFILE, _guard_interval, compile_funded_choice_v1,
)
from research.stage3.profiles import ProfileRegistry


def funded_choice_core():
    message = (
        "Bob deposits 20 ADA into Bob's account before 03/01/2027. "
        "Alice chooses 0 to 100 before 10/01/2027. "
        "At least 50 pays Carol; below 50 refunds Bob. "
        "Without a choice before 10/01/2027 refund Bob."
    )

    def evidence(span):
        return [{"requirement_version": 1, "message_index": 0,
                 "span": span, "relation": "supports"}]

    def claim(claim_id, kind, value, scope_id, span, status="explicit"):
        result = {"claim_id": claim_id, "kind": kind, "value": value,
                  "criticality": "financial", "status": status,
                  "scope_id": scope_id, "evidence": evidence(span)}
        if status == "derived":
            result["normalization_basis"] = "1 ADA = 1000000 lovelace"
        return result

    return {
        "schema_version": CORE_SCHEMA_VERSION_V2,
        "requirement_history": [{"version": 1, "messages": [message]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit",
             "continuation_scope_id": "choice"},
            {"scope_id": "choice", "scope_type": "transition", "transition_kind": "choice",
             "choice_bounds": {"from": 0, "to": 100,
                               "source_evidence": evidence("0 to 100")}},
            {"scope_id": "high", "scope_type": "branch", "decision_id": "choice",
             "branch_id": "high", "continuation_scope_id": "paid",
             "choice_guard": {"operator": "ge", "value": 50,
                              "source_evidence": evidence("At least 50")}},
            {"scope_id": "low", "scope_type": "branch", "decision_id": "choice",
             "branch_id": "low", "continuation_scope_id": "refunded",
             "choice_guard": {"operator": "lt", "value": 50,
                              "source_evidence": evidence("below 50")}},
            {"scope_id": "choice-timeout", "scope_type": "timeout", "decision_id": "choice",
             "timeout_id": "choice-timeout", "deadline_claim_id": "choice-deadline",
             "continuation_scope_id": "timeout-refund"},
            {"scope_id": "paid", "scope_type": "terminal_outcome",
             "outcome_id": "paid", "parent_scope_id": "high"},
            {"scope_id": "refunded", "scope_type": "terminal_outcome",
             "outcome_id": "refunded", "parent_scope_id": "low"},
            {"scope_id": "timeout-refund", "scope_type": "terminal_outcome",
             "outcome_id": "timeout-refund", "parent_scope_id": "choice-timeout"},
        ],
        "claims": [
            claim("asset", "asset", "ADA", "global", "20 ADA"),
            claim("amount", "amount_lovelace", 20000000, "deposit", "20 ADA", "derived"),
            claim("depositor", "depositing_party", "Bob", "deposit", "Bob deposits"),
            claim("account", "destination_account_owner", "Bob", "deposit", "Bob's account"),
            claim("deposit-deadline", "deposit_deadline_ms", 1798934400000,
                  "deposit", "before 03/01/2027"),
            claim("chooser", "choice_owner", "Alice", "choice", "Alice chooses"),
            claim("choice-deadline", "choice_deadline_ms", 1799539200000,
                  "choice", "before 10/01/2027"),
            claim("recipient", "payment_recipient", "Carol", "paid", "pays Carol"),
            claim("refund", "refund_recipient", "Bob", "refunded", "refunds Bob"),
            claim("timeout-refund", "refund_recipient", "Bob", "timeout-refund",
                  "refund Bob"),
        ],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }


def _compile(core):
    spec = project_intent_spec(core).intent_spec.to_dict()
    assert validate_intent_spec(spec, projected_core=core) == []
    accepted = ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"accepted_spec": spec, "simulation_only": True})
    port = CompilerPort(ProfileRegistry([FUNDED_CHOICE_PROFILE]),
                        {("funded-choice", "v1"): compile_funded_choice_v1})
    return port.execute([accepted], StageContext("test", {"allow_simulated_intent": True}))


def test_funded_choice_compiles_with_explicit_causal_graph_and_mapping():
    result = _compile(funded_choice_core())
    assert result.result.run_status == StageRunStatus.SUCCEEDED, result.result.diagnostics
    contract_artifact = next(item for item in result.artifacts
                             if item.artifact_type == "contract-candidate")
    contract = contract_artifact.payload["contract"]
    assert contract_artifact.payload["simulation_only"] is True
    assert contract["when"][0]["then"]["when"][0]["then"]["if"]["ge_than"] == 50
    assert contract["when"][0]["then"]["timeout_continuation"]["to"]["party"] == {
        "role_token": "Bob"}


def test_funded_choice_rejects_gap_in_integer_guards():
    core = funded_choice_core()
    next(scope for scope in core["behavior_scopes"] if scope["scope_id"] == "low")[
        "choice_guard"]["value"] = 40
    result = _compile(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED
    assert "partition" in " ".join(result.result.diagnostics)


def test_funded_choice_rejects_missing_timeout_continuation():
    core = deepcopy(funded_choice_core())
    core["behavior_scopes"] = [scope for scope in core["behavior_scopes"]
                               if scope["scope_id"] not in {"choice-timeout", "timeout-refund"}]
    core["claims"] = [claim for claim in core["claims"]
                      if claim["claim_id"] != "timeout-refund"]
    result = _compile(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED


def test_funded_choice_rejects_malformed_guard_without_exception():
    assert _guard_interval(None, 0, 100) is None


def _shared_scope_core():
    core = deepcopy(funded_choice_core())
    core["requirement_history"].append({
        "version": 2,
        "messages": ["Bob's account is the payment source for payout and refunds."],
    })
    amount = next(item for item in core["claims"] if item["claim_id"] == "amount")
    amount["scope_id"] = "global"
    recipient_scopes = {"paid": "high", "refunded": "low", "timeout-refund": "choice-timeout"}
    for item in core["claims"]:
        if item["scope_id"] in recipient_scopes:
            item["scope_id"] = recipient_scopes[item["scope_id"]]
    core["claims"].append({
        "claim_id": "payment-source", "kind": "payment_source_account_owner",
        "value": "Bob", "criticality": "financial", "status": "explicit",
        "scope_id": "global",
        "evidence": [{"requirement_version": 2, "message_index": 0,
                      "span": "Bob's account is the payment source",
                      "relation": "supports"}],
    })
    return core


def split_payout_core():
    core = deepcopy(funded_choice_core())
    core["requirement_history"].append({
        "version": 2,
        "messages": ["At least 50 pays Carol 3 ADA and refunds Bob 17 ADA."],
    })
    scopes = core["behavior_scopes"]
    paid_index = next(index for index, item in enumerate(scopes) if item["scope_id"] == "paid")
    scopes.insert(paid_index + 1, {"scope_id": "remainder", "scope_type": "terminal_outcome",
                                   "outcome_id": "remainder", "parent_scope_id": "high"})
    evidence = lambda span: [{"requirement_version": 2, "message_index": 0,
                              "span": span, "relation": "supports"}]
    core["claims"].extend([
        {"claim_id": "carol-amount", "kind": "amount_lovelace", "value": 3000000,
         "criticality": "financial", "status": "derived", "scope_id": "paid",
         "normalization_basis": "1 ADA = 1000000 lovelace",
         "evidence": evidence("Carol 3 ADA")},
        {"claim_id": "bob-remainder", "kind": "amount_lovelace", "value": 17000000,
         "criticality": "financial", "status": "derived", "scope_id": "remainder",
         "normalization_basis": "1 ADA = 1000000 lovelace",
         "evidence": evidence("Bob 17 ADA")},
        {"claim_id": "bob-recipient", "kind": "refund_recipient", "value": "Bob",
         "criticality": "financial", "status": "explicit", "scope_id": "remainder",
         "evidence": evidence("refunds Bob")},
    ])
    return core


def test_funded_choice_accepts_unambiguous_shared_amount_and_parent_scoped_recipients():
    result = _compile(_shared_scope_core())
    assert result.result.run_status == StageRunStatus.SUCCEEDED, result.result.diagnostics
    contract = next(item for item in result.artifacts if item.artifact_type == "contract-candidate")
    assert contract.payload["contract"]["when"][0]["case"]["deposits"] == 20000000
    assert any(item["source_id"] == "payment-source"
               for item in contract.payload["mapping_evidence"])


def test_funded_choice_rejects_mismatched_payment_source_account_owner():
    core = _shared_scope_core()
    next(item for item in core["claims"] if item["claim_id"] == "payment-source")["value"] = "Alice"
    result = _compile(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED


def test_funded_choice_lowers_fully_funded_split_payout_in_scope_order():
    result = _compile(split_payout_core())
    assert result.result.run_status == StageRunStatus.SUCCEEDED, result.result.diagnostics
    artifact = next(item for item in result.artifacts if item.artifact_type == "contract-candidate")
    payout = artifact.payload["contract"]["when"][0]["then"]["when"][0]["then"]["then"]
    assert payout["pay"] == 3000000
    assert payout["to"]["party"] == {"role_token": "Carol"}
    assert payout["then"]["pay"] == 17000000
    assert payout["then"]["to"]["party"] == {"role_token": "Bob"}
    assert payout["then"]["then"] == "close"
    mapped = {item["source_id"] for item in artifact.payload["mapping_evidence"]}
    assert {"carol-amount", "bob-remainder", "bob-recipient", "remainder"} <= mapped


def test_funded_choice_rejects_split_payout_that_overdraws_deposit():
    core = split_payout_core()
    next(item for item in core["claims"] if item["claim_id"] == "bob-remainder")[
        "value"] = 18000000
    result = _compile(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED
    assert "conserve" in " ".join(result.result.diagnostics)
