"""Observed reference identity is metadata, never implicit promotion input."""

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage3.authority import CompilerAuthorityPort
from research.stage3.models import CompilerAuthorityDecision, CompilerAuthorityStatus


PROFILE = {"profile_id": "direct-payment", "version": "v1",
           "compiler_id": "deterministic-direct-payment", "compiler_version": "0.1.0",
           "intent_schema_version": "stage2b-shadow-v1"}


def _contract(value):
    return ArtifactEnvelope("contract-candidate", "core-v1", "compile",
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.DETERMINISTIC_COMPILER_CANDIDATE,
                            {"contract": value, "profile": PROFILE})


def _comparison(contract_id, identity="real-pinned-id"):
    return ArtifactEnvelope("reference-comparison", "v1", "semantic_comparison",
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.NO_AUTHORITY,
                            {"contract_artifact_id": contract_id,
                             "reference_identity": identity, "verdict": "SATISFIED"})


def test_current_contract_observed_identity_is_candidate_metadata():
    contract = _contract("close")
    result = CompilerAuthorityPort().execute(
        [contract, _comparison(contract.artifact_id)], StageContext("test"))
    assert result.result.run_status == StageRunStatus.SUCCEEDED
    assert result.result.semantic_status == "CANDIDATE_ONLY"
    assert result.result.authority_level == AuthorityLevel.NO_AUTHORITY
    assert result.artifacts[0].payload["reference_identity"] == "real-pinned-id"
    assert result.artifacts[0].payload["decision"] is None


def test_other_contract_identity_cannot_be_reported_as_observed():
    contract = _contract("close")
    other = _contract({"pay": 1, "then": "close"})
    comparison = _comparison(other.artifact_id, "identity-from-other")
    no_config = CompilerAuthorityPort().execute([contract, comparison], StageContext("test"))
    assert no_config.artifacts[0].payload["reference_identity"] == "unavailable"
    configured = CompilerAuthorityPort().execute(
        [contract, comparison], StageContext("test", {"reference_identity": "configured-id"}))
    assert configured.artifacts[0].payload["reference_identity"] == "configured-id"
    assert configured.result.semantic_status == "CANDIDATE_ONLY"


def test_observed_identity_alone_does_not_authorize_promotion():
    contract = _contract("close")
    comparison = _comparison(contract.artifact_id)
    decision = CompilerAuthorityDecision(
        CompilerAuthorityStatus.AUTHORIZED_FOR_PROFILE, "direct-payment", "v1",
        "deterministic-direct-payment", "0.1.0", "stage2b-shadow-v1",
        "marlowe-core-v1", "real-pinned-id", "v1", ("evidence",), "reviewer")

    class Permit:
        def authorize(self, decision, contract, comparison):
            return True

    result = CompilerAuthorityPort(Permit()).execute(
        [contract, comparison], StageContext("test", {"compiler_authority_decision": decision}))
    assert result.result.semantic_status == "CANDIDATE_ONLY"
    assert result.result.authority_level == AuthorityLevel.NO_AUTHORITY
    assert result.artifacts[0].payload["reference_identity"] == "real-pinned-id"
    assert result.artifacts[0].payload["decision"] is None
