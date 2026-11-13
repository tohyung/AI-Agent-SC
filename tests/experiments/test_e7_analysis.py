import json
import random

import pytest

from research.experiments import e7_analysis as analysis


def _case(index, expected="converge"):
    return {"id": f"v5-{index}", "family": "escrow", "language": "vi", "info_mode": "complete",
            "expected_behavior": expected, "prompt": "p", "fact_sheet": ["f"]}


def _result(contract, history=(), requests=3):
    return {"contract": contract, "end": "x", "final_message": "status: X\nstop_reason: y\nhello",
            "history": [list(item) for item in history],
            "cost": {"requests": requests, "prompt_tokens": 10, "completion_tokens": 5,
                     "model_seconds": 1.0, "user_messages": 2, "scenarios": 1}}


def _machine(verdicts):
    return {index: {"verdict": verdict, "problems": [] if verdict == "RIGHT" else ["late"]}
            for index, verdict in verdicts.items()}


def test_arm_verdict_takes_the_machine_right_and_the_judged_review():
    assert analysis.arm_verdict("converge", "RIGHT", None) == {"contract": "RIGHT",
                                                               "told_unsupported": False}
    assert analysis.arm_verdict("converge", "REVIEW", {"contract": "WRONG"})["contract"] == "WRONG"
    assert analysis.arm_verdict("converge", "NONE", None)["contract"] is None
    with pytest.raises(ValueError):
        analysis.arm_verdict("converge", "REVIEW", None)
    with pytest.raises(ValueError):
        analysis.arm_verdict("reject_unsupported", "NONE", {})


def test_packets_ask_only_what_must_be_judged():
    assert analysis.packet_questions("converge", "RIGHT") == []
    assert analysis.packet_questions("converge", "REVIEW") == ["contract"]
    assert analysis.packet_questions("reject_unsupported", "NONE") == ["told_unsupported"]
    assert analysis.packet_questions("converge_and_decline_extra", "REVIEW") == [
        "contract", "told_unsupported"]


def test_a_delivered_contract_needs_a_machine_verdict():
    with pytest.raises(ValueError):
        analysis._machine_verdict({}, 1, {"close": True})
    assert analysis._machine_verdict({1: {"verdict": "RIGHT"}}, 1, None) == "NONE"


def test_packets_are_blind_and_strip_status_lines(tmp_path):
    cases = [_case(1), _case(2, "reject_unsupported")]
    results = {1: {"pipeline": _result("C", [("assistant", "[RESULT: shown] summary"), ("you", "no")]),
                   "baseline": _result("C")},
               2: {"pipeline": _result(None), "baseline": _result(None)}}
    machine = {"pipeline": {"1m": _machine({1: "REVIEW"})}, "baseline": {"1m": _machine({1: "RIGHT"})}}
    count = analysis.write_packets(results, cases, machine, tmp_path, rng=random.Random(1))
    packets = [json.loads(line) for line in (tmp_path / "packets.jsonl").read_text().splitlines()]
    assert count == 3  # pipeline 1 (contract), and both arms of case 2 (told)
    assert all("arm" not in packet for packet in packets)
    first = next(packet for packet in packets if packet["case_index"] == 1)
    assert first["final_message"] == "hello"
    assert first["conversation"][0]["text"] == "summary"
    key = json.loads((tmp_path / "blind-key.json").read_text())
    assert sorted(entry["arm"] for entry in key.values()) == ["baseline", "pipeline", "pipeline"]


def _score(tmp_path, cases, results, machine, judged):
    key = {f"k{index}{arm}": {"case_index": index, "arm": arm} for (index, arm) in judged}
    verdicts = {f"k{index}{arm}": value for (index, arm), value in judged.items()}
    return analysis.score(results, cases, machine, verdicts, key, tmp_path / "p", tmp_path / "b")


