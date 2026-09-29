from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from marlowe_agent.node3_policy import StructuredWarning
from marlowe_agent.node3_renderer import render_warning


REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tools" / "marlowe_smt" / "tests"


def _posix_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        return resolved.as_posix()
    tail = resolved.as_posix().split(":/", 1)[1]
    return f"/mnt/{drive}/{tail}"


def _real_warning(filename: str) -> StructuredWarning:
    repo = _posix_path(REPO)
    fixture = _posix_path(FIXTURES / filename)
    command = (
        f"cd {repo} && python3 tools/marlowe_smt/run_smt.py "
        f"--hard-timeout 90 --solver-timeout-ms 60000 < {fixture}"
    )
    process = subprocess.run(
        ["bash", "-lc", command], capture_output=True, text=True,
        stdin=subprocess.DEVNULL, check=True, timeout=100,
    )
    output = json.loads(process.stdout)
    assert output["status"] == "Counterexample"
    assert len(output["warnings"]) == 1
    raw = output["warnings"][0]
    return StructuredWarning(raw["type"], {key: value for key, value in raw.items() if key != "type"})


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
