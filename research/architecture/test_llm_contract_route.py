"""Offline checks for the model-generated contract route and its assurance gates."""

from copy import deepcopy

from research.architecture.cli_runner import (LocalExpectationPolicy, SessionOptions,
                                              _reference_counterexample_feedback,
                                              reviewed_expectation, run_session)
from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.bootstrap import ResearchPipelineWiring, build_research_pipeline
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.integrations.smt_gate import SMTVerificationPort
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2
from research.stage2b.projector import project_intent_spec
from research.stage3.intent_alignment import check_intent_alignment
from research.stage3.llm_generator import LLMContractGeneratorPort
from research.stage3.comparison import SemanticComparisonPort
from research.stage3.test_funded_choice_v1 import funded_choice_core
from research.stage4.declared_domain import DeclaredActionDomain
from research.stage4.oracles import NoWarningsOracle, OraclePort
from research.integrations.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT


class ContractModel:
    def __init__(self):
        self.requests = []

    def generate(self, system, user):
        self.requests.append((system, user))
        return {"contract": "close", "mapping_evidence": [],
                "reasoning_narrative": "Ứng viên cần được kiểm chứng."}


def _accepted():
    spec = project_intent_spec(funded_choice_core()).intent_spec.to_dict()
    return ArtifactEnvelope(
        "accepted-intent", "v1", "intent_acceptance",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED,
        AuthorityLevel.USER_ACCEPTED_INTENT,
        {"accepted_spec": spec, "simulation_only": False},
    )


def test_model_generator_uses_accepted_spec_and_keeps_candidate_authority():
    model = ContractModel()
    accepted = _accepted()
    execution = LLMContractGeneratorPort(model).execute(
        [accepted], StageContext("run", {"generation_feedback": ["deadline mismatch"]}))
    assert execution.result.run_status == StageRunStatus.SUCCEEDED
    assert execution.artifacts[0].authority_level == AuthorityLevel.MODEL_CANDIDATE
    assert execution.artifacts[0].payload["source_intent_id"] == accepted.artifact_id
    assert "deadline mismatch" in model.requests[0][1]
    assert 'never {"constant": 1}' in model.requests[0][0]
    assert 'Never wrap that Contract in {"pay": {...}}' in model.requests[0][0]


def test_reference_feedback_explains_timeout_path_without_rewriting_scenario():
    report = {
        "expectation": {"expected_status": "Success", "expected_payments": [
            {"amount": 17500000, "payee": {"party": {"role_token": "Nga"}}}]},
        "bound_transactions": [
            {"interval": {"from": 10, "to": 10}, "inputs": [{"type": "Deposit"}]},
            {"interval": {"from": 20, "to": 20}, "inputs": []}],
        "reference_result": {"status": "Success", "steps": [
            {"status": "Success", "contract": {"when": [{"case": {
                "notify_if": True}, "then": "close"}], "timeout": 20,
                "timeout_continuation": "close"}, "payments": []},
            {"status": "Success", "payments": [{"amount": 35000000,
                "payee": {"party": {"role_token": "Huy"}}}]}]},
    }
    feedback = _reference_counterexample_feedback(report)
    assert any("interval.from=20 reaches When.timeout=20" in item for item in feedback)
    assert any("timeout_continuation" in item and "not behind Notify" in item
               for item in feedback)
    assert any("35000000" in item and "Huy" in item for item in feedback)
    assert any("17500000" in item and "Nga" in item for item in feedback)


def test_model_generator_rejects_noncanonical_token_when_intent_only_uses_ada():
    class WrongAdaModel:
        def generate(self, _system, _user):
            return {"contract": {
                "pay": 1, "from_account": {"role_token": "Alice"},
                "to": {"party": {"role_token": "Bob"}},
                "token": {"currency_symbol": "", "token_name": "ADA"},
                "then": "close",
            }, "mapping_evidence": []}

    outcome = LLMContractGeneratorPort(WrongAdaModel()).execute(
        [_accepted()], StageContext("run"))
    assert outcome.result.run_status == StageRunStatus.FAILED
    assert any("accepted intent has only ADA" in item
               for item in outcome.result.diagnostics)


