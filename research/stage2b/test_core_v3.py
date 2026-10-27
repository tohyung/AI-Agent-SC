"""Versioned native-token quantity contract, without changing frozen v1/v2."""

from copy import deepcopy

from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3, SCHEMA_VERSION_V3,
    parse_native_asset_id, validate_shadow_semantic_core,
)
from research.stage2b.core_draft import derive_unambiguous_token_assets
from research.stage2b.projector import project_intent_spec
from research.stage2b.shadow_extractor import IntentShadowExtractor, build_prompt


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
    assert project_intent_spec(core).intent_spec.validation_errors() == []
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


def test_extractor_canonicalizes_complete_dot_separated_native_asset_id():
    core = token_core()
    dotted_id = "11" * 28 + ".474f4c44"
    core["requirement_history"][0]["messages"][0] = MESSAGE.replace(ASSET, dotted_id)
    asset_claim = next(claim for claim in core["claims"] if claim["kind"] == "asset")
    asset_claim["value"] = dotted_id
    asset_claim["evidence"][0]["span"] = dotted_id

    class FixedModel:
        def generate(self, _system, _user):
            return deepcopy(core)

    extractor = IntentShadowExtractor(FixedModel(), core_schema_version=CORE_SCHEMA_VERSION_V3)
    normalized, errors = extractor.extract_with_validation_feedback(
        core["requirement_history"], max_repairs=0)

    normalized_asset = next(claim["value"] for claim in normalized.to_dict()["claims"]
                            if claim["kind"] == "asset")
    assert normalized_asset == ASSET
    assert errors == []
    assert extractor.normalization_actions[0] == {
        "kind": "native_asset_id_format", "claim_id": "asset",
        "source_value": dotted_id, "normalized_value": ASSET,
    }


def test_extractor_resolves_unresolved_deadline_from_one_explicit_zoned_instant():
    core = token_core()
    span = "19:00 ngày 24/01/2027 theo giờ Hà Nội (UTC+7)"
    core["requirement_history"][0]["messages"][0] += f" Trang nạp trước {span}."
    core["claims"].append({
        "claim_id": "deadline", "kind": "deposit_deadline_ms", "value": None,
        "criticality": "financial", "status": "unresolved", "scope_id": "deposit-1",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": span, "relation": "supports"}],
    })

    class FixedModel:
        def generate(self, _system, _user):
            return deepcopy(core)

    extractor = IntentShadowExtractor(FixedModel(), core_schema_version=CORE_SCHEMA_VERSION_V3)
    normalized, errors = extractor.extract_with_validation_feedback(
        core["requirement_history"], max_repairs=0)
    deadline = next(claim for claim in normalized.to_dict()["claims"]
                    if claim["claim_id"] == "deadline")

    assert deadline["value"] == 1800792000000
    assert deadline["status"] == "derived"
    assert errors == []
    assert any(action.get("claim_id") == "deadline"
               and action["kind"] == "deposit_deadline_ms"
               for action in extractor.normalization_actions)


def test_extractor_recovers_uncited_deadline_from_unique_actor_clause():
    core = token_core()
    previous = "Quỳnh nạp trước 19:00 ngày 17/01/2027 theo giờ Hà Nội (UTC+7)"
    target = "Trang nạp trước 19:00 ngày 24/01/2027, đúng bảy ngày sau"
    core["requirement_history"][0]["messages"][0] = (
        MESSAGE.replace("Lan", "Trang") + f" {previous}; {target}.")
    depositor = next(claim for claim in core["claims"]
                     if claim["kind"] == "depositing_party")
    depositor.update(value="Trang", evidence=[{
        "requirement_version": 1, "message_index": 0,
        "span": "Trang nạp", "relation": "supports",
    }])
    core["claims"].append({
        "claim_id": "deadline", "kind": "deposit_deadline_ms", "value": None,
        "criticality": "financial", "status": "unresolved", "scope_id": "deposit-1",
        "evidence": [],
    })

    class FixedModel:
        def generate(self, _system, _user):
            return deepcopy(core)

    extractor = IntentShadowExtractor(FixedModel(), core_schema_version=CORE_SCHEMA_VERSION_V3)
    normalized, errors = extractor.extract_with_validation_feedback(
        core["requirement_history"], max_repairs=0)
    deadline = next(claim for claim in normalized.to_dict()["claims"]
                    if claim["claim_id"] == "deadline")

    assert deadline["value"] == 1800792000000
    assert deadline["status"] == "derived"
    assert deadline["evidence"][0]["span"] == target
    assert errors == []
    assert any(action.get("claim_id") == "deadline"
               and action.get("kind") == "deposit_deadline_ms"
               for action in extractor.normalization_actions)


