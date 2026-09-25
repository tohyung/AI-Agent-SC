from __future__ import annotations

from pathlib import Path

DATASET = Path(__file__).parent / "dataset" / "cases.jsonl"
RESULTS = Path(__file__).parent / "results"
TYPE_COUNTS = {
    "escrow_2party": 14, "escrow_3party": 10, "swap": 10, "loan": 10,
    "vesting": 10, "milestone": 8, "crowdfunding": 8, "third_party": 10,
    "rental_deposit": 8, "cancellation_fee": 7, "infeasible": 5,
}
DIFFICULTY_COUNTS = {1: 25, 2: 30, 3: 30, 4: 15}
LANGUAGE_COUNTS = {"vi": 60, "en": 40}
INFO_COUNTS = {"complete": 55, "missing": 30, "ambiguous": 10, "infeasible": 5}
WEIGHTS = {"structure": 0.25, "timing": 0.15, "scenarios": 0.60}
DEFAULT_ITERATIONS = 30
DEFAULT_LLM_CALLS = 250
DEFAULT_WALL_SECONDS = 900
DEFAULT_WORKERS = 3
DEFAULT_SEED = 1234
