"""IntentSpec structure, provenance, and authority tests without a model."""

from __future__ import annotations

from copy import deepcopy

from research.stage2b.intent_spec import validate_intent_spec


def simple_payment():
    history = [{"version": 1, "messages": [
        "Alice nạp 10 ADA vào tài khoản Alice; Bob nhận 10 ADA."]}]
    evidence = lambda span: [{"requirement_version": 1, "message_index": 0,
                              "span": span, "relation": "supports"}]
    return {
        "schema_version": "stage2b-shadow-v1", "requirement_history": history,
        "participants": [
            {"participant_id": "party:Alice", "name": "Alice", "claim_refs": ["depositor"]},
            {"participant_id": "party:Bob", "name": "Bob", "claim_refs": ["recipient"]},
        ],
        "assets_and_accounts": {
            "assets": [{"asset_id": "asset:ADA", "symbol": "ADA", "claim_refs": ["asset"]}],
            "accounts": [{"account_id": "account:Alice", "owner": "Alice",
                          "claim_refs": ["account"]}],
            "funding_relations": [],
        },
        "parameters": [{"parameter_id": "amount-1", "kind": "amount",
                        "normalized_value": 10000000, "unit": "lovelace",
                        "claim_refs": ["amount"]}],
        "states": [{"state_id": "initial", "claim_refs": []},
                   {"state_id": "funded", "claim_refs": ["depositor", "amount"]}],
        "transitions": [{"transition_id": "deposit-1", "kind": "deposit", "actor": "Alice",
                         "transaction_submitter": None, "claim_refs": ["depositor"]}],
        "obligations_and_outcomes": [
            {"outcome_id": "payout-1", "kind": "payment", "recipient": "Bob",
             "scope_id": "payout-1", "claim_refs": ["recipient"]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"},
            {"scope_id": "payout-1", "scope_type": "transition", "transition_kind": "payment"},
        ],
        "claims": [
            {"claim_id": "depositor", "kind": "depositing_party", "value": "Alice",
             "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
             "evidence": evidence("Alice nạp")},
            {"claim_id": "account", "kind": "destination_account_owner", "value": "Alice",
             "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
             "evidence": evidence("tài khoản Alice")},
            {"claim_id": "asset", "kind": "asset", "value": "ADA",
             "criticality": "financial", "status": "explicit", "scope_id": "global",
             "evidence": evidence("10 ADA")},
            {"claim_id": "amount", "kind": "amount_lovelace", "value": 10000000,
             "criticality": "financial", "status": "derived", "scope_id": "deposit-1",
             "evidence": evidence("10 ADA"), "derived_from": "asset",
             "normalization_basis": "1 ADA = 1000000 lovelace"},
            {"claim_id": "recipient", "kind": "payment_recipient", "value": "Bob",
             "criticality": "financial", "status": "explicit", "scope_id": "payout-1",
             "evidence": evidence("Bob nhận 10 ADA")},
        ],
        "required_clarifications": [], "conflicts": [], "assumptions_and_provenance": [],
        "unscored_observations": [], "predicted_resolution": "accepted_interpretation",
    }


def errors_with(spec, fragment):
    assert any(fragment in error for error in validate_intent_spec(spec))


def test_valid_simple_payment_and_derived_lovelace():
    assert validate_intent_spec(simple_payment()) == []


def test_unknown_recipient_requires_business_clarification():
    spec = simple_payment()
    recipient = next(c for c in spec["claims"] if c["claim_id"] == "recipient")
    recipient.update(value=None, status="unresolved", evidence=[])
    spec["participants"].pop()
    spec["obligations_and_outcomes"][0]["recipient"] = None
    spec["predicted_resolution"] = "clarification_required"
    spec["required_clarifications"] = ["Ai nhận 10 ADA?"]
    assert validate_intent_spec(spec) == []


def test_corrected_choice_owner_supersedes_old_owner():
    spec = simple_payment()
    spec["requirement_history"] = [
        {"version": 1, "messages": ["Bob quyết định approve."]},
        {"version": 2, "messages": ["Alice mới là người quyết định approve."]},
    ]
    spec["claims"] = [
        {"claim_id": "old", "kind": "choice_owner", "value": "Bob",
         "criticality": "financial", "status": "superseded", "scope_id": "decision-1",
         "superseded_by": "new", "evidence": [{"requirement_version": 1,
         "message_index": 0, "span": "Bob quyết định approve", "relation": "supports"}]},
        {"claim_id": "new", "kind": "choice_owner", "value": "Alice",
         "criticality": "financial", "status": "user_confirmed", "scope_id": "decision-1",
         "evidence": [{"requirement_version": 2, "message_index": 0,
                      "span": "Alice mới là người quyết định approve", "relation": "supports"}]},
    ]
    spec["behavior_scopes"] = [{"scope_id": "decision-1", "scope_type": "transition",
                                 "transition_kind": "choice"}]
    spec["participants"] = [{"participant_id": "party:Alice", "name": "Alice",
                             "claim_refs": ["new"]}]
    spec["assets_and_accounts"] = {"assets": [], "accounts": [], "funding_relations": []}
    spec["parameters"] = []
    spec["states"] = []
    spec["transitions"] = [{"transition_id": "decision-1", "kind": "choice",
                            "actor": "Alice", "transaction_submitter": None,
                            "claim_refs": ["new"]}]
    spec["obligations_and_outcomes"] = []
    assert validate_intent_spec(spec) == []
    spec["claims"][0]["superseded_by"] = "missing"
    errors_with(spec, "invalid supersession")


def test_scoped_conflict_requires_resolution():
    spec = simple_payment()
    spec["predicted_resolution"] = "conflict_requires_resolution"
    spec["required_clarifications"] = ["Bob hay Alice là người nhận?"]
    spec["claims"][-1]["status"] = "conflicted"
    other = deepcopy(spec["claims"][-1])
    other.update(claim_id="other", value="Alice")
    other["evidence"][0]["span"] = "Alice"
    spec["claims"].append(other)
    assert validate_intent_spec(spec) == []
    spec["predicted_resolution"] = "accepted_interpretation"
    errors_with(spec, "active claim conflict")


def test_unsupported_autonomous_execution_is_not_clarification():
    spec = simple_payment()
    spec["predicted_resolution"] = "unsupported_for_current_study"
    spec["requirement_history"][0]["messages"][0] += " Tự động hoàn không giao dịch."
    spec["claims"].append({
        "claim_id": "autonomous", "kind": "autonomous_execution", "value": True,
        "criticality": "financial", "status": "explicit", "scope_id": "global",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": "Tự động hoàn không giao dịch", "relation": "supports"}],
    })
    assert validate_intent_spec(spec) == []


def test_asset_does_not_infer_account_owner_or_transaction_submitter():
    spec = simple_payment()
    spec["claims"] = [claim for claim in spec["claims"]
                      if claim["claim_id"] != "account"]
    spec["assets_and_accounts"]["accounts"] = []
    assert validate_intent_spec(spec) == []
    spec["assets_and_accounts"]["accounts"] = [{
        "account_id": "account:Alice", "owner": "Alice", "claim_refs": ["asset"]}]
    errors_with(spec, "account owner lacks matching claim_ref")
    spec["assets_and_accounts"]["accounts"] = []
    spec["transitions"][0]["transaction_submitter"] = "Alice"
    errors_with(spec, "transaction_submitter cannot be inferred")


def test_transition_actor_and_rich_claim_refs_are_authoritative():
    spec = simple_payment()
    spec["transitions"][0]["claim_refs"] = []
    errors_with(spec, "transition actor lacks matching claim_ref")
    spec = simple_payment()
    spec["participants"][0]["claim_refs"] = ["missing"]
    errors_with(spec, "broken claim_ref")


def test_invalid_evidence_kind_and_normalization_rejected():
    spec = simple_payment()
    spec["claims"][0]["evidence"][0]["span"] = "fabricated"
    errors_with(spec, "invalid evidence target/span")
    spec = simple_payment()
    spec["claims"][0]["kind"] = "typo_recipient"
    errors_with(spec, "unknown claim kind")
    spec = simple_payment()
    spec["claims"][3].pop("normalization_basis")
    errors_with(spec, "normalization_basis required")
    spec = simple_payment()
    spec["claims"][3]["derived_from"] = "depositor"
    errors_with(spec, "derivation source evidence must overlap")


def test_assumed_financial_claim_has_no_fake_provenance_and_is_unsafe():
    spec = simple_payment()
    claim = spec["claims"][-1]
    claim.update(status="assumed", evidence=[], assumption_reason="Recipient not stated")
    spec["participants"].pop()
    spec["obligations_and_outcomes"] = []
    spec["predicted_resolution"] = "clarification_required"
    spec["required_clarifications"] = ["Ai nhận tiền?"]
    assert validate_intent_spec(spec) == []
    claim["evidence"] = [{"requirement_version": 1, "message_index": 0,
                           "span": "Bob nhận 10 ADA", "relation": "supports"}]
    assert validate_intent_spec(spec) == []
    spec["predicted_resolution"] = "accepted_interpretation"
    errors_with(spec, "accepted prediction has unsafe critical claim")


def test_unscored_observation_cannot_back_rich_fact():
    spec = simple_payment()
    spec["unscored_observations"] = [{
        "observation_id": "o1", "text": "delivery verified by an oracle",
        "reason": "outside_stage2b_v1_claim_taxonomy",
        "source_evidence": [{"requirement_version": 1, "message_index": 0,
                             "span": "Alice nạp", "relation": "supports"}],
    }]
    spec["transitions"][0]["actor"] = "Oracle"
    errors_with(spec, "transition actor lacks matching claim_ref")


def test_unknown_rich_field_cannot_hide_new_financial_fact():
    spec = simple_payment()
    spec["transitions"][0]["extra_payment_amount"] = 5000000
    errors_with(spec, "unsupported rich fields")
    spec = simple_payment()
    spec["obligations_and_outcomes"][0]["kind"] = "refund"
    errors_with(spec, "outcome recipient lacks matching scoped claim_ref")


def test_model_cannot_rewrite_requirement_history():
    spec = simple_payment()
    source = deepcopy(spec["requirement_history"])
    spec["requirement_history"][0]["messages"][0] += " Invented condition."
    assert "requirement_history differs from supplied source" in validate_intent_spec(
        spec, expected_history=source)


def test_malformed_model_types_return_errors_instead_of_raising():
    spec = simple_payment()
    spec["predicted_resolution"] = []
    spec["claims"][0]["status"] = []
    spec["claims"][0]["evidence"][0]["relation"] = []
    spec["behavior_scopes"][0]["scope_type"] = []
    errors = validate_intent_spec(spec)
    assert any("invalid predicted_resolution" in error for error in errors)
    assert any("invalid status" in error for error in errors)
    assert any("invalid scope_type" in error for error in errors)
