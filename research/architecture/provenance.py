"""Lineage is separate from content identity: identical content may recur."""

from __future__ import annotations

from dataclasses import dataclass

from .artifacts import stable_artifact_id


@dataclass(frozen=True)
class ProvenanceEdge:
    parent_artifact_id: str
    child_artifact_id: str
    run_id: str
    producer_stage: str

    @property
    def edge_id(self) -> str:
        return stable_artifact_id("provenance-edge", "v1", self.to_dict())

    def to_dict(self) -> dict[str, str]:
        return {"parent_artifact_id": self.parent_artifact_id,
                "child_artifact_id": self.child_artifact_id,
                "run_id": self.run_id, "producer_stage": self.producer_stage}
