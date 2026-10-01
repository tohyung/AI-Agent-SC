"""Exploratory metric and frozen-candidate adapter tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from research.stage2b import scoring
from research.stage2b.test_intent_spec import simple_payment
from research.stage2b.intent_spec import extract_core_view
from research.stage2b.projector import project_intent_spec


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
    return scoring.score_predictions(predictions, candidates)


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
    assert metric(result, "resolution_exact_match_rate") == {
        "numerator": 0, "denominator": 2, "value": 0.0}


def test_unnecessary_clarification_on_fully_specified_accepted_case():
    result = score({"c1": prediction("clarification_required")}, [candidate()])
    assert metric(result, "unnecessary_clarification_rate") == {
        "numerator": 1, "denominator": 1, "value": 1.0}


def test_conflict_hold_is_not_exact_conflict_classification():
    result = score({"c1": prediction("clarification_required")},
                   [candidate(resolution="conflict_requires_resolution")])
    assert metric(result, "required_clarification_recall") == {
        "numerator": 1, "denominator": 1, "value": 1.0}
    assert metric(result, "resolution_exact_match_rate") == {
        "numerator": 0, "denominator": 1, "value": 0.0}
    assert metric(result, "conflict_classification_recall") == {
        "numerator": 0, "denominator": 1, "value": 0.0}
    assert "exploratory_structural_validity_rate" in result["exploratory_metrics"]

    exact = score({"c1": prediction("conflict_requires_resolution")},
                  [candidate(resolution="conflict_requires_resolution")])
    assert metric(exact, "conflict_classification_recall") == {
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


def test_invalid_prediction_is_scored_and_reported_by_default():
    result = score({"c1": prediction()}, [candidate()])
    assert result["validation_errors"]["c1"]
    assert metric(result, "structural_validity_rate") == {
        "numerator": 0, "denominator": 1, "value": 0.0}
    assert metric(result, "critical_claim_precision")["numerator"] == 1
    with pytest.raises(ValueError, match="invalid prediction"):
        scoring.score_predictions({"c1": prediction()}, [candidate()],
                                  strict_validation=True)


def test_malformed_prediction_remains_in_report_without_crashing():
    result = score({"c1": {"claims": "not a list", "predicted_resolution": []}},
                   [candidate()])
    assert result["validation_errors"]["c1"]
    assert metric(result, "structural_validity_rate")["numerator"] == 0
    assert metric(result, "critical_claim_recall")["denominator"] == 1


def test_unsafe_accepted_assumption_survives_validation_failure_in_metrics():
    assumed = claim()
    assumed.update(status="assumed", evidence=[], assumption_reason="recipient guessed")
    result = score({"c1": prediction(claims=[assumed])}, [candidate()])
    assert any("invalid" in error or "unsafe" in error
               for error in result["validation_errors"]["c1"])
    assert metric(result, "unsafe_assumption_rate") == {
        "numerator": 1, "denominator": 1, "value": 1.0}
    assert metric(result, "structural_validity_rate")["numerator"] == 0


def test_derived_amount_uses_direct_span_not_fake_asset_source():
    spec = simple_payment()
    reference = {"case_id": "derived", "mutation": None, "split": "development",
                 "claims": deepcopy(spec["claims"]),
                 "requirement_history": deepcopy(spec["requirement_history"]),
                 "expected_resolution": "accepted_interpretation", "required_clarifications": []}
    result = score({"derived": spec}, [reference])
    assert result["validation_errors"]["derived"] == []
    assert metric(result, "structural_validity_rate")["numerator"] == 1
    assert metric(result, "provenance_completeness") == {
        "numerator": 5, "denominator": 5, "value": 1.0}

    spec["claims"][3]["derived_from"] = "asset"
    result = score({"derived": spec}, [reference])
    assert any("invalid derived_from" in error for error in result["validation_errors"]["derived"])
    assert metric(result, "provenance_completeness")["numerator"] == 4


def test_native_core_and_projection_metrics_do_not_relabel_historical_runs():
    historical = score({"c1": prediction()}, [candidate()])
    for name in ("core_structural_validity_rate", "projection_completeness"):
        metric_value = metric(historical, name)
        assert metric_value["value"] is None
        assert "historical run predates" in metric_value["reason"]

    source = extract_core_view(simple_payment())
    projection = project_intent_spec(source)
    reference = {"case_id": "native", "mutation": None, "split": "development",
                 "claims": deepcopy(source["claims"]),
                 "requirement_history": deepcopy(source["requirement_history"]),
                 "expected_resolution": source["predicted_resolution"],
                 "required_clarifications": []}
    result = scoring.score_predictions(
        {"native": projection.intent_spec.data}, [reference], run_records={
            "native": {"semantic_core": source,
                       "projection_diagnostics": projection.projection_diagnostics}})
    assert metric(result, "core_structural_validity_rate") == {
        "numerator": 1, "denominator": 1, "value": 1.0}
    assert metric(result, "projection_completeness")["value"] == 1.0