def test_score_pairs_outcomes_and_builds_the_sensitivity_table(tmp_path):
    cases = [_case(1), _case(2), _case(3)]
    results = {index: {"pipeline": _result("C"), "baseline": _result("C" if index < 3 else None)}
               for index in (1, 2, 3)}
    machine = {"pipeline": {"1m": _machine({1: "RIGHT", 2: "REVIEW", 3: "REVIEW"}),
                            "1h": _machine({1: "RIGHT", 2: "RIGHT", 3: "REVIEW"})},
               "baseline": {"1m": _machine({1: "REVIEW", 2: "RIGHT", 3: "RIGHT"}),
                            "1h": _machine({1: "REVIEW", 2: "RIGHT", 3: "RIGHT"})}}
    judged = {(2, "pipeline"): {"contract": "WRONG"}, (3, "pipeline"): {"contract": "RIGHT"},
              (1, "baseline"): {"contract": "WRONG"}}
    report = _score(tmp_path, cases, results, machine, judged)
    assert report["outcomes"]["pipeline"]["SUCCESS"] == 2
    assert report["outcomes"]["baseline"]["SUCCESS"] == 1
    assert report["outcomes"]["baseline"]["NO_DELIVERY"] == 1
    assert report["rq3_success"]["pipeline_only"] == 2
    assert report["rq3_success"]["baseline_only"] == 1
    assert report["time_sensitivity"]["1h"] == {"pipeline": 3, "baseline": 1}
    assert report["rq4"]["pipeline"]["total"]["requests"] == 9
    assert report["rq4"]["pipeline"]["requests_per_success"] == 4.5


def test_undetermined_cases_are_left_out_of_the_pairing(tmp_path):
    cases = [_case(1), _case(2)]
    results = {index: {"pipeline": _result("C"), "baseline": _result("C")} for index in (1, 2)}
    machine = {arm: {"1m": _machine({1: "REVIEW", 2: "RIGHT"})} for arm in analysis.ARMS}
    judged = {(1, "pipeline"): {"contract": "UNDETERMINED"}, (1, "baseline"): {"contract": "RIGHT"}}
    report = _score(tmp_path, cases, results, machine, judged)
    assert report["cases_paired"] == 1 and report["undetermined"] == 1


def test_simuser_report_counts_rejects_fallbacks_objections_and_invalid_turns(tmp_path):
    case_dir = tmp_path / "case-001"
    case_dir.mkdir()
    (case_dir / "simuser.json").write_text(json.dumps({
        "history": [["assistant", "[RESULT: x] s"], ["you", "wrong"], ["assistant", "[RESULT: x] t"],
                    ["you", "(you accepted)"]],
        "turns": [{"problems": [], "retry": 0}, {"problems": ["n"], "retry": 0},
                  {"problems": ["n"], "retry": 1}, {"problems": ["n"], "retry": 2}],
        "user_messages": 1}), encoding="utf-8")
    (case_dir / "subagent-audit.jsonl").write_text(
        json.dumps({"problems": ["0 handbacks"]}) + "\n" + json.dumps({"problems": []}) + "\n",
        encoding="utf-8")
    report = analysis.simuser_report(tmp_path, [1])
    assert report == {"turns": 1, "rejected_by_checker": 3, "fallbacks": 1, "objections": 1,
                      "invalid_subagent_turns": 1}


def test_a_pipeline_case_that_did_not_deliver_has_no_contract(tmp_path, monkeypatch):
    case_dir = tmp_path / "case-001"
    case_dir.mkdir()
    (case_dir / "final.json").write_text(json.dumps({"end": "scenario_not_delivered:a",
                                                     "delivered": False}), encoding="utf-8")
    monkeypatch.setattr(analysis, "pipeline_outcome",
                        lambda path: {"contract": {"when": []}, "final_message": ""})
    monkeypatch.setattr(analysis, "pipeline_requests", lambda path: 4)
    result = analysis.pipeline_result(case_dir)
    assert result["contract"] is None and result["cost"]["requests"] == 4
