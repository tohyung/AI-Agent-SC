"""Offline capability inventory for the frozen Batch 01 selection.

This is a planning inventory, not a verdict on any extracted candidate. Family
requirements are intentionally coarser than compiler profile acceptance.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json

from research.experiments.online_tuning_batch01 import load_batch


FAMILY_OPERATIONS: dict[str, tuple[str, ...]] = {
    "third_party": ("deposit", "choice", "choice_guard", "pay", "refund", "timeout"),
    "rental_deposit": ("deposit", "choice", "split_pay", "refund", "timeout"),
    "escrow_3party": ("deposit", "choice", "pay", "refund", "timeout"),
    "swap": ("multi_asset_deposit", "pay", "refund", "timeout"),
    "milestone": ("deposit", "choice", "split_pay", "refund", "timeout"),
    "vesting": ("deposit", "timed_pay", "timeout"),
    "escrow_2party": ("deposit", "choice", "pay", "refund", "timeout"),
    "crowdfunding": ("multi_deposit", "threshold", "pay", "refund", "timeout"),
    "infeasible": ("feasibility_review",),
}

# A candidate profile is a search hint only. Exact match still requires a
# validated accepted intent and the profile's full conservation/linkage checks.
PROFILE_HINTS: dict[str, tuple[str, ...]] = {
    "third_party": ("funded-choice/v1",),
    "rental_deposit": ("funded-choice/v1",),
    "escrow_3party": ("funded-choice/v1",),
    "swap": ("funded-swap/v1",),
    "milestone": ("sequential-approval/v1",),
    "vesting": ("linear-time-release/v1",),
    "escrow_2party": ("funded-choice/v1",),
    "crowdfunding": (),
    "infeasible": (),
}

COMPOSITION_REQUIREMENTS = frozenset({
    "deposit", "choice", "choice_guard", "pay", "split_pay", "refund",
    "timeout", "multi_asset_deposit", "timed_pay", "multi_deposit", "threshold",
})


@dataclass(frozen=True)
class CaseCapability:
    case_id: str
    family: str
    source_info_mode: str
    source_missing_facts: tuple[str, ...]
    required_operations: tuple[str, ...]
    profile_hints: tuple[str, ...]
    capability_gaps: tuple[str, ...]
    caveats: tuple[str, ...]
    profile_match_status: str = "NOT_RUN"
    candidate_verdict: str = "NOT_EVALUATED"


def build_matrix() -> tuple[CaseCapability, ...]:
    _, cases = load_batch()
    if len(cases) != 20 or len({case["id"] for case in cases}) != 20:
        raise ValueError("Batch 01 capability inventory requires 20 unique cases")
    if set(case["type"] for case in cases) != set(FAMILY_OPERATIONS):
        raise ValueError("unrecognized or absent contract family")
    rows: list[CaseCapability] = []
    for case in cases:
        family = case["type"]
        missing = tuple(case.get("missing_facts", ()))
        mode = case["info_mode"]
        caveats = ["source metadata is not an acceptance verdict",
                   "exact compiler profile match has not been evaluated"]
        if missing:
            caveats.append("requires user clarification before an accepted intent")
        if mode == "infeasible":
            caveats.append("requires explicit feasibility review, never forced compilation")
        if family == "swap":
            caveats.append("native asset identity must be explicit or labeled simulation-only")
        operations = FAMILY_OPERATIONS[family]
        if set(operations) - COMPOSITION_REQUIREMENTS - {"feasibility_review"}:
            raise ValueError(f"unclassified operation in family {family}")
        gaps = []
        if "feasibility_review" in operations:
            gaps.append("feasibility_review")
        if not PROFILE_HINTS[family] and family != "infeasible":
            gaps.append("accepted-intent compiler profile")
        if family == "crowdfunding":
            gaps.extend(("multi-depositor accounting", "threshold refund coverage"))
        rows.append(CaseCapability(case["id"], family, mode, missing,
                                   operations, PROFILE_HINTS[family], tuple(gaps),
                                   tuple(caveats)))
    return tuple(rows)


def summary() -> dict:
    rows = build_matrix()
    return {
        "case_count": len(rows),
        "family_counts": dict(sorted(Counter(row.family for row in rows).items())),
        "missing_source_fact_cases": sum(bool(row.source_missing_facts) for row in rows),
        "composition_requirements": sorted(COMPOSITION_REQUIREMENTS),
        "candidate_verdicts": {"NOT_EVALUATED": len(rows)},
        "rows": [asdict(row) for row in rows],
    }


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
