"""Exploratory exact-match agreement against frozen Stage 2A candidates."""

from __future__ import annotations

from collections import Counter
import json
from typing import Any

from research.stage2a import foundation, verify_freeze
from research.stage2b.intent_spec import (
    ACTIVE_STATUSES, valid_derived_source, valid_supporting_evidence,
    validate_intent_spec,
)


CORPUS_VERSION = "stage2a-v1"
MANIFEST = foundation.ROOT / "freeze/stage2a-v1.manifest.json"
METRIC_NAMES = (
    "exploratory_critical_claim_precision",
    "exploratory_critical_claim_recall",
    "exploratory_unsafe_assumption_rate",
    "exploratory_required_clarification_recall",
    "exploratory_unnecessary_clarification_rate",
    "exploratory_unsafe_freeze_rate",
    "exploratory_unsafe_acceptance_rate",
    "exploratory_provenance_completeness",
    "exploratory_structural_validity_rate",
)


class FrozenCandidateAdapter:
    def load(self, *, split: str = "development", all_canonical: bool = False,
             case_id: str | None = None) -> list[dict[str, Any]]:
        verify_freeze.verify_freeze(MANIFEST)
        records = foundation.load_corpus()
        errors = foundation.validate(records)
        if errors:
            raise ValueError("frozen candidate corpus invalid: " + "; ".join(errors))
        canonical = [record for record in records if record["mutation"] is None]
        if case_id is not None:
            selected = [record for record in canonical if record["case_id"] == case_id]
            if not selected:
                raise ValueError(f"canonical case_id not found: {case_id}")
            return selected
        if all_canonical:
            return canonical
        if split not in foundation.SPLITS:
            raise ValueError(f"invalid split: {split}")
        return [record for record in canonical if record["split"] == split]


def _active_critical(claims: Any) -> list[dict[str, Any]]:
    if not isinstance(claims, list):
        return []
    return [claim for claim in claims if isinstance(claim, dict)
            and claim.get("criticality") == "financial"
            and isinstance(claim.get("status"), str)
            and claim["status"] in ACTIVE_STATUSES]


def _key(claim: dict[str, Any]) -> tuple[str, str, str, int | None]:
    evidence = claim.get("evidence")
    versions = [item["requirement_version"] for item in
                (evidence if isinstance(evidence, list) else [])
                if isinstance(item, dict) and isinstance(item.get("requirement_version"), int)]
    kind = claim.get("kind")
    scope_id = claim.get("scope_id")
    return (kind if isinstance(kind, str) else repr(kind),
            json.dumps(claim.get("value"), ensure_ascii=False, sort_keys=True),
            scope_id if isinstance(scope_id, str) else repr(scope_id),
            max(versions) if versions else None)


