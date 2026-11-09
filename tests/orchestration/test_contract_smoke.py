"""Offline interface smoke, not semantic or compiler validation."""

from __future__ import annotations

from copy import deepcopy
import importlib
import json
import pytest

from research.orchestration.artifacts import ArtifactEnvelope, ArtifactStore, stable_artifact_id
from research.orchestration.assurance import AssuranceClaim, EvidenceRef
from research.orchestration.bootstrap import build_research_pipeline
from research.orchestration.models import ResearchPipelineRun, StepResult
from research.orchestration.orchestrator import ResearchOrchestrator, STEP_ORDER
from research.orchestration.ports import StepExecution
from research.orchestration.status import (AssuranceMethod, AssuranceVerdict, AuthorityLevel,
                                          ImplementationStatus, StepRunStatus)
from research.formalization.intent_spec import extract_core_view
from tests.formalization.test_intent_spec import simple_payment
from research.ratification.acceptance import IntentAcceptancePort
from research.synthesis.authority import CompilerAuthorityPort
from research.synthesis.compiler import CompilerPort
from research.synthesis.comparison import BehaviorExpectation, SemanticComparisonPort
from research.synthesis.models import CompilerAuthorityDecision, CompilerAuthorityStatus
from research.synthesis.models import CompileResult, CompileStatus, SupportedProfile
from research.synthesis.profiles import ProfileRegistry
from research.synthesis.reference import ReferenceRequest
from research.exploration.oracles import NoWarningsOracle
from research.exploration.domains import (ExplicitTransactionDomain, IntervalRelation,
                                     TransactionTemplate, classify_interval)
from research.induction.registry import PropertyCandidate, PropertyRegistry, PropertyStatus


def _candidate(spec, core_errors=None):
    return ArtifactEnvelope("intent-candidate", "v1", "intent_extraction",
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.MODEL_CANDIDATE,
                            {"semantic_core": extract_core_view(spec), "intent_spec": spec,
                             "source_history": spec["requirement_history"],
                             "core_validation_errors": core_errors or [], "full_validation_errors": []})


class _CandidatePort:
    def __init__(self, candidate):
        self.candidate = candidate

    def execute(self, artifacts, context):
        return StepExecution(StepResult("intent_extraction", ImplementationStatus.SCAFFOLDED,
                                          StepRunStatus.SUCCEEDED,
                                          input_artifacts=[artifacts[0].artifact_id]),
                              [self.candidate])


def test_imports_are_offline_and_acyclic():
    for package in ("research.orchestration", "research.ratification", "research.synthesis",
                    "research.exploration", "research.induction", "research.ledger",
                    "research.orchestration.bootstrap"):
        importlib.import_module(package)


def test_artifact_hash_ignores_envelope_metadata_and_preserves_lineage():
    first = ArtifactEnvelope("kind-a", "v1", "one", ImplementationStatus.SCAFFOLDED,
                             AuthorityLevel.NO_AUTHORITY, {"k": "é", "n": 3}, {"run": 1})
    second = ArtifactEnvelope("kind-a", "v1", "two", ImplementationStatus.SCAFFOLDED,
                              AuthorityLevel.NO_AUTHORITY, {"n": 3, "k": "é"}, {"run": 2})
    assert first.artifact_id == second.artifact_id
    assert first.artifact_id != stable_artifact_id("kind-b", "v1", first.payload)
    assert first.artifact_id != stable_artifact_id("kind-a", "v2", first.payload)
    store = ArtifactStore()
    store.put(first)
    with pytest.raises(TypeError):
        first.payload["n"] = 99
    assert store.get(second.artifact_id).payload["n"] == 3
    assert json.loads(json.dumps(store.get(second.artifact_id).to_dict()))["content_hash"] == first.content_hash
    evidence = EvidenceRef("e", "artifact", "test", first.artifact_id,
                           content_hash=first.content_hash)
    assert evidence.verify_artifact(store)
    assert not EvidenceRef("bad", "artifact", "test", first.artifact_id,
                           content_hash="0" * 64).verify_artifact(store)
    with pytest.raises(ValueError):
        AssuranceClaim("c", "contract", AssuranceVerdict.SATISFIED,
                       AssuranceMethod.DETERMINISTIC_VALIDATION, {}, {})


