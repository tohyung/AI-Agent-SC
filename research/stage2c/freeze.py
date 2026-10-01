"""Versioned accepted-intent snapshot; freeze is not a proof of correctness."""

from __future__ import annotations

from research.architecture.artifacts import ArtifactEnvelope, stable_artifact_id
from research.architecture.status import AuthorityLevel, ImplementationStatus
from .models import AcceptedIntentSpec, IntentFreezeManifest


def freeze_accepted_intent(accepted: AcceptedIntentSpec,
                           answer_ids: tuple[str, ...] = ()) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    package = ArtifactEnvelope("accepted-intent", "v1", "intent_acceptance",
                               ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                               AuthorityLevel.USER_ACCEPTED_INTENT, accepted.to_dict())
    spec = accepted.accepted_spec
    manifest = IntentFreezeManifest(
        package.artifact_id, accepted.candidate_artifact_id,
        str(spec.get("schema_version", "")),
        stable_artifact_id("requirement-history", "v1", spec["requirement_history"]),
        accepted.reviewer_id,
        answer_ids,
    )
    manifest_artifact = ArtifactEnvelope(
        "accepted-intent-manifest", "v1", "intent_acceptance",
        ImplementationStatus.IMPLEMENTED_UNVALIDATED,
        AuthorityLevel.NO_AUTHORITY, manifest.to_dict())
    return package, manifest_artifact
