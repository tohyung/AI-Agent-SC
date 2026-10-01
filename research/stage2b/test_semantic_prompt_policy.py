"""Offline checks for the research-only semantic extraction contract."""

from research.stage2b import shadow_extractor
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION


def _prompt(message):
    return shadow_extractor.build_prompt([{"version": 1, "messages": [message]}])


def test_minimal_claim_evidence_and_derived_amount_policy():
    system, user = _prompt("Noor deposits 6 ADA into Kei's account.")
    assert "minimal set of atomic claims" in system
    assert "a party name alone does not prove" in system
    assert "status=derived" in system and "not status=explicit" in system
    assert "normalization_basis" in system
    assert "Noor deposits 6 ADA" in user
    assert "seven semantic core fields" in system


def test_event_scope_and_account_role_policy():
    system, _ = _prompt("Kei chooses release; the timeout refunds Noor.")
    assert "outcome recipients on their actual" in system
    assert "Choice/Notify branch or timeout" in system
    assert "Do not detach an outcome" in system
    assert "deposit account owner" in system
    assert "payment source" in system
    assert "branch-independent facts" in system


def test_question_and_notify_policy():
    system, _ = _prompt("Notify confirms delivery, then Kei is paid.")
    assert "if its Observation condition is undefined" in system
    assert "not who owns a Choice" in system
    assert "nonduplicate Vietnamese business" in system
    assert "Ask which" in system and "competing value" in system
    assert "transaction_submitter" in system
    assert "Keep schema field names out" in system


def test_correction_conflict_and_resolution_order_policy():
    system, _ = _prompt("Version 1 names Kei; version 2 corrects the owner to Noor.")
    assert "later explicit correction supersedes" in system
    assert "simultaneously active incompatible values" in system
    assert "Choose predicted_resolution last" in system
    assert system.index("Read requirement history") < system.index("Choose predicted_resolution")


def test_fake_core_with_role_evidence_and_derived_amount_validates():
    history = [{"version": 1, "messages": [
        "Noor deposits 6 ADA into Kei's account; Kei receives 6 ADA."]}]

    def evidence(span):
        return [{"requirement_version": 1, "message_index": 0,
                 "span": span, "relation": "supports"}]

    core = {
        "schema_version": CORE_SCHEMA_VERSION,
        "requirement_history": history,
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit-1", "scope_type": "transition",
             "transition_kind": "deposit"},
            {"scope_id": "payment-1", "scope_type": "transition",
             "transition_kind": "payment"},
        ],
        "claims": [
            {"claim_id": "depositor", "kind": "depositing_party", "value": "Noor",
             "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
             "evidence": evidence("Noor deposits")},
            {"claim_id": "account", "kind": "destination_account_owner", "value": "Kei",
             "criticality": "financial", "status": "explicit", "scope_id": "deposit-1",
             "evidence": evidence("Kei's account")},
            {"claim_id": "asset", "kind": "asset", "value": "ADA",
             "criticality": "financial", "status": "explicit", "scope_id": "global",
             "evidence": evidence("6 ADA")},
            {"claim_id": "amount", "kind": "amount_lovelace", "value": 6000000,
             "criticality": "financial", "status": "derived", "scope_id": "deposit-1",
             "evidence": evidence("6 ADA"),
             "normalization_basis": "1 ADA = 1000000 lovelace"},
            {"claim_id": "recipient", "kind": "payment_recipient", "value": "Kei",
             "criticality": "financial", "status": "explicit", "scope_id": "payment-1",
             "evidence": evidence("Kei receives 6 ADA")},
        ],
        "required_clarifications": [],
        "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }

    class FakeModel:
        def generate(self, system, user):
            assert "minimal set of atomic claims" in system
            assert "Noor deposits" in user
            return core

    extracted = shadow_extractor.IntentShadowExtractor(FakeModel()).extract(history)
    assert extracted.validation_errors(expected_history=history) == []
    assert extracted.to_dict() == core
