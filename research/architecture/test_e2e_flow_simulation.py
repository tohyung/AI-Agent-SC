"""Offline interface integration, not semantic or external-system validation."""

from copy import deepcopy

import pytest

from research.architecture.artifacts import ArtifactEnvelope, canonical_json_v1
from research.architecture.bootstrap import ResearchPipelineWiring, build_research_pipeline
from research.architecture.orchestrator import STAGE_ORDER
from research.architecture.ports import StageExecution
from research.architecture.models import StageResult
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION
from research.stage3.comparison import BehaviorExpectation
from research.stage3.models import (CompileResult, CompileStatus, CompilerAuthorityDecision,
                                    CompilerAuthorityStatus, SupportedProfile)
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import ReferenceRequest
from research.stage4.domains import ExplicitTransactionDomain, TransactionTemplate
from research.stage4.explorer import ExplorationBounds
from research.stage4.oracles import NoWarningsOracle
from research.stage5.registry import (PropertyCandidate, PropertyCheckResult,
                                      PropertyRegistry, PropertyStatus)


MESSAGE = "Alice deposits 10 ADA to Alice account; Bob receives 10 ADA."
HISTORY = [{"version": 1, "messages": [MESSAGE]}]
REFERENCE_ID = "simulation-reference:integration-v1"


def _core():
    def claim(claim_id, kind, value, scope, span, status="explicit"):
        item = {"claim_id": claim_id, "kind": kind, "value": value,
                "criticality": "financial", "status": status, "scope_id": scope,
                "evidence": [{"requirement_version": 1, "message_index": 0,
                              "span": span, "relation": "supports"}]}
        if status == "derived":
            item["normalization_basis"] = "1 ADA = 1000000 lovelace"
        return item

    return {"schema_version": CORE_SCHEMA_VERSION, "requirement_history": deepcopy(HISTORY),
            "behavior_scopes": [
                {"scope_id": "global", "scope_type": "global"},
                {"scope_id": "deposit-1", "scope_type": "transition", "transition_kind": "deposit"},
                {"scope_id": "payout-1", "scope_type": "transition", "transition_kind": "payment"}],
            "claims": [
                claim("depositor", "depositing_party", "Alice", "deposit-1", "Alice deposits"),
                claim("account", "destination_account_owner", "Alice", "deposit-1", "Alice account"),
                claim("asset", "asset", "ADA", "global", "10 ADA"),
                claim("amount", "amount_lovelace", 10000000, "deposit-1", "10 ADA", "derived"),
                claim("recipient", "payment_recipient", "Bob", "payout-1", "Bob receives 10 ADA")],
            "required_clarifications": [], "unscored_observations": [],
            "predicted_resolution": "accepted_interpretation"}


class StaticShadowModel:
    def __init__(self):
        self.calls = 0

    def generate(self, system, user):
        self.calls += 1
        return _core()


class TestReviewerPolicy:
    def authorize(self, candidate, decision):
        return decision.reviewer_id == "simulation-reviewer"


class TestCompilerPlugin:
    __test__ = False
    def __init__(self):
        self.received = []

    def __call__(self, ir):
        self.received.append(ir)
        mapping = []
        for kind, items, key in (
            ("claim", (item for item in ir.claims if item.status != "superseded"), "claim_id"),
            ("scope", ir.scopes, "scope_id"),
            ("participants", ir.participants, "participant_id"),
            ("parameters", ir.parameters, "parameter_id"),
            ("states", ir.states, "state_id"),
            ("transitions", ir.transitions, "transition_id"),
            ("obligations_and_outcomes", ir.outcomes, "outcome_id"),
            ("assets", ir.assets, "asset_id"),
            ("accounts", ir.accounts, "account_id"),
            ("funding_relations", ir.funding_relations, "relation_id"),
        ):
            mapping.extend({"source_kind": kind, "source_id": getattr(item, key),
                            "ast_path": "$"} for item in items)
        return CompileResult(CompileStatus.SUPPORTED, "close", tuple(mapping))


class FakeReferenceExecutor:
    def __init__(self, warning=False):
        self.warning = warning
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return {"status": "Success", "steps": [{"warnings": ["synthetic warning"]
                if self.warning else []}], "final_state": request.state,
                "final_contract": "close",
                "meta": {"upstream_commit": "simulation-reference",
                         "reference_driver_version": "integration-v1"}}


class TestExpectationPolicy:
    def authorize(self, artifact):
        return (artifact.producer_stage == "simulation_review"
                and artifact.payload.get("reviewer_id") == "simulation-reviewer")


class TestPromotionPolicy:
    def authorize(self, decision, contract, comparison):
        return decision.reviewer_id == "simulation-reviewer"


