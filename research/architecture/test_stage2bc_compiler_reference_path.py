"""Controlled Stage 2B/2C to deterministic compiler and pinned reference.

Extraction, projection, acceptance, compilation, and reference execution are
real. The semantic-core model and reviewer policy are deterministic test
dependencies; this does not validate live LLM accuracy or reviewer identity.
"""

from copy import deepcopy

from research.architecture.artifacts import ArtifactEnvelope, canonical_json_v1, stable_artifact_id
from research.architecture.bootstrap import ResearchPipelineWiring, build_research_pipeline
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.architecture.test_compiler_reference_integration import (
    EXPECTED_CONTRACT, EXPECTED_PAYMENT, FINAL_STATE, FUNDED_STATE, REFERENCE_IDENTITY,
    _independent_expectation, real_binary as real_binary,
)
from research.architecture.test_orchestrated_compiler_reference_path import (
    IntegrationExpectationPolicy,
)
from research.stage2b.intent_spec import validate_intent_spec, validate_shadow_semantic_core
from research.stage2b.projector import project_intent_spec
from research.stage2c.models import IntentDecision, IntentDecisionStatus
from research.stage3.compiler import CompilerPort
from research.stage3.profile_compilers.direct_payment_v1 import (
    DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1,
)
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import PinnedMarloweReference
from research.stage4.domains import ExplicitTransactionDomain, TransactionTemplate
from research.stage4.explorer import ExplorationBounds
from research.stage4.oracles import NoWarningsOracle


SOURCE_TEXT = "Pay 10 ADA from Alice account to Bob."
HISTORY = [{"version": 1, "messages": [SOURCE_TEXT]}]
REVIEWER_ID = "stage2b-stage2c-integration-reviewer"


def semantic_core():
    def claim(claim_id, kind, value, scope_id, span, status="explicit"):
        item = {"claim_id": claim_id, "kind": kind, "value": value,
                "criticality": "financial", "status": status, "scope_id": scope_id,
                "evidence": [{"requirement_version": 1, "message_index": 0,
                              "span": span, "relation": "supports"}]}
        if status == "derived":
            item["normalization_basis"] = "1 ADA = 1000000 lovelace"
        return item

    return {"schema_version": "stage2b-shadow-core-v1",
            "requirement_history": deepcopy(HISTORY),
            "behavior_scopes": [
                {"scope_id": "global", "scope_type": "global"},
                {"scope_id": "payment-1", "scope_type": "transition",
                 "transition_kind": "payment"}],
            "claims": [
                claim("source", "payment_source_account_owner", "Alice", "payment-1",
                      "from Alice account"),
                claim("asset", "asset", "ADA", "global", "10 ADA"),
                claim("amount", "amount_lovelace", 10000000, "payment-1", "10 ADA", "derived"),
                claim("recipient", "payment_recipient", "Bob", "payment-1", "to Bob")],
            "required_clarifications": [], "unscored_observations": [],
            "predicted_resolution": "accepted_interpretation"}


class DeterministicShadowModel:
    def __init__(self):
        self.calls = 0

    def generate(self, system, user):
        assert SOURCE_TEXT in user
        self.calls += 1
        return deepcopy(semantic_core())


class ExactSpecReviewerPolicy:
    def __init__(self):
        self.candidate_id = None

    def authorize(self, candidate, decision):
        return (candidate.artifact_type == "intent-candidate"
                and candidate.artifact_id == self.candidate_id
                and decision.reviewer_id == REVIEWER_ID
                and decision.approved_spec is not None
                and canonical_json_v1(decision.approved_spec)
                == canonical_json_v1(candidate.payload["intent_spec"]))


class CountingPinnedReference:
    def __init__(self, binary):
        self.real = PinnedMarloweReference(binary=binary, hard_timeout_seconds=10.0)
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return self.real.execute(request)


def _pipeline(reference):
    model = DeterministicShadowModel()
    reviewer = ExactSpecReviewerPolicy()
    scenario, expectation = _independent_expectation()
    wiring = ResearchPipelineWiring(
        reviewer_policy=reviewer,
        profile_registry=ProfileRegistry([DIRECT_PAYMENT_PROFILE]),
        compiler_plugins={("direct-payment", "v1"): compile_direct_payment_v1},
        reference_executor=reference,
        expectation_policy=IntegrationExpectationPolicy(expectation, scenario),
        promotion_policy=None,
        exploration_domain=ExplicitTransactionDomain(
            "stage2bc-direct-payment-real-reference-v1",
            [TransactionTemplate("NoInput", 0, 0, ())]),
        exploration_initial_state=FUNDED_STATE,
        exploration_bounds=ExplorationBounds(max_depth=1, max_traces=1),
        oracles=[NoWarningsOracle()],
    )
    return build_research_pipeline(model=model, wiring=wiring), model, reviewer, scenario, expectation


def _artifact(pipeline, run, stage, artifact_type):
    return next(pipeline.store.get(item) for item in run.stages[stage].output_artifacts
                if pipeline.store.get(item).artifact_type == artifact_type)