def test_invalid_candidate_blocks_2c_and_compiler_is_not_evaluated():
    spec = simple_payment()
    candidate = _candidate(spec, ["invalid core"])
    pipeline = ResearchOrchestrator({"intent_extraction": _CandidatePort(candidate),
                                     "intent_acceptance": IntentAcceptancePort(),
                                     "compile": CompilerPort()})
    run = pipeline.run(spec["requirement_history"], stop_after="compile")
    assert run.steps["intent_acceptance"].run_status == StepRunStatus.BLOCKED
    assert run.steps["compile"].run_status == StepRunStatus.NOT_EVALUATED


def test_waiting_review_resumes_with_immutable_answer_then_profile_is_unsupported():
    spec = simple_payment()
    candidate_spec = deepcopy(spec)
    candidate_spec["required_clarifications"] = ["Xác nhận phương án?"]
    candidate = _candidate(candidate_spec)
    class _ReviewerPolicyForInterfaceTest:
        def authorize(self, candidate, decision):
            return decision.reviewer_id == "human-1"

    pipeline = ResearchOrchestrator({"intent_extraction": _CandidatePort(candidate),
                                     "intent_acceptance": IntentAcceptancePort(
                                         _ReviewerPolicyForInterfaceTest()),
                                     "compile": CompilerPort()})
    first = pipeline.run(spec["requirement_history"], stop_after="intent_acceptance")
    assert first.steps["intent_acceptance"].run_status == StepRunStatus.WAITING_USER
    approved = deepcopy(spec)
    approved["requirement_history"].append({"version": 2, "messages": ["Tôi xác nhận phương án."]})
    decision = {"status": "ACCEPTED", "reviewer_id": "human-1", "explicit_consent": True,
                "answers": [{"issue_id": "question-0", "text": "Tôi xác nhận phương án."}],
                "approved_spec": approved}
    resumed = pipeline.run(spec["requirement_history"], stop_after="compile", resume=first,
                           options={"intent_decision": decision})
    assert resumed.steps["intent_acceptance"].run_status == StepRunStatus.SUCCEEDED
    assert any(item.startswith("clarification-answer:")
               for item in resumed.steps["intent_acceptance"].output_artifacts)
    assert resumed.steps["compile"].semantic_status == "UNSUPPORTED_FEATURE"
    assert not any(item.startswith("contract-candidate:")
                   for item in resumed.steps["compile"].output_artifacts)


def test_self_reported_reviewer_id_cannot_accept_without_policy():
    spec = simple_payment()
    candidate = _candidate(spec)
    from research.orchestration.ports import StepContext
    decision = {"status": "ACCEPTED", "reviewer_id": "claimed-human",
                "explicit_consent": True, "approved_spec": spec}
    outcome = IntentAcceptancePort().execute(
        [candidate], StepContext("r", {"intent_decision": decision}))
    assert outcome.result.run_status == StepRunStatus.BLOCKED
    assert not any(item.artifact_type == "accepted-intent" for item in outcome.artifacts)