def test_terminal_outcome_inherits_unique_native_asset_with_derivation_provenance():
    core = token_core()
    core["behavior_scopes"][1]["continuation_scope_id"] = "outcome-first"
    core["behavior_scopes"].extend([
        {"scope_id": "outcome-first", "scope_type": "terminal_outcome",
         "outcome_id": "first", "parent_scope_id": "deposit-1",
         "continuation_scope_id": "outcome-second"},
        {"scope_id": "outcome-second", "scope_type": "terminal_outcome",
         "outcome_id": "second", "parent_scope_id": "outcome-first"},
    ])
    quantity = deepcopy(next(claim for claim in core["claims"]
                            if claim["kind"] == "amount_token_units"))
    quantity.update(claim_id="outcome-quantity", scope_id="outcome-second")
    core["claims"].append(quantity)
    extractor_input = deepcopy(core)

    actions = derive_unambiguous_token_assets(core)

    inherited = next(claim for claim in core["claims"]
                     if claim.get("derived_from") == "asset")
    assert inherited["scope_id"] == "outcome-second"
    assert inherited["value"] == ASSET
    assert inherited["status"] == "derived"
    assert validate_shadow_semantic_core(core) == []
    assert actions == [{"kind": "unique_token_asset_binding",
                        "claim_id": "derived-asset:asset:outcome-second",
                        "scope_id": "outcome-second", "derived_from": "asset"}]

    class FixedModel:
        def generate(self, _system, _user):
            return deepcopy(extractor_input)

    extractor = IntentShadowExtractor(FixedModel(), core_schema_version=CORE_SCHEMA_VERSION_V3)
    normalized, errors = extractor.extract_with_validation_feedback(
        extractor_input["requirement_history"], max_repairs=0)
    assert errors == []
    assert any(action["kind"] == "unique_token_asset_binding"
               for action in extractor.normalization_actions)
    assert validate_shadow_semantic_core(normalized.to_dict()) == []


def test_unique_global_native_asset_is_bound_to_token_quantity_scope():
    core = token_core()
    core["claims"][0]["scope_id"] = "global"
    core["requirement_history"][0]["messages"][0] += " Lan cũng nạp 5 ADA."
    core["claims"].append({
        "claim_id": "ada", "kind": "asset", "value": "ADA",
        "criticality": "financial", "status": "explicit", "scope_id": "global",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": "5 ADA", "relation": "supports"}],
    })

    actions = derive_unambiguous_token_assets(core)

    inherited = next(claim for claim in core["claims"]
                     if claim.get("derived_from") == "asset")
    assert inherited["scope_id"] == "deposit-1"
    assert inherited["value"] == ASSET
    assert actions[0]["kind"] == "unique_token_asset_binding"
    assert validate_shadow_semantic_core(core) == []
    assert project_intent_spec(core).intent_spec.validation_errors() == []


