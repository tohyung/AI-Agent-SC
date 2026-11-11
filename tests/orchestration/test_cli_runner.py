"""The default CLI path must retain explicit user gates and fail closed."""

from copy import deepcopy

from research.orchestration.cli_runner import (
    LocalReviewerPolicy, SessionOptions, clarification_questions,
    reviewed_expectation, run_session,
)
from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.status import AuthorityLevel, ImplementationStatus
from research.ratification.models import IntentDecision, IntentDecisionStatus
from research.exploration.declared_domain import DeclaredActionDomain
from tests.synthesis.test_funded_choice_v1 import funded_choice_core
from research.formalization.intent_spec import (
    CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V4,
)


class StaticModel:
    def __init__(self, core):
        self.core = core
        self.calls = 0

    def generate(self, _system, _user):
        self.calls += 1
        return deepcopy(self.core)


class ContractModel(StaticModel):
    def generate(self, system, user):
        self.calls += 1
        if "Generate one canonical Marlowe" in system:
            return {"contract": "close", "mapping_evidence": []}
        return deepcopy(self.core)


def test_clarification_questions_use_formalization_string_schema():
    core = {"required_clarifications": ["Ai nhận tiền hoàn?", "Ai nhận tiền hoàn?",
                                        "Hạn chót là khi nào?"]}
    assert clarification_questions(core) == ["Ai nhận tiền hoàn?", "Hạn chót là khi nào?"]


def test_clarification_questions_use_formalization_object_schema():
    core = {"required_clarifications": [
        {"question": "  Ai nhận tiền hoàn?  ", "claim_ids": ["refund"]},
        "Ai nhận tiền hoàn?",
        {"question": "Hạn chót là khi nào?", "missing_claim_kind": "deadline"},
    ]}
    assert clarification_questions(core) == ["Ai nhận tiền hoàn?", "Hạn chót là khi nào?"]


def test_noninteractive_pipeline_waits_for_explicit_acceptance():
    core = funded_choice_core()
    result = run_session(core["requirement_history"][0]["messages"][0], StaticModel(core),
                         options=SessionOptions(formalization_method="DCF", core_schema_version=CORE_SCHEMA_VERSION_V2))
    assert result["status"] == "WAITING_USER"
    assert result["stop_reason"] == "explicit_acceptance_required"
    assert result["steps"]["intent_acceptance"]["run_status"] == "WAITING_USER"
    assert "compile" not in result["steps"]


def test_interactive_acceptance_uses_model_contract_without_claiming_ledger(monkeypatch):
    core = funded_choice_core()
    from research.adapters.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT
    monkeypatch.setattr("research.adapters.smt_gate.analyze", lambda *_a, **_k: {
        "status": "Valid", "warnings": [], "analysis_notes": [],
        "meta": {"upstream_commit": UPSTREAM_COMMIT, "driver_version": DRIVER_VERSION},
    })
    answers = iter(["dong y", "Tester"])
    progress = []
    result = run_session(core["requirement_history"][0]["messages"][0],
                         ContractModel(core), options=SessionOptions(formalization_method="DCF", 
                             interactive=True, core_schema_version=CORE_SCHEMA_VERSION_V2),
                         ask=lambda _question: next(answers), emit=progress.append)
    assert result["steps"]["intent_acceptance"]["run_status"] == "SUCCEEDED"
    assert result["steps"]["compile"]["run_status"] == "SUCCEEDED"
    assert result["steps"]["semantic_comparison"]["run_status"] == "INCONCLUSIVE"
    assert result["status"] == "CANDIDATE_ONLY"
    assert result["steps"]["ledger_validation"]["run_status"] != "SUCCEEDED"
    assert "Đang chạy: intent_extraction" in progress
    assert "Đang chạy: compile" in progress


def test_default_session_uses_aff_and_core_v4():
    assert SessionOptions().formalization_method == "AFF"
    assert SessionOptions().core_schema_version == CORE_SCHEMA_VERSION_V4


def test_aff_session_builds_the_core_from_a_fact_draft_and_waits_for_acceptance():
    from research.formalization.fact_extractor import EXAMPLE_DRAFT, EXAMPLE_REQUEST

    result = run_session(EXAMPLE_REQUEST, StaticModel(EXAMPLE_DRAFT))
    assert result["status"] == "WAITING_USER"
    assert result["stop_reason"] == "explicit_acceptance_required"
    assert result["candidate"]["formalization_method"] == "AFF"
    assert result["candidate"]["semantic_core"]["schema_version"] == CORE_SCHEMA_VERSION_V4


EXAMPLE_PROMPT_FOR_AFF_FAILURE = "Ana deposits 10 ADA for Bo before 2027-01-01 00:00 UTC."


def test_aff_session_with_a_non_draft_output_fails_without_a_candidate_core():
    result = run_session(EXAMPLE_PROMPT_FOR_AFF_FAILURE, StaticModel({"not": "a draft"}))
    assert result["status"] == "BLOCKED"