def test_missing_reference_evidence_blocks_authority_and_exploration():
    spec = simple_payment()
    contract = ArtifactEnvelope("contract-candidate", "core-v1", "compile",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.DETERMINISTIC_COMPILER_CANDIDATE,
                                {"contract": "close", "profile": {
                                    "profile_id": "p", "version": "v1", "compiler_id": "c",
                                    "compiler_version": "v1", "intent_schema_version": "Formalization-IntentSpec-v1"}})
    accepted = ArtifactEnvelope("accepted-intent", "v1", "intent_acceptance",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.USER_ACCEPTED_INTENT, {"accepted_spec": spec})

    class _Seed:
        def __init__(self, step, output):
            self.step = step
            self.output = output

        def execute(self, artifacts, context):
            return StepExecution(StepResult(self.step, ImplementationStatus.SCAFFOLDED,
                                              StepRunStatus.SUCCEEDED), [self.output])

    pipeline = ResearchOrchestrator({"intent_extraction": _Seed("intent_extraction", _candidate(spec)),
                                     "intent_acceptance": _Seed("intent_acceptance", accepted),
                                     "compile": _Seed("compile", contract),
                                     "semantic_comparison": SemanticComparisonPort(),
                                     "compiler_authority": CompilerAuthorityPort()})
    run = pipeline.run(spec["requirement_history"], stop_after="exploration")
    assert run.steps["semantic_comparison"].run_status == StepRunStatus.INCONCLUSIVE
    assert run.steps["compiler_authority"].run_status == StepRunStatus.NOT_EVALUATED
    assert run.steps["compiler_authority"].blocked_by == ["semantic_comparison"]
    assert run.steps["exploration"].run_status == StepRunStatus.NOT_EVALUATED
    assert run.steps["exploration"].blocked_by == ["semantic_comparison"]


def test_bootstrap_defaults_do_not_create_authority_or_live_model():
    pipeline = build_research_pipeline()
    run = pipeline.run([{"version": 1, "messages": ["pay"]}], stop_after="deployment")
    assert run.entry_step == "intent_extraction"
    assert run.to_dict()["entry_step"] == "intent_extraction"
    assert run.steps["intent_extraction"].run_status == StepRunStatus.NOT_EVALUATED
    assert all(step.authority_level == AuthorityLevel.NO_AUTHORITY for step in run.steps.values())


def test_partial_entry_preserves_constructor_and_rejects_invalid_boundaries():
    steps = {}
    positional = ResearchPipelineRun("run", "requirement", steps)
    assert positional.steps is steps
    assert positional.entry_step == "intent_extraction"
    assert positional.to_dict()["entry_step"] == "intent_extraction"

    pipeline = build_research_pipeline()
    history = [{"version": 1, "messages": ["pay"]}]
    with pytest.raises(ValueError, match="unknown entry"):
        pipeline.run(history, entry_step="unknown")
    with pytest.raises(ValueError, match="unknown entry"):
        pipeline.run(history, entry_step="")
    with pytest.raises(ValueError, match="precedes entry"):
        pipeline.run(history, entry_step="compile", stop_after="intent_acceptance")
    partial = pipeline.run(history, entry_step="compile", stop_after="compile")
    assert partial.entry_step == "compile"
    assert list(partial.steps) == ["compile"]
    assert partial.steps["compile"].run_status == StepRunStatus.NOT_EVALUATED
    assert partial.step_executions == 1
    assert not partial.steps["compile"].output_artifacts
    resumed = pipeline.run(history, resume=partial, stop_after="semantic_comparison")
    assert resumed.run_id == partial.run_id
    assert resumed.requirement_artifact_id == partial.requirement_artifact_id
    assert resumed.entry_step == "compile"
    assert "intent_extraction" not in resumed.steps
    with pytest.raises(ValueError, match="entry_step differs"):
        pipeline.run(history, resume=partial, entry_step="intent_extraction")
    with pytest.raises(ValueError, match="outside requested"):
        pipeline.run(history, resume=partial, stop_after="compile",
                     invalidate_from="intent_acceptance")
    with pytest.raises(ValueError, match="outside requested"):
        pipeline.run(history, resume=partial, stop_after="compile",
                     invalidate_from="exploration")


