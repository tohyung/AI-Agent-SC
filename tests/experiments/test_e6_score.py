"""E6 scoring: outcome classes, blind packets, paired statistics."""

from __future__ import annotations

import json
import random

import pytest

from research.experiments import e6_score as e6


@pytest.mark.parametrize("expected, verdict, outcome", [
    ("converge", {"contract": "RIGHT"}, "SUCCESS"),
    ("ask_then_converge", {"contract": "WRONG"}, "WRONG_DELIVERY"),
    ("converge", {"contract": None}, "NO_DELIVERY"),
    ("converge", {"contract": "UNDETERMINED"}, "UNDETERMINED"),
    ("converge_and_decline_extra", {"contract": "RIGHT", "told_unsupported": False}, "RIGHT_NO_NOTICE"),
    ("converge_and_decline_extra", {"contract": "RIGHT", "told_unsupported": True}, "SUCCESS"),
    ("reject_unsupported", {"contract": None, "told_unsupported": True}, "SUCCESS"),
    ("reject_unsupported", {"contract": None, "told_unsupported": False}, "NO_DELIVERY"),
    ("reject_unsupported", {"contract": "RIGHT", "told_unsupported": True}, "WRONG_DELIVERY"),
])
def test_classify_follows_the_protocol_table(expected, verdict, outcome):
    assert e6.classify(expected, verdict) == outcome


def test_mcnemar_exact_matches_known_values():
    assert e6.mcnemar_exact(0, 0) == 1.0
    assert e6.mcnemar_exact(5, 5) == 1.0
    assert e6.mcnemar_exact(0, 6) == pytest.approx(2 / 64)
    assert e6.mcnemar_exact(10, 2) == pytest.approx(0.0386, abs=1e-4)


def test_paired_comparison_reports_delta_ci_and_relative_gain():
    pipeline = [True] * 60 + [False] * 40
    baseline = [True] * 40 + [False] * 60
    result = e6.paired_comparison(pipeline, baseline, rounds=2000)
    assert result["delta"] == pytest.approx(0.2) and result["relative"] == pytest.approx(0.5)
    assert result["pipeline_only"] == 20 and result["baseline_only"] == 0
    low, high = result["delta_ci95"]
    assert 0.1 < low < 0.2 < high < 0.3
    assert e6.conclusion(result) == "pipeline stronger"


def _outcome(arm, contract):
    return {"arm": arm, "contract": contract, "final_message": "", "user_messages": [],
            "cost": {"requests": 3, "prompt_tokens": 10, "completion_tokens": 5, "model_seconds": 1.0,
                     "user_messages": 1, "intent_reviews": 0, "scenarios": 0,
                     "forwarded_errors": 0, "cap_reached": False}}


def test_packets_hide_the_arm_and_scoring_uses_the_key(tmp_path):
    cases = e6.load_cases()
    results = {1: {"pipeline": _outcome("pipeline", "close"), "baseline": _outcome("baseline", None)}}
    e6.write_packets(results, cases, tmp_path, rng=random.Random(7))
    packets = [json.loads(line) for line in (tmp_path / "packets.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(packets) == 2 and all("arm" not in packet for packet in packets)
    key = json.loads((tmp_path / "blind-key.json").read_text(encoding="utf-8"))
    verdicts = {packet["code"]: {"contract": "RIGHT" if packet["contract"] else None}
                for packet in packets}
    report = e6.score(results, cases, verdicts, key)
    assert report["outcomes"]["pipeline"]["SUCCESS"] == 1
    assert report["outcomes"]["baseline"]["NO_DELIVERY"] == 1
    assert report["rq4_totals"]["pipeline"]["requests_per_success"] == 3
    with pytest.raises(FileExistsError):
        e6.write_packets(results, cases, tmp_path, rng=random.Random(7))
    with pytest.raises(ValueError, match="verdict missing"):
        e6.score(results, cases, {}, key)


def test_baseline_outcome_needs_an_ended_session(tmp_path):
    (tmp_path / "session.json").write_text(json.dumps({"status": "awaiting_review"}), encoding="utf-8")
    with pytest.raises(ValueError, match="has not ended"):
        e6.baseline_outcome(tmp_path)
