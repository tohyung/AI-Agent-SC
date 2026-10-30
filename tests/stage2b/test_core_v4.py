"""Positive payment release times stay distinct from timeout deadlines."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4, SCHEMA_VERSION_V4,
    extract_core_view, validate_intent_spec, validate_shadow_semantic_core,
)
from research.stage2b.core_draft import materialize_core_draft
from research.stage2b.projector import project_intent_spec
from research.stage2b.shadow_extractor import build_prompt
from tests.stage2b.test_intent_spec import simple_payment


def payment_release_core():
    core = extract_core_view(deepcopy(simple_payment()))
    core["schema_version"] = CORE_SCHEMA_VERSION_V4
    message = core["requirement_history"][0]["messages"][0]
    core["requirement_history"][0]["messages"][0] = (
        message + " After the deposit, payment is available at or after "
        "00:00 on 12/01/2027 in Vietnam time (UTC+7)."
    )
    core["behavior_scopes"][1]["continuation_scope_id"] = "payout-1"
    release_span = "00:00 on 12/01/2027 in Vietnam time (UTC+7)"
    release_ms = int(datetime(2027, 1, 12, tzinfo=timezone(
        timedelta(hours=7))).timestamp() * 1000)
    core["claims"].append({
        "claim_id": "release-time", "kind": "payment_release_time_ms",
        "value": release_ms, "criticality": "financial", "status": "explicit",
        "scope_id": "payout-1",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": release_span, "relation": "supports"}],
    })
    return core


def test_v4_projects_payment_release_time_to_its_payment_transition():
    core = payment_release_core()
    assert validate_shadow_semantic_core(core) == []
    result = project_intent_spec(core)
    spec = result.intent_spec.to_dict()
    payment = next(item for item in spec["transitions"]
                   if item["transition_id"] == "payout-1")
    parameter = next(item for item in spec["parameters"]
                     if item["parameter_id"] == "parameter:release-time")
    assert spec["schema_version"] == SCHEMA_VERSION_V4
    assert parameter == {
        "parameter_id": "parameter:release-time", "kind": "release_time",
        "normalized_value": core["claims"][-1]["value"], "unit": "posix_ms",
        "claim_refs": ["release-time"],
    }
    assert payment["release_time_parameter_id"] == parameter["parameter_id"]
    assert validate_intent_spec(spec, projected_core=core) == []
    assert result.projection_diagnostics["complete"] is True


def test_v3_rejects_v4_payment_release_claim():
    core = payment_release_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V3
    assert any("unknown claim kind" in error
               for error in validate_shadow_semantic_core(core))


def test_v4_normalizes_explicit_release_time_to_posix_milliseconds():
    core = payment_release_core()
    claim = core["claims"][-1]
    expected = claim["value"]
    source_value = "00:00 on 12/01/2027 in Vietnam time (UTC+7)"
    claim["value"] = source_value
    draft = {key: value for key, value in core.items()
             if key not in {"schema_version", "requirement_history"}}
    result, actions = materialize_core_draft(
        draft, core["requirement_history"], CORE_SCHEMA_VERSION_V4)
    assert result["claims"][-1]["value"] == expected
    assert actions[0]["kind"] == "payment_release_time_ms"
    assert actions[0]["source_literal"] == source_value


def test_v4_prompt_defines_release_time_as_not_before_not_timeout():
    system, user = build_prompt(payment_release_core()["requirement_history"],
                                core_schema_version=CORE_SCHEMA_VERSION_V4)
    assert "payment_release_time_ms" in system
    assert "not timeout_ms or a latest deadline" in system
    assert '"payment_release_time_ms"' in user


def test_v4_terminal_payout_requires_same_scope_recipient():
    core = extract_core_view(deepcopy(simple_payment()))
    core["schema_version"] = CORE_SCHEMA_VERSION_V4
    core["behavior_scopes"][1]["continuation_scope_id"] = "payout-1"
    core["behavior_scopes"][2] = {
        "scope_id": "payout-1", "scope_type": "terminal_outcome",
        "outcome_id": "payout-1", "parent_scope_id": "deposit-1",
    }
    amount = next(claim for claim in core["claims"] if claim["claim_id"] == "amount")
    recipient = next(claim for claim in core["claims"] if claim["claim_id"] == "recipient")
    amount["scope_id"] = "payout-1"
    core["claims"].remove(recipient)
    error = "scope payout-1: payout amount requires same-scope recipient"
    assert error in validate_shadow_semantic_core(core)
    core["claims"].append(recipient)
    assert error not in validate_shadow_semantic_core(core)


def test_v4_deposit_account_owner_cannot_be_global_seller_role():
    core = extract_core_view(deepcopy(simple_payment()))
    core["schema_version"] = CORE_SCHEMA_VERSION_V4
    core["behavior_scopes"][1]["continuation_scope_id"] = "payout-1"
    owner = next(claim for claim in core["claims"] if claim["claim_id"] == "account")
    assert validate_shadow_semantic_core(core) == []
    owner["scope_id"] = "global"
    assert ("claim account: deposit account owner must scope a deposit transition"
            in validate_shadow_semantic_core(core))


def test_v4_depositing_party_must_scope_actual_deposit():
    core = payment_release_core()
    depositor = next(claim for claim in core["claims"]
                     if claim["kind"] == "depositing_party")
    assert validate_shadow_semantic_core(core) == []
    depositor["scope_id"] = "global"
    assert (f"claim {depositor['claim_id']}: depositing party must scope a deposit transition"
            in validate_shadow_semantic_core(core))


def test_v4_unrepresented_behavior_can_require_clarification():
    core = {
        "schema_version": CORE_SCHEMA_VERSION_V4,
        "requirement_history": [{"version": 1, "messages": [
            "I want live prices without anyone providing them."]}],
        "behavior_scopes": [{"scope_id": "global", "scope_type": "global"}],
        "claims": [],
        "required_clarifications": [{
            "clarification_id": "clar-1",
            "question": "Who will provide the price data?",
            "target_claim_kinds": [], "target_scope_ids": ["global"],
        }],
        "unscored_observations": [{
            "observation_id": "obs-1", "text": "Live external prices are required.",
            "reason": "outside_stage2b_v4_claim_taxonomy",
            "source_evidence": [{"requirement_version": 1, "message_index": 0,
                                 "span": "live prices", "relation": "supports"}],
        }],
        "predicted_resolution": "clarification_required",
    }
    assert validate_shadow_semantic_core(core) == []
