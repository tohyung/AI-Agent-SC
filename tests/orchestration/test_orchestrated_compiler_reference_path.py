"""A compile-entry research run through real pinned Marlowe behavior.

The accepted intent and reviewed scenario are synthetic external fixtures, not
evidence of authenticated review or production compiler authority.
"""

from research.orchestration.bootstrap import ResearchPipelineWiring, build_research_pipeline
from research.orchestration.status import AuthorityLevel, StepRunStatus
from tests.orchestration.test_compiler_reference_integration import (
    ALICE, EXPECTED_CONTRACT, EXPECTED_PAYMENT, FINAL_STATE, FUNDED_STATE,
    REFERENCE_IDENTITY, REVIEWED_SCENARIO, UPSTREAM_COMMIT, _accepted, _independent_expectation,
    real_binary as real_binary,
)
from research.synthesis.models import CompileResult, CompileStatus
from research.synthesis.profile_compilers.direct_payment_v1 import (
    DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1,
)
from research.synthesis.profiles import ProfileRegistry
from research.synthesis.reference import PinnedMarloweReference
from research.exploration.domains import ExplicitTransactionDomain, TransactionTemplate
from research.exploration.explorer import ExplorationBounds
from research.exploration.oracles import NoWarningsOracle


STEPS = ["compile", "semantic_comparison", "compiler_authority",
          "exploration", "oracle_evaluation"]


class IntegrationExpectationPolicy:
    def __init__(self, expectation, scenario):
        self.expectation = expectation
        self.scenario = scenario

    def authorize(self, artifact):
        return (artifact.artifact_id == self.expectation.artifact_id
                and artifact.payload["source_artifact_id"] == self.scenario.artifact_id
                and artifact.payload["reviewer_id"] == REVIEWED_SCENARIO["reviewer_id"])


def _setup(reference, plugin=compile_direct_payment_v1, expectation_policy=None):
    accepted = _accepted()
    scenario, expectation = _independent_expectation()
    policy = expectation_policy or IntegrationExpectationPolicy(expectation, scenario)
    wiring = ResearchPipelineWiring(
        profile_registry=ProfileRegistry([DIRECT_PAYMENT_PROFILE]),
        compiler_plugins={("direct-payment", "v1"): plugin},
        reference_executor=reference, expectation_policy=policy,
        promotion_policy=None,
        exploration_domain=ExplicitTransactionDomain(
            "direct-payment-orchestrated-real-reference-v1",
            [TransactionTemplate("NoInput", 0, 0, ())]),
        exploration_initial_state=FUNDED_STATE,
        exploration_bounds=ExplorationBounds(max_depth=1, max_traces=1),
        oracles=[NoWarningsOracle()],
    )
    return (build_research_pipeline(wiring=wiring), accepted, scenario, expectation,
            accepted.payload["accepted_spec"]["requirement_history"])


def _run(pipeline, accepted, scenario, expectation, history, stop_after="oracle_evaluation"):
    return pipeline.run(history, entry_step="compile", stop_after=stop_after,
                        external_artifacts=[accepted, scenario, expectation])


def _artifact(pipeline, run, step):
    return pipeline.store.get(run.steps[step].output_artifacts[0])


def _edges(run):
    return {(item["parent_artifact_id"], item["child_artifact_id"])
            for item in run.provenance_records.values()}