def test_reference_unavailable_is_inconclusive_and_not_authority():
    spec = simple_payment()
    accepted = ArtifactEnvelope("accepted-intent", "v1", "intent_acceptance",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.USER_ACCEPTED_INTENT, {"accepted_spec": spec})
    contract = ArtifactEnvelope("contract-candidate", "core-v1", "compile",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.DETERMINISTIC_COMPILER_CANDIDATE,
                                {"contract": "close", "profile": {
                                    "profile_id": "p", "version": "v1", "compiler_id": "c",
                                    "compiler_version": "v1", "intent_schema_version": "Formalization-IntentSpec-v1"}})

    class _Unavailable:
        def execute(self, request):
            return {"status": "Unavailable", "steps": [], "detail": {"reason": "missing binary"}}

    class _ReviewPolicy:
        def authorize(self, artifact):
            return artifact.payload.get("reviewer_id") == "reviewer"

    expectation = BehaviorExpectation(accepted.artifact_id, "accepted_intent",
                                      ReferenceRequest(None, {}, ()), "Success",
                                      reviewer_id="reviewer")
    expectation_artifact = ArtifactEnvelope(
        "behavior-expectation", "v1", "human_review",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED, AuthorityLevel.NO_AUTHORITY,
        expectation.to_dict())
    from research.orchestration.ports import StepContext
    compared = SemanticComparisonPort(_Unavailable(), _ReviewPolicy()).execute(
        [accepted, contract, expectation_artifact], StepContext("r"))
    assert compared.result.run_status == StepRunStatus.UNAVAILABLE
    assert compared.artifacts[0].payload["verdict"] == "INCONCLUSIVE"
    decision = CompilerAuthorityDecision(
        CompilerAuthorityStatus.AUTHORIZED_FOR_PROFILE, "p", "v1", "c", "v1",
        "Formalization-IntentSpec-v1", "marlowe-core-v1", "pinned", "v1", ("evidence",), "reviewer")
    authority = CompilerAuthorityPort().execute(
        [contract, compared.artifacts[0]],
        StepContext("r", {"compiler_authority_decision": decision,
                           "reference_identity": "pinned"}))
    assert authority.result.semantic_status == "CANDIDATE_ONLY"
    assert authority.result.authority_level == AuthorityLevel.NO_AUTHORITY


def test_authority_rejects_comparison_from_other_contract_even_with_policy():
    from research.orchestration.ports import StepContext

    profile = {"profile_id": "p", "version": "v1", "compiler_id": "c",
               "compiler_version": "v1", "intent_schema_version": "Formalization-IntentSpec-v1"}
    contract = ArtifactEnvelope("contract-candidate", "core-v1", "compile",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.DETERMINISTIC_COMPILER_CANDIDATE,
                                {"contract": "close", "profile": profile})
    comparison = ArtifactEnvelope("reference-comparison", "v1", "semantic_comparison",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY,
                                  {"verdict": "SATISFIED", "contract_artifact_id": "other",
                                   "reference_identity": "pinned"})
    decision = CompilerAuthorityDecision(
        CompilerAuthorityStatus.AUTHORIZED_FOR_PROFILE, "p", "v1", "c", "v1",
        "Formalization-IntentSpec-v1", "marlowe-core-v1", "pinned", "v1", ("evidence",), "reviewer")

    class _Permit:
        def authorize(self, decision, contract, comparison):
            return True

    outcome = CompilerAuthorityPort(_Permit()).execute(
        [contract, comparison], StepContext("r", {
            "compiler_authority_decision": decision, "reference_identity": "pinned"}))
    assert outcome.result.semantic_status == "CANDIDATE_ONLY"


def test_oracle_missing_warning_schema_is_not_pass():
    result = NoWarningsOracle().evaluate({"status": "Success", "trace_id": "t",
                                          "steps": [{"steps": [{"status": "Success"}]}]})
    assert result["verdict"] == "INCONCLUSIVE"


