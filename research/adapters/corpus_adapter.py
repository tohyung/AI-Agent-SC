"""Frozen Corpus records are candidate annotations, never human acceptance."""

from __future__ import annotations

from typing import Any

from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.status import AuthorityLevel, ImplementationStatus


class CorpusFrozenCandidateAdapter:
    def load(self, *, split: str = "development", case_id: str | None = None) -> list[ArtifactEnvelope]:
        from research.formalization.scoring import FrozenCandidateAdapter

        records: list[dict[str, Any]] = FrozenCandidateAdapter().load(split=split, case_id=case_id)
        return [ArtifactEnvelope("corpus-candidate-annotation", "Corpus-v1", "corpus_adapter",
                                 ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                 AuthorityLevel.NO_AUTHORITY, record) for record in records]
