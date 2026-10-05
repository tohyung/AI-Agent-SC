"""Local user-facing route through the research pipeline's real gates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.bootstrap import (
    ResearchPipelineWiring,
    build_research_pipeline,
)
from research.architecture.status import (
    AuthorityLevel,
    ImplementationStatus,
    StageRunStatus,
)
from research.final_validation.marlowe_cli import (
    MarloweCliSizeAnalysisPort,
    MarloweCliSizeConfig,
)
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2
from research.stage2c.models import IntentDecision, IntentDecisionStatus
from research.stage3.comparison import SemanticComparisonPort
from research.stage3.reference import PinnedMarloweReference
from research.stage4.explorer import ExplorationBounds, ExplorationPort
from research.stage4.declared_domain import DeclaredActionDomain
from research.stage4.oracles import NoWarningsOracle, OraclePort


@dataclass(frozen=True)
class SessionOptions:
    interactive: bool = False
    max_iterations: int = 8
    max_llm_calls: int = 40
    stop_on_stall: int = 2
    reference_binary: str | None = None
    ledger_config: MarloweCliSizeConfig | None = None
    expectation: dict[str, Any] | None = None
    smt_binary: str | None = None

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 1
            for value in (self.max_iterations, self.max_llm_calls, self.stop_on_stall)
        ):
            raise ValueError("session limits must be positive integers")
        if self.expectation is not None and not self.interactive:
            raise ValueError(
                "reviewed expectation requires interactive mode and reference driver"
            )


class LocalReviewerPolicy:
    """Accept only exact spec consent from this terminal session, not identity proof."""

    def __init__(self, reviewer_id: str) -> None:
        self.reviewer_id = reviewer_id

    def authorize(self, candidate: ArtifactEnvelope, decision: IntentDecision) -> bool:
        return (
            bool(self.reviewer_id)
            and decision.reviewer_id == self.reviewer_id
            and decision.explicit_consent
            and decision.approved_spec == candidate.payload.get("intent_spec")
        )


class LocalExpectationPolicy:
    def __init__(self, reviewer_id: str) -> None:
        self.reviewer_id = reviewer_id

    def authorize(self, artifact: ArtifactEnvelope) -> bool:
        return (
            artifact.artifact_type == "behavior-expectation"
            and artifact.producer_stage == "local_reviewed_expectation"
            and artifact.authority_level == AuthorityLevel.NO_AUTHORITY
            and artifact.payload.get("reviewer_id") == self.reviewer_id
            and artifact.payload.get("explicit_review") is True
        )


def reviewed_expectation(
    accepted: ArtifactEnvelope, payload: dict[str, Any], reviewer_id: str
) -> ArtifactEnvelope:
    """Bind a user-authored scenario to the accepted intent, never to compiler AST."""
    if not isinstance(payload, dict) or set(payload) - {
        "request",
        "expected_status",
        "expected_final_contract",
        "expected_final_state",
        "expected_warnings",
        "expected_payments",
    }:
        raise ValueError("expectation file has unknown fields")
    request = payload.get("request")
    if (
        not isinstance(request, dict)
        or set(request) != {"state", "transactions"}
        or not isinstance(request["state"], dict)
        or not isinstance(request["transactions"], list)
        or not request["transactions"]
        or payload.get("expected_status") not in {"Success", "TransactionError"}
    ):
        raise ValueError("expectation requires independent state and transactions")
    if not any(
        payload.get(key) is not None
        for key in (
            "expected_final_contract",
            "expected_final_state",
            "expected_warnings",
            "expected_payments",
        )
    ):
        raise ValueError("expectation needs an observable beyond status")
    state = request["state"]
    if (
        set(state) != {"accounts", "choices", "boundValues", "minTime"}
        or any(
            not isinstance(state[key], list)
            for key in ("accounts", "choices", "boundValues")
        )
        or type(state["minTime"]) is not int
        or state["minTime"] < 0
    ):
        raise ValueError("expectation state must use the pinned reference state shape")
    for transaction in request["transactions"]:
        if (
            not isinstance(transaction, dict)
            or set(transaction) != {"interval", "inputs"}
            or not isinstance(transaction["inputs"], list)
            or not isinstance(transaction["interval"], dict)
            or set(transaction["interval"]) != {"from", "to"}
            or any(
                type(transaction["interval"][key]) is not int for key in ("from", "to")
            )
            or transaction["interval"]["from"] < 0
            or transaction["interval"]["to"] < transaction["interval"]["from"]
        ):
            raise ValueError(
                "expectation transactions require valid interval and inputs"
            )
    data = {
        **payload,
        "request": {"contract": None, **request},
        "source_artifact_id": accepted.artifact_id,
        "source_kind": "accepted_intent",
        "reviewer_id": reviewer_id,
        "explicit_review": True,
    }
    return ArtifactEnvelope(
        "behavior-expectation",
        "local-v1",
        "local_reviewed_expectation",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED,
        AuthorityLevel.NO_AUTHORITY,
        data,
    )


def _artifact(
    pipeline: Any, run: Any, stage: str, kind: str
) -> ArtifactEnvelope | None:
    record = run.stages.get(stage)
    if record is None:
        return None
    return next(
        (
            item
            for artifact_id in record.output_artifacts
            if (item := pipeline.store.get(artifact_id)).artifact_type == kind
        ),
        None,
    )


def _snapshot(
    pipeline: Any,
    run: Any,
    history: list[dict[str, Any]],
    *,
    status: str,
    stop_reason: str,
    iterations: int,
    model: Any,
    questions: list[str] | None = None,
) -> dict[str, Any]:
    candidate = _artifact(pipeline, run, "intent_extraction", "intent-candidate")
    contract = _artifact(pipeline, run, "compile", "contract-candidate")
    artifact_ids = {
        artifact_id
        for execution in run.execution_history
        for artifact_id in execution["output_artifacts"]
    }
    blocking_stage = next(
        (
            name
            for name in pipeline.stage_order
            if name in run.stages
            and run.stages[name].run_status != StageRunStatus.SUCCEEDED
        ),
        None,
    )
    return {
        "status": status,
        "stop_reason": stop_reason,
        "iterations": iterations,
        "requirement_history": history,
        "questions": questions or [],
        "stages": {name: stage.to_dict() for name, stage in run.stages.items()},
        "run_id": run.run_id,
        "stage_executions": run.stage_executions,
        "execution_history": list(run.execution_history),
        "artifacts": {
            artifact_id: pipeline.store.get(artifact_id).to_dict()
            for artifact_id in sorted(artifact_ids)
        },
        "candidate": candidate.payload if candidate else None,
        "contract_candidate": contract.to_dict() if contract else None,
        "llm_calls": getattr(
            model,
            "llm_calls",
            getattr(getattr(model, "reasoner", None), "llm_calls", None),
        ),
        "model_usage": (
            model.usage_summary() if hasattr(model, "usage_summary") else None
        ),
        "model_call_log": list(getattr(model, "call_log", [])),
        "blocking_stage": blocking_stage,
        "blocking_diagnostics": (
            list(run.stages[blocking_stage].diagnostics) if blocking_stage else []
        ),
        "limitations": [
            "local reviewer identity is self-reported",
            "compiler authority is candidate-only without scoped promotion",
            "ledger size is not transaction submission or deployment",
        ],
    }


def run_session(
    prompt: str,
    model: Any,
    *,
    options: SessionOptions = SessionOptions(),
    ask: Callable[[str], str] | None = None,
    emit: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Repeat extraction after real answers; never fabricate approval or a trace."""
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    if options.interactive and ask is None:
        raise ValueError("interactive session requires an input callback")
    if hasattr(model, "set_call_budget"):
        model.set_call_budget(options.max_llm_calls)
    elif hasattr(model, "reasoner") and hasattr(model.reasoner, "set_call_budget"):
        model.reasoner.set_call_budget(options.max_llm_calls)
    history = [{"version": 1, "messages": [prompt]}]
    seen: dict[str, int] = {}
    reporter = emit or (lambda _message: None)

    def stage_start(stage: str) -> None:
        reporter(f"Đang chạy: {stage}")

    last_pipeline = last_run = None
    for iteration in range(1, options.max_iterations + 1):
        wiring = ResearchPipelineWiring(
            contract_model=model, enable_smt=True, smt_binary=options.smt_binary
        )
        pipeline = build_research_pipeline(model=model, wiring=wiring)
        reporter(f"Lượt {iteration}: Stage 2B đang trích xuất intent")
        run = pipeline.run(
            history,
            stop_after="intent_acceptance",
            options={
                "core_schema_version": CORE_SCHEMA_VERSION_V2,
                "max_core_validation_repairs": 3,
            },
            on_stage_start=stage_start,
        )
        last_pipeline, last_run = pipeline, run
        extraction = run.stages["intent_extraction"]
        if extraction.run_status != StageRunStatus.SUCCEEDED:
            reason = (
                "llm_error"
                if extraction.semantic_status == "MODEL_ERROR"
                else "extraction_failed"
            )
            return _snapshot(
                pipeline,
                run,
                history,
                status="BLOCKED",
                stop_reason=reason,
                iterations=iteration,
                model=model,
            )
        candidate = _artifact(pipeline, run, "intent_extraction", "intent-candidate")
        if candidate is None:
            raise RuntimeError("successful extraction has no candidate")
        payload = candidate.payload
        if payload["core_validation_errors"] or payload["full_validation_errors"]:
            return _snapshot(
                pipeline,
                run,
                history,
                status="BLOCKED",
                stop_reason="invalid_candidate",
                iterations=iteration,
                model=model,
            )
        fingerprint = json.dumps(
            {
                key: value
                for key, value in payload["semantic_core"].items()
                if key != "requirement_history"
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        seen[fingerprint] = seen.get(fingerprint, 0) + 1
        if seen[fingerprint] >= options.stop_on_stall:
            return _snapshot(
                pipeline,
                run,
                history,
                status="BLOCKED",
                stop_reason="stalled",
                iterations=iteration,
                model=model,
            )
        core = payload["semantic_core"]
        questions = list(
            dict.fromkeys(
                item["question"]
                for item in core["required_clarifications"]
                if isinstance(item, dict)
                and isinstance(item.get("question"), str)
                and item["question"].strip()
            )
        )
        if core["predicted_resolution"] != "accepted_interpretation" or questions:
            if not questions:
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="BLOCKED",
                    stop_reason="intent_not_acceptable",
                    iterations=iteration,
                    model=model,
                )
            if not options.interactive:
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="WAITING_USER",
                    stop_reason="clarification_required",
                    iterations=iteration,
                    model=model,
                    questions=questions,
                )
            answers = [ask(question + "\n> ").strip() for question in questions[:4]]
            if any(not answer for answer in answers):
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="WAITING_USER",
                    stop_reason="no_user_input",
                    iterations=iteration,
                    model=model,
                    questions=questions,
                )
            history.append({"version": len(history) + 1, "messages": answers})
            continue
        if not options.interactive:
            return _snapshot(
                pipeline,
                run,
                history,
                status="WAITING_USER",
                stop_reason="explicit_acceptance_required",
                iterations=iteration,
                model=model,
            )
        reporter("Stage 2C: kiểm tra từng claim trong candidate trước khi xác nhận")
        reporter("Diễn giải intent được đề nghị:")
        reporter(json.dumps(payload["intent_spec"], ensure_ascii=False, indent=2))
        for claim in core["claims"]:
            if claim.get("status") not in {"superseded", "unresolved"}:
                reporter(f"  {claim['kind']}={claim['value']} @ {claim['scope_id']}")
        consent = (
            ask("Xác nhận đúng toàn bộ diễn giải trên? Gõ 'dong y' để tiếp tục: ")
            .strip()
            .lower()
        )
        if consent != "dong y":
            correction = ask(
                "Nếu có dữ kiện nghiệp vụ sai, hãy nêu phần cần sửa (để trống để dừng): "
            ).strip()
            if not correction:
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="WAITING_USER",
                    stop_reason="explicit_acceptance_required",
                    iterations=iteration,
                    model=model,
                )
            history.append({"version": len(history) + 1, "messages": [correction]})
            continue
        reviewer_id = ask("Tên người xác nhận (tự khai trong phiên CLI): ").strip()
        if not reviewer_id:
            return _snapshot(
                pipeline,
                run,
                history,
                status="WAITING_USER",
                stop_reason="reviewer_missing",
                iterations=iteration,
                model=model,
            )
        pipeline.ports["intent_acceptance"].reviewer_policy = LocalReviewerPolicy(
            reviewer_id
        )
        decision = IntentDecision(
            IntentDecisionStatus.ACCEPTED,
            reviewer_id,
            True,
            approved_spec=payload["intent_spec"],
        )
        reporter("Stage 2C/3: xác nhận intent và sinh Marlowe candidate")
        run = pipeline.run(
            history,
            resume=run,
            stop_after="smt_verification",
            options={"intent_decision": decision},
            on_stage_start=stage_start,
        )
        last_run = run
        seen_contracts: set[str] = set()
        for generation in range(1, options.max_iterations + 1):
            compile_stage = run.stages["compile"]
            smt_stage = run.stages.get("smt_verification")
            if (
                compile_stage.run_status == StageRunStatus.SUCCEEDED
                and smt_stage is not None
                and smt_stage.run_status == StageRunStatus.SUCCEEDED
            ):
                break
            if compile_stage.semantic_status == "MODEL_ERROR":
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="BLOCKED",
                    stop_reason="llm_error",
                    iterations=iteration,
                    model=model,
                )
            if smt_stage is not None and smt_stage.run_status in {
                StageRunStatus.UNAVAILABLE,
                StageRunStatus.INCONCLUSIVE,
            }:
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="BLOCKED",
                    stop_reason="smt_unavailable_or_inconclusive",
                    iterations=iteration,
                    model=model,
                )
            if generation == options.max_iterations:
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="BLOCKED",
                    stop_reason="max_generation_attempts",
                    iterations=iteration,
                    model=model,
                )
            failed = (
                smt_stage
                if (
                    smt_stage is not None
                    and smt_stage.run_status == StageRunStatus.FAILED
                )
                else compile_stage
            )
            feedback = list(failed.diagnostics)
            report = _artifact(pipeline, run, "smt_verification", "smt-report")
            if report is not None:
                feedback.extend(
                    json.dumps(item, ensure_ascii=False, sort_keys=True)
                    for item in report.payload.get("structured_findings", [])
                )
            fingerprint = json.dumps(feedback, ensure_ascii=False, sort_keys=True)
            if fingerprint in seen_contracts:
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="BLOCKED",
                    stop_reason="generation_stalled",
                    iterations=iteration,
                    model=model,
                )
            seen_contracts.add(fingerprint)
            reporter(f"AST chưa đạt gate; sinh lại candidate (lượt {generation + 1})")
            run = pipeline.run(
                history,
                resume=run,
                stop_after="smt_verification",
                invalidate_from="compile",
                options={"generation_feedback": feedback},
                on_stage_start=stage_start,
            )
            last_run = run
        else:
            raise RuntimeError("generation loop exited without a result")
        if run.stages["compile"].run_status != StageRunStatus.SUCCEEDED:
            return _snapshot(
                pipeline,
                run,
                history,
                status="BLOCKED",
                stop_reason="compile_not_supported",
                iterations=iteration,
                model=model,
            )
        external: list[ArtifactEnvelope] = []
        reference = PinnedMarloweReference(
            binary=options.reference_binary, hard_timeout_seconds=15
        )
        pipeline.ports["semantic_comparison"] = SemanticComparisonPort(
            reference,
            LocalExpectationPolicy(reviewer_id),
            require_intent_alignment=True,
        )
        if options.expectation is not None:
            reporter("Kịch bản hành vi do người dùng cung cấp:")
            reporter(json.dumps(options.expectation, ensure_ascii=False, indent=2))
            confirmed = (
                ask("Xác nhận kịch bản này độc lập và đúng? Gõ 'dong y': ")
                .strip()
                .lower()
            )
            if confirmed != "dong y":
                return _snapshot(
                    pipeline,
                    run,
                    history,
                    status="WAITING_USER",
                    stop_reason="expectation_review_required",
                    iterations=iteration,
                    model=model,
                )
            accepted = _artifact(pipeline, run, "intent_acceptance", "accepted-intent")
            if accepted is None:
                raise RuntimeError("accepted intent artifact missing")
            expectation = reviewed_expectation(
                accepted, options.expectation, reviewer_id
            )
            external.append(expectation)
            transactions = tuple(expectation.payload["request"]["transactions"])
            domain = DeclaredActionDomain(
                "local-user-declared-actions-v1", transactions
            )
            pipeline.ports["exploration"] = ExplorationPort(
                domain,
                reference,
                expectation.payload["request"]["state"],
                ExplorationBounds(max_depth=max(2, len(transactions)), max_traces=8),
            )
            pipeline.ports["oracle_evaluation"] = OraclePort([NoWarningsOracle()])
        if options.ledger_config is not None:
            pipeline.ports["ledger_validation"] = MarloweCliSizeAnalysisPort(
                options.ledger_config
            )
        reporter(
            "Stage 3-5: đối chiếu intent/reference, khám phá và kiểm tra bằng chứng"
        )
        run = pipeline.run(
            history,
            resume=run,
            stop_after="deployment",
            external_artifacts=external,
            invalidate_from="semantic_comparison" if external else None,
            on_stage_start=stage_start,
        )
        last_run = run
        ledger = run.stages.get("ledger_validation")
        checked = (
            ledger is not None
            and ledger.run_status == StageRunStatus.SUCCEEDED
            and ledger.semantic_status == "REACHED_LEDGER_PASS"
        )
        comparison = run.stages.get("semantic_comparison")
        if comparison is not None and comparison.semantic_status == "VIOLATED":
            return _snapshot(
                pipeline,
                run,
                history,
                status="BLOCKED",
                stop_reason="reference_mismatch",
                iterations=iteration,
                model=model,
            )
        if ledger is not None and ledger.semantic_status == "REACHED_LEDGER_FAIL":
            return _snapshot(
                pipeline,
                run,
                history,
                status="BLOCKED",
                stop_reason="ledger_size_failed",
                iterations=iteration,
                model=model,
            )
        return _snapshot(
            pipeline,
            run,
            history,
            status="LEDGER_SIZE_CHECKED" if checked else "CANDIDATE_ONLY",
            stop_reason="candidate_only",
            iterations=iteration,
            model=model,
        )
    if last_pipeline is None or last_run is None:
        raise RuntimeError("session exhausted without a pipeline run")
    return _snapshot(
        last_pipeline,
        last_run,
        history,
        status="BLOCKED",
        stop_reason="max_iterations",
        iterations=options.max_iterations,
        model=model,
    )
