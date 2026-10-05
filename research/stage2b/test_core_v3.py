"""Versioned native-token quantity contract, without changing frozen v1/v2."""

from copy import deepcopy

from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3, SCHEMA_VERSION_V3,
    parse_native_asset_id, validate_shadow_semantic_core,
)
from research.stage2b.projector import project_intent_spec
from research.stage2b.shadow_extractor import build_prompt


ASSET = "native:" + "11" * 28 + "/474f4c44"
MESSAGE = f"Lan nạp 13 đơn vị token {ASSET} vào tài khoản Lan."


def token_core():
    return {
        "schema_version": CORE_SCHEMA_VERSION_V3,
        "requirement_history": [{"version": 1, "messages": [MESSAGE]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit-1", "scope_type": "transition",
             "transition_kind": "deposit"},
        ],
        "claims": [
            {"claim_id": "asset", "kind": "asset", "value": ASSET,
             "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
             "evidence": [{"requirement_version": 1, "message_index": 0,
                           "span": ASSET, "relation": "supports"}]},
            {"claim_id": "quantity", "kind": "amount_token_units", "value": 13,
             "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
             "evidence": [{"requirement_version": 1, "message_index": 0,
                           "span": "13 đơn vị token", "relation": "supports"}]},
            {"claim_id": "depositor", "kind": "depositing_party", "value": "Lan",
             "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
             "evidence": [{"requirement_version": 1, "message_index": 0,
                           "span": "Lan nạp", "relation": "supports"}]},
        ],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }


def test_native_quantity_projects_without_lovelace_conversion():
    core = token_core()
    assert validate_shadow_semantic_core(core) == []
    projected = project_intent_spec(core).intent_spec.to_dict()
    assert projected["schema_version"] == SCHEMA_VERSION_V3
    quantity = next(item for item in projected["parameters"]
                    if item["parameter_id"] == "parameter:quantity")
    assert quantity["normalized_value"] == 13
    assert quantity["unit"] == "token_units"
    assert parse_native_asset_id(ASSET) == ("11" * 28, "474f4c44")


def test_native_quantity_is_rejected_in_v2_and_without_identified_asset():
    old = token_core()
    old["schema_version"] = CORE_SCHEMA_VERSION_V2
    assert any("unknown claim kind" in error for error in validate_shadow_semantic_core(old))
    missing = deepcopy(token_core())
    missing["claims"][0]["scope_id"] = "global"
    assert any("same-scope native asset id" in error
               for error in validate_shadow_semantic_core(missing))
    malformed = deepcopy(token_core())
    malformed["claims"][0]["value"] = "native:bad/474f4c44"
    assert any("invalid native asset id" in error
               for error in validate_shadow_semantic_core(malformed))


def test_v3_sequential_outcomes_and_automatic_payment_are_not_v1_unsupported():
    core = token_core()
    core["requirement_history"][0]["messages"][0] += " Tự động trả cho Giang."
    core["behavior_scopes"].extend([
        {"scope_id": "pay-1", "scope_type": "terminal_outcome",
         "outcome_id": "pay-1", "parent_scope_id": "deposit-1",
         "continuation_scope_id": "pay-2"},
        {"scope_id": "pay-2", "scope_type": "terminal_outcome",
         "outcome_id": "pay-2", "parent_scope_id": "pay-1"},
    ])
    core["claims"].append({
        "claim_id": "auto", "kind": "autonomous_execution", "value": True,
        "criticality": "nonfinancial", "status": "explicit", "scope_id": "pay-2",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": "Tự động trả", "relation": "supports"}],
    })
    assert validate_shadow_semantic_core(core) == []
    old = deepcopy(core)
    old["schema_version"] = CORE_SCHEMA_VERSION_V2
    assert any("authoritative unsupported signal" in error
               for error in validate_shadow_semantic_core(old))


def test_v3_prompt_distinguishes_represented_behavior_and_later_utc_answer():
    system, _ = build_prompt(token_core()["requirement_history"],
                             core_schema_version=CORE_SCHEMA_VERSION_V3)
    assert "outside_stage2b_v3_claim_taxonomy" in system
    assert "already represented by" in system
    assert "resolves the timezone ambiguity" in system
    assert "same-scope asset claim for EACH" in system
