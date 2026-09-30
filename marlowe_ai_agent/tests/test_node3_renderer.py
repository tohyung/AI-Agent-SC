from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from marlowe_agent.node3_policy import StructuredWarning
from marlowe_agent.node3_renderer import render_warning, render_warning_safe


REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tools" / "marlowe_smt" / "tests"


def _require_real_smt() -> None:
    configured = os.environ.get("MARLOWE_SMT_BIN")
    if configured:
        binary = Path(configured)
        available = binary.is_file() and os.access(binary, os.X_OK)
    else:
        available = shutil.which("cabal") is not None
    if not available:
        pytest.skip("real Marlowe SMT toolchain is not available")


def _real_warning(filename: str) -> StructuredWarning:
    _require_real_smt()
    process = subprocess.run(
        [sys.executable, str(REPO / "tools" / "marlowe_smt" / "run_smt.py"),
         "--hard-timeout", "90", "--solver-timeout-ms", "60000"],
        input=(FIXTURES / filename).read_text(encoding="utf-8"),
        capture_output=True, text=True, check=True, timeout=100, cwd=REPO,
    )
    output = json.loads(process.stdout)
    assert output["status"] == "Counterexample"
    assert len(output["warnings"]) == 1
    raw = output["warnings"][0]
    return StructuredWarning(raw["type"], {key: value for key, value in raw.items() if key != "type"})


@pytest.mark.parametrize(("warning", "expected_text"), [
    (StructuredWarning("TransactionNonPositiveDeposit", {
        "party": {"role_token": "Alice"}, "account": {"role_token": "Alice"}, "amount": 0,
    }), "Bên Alice cố nạp 0 vào tài khoản Alice; Deposit phải lớn hơn 0."),
    (StructuredWarning("TransactionNonPositivePay", {
        "account": {"role_token": "Alice"}, "payee": {"party": {"role_token": "Bob"}}, "amount": 0,
    }), "Tài khoản Alice cố trả 0 cho bên Bob; Pay phải lớn hơn 0."),
    (StructuredWarning("TransactionPartialPay", {
        "account": {"role_token": "Alice"}, "payee": {"party": {"role_token": "Bob"}},
        "expected": 20, "paid": 10,
    }), "Tài khoản Alice cố trả 20 cho bên Bob nhưng chỉ trả được 10."),
    (StructuredWarning("TransactionShadowing", {
        "value_id": "x", "old_value": 1, "new_value": 2,
    }), "Biến x bị Let ghi đè: giá trị cũ 1, giá trị mới 2."),
    (StructuredWarning("TransactionAssertionFailed"),
     "Assert có thể sai trên một đường đi khả thi."),
])
def test_renderer_pure_warning_text(warning: StructuredWarning, expected_text: str) -> None:
    assert render_warning(warning) == expected_text


@pytest.mark.parametrize("warning", [
    StructuredWarning("FutureTransactionWarning"),
    StructuredWarning("TransactionPartialPay", {"expected": 20}),
    StructuredWarning("TransactionPartialPay", None),
])
def test_renderer_safe_fallback_for_unknown_or_malformed_warning(warning: StructuredWarning) -> None:
    assert render_warning_safe(warning) == f"SMT phát hiện {warning.type}."


@pytest.mark.parametrize(
    ("fixture", "expected_type", "expected_text"),
    [
        (
            "nonpositive_deposit.json", "TransactionNonPositiveDeposit",
            "Bên Alice cố nạp 0 vào tài khoản Alice; Deposit phải lớn hơn 0.",
        ),
        (
            "nonpositive_pay.json", "TransactionNonPositivePay",
            "Tài khoản Alice cố trả 0 cho bên Bob; Pay phải lớn hơn 0.",
        ),
        (
            "partial_pay.json", "TransactionPartialPay",
            "Tài khoản Alice cố trả 20 cho bên Bob nhưng chỉ trả được 10.",
        ),
        (
            "shadowing.json", "TransactionShadowing",
            "Biến x bị Let ghi đè: giá trị cũ 1, giá trị mới 2.",
        ),
        (
            "assertion_failed.json", "TransactionAssertionFailed",
            "Assert có thể sai trên một đường đi khả thi.",
        ),
    ],
)
def test_renderer_uses_real_driver_warning_fields(
    fixture: str, expected_type: str, expected_text: str,
) -> None:
    warning = _real_warning(fixture)
    assert warning.type == expected_type
    assert render_warning(warning) == expected_text


def test_partial_pay_keeps_expected_and_paid_in_their_positions() -> None:
    warning = _real_warning("partial_pay.json")
    text = render_warning(warning)
    assert warning.fields["expected"] == 20
    assert warning.fields["paid"] == 10
    assert text.index("trả 20") < text.index("trả được 10")


def test_shadowing_keeps_old_and_new_values_in_their_positions() -> None:
    warning = _real_warning("shadowing.json")
    text = render_warning(warning)
    assert warning.fields["old_value"] == 1
    assert warning.fields["new_value"] == 2
    assert text.index("cũ 1") < text.index("mới 2")
