"""The inventory must not turn dataset metadata into a fabricated pass."""

from collections import Counter

from research.experiments.batch_capability_matrix import (FAMILY_OPERATIONS,
                                                          build_matrix, summary)
from research.experiments.online_tuning_batch01 import load_batch


def test_capability_matrix_covers_exactly_frozen_twenty_in_order():
    manifest, cases = load_batch()
    rows = build_matrix()
    assert [row.case_id for row in rows] == manifest["case_ids"]
    assert [row.case_id for row in rows] == [case["id"] for case in cases]
    assert len(set(row.case_id for row in rows)) == 20
    assert set(row.family for row in rows) == set(FAMILY_OPERATIONS)
    assert Counter(row.family for row in rows) == Counter(case["type"] for case in cases)


def test_matrix_keeps_source_gaps_separate_from_compiler_and_candidate_verdict():
    rows = {row.case_id: row for row in build_matrix()}
    missing = rows["vi-rental_deposit-L4-001"]
    assert missing.source_missing_facts == ("deadline",)
    assert missing.candidate_verdict == "NOT_EVALUATED"
    assert "requires user clarification before an accepted intent" in missing.caveats
    swap = rows["vi-swap-L2-001"]
    assert swap.source_info_mode == "complete"
    assert swap.candidate_verdict == "NOT_EVALUATED"
    assert "native asset identity must be explicit or labeled simulation-only" in swap.caveats
    infeasible = rows["vi-infeasible-L2-001"]
    assert infeasible.profile_hints == ()
    assert "feasibility_review" in infeasible.capability_gaps
    crowdfunding = rows["vi-crowdfunding-L3-001"]
    assert "accepted-intent compiler profile" in crowdfunding.capability_gaps
    assert summary()["candidate_verdicts"] == {"NOT_EVALUATED": 20}
