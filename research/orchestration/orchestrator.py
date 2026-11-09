"""Injected, resumable research pipeline. No concrete step imports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any
from uuid import uuid4

from .artifacts import ArtifactEnvelope, ArtifactStore
from .models import ResearchPipelineRun, StepResult
from .ports import StepContext, StepPort
from .provenance import ProvenanceEdge
from .status import AuthorityLevel, ImplementationStatus, StepRunStatus


STEP_ORDER = (
    "intent_extraction", "intent_acceptance", "compile", "semantic_comparison",
    "compiler_authority", "exploration", "oracle_evaluation", "coverage",
    "adversarial_search", "property_validation", "ledger_validation",
    "testnet", "deployment",
)


class ResearchOrchestrator:
    def __init__(self, ports: Mapping[str, StepPort] | None = None,
                 store: ArtifactStore | None = None,
                 step_order: tuple[str, ...] = STEP_ORDER) -> None:
        if len(step_order) != len(set(step_order)) or not step_order:
            raise ValueError("step_order must contain unique step names")
        unknown = set(ports or {}) - set(step_order)
        if unknown:
            raise ValueError(f"unknown step ports: {sorted(unknown)}")
        self.ports = dict(ports or {})
        self.store = store or ArtifactStore()
        self.step_order = step_order

    def run(self, requirement_history: list[dict[str, Any]], *,
            stop_after: str = "deployment", resume: ResearchPipelineRun | None = None,
            options: dict[str, Any] | None = None,
            external_artifacts: list[ArtifactEnvelope] | None = None,
            invalidate_from: str | None = None,
            entry_step: str | None = None,
            on_step_start: Callable[[str], None] | None = None) -> ResearchPipelineRun:
        step_order = self.step_order
        if stop_after not in step_order:
            raise ValueError(f"unknown stop step: {stop_after}")
        effective_entry = (resume.entry_step if resume is not None else
                           (entry_step if entry_step is not None else "intent_extraction"))
        if entry_step is not None and resume is not None and entry_step != effective_entry:
            raise ValueError("entry_step differs from resumed run")
        if effective_entry not in step_order:
            raise ValueError(f"unknown entry step: {effective_entry}")
        entry_index = step_order.index(effective_entry)
        stop_index = step_order.index(stop_after)
        if stop_index < entry_index:
            raise ValueError("stop_after precedes entry_step")
        if invalidate_from is not None and invalidate_from not in step_order:
            raise ValueError(f"unknown invalidation step: {invalidate_from}")
        if invalidate_from is not None and resume is None:
            raise ValueError("invalidate_from requires a resumed run")
        if invalidate_from is not None and not entry_index <= step_order.index(invalidate_from) <= stop_index:
            raise ValueError("invalidate_from lies outside requested step slice")
        source = ArtifactEnvelope("requirement-history", "v1", "user_input",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY, requirement_history)
        self.store.put(source)
        run_id = resume.run_id if resume is not None else f"research-run:{uuid4()}"
        if resume is not None and resume.requirement_artifact_id != source.artifact_id:
            raise ValueError("resume requirement differs from original run")
        result = (deepcopy(resume) if resume is not None else
                  ResearchPipelineRun(run_id, source.artifact_id, entry_step=effective_entry))
        new_external = any(item.artifact_id not in result.external_artifact_ids
                           for item in external_artifacts or [])
        if resume is not None and new_external and invalidate_from is None:
            raise ValueError("new external artifact on resume requires invalidate_from")
        if resume is not None:
            first_stale = next((index for index, step in enumerate(step_order)
                                if index >= entry_index and (
                                    step not in result.steps
                                    or result.steps[step].run_status != StepRunStatus.SUCCEEDED)),
                               len(step_order))
            if invalidate_from is not None:
                first_stale = min(first_stale, step_order.index(invalidate_from))
            invalidated = set(step_order[first_stale:])
            for step in invalidated:
                result.steps.pop(step, None)
            result.provenance_edges = [edge_id for edge_id in result.provenance_edges
                                       if result.provenance_records[edge_id]["producer_step"]
                                       not in invalidated]
            result.provenance_records = {
                edge_id: record for edge_id, record in result.provenance_records.items()
                if record["producer_step"] not in invalidated}
        artifacts = [source]
        for external in external_artifacts or []:
            self.store.put(external)
            if external.artifact_id not in result.external_artifact_ids:
                result.external_artifact_ids.append(external.artifact_id)
        artifacts.extend(self.store.get(item) for item in result.external_artifact_ids)
        configured = options or {}
        max_executions = configured.get("max_step_executions")
        if max_executions is not None and (not isinstance(max_executions, int)
                                           or isinstance(max_executions, bool)
                                           or max_executions < 1):
            raise ValueError("max_step_executions must be a positive integer")
        context = StepContext(run_id, configured)
        previous: StepResult | None = None
        for step in step_order[entry_index:stop_index + 1]:
            comparison = result.steps.get("semantic_comparison")
            if (step == "exploration" and entry_index <= step_order.index("semantic_comparison")
                    and (comparison is None or comparison.run_status != StepRunStatus.SUCCEEDED
                         or comparison.semantic_status != "SATISFIED")):
                blocked = StepResult(step, ImplementationStatus.SCAFFOLDED,
                                      StepRunStatus.NOT_EVALUATED,
                                      input_artifacts=[item.artifact_id for item in artifacts],
                                      blocked_by=["semantic_comparison"],
                                      diagnostics=["satisfied reference behavior required for exploration"])
                result.steps[step] = blocked
                previous = blocked
                continue
            old = result.steps.get(step)
            if old is not None and old.run_status == StepRunStatus.SUCCEEDED:
                artifacts.extend(self.store.get(item) for item in old.output_artifacts)
                previous = old
                continue
            authority_after_reference_gap = (step == "compiler_authority"
                and previous is not None and previous.step == "semantic_comparison"
                and previous.run_status == StepRunStatus.UNAVAILABLE)
            if (previous is not None and previous.run_status != StepRunStatus.SUCCEEDED
                    and not authority_after_reference_gap):
                blocked = StepResult(step, ImplementationStatus.SCAFFOLDED,
                                      StepRunStatus.NOT_EVALUATED,
                                      input_artifacts=[item.artifact_id for item in artifacts],
                                      blocked_by=[previous.step],
                                      diagnostics=["upstream step did not succeed"])
                result.steps[step] = blocked
                previous = blocked
                continue
            port = self.ports.get(step)
            if port is None:
                missing = StepResult(step, ImplementationStatus.SCAFFOLDED,
                                      StepRunStatus.NOT_EVALUATED,
                                      input_artifacts=[item.artifact_id for item in artifacts],
                                      diagnostics=["step port not configured"])
                result.steps[step] = missing
                previous = missing
                continue
            if max_executions is not None and result.step_executions >= max_executions:
                budget = StepResult(step, ImplementationStatus.SCAFFOLDED,
                                     StepRunStatus.BLOCKED,
                                     input_artifacts=[item.artifact_id for item in artifacts],
                                     diagnostics=["step execution budget exhausted"])
                result.steps[step] = budget
                previous = budget
                continue
            if on_step_start is not None:
                on_step_start(step)
            execution = port.execute(artifacts, context)
            result.step_executions += 1
            if execution.result.step != step:
                raise ValueError(f"port returned result for {execution.result.step}, expected {step}")
            if execution.result.run_status == StepRunStatus.SUCCEEDED and not execution.artifacts:
                raise ValueError(f"successful step {step} returned no artifact")
            for output in execution.artifacts:
                self.store.put(output)
                for input_id in execution.result.input_artifacts:
                    edge = ProvenanceEdge(input_id, output.artifact_id, run_id, step)
                    if edge.edge_id not in result.provenance_edges:
                        result.provenance_edges.append(edge.edge_id)
                        result.provenance_records[edge.edge_id] = edge.to_dict()
            execution.result.output_artifacts = [item.artifact_id for item in execution.artifacts]
            result.execution_history.append(execution.result.to_dict())
            result.steps[step] = execution.result
            artifacts.extend(execution.artifacts)
            previous = execution.result
        return result
