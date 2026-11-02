"""Builder theorems T4 and T5 against the pinned Haskell semantics and SMT analyzer.

For each seeded draft, ⟦D⟧ runs on the official Marlowe reference along every
path and must pay exactly what the builder's outcome claims say (then refund
the rest on Close), with no warnings; the SMT analyzer must find no warning on
any input. Needs the built binaries: the Reference CI job runs these. On
Windows set MARLOWE_REFERENCE_VIA_WSL=1 to run them through WSL.
"""

import os
import shutil

import pytest

from research.integrations import reference_driver, smt_driver
from research.stage2b.fact_builder import build_core
from research.stage2b.fact_semantics import denote, paths
from tests.stage2b.fact_draft_gen import core_path, random_draft

SEEDS = range(15)
EMPTY_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}


@pytest.fixture(scope="module", autouse=True)
def toolchain():
    if os.environ.get("MARLOWE_REFERENCE_VIA_WSL") != "1" and (
            shutil.which("cabal") is None or shutil.which("ghc") is None):
        pytest.skip("cabal/GHC unavailable; real Haskell reference not exercised")


def _payments(result):
    return [(payment["source_account"]["role_token"],
             payment["payee"]["party"]["role_token"], payment["amount"])
            for step in result["steps"] for payment in step["payments"]]


@pytest.mark.parametrize("seed", SEEDS)
def test_t4_reference_semantics_pays_what_the_core_claims(seed):
    draft, history = random_draft(seed)
    core = build_core(draft, history)
    contract = denote(draft)
    for run in paths(contract):
        result = reference_driver.execute({"contract": contract, "state": EMPTY_STATE,
                                           "transactions": run.transactions})
        assert result["status"] == "Success", (run.moves, result.get("detail"))
        assert result["final_contract"] == "close"
        assert [step["warnings"] for step in result["steps"] if step["warnings"]] == []
        outcomes, _ = core_path(core, run.moves)
        paid = _payments(result)
        assert paid[:len(outcomes)] == outcomes, run.moves
        assert paid == run.payments, run.moves


@pytest.mark.parametrize("seed", SEEDS)
def test_t5_smt_finds_no_warning_on_any_input(seed):
    draft, _history = random_draft(seed)
    result = smt_driver.analyze(denote(draft))
    assert result["status"] == "Valid", (result.get("warnings"), result.get("counterexample"))
