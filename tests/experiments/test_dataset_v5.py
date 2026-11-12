import hashlib
from pathlib import Path

from dataset.v5.build import assemble, check_case, coverage, style_report

ROOT = Path(__file__).resolve().parents[2]
FROZEN = "85f70d4330a547663706381a8079e0b3176769d669946235650340cdd8d09cae"


def test_v5_builds_without_problems_and_meets_every_minimum():
    cases, problems = assemble()
    assert problems == [] and len(cases) == 100
    _, gaps = coverage(cases)
    _, style_gaps = style_report(cases)
    assert gaps == [] and style_gaps == []


def test_the_frozen_file_is_unchanged():
    data = (ROOT / "dataset" / "v5" / "cases.jsonl").read_bytes()
    assert hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest() == FROZEN


def test_the_accuracy_checks_catch_planted_errors():
    case = {"id": "t", "info_mode": "complete", "expected_behavior": "converge", "register": "chat",
            "phenomena": [], "family": "loan",
            "prompt": "Lan cho Tú vay 100 ADA trước 20:00 ngày 01/03/2027 giờ VN, Tú trả 110 ADA trước "
                      "20:00 ngày 01/06/2027.",
            "spec": {"roles": {"lender": "Lan", "borrower": "Tú"}, "principal": 100, "repay": 115,
                     "fund_by": "2027-03-01T21:00+07:00", "repay_by": "2027-06-02T20:00+07:00"},
            "fact_sheet": []}
    found = " ".join(check_case(case, set(), []))
    assert "amount 115" in found and "time 21:00" in found and "date 2027-06-02" in found
