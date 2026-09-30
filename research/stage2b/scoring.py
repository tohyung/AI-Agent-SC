"""Exploratory exact-match agreement against frozen Stage 2A candidates."""

from __future__ import annotations

from collections import Counter
import json
from typing import Any

from research.stage2a import foundation, verify_freeze
from research.stage2b.intent_spec import (
    ACTIVE_STATUSES, valid_supporting_evidence, validate_intent_spec,
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


def _active_critical(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [claim for claim in claims if claim.get("criticality") == "financial"
            and claim.get("status") in ACTIVE_STATUSES]


def _key(claim: dict[str, Any]) -> tuple[str, str, str, int | None]:
    versions = [item["requirement_version"] for item in claim.get("evidence", [])
                if isinstance(item, dict) and isinstance(item.get("requirement_version"), int)]
    return (claim.get("kind"), json.dumps(claim.get("value"), ensure_ascii=False, sort_keys=True),
            claim.get("scope_id"), max(versions) if versions else None)


def _messages(history: list[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {(version["version"], index): message
            for version in history for index, message in enumerate(version["messages"])}


def _has_provenance(claim: dict[str, Any], claims: dict[str, dict[str, Any]],
                    messages: dict[tuple[int, int], str]) -> bool:
    if not valid_supporting_evidence(claim, messages):
        return False
    if claim.get("status") == "derived":
        source = claims.get(claim.get("derived_from"))
        return bool(claim.get("normalization_basis") and source and
                    source.get("status") in {"explicit", "user_confirmed"} and
                    valid_supporting_evidence(source, messages))
    return True


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def score_predictions(predictions: dict[str, dict[str, Any]],
                      candidates: list[dict[str, Any]], *,
                      validate_predictions: bool = True) -> dict[str, Any]:
    aggregate = verify_freeze.verify_freeze(MANIFEST)
    if any(record.get("mutation") is not None for record in candidates):
        raise ValueError("mutation is not an independent intent observation")
    if validate_predictions:
        for candidate in candidates:
            prediction = predictions.get(candidate["case_id"])
            if prediction is not None:
                errors = validate_intent_spec(
                    prediction, expected_history=candidate["requirement_history"])
                if errors:
                    raise ValueError(f"invalid prediction for {candidate['case_id']}: " +
                                     "; ".join(errors))
    counts = {name: [0, 0] for name in METRIC_NAMES}
    missing = []
    for candidate in candidates:
        case_id = candidate["case_id"]
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
        prediction = predictions.get(case_id)
        if prediction is None:
            missing.append(case_id)
            continue
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
        pred_by_id = {claim.get("claim_id"): claim for claim in prediction.get("claims", [])}
        messages = _messages(prediction.get("requirement_history", []))
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
            clarification[0] += int(predicted_resolution in {
                "clarification_required", "conflict_requires_resolution"})
            freeze = counts["exploratory_unsafe_freeze_rate"]
            freeze[0] += int(predicted_resolution == "accepted_interpretation")
        if candidate_resolution == "accepted_interpretation" and not candidate["required_clarifications"]:
            unnecessary = counts["exploratory_unnecessary_clarification_rate"]
            unnecessary[0] += int(predicted_resolution in {
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
        "exploratory_metrics": {name: _ratio(*counts[name]) for name in METRIC_NAMES},
    }
