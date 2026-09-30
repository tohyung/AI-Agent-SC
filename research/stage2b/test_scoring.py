"""Exploratory metric and frozen-candidate adapter tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from research.stage2b import scoring


HISTORY = [{"version": 1, "messages": ["Bob nhận 2 ADA; Alice nhận 2 ADA."]}]


def claim(value="Bob", scope="decision-1:approve", claim_id="prediction-1"):
    return {
        "claim_id": claim_id, "kind": "payment_recipient", "value": value,
        "scope_id": scope, "criticality": "financial", "status": "explicit",
        "evidence": [{"requirement_version": 1, "message_index": 0,
                      "span": f"{value} nhận 2 ADA", "relation": "supports"}],
    }


def candidate(case_id="c1", resolution="accepted_interpretation"):
    return {"case_id": case_id, "mutation": None, "split": "development",
            "claims": [claim(claim_id="candidate-id")],
            "requirement_history": deepcopy(HISTORY),
            "expected_resolution": resolution,
            "required_clarifications": ["Ai nhận tiền?"]
            if resolution in {"clarification_required", "conflict_requires_resolution"} else []}


def prediction(resolution="accepted_interpretation", claims=None):
    return {"predicted_resolution": resolution, "claims": [claim()] if claims is None else claims,
            "requirement_history": deepcopy(HISTORY),
            "required_clarifications": ["Ai nhận tiền?"]
            if resolution in {"clarification_required", "conflict_requires_resolution"} else [],
            "unscored_observations": []}


def metric(result, name):
    return result["exploratory_metrics"][f"exploratory_{name}"]


def score(predictions, candidates):
    # Metric fixtures are deliberately minimal; production calls validate by default.
    return scoring.score_predictions(predictions, candidates, validate_predictions=False)


def test_exact_claim_match_ignores_claim_id_and_reports_exploratory_labels():
    result = score({"c1": prediction()}, [candidate()])
    assert metric(result, "critical_claim_precision") == {
        "numerator": 1, "denominator": 1, "value": 1.0}
    assert metric(result, "critical_claim_recall") == {
        "numerator": 1, "denominator": 1, "value": 1.0}
    assert result["evaluation_status"] == "exploratory"
    assert result["reference_status"] == "frozen_candidate_annotations"
    assert result["human_review_status"] == "draft"
    assert "accuracy" not in result


@pytest.mark.parametrize("replacement", [claim("Alice"), claim(scope="approve-branch")])
def test_wrong_recipient_or_exact_scope_mismatch_produces_fp_and_fn(replacement):
    result = score({"c1": prediction(claims=[replacement])}, [candidate()])
    assert metric(result, "critical_claim_precision")["numerator"] == 0
    assert metric(result, "critical_claim_precision")["denominator"] == 1
    assert metric(result, "critical_claim_recall")["numerator"] == 0
    assert metric(result, "critical_claim_recall")["denominator"] == 1


def test_critical_claim_recall_denominator_only_accepted_candidates():
    cases = [candidate("accepted"), candidate("needs-user", "clarification_required")]
    preds = {"accepted": prediction(), "needs-user": prediction("clarification_required")}
    result = score(preds, cases)
    assert metric(result, "critical_claim_recall")["denominator"] == 1
    assert metric(result, "required_clarification_recall")["denominator"] == 1


def test_missing_prediction_does_not_disappear_from_candidate_denominators():
    cases = [candidate("accepted"), candidate("clarify", "clarification_required")]
    result = score({}, cases)
    assert metric(result, "critical_claim_recall") == {
        "numerator": 0, "denominator": 1, "value": 0.0}
    assert metric(result, "required_clarification_recall") == {
        "numerator": 0, "denominator": 1, "value": 0.0}
    assert metric(result, "unsafe_freeze_rate")["denominator"] == 1
    assert result["missing_predictions"] == ["accepted", "clarify"]


def test_unnecessary_clarification_on_fully_specified_accepted_case():
    result = score({"c1": prediction("clarification_required")}, [candidate()])
    assert metric(result, "unnecessary_clarification_rate") == {
        "numerator": 1, "denominator": 1, "value": 1.0}


def test_unsafe_freeze_and_unsafe_acceptance_have_distinct_denominators():
    cases = [candidate("clarify", "clarification_required"),
             candidate("conflict", "conflict_requires_resolution"),
             candidate("unsupported", "unsupported_for_current_study"),
             candidate("accepted")]
    preds = {case["case_id"]: prediction() for case in cases}
    result = score(preds, cases)
    assert metric(result, "unsafe_freeze_rate") == {
        "numerator": 2, "denominator": 2, "value": 1.0}
    assert metric(result, "unsafe_acceptance_rate") == {
        "numerator": 3, "denominator": 4, "value": 0.75}
    assert result["simulated_freeze_decision_only"] is True


def test_assumed_claim_is_unsafe_even_with_valid_looking_evidence():
    assumed = claim()
    assumed.update(status="assumed", assumption_reason="not actually confirmed")
    result = score({"c1": prediction(claims=[assumed])}, [candidate()])
    assert metric(result, "unsafe_assumption_rate")["numerator"] == 1
    assert metric(result, "provenance_completeness")["numerator"] == 0


def test_unscored_observation_never_becomes_matched_claim():
    pred = prediction(claims=[])
    pred["unscored_observations"] = [{"observation_id": "o1", "text": "Bob nhận 2 ADA",
                                       "reason": "outside_stage2b_v1_claim_taxonomy"}]
    result = score({"c1": pred}, [candidate()])
    assert metric(result, "critical_claim_precision")["denominator"] == 0
    assert metric(result, "critical_claim_recall")["numerator"] == 0


def test_frozen_adapter_uses_only_canonical_and_defaults_to_development():
    adapter = scoring.FrozenCandidateAdapter()
    development = adapter.load()
    assert len(development) == 10
    assert all(case["split"] == "development" and case["mutation"] is None
               for case in development)
    assert len(adapter.load(all_canonical=True)) == 20
    with pytest.raises(ValueError, match="canonical case_id not found"):
        adapter.load(case_id="pay-d1-m-recipient")


def test_freeze_verification_is_required_before_scoring(monkeypatch):
    def fail(_):
        raise ValueError("freeze mismatch")

    monkeypatch.setattr(scoring.verify_freeze, "verify_freeze", fail)
    with pytest.raises(ValueError, match="freeze mismatch"):
        score({"c1": prediction()}, [candidate()])
    with pytest.raises(ValueError, match="freeze mismatch"):
        scoring.FrozenCandidateAdapter().load()


def test_mutations_cannot_be_scored_as_independent_intent_examples():
    mutated = candidate()
    mutated["mutation"] = {"parent_case_id": "parent"}
    with pytest.raises(ValueError, match="mutation is not an independent"):
        score({"c1": prediction()}, [mutated])


def test_scoring_rejects_invalid_prediction_by_default():
    with pytest.raises(ValueError, match="invalid prediction"):
        scoring.score_predictions({"c1": prediction()}, [candidate()])
