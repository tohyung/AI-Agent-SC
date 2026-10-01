"""The core prompt exposes the existing validator contract without model calls."""

from __future__ import annotations

from copy import deepcopy

import pytest

from research.stage2b import intent_spec, shadow_extractor
from research.stage2b.projector import project_intent_spec
from research.stage2b.test_intent_spec import simple_payment


def core():
    return intent_spec.extract_core_view(deepcopy(simple_payment()))


def errors(source):
    return intent_spec.validate_shadow_semantic_core(source)


def test_scope_reference_contract_and_prompt_share_validator_constants(monkeypatch):
    contract = intent_spec.core_prompt_schema_contract()
    scope = contract["scope"]
    assert scope["types"] == sorted(intent_spec.SCOPE_TYPES)
    assert scope["allowed_fields_by_type"] == {
        key: sorted(value) for key, value in intent_spec.SCOPE_FIELDS.items()}
    assert scope["scope_id_unique"] is True
    assert scope["global_scope_id"] == "global"
    assert contract["transition_kinds"] == sorted(intent_spec.TRANSITION_KINDS)
    decision = scope["references"]["decision_id"]
    assert decision == {
        "target_collection": "behavior_scopes", "target_id_field": "scope_id",
        "target_scope_type": intent_spec.DECISION_TARGET_SCOPE_TYPE,
        "required_for": ["branch"], "optional_for": ["timeout"],
    }
    deadline = scope["references"]["deadline_claim_id"]
    assert deadline["target_collection"] == "claims"
    assert deadline["target_id_field"] == "claim_id"
    assert deadline["allowed_kinds"] == sorted(intent_spec.DEADLINE_KINDS)
    monkeypatch.setattr(intent_spec, "DEADLINE_KINDS", intent_spec.DEADLINE_KINDS | {"new_deadline"})
    assert "new_deadline" in intent_spec.core_prompt_schema_contract()["scope"][
        "references"]["deadline_claim_id"]["allowed_kinds"]

    _, user = shadow_extractor.build_prompt(core()["requirement_history"])
    assert "Every decision_id must equal the scope_id of an existing scope_type=transition" in user
    assert "Do not create a branch/timeout reference before creating" in user
    assert "behavior_scopes.scope_id must be unique" in user
    assert "deadline_claim_id must refer to an existing claim" in user


@pytest.mark.parametrize("target", ["missing", "global"])
def test_branch_rejects_missing_or_nontransition_decision(target):
    source = core()
    source["behavior_scopes"].append({
        "scope_id": "branch-1", "scope_type": "branch",
        "decision_id": target, "branch_id": "approved",
    })
    assert "scope branch-1: decision_id does not reference transition" in errors(source)


def test_branch_accepts_existing_transition_decision():
    source = core()
    source["behavior_scopes"].append({
        "scope_id": "branch-1", "scope_type": "branch",
        "decision_id": "deposit-1", "branch_id": "approved",
    })
    assert errors(source) == []


@pytest.mark.parametrize("target", ["missing", "global", "deposit-1"])
def test_timeout_decision_reference_follows_same_rule(target):
    source = core()
    source["behavior_scopes"].append({
        "scope_id": "timeout-1", "scope_type": "timeout",
        "timeout_id": "deadline-1", "decision_id": target,
    })
    assert ("scope timeout-1: decision_id does not reference transition" in errors(source)) == (
        target != "deposit-1")


def test_deadline_claim_id_references_existing_deadline_kind():
    source = core()
    source["requirement_history"][0]["messages"][0] += " Nạp trước POSIX 4000 ms."
    timeout = {"scope_id": "timeout-1", "scope_type": "timeout", "timeout_id": "deadline-1"}
    source["behavior_scopes"].append(timeout)
    for target in ("missing", "amount"):
        timeout["deadline_claim_id"] = target
        assert "scope timeout-1: deadline_claim_id must reference deadline claim" in errors(source)
    source["claims"].append({
        "claim_id": "deadline", "kind": "deposit_deadline_ms", "value": 4000,
        "criticality": "financial", "status": "explicit", "scope_id": "timeout-1",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": "POSIX 4000 ms", "relation": "supports"}],
    })
    timeout["deadline_claim_id"] = "deadline"
    assert errors(source) == []


def test_duplicate_scope_id_still_rejected():
    source = core()
    source["behavior_scopes"].append(deepcopy(source["behavior_scopes"][1]))
    assert "duplicate scope_id deposit-1" in errors(source)


def observation():
    return {
        "observation_id": "observation-1", "text": "Bob receives payment",
        "reason": intent_spec.UNSCORED_OBSERVATION_REASON,
        "source_evidence": [{"requirement_version": 1, "message_index": 0,
                             "span": "Bob nhận 10 ADA", "relation": "supports"}],
    }


def test_observation_contract_and_prompt_expose_exact_shape():
    contract = intent_spec.core_prompt_schema_contract()["unscored_observation"]
    assert contract["fields"] == sorted(intent_spec.UNSCORED_OBSERVATION_FIELDS)
    assert contract["reason"] == intent_spec.UNSCORED_OBSERVATION_REASON
    assert contract["source_evidence"]["fields"] == sorted(intent_spec.EVIDENCE_FIELDS)
    assert contract["source_evidence"]["relations"] == sorted(intent_spec.EVIDENCE_RELATIONS)
    assert contract["source_evidence"]["nonempty"] is True
    assert contract["source_evidence"]["exact_source_span"] is True
    assert contract["authoritative_financial_facts_belong_in_claims"] is True
    _, user = shadow_extractor.build_prompt(core()["requirement_history"])
    for field in ("observation_id", "text", "reason", "source_evidence",
                  intent_spec.UNSCORED_OBSERVATION_REASON):
        assert field in user
    assert "never a plain string" in user


@pytest.mark.parametrize("bad_observation", [
    "Bob receives payment",
    {key: value for key, value in observation().items() if key != "source_evidence"},
    {**observation(), "source_evidence": []},
    {**observation(), "source_evidence": [{"requirement_version": 1,
       "message_index": 0, "span": "not in source", "relation": "supports"}]},
    {**observation(), "reason": "other"},
])
def test_invalid_unscored_observation_rejected(bad_observation):
    source = core()
    source["unscored_observations"] = [bad_observation]
    assert "invalid unscored_observation" in errors(source)


def test_source_grounded_observation_is_valid_but_not_rich_authority():
    source = core()
    source["claims"] = [claim for claim in source["claims"]
                        if claim["claim_id"] != "recipient"]
    without_observation = project_intent_spec(source).intent_spec.data
    source["unscored_observations"] = [observation()]
    assert errors(source) == []
    with_observation = project_intent_spec(source).intent_spec.data
    assert with_observation["unscored_observations"] == [observation()]
    for section in ("participants", "assets_and_accounts", "parameters", "states",
                    "transitions", "obligations_and_outcomes", "conflicts",
                    "assumptions_and_provenance"):
        assert with_observation[section] == without_observation[section]
    assert with_observation["obligations_and_outcomes"] == []
