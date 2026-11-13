import json

from dataset import rq2_variants


def test_every_variant_regenerates_from_its_reference_and_counts_match_the_results():
    assert rq2_variants.check() == []


def test_the_oracle_decisions_give_the_published_rates():
    rows = [json.loads(line) for line in rq2_variants.OUT.read_text(encoding="utf-8").splitlines()]
    test = [row for row in rows if row["split"] == "test"]
    wrong = [row for row in test if row["label"] == "WRONG"]
    right = [row for row in test if row["label"] == "RIGHT"]
    accepted_wrong = sum(row["decisions"]["Oracle"] == "ACCEPT" for row in wrong)
    accepted_right = sum(row["decisions"]["Oracle"] == "ACCEPT" for row in right)
    rejected_right = sum(row["decisions"]["Oracle"] == "REJECT" for row in right)
    assert round(accepted_wrong / len(wrong), 3) == 0.171
    assert round(accepted_right / len(right), 3) == 0.936
    assert round(rejected_right / len(right), 3) == 0.011
