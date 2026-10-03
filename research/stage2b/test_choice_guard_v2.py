"""Versioned, source-grounded numeric Choice semantics."""

from copy import deepcopy
from dataclasses import replace

from research.stage2b.intent_spec import (
    CORE_SCHEMA_VERSION_V2, SCHEMA_VERSION_V2, validate_intent_spec,
    validate_shadow_semantic_core,
)
from research.stage2b.projector import project_intent_spec
from research.stage2b.shadow_extractor import build_prompt
from research.stage2b.test_core_projector import core
from research.stage3.profile_compilers.direct_payment_v1 import DIRECT_PAYMENT_PROFILE
from research.stage3.profiles import profile_mismatches


def guarded_choice():
    source = core()
    source["schema_version"] = CORE_SCHEMA_VERSION_V2
    source["requirement_history"][0]["messages"][0] += (
        " Alice chooses 0 to 100; at least 50 pays Bob, below 50 refunds Alice."
    )

    def evidence(span):
        return [{"requirement_version": 1, "message_index": 0,
                 "span": span, "relation": "supports"}]

    source["behavior_scopes"].extend([
        {"scope_id": "choice-1", "scope_type": "transition", "transition_kind": "choice",
         "choice_bounds": {"from": 0, "to": 100, "source_evidence": evidence("0 to 100")}},
        {"scope_id": "choice-1:high", "scope_type": "branch", "decision_id": "choice-1",
         "branch_id": "high", "choice_guard": {"operator": "ge", "value": 50,
                                              "source_evidence": evidence("at least 50")}},
        {"scope_id": "choice-1:low", "scope_type": "branch", "decision_id": "choice-1",
         "branch_id": "low", "choice_guard": {"operator": "lt", "value": 50,
                                             "source_evidence": evidence("below 50")}},
        {"scope_id": "outcome-high", "scope_type": "terminal_outcome",
         "outcome_id": "paid-high", "parent_scope_id": "choice-1:high"},
    ])
    return source


def test_v2_choice_guards_survive_projection_without_changing_v1():
    source = guarded_choice()
    assert validate_shadow_semantic_core(source) == []
    projected = project_intent_spec(source).intent_spec.to_dict()
    assert projected["schema_version"] == SCHEMA_VERSION_V2
    assert validate_intent_spec(projected, projected_core=source) == []
    assert projected["behavior_scopes"] == source["behavior_scopes"]
    system, user = build_prompt(source["requirement_history"],
                                core_schema_version=CORE_SCHEMA_VERSION_V2)
    assert "numeric Choice" in system
    assert "choice_guard" in user
    assert "A Choice transition does not continue to its timeout scope" in system


def test_v2_rejects_missing_guard_and_out_of_bound_threshold():
    source = guarded_choice()
    missing = deepcopy(source)
    del next(scope for scope in missing["behavior_scopes"]
             if scope["scope_id"] == "choice-1:low")["choice_guard"]
    assert "invalid choice_guard" in " ".join(validate_shadow_semantic_core(missing))
    outside = deepcopy(source)
    next(scope for scope in outside["behavior_scopes"]
         if scope["scope_id"] == "choice-1:low")["choice_guard"]["value"] = 101
    assert "outside choice_bounds" in " ".join(validate_shadow_semantic_core(outside))
    unsupported = deepcopy(source)
    next(scope for scope in unsupported["behavior_scopes"]
         if scope["scope_id"] == "choice-1:low")["choice_guard"]["source_evidence"][0]["span"] = "not there"
    assert "invalid choice_guard" in " ".join(validate_shadow_semantic_core(unsupported))
    malformed = deepcopy(source)
    next(scope for scope in malformed["behavior_scopes"]
         if scope["scope_id"] == "choice-1:low")["choice_guard"]["operator"] = ["lt"]
    assert "invalid choice_guard" in " ".join(validate_shadow_semantic_core(malformed))


def test_v2_terminal_outcome_requires_explicit_existing_parent():
    source = guarded_choice()
    missing = deepcopy(source)
    del missing["behavior_scopes"][-1]["parent_scope_id"]
    assert "invalid parent_scope_id" in " ".join(validate_shadow_semantic_core(missing))
    wrong = deepcopy(source)
    wrong["behavior_scopes"][-1]["parent_scope_id"] = "missing-branch"
    assert "invalid parent_scope_id" in " ".join(validate_shadow_semantic_core(wrong))
    invalid_type = deepcopy(source)
    invalid_type["behavior_scopes"][-1]["parent_scope_id"] = "global"
    assert "invalid parent_scope_id" in " ".join(validate_shadow_semantic_core(invalid_type))


def test_v2_continuation_is_a_typed_explicit_reference():
    source = guarded_choice()
    source["behavior_scopes"].append({
        "scope_id": "deposit-2", "scope_type": "transition",
        "transition_kind": "deposit", "continuation_scope_id": "choice-1",
    })
    assert validate_shadow_semantic_core(source) == []
    source["behavior_scopes"][-1]["continuation_scope_id"] = "global"
    assert "invalid continuation_scope_id" in " ".join(validate_shadow_semantic_core(source))


def test_v2_choice_to_timeout_is_not_a_sequential_continuation():
    source = guarded_choice()
    source["behavior_scopes"].append({
        "scope_id": "choice-timeout", "scope_type": "timeout",
        "timeout_id": "choice-timeout", "decision_id": "choice-1",
    })
    choice = next(item for item in source["behavior_scopes"]
                  if item["scope_id"] == "choice-1")
    choice["continuation_scope_id"] = "choice-timeout"
    assert "invalid continuation_scope_id" in " ".join(validate_shadow_semantic_core(source))


def test_v2_irrelevant_context_does_not_hide_unrepresented_behavior():
    source = guarded_choice()
    source["unscored_observations"] = [{
        "observation_id": "context-1", "text": "Alice",
        "reason": "irrelevant_context", "source_evidence": [{
            "requirement_version": 1, "message_index": 0, "span": "Alice",
            "relation": "supports",
        }],
    }]
    spec = project_intent_spec(source).intent_spec.to_dict()
    assert validate_intent_spec(spec) == []
    profile = replace(DIRECT_PAYMENT_PROFILE, intent_schema_version=SCHEMA_VERSION_V2,
                      transition_kinds=frozenset({"payment", "choice"}),
                      scope_types=frozenset({"global", "transition", "branch"}),
                      supports_branches=True)
    assert "unrepresented contract behavior" not in " ".join(profile_mismatches(spec, profile))
    source["unscored_observations"][0]["reason"] = "outside_stage2b_v2_claim_taxonomy"
    spec = project_intent_spec(source).intent_spec.to_dict()
    assert "unrepresented contract behavior" in " ".join(profile_mismatches(spec, profile))
