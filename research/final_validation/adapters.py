"""External side effects are absent in architecture v1."""

from __future__ import annotations

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution
from research.architecture.status import ImplementationStatus, StageRunStatus


class DisabledExternalPort:
    def __init__(self, stage: str) -> None:
        if stage not in {"ledger_validation", "testnet", "deployment"}:
            raise ValueError("invalid external stage")
        self.stage = stage

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        return StageExecution(StageResult(
            self.stage, ImplementationStatus.SCAFFOLDED, StageRunStatus.NOT_EVALUATED,
            diagnostics=["external adapter disabled; operator approval and replay guard required"],
            limitations=["no network, wallet, signing or deployment action occurred"]))
