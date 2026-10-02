"""Offline observable comparison contracts; real reference is tested separately."""

from copy import deepcopy

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage3.comparison import BehaviorExpectation, SemanticComparisonPort
from research.stage3.reference import ReferenceRequest


PAYMENT = {"source_account": {"role_token": "Alice"},
           "payee": {"party": {"role_token": "Bob"}},
           "token": {"currency_symbol": "", "token_name": ""}, "amount": 10000000}


class StaticReference:
    def __init__(self, result):
        self.result = result

    def execute(self, request):
        return self.result


def _run(raw, *, payments=(PAYMENT,), warnings=(), final_state=None,
         malformed_expectation=None, legacy=False):
    accepted = ArtifactEnvelope("accepted-intent", "v1", "unit",
                                ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY, {})
    contract = ArtifactEnvelope("contract-candidate", "v1", "unit",
                                ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY,
                                {"contract": "close"})
    expectation = BehaviorExpectation(
        accepted.artifact_id, "accepted_intent", ReferenceRequest(None, {}, ()),
        "Success", "close", "unit-reviewer",
        None if legacy else final_state,
        None if legacy else warnings,
        None if legacy else payments).to_dict()
    if malformed_expectation:
        expectation.update(malformed_expectation)
    external = ArtifactEnvelope("behavior-expectation", "v1", "unit",
                                ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY,
                                expectation)

    class Policy:
        def authorize(self, artifact):
            return artifact.artifact_id == external.artifact_id

    return SemanticComparisonPort(StaticReference(raw), Policy()).execute(
        [accepted, contract, external], StageContext("unit"))


def _raw():
    return {"status": "Success", "meta": {"upstream_commit": "unit",
                                         "reference_driver_version": "v1"},
            "steps": [{"status": "Success", "warnings": [], "payments": [PAYMENT]}],
            "final_contract": "close", "final_state": {"accounts": []}}


def test_old_expectation_uses_unchanged_payload_keys_and_legacy_comparison():
    legacy = BehaviorExpectation("accepted", "accepted_intent",
                                 ReferenceRequest(None, {}, ()), "Success", "close", "reviewer")
    assert set(legacy.to_dict()) == {"source_artifact_id", "source_kind", "request",
                                     "expected_status", "expected_final_contract", "reviewer_id"}
    raw = _raw()
    del raw["steps"]
    result = _run(raw, legacy=True)
    assert result.result.run_status == StageRunStatus.SUCCEEDED
    assert "mismatches" not in result.artifacts[0].payload
    del raw["final_contract"]
    assert _run(raw, legacy=True).result.run_status == StageRunStatus.FAILED


@pytest.mark.parametrize("malformed", [
    {"expected_final_state": None},
    {"expected_warnings": None},
    {"expected_warnings": [{}, "bad"]},
    {"expected_payments": "not-a-list"},
])
def test_malformed_expected_observables_block(malformed):
    result = _run(_raw(), malformed_expectation=malformed)
    assert result.result.run_status == StageRunStatus.BLOCKED


@pytest.mark.parametrize("field", ["warnings", "payments"])
def test_missing_requested_reference_observable_is_inconclusive(field):
    raw = _raw()
    del raw["steps"][0][field]
    result = _run(raw)
    assert result.result.run_status == StageRunStatus.INCONCLUSIVE
    assert result.result.semantic_status == "INCONCLUSIVE"
    assert field in result.artifacts[0].payload["unavailable_observables"]


def test_all_observables_match_or_name_only_mismatched_fields():
    raw = _raw()
    assert _run(raw, final_state={"accounts": []}).result.run_status == StageRunStatus.SUCCEEDED
    wrong = deepcopy(raw)
    wrong["steps"][0]["payments"][0]["payee"] = {"party": {"role_token": "Alice"}}
    result = _run(wrong, final_state={"accounts": []})
    assert result.result.run_status == StageRunStatus.FAILED
    assert result.result.semantic_status == "VIOLATED"
    assert result.artifacts[0].payload["mismatches"] == ["payments"]
    assert result.result.diagnostics == ["observable mismatch: payments"]


def test_successful_step_order_is_preserved():
    raw = _raw()
    second = {**PAYMENT, "amount": 1}
    raw["steps"].append({"status": "Success", "warnings": [], "payments": [second]})
    assert _run(raw, payments=(PAYMENT, second)).result.run_status == StageRunStatus.SUCCEEDED
    reversed_result = _run(raw, payments=(second, PAYMENT))
    assert reversed_result.artifacts[0].payload["mismatches"] == ["payments"]
