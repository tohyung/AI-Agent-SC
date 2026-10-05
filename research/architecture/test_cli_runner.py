"""The default CLI path must retain explicit user gates and fail closed."""

from copy import deepcopy

from research.architecture.cli_runner import (
    LocalReviewerPolicy, SessionOptions, reviewed_expectation, run_session,
)
from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.stage2c.models import IntentDecision, IntentDecisionStatus
from research.stage4.declared_domain import DeclaredActionDomain
from research.stage3.test_funded_choice_v1 import funded_choice_core


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


def test_noninteractive_pipeline_waits_for_explicit_acceptance():
    core = funded_choice_core()
    result = run_session(core["requirement_history"][0]["messages"][0], StaticModel(core))
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
                         ContractModel(core), options=SessionOptions(interactive=True),
                         ask=lambda _question: next(answers), emit=progress.append)
    assert result["stages"]["intent_acceptance"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["compile"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["semantic_comparison"]["run_status"] == "INCONCLUSIVE"
    assert result["status"] == "CANDIDATE_ONLY"
    assert result["stages"]["ledger_validation"]["run_status"] != "SUCCEEDED"
    assert "Đang chạy: intent_extraction" in progress
    assert "Đang chạy: compile" in progress


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