class TestPropertyChecker:
    __test__ = False
    def __init__(self):
        self.checked = []

    def check(self, candidate):
        self.checked.append(candidate)
        return PropertyCheckResult(PropertyStatus.REFUTED,
                                   ("simulation-property-evidence",), "simulation-reviewer")


class SimulationFinalPort:
    def __init__(self, stage, input_type):
        self.stage = stage
        self.input_type = input_type

    def execute(self, artifacts, context):
        source = next(item for item in reversed(artifacts)
                      if item.artifact_type == self.input_type)
        output = ArtifactEnvelope(self.stage.replace("_validation", "") + "-simulation",
                                  "v1", self.stage, ImplementationStatus.SCAFFOLDED,
                                  AuthorityLevel.NO_AUTHORITY,
                                  {"simulation_only": True, "source_id": source.artifact_id})
        return StageExecution(StageResult(self.stage, ImplementationStatus.SCAFFOLDED,
                                          StageRunStatus.SUCCEEDED,
                                          input_artifacts=[source.artifact_id],
                                          limitations=["simulation interface only"]), [output])


def _pipeline(warning=False):
    model = StaticShadowModel()
    plugin = TestCompilerPlugin()
    reference = FakeReferenceExecutor(warning)
    checker = TestPropertyChecker()
    registry = PropertyRegistry()
    profile = SupportedProfile(
        "integration-simulation-payment-v1", "v1", "simulation-compiler", "v1",
        "stage2b-shadow-v1",
        frozenset({"depositing_party", "destination_account_owner", "asset",
                   "amount_lovelace", "payment_recipient"}),
        frozenset({"global", "transition"}), frozenset({"deposit", "payment"}),
        frozenset({"ADA"}))
    wiring = ResearchPipelineWiring(
        reviewer_policy=TestReviewerPolicy(), profile_registry=ProfileRegistry([profile]),
        compiler_plugins={(profile.profile_id, profile.version): plugin},
        reference_executor=reference, expectation_policy=TestExpectationPolicy(),
        promotion_policy=TestPromotionPolicy(),
        exploration_domain=ExplicitTransactionDomain("simulation-domain", [
            TransactionTemplate("Timeout", 0, 0, ())]),
        exploration_initial_state={}, exploration_bounds=ExplorationBounds(1, 1),
        oracles=[NoWarningsOracle()], property_checker=checker, property_registry=registry,
        ledger_port=SimulationFinalPort("ledger_validation", "property-candidates"),
        testnet_port=SimulationFinalPort("testnet", "ledger-simulation"),
        deployment_port=SimulationFinalPort("deployment", "testnet-simulation"))
    return build_research_pipeline(model=model, wiring=wiring), model, plugin, reference, checker, registry, profile


def _advance_to_compile(pipeline):
    first = pipeline.run(HISTORY, stop_after="intent_acceptance")
    assert first.stages["intent_extraction"].run_status == StageRunStatus.SUCCEEDED
    assert first.stages["intent_acceptance"].run_status == StageRunStatus.WAITING_USER
    candidate_id = first.stages["intent_extraction"].output_artifacts[0]
    spec = pipeline.store.get(candidate_id).to_dict()["payload"]["intent_spec"]
    decision = {"status": "ACCEPTED", "reviewer_id": "simulation-reviewer",
                "explicit_consent": True, "approved_spec": spec}
    second = pipeline.run(HISTORY, resume=first, stop_after="compile",
                          options={"intent_decision": decision})
    assert second.stages["intent_acceptance"].run_status == StageRunStatus.SUCCEEDED
    assert second.stages["compile"].run_status == StageRunStatus.SUCCEEDED
    assert (first.run_id, first.requirement_artifact_id) == (
        second.run_id, second.requirement_artifact_id)
    return first, second


def _expectation(pipeline, run):
    accepted_id = next(item for item in run.stages["intent_acceptance"].output_artifacts
                       if item.startswith("accepted-intent:"))
    payload = BehaviorExpectation(accepted_id, "accepted_intent",
                                  ReferenceRequest(None, {}, ()), "Success",
                                  expected_final_contract="close",
                                  reviewer_id="simulation-reviewer").to_dict()
    return ArtifactEnvelope("behavior-expectation", "v1", "simulation_review",
                            ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY, payload)


def _authority_decision(profile):
    return CompilerAuthorityDecision(
        CompilerAuthorityStatus.AUTHORIZED_FOR_PROFILE, profile.profile_id,
        profile.version, profile.compiler_id, profile.compiler_version,
        profile.intent_schema_version, "marlowe-core-v1", REFERENCE_ID,
        "simulation-policy-v1", ("simulation-evidence",), "simulation-reviewer")


def _assert_edge(run, source, target):
    assert any(edge["parent_artifact_id"] == source and edge["child_artifact_id"] == target
               for edge in run.provenance_records.values())