def test_property_registry_requires_evidence_and_is_idempotent():
    registry = PropertyRegistry()
    candidate = PropertyCandidate("p", "statement", "finding", "contract", {"trace": "t"})
    registry.add(candidate, PropertyStatus.CANDIDATE)
    registry.add(candidate, PropertyStatus.CANDIDATE)
    assert len(registry.history("p")) == 1
    with pytest.raises(ValueError):
        registry.add(PropertyCandidate("p2", "statement", "finding", "contract", {}),
                     PropertyStatus.VALIDATED_FOR_SCOPE)


def test_run_identity_differs_from_content_identity():
    pipeline = build_research_pipeline()
    history = [{"version": 1, "messages": ["pay"]}]
    first = pipeline.run(history, stop_after="intent_extraction")
    second = pipeline.run(history, stop_after="intent_extraction")
    assert first.requirement_artifact_id == second.requirement_artifact_id
    assert first.run_id != second.run_id


def test_explicit_reference_domain_preserves_timeout_interval_convention():
    assert classify_interval(0, 49, 50) == IntervalRelation.BEFORE
    assert classify_interval(50, 60, 50) == IntervalRelation.AFTER
    assert classify_interval(0, 50, 50) == IntervalRelation.STRADDLES
    domain = ExplicitTransactionDomain("reviewed-domain", [
        TransactionTemplate("Notify", 0, 49, ({"type": "Notify"},)),
        TransactionTemplate("Timeout", 50, 50, ())])
    transactions = domain.transactions({}, "close")
    assert transactions[0]["inputs"] == [{"type": "Notify"}]
    assert transactions[1]["inputs"] == []
    with pytest.raises(ValueError):
        TransactionTemplate("Timeout", 0, 49, ({"type": "Notify"},))


def test_fake_compiler_interface_requires_complete_typed_mapping():
    spec = simple_payment()
    accepted = ArtifactEnvelope("accepted-intent", "v1", "intent_acceptance",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.USER_ACCEPTED_INTENT, {"accepted_spec": spec})
    profile = SupportedProfile("payment-demo", "v1", "fake-compiler", "v1",
                               "Formalization-IntentSpec-v1",
                               frozenset(item["kind"] for item in spec["claims"]),
                               frozenset(item["scope_type"] for item in spec["behavior_scopes"]),
                               frozenset(item["transition_kind"] for item in spec["behavior_scopes"]
                                         if item["scope_type"] == "transition"), frozenset({"ADA"}))
    observed = []

    def fake_plugin(ir):
        observed.append(ir)
        return CompileResult(CompileStatus.SUPPORTED, "close", ())

    from research.orchestration.ports import StepContext
    port = CompilerPort(ProfileRegistry([profile]), {("payment-demo", "v1"): fake_plugin})
    result = port.execute([accepted], StepContext("r"))
    assert observed and observed[0].claims[0].claim_id == "depositor"
    assert result.result.semantic_status == "AMBIGUOUS_MAPPING"
    assert result.result.run_status == StepRunStatus.UNSUPPORTED
    assert not any(item.artifact_type == "contract-candidate" for item in result.artifacts)


def test_synthetic_ports_connect_full_dag_without_assurance_claims():
    class _InterfaceOnlyPort:
        def __init__(self, step):
            self.step = step

        def execute(self, artifacts, context):
            output = ArtifactEnvelope(f"interface-{self.step}", "v1", self.step,
                                      ImplementationStatus.SCAFFOLDED,
                                      AuthorityLevel.NO_AUTHORITY,
                                      {"prior_artifact_id": artifacts[-1].artifact_id})
            return StepExecution(StepResult(
                self.step, ImplementationStatus.SCAFFOLDED, StepRunStatus.SUCCEEDED,
                semantic_status="SATISFIED" if self.step == "semantic_comparison" else None,
                input_artifacts=[artifacts[-1].artifact_id],
                limitations=["interface smoke only; no domain behavior evaluated"]), [output])

    pipeline = ResearchOrchestrator({step: _InterfaceOnlyPort(step) for step in STEP_ORDER})
    history = [{"version": 1, "messages": ["synthetic"]}]
    run = pipeline.run(history)
    assert list(run.steps) == list(STEP_ORDER)
    assert run.step_executions == len(STEP_ORDER)
    assert len(run.provenance_records) == len(STEP_ORDER)
    serialized = json.loads(json.dumps(run.to_dict()))
    assert serialized["steps"]["deployment"]["run_status"] == "SUCCEEDED"
    assert all(not item["assurance_claims"] for item in serialized["steps"].values())
    resumed = pipeline.run(history, resume=run)
    assert resumed.step_executions == run.step_executions
    assert resumed.provenance_records == run.provenance_records


