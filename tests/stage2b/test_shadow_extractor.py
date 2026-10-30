"""Shadow transport and CLI tests using only fake models."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from research.integrations.reasoner_models import LLMConfigError, LLMTransientError
from research.integrations.openai_reasoner import summarize_call_log
from research.stage2b import intent_spec, run_shadow, shadow_extractor
from research.stage2b.repair_policy import REPAIR_POLICY_VERSION
from tests.stage2b.test_intent_spec import simple_payment
from tests.stage3.test_funded_choice_v1 import funded_choice_core


@pytest.fixture(autouse=True)
def clean_git_for_offline_cli(monkeypatch):
    monkeypatch.setattr(run_shadow, "require_clean_worktree", lambda _root: "a" * 40)


def live_argv(*args):
    return ["run_shadow.py", "--live", "--model", "fake", "--max-physical-calls", "60",
            "--max-spend-usd", "30", "--per-request-cost-ceiling-usd", "0.5", *args]


class FakeTransportBase:
    def init_usage(self, model="fake"):
        self.reasoner = type("Reasoner", (), {})()
        self.reasoner.model = model
        self.reasoner.call_log = []
        self.reasoner.llm_calls = 0
        self.reasoner.set_call_budget = lambda limit: setattr(self.reasoner, "max_llm_calls", limit)

    def record_usage(self, *, latency=0.0, prompt=None, completion=None, cost=None):
        self.reasoner.llm_calls += 1
        self.reasoner.call_log.append({"latency_seconds": latency, "prompt_tokens": prompt,
                                       "completion_tokens": completion, "cost": cost})

    def request_count(self):
        return len(self.reasoner.call_log)

    def usage_window(self, start):
        return summarize_call_log(self.reasoner.call_log[start:])

    def usage(self):
        return summarize_call_log(self.reasoner.call_log)


class FakeModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, system, user):
        self.calls.append((system, user))
        return self.response


def test_fake_extractor_separates_prompt_transport_parse_and_validation():
    spec = intent_spec.extract_core_view(simple_payment())
    model = FakeModel(spec)
    result = shadow_extractor.IntentShadowExtractor(model).extract(spec["requirement_history"])
    assert result.to_dict() == spec
    assert result.validation_errors(expected_history=spec["requirement_history"]) == []
    assert len(model.calls) == 1
    system, user = model.calls[0]
    assert "Do NOT generate Marlowe AST" in system
    assert "transaction_submitter" in system
    assert "10 ADA" in user
    assert "transaction_submitter" not in user
    assert "value=null" in user and "evidence=[]" in user
    assert "normalization_basis" in user and "ShadowSemanticCore" in system
    assert "Distinct amounts for distinct recipients" in system


def test_bounded_validation_feedback_preserves_validator_authority():
    valid = intent_spec.extract_core_view(simple_payment())
    invalid = deepcopy(valid)
    invalid["claims"] = None

    class SequencedModel:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            return invalid if len(self.calls) == 1 else valid

    model = SequencedModel()
    core, initial_errors = shadow_extractor.IntentShadowExtractor(
        model).extract_with_validation_feedback(valid["requirement_history"])
    assert initial_errors
    assert core.validation_errors(expected_history=valid["requirement_history"]) == []
    assert len(model.calls) == 2
    assert "Validation errors:" in model.calls[1][1]
    assert "never use ellipses" in model.calls[1][1]
    assert "Previous core:" not in model.calls[1][1]
    assert "10 ADA" in model.calls[1][1]


def test_scope_repair_changes_only_model_proposed_scopes():
    history = [{"version": 1, "messages": ["Grace deposits, then Jack deposits."]}]
    source = {
        "schema_version": intent_spec.CORE_SCHEMA_VERSION_V3,
        "requirement_history": history,
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "grace", "scope_type": "transition", "transition_kind": "deposit"},
            {"scope_id": "jack", "scope_type": "transition", "transition_kind": "deposit"},
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }

    class ScopeModel:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            if len(self.calls) == 1:
                return deepcopy(source)
            scopes = deepcopy(source["behavior_scopes"])
            scopes[1]["continuation_scope_id"] = "jack"
            return {"behavior_scopes": scopes}

    model = ScopeModel()
    core, initial = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V3
    ).extract_with_validation_feedback(history)
    assert any("multiple root transitions" in error for error in initial)
    assert core.validation_errors(expected_history=history) == []
    assert core.to_dict()["claims"] == source["claims"]
    assert len(model.calls) == 2
    assert "funding deposit is followed by a repayment deposit" in model.calls[1][0]
    assert "the first is not terminal" in model.calls[1][0]
    assert "a transition may not point to its timeout scope" in model.calls[1][0]
    assert "Do not preserve any invalid continuation_scope_id" in model.calls[1][0]
    assert "becoming available on or after a date is not a timeout" in model.calls[1][0]
    assert "allowed_fields_by_type" in json.loads(model.calls[1][1])["scope_schema_contract"]


@pytest.mark.parametrize("wrapped", [True, False])
def test_invalid_derived_from_repair_changes_only_links(wrapped):
    core = intent_spec.extract_core_view(simple_payment())
    invalid = deepcopy(core)
    amount = next(claim for claim in invalid["claims"] if claim["claim_id"] == "amount")
    amount["derived_from"] = ["asset"]

    class LinkModel:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            if len(self.calls) == 1:
                return invalid
            mapping = {"amount": None}
            return {"derived_from": mapping} if wrapped else mapping

    model = LinkModel()
    result, initial = shadow_extractor.IntentShadowExtractor(model).extract_with_validation_feedback(
        core["requirement_history"])
    assert any("invalid derived_from source claim" in error for error in initial)
    assert result.validation_errors(expected_history=core["requirement_history"]) == []
    assert result.to_dict() == core
    assert len(model.calls) == 2
    assert "Return exactly one JSON object with derived_from mapping" in model.calls[1][0]
    assert f"Repair policy {REPAIR_POLICY_VERSION}." in model.calls[1][0]


def test_orphan_repair_revalidates_model_proposed_scopes_and_claims():
    history = [{"version": 1, "messages": ["Grace deposits."]}]
    source = {
        "schema_version": intent_spec.CORE_SCHEMA_VERSION_V3,
        "requirement_history": history,
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "grace", "scope_type": "transition", "transition_kind": "deposit"},
            {"scope_id": "orphan", "scope_type": "terminal_outcome",
             "outcome_id": "orphan", "parent_scope_id": "grace"},
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }

    class OutcomeModel:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            if len(self.calls) == 1:
                return deepcopy(source)
            return {"behavior_scopes": deepcopy(source["behavior_scopes"][:2]), "claims": []}

    model = OutcomeModel()
    core, initial = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V3
    ).extract_with_validation_feedback(history)
    assert any("terminal outcome has no incoming continuation" in error for error in initial)
    assert core.validation_errors(expected_history=history) == []
    assert core.to_dict()["requirement_history"] == history
    assert len(model.calls) == 2
    assert "allowed_fields_by_type" in json.loads(model.calls[1][1])["scope_schema_contract"]


def test_deadline_repair_preserves_other_core_fields():
    message = "Grace deposits by 23:59 ngày 12/01/2027 (UTC+7)."
    history = [{"version": 1, "messages": [message]}]
    source = {
        "schema_version": intent_spec.CORE_SCHEMA_VERSION_V3,
        "requirement_history": history,
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        ],
        "claims": [{"claim_id": "deadline", "kind": "deposit_deadline_ms",
                    "value": 1799859540000, "criticality": "financial", "status": "derived",
                    "normalization_basis": "UTC+7 to POSIX milliseconds", "scope_id": "deposit",
                    "evidence": [{"requirement_version": 1, "message_index": 0,
                                  "span": "23:59 ngày 12/01/2027 (UTC+7)", "relation": "supports"}]}],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }

    class DeadlineModel:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            return deepcopy(source) if len(self.calls) == 1 else {
                "deadline_values": {"deadline": 1799773140000}}

    model = DeadlineModel()
    core, initial = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V3
    ).extract_with_validation_feedback(history)
    assert any("deadline value contradicts" in error for error in initial)
    assert core.validation_errors(expected_history=history) == []
    assert core.to_dict()["behavior_scopes"] == source["behavior_scopes"]
    assert f"Repair policy {REPAIR_POLICY_VERSION}." in model.calls[1][0]
    assert "Repair only numeric POSIX millisecond values" in model.calls[1][0]


def test_requested_core_version_is_repaired_and_cannot_silently_downgrade():
    old = funded_choice_core()
    current = deepcopy(old)
    current["schema_version"] = intent_spec.CORE_SCHEMA_VERSION_V3

    class SequencedModel:
        def __init__(self):
            self.calls = []

        def generate(self, _system, user):
            self.calls.append(user)
            return old if len(self.calls) == 1 else current

    model = SequencedModel()
    extractor = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V3)
    core, initial_errors = extractor.extract_with_validation_feedback(
        old["requirement_history"], max_repairs=1)
    assert initial_errors == [
        f"schema_version must equal {intent_spec.CORE_SCHEMA_VERSION_V3}"]
    assert extractor.validation_errors(core, old["requirement_history"]) == []
    assert len(model.calls) == 2
    assert "schema_version must equal" in model.calls[1]


def test_multiple_repairs_use_latest_errors_and_stop_on_valid_core():
    valid = intent_spec.extract_core_view(simple_payment())
    first = deepcopy(valid)
    first["claims"] = None
    second = deepcopy(valid)
    second["predicted_resolution"] = "not_a_resolution"

    class SequencedModel:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append(user)
            return (first, second, valid)[len(self.calls) - 1]

    model = SequencedModel()
    core, initial_errors = shadow_extractor.IntentShadowExtractor(
        model).extract_with_validation_feedback(valid["requirement_history"], max_repairs=3)
    assert initial_errors
    assert core.validation_errors(expected_history=valid["requirement_history"]) == []
    assert len(model.calls) == 3
    assert "claims must be a list" in model.calls[1]
    assert "claims must be a list" not in model.calls[2]


def test_repair_stalls_on_identical_core_and_never_exceeds_cap():
    valid = intent_spec.extract_core_view(simple_payment())
    invalid = deepcopy(valid)
    invalid["claims"] = None

    class RepeatingModel:
        calls = 0

        def generate(self, system, user):
            self.calls += 1
            return invalid

    model = RepeatingModel()
    core, errors = shadow_extractor.IntentShadowExtractor(
        model).extract_with_validation_feedback(valid["requirement_history"], max_repairs=3)
    assert errors and core.validation_errors(expected_history=valid["requirement_history"])
    assert model.calls == 2
    with pytest.raises(ValueError, match="0 through 3"):
        shadow_extractor.IntentShadowExtractor(model).extract_with_validation_feedback(
            valid["requirement_history"], max_repairs=4)


def test_business_decision_repair_preserves_source_claims_and_graph():
    from tests.stage2b.test_core_v4 import payment_release_core

    valid = payment_release_core()
    invalid = deepcopy(valid)
    invalid["predicted_resolution"] = "clarification_required"
    invalid["required_clarifications"] = ["What is the deadline?"]

    class Model:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            if len(self.calls) == 1:
                return deepcopy(invalid)
            return {"predicted_resolution": "accepted_interpretation",
                    "required_clarifications": []}

    model = Model()
    extractor = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V4)
    core, initial = extractor.extract_with_validation_feedback(
        valid["requirement_history"], max_repairs=1)
    assert initial == ["clarification prediction requires an unresolved claim or "
                       "unrepresented behavior observation"]
    assert core.validation_errors(expected_history=valid["requirement_history"]) == []
    assert core.to_dict()["claims"] == valid["claims"]
    assert core.to_dict()["behavior_scopes"] == valid["behavior_scopes"]
    assert extractor.repair_trace[0]["repair_kind"] == "BUSINESS_DECISION"
    assert "predicted_resolution and required_clarifications" in model.calls[1][0]


def test_evidence_repair_targets_allow_independent_observation_error():
    core = {"claims": [{"claim_id": "depositor"}]}
    errors = ["claim depositor: invalid evidence target/span",
              "claim depositor: supporting evidence required",
              "invalid unscored_observation"]
    assert shadow_extractor._evidence_repair_targets(core, errors) == {"depositor"}
    assert shadow_extractor._evidence_repair_targets(
        core, errors + ["scope deposit: invalid continuation_scope_id"]) == set()


def test_observation_repair_retries_rejected_span_without_changing_claims():
    from tests.stage2b.test_core_v4 import payment_release_core

    valid = payment_release_core()
    invalid = deepcopy(valid)
    invalid["unscored_observations"] = [{
        "observation_id": "obs-1", "text": "Unrelated note.",
        "reason": "irrelevant_context",
        "source_evidence": [{"requirement_version": 1, "message_index": 0,
                             "span": "not in source", "relation": "supports"}],
    }]

    class Model:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            if len(self.calls) == 1:
                return deepcopy(invalid)
            return {"claim_evidence_or_drop": {},
                    "observation_or_drop": {"obs-1": (
                        deepcopy(invalid["unscored_observations"][0])
                        if len(self.calls) == 2 else None)}}

    model = Model()
    extractor = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V4)
    core, initial = extractor.extract_with_validation_feedback(
        valid["requirement_history"], max_repairs=1)
    assert initial == ["invalid unscored_observation"]
    assert core.validation_errors(expected_history=valid["requirement_history"]) == []
    assert core.to_dict()["claims"] == valid["claims"]
    assert len(model.calls) == 3
    assert "rejected_repair" in model.calls[2][1]


def test_depositor_scope_repair_drops_source_negation_only_on_model_decision():
    from tests.stage2b.test_core_v4 import payment_release_core

    valid = payment_release_core()
    invalid = deepcopy(valid)
    invalid["requirement_history"][0]["messages"][0] += " Ann does not deposit."
    invalid["claims"].append({
        "claim_id": "non-depositor", "kind": "depositing_party",
        "value": "Ann does not deposit", "criticality": "nonfinancial",
        "status": "explicit", "scope_id": "global",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": "Ann does not deposit", "relation": "supports"}],
    })

    class Model:
        def __init__(self):
            self.calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            return deepcopy(invalid) if len(self.calls) == 1 else {
                "scope_or_drop": {"non-depositor": None}}

    model = Model()
    extractor = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V4)
    core, initial = extractor.extract_with_validation_feedback(
        invalid["requirement_history"], max_repairs=1)
    assert initial == ["claim non-depositor: depositing party must scope a deposit transition"]
    assert core.validation_errors(expected_history=invalid["requirement_history"]) == []
    assert core.to_dict()["claims"] == valid["claims"]
    assert extractor.repair_trace[0]["repair_kind"] == "PARTY_SCOPE"


def test_repair_stops_after_two_distinct_nonprogressing_outputs():
    valid = intent_spec.extract_core_view(simple_payment())

    class DriftingModel:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            output = deepcopy(valid)
            output["predicted_resolution"] = f"invalid-{self.calls}"
            return output

    model = DriftingModel()
    extractor = shadow_extractor.IntentShadowExtractor(model)
    core, initial = extractor.extract_with_validation_feedback(
        valid["requirement_history"], max_repairs=3)
    assert initial == ["invalid predicted_resolution"]
    assert core.validation_errors(expected_history=valid["requirement_history"])
    assert model.calls == 3
    assert len(extractor.repair_trace) == 2
    assert all(step["progressed"] is False for step in extractor.repair_trace)
    assert extractor.repair_trace[0]["before_codes"] == ["BUSINESS_DECISION"]


def test_worse_full_regeneration_does_not_replace_best_candidate():
    initial = intent_spec.extract_core_view(simple_payment())
    initial["predicted_resolution"] = "invalid-initial"
    worse = deepcopy(initial)
    worse["claims"][0]["kind"] = "not-a-claim-kind"

    class Model:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return deepcopy(initial if self.calls == 1 else worse)

    model = Model()
    extractor = shadow_extractor.IntentShadowExtractor(model)
    result, errors = extractor.extract_with_validation_feedback(
        initial["requirement_history"], max_repairs=1)
    assert model.calls == 2
    assert errors == ["invalid predicted_resolution"]
    assert result.to_dict() == initial
    assert extractor.repair_trace[0]["progressed"] is False


def test_unchanged_targeted_repair_falls_back_to_full_regeneration_once():
    valid = intent_spec.extract_core_view(simple_payment())
    invalid = deepcopy(valid)
    amount = next(item for item in invalid["claims"] if item["claim_id"] == "amount")
    amount["derived_from"] = "missing-source"
    amount["evidence"] = []

    class Model:
        calls = 0

        def generate(self, system, user):
            self.calls += 1
            if self.calls == 1:
                return deepcopy(invalid)
            if "Repair only invalid derived_from references" in system:
                return {"derived_from": {"amount": "missing-source"}}
            assert "Regenerate the complete seven-field core" in user
            return deepcopy(valid)

    model = Model()
    extractor = shadow_extractor.IntentShadowExtractor(model)
    result, initial = extractor.extract_with_validation_feedback(
        valid["requirement_history"], max_repairs=3)

    assert "claim amount: invalid derived_from source claim" in initial
    assert result.validation_errors(expected_history=valid["requirement_history"]) == []
    assert model.calls == 3
    assert [item["repair_kind"] for item in extractor.repair_trace] == [
        "PROVENANCE_LINK", "FULL_REGENERATION_FALLBACK"]
    assert extractor.repair_trace[0]["progressed"] is False
    assert extractor.repair_trace[1]["progressed"] is True


def test_v4_choice_evidence_repair_keeps_existing_graph_and_values():
    history = [{"version": 1, "messages": [
        "Tina may choose integer 1 to cancel or integer 0 to confirm."]}]
    source = {
        "schema_version": intent_spec.CORE_SCHEMA_VERSION_V4,
        "requirement_history": history,
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "choice", "scope_type": "transition", "transition_kind": "choice",
             "choice_bounds": {"from": 0, "to": 1, "source_evidence": [{
                 "requirement_version": 1, "message_index": 0,
                 "span": "integer 1 to cancel or integer 0", "relation": "supports"}]}},
            {"scope_id": "confirm", "scope_type": "branch", "decision_id": "choice",
             "branch_id": "confirm", "choice_guard": {"operator": "eq", "value": 0,
                 "source_evidence": [{"requirement_version": 1, "message_index": 0,
                                     "span": "Tina may choose 0 confirmed",
                                     "relation": "supports"}]}}
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }
    replacement = [{"requirement_version": 1, "message_index": 0,
                    "span": "integer 0 to confirm", "relation": "supports"}]

    class Model:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return (deepcopy(source) if self.calls == 1 else
                    {"evidence_by_scope": {"confirm": replacement}})

    model = Model()
    extractor = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V4)
    result, errors = extractor.extract_with_validation_feedback(history)
    assert errors == ["scope confirm: invalid choice_guard"]
    assert result.validation_errors(expected_history=history) == []
    assert result.to_dict()["behavior_scopes"][2]["choice_guard"] == {
        **source["behavior_scopes"][2]["choice_guard"], "source_evidence": replacement}
    assert extractor.repair_trace[0]["repair_kind"] == "CHOICE_EVIDENCE"


def test_v4_choice_evidence_retries_one_noncontiguous_span():
    history = [{"version": 1, "messages": [
        "Tina chooses integer 1 to cancel or integer 0 to confirm."]}]
    draft = {
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "choice", "scope_type": "transition", "transition_kind": "choice",
             "choice_bounds": {"from": 0, "to": 1, "source_evidence": [{
                 "requirement_version": 1, "message_index": 0,
                 "span": "integer 1 to cancel or integer 0", "relation": "supports"}]}},
            {"scope_id": "confirm", "scope_type": "branch", "decision_id": "choice",
             "branch_id": "confirm", "choice_guard": {"operator": "eq", "value": 0,
                 "source_evidence": [{"requirement_version": 1, "message_index": 0,
                                     "span": "Tina chooses 0 confirmed",
                                     "relation": "supports"}]}}
        ],
        "claims": [], "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }

    class Model:
        calls = 0

        def generate(self, _system, user):
            self.calls += 1
            if self.calls == 1:
                return deepcopy(draft)
            if self.calls == 2:
                return {"evidence_by_scope": {"confirm": [{
                    "requirement_version": 1, "message_index": 0,
                    "span": "Tina chooses 0 confirmed", "relation": "supports"}]}}
            assert "rejected_evidence_by_scope" in user
            return {"evidence_by_scope": {"confirm": [{
                "requirement_version": 1, "message_index": 0,
                "span": "integer 0 to confirm", "relation": "supports"}]}}

    model = Model()
    extractor = shadow_extractor.IntentShadowExtractor(
        model, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V4)
    result, _ = extractor.extract_with_validation_feedback(history)
    assert model.calls == 3
    assert result.validation_errors(expected_history=history) == []
    assert extractor.repair_trace[0]["repair_kind"] == "CHOICE_EVIDENCE"


def test_repair_guidance_keeps_approval_evidence_and_questions_source_grounded():
    guidance = shadow_extractor._repair_guidance({}, [
        "scope decision-2: invalid choice_bounds",
        "scope branch-2: invalid choice_guard",
        "required_clarifications must contain nonempty questions",
    ])
    assert len(guidance) == 3
    assert "case-sensitive" in guidance[0]["rule"]
    assert "nonempty JSON array" in guidance[0]["rule"]
    assert "Do not omit choice_bounds" in guidance[0]["rule"]
    assert "not one object" in guidance[1]["rule"]
    assert "Do not omit choice_guard" in guidance[1]["rule"]
    assert "do not invent a rejection branch" in guidance[1]["rule"]
    assert "JSON array" in guidance[2]["rule"]
    assert "question strings" in guidance[2]["rule"]


def test_repair_feedback_groups_repeated_rules_without_losing_diagnostics():
    guidance = [
        {"error": "claim first: invalid derived_from source claim", "rule": "Fix link"},
        {"error": "claim second: invalid derived_from source claim", "rule": "Fix link"},
        {"error": "claim deadline: invalid value", "rule": "Use source instant",
         "source_backed_utc_milliseconds": [1798909200000]},
    ]
    grouped = shadow_extractor._group_repair_guidance(guidance)
    assert len(grouped) == 2
    assert [item["error"] for item in grouped[0]["diagnostics"]] == [
        guidance[0]["error"], guidance[1]["error"]]
    assert grouped[1]["diagnostics"][0]["source_backed_utc_milliseconds"] == [
        1798909200000]


def test_evidence_only_repair_keeps_other_core_fields_unchanged():
    valid = intent_spec.extract_core_view(simple_payment())
    invalid = deepcopy(valid)
    claim = next(item for item in invalid["claims"] if item.get("evidence"))
    claim_id = claim["claim_id"]
    original_evidence = deepcopy(claim["evidence"])
    claim["evidence"][0]["span"] = "not an exact source quote ..."

    class EvidenceModel:
        calls = []

        def generate(self, system, user):
            self.calls.append((system, user))
            if len(self.calls) == 1:
                return invalid
            return {"evidence_by_claim": {claim_id: original_evidence}}

    model = EvidenceModel()
    core, initial_errors = shadow_extractor.IntentShadowExtractor(
        model).extract_with_validation_feedback(valid["requirement_history"])
    assert initial_errors
    assert core.to_dict() == valid
    assert "Repair only the evidence" in model.calls[1][0]
    assert claim_id in model.calls[1][1]
    assert "not an exact source quote" in claim["evidence"][0]["span"]


def test_evidence_repair_supplies_verbatim_cited_source_message():
    valid = intent_spec.extract_core_view(simple_payment())
    invalid = deepcopy(valid)
    claim = next(item for item in invalid["claims"] if item.get("evidence"))
    original = deepcopy(claim["evidence"])
    claim["evidence"][0]["span"] = "merged phrase absent from source"
    calls = []

    class EvidenceModel:
        def generate(self, system, user):
            calls.append((system, user))
            if len(calls) == 1:
                return invalid
            return {"evidence_by_claim": {claim["claim_id"]: original}}

    shadow_extractor.IntentShadowExtractor(EvidenceModel()).extract_with_validation_feedback(
        valid["requirement_history"])
    repair = json.loads(calls[1][1])
    cited = repair["verbatim_source_messages"][claim["claim_id"]]
    assert cited == [{"requirement_version": original[0]["requirement_version"],
                      "message_index": original[0]["message_index"],
                      "message": valid["requirement_history"][
                          original[0]["requirement_version"] - 1]["messages"][
                              original[0]["message_index"]]}]
    assert "rather than joining fragments" in calls[1][0]


def test_evidence_repair_rejects_unlisted_claim_changes():
    core = intent_spec.extract_core_view(simple_payment())
    claim = next(item for item in core["claims"] if item.get("evidence"))
    target = {claim["claim_id"]}
    proposed = {"evidence_by_claim": {claim["claim_id"]: claim["evidence"],
                                      "unlisted": claim["evidence"]}}
    assert shadow_extractor._apply_evidence_repair(core, proposed, target) is None


def test_date_only_feedback_never_invents_posix_milliseconds():
    guidance = shadow_extractor._repair_guidance({}, [
        "claim deadline: deadline value contradicts cited calendar date",
    ])
    assert "value=null" in guidance[0]["rule"]
    assert "Never shift" in guidance[0]["rule"]


def test_repair_guidance_uses_exact_local_instant_and_detects_ada_unit_duplicate():
    span = "trước 00:00 ngày 03/01/2027 theo giờ Việt Nam (UTC+7)"
    core = {"claims": [
        {"claim_id": "deadline", "kind": "deposit_deadline_ms",
         "evidence": [{"relation": "supports", "span": span}]},
        {"claim_id": "normalized", "kind": "amount_lovelace", "scope_id": "deposit",
         "value": 20_000_000},
        {"claim_id": "raw", "kind": "amount_lovelace", "scope_id": "deposit",
         "value": 20},
    ]}
    guidance = shadow_extractor._repair_guidance(core, [
        "claim deadline: deadline value contradicts cited calendar date",
        "active claim conflict for amount_lovelace in deposit",
        "claim normalized: invalid derived_from source claim",
    ])
    assert guidance[0]["source_backed_utc_milliseconds"] == [1798909200000]
    assert "20000000-lovelace" in guidance[1]["rule"]
    assert "omit that raw" in guidance[2]["rule"]
    assert "points to an asset claim" in guidance[2]["rule"]


def test_prompt_and_repair_distinguish_corrected_value_and_outcome_reachability():
    history = [{"version": 1, "messages": ["Alice lends 102 ADA to Bob."]},
               {"version": 2, "messages": ["I meant 101 ADA, not 102 ADA."]}]
    system, user = shadow_extractor.build_prompt(
        history, core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V3)
    assert "earlier value is superseded, not an active conflict" in user
    assert "parent_scope_id describes ownership" in system
    assert "continuation_scope_id" in system
    guidance = shadow_extractor._repair_guidance(
        {"claims": [
            {"claim_id": "old", "kind": "amount_lovelace", "scope_id": "deposit",
             "value": 102_000_000},
            {"claim_id": "new", "kind": "amount_lovelace", "scope_id": "deposit",
             "value": 101_000_000},
        ]}, ["active claim conflict for amount_lovelace in deposit"], history)
    assert "earlier claim superseded" in guidance[0]["rule"]
    assert "exact provenance" in guidance[0]["rule"]


def test_repair_guidance_resolves_english_shared_timezone_from_source_message():
    message = ("Helen deposits before 23:59 on 09/01/2027 in Vietnam time (UTC+7). "
               "Kate deposits before 23:59 on 16/01/2027 in the same timezone.")
    history = [{"version": 1, "messages": [message]}]
    core = {"claims": [{"claim_id": "kate-deadline", "kind": "deposit_deadline_ms",
                        "evidence": [{"requirement_version": 1, "message_index": 0,
                                      "span": "before 23:59 on 16/01/2027 in the same timezone",
                                      "relation": "supports"}]}]}
    guidance = shadow_extractor._repair_guidance(core, [
        "claim kate-deadline: deadline value contradicts cited calendar date"], history)
    expected = int(datetime(2027, 1, 16, 23, 59,
                            tzinfo=timezone(timedelta(hours=7))).timestamp() * 1000)
    assert guidance[0]["source_backed_utc_milliseconds"] == [expected]


def test_calendar_hints_are_source_only_and_preserve_timezone_uncertainty():
    history = [{"version": 1, "messages": ["Before 08/01/2027."]},
               {"version": 2, "messages": ["Use 2027-01-15T00:00:00Z."]}]
    hints = shadow_extractor._calendar_hints(history)
    assert hints[0]["calendar_date"] == "2027-01-08"
    assert hints[0]["timezone_unresolved"] is True
    assert "exact_utc_milliseconds" not in hints[0]
    assert hints[1]["exact_utc_milliseconds"] == 1799971200000
    _, user = shadow_extractor.build_prompt(history)
    assert "Deterministic calendar hints" in user
    assert "2027-01-15T00:00:00Z" in user
    system, _ = shadow_extractor.build_prompt(history)
    assert "never ask them to calculate POSIX" in system


def test_calendar_hint_resolves_local_clock_with_explicit_utc_offset():
    history = [{"version": 1, "messages": [
        "Bình nạp trước 00:00 ngày 03/01/2027 theo giờ Việt Nam (UTC+7)."]}]
    hints = shadow_extractor._calendar_hints(history)
    assert len(hints) == 1
    assert hints[0]["exact_utc_milliseconds"] == 1798909200000
    assert "timezone_unresolved" not in hints[0]


def test_choice_prompt_forbids_transition_to_its_branch():
    system, _ = shadow_extractor.build_prompt(
        [{"version": 1, "messages": ["Alice chooses between 0 and 100."]}],
        core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V3)
    assert "Omit continuation_scope_id on the Choice transition itself" in system
    assert "source_evidence is a NONEMPTY JSON ARRAY" in system


def test_loan_prompt_distinguishes_account_owner_from_disbursement_recipient():
    system, _ = shadow_extractor.build_prompt(
        [{"version": 1, "messages": ["Alice lends Bob 10 ADA, then Bob repays 12 ADA."]}],
        core_schema_version=intent_spec.CORE_SCHEMA_VERSION_V4)
    assert "deposit into a Marlowe account is not a transfer to the borrower" in system
    assert "distinct Pay" in system
    assert "destination_account_owner merely because they receive" in system
    assert "preserving Unicode accents and case" in system
    assert "Never duplicate that same normalized amount" in system
    assert "amount_lovelace claim on EACH corresponding terminal" in system


def test_choice_prompt_contract_matches_evidence_array_validator():
    contract = intent_spec.core_prompt_schema_contract(
        version=intent_spec.CORE_SCHEMA_VERSION_V3)
    for field in ("choice_bounds", "choice_guard"):
        shape = contract["scope"][field]
        assert shape["source_evidence_type"] == "nonempty_array_of_evidence_objects"
        assert shape["source_evidence_item_fields"] == sorted(intent_spec.EVIDENCE_FIELDS)


def test_prompt_contract_tracks_validator_enums(monkeypatch):
    contract = intent_spec.core_prompt_schema_contract()
    fields = {
        "statuses": (contract["claim"]["statuses"], intent_spec.CLAIM_STATUSES),
        "criticalities": (contract["claim"]["criticalities"], intent_spec.CRITICALITIES),
        "resolutions": (contract["resolution"]["values"], intent_spec.RESOLUTIONS),
        "scope_types": (contract["scope"]["types"], intent_spec.SCOPE_TYPES),
        "evidence": (contract["evidence"]["relations"], intent_spec.EVIDENCE_RELATIONS),
    }
    assert all(actual == sorted(expected) for actual, expected in fields.values())
    _, user = shadow_extractor.build_prompt(simple_payment()["requirement_history"])
    embedded = json.loads(user.split("Validator schema contract (closed enum/field vocabulary):\n", 1)[1]
                          .split("\n", 1)[0])
    assert embedded == contract
    for key, value in (("CLAIM_STATUSES", "new-status"),
                       ("RESOLUTIONS", "new-resolution"),
                       ("SCOPE_TYPES", "new-scope"),
                       ("CRITICALITIES", "new-criticality"),
                       ("EVIDENCE_RELATIONS", "new-relation")):
        monkeypatch.setattr(intent_spec, key, getattr(intent_spec, key) | {value})
    updated = intent_spec.core_prompt_schema_contract()
    assert "new-status" in updated["claim"]["statuses"]
    assert "new-resolution" in updated["resolution"]["values"]
    assert "new-scope" in updated["scope"]["types"]
    assert "new-criticality" in updated["claim"]["criticalities"]
    assert "new-relation" in updated["evidence"]["relations"]
    spec = intent_spec.extract_core_view(simple_payment())
    spec["claims"][0]["criticality"] = "new-criticality"
    assert not any("invalid criticality" in error for error in intent_spec.validate_shadow_semantic_core(spec))
    spec = intent_spec.extract_core_view(simple_payment())
    spec["claims"][0]["evidence"][0]["relation"] = "new-relation"
    assert not any("invalid evidence target/span" in error
                   for error in intent_spec.validate_shadow_semantic_core(spec))


def test_prompt_contract_covers_scope_and_rich_shapes():
    contract = intent_spec.prompt_schema_contract()
    assert contract["scope"]["allowed_fields_by_type"] == {
        key: sorted(value) for key, value in intent_spec.SCOPE_FIELDS.items()}
    assert contract["rich_fields"] == {
        key: sorted(value) for key, value in intent_spec.RICH_FIELDS.items()}
    assert contract["state_ids"] == sorted(intent_spec.STATE_IDS)
    assert contract["outcome_recipient_kinds"] == {
        key: sorted(value) for key, value in intent_spec.OUTCOME_RECIPIENT_KINDS.items()}


def test_parser_rejects_non_object_output():
    with pytest.raises(ValueError, match="JSON object"):
        shadow_extractor.parse_model_output(["not-an-object"])


def test_dry_run_default_loads_development_canonical_without_model(tmp_path, monkeypatch):
    def forbid_model(*_args, **_kwargs):
        raise AssertionError("dry-run must not instantiate live transport")

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", forbid_model)
    output = tmp_path / "dry-run.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--output", str(output)])
    assert run_shadow.main() == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10
    assert all(row["split"] == "development" for row in rows)
    assert all(row["prediction"] is None and "prompt" in row for row in rows)
    assert all(row["source_corpus_version"] == "stage2a-v1" for row in rows)


def test_validation_split_is_explicit(tmp_path, monkeypatch):
    output = tmp_path / "validation-prompts.jsonl"
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--split", "validation",
                                          "--output", str(output)])
    assert run_shadow.main() == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10
    assert all(row["split"] == "validation" for row in rows)


def test_live_requires_explicit_output_and_never_runs_by_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--live", "--case-id", "pay-d1"])
    with pytest.raises(SystemExit, match="2"):
        run_shadow.main()


def test_explicit_live_mode_uses_injected_fake_transport_only(tmp_path, monkeypatch):
    calls = []

    class FakeTransport(FakeTransportBase):
        def __init__(self, model):
            self.init_usage(model)
            self.calls = 0

        def generate(self, system, user):
            calls.append((system, user))
            self.calls += 1
            self.record_usage(latency=0.5, prompt=10, completion=20)
            return intent_spec.extract_core_view(simple_payment())

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "live.jsonl"
    monkeypatch.setattr(sys, "argv", live_argv("--case-id", "pay-d1", "--output", str(output)))
    assert run_shadow.main() == 0
    row = json.loads(output.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert row["model"] == "fake" and row["usage"]["calls"] == 1
    assert row["usage"]["prompt_tokens"] == 10 and row["usage"]["cost"] is None
    assert row["run_status"] == "core_invalid"
    assert row["semantic_core"]["schema_version"] == "stage2b-shadow-core-v1"
    assert row["projection_diagnostics"]["core_status"] == "invalid"
    assert row["prediction"]["schema_version"] == "stage2b-shadow-v1"
    assert "requirement_history differs from supplied source" in row["validation_errors"]


def test_runner_records_valid_raw_core_projection_and_usage(tmp_path, monkeypatch):
    source = intent_spec.extract_core_view(simple_payment())

    class FakeAdapter:
        def load(self, **_kwargs):
            return [{"case_id": "synthetic", "split": "development",
                     "requirement_history": source["requirement_history"]}]

    class FakeTransport(FakeTransportBase):
        def __init__(self, _model):
            self.init_usage()
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            self.record_usage(latency=0.1, prompt=10, completion=20)
            return source

    monkeypatch.setattr(run_shadow, "FrozenCandidateAdapter", FakeAdapter)
    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "native.jsonl"
    monkeypatch.setattr(sys, "argv", live_argv("--output", str(output)))
    assert run_shadow.main() == 0
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["run_status"] == "ok" and row["projection_classification"] == "PASS"
    assert row["semantic_core"] == source and row["core_validation_errors"] == []
    assert row["validation_errors"] == []
    assert row["prediction"]["obligations_and_outcomes"][0]["recipient"] == "Bob"
    assert row["projection_diagnostics"]["mandatory_eligible_count"] > 0
    assert row["projection_diagnostics"]["complete"]
    assert row["usage"]["calls"] == 1


def test_model_failure_preserves_prior_rows_continues_and_sanitizes(tmp_path, monkeypatch, capsys):
    secret = "sk-test-secret-do-not-log"
    output = tmp_path / "partial.jsonl"

    class FakeTransport(FakeTransportBase):
        def __init__(self, model):
            self.init_usage()
            self.calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            self.record_usage(latency=0.25, prompt=10, completion=5, cost=0.01)
            if self.calls == 2:
                completed = [json.loads(line) for line in
                             output.read_text(encoding="utf-8").splitlines()]
                assert len(completed) == 1 and completed[0]["run_status"] == "core_invalid"
                raise LLMTransientError(f"provider failed with key {secret}")
            return intent_spec.extract_core_view(simple_payment())

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    monkeypatch.setattr(sys, "argv", live_argv("--output", str(output)))
    assert run_shadow.main() == 0
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 10
    assert rows[0]["run_status"] == "core_invalid"
    assert rows[1]["run_status"] == "model_error" and rows[1]["prediction"] is None
    assert rows[1]["model_error"]["code"] == "provider_error"
    assert rows[1]["usage"]["calls"] == 1
    assert rows[1]["usage"]["prompt_tokens"] == 10
    assert rows[2]["run_status"] == "core_invalid"
    assert secret not in output.read_text(encoding="utf-8")
    assert secret not in capsys.readouterr().out
    assert sum(row["usage"]["calls"] for row in rows) == 10


def test_unexpected_model_programming_error_is_infrastructure_failure(tmp_path, monkeypatch):
    class BrokenTransport(FakeTransportBase):
        def __init__(self, _model):
            self.init_usage()

        def generate(self, _system, _user):
            raise KeyError("programmer bug")

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", BrokenTransport)
    output = tmp_path / "broken.jsonl"
    monkeypatch.setattr(sys, "argv", live_argv("--case-id", "pay-d1", "--output", str(output)))
    assert run_shadow.main() == 3
    summary = json.loads((tmp_path / "broken.jsonl.summary.json").read_text(encoding="utf-8"))
    assert summary["experiment_status"] == "INFRASTRUCTURE_FAILED"
    assert "programmer bug" not in json.dumps(summary)


@pytest.mark.parametrize(("response", "code", "phase"), [
    ("not JSON", "model_output_invalid_json", "model_output_parse"),
    (["not-an-object"], "invalid_model_output", "model_output_schema"),
])
def test_model_parse_failures_are_recorded(tmp_path, monkeypatch, response, code, phase):
    class FakeTransport(FakeTransportBase):
        def __init__(self, _model):
            self.init_usage()

        def generate(self, _system, _user):
            self.record_usage()
            return response

    monkeypatch.setattr(run_shadow, "LegacyReasonerTransport", FakeTransport)
    output = tmp_path / "parse-error.jsonl"
    monkeypatch.setattr(sys, "argv", live_argv("--case-id", "pay-d1", "--output", str(output)))
    assert run_shadow.main() == 0
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["run_status"] == "model_error"
    assert row["model_error"]["code"] == code
    assert row["model_error"]["phase"] == phase


def test_precheck_failures_do_not_truncate_existing_output(tmp_path, monkeypatch):
    output = tmp_path / "sentinel.jsonl"
    output.write_text("sentinel", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run_shadow.py", "--output", str(output)])
    with monkeypatch.context() as patch:
        patch.setattr(run_shadow.verify_freeze, "verify_freeze",
                      lambda _: (_ for _ in ()).throw(ValueError("freeze failed")))
        assert run_shadow.main() == 2
    assert output.read_text(encoding="utf-8") == "sentinel"
    monkeypatch.setattr(sys, "argv", live_argv("--output", str(output)))
    with monkeypatch.context() as patch:
        patch.setattr(run_shadow, "LegacyReasonerTransport",
                      lambda _: (_ for _ in ()).throw(LLMConfigError("bad config")))
        assert run_shadow.main() == 2
    assert output.read_text(encoding="utf-8") == "sentinel"
