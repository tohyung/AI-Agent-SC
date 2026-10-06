"""The default CLI path must retain explicit user gates and fail closed."""

from copy import deepcopy

from research.architecture.cli_runner import (
    LocalReviewerPolicy, SessionOptions, clarification_questions,
    reviewed_expectation, run_session,
)
from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.stage2c.models import IntentDecision, IntentDecisionStatus
from research.stage4.declared_domain import DeclaredActionDomain
from research.stage3.test_funded_choice_v1 import funded_choice_core
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3


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


def test_clarification_questions_use_stage2b_string_schema():
    core = {"required_clarifications": ["Ai nhận tiền hoàn?", "Ai nhận tiền hoàn?",
                                        "Hạn chót là khi nào?"]}
    assert clarification_questions(core) == ["Ai nhận tiền hoàn?", "Hạn chót là khi nào?"]


def test_clarification_questions_use_stage2b_object_schema():
    core = {"required_clarifications": [
        {"question": "  Ai nhận tiền hoàn?  ", "claim_ids": ["refund"]},
        "Ai nhận tiền hoàn?",
        {"question": "Hạn chót là khi nào?", "missing_claim_kind": "deadline"},
    ]}
    assert clarification_questions(core) == ["Ai nhận tiền hoàn?", "Hạn chót là khi nào?"]


def test_noninteractive_pipeline_waits_for_explicit_acceptance():
    core = funded_choice_core()
    result = run_session(core["requirement_history"][0]["messages"][0], StaticModel(core),
                         options=SessionOptions(core_schema_version=CORE_SCHEMA_VERSION_V2))
    assert result["status"] == "WAITING_USER"
    assert result["stop_reason"] == "explicit_acceptance_required"
    assert result["stages"]["intent_acceptance"]["run_status"] == "WAITING_USER"
    assert "compile" not in result["stages"]


def test_interactive_acceptance_uses_model_contract_without_claiming_ledger(monkeypatch):
    core = funded_choice_core()
    from research.integrations.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT
    monkeypatch.setattr("research.integrations.smt_gate.analyze", lambda *_a, **_k: {
        "status": "Valid", "warnings": [], "analysis_notes": [],
        "meta": {"upstream_commit": UPSTREAM_COMMIT, "driver_version": DRIVER_VERSION},
    })
    answers = iter(["dong y", "Tester"])
    progress = []
    result = run_session(core["requirement_history"][0]["messages"][0],
                         ContractModel(core), options=SessionOptions(
                             interactive=True, core_schema_version=CORE_SCHEMA_VERSION_V2),
                         ask=lambda _question: next(answers), emit=progress.append)
    assert result["stages"]["intent_acceptance"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["compile"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["semantic_comparison"]["run_status"] == "INCONCLUSIVE"
    assert result["status"] == "CANDIDATE_ONLY"
    assert result["stages"]["ledger_validation"]["run_status"] != "SUCCEEDED"
    assert "Đang chạy: intent_extraction" in progress
    assert "Đang chạy: compile" in progress


def test_default_cli_core_schema_is_v3_and_rejects_v2_output():
    core = funded_choice_core()
    assert SessionOptions().core_schema_version == CORE_SCHEMA_VERSION_V3
    result = run_session(core["requirement_history"][0]["messages"][0], StaticModel(core))
    assert result["status"] == "BLOCKED"
    assert result["stop_reason"] == "invalid_candidate"
    assert any("schema_version must equal" in item
               for item in result["candidate"]["core_validation_errors"])


def test_default_cli_core_schema_v3_reaches_human_acceptance_gate():
    core = funded_choice_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V3
    result = run_session(core["requirement_history"][0]["messages"][0], StaticModel(core))
    assert result["status"] == "WAITING_USER"
    assert result["stop_reason"] == "explicit_acceptance_required"
    assert result["candidate"]["semantic_core"]["schema_version"] == CORE_SCHEMA_VERSION_V3
    assert "compile" not in result["stages"]


def test_roleplay_runs_main_ports_without_claiming_human_acceptance(monkeypatch):
    core = funded_choice_core()
    core["schema_version"] = CORE_SCHEMA_VERSION_V3
    prompt = core["requirement_history"][0]["messages"][0]

    def unexpected_ask(_question):
        raise AssertionError("roleplay must not request or fabricate human consent")

    waiting = run_session(prompt, ContractModel(core),
                          options=SessionOptions(roleplay=True), ask=unexpected_ask)
    assert waiting["status"] == "WAITING_RESEARCH_REVIEW"
    assert waiting["simulation_only"] is True
    assert "compile" not in waiting["stages"]
    candidate_id = waiting["stages"]["intent_extraction"]["output_artifacts"][0]
    stale_review = run_session(prompt, ContractModel(core), options=SessionOptions(
        roleplay=True, roleplay_reviewed_candidate_id="intent-candidate:stale"),
        ask=unexpected_ask)
    assert stale_review["status"] == "WAITING_RESEARCH_REVIEW"

    from research.integrations.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT
    monkeypatch.setattr("research.integrations.smt_gate.analyze", lambda *_a, **_k: {
        "status": "Valid", "warnings": [], "analysis_notes": [],
        "meta": {"upstream_commit": UPSTREAM_COMMIT, "driver_version": DRIVER_VERSION},
    })
    reviewed = run_session(prompt, ContractModel(core),
                           options=SessionOptions(
                               roleplay=True,
                               roleplay_reviewed_candidate_id=candidate_id),
                           ask=unexpected_ask)
    assert reviewed["status"] == "SIMULATED_CANDIDATE_ONLY"
    assert reviewed["stages"]["intent_acceptance"]["authority_level"] == "NO_AUTHORITY"
    assert reviewed["stages"]["compile"]["run_status"] == "SUCCEEDED"
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
        SessionOptions(expectation=expectation)
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