def test_orchestrated_direct_payment_and_provenance(real_binary):
    pipeline, accepted, scenario, expectation, history = _setup(
        PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10.0))
    run = _run(pipeline, accepted, scenario, expectation, history)
    assert run.entry_step == run.to_dict()["entry_step"] == "compile"
    assert list(run.steps) == STEPS
    assert run.step_executions == 5
    assert run.external_artifact_ids == [accepted.artifact_id, scenario.artifact_id,
                                         expectation.artifact_id]
    assert run.steps["compile"].run_status == StepRunStatus.SUCCEEDED
    assert run.steps["compile"].semantic_status == "SUPPORTED"
    compiled = _artifact(pipeline, run, "compile")
    contract = pipeline.store.get(run.steps["compile"].output_artifacts[1])
    assert contract.payload["contract"] == EXPECTED_CONTRACT
    assert run.steps["semantic_comparison"].run_status == StepRunStatus.SUCCEEDED
    assert run.steps["semantic_comparison"].semantic_status == "SATISFIED"
    assert run.steps["semantic_comparison"].input_artifacts == [
        contract.artifact_id, accepted.artifact_id, expectation.artifact_id,
        scenario.artifact_id]
    comparison = _artifact(pipeline, run, "semantic_comparison")
    assert comparison.payload["reference_identity"] == REFERENCE_IDENTITY
    raw = comparison.payload["reference_result"]
    assert raw["status"] == "Success" and raw["final_contract"] == "close"
    assert raw["final_state"] == FINAL_STATE
    assert raw["steps"][0]["payments"] == [EXPECTED_PAYMENT]
    assert raw["steps"][0]["warnings"] == []
    authority_step = run.steps["compiler_authority"]
    assert authority_step.run_status == StepRunStatus.SUCCEEDED
    assert authority_step.semantic_status == "CANDIDATE_ONLY"
    assert authority_step.authority_level == AuthorityLevel.NO_AUTHORITY
    authority = _artifact(pipeline, run, "compiler_authority")
    assert authority.authority_level == AuthorityLevel.NO_AUTHORITY
    assert authority.payload["decision"] is None
    graph = _artifact(pipeline, run, "exploration")
    assert run.steps["exploration"].run_status == StepRunStatus.SUCCEEDED
    assert graph.payload["coverage"] == "BOUNDED"
    assert len(graph.payload["traces"]) == 1
    trace = graph.payload["traces"][0]
    assert trace["status"] == "Success"
    assert trace["steps"][0]["meta"]["upstream_commit"] == UPSTREAM_COMMIT
    assert trace["steps"][0]["steps"][0]["payments"] == [EXPECTED_PAYMENT]
    assert trace["steps"][0]["steps"][0]["warnings"] == []
    oracle = _artifact(pipeline, run, "oracle_evaluation")
    assert run.steps["oracle_evaluation"].run_status == StepRunStatus.SUCCEEDED
    assert oracle.payload["findings"][0]["verdict"] == "SATISFIED"
    edges = _edges(run)
    for parent, child in (
        (accepted.artifact_id, compiled.artifact_id),
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
    assert not any(parent == run.requirement_artifact_id and child in run.external_artifact_ids
                   for parent, child in edges)


def test_partial_run_resume_reuses_compilation_and_comparison(real_binary):
    pipeline, accepted, scenario, expectation, history = _setup(
        PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10.0))
    first = _run(pipeline, accepted, scenario, expectation, history, "semantic_comparison")
    assert list(first.steps) == STEPS[:2]
    assert first.step_executions == 2
    resumed = pipeline.run(history, resume=first, stop_after="oracle_evaluation")
    assert list(resumed.steps) == STEPS
    assert resumed.step_executions == 5
    assert (resumed.run_id, resumed.requirement_artifact_id, resumed.entry_step) == (
        first.run_id, first.requirement_artifact_id, "compile")
    assert resumed.steps["compile"].output_artifacts == first.steps["compile"].output_artifacts
    assert resumed.steps["semantic_comparison"].output_artifacts == (
        first.steps["semantic_comparison"].output_artifacts)


def test_wrong_close_fails_closed_before_authority(real_binary):
    def wrong_compiler(ir):
        correct = compile_direct_payment_v1(ir)
        assert correct.status == CompileStatus.SUPPORTED
        return CompileResult(CompileStatus.SUPPORTED, "close", correct.mapping_evidence)

    pipeline, accepted, scenario, expectation, history = _setup(
        PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10.0), wrong_compiler)
    run = _run(pipeline, accepted, scenario, expectation, history)
    assert run.step_executions == 2
    assert run.steps["compile"].run_status == StepRunStatus.SUCCEEDED
    assert run.steps["compile"].semantic_status == "SUPPORTED"
    assert run.steps["semantic_comparison"].run_status == StepRunStatus.FAILED
    assert run.steps["semantic_comparison"].semantic_status == "VIOLATED"
    raw = _artifact(pipeline, run, "semantic_comparison").payload
    assert raw["mismatches"] == ["payments"]
    assert raw["reference_result"]["steps"][0]["payments"][0]["payee"] == {"party": ALICE}
    assert run.steps["compiler_authority"].run_status == StepRunStatus.NOT_EVALUATED
    assert run.steps["compiler_authority"].blocked_by == ["semantic_comparison"]
    assert run.steps["exploration"].run_status == StepRunStatus.NOT_EVALUATED
    assert run.steps["oracle_evaluation"].run_status == StepRunStatus.NOT_EVALUATED
    assert not run.steps["compiler_authority"].output_artifacts
    assert not run.steps["exploration"].output_artifacts
    assert not run.steps["oracle_evaluation"].output_artifacts


