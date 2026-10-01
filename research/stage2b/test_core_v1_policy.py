"""Versioned unsupported and transition policies for native core-v1."""

from __future__ import annotations

from copy import deepcopy

import pytest

from research.stage2a import foundation
from research.stage2b.intent_spec import (
    TRANSITION_KINDS, UNSUPPORTED_SIGNALS_V1, core_prompt_schema_contract,
    validate_shadow_semantic_core,
)
from research.stage2b.projector import project_intent_spec
from research.stage2b.test_core_projector import core


def autonomous_refund_core():
    message = ("Đúng POSIX 22000 ms, hợp đồng tự động hoàn 3 ADA cho Lan "
               "dù không ai gửi giao dịch.")
    evidence = lambda span: [{"requirement_version": 1, "message_index": 0,
                              "span": span, "relation": "supports"}]
    return {
        "schema_version": "stage2b-shadow-core-v1",
        "requirement_history": [{"version": 1, "messages": [message]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "auto-refund-timeout-1", "scope_type": "timeout",
             "timeout_id": "refund-deadline-1"},
        ],
        "claims": [
            {"claim_id": "auto", "kind": "autonomous_execution", "value": True,
             "criticality": "financial", "status": "explicit",
             "scope_id": "auto-refund-timeout-1", "evidence": evidence("tự động hoàn 3 ADA")},
            {"claim_id": "refund", "kind": "refund_recipient", "value": "Lan",
             "criticality": "financial", "status": "explicit",
             "scope_id": "auto-refund-timeout-1", "evidence": evidence("hoàn 3 ADA cho Lan")},
            {"claim_id": "amount", "kind": "amount_lovelace", "value": 3000000,
             "criticality": "financial", "status": "derived",
             "scope_id": "auto-refund-timeout-1", "evidence": evidence("3 ADA"),
             "normalization_basis": "1 ADA = 1000000 lovelace"},
            {"claim_id": "asset", "kind": "asset", "value": "ADA",
             "criticality": "financial", "status": "explicit",
             "scope_id": "global", "evidence": evidence("3 ADA")},
        ],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "unsupported_for_current_study",
    }


def test_v1_unsupported_signal_is_explicit_and_escrow_style_core_passes():
    assert UNSUPPORTED_SIGNALS_V1 == {("autonomous_execution", True)}
    source = autonomous_refund_core()
    assert validate_shadow_semantic_core(source) == []
    assert project_intent_spec(source).projection_diagnostics["core_status"] == "valid"


@pytest.mark.parametrize("resolution", ["accepted_interpretation", "clarification_required"])
def test_authoritative_autonomous_true_cannot_be_accepted_or_generic_clarification(resolution):
    source = autonomous_refund_core()
    source["predicted_resolution"] = resolution
    if resolution == "clarification_required":
        source["required_clarifications"] = ["Ai gửi giao dịch?"]
    assert any("authoritative unsupported signal requires" in error
               for error in validate_shadow_semantic_core(source))


def test_unsupported_without_v1_signal_fails():
    source = core()
    source["predicted_resolution"] = "unsupported_for_current_study"
    assert any("unsupported prediction requires authoritative v1 unsupported signal" in error
               for error in validate_shadow_semantic_core(source))


@pytest.mark.parametrize("status", ["assumed", "superseded"])
def test_non_authoritative_autonomous_true_does_not_qualify(status):
    source = autonomous_refund_core()
    signal = source["claims"][0]
    signal["status"] = status
    if status == "assumed":
        signal["evidence"] = []
        signal["assumption_reason"] = "Not confirmed"
    else:
        source["requirement_history"].append({
            "version": 2, "messages": ["Không tự động hoàn nữa."]})
        signal["superseded_by"] = "auto-false"
        source["claims"].append({
            "claim_id": "auto-false", "kind": "autonomous_execution", "value": False,
            "criticality": "financial", "status": "user_confirmed",
            "scope_id": "auto-refund-timeout-1",
            "evidence": [{"requirement_version": 2, "message_index": 0,
                          "span": "Không tự động hoàn nữa", "relation": "supports"}],
        })
    assert any("unsupported prediction requires authoritative v1 unsupported signal" in error
               for error in validate_shadow_semantic_core(source))


def test_invalid_unsupported_provenance_cannot_qualify():
    source = autonomous_refund_core()
    source["claims"][0]["evidence"][0]["span"] = "không tồn tại trong yêu cầu"
    errors = validate_shadow_semantic_core(source)
    assert any("supporting evidence required" in error for error in errors)
    assert any("unsupported prediction requires authoritative v1 unsupported signal" in error
               for error in errors)


def test_conflict_resolution_is_not_masked_by_unsupported_rule():
    source = autonomous_refund_core()
    source["requirement_history"][0]["messages"][0] += " Không tự động hoàn."
    source["claims"][0]["status"] = "conflicted"
    opposite = deepcopy(source["claims"][0])
    opposite.update(claim_id="auto-false", value=False)
    opposite["evidence"][0]["span"] = "Không tự động hoàn"
    source["claims"].append(opposite)
    source["predicted_resolution"] = "conflict_requires_resolution"
    source["required_clarifications"] = ["Hợp đồng có phải tự động hoàn không?"]
    assert validate_shadow_semantic_core(source) == []


def test_transition_kind_closed_and_invalid_core_not_normalized():
    source = core()
    source["behavior_scopes"][1]["transition_kind"] = "magic_transition"
    assert any("unsupported transition_kind" in error
               for error in validate_shadow_semantic_core(source))
    result = project_intent_spec(source)
    assert result.projection_diagnostics["core_status"] == "invalid"
    assert result.intent_spec.data["behavior_scopes"][1]["transition_kind"] == "magic_transition"


def test_frozen_corpus_transition_kinds_fit_core_v1_enum():
    observed = {scope["transition_kind"] for record in foundation.load_corpus()
                for scope in record["behavior_scopes"]
                if scope["scope_type"] == "transition"}
    assert observed == {"choice", "deposit", "notify", "payment"}
    assert observed == TRANSITION_KINDS
    assert core_prompt_schema_contract()["transition_kinds"] == sorted(TRANSITION_KINDS)
