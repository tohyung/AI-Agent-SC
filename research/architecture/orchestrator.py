"""Injected, resumable research pipeline. No concrete stage imports."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any
from uuid import uuid4

from .artifacts import ArtifactEnvelope, ArtifactStore
from .models import ResearchPipelineRun, StageResult
from .ports import StageContext, StagePort
from .provenance import ProvenanceEdge
from .status import AuthorityLevel, ImplementationStatus, StageRunStatus


STAGE_ORDER = (
    "intent_extraction", "intent_acceptance", "compile", "semantic_comparison",
    "compiler_authority", "exploration", "oracle_evaluation", "coverage",
    "adversarial_search", "property_validation", "ledger_validation",
    "testnet", "deployment",
)


class ResearchOrchestrator:
    def __init__(self, ports: Mapping[str, StagePort] | None = None,
                 store: ArtifactStore | None = None) -> None:
        unknown = set(ports or {}) - set(STAGE_ORDER)
        if unknown:
            raise ValueError(f"unknown stage ports: {sorted(unknown)}")
        self.ports = dict(ports or {})
        self.store = store or ArtifactStore()

    def run(self, requirement_history: list[dict[str, Any]], *,
            stop_after: str = "deployment", resume: ResearchPipelineRun | None = None,
            options: dict[str, Any] | None = None,
            external_artifacts: list[ArtifactEnvelope] | None = None,
            invalidate_from: str | None = None) -> ResearchPipelineRun:
        if stop_after not in STAGE_ORDER:
            raise ValueError(f"unknown stop stage: {stop_after}")
        if invalidate_from is not None and invalidate_from not in STAGE_ORDER:
            raise ValueError(f"unknown invalidation stage: {invalidate_from}")
        if invalidate_from is not None and resume is None:
            raise ValueError("invalidate_from requires a resumed run")
        source = ArtifactEnvelope("requirement-history", "v1", "user_input",
                                  ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                  AuthorityLevel.NO_AUTHORITY, requirement_history)
        self.store.put(source)
        run_id = resume.run_id if resume is not None else f"research-run:{uuid4()}"
        if resume is not None and resume.requirement_artifact_id != source.artifact_id:
            raise ValueError("resume requirement differs from original run")
        result = deepcopy(resume) if resume is not None else ResearchPipelineRun(run_id, source.artifact_id)
        new_external = any(item.artifact_id not in result.external_artifact_ids
                           for item in external_artifacts or [])
        if resume is not None and new_external and invalidate_from is None:
            raise ValueError("new external artifact on resume requires invalidate_from")
        if resume is not None:
            first_stale = next((index for index, stage in enumerate(STAGE_ORDER)
                                if stage not in result.stages
                                or result.stages[stage].run_status != StageRunStatus.SUCCEEDED),
                               len(STAGE_ORDER))
            if invalidate_from is not None:
                first_stale = min(first_stale, STAGE_ORDER.index(invalidate_from))
            invalidated = set(STAGE_ORDER[first_stale:])
            for stage in invalidated:
                result.stages.pop(stage, None)
            result.provenance_edges = [edge_id for edge_id in result.provenance_edges
                                       if result.provenance_records[edge_id]["producer_stage"]
                                       not in invalidated]
            result.provenance_records = {
                edge_id: record for edge_id, record in result.provenance_records.items()
                if record["producer_stage"] not in invalidated}
        artifacts = [source]
        for external in external_artifacts or []:
            self.store.put(external)
            if external.artifact_id not in result.external_artifact_ids:
                result.external_artifact_ids.append(external.artifact_id)
        artifacts.extend(self.store.get(item) for item in result.external_artifact_ids)
        configured = options or {}
        max_executions = configured.get("max_stage_executions")
        if max_executions is not None and (not isinstance(max_executions, int)
                                           or isinstance(max_executions, bool)
                                           or max_executions < 1):
            raise ValueError("max_stage_executions must be a positive integer")
        context = StageContext(run_id, configured)
        previous: StageResult | None = None
        for stage in STAGE_ORDER[:STAGE_ORDER.index(stop_after) + 1]:
            old = result.stages.get(stage)
            if old is not None and old.run_status == StageRunStatus.SUCCEEDED:
                artifacts.extend(self.store.get(item) for item in old.output_artifacts)
                previous = old
                continue
            authority_after_reference_gap = (stage == "compiler_authority"
                and previous is not None and previous.stage == "semantic_comparison"
                and previous.run_status in {StageRunStatus.INCONCLUSIVE, StageRunStatus.UNAVAILABLE,
                                            StageRunStatus.FAILED, StageRunStatus.BLOCKED})
            if (previous is not None and previous.run_status != StageRunStatus.SUCCEEDED
                    and not authority_after_reference_gap):
                blocked = StageResult(stage, ImplementationStatus.SCAFFOLDED,
                                      StageRunStatus.NOT_EVALUATED,
                                      input_artifacts=[item.artifact_id for item in artifacts],
                                      blocked_by=[previous.stage],
                                      diagnostics=["upstream stage did not succeed"])
                result.stages[stage] = blocked
                previous = blocked
                continue
            port = self.ports.get(stage)
            if port is None:
                missing = StageResult(stage, ImplementationStatus.SCAFFOLDED,
                                      StageRunStatus.NOT_EVALUATED,
                                      input_artifacts=[item.artifact_id for item in artifacts],
                                      diagnostics=["stage port not configured"])
                result.stages[stage] = missing
                previous = missing
                continue
            if max_executions is not None and result.stage_executions >= max_executions:
                budget = StageResult(stage, ImplementationStatus.SCAFFOLDED,
                                     StageRunStatus.BLOCKED,
                                     input_artifacts=[item.artifact_id for item in artifacts],
                                     diagnostics=["stage execution budget exhausted"])
                result.stages[stage] = budget
                previous = budget
                continue
            execution = port.execute(artifacts, context)
            result.stage_executions += 1
            if execution.result.stage != stage:
                raise ValueError(f"port returned result for {execution.result.stage}, expected {stage}")
            if execution.result.run_status == StageRunStatus.SUCCEEDED and not execution.artifacts:
                raise ValueError(f"successful stage {stage} returned no artifact")
            for output in execution.artifacts:
                self.store.put(output)
                for input_id in execution.result.input_artifacts:
                    edge = ProvenanceEdge(input_id, output.artifact_id, run_id, stage)
                    if edge.edge_id not in result.provenance_edges:
                        result.provenance_edges.append(edge.edge_id)
                        result.provenance_records[edge.edge_id] = edge.to_dict()
            execution.result.output_artifacts = [item.artifact_id for item in execution.artifacts]
            result.stages[stage] = execution.result
            artifacts.extend(execution.artifacts)
            previous = execution.result
        return result