def test_roleplay_intent_requires_explicit_option_and_keeps_no_user_authority():
    source = _accepted()
    simulated = ArtifactEnvelope(
        "accepted-intent", "simulated-v1", "intent_acceptance",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED, AuthorityLevel.NO_AUTHORITY,
        {"accepted_spec": source.payload["accepted_spec"], "simulation_only": True},
    )
    model = ContractModel()
    port = LLMContractGeneratorPort(model)
    blocked = port.execute([simulated], StageContext("run"))
    assert blocked.result.run_status == StageRunStatus.BLOCKED
    assert model.requests == []
    outcome = port.execute([simulated], StageContext(
        "run", {"allow_simulated_intent": True}))
    assert outcome.result.run_status == StageRunStatus.SUCCEEDED
    assert outcome.artifacts[0].authority_level == AuthorityLevel.MODEL_CANDIDATE
    assert outcome.artifacts[0].payload["simulation_only"] is True


def test_smt_runs_before_reference_comparison_and_is_not_a_ledger_verdict():
    model = ContractModel()
    pipeline = build_research_pipeline(model=model, wiring=ResearchPipelineWiring(
        contract_model=model, enable_smt=True,
        smt_analyzer=lambda _contract: {
            "status": "Valid", "warnings": [], "analysis_notes": [],
            "meta": {"upstream_commit": UPSTREAM_COMMIT,
                     "driver_version": DRIVER_VERSION},
        },
    ))
    assert pipeline.stage_order.index("compile") < pipeline.stage_order.index("smt_verification")
    assert pipeline.stage_order.index("smt_verification") < pipeline.stage_order.index(
        "semantic_comparison")
    generated = LLMContractGeneratorPort(model).execute([_accepted()], StageContext("run"))
    result = pipeline.ports["smt_verification"].execute(generated.artifacts, StageContext("run"))
    assert result.result.run_status == StageRunStatus.SUCCEEDED
    assert result.result.semantic_status == "NO_MODELED_WARNINGS"
    assert result.artifacts[0].authority_level == AuthorityLevel.NO_AUTHORITY


def test_smt_unavailable_is_not_reclassified_as_business_failure():
    generated = LLMContractGeneratorPort(ContractModel()).execute(
        [_accepted()], StageContext("run"))

    def unavailable(_contract):
        raise OSError("driver missing")

    outcome = SMTVerificationPort(unavailable).execute(generated.artifacts, StageContext("run"))
    assert outcome.result.run_status == StageRunStatus.UNAVAILABLE
    assert outcome.result.semantic_status == "SMT_UNAVAILABLE"


def test_scope_path_existence_cannot_prove_intent_alignment():
    spec = project_intent_spec(funded_choice_core()).intent_spec.to_dict()
    mapping = [{"source_kind": "scope", "source_id": scope["scope_id"],
                "ast_path": "root"} for scope in spec["behavior_scopes"]]
    outcome = check_intent_alignment(spec, "close", mapping)
    assert outcome["verdict"] == "INCONCLUSIVE"
    assert any(item["reason"] == "ast_path_exists_only" for item in outcome["checks"])


