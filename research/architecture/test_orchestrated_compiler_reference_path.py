"""A compile-entry research run through real pinned Marlowe behavior.

The accepted intent and reviewed scenario are synthetic external fixtures, not
evidence of authenticated review or production compiler authority.
"""

from research.architecture.bootstrap import ResearchPipelineWiring, build_research_pipeline
from research.architecture.status import AuthorityLevel, StageRunStatus
from research.architecture.test_compiler_reference_integration import (
    ALICE, EXPECTED_CONTRACT, EXPECTED_PAYMENT, FINAL_STATE, FUNDED_STATE,
    REFERENCE_IDENTITY, REVIEWED_SCENARIO, UPSTREAM_COMMIT, _accepted, _independent_expectation,
    real_binary as real_binary,
)
from research.stage3.models import CompileResult, CompileStatus
from research.stage3.profile_compilers.direct_payment_v1 import (
    DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1,
)
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import PinnedMarloweReference
from research.stage4.domains import ExplicitTransactionDomain, TransactionTemplate
from research.stage4.explorer import ExplorationBounds
from research.stage4.oracles import NoWarningsOracle


STAGES = ["compile", "semantic_comparison", "compiler_authority",
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
    return pipeline.run(history, entry_stage="compile", stop_after=stop_after,
                        external_artifacts=[accepted, scenario, expectation])


def _artifact(pipeline, run, stage):
    return pipeline.store.get(run.stages[stage].output_artifacts[0])


def _edges(run):
    return {(item["parent_artifact_id"], item["child_artifact_id"])
            for item in run.provenance_records.values()}


def test_orchestrated_direct_payment_and_provenance(real_binary):
    pipeline, accepted, scenario, expectation, history = _setup(
        PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10.0))
    run = _run(pipeline, accepted, scenario, expectation, history)
    assert run.entry_stage == run.to_dict()["entry_stage"] == "compile"
    assert list(run.stages) == STAGES
    assert run.stage_executions == 5
    assert run.external_artifact_ids == [accepted.artifact_id, scenario.artifact_id,
                                         expectation.artifact_id]
    assert run.stages["compile"].run_status == StageRunStatus.SUCCEEDED
    assert run.stages["compile"].semantic_status == "SUPPORTED"
    compiled = _artifact(pipeline, run, "compile")
    contract = pipeline.store.get(run.stages["compile"].output_artifacts[1])
    assert contract.payload["contract"] == EXPECTED_CONTRACT
    assert run.stages["semantic_comparison"].run_status == StageRunStatus.SUCCEEDED
    assert run.stages["semantic_comparison"].semantic_status == "SATISFIED"
    assert run.stages["semantic_comparison"].input_artifacts == [
        contract.artifact_id, accepted.artifact_id, expectation.artifact_id,
        scenario.artifact_id]
    comparison = _artifact(pipeline, run, "semantic_comparison")
    assert comparison.payload["reference_identity"] == REFERENCE_IDENTITY
    raw = comparison.payload["reference_result"]
    assert raw["status"] == "Success" and raw["final_contract"] == "close"
    assert raw["final_state"] == FINAL_STATE
    assert raw["steps"][0]["payments"] == [EXPECTED_PAYMENT]
    assert raw["steps"][0]["warnings"] == []
    authority_stage = run.stages["compiler_authority"]
    assert authority_stage.run_status == StageRunStatus.SUCCEEDED
    assert authority_stage.semantic_status == "CANDIDATE_ONLY"
    assert authority_stage.authority_level == AuthorityLevel.NO_AUTHORITY
    authority = _artifact(pipeline, run, "compiler_authority")
    assert authority.authority_level == AuthorityLevel.NO_AUTHORITY
    assert authority.payload["decision"] is None
    graph = _artifact(pipeline, run, "exploration")
    assert run.stages["exploration"].run_status == StageRunStatus.SUCCEEDED
    assert graph.payload["coverage"] == "BOUNDED"
    assert len(graph.payload["traces"]) == 1
    trace = graph.payload["traces"][0]
    assert trace["status"] == "Success"
    assert trace["steps"][0]["meta"]["upstream_commit"] == UPSTREAM_COMMIT
    assert trace["steps"][0]["steps"][0]["payments"] == [EXPECTED_PAYMENT]
    assert trace["steps"][0]["steps"][0]["warnings"] == []
    oracle = _artifact(pipeline, run, "oracle_evaluation")
    assert run.stages["oracle_evaluation"].run_status == StageRunStatus.SUCCEEDED
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
    assert list(first.stages) == STAGES[:2]
    assert first.stage_executions == 2
    resumed = pipeline.run(history, resume=first, stop_after="oracle_evaluation")
    assert list(resumed.stages) == STAGES
    assert resumed.stage_executions == 5
    assert (resumed.run_id, resumed.requirement_artifact_id, resumed.entry_stage) == (
        first.run_id, first.requirement_artifact_id, "compile")
    assert resumed.stages["compile"].output_artifacts == first.stages["compile"].output_artifacts
    assert resumed.stages["semantic_comparison"].output_artifacts == (
        first.stages["semantic_comparison"].output_artifacts)


