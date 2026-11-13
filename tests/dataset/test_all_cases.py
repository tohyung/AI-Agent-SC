import json

from dataset import all_cases


def test_every_source_still_matches_its_frozen_hash():
    assert all_cases.check_sources() == []


def test_the_combined_file_is_current_and_keeps_each_case_verbatim():
    assert all_cases.main(["--check"]) == 0
    rows = [json.loads(line) for line in all_cases.OUT.read_text(encoding="utf-8").splitlines()]
    counts = {}
    for row in rows:
        counts[row["dataset"]] = counts.get(row["dataset"], 0) + 1
    assert counts == {"v2": 100, "supplement": 24, "v3": 100, "v4": 100, "v5": 100}
    first_v5 = next(row for row in rows if row["dataset"] == "v5")
    source = (all_cases.HERE / "v5" / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0]
    assert first_v5["case"] == json.loads(source) and first_v5["in_report"] is True