def _edges(run):
    return {(record["parent_artifact_id"], record["child_artifact_id"])
            for record in run.provenance_records.values()}


def test_direct_payment_core_projects_conservatively_and_compiles_without_rewriting():
    core = semantic_core()
    assert validate_shadow_semantic_core(core, expected_history=HISTORY) == []
    extraction = project_intent_spec(core, expected_history=HISTORY)
    spec = extraction.intent_spec.to_dict()
    assert spec["states"] == [{"state_id": "initial", "claim_refs": []}]
    assert extraction.projection_diagnostics["complete"] is True
    assert validate_intent_spec(spec, expected_history=HISTORY) == []
    match, _, diagnostics = ProfileRegistry([DIRECT_PAYMENT_PROFILE]).match(spec)
    assert match.value == "EXACT_SUPPORTED_PROFILE" and diagnostics == []
    accepted = ArtifactEnvelope("accepted-intent", "v1", "test-only",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.USER_ACCEPTED_INTENT,
                                {"accepted_spec": spec})
    compiled = CompilerPort(ProfileRegistry([DIRECT_PAYMENT_PROFILE]),
                            {("direct-payment", "v1"): compile_direct_payment_v1}).execute(
                                [accepted], StageContext("projector-test"))
    assert compiled.result.run_status == StageRunStatus.SUCCEEDED
    assert compiled.result.semantic_status == "SUPPORTED"
    assert next(item for item in compiled.artifacts
                if item.artifact_type == "contract-candidate").payload["contract"] == EXPECTED_CONTRACT


def test_exact_spec_reviewer_rejects_rewrite_and_wrong_reviewer():
    pipeline, model, reviewer, scenario, expectation = _pipeline(None)
    first = pipeline.run(HISTORY, stop_after="intent_acceptance",
                         external_artifacts=[scenario, expectation])
    candidate = _artifact(pipeline, first, "intent_extraction", "intent-candidate")
    reviewer.candidate_id = candidate.artifact_id
    spec = candidate.to_dict()["payload"]["intent_spec"]
    valid = IntentDecision(IntentDecisionStatus.ACCEPTED, REVIEWER_ID, True, (), spec)
    assert reviewer.authorize(candidate, valid)
    assert not reviewer.authorize(candidate, IntentDecision(
        IntentDecisionStatus.ACCEPTED, "other-reviewer", True, (), spec))
    changed = deepcopy(spec)
    changed["claims"][-1]["value"] = "Carol"
    denied = IntentDecision(IntentDecisionStatus.ACCEPTED, REVIEWER_ID, True, (), changed)
    assert not reviewer.authorize(candidate, denied)
    result = pipeline.run(HISTORY, resume=first, stop_after="compile",
                          options={"intent_decision": denied})
    assert result.stages["intent_acceptance"].run_status == StageRunStatus.BLOCKED
    assert result.stages["compile"].run_status == StageRunStatus.NOT_EVALUATED
    assert not any(pipeline.store.get(item).artifact_type == "accepted-intent"
                   for item in result.stages["intent_acceptance"].output_artifacts)
    assert model.calls == 1


