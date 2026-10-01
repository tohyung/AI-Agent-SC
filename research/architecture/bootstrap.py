"""Composition root. Concrete adapters are imported only when configured."""

from __future__ import annotations

from typing import Any

from .orchestrator import ResearchOrchestrator


def build_research_pipeline(*, live_model: bool = False, model_name: str | None = None,
                            model: Any | None = None) -> ResearchOrchestrator:
    from research.integrations.stage2b import Stage2BExtractionPort
    from research.stage2c.acceptance import IntentAcceptancePort
    from research.stage3.compiler import CompilerPort
    from research.stage3.comparison import SemanticComparisonPort
    from research.stage3.authority import CompilerAuthorityPort
    from research.stage4.explorer import ExplorationPort
    from research.stage4.oracles import OraclePort
    from research.stage4.coverage import CoveragePort
    from research.stage4.adversarial import AdversarialPort
    from research.stage5.registry import PropertyValidationPort
    from research.final_validation.adapters import DisabledExternalPort

    if live_model and model is None:
        from research.stage2b.shadow_extractor import LegacyReasonerTransport
        model = LegacyReasonerTransport(model=model_name)
    return ResearchOrchestrator({
        "intent_extraction": Stage2BExtractionPort(model),
        "intent_acceptance": IntentAcceptancePort(),
        "compile": CompilerPort(),
        "semantic_comparison": SemanticComparisonPort(),
        "compiler_authority": CompilerAuthorityPort(),
        "exploration": ExplorationPort(),
        "oracle_evaluation": OraclePort(),
        "coverage": CoveragePort(),
        "adversarial_search": AdversarialPort(),
        "property_validation": PropertyValidationPort(),
        "ledger_validation": DisabledExternalPort("ledger_validation"),
        "testnet": DisabledExternalPort("testnet"),
        "deployment": DisabledExternalPort("deployment"),
    })
