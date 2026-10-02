"""Run the versioned direct-payment canary with one shared live call budget."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

from marlowe_ai_agent.marlowe_agent.models import LLMError
from research.architecture.artifacts import ArtifactEnvelope, canonical_json_v1
from research.architecture.bootstrap import ResearchPipelineWiring, build_research_pipeline
from research.stage2b.live_safety import (EXPERIMENT_VERSION, LivePreflightError,
                                          make_live_budget, require_clean_worktree,
                                          safe_transport_metadata, validate_live_outputs,
                                          write_execution_summary)
from research.stage2b.intent_spec import ACTIVE_STATUSES
from research.stage2b.profile_diagnostic import direct_payment_profile_match
from research.stage2b.shadow_extractor import LegacyReasonerTransport
from research.stage2c.models import IntentDecision, IntentDecisionStatus
from research.stage3.comparison import BehaviorExpectation
from research.stage3.profile_compilers.direct_payment_v1 import DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import PinnedMarloweReference, ReferenceRequest
from research.stage4.domains import ExplicitTransactionDomain, TransactionTemplate
from research.stage4.explorer import ExplorationBounds
from research.stage4.oracles import NoWarningsOracle
from research.architecture.status import AuthorityLevel, ImplementationStatus

ROOT = Path(__file__).resolve().parents[2]
SOURCE_TEXT = "Pay 10 ADA from Alice account to Bob."
HISTORY = [{"version": 1, "messages": [SOURCE_TEXT]}]
REVIEWER_ID = "live-corridor-probe-reviewer"
REFERENCE_IDENTITY = "7b5b1e900ec53a8eb18747992bec73470704dfcb:0.1.0"
ALICE = {"role_token": "Alice"}
BOB = {"role_token": "Bob"}
ADA = {"currency_symbol": "", "token_name": ""}
FUNDED_STATE = {"accounts": [[[ALICE, ADA], 10000000]], "choices": [], "boundValues": [], "minTime": 0}
FINAL_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}
EXPECTED_PAYMENT = {"source_account": ALICE, "payee": {"party": BOB},
                    "token": ADA, "amount": 10000000}


class ExactSpecProbePolicy:
    def __init__(self):
        self.candidate_id = None

    def authorize(self, candidate, decision):
        return (candidate.artifact_id == self.candidate_id
                and decision.reviewer_id == REVIEWER_ID
                and decision.approved_spec is not None
                and canonical_json_v1(decision.approved_spec)
                == canonical_json_v1(candidate.payload["intent_spec"]))


class IndependentExpectationPolicy:
    def __init__(self, scenario, expectation):
        self.scenario = scenario
        self.expectation = expectation

    def authorize(self, artifact):
        return (artifact.artifact_id == self.expectation.artifact_id
                and artifact.payload.get("source_artifact_id") == self.scenario.artifact_id
                and artifact.payload.get("reviewer_id") == REVIEWER_ID)


def independent_expectation():
    scenario_payload = {"scenario_id": "live-direct-payment-funded-alice-v1",
                        "reviewer_id": REVIEWER_ID,
                        "initial_state": deepcopy(FUNDED_STATE),
                        "transactions": [{"interval": {"from": 0, "to": 0}, "inputs": []}],
                        "expected_status": "Success", "expected_final_contract": "close",
                        "expected_final_state": deepcopy(FINAL_STATE),
                        "expected_warnings": [], "expected_payments": [deepcopy(EXPECTED_PAYMENT)]}
    scenario = ArtifactEnvelope("reviewed-scenario", "v1", "live_probe_fixture",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY, scenario_payload)
    expectation = BehaviorExpectation(
        scenario.artifact_id, "reviewed_scenario",
        ReferenceRequest(None, scenario_payload["initial_state"], tuple(scenario_payload["transactions"])),
        "Success", "close", REVIEWER_ID, scenario_payload["expected_final_state"], (),
        tuple(scenario_payload["expected_payments"]))
    external = ArtifactEnvelope("behavior-expectation", "v1", "live_probe_fixture",
                                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                AuthorityLevel.NO_AUTHORITY, expectation.to_dict())
    return scenario, external


def _hash(value):
    return hashlib.sha256(canonical_json_v1(value)).hexdigest() if value is not None else None


def _artifact(pipeline, run, stage, artifact_type):
    for item in run.stages[stage].output_artifacts:
        artifact = pipeline.store.get(item)
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def claim_diagnostic(core):
    expected = {"payment_source_account_owner": "Alice", "payment_recipient": "Bob",
                "amount_lovelace": 10000000, "asset": "ADA"}
    raw_claims = (core or {}).get("claims", [])
    claims = [claim for claim in (raw_claims if isinstance(raw_claims, list) else [])
              if isinstance(claim, dict)
              and claim.get("criticality") == "financial"
              and claim.get("status") in ACTIVE_STATUSES]
    checks = {}
    for kind, value in expected.items():
        matching = [claim for claim in claims if claim.get("kind") == kind]
        checks[kind] = {"exactly_one_expected_value": len(matching) == 1
                        and matching[0].get("value") == value,
                        "claims": [{"value": claim.get("value"), "scope_id": claim.get("scope_id")}
                                   for claim in matching]}
    return {"required_claims": checks,
            "additional_active_critical_claims": [claim for claim in claims
                                                  if claim.get("kind") not in expected]}


def classify_first_failure(record):
    stages = record["stages"]
    extraction = stages.get("intent_extraction", {})
    if extraction.get("semantic_status") == "PROJECTOR_BUG":
        return "PROJECTOR_BUG"
    if extraction.get("run_status") != "SUCCEEDED":
        return "MODEL_ERROR"
    if record["core_validation_errors"]:
        return "CORE_INVALID"
    if record["projection_classification"] == "PROJECTOR_BUG":
        return "PROJECTOR_BUG"
    if stages.get("intent_acceptance", {}).get("semantic_status") != "ACCEPTED":
        return "STAGE2C_UNRESOLVED"
    if record.get("profile_match") != "EXACT_SUPPORTED_PROFILE":
        return "PROFILE_UNSUPPORTED"
    if stages.get("compile", {}).get("semantic_status") != "SUPPORTED":
        return "COMPILER_UNSUPPORTED"
    comparison = stages.get("semantic_comparison", {})
    if comparison.get("semantic_status") == "VIOLATED":
        return "SEMANTIC_VIOLATION"
    if comparison.get("run_status") == "UNAVAILABLE":
        return "REFERENCE_UNAVAILABLE"
    if comparison.get("semantic_status") != "SATISFIED":
        return "REFERENCE_INCONCLUSIVE"
    if stages.get("exploration", {}).get("run_status") != "SUCCEEDED":
        return "EXPLORATION_FAILURE"
    if stages.get("oracle_evaluation", {}).get("run_status") != "SUCCEEDED":
        return "ORACLE_INCONCLUSIVE"
    if record.get("oracle_verdict") != "SATISFIED":
        return "ORACLE_INCONCLUSIVE"
    if stages.get("compiler_authority", {}).get("semantic_status") != "CANDIDATE_ONLY":
        return "REFERENCE_INCONCLUSIVE"
    return "CORRIDOR_PASSED"


def run_repetition(model, binary, repetition, *, reference_executor=None):
    scenario, expectation = independent_expectation()
    reviewer = ExactSpecProbePolicy()
    wiring = ResearchPipelineWiring(
        reviewer_policy=reviewer, profile_registry=ProfileRegistry([DIRECT_PAYMENT_PROFILE]),
        compiler_plugins={("direct-payment", "v1"): compile_direct_payment_v1},
        reference_executor=reference_executor or PinnedMarloweReference(
            binary=binary, hard_timeout_seconds=10.0),
        expectation_policy=IndependentExpectationPolicy(scenario, expectation),
        promotion_policy=None,
        exploration_domain=ExplicitTransactionDomain("live-direct-payment-v1", [
            TransactionTemplate("NoInput", 0, 0, ())]),
        exploration_initial_state=FUNDED_STATE,
        exploration_bounds=ExplorationBounds(max_depth=1, max_traces=1),
        oracles=[NoWarningsOracle()],
    )
    pipeline = build_research_pipeline(model=model, wiring=wiring)
    start = model.request_count()
    first = pipeline.run(HISTORY, stop_after="intent_extraction",
                         external_artifacts=[scenario, expectation])
    run = first
    candidate = _artifact(pipeline, first, "intent_extraction", "intent-candidate")
    record = {"repetition": repetition, "requirement_history": HISTORY,
              "semantic_core": candidate.payload["semantic_core"] if candidate else None,
              "projected_intent_spec": candidate.payload["intent_spec"] if candidate else None,
              "core_validation_errors": candidate.payload["core_validation_errors"] if candidate else [],
              "full_validation_errors": candidate.payload["full_validation_errors"] if candidate else [],
              "projection_classification": candidate.payload["projection_classification"] if candidate else None,
              "logical_extractions": 1, "profile_match": None}
    record["claim_diagnostic"] = claim_diagnostic(record["semantic_core"])
    record["predicted_resolution"] = (record["semantic_core"] or {}).get("predicted_resolution")
    if candidate is None and first.stages["intent_extraction"].semantic_status == "MODEL_ERROR":
        record["model_error"] = first.stages["intent_extraction"].safe_error
    if candidate and not record["core_validation_errors"] and record["projection_classification"] == "PASS":
        review_run = pipeline.run(HISTORY, resume=first, stop_after="intent_acceptance")
        run = review_run
        review = _artifact(pipeline, review_run, "intent_acceptance", "intent-review")
        if review and not review.payload["issues"]:
            reviewer.candidate_id = candidate.artifact_id
            spec = candidate.payload["intent_spec"]
            decision = IntentDecision(IntentDecisionStatus.ACCEPTED, REVIEWER_ID, True, (), spec)
            run = pipeline.run(HISTORY, resume=review_run, stop_after="oracle_evaluation",
                               options={"intent_decision": decision})
            if "compile" in run.stages:
                record["profile_match"] = direct_payment_profile_match(spec)
    record["stages"] = {name: {"run_status": result.run_status.value,
                               "semantic_status": result.semantic_status}
                        for name, result in run.stages.items()}
    oracle = _artifact(pipeline, run, "oracle_evaluation", "oracle-findings") if "oracle_evaluation" in run.stages else None
    findings = oracle.payload.get("findings", []) if oracle else []
    record["oracle_verdict"] = (findings[0].get("verdict") if findings
                                and isinstance(findings[0], dict) else None)
    comparison = _artifact(pipeline, run, "semantic_comparison", "reference-comparison") if "semantic_comparison" in run.stages else None
    reference_status = (comparison.payload.get("reference_result", {}).get("status")
                        if comparison else None)
    record["reference_identity"] = (comparison.payload.get("reference_identity")
                                    if reference_status in {"Success", "TransactionError"} else None)
    record["semantic_core_hash"] = _hash(record["semantic_core"])
    record["projected_spec_hash"] = _hash(record["projected_intent_spec"])
    record["usage"] = model.usage_window(start)
    record["first_failure_class"] = classify_first_failure(record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--max-physical-calls", type=int)
    parser.add_argument("--max-spend-usd")
    parser.add_argument("--per-request-cost-ceiling-usd")
    parser.add_argument("--reference-binary")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.live or args.repetitions != 3:
        parser.error("v1 requires --live and exactly 3 repetitions")
    for field in ("model", "max_physical_calls", "max_spend_usd",
                  "per_request_cost_ceiling_usd", "reference_binary", "output"):
        if not getattr(args, field):
            parser.error(f"--{field.replace('_', '-')} is required")
    try:
        budget = make_live_budget(args.max_physical_calls, 9, args.max_spend_usd,
                                  args.per_request_cost_ceiling_usd)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        validate_live_outputs(args.output, ROOT)
        if not Path(args.reference_binary).is_file():
            raise LivePreflightError("LIVE_EXECUTION_BLOCKED_REFERENCE_BINARY_MISSING")
        code_sha = require_clean_worktree(ROOT)
    except LivePreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        model = LegacyReasonerTransport(args.model)
        model.reasoner.set_call_budget(budget.effective_calls)
    except (LLMError, OSError, ValueError):
        print("Canary preflight failed: model configuration unavailable", file=sys.stderr)
        return 2
    try:
        writer = args.output.open("x", encoding="utf-8")
    except OSError:
        print("Canary preflight failed: raw output cannot be created exclusively", file=sys.stderr)
        return 2
    transport = safe_transport_metadata(model.reasoner)
    print(json.dumps({"experiment_version": EXPERIMENT_VERSION, "code_sha": code_sha,
                      "model": args.model, "repetitions": 3, "budget": budget.to_dict(),
                      "transport": transport}))
    records = []
    budget_interrupted = False
    status = "COMPLETED"
    exit_code = 0
    try:
        for repetition in range(1, 4):
            if model.reasoner.llm_calls >= budget.effective_calls:
                break
            record = run_repetition(model, args.reference_binary, repetition)
            record.update(experiment_version=EXPERIMENT_VERSION, code_sha=code_sha,
                          model=args.model, budget=budget.to_dict())
            writer.write(json.dumps(record, ensure_ascii=False) + "\n")
            writer.flush()
            os.fsync(writer.fileno())
            records.append(record)
            if record.get("model_error", {}).get("code") == "physical_call_budget_exhausted":
                budget_interrupted = True
                break
        if budget_interrupted or len(records) < 3:
            status, exit_code = "BUDGET_EXHAUSTED", 2
    except LLMError:
        status, exit_code = "ENVIRONMENT_BLOCKED", 2
    except Exception:
        status, exit_code = "INFRASTRUCTURE_FAILED", 3
    finally:
        writer.close()
    summary = {"experiment_version": EXPERIMENT_VERSION, "experiment_status": status,
               "code_sha": code_sha, "model": args.model,
               "repetitions_requested": 3, "repetitions_completed": len(records),
               "corridor_passed_count": sum(item["first_failure_class"] == "CORRIDOR_PASSED"
                                            for item in records),
               "first_failure_class_counts": dict(Counter(item["first_failure_class"]
                                                          for item in records)),
               "budget": budget.to_dict(), "transport": transport, "usage": model.usage()}
    try:
        write_execution_summary(args.output, summary)
    except OSError:
        print("Canary summary could not be persisted", file=sys.stderr)
        return 3
    print(json.dumps(summary))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
