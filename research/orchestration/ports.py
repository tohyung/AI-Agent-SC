"""Ports are defined above concrete steps to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .artifacts import ArtifactEnvelope
from .models import StepResult


@dataclass
class StepContext:
    run_id: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepExecution:
    result: StepResult
    artifacts: list[ArtifactEnvelope] = field(default_factory=list)


class StepPort(Protocol):
    def execute(self, artifacts: list[ArtifactEnvelope], context: StepContext) -> StepExecution: ...


def latest_artifact(artifacts: list[ArtifactEnvelope], artifact_type: str) -> ArtifactEnvelope | None:
    return next((item for item in reversed(artifacts) if item.artifact_type == artifact_type), None)
