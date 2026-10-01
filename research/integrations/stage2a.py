"""Frozen Stage 2A records are candidate annotations, never human acceptance."""

from __future__ import annotations

from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.status import AuthorityLevel, ImplementationStatus


class Stage2AFrozenCandidateAdapter:
    def load(self, *, split: str = "development", case_id: str | None = None) -> list[ArtifactEnvelope]:
        from research.stage2b.scoring import FrozenCandidateAdapter

        records: list[dict[str, Any]] = FrozenCandidateAdapter().load(split=split, case_id=case_id)
        return [ArtifactEnvelope("stage2a-candidate-annotation", "stage2a-v1", "stage2a_adapter",
                                 ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                 AuthorityLevel.NO_AUTHORITY, record) for record in records]
