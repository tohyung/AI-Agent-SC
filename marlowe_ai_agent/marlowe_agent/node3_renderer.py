"""Deterministic Vietnamese rendering for structured Marlowe warnings."""

from __future__ import annotations

import json
from typing import Any

from .node3_policy import StructuredWarning


def _party(value: Any) -> str:
    if isinstance(value, dict):
        if "role_token" in value:
            return str(value["role_token"])
        if "address" in value:
            return str(value["address"])
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payee(value: Any) -> str:
    if isinstance(value, dict) and "party" in value:
        return f"bên {_party(value['party'])}"
    if isinstance(value, dict) and "account" in value:
        return f"tài khoản {_party(value['account'])}"
    return _party(value)


def render_warning(warning: StructuredWarning) -> str:
    fields = warning.fields
    if warning.type == "TransactionNonPositiveDeposit":
        return (
            f"Bên {_party(fields['party'])} cố nạp {fields['amount']} vào tài khoản "
            f"{_party(fields['account'])}; Deposit phải lớn hơn 0."
        )
    if warning.type == "TransactionNonPositivePay":
        return (
            f"Tài khoản {_party(fields['account'])} cố trả {fields['amount']} cho "
            f"{_payee(fields['payee'])}; Pay phải lớn hơn 0."
        )
    if warning.type == "TransactionPartialPay":
        return (
            f"Tài khoản {_party(fields['account'])} cố trả {fields['expected']} cho "
            f"{_payee(fields['payee'])} nhưng chỉ trả được {fields['paid']}."
        )
    if warning.type == "TransactionShadowing":
        return (
            f"Biến {fields['value_id']} bị Let ghi đè: giá trị cũ {fields['old_value']}, "
            f"giá trị mới {fields['new_value']}."
        )
    if warning.type == "TransactionAssertionFailed":
        return "Assert có thể sai trên một đường đi khả thi."
    raise ValueError(f"unsupported TransactionWarning: {warning.type}")