def test_clean_flow_traverses_all_real_internal_ports_and_simulated_external_ports():
    pipeline, model, plugin, reference, checker, registry, profile = _pipeline()
    first, second = _advance_to_compile(pipeline)
    expectation = _expectation(pipeline, second)
    final = pipeline.run(HISTORY, resume=second, external_artifacts=[expectation],
                         options={"compiler_authority_decision": _authority_decision(profile),
                                  "reference_identity": REFERENCE_ID,
                                  "evidence_policy_version": "simulation-policy-v1"})
    assert list(final.stages) == list(STAGE_ORDER)
    assert all(stage.run_status == StageRunStatus.SUCCEEDED for stage in final.stages.values())
    assert final.stage_executions == len(STAGE_ORDER) + 1
    assert (first.run_id, second.run_id, final.run_id) == (first.run_id,) * 3
    assert model.calls == 1 and reference.calls >= 2
    assert plugin.received and plugin.received[0].participants
    assert plugin.received[0].parameters and plugin.received[0].states
    assert plugin.received[0].transitions and plugin.received[0].outcomes
    assert canonical_json_v1(plugin.received[0].to_dict())
    mapping = pipeline.store.get(next(
        item for item in final.stages["compile"].output_artifacts
        if item.startswith("contract-candidate:"))).payload["mapping_evidence"]
    mapped = {(item["source_kind"], item["source_id"]) for item in mapping if item["ast_path"]}
    ir = plugin.received[0]
    expected = {(kind, getattr(item, key)) for kind, items, key in (
        ("claim", ir.claims, "claim_id"), ("scope", ir.scopes, "scope_id"),
        ("participants", ir.participants, "participant_id"),
        ("parameters", ir.parameters, "parameter_id"),
        ("states", ir.states, "state_id"),
        ("transitions", ir.transitions, "transition_id"),
        ("obligations_and_outcomes", ir.outcomes, "outcome_id"),
        ("assets", ir.assets, "asset_id"), ("accounts", ir.accounts, "account_id"),
        ("funding_relations", ir.funding_relations, "relation_id")) for item in items}
    assert expected <= mapped
    assert final.stages["compiler_authority"].semantic_status == "AUTHORIZED_FOR_PROFILE"
    assert final.stages["exploration"].run_status == StageRunStatus.SUCCEEDED
    graph = pipeline.store.get(final.stages["exploration"].output_artifacts[0])
    assert graph.payload["traces"] and graph.payload["coverage"] == "BOUNDED"
    findings = pipeline.store.get(final.stages["oracle_evaluation"].output_artifacts[0])
    assert all(item["verdict"] == "SATISFIED" for item in findings.payload["findings"])
    assert final.stages["property_validation"].semantic_status == "NO_CANDIDATES"
    assert not checker.checked and not registry._history
    assert final.external_artifact_ids == [expectation.artifact_id]
    source = final.requirement_artifact_id
    candidate = final.stages["intent_extraction"].output_artifacts[0]
    accepted = next(item for item in final.stages["intent_acceptance"].output_artifacts
                    if item.startswith("accepted-intent:"))
    contract = next(item for item in final.stages["compile"].output_artifacts
                    if item.startswith("contract-candidate:"))
    comparison = final.stages["semantic_comparison"].output_artifacts[0]
    authority = final.stages["compiler_authority"].output_artifacts[0]
    graph_id = graph.artifact_id
    findings_id = findings.artifact_id
    coverage = final.stages["coverage"].output_artifacts[0]
    adversarial = final.stages["adversarial_search"].output_artifacts[0]
    property_id = final.stages["property_validation"].output_artifacts[0]
    _assert_edge(final, source, candidate)
    for output in final.stages["intent_acceptance"].output_artifacts:
        _assert_edge(final, candidate, output)
    for output in final.stages["compile"].output_artifacts:
        _assert_edge(final, accepted, output)
    for input_id in (contract, accepted, expectation.artifact_id):
        _assert_edge(final, input_id, comparison)
    for input_id in (contract, comparison):
        _assert_edge(final, input_id, authority)
    _assert_edge(final, contract, graph_id)
    _assert_edge(final, graph_id, findings_id)
    for input_id in (graph_id, findings_id):
        _assert_edge(final, input_id, coverage)
    _assert_edge(final, findings_id, adversarial)
    for input_id in (adversarial, contract):
        _assert_edge(final, input_id, property_id)
    assert not any(edge["parent_artifact_id"] == source
                   and edge["child_artifact_id"] == expectation.artifact_id
                   for edge in final.provenance_records.values())
    for stage in ("ledger_validation", "testnet", "deployment"):
        artifact = pipeline.store.get(final.stages[stage].output_artifacts[0])
        assert artifact.payload["simulation_only"] is True
        assert artifact.authority_level == AuthorityLevel.NO_AUTHORITY
        _assert_edge(final, artifact.payload["source_id"], artifact.artifact_id)
    again = pipeline.run(HISTORY, resume=final, external_artifacts=[expectation])
    assert again.stage_executions == final.stage_executions
    assert again.external_artifact_ids == [expectation.artifact_id]


