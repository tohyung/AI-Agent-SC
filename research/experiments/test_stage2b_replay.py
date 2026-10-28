"""Offline replay pairs stored outputs with their history and never calls a model."""

import json

from research.experiments import stage2b_replay
from research.stage3.test_funded_choice_v1 import funded_choice_core


def _write_case(case_dir, outputs, attempts):
    case_dir.mkdir(parents=True)
    with (case_dir / "logical-model-outputs.jsonl").open("w", encoding="utf-8") as writer:
        for recorded, output in outputs:
            writer.write(json.dumps({"request_sha256": recorded, "model": "m",
                                     "output": output, "recorded_at_utc": recorded}) + "\n")
    for number, (recorded, history) in enumerate(attempts, 1):
        (case_dir / f"attempt-{number:03d}.json").write_text(json.dumps({
            "case_id": "c", "attempt": number, "recorded_at_utc": recorded,
            "requirement_history": history, "candidate": None}), encoding="utf-8")


def test_valid_stored_core_replays_as_pass_in_both_modes(tmp_path):
    core = funded_choice_core()
    history = core["requirement_history"]
    _write_case(tmp_path / "case-01", [("2026-01-01T00:00:01", core)],
                [("2026-01-01T00:00:02", history)])
    report = stage2b_replay.replay_runs([tmp_path])
    row = report["cases"]["case-01"]["outputs"][0]
    assert row["paired"] and row["history_versions"] == 1
    assert row["extract"]["classification"] == "PASS"
    assert row["normalized"]["classification"] == "PASS"
    assert report["summary"]["extract"]["cases_latest_output_pass"] == 1


def test_output_is_paired_with_the_attempt_that_recorded_it(tmp_path):
    core = funded_choice_core()
    history = core["requirement_history"]
    longer = history + [{"version": 2, "messages": ["Bob confirms."]}]
    _write_case(tmp_path / "case-01", [("2026-01-01T00:00:05", core)],
                [("2026-01-01T00:00:02", history), ("2026-01-01T00:00:09", longer)])
    row = stage2b_replay.pair_outputs(tmp_path / "case-01")[0]
    assert row["attempt"] == 2
    assert row["history"] == history


def test_invalid_output_is_reported_not_repaired(tmp_path):
    core = funded_choice_core()
    core["claims"][0]["evidence"][0]["span"] = "fabricated span"
    _write_case(tmp_path / "case-01", [("2026-01-01T00:00:01", core)],
                [("2026-01-01T00:00:02", core["requirement_history"])])
    row = stage2b_replay.replay_runs([tmp_path])["cases"]["case-01"]["outputs"][0]
    assert row["extract"]["classification"] == "CORE_INVALID"
    assert "SOURCE_EVIDENCE" in row["extract"]["error_codes"]


def test_repair_patches_and_contracts_are_not_replayed(tmp_path):
    _write_case(tmp_path / "case-01",
                [("2026-01-01T00:00:01", {"evidence_by_claim": {}}),
                 ("2026-01-01T00:00:02", {"contract": "close", "mapping_evidence": []})],
                [("2026-01-01T00:00:03", [{"version": 1, "messages": ["x"]}])])
    assert stage2b_replay.pair_outputs(tmp_path / "case-01") == []


def test_unpaired_output_is_kept_and_counted(tmp_path):
    core = funded_choice_core()
    _write_case(tmp_path / "case-01", [("2026-01-01T00:00:09", core)],
                [("2026-01-01T00:00:02", core["requirement_history"])])
    summary = stage2b_replay.replay_runs([tmp_path])["summary"]
    assert summary["outputs"] == 1 and summary["outputs_paired"] == 0
