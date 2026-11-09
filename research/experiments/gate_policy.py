"""E5 policy ladder B0-B4 over the pipeline's own gate implementations.

Each gate returns PASS, REJECT or ABSTAIN; rung Bk combines gates 0..k (any REJECT wins, then
any ABSTAIN, otherwise ACCEPT). See docs/E5-Evidence-Gates.md, section 5.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from research.adapters.smt_gate import SMTVerificationPort
from research.analysis.logic_graph import LogicGraphVerifier
from research.analysis.marlowe_validator import validate_contract
from research.exploration.declared_domain import DeclaredActionDomain
from research.exploration.explorer import ExplorationBounds, explore
from research.exploration.oracles import NoWarningsOracle
from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.ports import StepContext
from research.orchestration.status import AuthorityLevel, ImplementationStatus, StepRunStatus
from research.synthesis.comparison import SemanticComparisonPort

PASS, REJECT, ABSTAIN = "PASS", "REJECT", "ABSTAIN"
ACCEPT = "ACCEPT"
GATES = ("structural", "lint", "smt", "scenarios", "exploration")
RUNGS = ("B0", "B1", "B2", "B3", "B4")
EMPTY_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}
U = ImplementationStatus.IMPLEMENTED_UNVALIDATED


class _Authorize:
    def authorize(self, _: ArtifactEnvelope) -> bool:
        return True


class CountingExecutor:
    """Wraps a reference executor to count calls (RQ4 cost)."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.calls = inner, 0

    def execute(self, request: Any) -> dict[str, Any]:
        self.calls += 1
        return self.inner.execute(request)


@dataclass(frozen=True)
class Expectation:
    """A reviewed scenario: transactions and the behaviour the reviewer confirmed."""

    name: str
    reviewer_id: str
    payload: dict[str, Any]  # request, expected_status, expected_payments, ...


def decide(outcomes: list[str]) -> str:
    if REJECT in outcomes:
        return REJECT
    if ABSTAIN in outcomes:
        return ABSTAIN
    return ACCEPT


def ladder(gates: dict[str, str]) -> dict[str, str]:
    return {rung: decide([gates[name] for name in GATES[:index + 1]])
            for index, rung in enumerate(RUNGS)}


def _scenario_gate(contract: Any, expectations: list[Expectation],
                   executor: Any) -> tuple[str, list[dict[str, Any]]]:
    if not expectations:
        return ABSTAIN, [{"verdict": "NO_REVIEWED_SCENARIO"}]
    candidate = ArtifactEnvelope("contract-candidate", "core-v1", "compile", U,
                                 AuthorityLevel.MODEL_CANDIDATE,
                                 {"contract": contract, "mapping_evidence": []})
    accepted = ArtifactEnvelope("accepted-intent", "Ratification-Simulated-v1",
                                "intent_acceptance", U, AuthorityLevel.NO_AUTHORITY,
                                {"accepted_spec": {}, "simulation_only": True})
    port = SemanticComparisonPort(executor, _Authorize())
    details, outcomes = [], []
    for expectation in expectations:
        source = ArtifactEnvelope("reviewed-scenario", "v1", "review", U,
                                  AuthorityLevel.NO_AUTHORITY,
                                  {"reviewer_id": expectation.reviewer_id,
                                   "scenario": expectation.name})
        artifact = ArtifactEnvelope(
            "behavior-expectation", "E5-ReviewedScenario-v1", "review", U,
            AuthorityLevel.NO_AUTHORITY,
            {**expectation.payload, "source_artifact_id": source.artifact_id,
             "source_kind": "reviewed_scenario", "reviewer_id": expectation.reviewer_id})
        result = port.execute([candidate, accepted, source, artifact],
                              StepContext("e5-scenario")).result
        verdict = result.semantic_status or str(result.run_status)
        details.append({"scenario": expectation.name, "verdict": verdict,
                        "run_status": str(result.run_status),
                        "diagnostics": list(result.diagnostics)})
        outcomes.append(REJECT if result.run_status == StepRunStatus.FAILED
                        else PASS if verdict == "SATISFIED" else ABSTAIN)
    overall = decide(outcomes)
    return (PASS if overall == ACCEPT else overall), details


def _exploration_gate(contract: Any, expectations: list[Expectation],
                      executor: Any) -> tuple[str, dict[str, Any]]:
    declared = tuple(tx for item in expectations
                     for tx in item.payload["request"]["transactions"])
    if not declared:
        return ABSTAIN, {"reason": "no declared actions"}
    longest = max(len(item.payload["request"]["transactions"]) for item in expectations)
    graph = explore(contract, dict(EMPTY_STATE), DeclaredActionDomain("E5-Declared-v1", declared),
                    executor, ExplorationBounds(max_depth=max(2, longest), max_traces=8))
    oracle = NoWarningsOracle()
    verdicts = [oracle.evaluate(trace)["verdict"] for trace in graph["traces"]]
    detail = {"traces": len(verdicts), "verdicts": verdicts, "truncated": graph.get("truncated")}
    if "VIOLATED" in verdicts:
        return REJECT, detail
    if "SATISFIED" not in verdicts:
        return ABSTAIN, detail
    return PASS, detail


def evaluate(contract: Any, expectations: list[Expectation], *, executor: Any,
             smt_binary: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    counting = CountingExecutor(executor)
    gates = dict.fromkeys(GATES, "NOT_RUN")
    detail: dict[str, Any] = {}
    errors = validate_contract(contract)
    if errors:
        gates = dict.fromkeys(GATES, REJECT)
        detail["structural"] = errors[:5]
        return {"gates": gates, "decisions": ladder(gates), "detail": detail,
                "reference_calls": 0, "smt_calls": 0,
                "seconds": round(time.perf_counter() - started, 3)}
    gates["structural"] = PASS
    lint = LogicGraphVerifier().lint(contract)
    gates["lint"] = REJECT if lint.errors else PASS
    detail["lint"] = {"errors": lint.errors[:5], "warnings": lint.warnings[:5]}
    smt_calls = 0
    if lint.errors:
        gates["smt"] = REJECT
        detail["smt"] = "not run: lint failed"
    else:
        candidate = ArtifactEnvelope("contract-candidate", "core-v1", "compile", U,
                                     AuthorityLevel.MODEL_CANDIDATE, {"contract": contract})
        result = SMTVerificationPort(binary=smt_binary).execute(
            [candidate], StepContext("e5-smt")).result
        smt_calls = 1
        gates["smt"] = (PASS if result.semantic_status == "NO_MODELED_WARNINGS"
                        else REJECT if result.semantic_status in {"SMT_COUNTEREXAMPLE", "LINT_FAILED"}
                        else ABSTAIN)
        detail["smt"] = {"status": result.semantic_status, "diagnostics": list(result.diagnostics)[:5]}
    gates["scenarios"], detail["scenarios"] = _scenario_gate(contract, expectations, counting)
    gates["exploration"], detail["exploration"] = _exploration_gate(contract, expectations, counting)
    return {"gates": gates, "decisions": ladder(gates), "detail": detail,
            "reference_calls": counting.calls, "smt_calls": smt_calls,
            "seconds": round(time.perf_counter() - started, 3)}
