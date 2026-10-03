"""Tuning-only acceptance cannot masquerade as authenticated human approval."""

from copy import deepcopy

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.experiments.simulated_acceptance import SimulatedIntentAcceptancePort
from research.stage3.compiler import CompilerPort
from research.stage3.profile_compilers.direct_payment_v1 import (
    DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1,
)
from research.stage3.profiles import ProfileRegistry
from research.stage3.test_direct_payment_v1 import direct_payment_spec


def _candidate(spec):
    return ArtifactEnvelope(
        "intent-candidate", "v1", "intent_extraction",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED, AuthorityLevel.MODEL_CANDIDATE,
        {"intent_spec": spec, "source_history": spec["requirement_history"],
         "core_validation_errors": [], "full_validation_errors": []},
    )


def test_simulated_acceptance_is_no_authority_and_compiler_requires_opt_in():
    spec = direct_payment_spec()
    spec["requirement_history"].append({"version": 2, "messages": ["Alice owns the account."]})
    transcript = [{"question": "Who owns the account?", "answer": "Alice owns the account.",
                   "synthetic_assumption": True}]
    acceptance = SimulatedIntentAcceptancePort().execute(
        [_candidate(spec)], StageContext("batch", {"simulation_transcript": transcript}))
    assert acceptance.result.run_status == StageRunStatus.SUCCEEDED
    accepted = acceptance.artifacts[0]
    assert accepted.authority_level == AuthorityLevel.NO_AUTHORITY
    assert accepted.payload["simulation_only"] is True
    compiler = CompilerPort(ProfileRegistry([DIRECT_PAYMENT_PROFILE]),
                            {("direct-payment", "v1"): compile_direct_payment_v1})
    denied = compiler.execute([accepted], StageContext("ordinary"))
    assert denied.result.run_status == StageRunStatus.BLOCKED
    allowed = compiler.execute([accepted], StageContext("batch", {
        "allow_simulated_intent": True,
    }))
    assert allowed.result.run_status == StageRunStatus.SUCCEEDED
    assert any(item.artifact_type == "contract-candidate" for item in allowed.artifacts)


def test_simulated_acceptance_waits_for_unresolved_questions():
    spec = direct_payment_spec()
    spec["predicted_resolution"] = "clarification_required"
    spec["required_clarifications"] = ["Which account owns the funds?"]
    result = SimulatedIntentAcceptancePort().execute([_candidate(spec)], StageContext("batch"))
    assert result.result.run_status == StageRunStatus.WAITING_USER
    assert result.artifacts == []


def test_simulated_answer_must_be_in_requirement_history():
    spec = deepcopy(direct_payment_spec())
    transcript = [{"question": "Who owns the account?", "answer": "Alice",
                   "synthetic_assumption": True}]
    result = SimulatedIntentAcceptancePort().execute(
        [_candidate(spec)], StageContext("batch", {"simulation_transcript": transcript}))
    assert result.result.run_status == StageRunStatus.BLOCKED
    assert result.artifacts == []
