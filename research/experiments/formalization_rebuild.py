"""Rebuild an AFF arm's cores offline from its recorded drafts, with no model call.

A builder fix that changes only claims and questions, never which draft
problems are reported, leaves every repair prompt unchanged. Replaying the
recorded drafts through `extract_fact_core` then gives exactly the result a
live rerun would have given. Each case is checked: the replay must consume the
same drafts and report the same problems per attempt, otherwise the case is
marked `rebuild_mismatch` and keeps its original result. Records are written to
a new directory; the original arm is never modified.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research.experiments.formalization_eval import (
    MAX_REPAIRS,
    ROOT,
    aff_result_fields,
    dev_prompts,
)
from research.formalization.fact_extractor import extract_fact_core


class _RecordedDrafts:
    """Stands in for the model: returns the recorded drafts in order."""

    def __init__(self, drafts: list[Any]):
        self.drafts = list(drafts)
        self.served = 0

    def generate(self, system: str, user: str) -> Any:
        if self.served == len(self.drafts):
            raise LookupError("replay needs a draft the live run never received")
        self.served += 1
        return self.drafts[self.served - 1]


def rebuild_record(record: dict[str, Any], prompt: str) -> dict[str, Any]:
    """The record with its core rebuilt by the current builder, or flagged."""
    attempts = record.get("fact_draft_attempts")
    if not attempts:  # model error before any draft: nothing to rebuild
        return dict(record)
    history = [{"version": 1, "messages": [prompt]}]
    replay = _RecordedDrafts([attempt["draft"] for attempt in attempts])
    try:
        result = extract_fact_core(replay, history, max_repairs=MAX_REPAIRS)
    except LookupError:
        result = None
    same = (result is not None and replay.served == len(attempts)
            and [a["problems"] for a in result["attempts"]]
            == [a["problems"] for a in attempts])
    if not same:
        return {**record, "rebuild_mismatch": True}
    return {**record, **aff_result_fields(result), "rebuild_mismatch": False}


def rebuild_arm(source: Path, target: Path) -> dict[str, Any]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    prompts = {index: prompt for index, _case_id, prompt in dev_prompts()}
    target.mkdir(parents=True, exist_ok=False)
    changed, mismatched = [], []
    for path in sorted(source.glob("case-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        rebuilt = rebuild_record(record, prompts[record["case_index"]])
        if rebuilt.get("rebuild_mismatch"):
            mismatched.append(record["case_index"])
        elif any(rebuilt.get(key) != record.get(key)
                 for key in ("semantic_core", "final_valid", "semantic_status")):
            changed.append(record["case_index"])
        rebuilt.update({"rebuilt_from_code_head": record.get("code_head"),
                        "rebuilt_with_code_head": head,
                        "rebuilt_at_utc": datetime.now(UTC).isoformat()})
        (target / path.name).write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2)
                                        + "\n", encoding="utf-8")
    return {"cases": len(list(target.glob("case-*.json"))), "changed": changed,
            "mismatched": mismatched}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild an AFF arm's cores offline")
    parser.add_argument("source", type=Path, help="recorded AFF arm directory")
    parser.add_argument("target", type=Path, help="new directory for rebuilt records")
    args = parser.parse_args()
    print(json.dumps(rebuild_arm(args.source, args.target)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
