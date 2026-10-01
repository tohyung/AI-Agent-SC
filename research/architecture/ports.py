"""Ports are defined above concrete stages to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .artifacts import ArtifactEnvelope
from .models import StageResult


@dataclass
class StageContext:
    run_id: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageExecution:
    result: StageResult
    artifacts: list[ArtifactEnvelope] = field(default_factory=list)


class StagePort(Protocol):
    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution: ...


def latest_artifact(artifacts: list[ArtifactEnvelope], artifact_type: str) -> ArtifactEnvelope | None:
    return next((item for item in reversed(artifacts) if item.artifact_type == artifact_type), None)
