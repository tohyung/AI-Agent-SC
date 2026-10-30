"""Offline checks for the research-only semantic extraction contract."""

from research.stage2b import shadow_extractor
from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V3, ShadowSemanticCore,
    _absolute_deadline_mismatch, explicit_utc_instants,
)


def _prompt(message):
    return shadow_extractor.build_prompt([{"version": 1, "messages": [message]}])


def test_minimal_claim_evidence_and_derived_amount_policy():
    system, user = _prompt("Noor deposits 6 ADA into Kei's account.")
    assert "minimal set of atomic claims" in system
    assert "a party name alone does not prove" in system
    assert "status=derived" in system and "not status=explicit" in system
    assert "normalization_basis" in system
    assert "never emit `derived_from=[]`" in system
    assert "do not emit derived_from=[]" in user
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
    assert "Do not ask the business user to choose a wallet" in system


def test_time_release_does_not_require_transaction_submitter_clarification():
    system, _ = _prompt("Release the two payments at fixed times; the contract does not submit transactions itself.")
    assert "does not imply a missing business" in system
    assert "do not ask" in system.lower() and "activates payment" in system
    assert "destination_account_owner" in system
    assert "outside-taxonomy unscored behavior" in system


def test_terminal_outcome_and_lovelace_prompt_invariants():
    system, user = shadow_extractor.build_prompt(
        [{"version": 1, "messages": ["Grace and Jack contribute 47.5 ADA each; refund if incomplete."]}],
        core_schema_version=CORE_SCHEMA_VERSION_V3,
    )
    assert "final outcome on its path, omit continuation_scope_id" in system
    assert "never use its own scope_id as continuation_scope_id" in system
    assert "the runtime converts it to 47500000 lovelace" in user
    assert "If neither exists," in system
    assert "use accepted_interpretation, not clarification_required" in system
    assert "two unrelated root transitions" in system
    assert "two distinct terminal_outcome scopes in sequence" in system


def test_v3_rejects_disconnected_transition_roots():
    core = ShadowSemanticCore({
        "schema_version": CORE_SCHEMA_VERSION_V3,
        "requirement_history": [{"version": 1, "messages": ["Grace and Jack deposit."]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit-grace", "scope_type": "transition", "transition_kind": "deposit"},
            {"scope_id": "deposit-jack", "scope_type": "transition", "transition_kind": "deposit"},
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    })
    assert any("multiple root transitions" in error for error in core.validation_errors())


def test_optional_null_continuation_does_not_create_a_successor():
    core = ShadowSemanticCore({
        "schema_version": CORE_SCHEMA_VERSION_V3,
        "requirement_history": [{"version": 1, "messages": ["Grace deposits."]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit-grace", "scope_type": "transition", "transition_kind": "deposit",
             "continuation_scope_id": "done"},
            {"scope_id": "done", "scope_type": "terminal_outcome", "outcome_id": "done",
             "parent_scope_id": "deposit-grace", "continuation_scope_id": None},
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    })
    assert not any("invalid continuation_scope_id" in error
                   for error in core.validation_errors())


def test_v3_rejects_orphan_terminal_outcome():
    core = ShadowSemanticCore({
        "schema_version": CORE_SCHEMA_VERSION_V3,
        "requirement_history": [{"version": 1, "messages": ["Grace deposits."]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit-grace", "scope_type": "transition", "transition_kind": "deposit"},
            {"scope_id": "unused", "scope_type": "terminal_outcome", "outcome_id": "unused",
             "parent_scope_id": "deposit-grace"},
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    })
    assert "scope unused: terminal outcome has no incoming continuation" in core.validation_errors()


def test_ict_named_date_is_an_exact_instant_for_deadline_validation():
    span = "Grace's deadline is 23:59 ICT on 10 January 2027"
    assert [value for _, _, value in explicit_utc_instants(span)] == [1799600340000]
    claim = {"value": 1799552340000, "evidence": [{"span": span, "relation": "supports"}]}
    assert _absolute_deadline_mismatch(claim)
    claim["value"] = 1799600340000
    assert not _absolute_deadline_mismatch(claim)
    date_first = "11 January 2027 at 23:59 ICT (UTC+7)"
    assert [value for _, _, value in explicit_utc_instants(date_first)] == [1799686740000]
    assert _absolute_deadline_mismatch({
        "value": 1799692740000,
        "evidence": [{"span": date_first, "relation": "supports"}],
    })
    vietnamese = "23:59 giờ Việt Nam (ICT, UTC+7) ngày 12/01/2027"
    short_ict = "23:59 ICT ngày 19/01/2027"
    assert [value for _, _, value in explicit_utc_instants(vietnamese)] == [1799773140000]
    assert [value for _, _, value in explicit_utc_instants(short_ict)] == [1800377940000]


def test_correction_conflict_and_resolution_order_policy():
    system, _ = _prompt("Version 1 names Kei; version 2 corrects the owner to Noor.")
    assert "later explicit correction supersedes" in system
    assert "do not retain that old uncertainty as unscored contract behavior" in system
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
