from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import AMOUNT, DECISION_TIMEOUT, DEPOSIT_TIMEOUT

from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.marlowe_ast import (
    ada_to_lovelace,
    close,
    escrow_contract,
    is_close,
    normalize_marlowe_ast,
    pay,
    seconds_to_posix_ms,
    walk_contract,
)
from marlowe_agent.marlowe_validator import (
    MarloweValidationError,
    assert_valid,
    validate_contract,
)


def test_escrow_builder_matches_spec_golden() -> None:
    expected = json.loads((Path(__file__).parent / "fixtures" / "escrow_golden.json").read_text(encoding="utf-8"))
    actual = escrow_contract("Alice", "Bob", AMOUNT, DEPOSIT_TIMEOUT, DECISION_TIMEOUT)
    assert actual == expected
    assert_valid(actual)


def test_close_is_string_not_dict() -> None:
    assert close() == "close"
    assert is_close(close())
    assert validate_contract(close()) == []
    with pytest.raises(MarloweValidationError):
        assert_valid({"close": "close"})


def test_string_close_does_not_break_tree_walkers() -> None:
    assert walk_contract("close") == [("root", "close")]
    result = LogicGraphVerifier().verify("close")
    assert result.passed
    assert result.graph["nodes"] == [{"id": "root", "type": "Close"}]


def test_normalize_legacy_dialect() -> None:
    legacy = {
        "when": [{"case": {"choice": {"choice_name": "approve", "choice_owner": {"role_token": "Alice"}},
                           "bounds": [{"from": 1, "to": 1}]},
                  "then": {"pay": {"constant": 5}, "from_account": {"role_token": "Alice"},
                           "to": {"party": {"role_token": "Bob"}},
                           "token": {"currency_symbol": "", "token_name": ""},
                           "then": {"close": "close"}}}],
        "timeout": DEPOSIT_TIMEOUT, "timeout_continuation": {"close": "close"},
    }
    normalized, notes = normalize_marlowe_ast(legacy)
    assert validate_contract(normalized) == []
    assert normalized["when"][0]["case"]["for_choice"]["choice_name"] == "approve"
    assert normalized["when"][0]["then"]["pay"] == 5
    assert normalized["timeout_continuation"] == "close"
    assert len(notes) == 4


def test_normalize_does_not_touch_seconds_or_units() -> None:
    legacy = {"when": [{"case": {"party": {"role_token": "Alice"}, "deposits": {"constant": 250},
                                "of_token": {"currency_symbol": "", "token_name": ""},
                                "into_account": {"role_token": "Alice"}}, "then": {"close": "close"}}],
              "timeout": 1893456000, "timeout_continuation": {"close": "close"}}
    normalized, _ = normalize_marlowe_ast(legacy)
    assert normalized["timeout"] == 1893456000
    assert normalized["when"][0]["case"]["deposits"] == 250
    assert any("POSIX ms" in error for error in validate_contract(normalized))
    assert ada_to_lovelace(250) == 250_000_000
    assert seconds_to_posix_ms(1893456000) == DEPOSIT_TIMEOUT


def test_validator_rejects_unknown_keys() -> None:
    assert any("field" in error for error in validate_contract({"pay": 1, "unexpected": 2}))


def test_validator_rejects_bad_bounds() -> None:
    contract = {"when": [{"case": {"for_choice": {"choice_name": "x", "choice_owner": {"role_token": "Alice"}},
                                    "choose_between": [{"from": 2, "to": 1}]}, "then": "close"}],
                "timeout": DEPOSIT_TIMEOUT, "timeout_continuation": "close"}
    assert any("from phải <= to" in error for error in validate_contract(contract))


def test_validator_rejects_bool_timeout() -> None:
    assert any("POSIX ms" in error for error in validate_contract(
        {"when": [], "timeout": True, "timeout_continuation": "close"}))


def test_validator_rejects_seconds_timeout() -> None:
    assert any("đang dùng giây" in error for error in validate_contract(
        {"when": [], "timeout": 1893456000, "timeout_continuation": "close"}))


def test_typed_grammar_does_not_accept_integer_type_label_as_value() -> None:
    contract = pay("Alice", "Bob", 10)
    contract["pay"] = "integer"
    assert any("Value phải là số nguyên" in error for error in validate_contract(contract))
