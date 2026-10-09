"""Composition root. Concrete adapters are imported only when configured."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .orchestrator import ResearchOrchestrator, STAGE_ORDER


@dataclass
class ResearchPipelineWiring:
    reviewer_policy: Any = None
    intent_acceptance_port: Any = None
    profile_registry: Any = None
    compiler_plugins: dict[tuple[str, str], Any] = field(default_factory=dict)
    contract_model: Any = None
    smt_analyzer: Any = None
    smt_binary: str | None = None
    enable_smt: bool = False
    reference_executor: Any = None
    expectation_policy: Any = None
    promotion_policy: Any = None
    exploration_domain: Any = None
    exploration_initial_state: dict[str, Any] | None = None
    exploration_bounds: Any = None
    oracles: list[Any] = field(default_factory=list)
    property_checker: Any = None
    property_registry: Any = None
    property_dataset: Any = None
    ledger_port: Any = None
    testnet_port: Any = None
    deployment_port: Any = None


def build_research_pipeline(*, live_model: bool = False, model_name: str | None = None,
                            model: Any | None = None,
                            wiring: ResearchPipelineWiring | None = None) -> ResearchOrchestrator:
    from research.integrations.stage2b import Stage2BExtractionPort
    from research.stage2c.acceptance import IntentAcceptancePort
    from research.stage3.compiler import CompilerPort
    from research.stage3.llm_generator import LLMContractGeneratorPort
    from research.stage3.comparison import SemanticComparisonPort
    from research.stage3.authority import CompilerAuthorityPort
    from research.stage3.candidate_gate import CandidateGatePort
    from research.stage4.explorer import ExplorationPort
    from research.stage4.oracles import OraclePort
    from research.stage4.coverage import CoveragePort
    from research.stage4.adversarial import AdversarialPort
    from research.stage5.registry import PropertyValidationPort
    from research.final_validation.adapters import DisabledExternalPort
    from research.integrations.smt_gate import SMTVerificationPort

    if live_model and model is None:
        from research.integrations.model_transport import ModelTransport
        model = ModelTransport(model=model_name)
    configured = wiring or ResearchPipelineWiring()
    from research.stage4.explorer import ExplorationBounds
    ports = {
        "intent_extraction": Stage2BExtractionPort(model),
        "intent_acceptance": (configured.intent_acceptance_port
                              or IntentAcceptancePort(configured.reviewer_policy)),
        "compile": (LLMContractGeneratorPort(configured.contract_model)
                    if configured.contract_model is not None else
                    CompilerPort(configured.profile_registry, configured.compiler_plugins)),
        "semantic_comparison": SemanticComparisonPort(
            configured.reference_executor, configured.expectation_policy,
            require_intent_alignment=configured.contract_model is not None),
        "compiler_authority": (CandidateGatePort() if configured.contract_model is not None
                               else CompilerAuthorityPort(configured.promotion_policy)),
        "exploration": ExplorationPort(configured.exploration_domain, configured.reference_executor,
                                       configured.exploration_initial_state,
                                       configured.exploration_bounds or ExplorationBounds()),
        "oracle_evaluation": OraclePort(configured.oracles, configured.property_dataset),
        "coverage": CoveragePort(),
        "adversarial_search": AdversarialPort(),
        "property_validation": PropertyValidationPort(configured.property_checker,
                                                      configured.property_registry,
                                                      configured.property_dataset),
        "ledger_validation": configured.ledger_port or DisabledExternalPort("ledger_validation"),
        "testnet": configured.testnet_port or DisabledExternalPort("testnet"),
        "deployment": configured.deployment_port or DisabledExternalPort("deployment"),
    }
    if configured.enable_smt:
        ports["smt_verification"] = SMTVerificationPort(
            configured.smt_analyzer, configured.smt_binary)
        position = STAGE_ORDER.index("semantic_comparison")
        order = STAGE_ORDER[:position] + ("smt_verification",) + STAGE_ORDER[position:]
    else:
        order = STAGE_ORDER
    return ResearchOrchestrator(ports, stage_order=order)
