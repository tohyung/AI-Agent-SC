"""E6 automatic simulated user: the same fixed replies for both arms (docs/E6-Protocol.md, section 3).

The arm asks (any question, any number of questions in one turn):
  1st time: the whole fact sheet of the case, or a fixed "no more details" line when it is empty;
  2nd time: a fixed "no other information" line;
  3rd time: the user gives up.
Reviews are accepted automatically (pipeline intent, baseline contract or refusal); correctness is
judged later by blind adjudication. Only `prompt`, `language` and `fact_sheet` are read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASET_V3 = ROOT / "dataset" / "v3" / "cases.jsonl"
MAX_REPLIES = 2

_TEXT = {
    "vi": {"facts": "Thông tin bổ sung:", "empty": "Tôi không có thêm thông tin; hãy làm đúng theo "
           "những gì tôi đã nêu.", "again": "Tôi không có thêm thông tin nào khác."},
    "en": {"facts": "More details:", "empty": "I have no more details; please go with what I "
           "already said.", "again": "I don't have any other information."},
}


def user_view(index: int) -> dict[str, Any]:
    """The fields the simulated user may read."""
    lines = DATASET_V3.read_text(encoding="utf-8").splitlines()
    if len(lines) != 100 or not 1 <= index <= 100:
        raise ValueError("case index outside frozen dataset v3")
    case = json.loads(lines[index - 1])
    return {"id": case["id"], "prompt": case["prompt"], "language": case["language"],
            "fact_sheet": case["fact_sheet"]}


def reply(view: dict[str, Any], replies_so_far: int) -> str | None:
    """The user's reply to the arm's next question; None means the user gives up."""
    text = _TEXT[view["language"]]
    if replies_so_far >= MAX_REPLIES:
        return None
    if replies_so_far == 1:
        return text["again"]
    facts = [item["answer"] for item in view["fact_sheet"]]
    if not facts:
        return text["empty"]
    return text["facts"] + "\n" + "\n".join(f"- {fact}" for fact in facts)