class RecoveringReference:
    def __init__(self, binary):
        self.real = PinnedMarloweReference(binary=binary, hard_timeout_seconds=10.0)
        self.available = False

    def execute(self, request):
        if not self.available:
            return {"status": "Unavailable", "steps": [], "detail": {"reason": "test outage"}}
        return self.real.execute(request)


def test_reference_outage_records_candidate_but_blocks_exploration_then_recovers(real_binary):
    reference = RecoveringReference(real_binary)
    pipeline, accepted, scenario, expectation, history = _setup(reference)
    unavailable = _run(pipeline, accepted, scenario, expectation, history)
    assert unavailable.step_executions == 3
    assert unavailable.steps["semantic_comparison"].run_status == StepRunStatus.UNAVAILABLE
    assert unavailable.steps["semantic_comparison"].semantic_status != "SATISFIED"
    authority = unavailable.steps["compiler_authority"]
    assert authority.run_status == StepRunStatus.SUCCEEDED
    assert authority.semantic_status == "CANDIDATE_ONLY"
    assert authority.authority_level == AuthorityLevel.NO_AUTHORITY
    old_comparison = authority.input_artifacts[1]
    old_authority = authority.output_artifacts[0]
    assert _artifact(pipeline, unavailable, "compiler_authority").payload["decision"] is None
    assert unavailable.steps["exploration"].run_status == StepRunStatus.NOT_EVALUATED
    assert unavailable.steps["exploration"].blocked_by == ["semantic_comparison"]
    assert unavailable.steps["oracle_evaluation"].run_status == StepRunStatus.NOT_EVALUATED
    stale_edges = {key for key, value in unavailable.provenance_records.items()
                   if value["child_artifact_id"] == old_comparison
                   or value["parent_artifact_id"] == old_comparison}
    reference.available = True
    recovered = pipeline.run(history, resume=unavailable, stop_after="oracle_evaluation")
    assert recovered.step_executions == 7
    assert recovered.run_id == unavailable.run_id
    assert recovered.steps["semantic_comparison"].run_status == StepRunStatus.SUCCEEDED
    assert recovered.steps["semantic_comparison"].semantic_status == "SATISFIED"
    assert recovered.steps["compiler_authority"].semantic_status == "CANDIDATE_ONLY"
    assert recovered.steps["exploration"].run_status == StepRunStatus.SUCCEEDED
    assert recovered.steps["oracle_evaluation"].run_status == StepRunStatus.SUCCEEDED
    assert stale_edges.isdisjoint(recovered.provenance_records)
    assert pipeline.store.has(old_comparison) and pipeline.store.has(old_authority)


class StaticReference:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, request):
        return self.raw


def test_inconclusive_and_blocked_comparisons_do_not_run_authority():
    raw = {"status": "Success", "final_contract": "close", "final_state": FINAL_STATE,
           "steps": [{"status": "Success", "warnings": []}],
           "meta": {"upstream_commit": "test", "reference_driver_version": "v1"}}
    pipeline, accepted, scenario, expectation, history = _setup(StaticReference(raw))
    inconclusive = _run(pipeline, accepted, scenario, expectation, history)
    assert inconclusive.steps["semantic_comparison"].run_status == StepRunStatus.INCONCLUSIVE
    assert inconclusive.steps["compiler_authority"].run_status == StepRunStatus.NOT_EVALUATED
    assert inconclusive.steps["exploration"].run_status == StepRunStatus.NOT_EVALUATED
    assert inconclusive.step_executions == 2

    class RejectPolicy:
        def authorize(self, artifact):
            return False

    pipeline, accepted, scenario, expectation, history = _setup(
        StaticReference(raw), expectation_policy=RejectPolicy())
    blocked = _run(pipeline, accepted, scenario, expectation, history)
    assert blocked.steps["semantic_comparison"].run_status == StepRunStatus.BLOCKED
    assert blocked.steps["compiler_authority"].run_status == StepRunStatus.NOT_EVALUATED
    assert blocked.steps["exploration"].run_status == StepRunStatus.NOT_EVALUATED
    assert blocked.step_executions == 2