def test_warning_flow_checks_property_and_stops_before_external_stages():
    pipeline, model, plugin, reference, checker, registry, profile = _pipeline(warning=True)
    _, second = _advance_to_compile(pipeline)
    expectation = _expectation(pipeline, second)
    result = pipeline.run(HISTORY, resume=second, stop_after="property_validation",
                          external_artifacts=[expectation],
                          options={"compiler_authority_decision": _authority_decision(profile),
                                   "reference_identity": REFERENCE_ID,
                                   "evidence_policy_version": "simulation-policy-v1"})
    findings = pipeline.store.get(result.stages["oracle_evaluation"].output_artifacts[0])
    assert any(item["verdict"] == "VIOLATED" for item in findings.payload["findings"])
    assert result.stages["adversarial_search"].run_status == StageRunStatus.SUCCEEDED
    assert result.stages["property_validation"].run_status == StageRunStatus.SUCCEEDED
    assert result.stages["property_validation"].semantic_status == "REFUTED"
    assert checker.checked
    history = registry.history(checker.checked[0].property_id)
    assert [item["status"] for item in history] == ["CANDIDATE", "REFUTED"]
    assert [item["candidate"]["version"] for item in history] == [1, 1]
    assert "ledger_validation" not in result.stages


def test_external_artifact_collision_and_resume_store_boundary():
    pipeline, _, _, _, _, _, _ = _pipeline()
    external = ArtifactEnvelope("reviewed-scenario", "v1", "simulation_review",
                                ImplementationStatus.SCAFFOLDED, AuthorityLevel.NO_AUTHORITY,
                                {"reviewer_id": "simulation-reviewer"})
    first = pipeline.run(HISTORY, stop_after="intent_acceptance",
                         external_artifacts=[external])
    assert first.external_artifact_ids == [external.artifact_id]
    assert pipeline.store.get(external.artifact_id).producer_stage == "simulation_review"
    assert not any(edge["child_artifact_id"] == external.artifact_id
                   for edge in first.provenance_records.values())
    repeated = pipeline.run(HISTORY, resume=first, stop_after="intent_acceptance",
                            external_artifacts=[external, external])
    assert repeated.external_artifact_ids == [external.artifact_id]
    collision = ArtifactEnvelope("reviewed-scenario", "v1", "simulation_review",
                                 ImplementationStatus.SCAFFOLDED, AuthorityLevel.USER_ACCEPTED_INTENT,
                                 {"reviewer_id": "simulation-reviewer"})
    with pytest.raises(ValueError, match="collision"):
        pipeline.run(HISTORY, resume=first, stop_after="intent_acceptance",
                     external_artifacts=[collision])
    other, *_ = _pipeline()
    with pytest.raises(KeyError):
        other.run(HISTORY, resume=repeated, stop_after="intent_acceptance")


def test_registry_same_version_events_and_content_identity():
    registry = PropertyRegistry()
    candidate = PropertyCandidate("p", "statement", "finding", "contract", {}, 1)
    registry.add(candidate, PropertyStatus.CANDIDATE)
    registry.add(candidate, PropertyStatus.REFUTED, ["e"], "reviewer")
    registry.add(candidate, PropertyStatus.REFUTED, ["e"], "reviewer")
    assert len(registry.history("p")) == 2
    snapshot = registry.history("p")
    snapshot[0]["status"] = "changed"
    assert registry.history("p")[0]["status"] == "CANDIDATE"
    with pytest.raises(ValueError, match="different candidate"):
        registry.add(PropertyCandidate("p", "different", "finding", "contract", {}, 1),
                     PropertyStatus.CANDIDATE)
    registry.add(PropertyCandidate("p", "new", "finding", "contract", {}, 2),
                 PropertyStatus.CANDIDATE)
    with pytest.raises(ValueError, match="older"):
        registry.add(candidate, PropertyStatus.CANDIDATE)


def test_default_bootstrap_remains_offline_and_fail_closed():
    pipeline = build_research_pipeline()
    result = pipeline.run(HISTORY)
    assert result.stages["intent_extraction"].run_status == StageRunStatus.NOT_EVALUATED
    assert all(stage.authority_level == AuthorityLevel.NO_AUTHORITY
               for stage in result.stages.values())
    assert pipeline.ports["ledger_validation"].__class__.__name__ == "DisabledExternalPort"