def _messages(history: list[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {(version["version"], index): message
            for version in history for index, message in enumerate(version["messages"])}


def _has_provenance(claim: dict[str, Any], claims: dict[str, dict[str, Any]],
                    messages: dict[tuple[int, int], str]) -> bool:
    if not valid_supporting_evidence(claim, messages):
        return False
    if claim.get("status") == "derived":
        if not claim.get("normalization_basis"):
            return False
        source_id = claim.get("derived_from")
        if source_id is not None:
            source = claims.get(source_id) if isinstance(source_id, str) else None
            return bool(valid_derived_source(claim, source) and
                        valid_supporting_evidence(source, messages))
    return True


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def score_predictions(predictions: dict[str, dict[str, Any]],
                      candidates: list[dict[str, Any]], *,
                      strict_validation: bool = False) -> dict[str, Any]:
    aggregate = verify_freeze.verify_freeze(MANIFEST)
    if any(record.get("mutation") is not None for record in candidates):
        raise ValueError("mutation is not an independent intent observation")
    counts = {name: [0, 0] for name in METRIC_NAMES}
    missing = []
    validation_errors: dict[str, list[str]] = {}
    for candidate in candidates:
        case_id = candidate["case_id"]
        raw_prediction = predictions.get(case_id)
        errors = (["prediction missing"] if raw_prediction is None else
                  validate_intent_spec(raw_prediction,
                                       expected_history=candidate["requirement_history"]))
        validation_errors[case_id] = errors
        validity = counts["exploratory_structural_validity_rate"]
        validity[0] += int(not errors)
        validity[1] += 1
        if errors and strict_validation:
            raise ValueError(f"invalid prediction for {case_id}: " + "; ".join(errors))
        candidate_claims = _active_critical(candidate["claims"])
        candidate_resolution = candidate["expected_resolution"]
        if candidate_resolution == "accepted_interpretation":
            counts["exploratory_critical_claim_recall"][1] += len(candidate_claims)
            if not candidate["required_clarifications"]:
                counts["exploratory_unnecessary_clarification_rate"][1] += 1
        requires_resolution = candidate_resolution in {
            "clarification_required", "conflict_requires_resolution"}
        if requires_resolution:
            counts["exploratory_required_clarification_recall"][1] += 1
            counts["exploratory_unsafe_freeze_rate"][1] += 1
        if raw_prediction is None:
            missing.append(case_id)
            continue
        prediction = raw_prediction if isinstance(raw_prediction, dict) else {}
        predicted_claims = _active_critical(prediction.get("claims", []))
        predicted_keys = Counter(map(_key, predicted_claims))
        candidate_keys = Counter(map(_key, candidate_claims))
        matched = sum((predicted_keys & candidate_keys).values())
        precision = counts["exploratory_critical_claim_precision"]
        precision[0] += matched
        precision[1] += len(predicted_claims)
        if candidate["expected_resolution"] == "accepted_interpretation":
            recall = counts["exploratory_critical_claim_recall"]
            recall[0] += matched

        predicted_resolution = prediction.get("predicted_resolution")
        pred_by_id = {claim.get("claim_id"): claim for claim in
                      (prediction.get("claims") if isinstance(prediction.get("claims"), list) else [])
                      if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)}
        messages = _messages(candidate["requirement_history"])
        unsupported = any(claim.get("status") == "assumed" or
                          not _has_provenance(claim, pred_by_id, messages)
                          for claim in predicted_claims)
        if predicted_resolution == "accepted_interpretation":
            metric = counts["exploratory_unsafe_assumption_rate"]
            metric[0] += int(unsupported)
            metric[1] += 1
            acceptance = counts["exploratory_unsafe_acceptance_rate"]
            acceptance[0] += int(candidate_resolution != "accepted_interpretation")
            acceptance[1] += 1

        if requires_resolution:
            clarification = counts["exploratory_required_clarification_recall"]
            clarification[0] += int(isinstance(predicted_resolution, str) and predicted_resolution in {
                "clarification_required", "conflict_requires_resolution"})
            freeze = counts["exploratory_unsafe_freeze_rate"]
            freeze[0] += int(predicted_resolution == "accepted_interpretation")
        if candidate_resolution == "accepted_interpretation" and not candidate["required_clarifications"]:
            unnecessary = counts["exploratory_unnecessary_clarification_rate"]
            unnecessary[0] += int(isinstance(predicted_resolution, str) and predicted_resolution in {
                "clarification_required", "conflict_requires_resolution"} or
                bool(prediction.get("required_clarifications")))
        provenance = counts["exploratory_provenance_completeness"]
        provenance[0] += sum(_has_provenance(claim, pred_by_id, messages)
                             for claim in predicted_claims)
        provenance[1] += len(predicted_claims)
    return {
        "evaluation_status": "exploratory",
        "reference_status": "frozen_candidate_annotations",
        "source_corpus_version": CORPUS_VERSION,
        "source_corpus_aggregate_sha256": aggregate,
        "human_review_status": "draft",
        "simulated_freeze_decision_only": True,
        "scored_cases": len(candidates) - len(missing),
        "missing_predictions": missing,
        "validation_errors": validation_errors,
        "exploratory_metrics": {name: _ratio(*counts[name]) for name in METRIC_NAMES},
    }
