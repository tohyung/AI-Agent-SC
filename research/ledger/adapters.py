"""External side effects are absent in architecture v1."""

from __future__ import annotations

from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.models import StepResult
from research.orchestration.ports import StepContext, StepExecution
from research.orchestration.status import ImplementationStatus, StepRunStatus


class DisabledExternalPort:
    def __init__(self, step: str) -> None:
        if step not in {"ledger_validation", "testnet", "deployment"}:
            raise ValueError("invalid external step")
        self.step = step

    def execute(self, artifacts: list[ArtifactEnvelope], context: StepContext) -> StepExecution:
        return StepExecution(StepResult(
            self.step, ImplementationStatus.SCAFFOLDED, StepRunStatus.NOT_EVALUATED,
            diagnostics=["external adapter disabled; operator approval and replay guard required"],
            limitations=["no network, wallet, signing or deployment action occurred"]))
