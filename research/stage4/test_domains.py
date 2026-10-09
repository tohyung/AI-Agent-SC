"""Focused regressions for explicit empty-input transaction labels."""

import pytest

from research.stage4.domains import TransactionTemplate
from research.stage4.declared_domain import DeclaredActionDomain


def test_no_input_transaction_shape() -> None:
    assert TransactionTemplate("NoInput", 0, 0, ()).to_transaction() == {
        "interval": {"from": 0, "to": 0},
        "inputs": [],
    }


def test_no_input_rejects_nonempty_inputs() -> None:
    with pytest.raises(ValueError, match="input kind"):
        TransactionTemplate("NoInput", 0, 0, ({"type": "Notify"},))


def test_timeout_keeps_empty_input_behavior() -> None:
    assert TransactionTemplate("Timeout", 0, 0, ()).to_transaction() == {
        "interval": {"from": 0, "to": 0},
        "inputs": [],
    }


def test_declared_timeout_action_accepts_post_deadline_but_not_straddling_interval() -> None:
    contract = {"when": [], "timeout": 100, "timeout_continuation": "close"}
    before = {"interval": {"from": 99, "to": 99}, "inputs": []}
    straddling = {"interval": {"from": 99, "to": 100}, "inputs": []}
    at_deadline = {"interval": {"from": 100, "to": 100}, "inputs": []}
    after = {"interval": {"from": 101, "to": 102}, "inputs": []}
    domain = DeclaredActionDomain("reviewed", (before, straddling, at_deadline, after))
    assert domain.transactions({}, contract) == [at_deadline, after]