def test_stage2bc_to_real_reference_with_pause_and_exact_freeze(real_binary):
    reference = CountingPinnedReference(real_binary)
    pipeline, model, reviewer, scenario, expectation = _pipeline(reference)
    first = pipeline.run(HISTORY, stop_after="intent_acceptance",
                         external_artifacts=[scenario, expectation])
    assert list(first.stages) == ["intent_extraction", "intent_acceptance"]
    assert first.stage_executions == 2 and model.calls == 1
    assert first.stages["intent_extraction"].run_status == StageRunStatus.SUCCEEDED
    assert first.stages["intent_extraction"].semantic_status == "PASS"
    assert first.stages["intent_extraction"].authority_level == AuthorityLevel.MODEL_CANDIDATE
    assert first.stages["intent_acceptance"].run_status == StageRunStatus.WAITING_USER
    review = _artifact(pipeline, first, "intent_acceptance", "intent-review")
    assert review.payload["issues"] == []
    candidate = _artifact(pipeline, first, "intent_extraction", "intent-candidate")
    assert candidate.payload["core_validation_errors"] == []
    assert candidate.payload["full_validation_errors"] == []
    assert candidate.payload["projection_classification"] == "PASS"
    assert candidate.payload["projection_diagnostics"]["complete"] is True
    spec = candidate.to_dict()["payload"]["intent_spec"]
    assert spec["states"] == [{"state_id": "initial", "claim_refs": []}]
    assert {item["name"] for item in spec["participants"]} == {"Alice", "Bob"}
    assert spec["assets_and_accounts"]["assets"][0]["symbol"] == "ADA"
    assert spec["assets_and_accounts"]["accounts"][0]["owner"] == "Alice"
    assert spec["assets_and_accounts"]["funding_relations"] == []
    assert spec["parameters"][0]["normalized_value"] == 10000000
    assert spec["parameters"][0]["unit"] == "lovelace"
    assert spec["transitions"][0]["kind"] == "payment"
    assert spec["obligations_and_outcomes"][0]["recipient"] == "Bob"
    assert spec["required_clarifications"] == spec["conflicts"] == spec["assumptions_and_provenance"] == []
    assert spec["predicted_resolution"] == "accepted_interpretation"
    reviewer.candidate_id = candidate.artifact_id
    decision = IntentDecision(IntentDecisionStatus.ACCEPTED, REVIEWER_ID, True, (), spec)
    assert reviewer.authorize(candidate, decision)
    resumed = pipeline.run(HISTORY, resume=first, stop_after="oracle_evaluation",
                           options={"intent_decision": decision})
    assert model.calls == 1 and reference.calls == 2
    assert resumed.stage_executions == 8
    assert resumed.stages["intent_extraction"].output_artifacts == first.stages["intent_extraction"].output_artifacts
    assert resumed.stages["intent_acceptance"].run_status == StageRunStatus.SUCCEEDED
    assert resumed.stages["intent_acceptance"].semantic_status == "ACCEPTED"
    assert resumed.stages["intent_acceptance"].authority_level == AuthorityLevel.USER_ACCEPTED_INTENT
    accepted = _artifact(pipeline, resumed, "intent_acceptance", "accepted-intent")
    manifest = _artifact(pipeline, resumed, "intent_acceptance", "accepted-intent-manifest")
    assert canonical_json_v1(accepted.payload["accepted_spec"]) == canonical_json_v1(spec)
    assert manifest.payload["candidate_artifact_id"] == candidate.artifact_id
    assert manifest.payload["accepted_artifact_id"] == accepted.artifact_id
    assert manifest.payload["accepted_spec_schema"] == "stage2b-shadow-v1"
    assert manifest.payload["source_history_hash"] == stable_artifact_id(
        "requirement-history", "v1", HISTORY)
    assert resumed.stages["compile"].run_status == StageRunStatus.SUCCEEDED
    assert resumed.stages["compile"].semantic_status == "SUPPORTED"
    contract = _artifact(pipeline, resumed, "compile", "contract-candidate")
    compile_result = _artifact(pipeline, resumed, "compile", "compile-result")
    assert contract.payload["contract"] == EXPECTED_CONTRACT
    assert resumed.stages["semantic_comparison"].run_status == StageRunStatus.SUCCEEDED
    assert resumed.stages["semantic_comparison"].semantic_status == "SATISFIED"
    comparison = _artifact(pipeline, resumed, "semantic_comparison", "reference-comparison")
    assert comparison.payload["reference_identity"] == REFERENCE_IDENTITY
    assert comparison.payload["contract_artifact_id"] == contract.artifact_id
    raw = comparison.payload["reference_result"]
    assert raw["status"] == "Success" and raw["final_contract"] == "close"
    assert raw["final_state"] == FINAL_STATE
    assert raw["steps"][0]["payments"] == [EXPECTED_PAYMENT]
    assert raw["steps"][0]["warnings"] == []
    authority = _artifact(pipeline, resumed, "compiler_authority", "compiler-authority-decision")
    assert resumed.stages["compiler_authority"].run_status == StageRunStatus.SUCCEEDED
    assert resumed.stages["compiler_authority"].semantic_status == "CANDIDATE_ONLY"
    assert authority.authority_level == AuthorityLevel.NO_AUTHORITY
    assert authority.payload["reference_identity"] == REFERENCE_IDENTITY
    assert authority.payload["decision"] is None
    graph = _artifact(pipeline, resumed, "exploration", "exploration-graph")
    assert resumed.stages["exploration"].run_status == StageRunStatus.SUCCEEDED
    assert graph.payload["coverage"] == "BOUNDED" and len(graph.payload["traces"]) == 1
    assert graph.payload["traces"][0]["steps"][0]["steps"][0]["payments"] == [EXPECTED_PAYMENT]
    oracle = _artifact(pipeline, resumed, "oracle_evaluation", "oracle-findings")
    assert resumed.stages["oracle_evaluation"].run_status == StageRunStatus.SUCCEEDED
    assert oracle.payload["findings"][0]["verdict"] == "SATISFIED"
    edges = _edges(resumed)
    for parent, child in (
        (resumed.requirement_artifact_id, candidate.artifact_id),
        (candidate.artifact_id, review.artifact_id),
        (candidate.artifact_id, accepted.artifact_id),
        (candidate.artifact_id, manifest.artifact_id),
        (accepted.artifact_id, compile_result.artifact_id),
        (accepted.artifact_id, contract.artifact_id),
        (contract.artifact_id, comparison.artifact_id),
        (accepted.artifact_id, comparison.artifact_id),
        (expectation.artifact_id, comparison.artifact_id),
        (scenario.artifact_id, comparison.artifact_id),
        (contract.artifact_id, authority.artifact_id),
        (comparison.artifact_id, authority.artifact_id),
        (contract.artifact_id, graph.artifact_id),
        (graph.artifact_id, oracle.artifact_id),
    ):
        assert (parent, child) in edges
    assert not any(parent == resumed.requirement_artifact_id and child in {
        scenario.artifact_id, expectation.artifact_id} for parent, child in edges)
