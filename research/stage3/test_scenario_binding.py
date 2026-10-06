"""Abstract reviewed Choice actions bind mechanically, never by guessed names."""

from copy import deepcopy

import pytest

from research.stage3.scenario_binding import (ScenarioBindingError,
                                              bind_choice_transactions)
from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.stage4.declared_domain import DeclaredActionDomain


OWNER = {"role_token": "Lan"}
CHOICE = {"for_choice": {"choice_name": "internal-price-id", "choice_owner": OWNER},
          "choose_between": [{"from": 0, "to": 100}]}
CONTRACT = {"when": [{"case": CHOICE, "then": "close"}],
            "timeout": 100, "timeout_continuation": "close"}
DECLARED = {"interval": {"from": 10, "to": 10},
            "inputs": [{"type": "Choice", "choice_owner": OWNER, "chosen": 60}]}


def test_choice_name_binding_preserves_independent_value_and_source():
    original = deepcopy(DECLARED)
    transactions, evidence = bind_choice_transactions(CONTRACT, (DECLARED,))
    assert DECLARED == original
    assert transactions[0]["inputs"] == [{"type": "Choice",
                                           "choice_id": CHOICE["for_choice"], "chosen": 60}]
    assert evidence[0]["binding_kind"] == "unique_choice_owner_and_bound"
    assert DeclaredActionDomain("reviewed", (DECLARED,)).transactions({}, CONTRACT) == [
        transactions[0]]


def test_choice_binding_rejects_missing_or_ambiguous_match():
    with pytest.raises(ScenarioBindingError, match="uniquely"):
        bind_choice_transactions("close", (DECLARED,))
    ambiguous = deepcopy(CONTRACT)
    ambiguous["when"].append({"case": {"for_choice": {
        "choice_name": "second-name", "choice_owner": OWNER},
        "choose_between": [{"from": 0, "to": 100}]}, "then": "close"})
    with pytest.raises(ScenarioBindingError, match="uniquely"):
        bind_choice_transactions(ambiguous, (DECLARED,))
    wrong_owner = deepcopy(DECLARED)
    wrong_owner["inputs"][0]["choice_owner"] = {"role_token": "Other"}
    with pytest.raises(ScenarioBindingError, match="uniquely"):
        bind_choice_transactions(CONTRACT, (wrong_owner,))


def test_binding_accepts_immutable_artifact_payload_without_mutating_it():
    artifact = ArtifactEnvelope("scenario", "v1", "test",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY,
                                {"transactions": [DECLARED]})
    original = artifact.to_dict()["payload"]
    bound, _ = bind_choice_transactions(CONTRACT, tuple(artifact.payload["transactions"]))
    assert bound[0]["inputs"][0]["choice_id"] == CHOICE["for_choice"]
    assert artifact.to_dict()["payload"] == original
