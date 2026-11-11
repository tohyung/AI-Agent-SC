"""Dataset v3 is frozen: its file hash is pinned and rebuilding from the specs reproduces it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dataset.v3 import build

FROZEN_SHA256 = "cdc0ea456f2e103d86bb195522b6510755e65fdd5c9f9e1e2342cf68ad6e46cc"
CASES = Path(build.__file__).resolve().parent / "cases.jsonl"


def test_frozen_file_hash():
    assert hashlib.sha256(CASES.read_bytes()).hexdigest() == FROZEN_SHA256


def test_rebuild_from_specs_matches_the_frozen_file_and_passes_all_checks():
    cases, problems = build.assemble()
    _, gaps = build.coverage(cases)
    assert problems == [] and gaps == []
    rebuilt = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    assert rebuilt == CASES.read_text(encoding="utf-8")


def test_infeasible_cases_have_no_reference_and_feasible_ones_have_scenarios():
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines()]
    assert len(cases) == 100
    for case in cases:
        if case["family"] == "infeasible":
            assert case["reference_contract"] is None
        else:
            assert case["reference_contract"] and case["checks"]["scenarios"]