def test_wrong_close_fails_closed_before_authority(real_binary):
    def wrong_compiler(ir):
        correct = compile_direct_payment_v1(ir)
        assert correct.status == CompileStatus.SUPPORTED
        return CompileResult(CompileStatus.SUPPORTED, "close", correct.mapping_evidence)

    pipeline, accepted, scenario, expectation, history = _setup(
        PinnedMarloweReference(binary=real_binary, hard_timeout_seconds=10.0), wrong_compiler)
    run = _run(pipeline, accepted, scenario, expectation, history)
    assert run.stage_executions == 2
    assert run.stages["compile"].run_status == StageRunStatus.SUCCEEDED
    assert run.stages["compile"].semantic_status == "SUPPORTED"
    assert run.stages["semantic_comparison"].run_status == StageRunStatus.FAILED
    assert run.stages["semantic_comparison"].semantic_status == "VIOLATED"
    raw = _artifact(pipeline, run, "semantic_comparison").payload
    assert raw["mismatches"] == ["payments"]
    assert raw["reference_result"]["steps"][0]["payments"][0]["payee"] == {"party": ALICE}
    assert run.stages["compiler_authority"].run_status == StageRunStatus.NOT_EVALUATED
    assert run.stages["compiler_authority"].blocked_by == ["semantic_comparison"]
    assert run.stages["exploration"].run_status == StageRunStatus.NOT_EVALUATED
    assert run.stages["oracle_evaluation"].run_status == StageRunStatus.NOT_EVALUATED
    assert not run.stages["compiler_authority"].output_artifacts
    assert not run.stages["exploration"].output_artifacts
    assert not run.stages["oracle_evaluation"].output_artifacts


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
    assert unavailable.stage_executions == 3
    assert unavailable.stages["semantic_comparison"].run_status == StageRunStatus.UNAVAILABLE
    assert unavailable.stages["semantic_comparison"].semantic_status != "SATISFIED"
    authority = unavailable.stages["compiler_authority"]
    assert authority.run_status == StageRunStatus.SUCCEEDED
    assert authority.semantic_status == "CANDIDATE_ONLY"
    assert authority.authority_level == AuthorityLevel.NO_AUTHORITY
    old_comparison = authority.input_artifacts[1]
    old_authority = authority.output_artifacts[0]
    assert _artifact(pipeline, unavailable, "compiler_authority").payload["decision"] is None
    assert unavailable.stages["exploration"].run_status == StageRunStatus.NOT_EVALUATED
    assert unavailable.stages["exploration"].blocked_by == ["semantic_comparison"]
    assert unavailable.stages["oracle_evaluation"].run_status == StageRunStatus.NOT_EVALUATED
    stale_edges = {key for key, value in unavailable.provenance_records.items()
                   if value["child_artifact_id"] == old_comparison
                   or value["parent_artifact_id"] == old_comparison}
    reference.available = True
    recovered = pipeline.run(history, resume=unavailable, stop_after="oracle_evaluation")
    assert recovered.stage_executions == 7
    assert recovered.run_id == unavailable.run_id
    assert recovered.stages["semantic_comparison"].run_status == StageRunStatus.SUCCEEDED
    assert recovered.stages["semantic_comparison"].semantic_status == "SATISFIED"
    assert recovered.stages["compiler_authority"].semantic_status == "CANDIDATE_ONLY"
    assert recovered.stages["exploration"].run_status == StageRunStatus.SUCCEEDED
    assert recovered.stages["oracle_evaluation"].run_status == StageRunStatus.SUCCEEDED
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
    assert inconclusive.stages["semantic_comparison"].run_status == StageRunStatus.INCONCLUSIVE
    assert inconclusive.stages["compiler_authority"].run_status == StageRunStatus.NOT_EVALUATED
    assert inconclusive.stages["exploration"].run_status == StageRunStatus.NOT_EVALUATED
    assert inconclusive.stage_executions == 2

    class RejectPolicy:
        def authorize(self, artifact):
            return False

    pipeline, accepted, scenario, expectation, history = _setup(
        StaticReference(raw), expectation_policy=RejectPolicy())
    blocked = _run(pipeline, accepted, scenario, expectation, history)
    assert blocked.stages["semantic_comparison"].run_status == StageRunStatus.BLOCKED
    assert blocked.stages["compiler_authority"].run_status == StageRunStatus.NOT_EVALUATED
    assert blocked.stages["exploration"].run_status == StageRunStatus.NOT_EVALUATED
    assert blocked.stage_executions == 2
