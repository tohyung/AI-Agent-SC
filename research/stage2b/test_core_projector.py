"""Core authority and deterministic projection, without provider calls."""

from __future__ import annotations

from copy import deepcopy

import pytest

from research.stage2b.intent_spec import (
    CORE_FIELDS, CORE_SCHEMA_VERSION, extract_core_view, validate_intent_spec,
    validate_shadow_semantic_core,
)
from research.stage2b.projector import classify_projection, project_intent_spec
from research.stage2b.ablation import ablate
from research.stage2b.test_intent_spec import simple_payment


def core():
    return extract_core_view(deepcopy(simple_payment()))


def projected(source):
    return project_intent_spec(source)


def test_valid_core_closed_schema_and_full_validator_reuse():
    source = core()
    assert set(source) == CORE_FIELDS
    assert source["schema_version"] == CORE_SCHEMA_VERSION
    assert validate_shadow_semantic_core(source) == []
    source["participants"] = []
    assert "unknown top-level fields" in " ".join(validate_shadow_semantic_core(source))
    source.pop("participants")
    source["claims"][0]["scope_id"] = "missing"
    assert "scope_id not found" in " ".join(validate_shadow_semantic_core(source))
    assert "scope_id not found" in " ".join(validate_intent_spec(
        projected(source).intent_spec.to_dict()))


def test_malformed_kind_reports_error_without_type_error():
    source = core()
    source["claims"][0]["kind"] = []
    assert "unknown claim kind" in " ".join(validate_shadow_semantic_core(source))
    assert "unknown claim kind" in " ".join(validate_intent_spec(
        projected(source).intent_spec.data))


@pytest.mark.parametrize(("mutation", "fragment"), [
    (lambda c: c["behavior_scopes"][0].update(scope_type="transition", transition_kind="deposit"),
     "scope global: scope_type must be global"),
    (lambda c: c["claims"][3].update(derived_from="asset"), "invalid derived_from"),
    (lambda c: c.update(predicted_resolution="clarification_required"), "business question"),
    (lambda c: c["claims"][0].update(kind="invented"), "unknown claim kind"),
])
def test_core_semantic_preconditions(mutation, fragment):
    source = core()
    mutation(source)
    assert fragment in " ".join(validate_shadow_semantic_core(source))


def test_conflict_and_assumption_have_only_atomic_authority():
    source = core()
    recipient = source["claims"][-1]
    recipient["status"] = "conflicted"
    other = deepcopy(recipient)
    other.update(claim_id="recipient-other", value="Alice")
    other["evidence"][0]["span"] = "Alice"
    source["claims"].append(other)
    source["predicted_resolution"] = "conflict_requires_resolution"
    source["required_clarifications"] = ["Bob hay Alice nhận tiền?"]
    assert validate_shadow_semantic_core(source) == []
    result = projected(source)
    assert result.intent_spec.data["conflicts"] == [{
        "conflict_id": "conflict:payment_recipient:payout-1",
        "kind": "payment_recipient", "scope_id": "payout-1",
        "claim_refs": ["recipient", "recipient-other"]}]
    assert result.intent_spec.data["obligations_and_outcomes"] == []
    assert validate_intent_spec(result.intent_spec.data, projected_core=source) == []
    source["claims"][-1]["status"] = "assumed"
    source["claims"][-1]["assumption_reason"] = "Not confirmed"
    assert "conflicting values" in " ".join(validate_shadow_semantic_core(source))


def test_assumption_metadata_is_derived_not_authority():
    source = core()
    claim = source["claims"][-1]
    claim.update(status="assumed", evidence=[], assumption_reason="Recipient not confirmed")
    source["predicted_resolution"] = "clarification_required"
    source["required_clarifications"] = ["Ai nhận tiền?"]
    result = projected(source)
    assert result.intent_spec.data["assumptions_and_provenance"] == [{
        "assumption_id": "assumption:recipient", "text": "Recipient not confirmed",
        "claim_refs": ["recipient"]}]
    assert result.intent_spec.data["obligations_and_outcomes"] == []
    assert validate_intent_spec(result.intent_spec.data, projected_core=source) == []