def test_deadline_mapping_uses_verified_when_case_parent_without_claiming_scope_proof():
    contract = {"when": [{"case": {"deposits": 1}, "then": {
        "when": [{"case": {"for_choice": {"choice_name": "q"}}, "then": "close"}],
        "timeout": 20, "timeout_continuation": "close"}}],
        "timeout": 10, "timeout_continuation": "close"}
    spec = {"claims": [
        {"claim_id": "deposit-time", "kind": "deposit_deadline_ms",
         "value": 10, "scope_id": "deposit"},
        {"claim_id": "choice-time", "kind": "choice_deadline_ms",
         "value": 20, "scope_id": "choice"}],
        "behavior_scopes": [
            {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
            {"scope_id": "choice", "scope_type": "transition", "transition_kind": "choice"},
            {"scope_id": "choice-timeout", "scope_type": "timeout", "decision_id": "choice"}]}
    evidence = [
        {"source_kind": "scope", "source_id": "deposit", "ast_path": "$.when[0]"},
        {"source_kind": "scope", "source_id": "choice",
         "ast_path": "$.when[0].then.when[0]"},
        {"source_kind": "scope", "source_id": "choice-timeout",
         "ast_path": "$.when[0].then.when[0].timeout_continuation"},
        {"source_kind": "claim", "source_id": "deposit-time",
         "ast_path": "$.when[0].timeout"},
        {"source_kind": "claim", "source_id": "choice-time",
         "ast_path": "$.when[0].then.when[0].timeout"},
    ]
    outcome = check_intent_alignment(spec, contract, evidence)
    checks = {item["source_id"]: item for item in outcome["checks"]}
    assert checks["deposit-time"]["status"] == "SATISFIED"
    assert checks["deposit-time"]["ast_path"] == "$.timeout"
    assert checks["choice-time"]["status"] == "SATISFIED"
    assert checks["choice-time"]["ast_path"] == "$.when[0].then.timeout"
    assert checks["choice-timeout"]["status"] == "INCONCLUSIVE"
    assert outcome["verdict"] == "INCONCLUSIVE"

    wrong_action = deepcopy(contract)
    wrong_action["when"][0]["case"] = {"for_choice": {"choice_name": "other"}}
    wrong = check_intent_alignment(spec, wrong_action, evidence)
    assert next(item for item in wrong["checks"]
                if item["source_id"] == "deposit-time")["reason"] == "ast_path_missing"
    assert wrong["verdict"] == "INCONCLUSIVE"

    wrong_time = deepcopy(contract)
    wrong_time["timeout"] = 11
    wrong = check_intent_alignment(spec, wrong_time, evidence)
    assert next(item for item in wrong["checks"]
                if item["source_id"] == "deposit-time")["status"] == "VIOLATED"


def test_interactive_route_repairs_ast_then_runs_smt_without_fabricating_reference(monkeypatch):
    core = funded_choice_core()

    class TwoPhaseModel:
        def __init__(self):
            self.generation_inputs = []
            self.llm_calls = 0

        def set_call_budget(self, _limit):
            pass

        def generate(self, system, user):
            self.llm_calls += 1
            if "Generate one canonical Marlowe" not in system:
                return deepcopy(core)
            self.generation_inputs.append(user)
            return {"contract": {"unexpected": "AST"} if len(self.generation_inputs) == 1
                    else "close", "mapping_evidence": []}

    monkeypatch.setattr("research.integrations.smt_gate.analyze", lambda *_args, **_kwargs: {
        "status": "Valid", "warnings": [], "analysis_notes": [],
        "meta": {"upstream_commit": UPSTREAM_COMMIT, "driver_version": DRIVER_VERSION},
    })
    answers = iter(["dong y", "Tester"])
    model = TwoPhaseModel()
    result = run_session(core["requirement_history"][0]["messages"][0], model,
                         options=SessionOptions(
                             interactive=True, core_schema_version=CORE_SCHEMA_VERSION_V2),
                         ask=lambda _question: next(answers))
    assert len(model.generation_inputs) == 2
    assert "generation_feedback" in model.generation_inputs[1]
    assert result["stages"]["smt_verification"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["semantic_comparison"]["run_status"] == "INCONCLUSIVE"
    assert result["blocking_stage"] == "semantic_comparison"
    assert result["stages"]["ledger_validation"]["run_status"] != "SUCCEEDED"
    assert result["status"] == "CANDIDATE_ONLY"
    assert [item["stage"] for item in result["execution_history"]].count("compile") == 2
    assert result["stage_executions"] == len(result["execution_history"])
    assert result["contract_candidate"]["artifact_id"] in result["artifacts"]


def test_bad_model_mapping_does_not_regenerate_an_unchanged_contract(monkeypatch):
    core = funded_choice_core()
    first_claim_id = core["claims"][0]["claim_id"]

    class TwoContractModel:
        def __init__(self):
            self.generation_inputs = []

        def generate(self, system, user):
            if "Generate one canonical Marlowe" not in system:
                return deepcopy(core)
            self.generation_inputs.append(user)
            evidence = ([{"source_kind": "claim", "source_id": first_claim_id,
                          "ast_path": "$.missing"}]
                        if len(self.generation_inputs) == 1 else [])
            return {"contract": "close", "mapping_evidence": evidence}

    monkeypatch.setattr("research.integrations.smt_gate.analyze", lambda *_a, **_k: {
        "status": "Valid", "warnings": [], "analysis_notes": [],
        "meta": {"upstream_commit": UPSTREAM_COMMIT, "driver_version": DRIVER_VERSION},
    })
    answers = iter(["dong y", "Tester"])
    model = TwoContractModel()
    result = run_session(
        core["requirement_history"][0]["messages"][0], model,
        options=SessionOptions(interactive=True, core_schema_version=CORE_SCHEMA_VERSION_V2),
        ask=lambda _question: next(answers))
    assert len(model.generation_inputs) == 1
    assert result["stages"]["smt_verification"]["run_status"] == "SUCCEEDED"
    assert result["stages"]["semantic_comparison"]["run_status"] == "INCONCLUSIVE"
    assert [item["stage"] for item in result["execution_history"]].count("compile") == 1


def test_reviewed_reference_trace_runs_despite_unproven_scope_alignment():
    accepted = _accepted()
    candidate = LLMContractGeneratorPort(ContractModel()).execute(
        [accepted], StageContext("run")).artifacts[0]
    wrong_mapping = [{
        "source_kind": "claim", "source_id": accepted.payload["accepted_spec"]["claims"][0]["claim_id"],
        "ast_path": "$.missing",
    }]
    candidate = ArtifactEnvelope(
        candidate.artifact_type, candidate.schema_version, candidate.producer_stage,
        candidate.implementation_status, candidate.authority_level,
        {**candidate.payload, "mapping_evidence": wrong_mapping})
    expectation = reviewed_expectation(accepted, {
        "request": {
            "state": {"accounts": [], "choices": [], "boundValues": [], "minTime": 0},
            "transactions": [{"interval": {"from": 0, "to": 0}, "inputs": []}],
        },
        "expected_status": "Success", "expected_final_contract": "close",
    }, "Tester")

    class FakeReference:
        def execute(self, _request):
            return {"status": "Success", "final_contract": "close",
                    "meta": {"upstream_commit": "test", "reference_driver_version": "test"}}

    outcome = SemanticComparisonPort(
        FakeReference(), LocalExpectationPolicy("Tester"),
        require_intent_alignment=True,
    ).execute([accepted, candidate, expectation], StageContext("run"))
    assert outcome.result.run_status == StageRunStatus.SUCCEEDED
    assert outcome.result.semantic_status == "SATISFIED"
    assert outcome.artifacts[0].payload["intent_alignment"]["verdict"] == "INCONCLUSIVE"
    assert "claim/scope alignment remains inconclusive" in outcome.result.limitations


def test_stage4_domain_does_not_invent_payment_or_timeout_transactions():
    domain = DeclaredActionDomain("reviewed", ())
    pay = {"pay": 5, "from_account": {"role_token": "Alice"},
           "to": {"party": {"role_token": "Bob"}},
           "token": {"currency_symbol": "", "token_name": ""},
           "then": "close"}
    when = {"when": [], "timeout": 100, "timeout_continuation": "close"}
    assert domain.transactions({}, pay) == []
    assert domain.transactions({}, when) == []
    declared = {"interval": {"from": 100, "to": 100}, "inputs": []}
    assert DeclaredActionDomain("reviewed", (declared,)).transactions({}, when) == [declared]


def test_contract_model_failure_is_llm_error_not_business_clarification():
    core = funded_choice_core()

    class FailingContractModel:
        def generate(self, system, _user):
            if "Generate one canonical Marlowe" in system:
                raise RuntimeError("provider unavailable")
            return deepcopy(core)

    answers = iter(["dong y", "Tester"])
    result = run_session(core["requirement_history"][0]["messages"][0],
                         FailingContractModel(),
                         options=SessionOptions(
                             interactive=True, core_schema_version=CORE_SCHEMA_VERSION_V2),
                         ask=lambda _question: next(answers))
    assert result["status"] == "BLOCKED"
    assert result["stop_reason"] == "llm_error"
    assert result["blocking_stage"] == "compile"
    assert result["questions"] == []
    assert result["stages"]["smt_verification"]["run_status"] == "NOT_EVALUATED"


def test_empty_stage4_oracle_evidence_is_inconclusive():
    graph = ArtifactEnvelope("exploration-graph", "v1", "exploration",
                             ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                             AuthorityLevel.NO_AUTHORITY, {"traces": []})
    outcome = OraclePort([NoWarningsOracle()]).execute([graph], StageContext("run"))
    assert outcome.result.run_status == StageRunStatus.INCONCLUSIVE
    assert outcome.result.semantic_status == "NO_EVALUATED_ORACLE"
