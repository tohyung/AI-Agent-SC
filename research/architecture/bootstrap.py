"""Composition root. Concrete adapters are imported only when configured."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .orchestrator import ResearchOrchestrator


@dataclass
class ResearchPipelineWiring:
    reviewer_policy: Any = None
    profile_registry: Any = None
    compiler_plugins: dict[tuple[str, str], Any] = field(default_factory=dict)
    reference_executor: Any = None
    expectation_policy: Any = None
    promotion_policy: Any = None
    exploration_domain: Any = None
    exploration_initial_state: dict[str, Any] | None = None
    exploration_bounds: Any = None
    oracles: list[Any] = field(default_factory=list)
    property_checker: Any = None
    property_registry: Any = None
    ledger_port: Any = None
    testnet_port: Any = None
    deployment_port: Any = None


def build_research_pipeline(*, live_model: bool = False, model_name: str | None = None,
                            model: Any | None = None,
                            wiring: ResearchPipelineWiring | None = None) -> ResearchOrchestrator:
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
    configured = wiring or ResearchPipelineWiring()
    from research.stage4.explorer import ExplorationBounds
    return ResearchOrchestrator({
        "intent_extraction": Stage2BExtractionPort(model),
        "intent_acceptance": IntentAcceptancePort(configured.reviewer_policy),
        "compile": CompilerPort(configured.profile_registry, configured.compiler_plugins),
        "semantic_comparison": SemanticComparisonPort(configured.reference_executor,
                                                       configured.expectation_policy),
        "compiler_authority": CompilerAuthorityPort(configured.promotion_policy),
        "exploration": ExplorationPort(configured.exploration_domain, configured.reference_executor,
                                       configured.exploration_initial_state,
                                       configured.exploration_bounds or ExplorationBounds()),
        "oracle_evaluation": OraclePort(configured.oracles),
        "coverage": CoveragePort(),
        "adversarial_search": AdversarialPort(),
        "property_validation": PropertyValidationPort(configured.property_checker,
                                                      configured.property_registry),
        "ledger_validation": configured.ledger_port or DisabledExternalPort("ledger_validation"),
        "testnet": configured.testnet_port or DisabledExternalPort("testnet"),
        "deployment": configured.deployment_port or DisabledExternalPort("deployment"),
    })