def test_projection_deterministic_nonmutating_and_order_independent():
    source = core()
    before = deepcopy(source)
    first = projected(source)
    assert projected(source).intent_spec.data == first.intent_spec.data
    assert source == before
    reversed_source = deepcopy(source)
    reversed_source["claims"].reverse()
    assert projected(reversed_source).intent_spec.data["participants"] == first.intent_spec.data["participants"]
    for section in ("parameters", "transitions", "obligations_and_outcomes"):
        assert projected(reversed_source).intent_spec.data[section] == first.intent_spec.data[section]
    assert len(first.intent_spec.data["states"]) == 1
    assert first.intent_spec.data["states"][0]["state_id"] == "initial"
    assert all("hash" not in item["participant_id"] and "uuid" not in item["participant_id"]
               for item in first.intent_spec.data["participants"])


def test_asset_depositor_and_choice_owner_do_not_invent_accounts_or_submitter():
    source = core()
    source["claims"] = [claim for claim in source["claims"] if claim["claim_id"] != "account"]
    result = projected(source)
    assert result.intent_spec.data["assets_and_accounts"]["assets"]
    assert result.intent_spec.data["assets_and_accounts"]["accounts"] == []
    assert result.intent_spec.data["assets_and_accounts"]["funding_relations"] == []
    assert all(item["transaction_submitter"] is None for item in result.intent_spec.data["transitions"])
    assert any(fact["not_projected_reason"] == "insufficient_relational_evidence"
               for fact in result.projection_diagnostics["facts"])


@pytest.mark.parametrize(("kind", "outcome_kind"), [
    ("payment_recipient", "payment"), ("refund_recipient", "refund"),
    ("release_recipient", "release"),
])
def test_scoped_recipient_projects_mandatory_outcome(kind, outcome_kind):
    source = core()
    source["claims"][-1]["kind"] = kind
    result = projected(source)
    outcome = result.intent_spec.data["obligations_and_outcomes"][0]
    assert (outcome["kind"], outcome["recipient"], outcome["scope_id"]) == (
        outcome_kind, "Bob", "payout-1")
    assert result.projection_diagnostics["coverage"]["outcome"] == {
        "eligible_count": 1, "projected_count": 1, "omitted_count": 0}
    assert validate_intent_spec(result.intent_spec.data, projected_core=source) == []


def test_duplicate_backing_for_same_outcome_is_one_semantic_projection():
    source = core()
    duplicate = deepcopy(source["claims"][-1])
    duplicate["claim_id"] = "recipient-second"
    source["claims"].append(duplicate)
    result = projected(source)
    assert len(result.intent_spec.data["obligations_and_outcomes"]) == 1
    assert result.intent_spec.data["obligations_and_outcomes"][0]["claim_refs"] == [
        "recipient", "recipient-second"]
    assert result.projection_diagnostics["coverage"]["outcome"]["eligible_count"] == 2
    assert validate_intent_spec(result.intent_spec.data, projected_core=source) == []


@pytest.mark.parametrize("status", ["unresolved", "assumed"])
def test_unresolved_or_assumed_recipient_has_no_authoritative_outcome(status):
    source = core()
    claim = source["claims"][-1]
    claim.update(status=status, value=None if status == "unresolved" else "Bob", evidence=[])
    if status == "assumed":
        claim["assumption_reason"] = "Unknown"
    source["predicted_resolution"] = "clarification_required"
    source["required_clarifications"] = ["Ai nhận tiền?"]
    result = projected(source)
    assert result.intent_spec.data["obligations_and_outcomes"] == []
    assert result.projection_diagnostics["coverage"]["outcome"]["eligible_count"] == 0


def test_transition_actor_and_deadline_require_compatible_same_scope_claims():
    source = core()
    source["requirement_history"][0]["messages"][0] += " Trước 1000 ms."
    source["claims"].append({
        "claim_id": "deadline", "kind": "deposit_deadline_ms", "value": 1000,
        "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": "1000 ms", "relation": "supports"}],
    })
    result = projected(source)
    deposit = next(item for item in result.intent_spec.data["transitions"]
                   if item["transition_id"] == "deposit-1")
    assert deposit["actor"] == "Alice"
    assert deposit["deadline_parameter_id"] == "parameter:deadline"
    payout = next(item for item in result.intent_spec.data["transitions"]
                  if item["transition_id"] == "payout-1")
    assert payout["actor"] is None and payout["deadline_parameter_id"] is None
    source["claims"][0]["scope_id"] = "payout-1"
    assert next(item for item in projected(source).intent_spec.data["transitions"]
                if item["transition_id"] == "deposit-1")["actor"] is None