def test_ambiguous_global_native_assets_are_not_bound_or_reported_as_conflict():
    core = token_core()
    core["claims"][0]["scope_id"] = "global"
    second_asset = "native:" + "22" * 28 + "/474f4c44"
    core["requirement_history"][0]["messages"][0] += f" Lan cũng nhắc {second_asset}."
    core["claims"].append({
        "claim_id": "second-asset", "kind": "asset", "value": second_asset,
        "criticality": "financial", "status": "explicit", "scope_id": "global",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": second_asset, "relation": "supports"}],
    })

    actions = derive_unambiguous_token_assets(core)
    errors = validate_shadow_semantic_core(core)

    assert actions == []
    assert any("same-scope native asset id" in error for error in errors)
    assert not any("active claim conflict for asset" in error for error in errors)


def test_explicitly_conflicted_asset_alternatives_still_require_resolution():
    core = token_core()
    core["claims"] = [claim for claim in core["claims"]
                      if claim["kind"] != "amount_token_units"]
    core["predicted_resolution"] = "conflict_requires_resolution"
    core["required_clarifications"] = ["Token nào được dùng?"]
    core["claims"][0].update(scope_id="global", status="conflicted")
    second_asset = "native:" + "22" * 28 + "/474f4c44"
    core["requirement_history"][0]["messages"][0] += f" hoặc {second_asset}."
    core["claims"].append({
        "claim_id": "second-asset", "kind": "asset", "value": second_asset,
        "criticality": "financial", "status": "conflicted", "scope_id": "global",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": second_asset, "relation": "supports"}],
    })

    assert validate_shadow_semantic_core(core) == []
    assert project_intent_spec(core).intent_spec.validation_errors() == []


def test_v3_sequential_outcomes_and_automatic_payment_are_not_v1_unsupported():
    core = token_core()
    core["requirement_history"][0]["messages"][0] += " Tự động trả cho Giang."
    core["behavior_scopes"][1]["continuation_scope_id"] = "pay-1"
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


def test_v3_confirmed_ledger_history_deletion_is_source_backed_unsupported():
    core = token_core()
    core["requirement_history"] = [{
        "version": 1,
        "messages": ["Xóa hẳn lịch sử giao dịch đã xác nhận trên Cardano."],
    }]
    core["behavior_scopes"] = [{"scope_id": "global", "scope_type": "global"}]
    core["claims"] = [{
        "claim_id": "erase-confirmed", "kind": "ledger_history_deletion", "value": True,
        "criticality": "nonfinancial", "status": "explicit", "scope_id": "global",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": "Xóa hẳn lịch sử giao dịch đã xác nhận",
                      "relation": "supports"}],
    }]
    core["predicted_resolution"] = "unsupported_for_current_study"
    assert validate_shadow_semantic_core(core) == []
    missing_evidence = deepcopy(core)
    missing_evidence["claims"][0]["evidence"] = []
    assert any("unsupported prediction requires authoritative" in error
               for error in validate_shadow_semantic_core(missing_evidence))
    false_signal = deepcopy(core)
    false_signal["claims"][0]["value"] = False
    assert any("unsupported prediction requires authoritative" in error
               for error in validate_shadow_semantic_core(false_signal))
    legacy = deepcopy(core)
    legacy["schema_version"] = CORE_SCHEMA_VERSION_V2
    assert any("unknown claim kind" in error
               for error in validate_shadow_semantic_core(legacy))


def test_v3_prompt_exposes_only_confirmed_ledger_deletion_unsupported_signal():
    system, user = build_prompt([{"version": 1, "messages": [
        "Xóa hẳn lịch sử giao dịch đã xác nhận trên Cardano."]}],
        core_schema_version=CORE_SCHEMA_VERSION_V3)
    assert "ledger_history_deletion" in system
    assert '"kind": "ledger_history_deletion"' in user
    assert '"kind": "autonomous_execution", "value": true' not in user


def test_v3_prompt_distinguishes_represented_behavior_and_later_utc_answer():
    system, _ = build_prompt(token_core()["requirement_history"],
                             core_schema_version=CORE_SCHEMA_VERSION_V3)
    assert "outside_stage2b_v3_claim_taxonomy" in system
    assert "already represented by" in system
    assert "resolves the timezone ambiguity" in system
    assert "same-scope asset claim for EACH" in system
