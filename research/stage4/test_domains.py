"""Focused regressions for explicit empty-input transaction labels."""

import pytest

from research.stage4.domains import TransactionTemplate


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