def test_ambiguous_deadline_and_actor_do_not_choose_arbitrarily():
    source = core()
    source["behavior_scopes"].append({"scope_id": "decision-1", "scope_type": "transition",
                                      "transition_kind": "choice"})
    source["requirement_history"][0]["messages"][0] += " Chọn trước 1000 ms; timeout 2000 ms."
    for claim_id, kind, value, span in (
        ("choice-deadline", "choice_deadline_ms", 1000, "1000 ms"),
        ("choice-timeout", "timeout_ms", 2000, "2000 ms"),
    ):
        source["claims"].append({"claim_id": claim_id, "kind": kind, "value": value,
            "criticality": "financial", "status": "explicit", "scope_id": "decision-1",
            "evidence": [{"requirement_version": 1, "message_index": 0,
                          "span": span, "relation": "supports"}]})
    result = projected(source)
    decision = next(item for item in result.intent_spec.data["transitions"]
                    if item["transition_id"] == "decision-1")
    assert decision["deadline_parameter_id"] is None
    assert any(f["not_projected_reason"] == "ambiguous_deadline"
               for f in result.projection_diagnostics["facts"])


def test_conflicted_choice_owners_report_ambiguous_actor():
    source = core()
    source["behavior_scopes"].append({"scope_id": "decision-1", "scope_type": "transition",
                                      "transition_kind": "choice"})
    for claim_id, value, span in (("owner-a", "Alice", "Alice"),
                                  ("owner-b", "Bob", "Bob")):
        source["claims"].append({"claim_id": claim_id, "kind": "choice_owner",
            "value": value, "criticality": "financial", "status": "conflicted",
            "scope_id": "decision-1", "evidence": [{"requirement_version": 1,
            "message_index": 0, "span": span, "relation": "supports"}]})
    source["predicted_resolution"] = "conflict_requires_resolution"
    source["required_clarifications"] = ["Ai có quyền chọn?"]
    assert validate_shadow_semantic_core(source) == []
    result = projected(source)
    decision = next(item for item in result.intent_spec.data["transitions"]
                    if item["transition_id"] == "decision-1")
    assert decision["actor"] is None
    assert any(f["not_projected_reason"] == "ambiguous_actor"
               for f in result.projection_diagnostics["facts"])


def test_coexisting_depositor_account_and_asset_do_not_prove_funding_relation():
    source = core()
    source["claims"][2]["scope_id"] = "deposit-1"
    assert validate_shadow_semantic_core(source) == []
    result = projected(source)
    assert result.intent_spec.data["assets_and_accounts"]["funding_relations"] == []
    assert any(f["not_projected_reason"] == "insufficient_relational_evidence"
               for f in result.projection_diagnostics["facts"])


def test_strict_full_projection_coverage_and_bug_classification():
    source = core()
    result = projected(source)
    assert result.projection_diagnostics["complete"]
    assert validate_intent_spec(result.intent_spec.data, projected_core=source) == []
    broken = deepcopy(result.intent_spec.data)
    broken["obligations_and_outcomes"] = []
    errors = validate_intent_spec(broken, projected_core=source)
    assert any("missing mandatory obligations_and_outcomes" in error for error in errors)
    assert classify_projection([], errors, result.projection_diagnostics) == "PROJECTOR_BUG"
    source["claims"][0]["scope_id"] = "missing"
    assert classify_projection(validate_shadow_semantic_core(source), errors,
                               result.projection_diagnostics) == "CORE_INVALID"


def test_no_eligible_outcome_is_not_coverage_failure():
    source = core()
    source["claims"] = [claim for claim in source["claims"] if claim["claim_id"] != "recipient"]
    result = projected(source)
    assert result.projection_diagnostics["coverage"]["outcome"]["eligible_count"] == 0
    assert result.projection_diagnostics["complete"]


def test_ablation_utility_accepts_arbitrary_historical_prediction(tmp_path):
    import json

    path = tmp_path / "historical.jsonl"
    path.write_text(json.dumps({"case_id": "synthetic", "prediction": simple_payment(),
                                "validation_errors": []}) + "\n", encoding="utf-8")
    summary = ablate(path)
    assert summary["case_count"] == 1
    assert summary["core_valid_count"] == 1
    assert summary["projected_full_valid_count"] == 1