def test_dcf_session_rejects_v3_output():
    core = funded_choice_core()
    result = run_session(core["requirement_history"][0]["messages"][0], StaticModel(core),
                         options=SessionOptions(formalization_method="DCF"))
    assert result["status"] == "BLOCKED"
    assert result["stop_reason"] == "invalid_candidate"
    assert any("schema_version must equal" in item
               for item in result["candidate"]["core_validation_errors"])


def test_dcf_session_core_v4_reaches_human_acceptance_gate():
    core = funded_choice_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V4
    result = run_session(core["requirement_history"][0]["messages"][0], StaticModel(core),
                         options=SessionOptions(formalization_method="DCF"))
    assert result["status"] == "WAITING_USER"
    assert result["stop_reason"] == "explicit_acceptance_required"
    assert result["candidate"]["semantic_core"]["schema_version"] == CORE_SCHEMA_VERSION_V4
    assert "compile" not in result["steps"]


def test_roleplay_runs_main_ports_without_claiming_human_acceptance(monkeypatch):
    core = funded_choice_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V4
    prompt = core["requirement_history"][0]["messages"][0]

    def unexpected_ask(_question):
        raise AssertionError("roleplay must not request or fabricate human consent")

    waiting = run_session(prompt, ContractModel(core),
                          options=SessionOptions(formalization_method="DCF", roleplay=True), ask=unexpected_ask)
    assert waiting["status"] == "WAITING_RESEARCH_REVIEW"
    assert waiting["simulation_only"] is True
    assert "compile" not in waiting["steps"]
    candidate_id = waiting["steps"]["intent_extraction"]["output_artifacts"][0]
    stale_review = run_session(prompt, ContractModel(core), options=SessionOptions(formalization_method="DCF", 
        roleplay=True, roleplay_reviewed_candidate_id="intent-candidate:stale"),
        ask=unexpected_ask)
    assert stale_review["status"] == "WAITING_RESEARCH_REVIEW"

    from research.adapters.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT
    monkeypatch.setattr("research.adapters.smt_gate.analyze", lambda *_a, **_k: {
        "status": "Valid", "warnings": [], "analysis_notes": [],
        "meta": {"upstream_commit": UPSTREAM_COMMIT, "driver_version": DRIVER_VERSION},
    })
    reviewed = run_session(prompt, ContractModel(core),
                           options=SessionOptions(formalization_method="DCF", 
                               roleplay=True,
                               roleplay_reviewed_candidate_id=candidate_id),
                           ask=unexpected_ask)
    assert reviewed["status"] == "SIMULATED_CANDIDATE_ONLY"
    assert reviewed["steps"]["intent_acceptance"]["authority_level"] == "NO_AUTHORITY"
    assert reviewed["steps"]["compile"]["run_status"] == "SUCCEEDED"
    assert reviewed["contract_candidate"]["payload"]["simulation_only"] is True


def test_reviewer_policy_requires_exact_candidate_and_consent():
    class Candidate:
        payload = {"intent_spec": {"claims": ["approved"]}}

    policy = LocalReviewerPolicy("Tester")
    assert policy.authorize(Candidate(), IntentDecision(
        IntentDecisionStatus.ACCEPTED, "Tester", True,
        approved_spec={"claims": ["approved"]}))
    assert not policy.authorize(Candidate(), IntentDecision(
        IntentDecisionStatus.ACCEPTED, "Tester", True,
        approved_spec={"claims": ["altered"]}))


def test_expectation_requires_interaction_and_pinned_reference():
    expectation = {"request": {"state": {}, "transactions": [{}]},
                   "expected_status": "Success"}
    try:
        SessionOptions(formalization_method="DCF", expectation=expectation)
    except ValueError:
        pass
    else:
        raise AssertionError("an unreviewed expectation was accepted")


def test_reviewed_expectation_rejects_hollow_or_invalid_reference_request():
    accepted = ArtifactEnvelope("accepted-intent", "v1", "intent_acceptance",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.USER_ACCEPTED_INTENT, {})
    request = {"state": {"accounts": [], "choices": [], "boundValues": [], "minTime": 0},
               "transactions": [{"interval": {"from": 0, "to": 0}, "inputs": []}]}
    base = {"request": request, "expected_status": "Success"}
    for payload in (base, {**base, "expected_final_contract": None},
                    {**base, "expected_final_contract": "close",
                     "request": {"state": {}, "transactions": request["transactions"]}}):
        try:
            reviewed_expectation(accepted, payload, "Tester")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid expectation was accepted")
    result = reviewed_expectation(accepted,
                                  {**base, "expected_final_contract": "close"}, "Tester")
    assert result.payload["source_artifact_id"] == accepted.artifact_id
    assert result.payload["request"]["contract"] is None


def test_declared_domain_matches_notify_without_inventing_input():
    notify = {"interval": {"from": 0, "to": 0}, "inputs": [{"type": "Notify"}]}
    domain = DeclaredActionDomain("reviewed", (notify,))
    contract = {"when": [{"case": {"notify_if": True}, "then": "close"}],
                "timeout": 100, "timeout_continuation": "close"}
    assert domain.transactions({}, contract) == [notify]
    assert domain.transactions({}, {"when": [], "timeout": 100,
                                    "timeout_continuation": "close"}) == []
