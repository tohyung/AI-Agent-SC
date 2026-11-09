"""Opt-in real reference and node-backed ledger-size corridor, with no model API."""

import os

import pytest

from research.orchestration.bootstrap import build_research_pipeline
from research.orchestration.status import StepRunStatus
from research.experiments.online_tuning import (batch_wiring, configure_downstream,
                                                        configured_ledger)
from research.formalization.intent_spec import CORE_SCHEMA_VERSION_V2
from tests.synthesis.test_funded_choice_v1 import funded_choice_core


def test_simulated_funded_choice_reaches_real_ledger_size_analysis():
    binary = os.getenv("MARLOWE_REFERENCE_BINARY")
    ledger = configured_ledger()
    if binary is None or ledger is None:
        pytest.skip("explicit reference and ledger configuration required")
    core = funded_choice_core()

    class StaticModel:
        def generate(self, system, user):
            return core

    pipeline = build_research_pipeline(model=StaticModel(), wiring=batch_wiring())
    compiled = pipeline.run(core["requirement_history"], stop_after="compile", options={
        "core_schema_version": CORE_SCHEMA_VERSION_V2,
        "allow_simulated_intent": True,
    })
    assert compiled.steps["compile"].run_status == StepRunStatus.SUCCEEDED
    accepted = next(pipeline.store.get(item) for item in
                    compiled.steps["intent_acceptance"].output_artifacts
                    if item.startswith("accepted-intent:"))
    contract = next(pipeline.store.get(item) for item in
                    compiled.steps["compile"].output_artifacts
                    if item.startswith("contract-candidate:"))
    assert contract.payload["simulation_only"] is True
    assert contract.payload["mapping_evidence"]
    expectation = configure_downstream(pipeline, accepted, "funded-choice",
                                       reference_binary=binary, ledger_config=ledger)
    result = pipeline.run(core["requirement_history"], resume=compiled,
                          external_artifacts=[expectation],
                          invalidate_from="semantic_comparison",
                          stop_after="ledger_validation")
    assert result.steps["semantic_comparison"].semantic_status == "SATISFIED"
    assert result.steps["compiler_authority"].semantic_status == "CANDIDATE_ONLY"
    assert result.steps["exploration"].run_status == StepRunStatus.SUCCEEDED
    assert result.steps["oracle_evaluation"].run_status == StepRunStatus.SUCCEEDED
    assert result.steps["property_validation"].semantic_status == "NO_CANDIDATES"
    assert result.steps["ledger_validation"].semantic_status == "REACHED_LEDGER_PASS"
    ledger_evidence = pipeline.store.get(result.steps["ledger_validation"].output_artifacts[0])
    assert ledger_evidence.payload["simulation_only"] is True
    assert ledger_evidence.payload["maxTxSize"] > ledger_evidence.payload["actual_tx_bytes"]
    assert "testnet" not in result.steps and "deployment" not in result.steps