def test_resume_reuses_only_contiguous_successful_prefix():
    calls = []

    class _CountingPort:
        def __init__(self, step):
            self.step = step

        def execute(self, artifacts, context):
            calls.append(self.step)
            output = ArtifactEnvelope(f"counted-{self.step}", "v1", self.step,
                                      ImplementationStatus.SCAFFOLDED,
                                      AuthorityLevel.NO_AUTHORITY,
                                      {"execution": len(calls)})
            return StepExecution(StepResult(
                self.step, ImplementationStatus.SCAFFOLDED, StepRunStatus.SUCCEEDED,
                input_artifacts=[artifacts[-1].artifact_id]), [output])

    steps = STEP_ORDER[:4]
    pipeline = ResearchOrchestrator({step: _CountingPort(step) for step in steps})
    history = [{"version": 1, "messages": ["synthetic"]}]
    complete = pipeline.run(history, stop_after=steps[-1])
    old_compile = complete.steps["compile"].output_artifacts[0]
    old_comparison = complete.steps["semantic_comparison"].output_artifacts[0]
    missing = deepcopy(complete)
    del missing.steps["compile"]
    resumed = pipeline.run(history, resume=missing, stop_after=steps[-1])
    assert calls == list(steps) + list(steps[2:])
    assert resumed.step_executions == complete.step_executions + 2
    assert old_compile != resumed.steps["compile"].output_artifacts[0]
    assert old_comparison != resumed.steps["semantic_comparison"].output_artifacts[0]
    assert pipeline.store.has(old_compile) and pipeline.store.has(old_comparison)
    assert not any(edge["child_artifact_id"] in {old_compile, old_comparison}
                   for edge in resumed.provenance_records.values())
    forced = pipeline.run(history, resume=resumed, stop_after=steps[-1],
                          invalidate_from="compile")
    assert calls == list(steps) + list(steps[2:]) + list(steps[2:])
    assert forced.step_executions == resumed.step_executions + 2
    assert forced.steps["intent_extraction"].output_artifacts == (
        resumed.steps["intent_extraction"].output_artifacts)


def test_step_execution_budget_blocks_without_calling_next_port():
    class _Port:
        def __init__(self, step):
            self.step = step

        def execute(self, artifacts, context):
            output = ArtifactEnvelope(f"{self.step}-output", "v1", self.step,
                                      ImplementationStatus.SCAFFOLDED,
                                      AuthorityLevel.NO_AUTHORITY, {"ok": True})
            return StepExecution(StepResult(self.step, ImplementationStatus.SCAFFOLDED,
                                              StepRunStatus.SUCCEEDED), [output])

    pipeline = ResearchOrchestrator({"intent_extraction": _Port("intent_extraction"),
                                     "intent_acceptance": _Port("intent_acceptance")})
    run = pipeline.run([{"version": 1, "messages": ["x"]}], stop_after="intent_acceptance",
                       options={"max_step_executions": 1})
    assert run.step_executions == 1
    assert run.steps["intent_acceptance"].run_status == StepRunStatus.BLOCKED


def test_cli_rejects_removed_candidate_route_without_model_call():
    import pytest
    from research.orchestration import cli
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--prompt", "pay", "--research-mode", "candidate"])
    assert exc.value.code == 2
