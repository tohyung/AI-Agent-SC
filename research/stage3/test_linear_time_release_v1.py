"""Offline coverage for a two-installment funded time release."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

import pytest

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2, validate_intent_spec
from research.stage2b.projector import project_intent_spec
from research.stage3.compiler import CompilerPort
from research.stage3.profile_compilers.linear_time_release_v1 import (
    LINEAR_TIME_RELEASE_PROFILE, compile_linear_time_release_v1,
)
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import PinnedMarloweReference, ReferenceRequest


def _ms(day):
    return int(datetime(2027, 1, day, tzinfo=timezone.utc).timestamp() * 1000)


def release_core():
    message = (
        "Huy deposits 35 ADA in Huy's contract account before 08/01/2027. "
        "Pay Nga 17.5 ADA after 15/01/2027 and pay Nga the remaining "
        "17.5 ADA after 22/01/2027 from Huy's account."
    )

    def claim(claim_id, kind, value, scope_id, span, status="explicit"):
        item = {"claim_id": claim_id, "kind": kind, "value": value,
                "criticality": "financial", "status": status, "scope_id": scope_id,
                "evidence": [{"requirement_version": 1, "message_index": 0,
                              "span": span, "relation": "supports"}]}
        if status == "derived":
            item["normalization_basis"] = "source amount or date converted to canonical units"
        return item

    return {
        "schema_version": CORE_SCHEMA_VERSION_V2,
        "requirement_history": [{"version": 1, "messages": [message]}],
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "fund", "scope_type": "transition", "transition_kind": "deposit",
             "continuation_scope_id": "first"},
            {"scope_id": "first", "scope_type": "transition", "transition_kind": "payment",
             "continuation_scope_id": "second"},
            {"scope_id": "second", "scope_type": "transition", "transition_kind": "payment"},
        ],
        "claims": [
            claim("asset", "asset", "ADA", "global", "35 ADA"),
            claim("fund-amount", "amount_lovelace", 35000000, "fund", "35 ADA", "derived"),
            claim("depositor", "depositing_party", "Huy", "fund", "Huy deposits"),
            claim("account", "destination_account_owner", "Huy", "fund", "Huy's contract account"),
            claim("fund-deadline", "deposit_deadline_ms", _ms(8), "fund", "08/01/2027", "derived"),
            claim("first-amount", "amount_lovelace", 17500000, "first", "17.5 ADA", "derived"),
            claim("first-recipient", "payment_recipient", "Nga", "first", "Pay Nga 17.5 ADA"),
            claim("first-source", "payment_source_account_owner", "Huy", "first", "Huy's account"),
            claim("first-time", "timeout_ms", _ms(15), "first", "15/01/2027", "derived"),
            claim("second-amount", "amount_lovelace", 17500000, "second", "17.5 ADA", "derived"),
            claim("second-recipient", "payment_recipient", "Nga", "second", "pay Nga"),
            claim("second-source", "payment_source_account_owner", "Huy", "second", "Huy's account"),
            claim("second-time", "timeout_ms", _ms(22), "second", "22/01/2027", "derived"),
        ],
        "required_clarifications": [], "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }


def _compile(core):
    spec = project_intent_spec(core).intent_spec.to_dict()
    assert validate_intent_spec(spec, projected_core=core) == []
    accepted = ArtifactEnvelope("accepted-intent", "simulated-v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"accepted_spec": spec, "simulation_only": True})
    port = CompilerPort(ProfileRegistry([LINEAR_TIME_RELEASE_PROFILE]), {
        ("linear-time-release", "v1"): compile_linear_time_release_v1,
    })
    return port.execute([accepted], StageContext("test", {"allow_simulated_intent": True}))


def test_linear_time_release_compiles_two_ordered_payments():
    result = _compile(release_core())
    assert result.result.run_status == StageRunStatus.SUCCEEDED, result.result.diagnostics
    artifact = next(item for item in result.artifacts if item.artifact_type == "contract-candidate")
    contract = artifact.payload["contract"]
    first_when = contract["when"][0]["then"]
    assert first_when["when"] == [] and first_when["timeout"] == _ms(15)
    first_pay = first_when["timeout_continuation"]
    assert first_pay["pay"] == 17500000
    second_when = first_pay["then"]
    assert second_when["timeout"] == _ms(22)
    assert second_when["timeout_continuation"]["then"] == "close"
    assert artifact.payload["simulation_only"] is True


def test_linear_time_release_rejects_nonconserved_or_reversed_payouts():
    core = release_core()
    next(item for item in core["claims"] if item["claim_id"] == "second-amount")["value"] = 17000000
    result = _compile(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED
    assert "conserve" in " ".join(result.result.diagnostics)
    core = deepcopy(release_core())
    first_time = next(item for item in core["claims"] if item["claim_id"] == "first-time")
    first_time["value"] = _ms(22)
    first_time["evidence"][0]["span"] = "22/01/2027"
    second_time = next(item for item in core["claims"] if item["claim_id"] == "second-time")
    second_time["value"] = _ms(15)
    second_time["evidence"][0]["span"] = "15/01/2027"
    result = _compile(core)
    assert result.result.run_status == StageRunStatus.UNSUPPORTED
    assert "deadlines" in " ".join(result.result.diagnostics)


def test_linear_time_release_real_reference_pays_at_both_timeouts():
    if shutil.which("cabal") is None or shutil.which("ghc") is None:
        pytest.skip("real Haskell reference toolchain unavailable")
    root = Path(__file__).resolve().parents[2] / "tools/marlowe_smt"
    resolved = subprocess.run(["cabal", "list-bin", "exe:marlowe-reference"],
                              cwd=root, capture_output=True, text=True, check=True)
    binary = resolved.stdout.strip()
    if not Path(binary).is_file():
        pytest.fail("real reference executable missing")
    execution = _compile(release_core())
    contract = next(item.payload["contract"] for item in execution.artifacts
                    if item.artifact_type == "contract-candidate")
    role = {"role_token": "Huy"}
    token = {"currency_symbol": "", "token_name": ""}

    def tx(instant, inputs):
        return {"interval": {"from": instant, "to": instant}, "inputs": inputs}

    request = ReferenceRequest(contract, {"accounts": [], "choices": [],
                                          "boundValues": [], "minTime": 0}, (
        tx(_ms(7), [{"type": "Deposit", "account": role, "party": role,
                     "token": token, "amount": 35000000}]),
        tx(_ms(15), []), tx(_ms(22), []),
    ))
    result = PinnedMarloweReference(binary=binary, hard_timeout_seconds=15).execute(request)
    assert result["status"] == "Success", result
    assert result["final_contract"] == "close"
    assert [payment["amount"] for step in result["steps"]
            for payment in step["payments"]] == [17500000, 17500000]
