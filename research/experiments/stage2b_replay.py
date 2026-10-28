"""Offline replay of journaled first-pass Stage 2B outputs through current code.

No model is called. Each stored extraction output (compact draft or full core)
is paired with the requirement history active when it was recorded, then run
through today's deterministic layer. Repair patches are not replayed: their
requests depend on repair prompts that changed across policy versions.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from research.stage2b.core_draft import DRAFT_FIELDS
from research.stage2b.intent_spec import CORE_FIELDS, CORE_SCHEMA_VERSION_V4
from research.stage2b.projector import classify_projection, project_intent_spec
from research.stage2b.repair_policy import REPAIR_POLICY_VERSION, diagnostic_codes
from research.stage2b.shadow_extractor import IntentShadowExtractor


ROOT = Path(__file__).resolve().parents[2]
RUN_ROOTS = ("runs/roleplay-main-batch20", "runs/roleplay-main-batch80")
MODES = ("extract", "normalized")


class _StoredOutput:
    """Return one stored output; any second request means a repair was attempted."""

    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output
        self.calls = 0

    def generate(self, system: str, user: str) -> dict[str, Any]:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("replay cannot serve a repair request")
        return json.loads(json.dumps(self.output))


def output_kind(output: Any) -> str | None:
    if not isinstance(output, dict):
        return None
    if set(output) == DRAFT_FIELDS:
        return "draft"
    if set(output) == CORE_FIELDS:
        return "core"
    return None


def _cited_version(output: dict[str, Any]) -> int:
    versions = [item.get("requirement_version")
                for claim in output.get("claims") or [] if isinstance(claim, dict)
                for item in claim.get("evidence") or [] if isinstance(item, dict)]
    return max([value for value in versions if type(value) is int] or [1])


def _attempts(case_dir: Path) -> list[dict[str, Any]]:
    records = [json.loads(path.read_text(encoding="utf-8"))
               for path in sorted(case_dir.glob("attempt-*.json"))]
    return sorted((item for item in records if item.get("recorded_at_utc")),
                  key=lambda item: item["recorded_at_utc"])


def _schema_version(attempt: dict[str, Any], output: dict[str, Any]) -> str:
    if isinstance(output.get("schema_version"), str):
        return output["schema_version"]
    candidate = attempt.get("candidate")
    core = candidate.get("semantic_core") if isinstance(candidate, dict) else None
    version = core.get("schema_version") if isinstance(core, dict) else None
    return version if isinstance(version, str) else CORE_SCHEMA_VERSION_V4


def pair_outputs(case_dir: Path) -> list[dict[str, Any]]:
    """Pair each first-pass output with the history prefix it was produced from."""
    journal = case_dir / "logical-model-outputs.jsonl"
    if not journal.exists():
        return []
    attempts = _attempts(case_dir)
    paired = []
    for line_number, line in enumerate(journal.read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(line)
        output = record["output"]
        kind = output_kind(output)
        if kind is None:
            continue
        owner = next((item for item in attempts
                      if item["recorded_at_utc"] >= record["recorded_at_utc"]), None)
        history = owner.get("requirement_history") if owner else None
        cited = _cited_version(output)
        if not isinstance(history, list) or len(history) < cited:
            paired.append({"line": line_number, "kind": kind, "paired": False,
                           "recorded_at_utc": record["recorded_at_utc"]})
            continue
        paired.append({
            "line": line_number, "kind": kind, "paired": True,
            "recorded_at_utc": record["recorded_at_utc"],
            "attempt": owner.get("attempt"), "case_id": owner.get("case_id"),
            "history": history[:max(cited, 1)],
            "schema_version": _schema_version(owner, output), "output": output,
        })
    return paired


def replay_output(output: dict[str, Any], history: list[dict[str, Any]],
                  schema_version: str, mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unknown replay mode: {mode}")
    model = _StoredOutput(output)
    extractor = IntentShadowExtractor(model, core_schema_version=schema_version)
    try:
        if mode == "extract":
            core = extractor.extract(history)
        else:
            core, _ = extractor.extract_with_validation_feedback(history, max_repairs=0)
        core_errors = extractor.validation_errors(core, history)
        projection = project_intent_spec(core, expected_history=history)
        full_errors = projection.intent_spec.validation_errors(expected_history=history)
        classification = classify_projection(core_errors, full_errors,
                                             projection.projection_diagnostics)
    except Exception as exc:  # noqa: BLE001 - a crash is a replay result, not a skip
        return {"classification": "REPLAY_ERROR", "error_type": type(exc).__name__,
                "core_error_count": None, "error_codes": [], "resolution": None}
    data = core.to_dict()
    return {"classification": classification,
            "core_error_count": len(set(core_errors)),
            "full_error_count": len(set(full_errors)),
            "error_codes": diagnostic_codes(core_errors + full_errors),
            "resolution": data.get("predicted_resolution"),
            "normalization_count": len(extractor.normalization_actions)}


def replay_runs(roots: list[Path]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {}
    for root in roots:
        for case_dir in sorted(root.glob("case-*")):
            rows = []
            for item in pair_outputs(case_dir):
                row = {key: item[key] for key in ("line", "kind", "paired", "recorded_at_utc")}
                if item["paired"]:
                    row.update(attempt=item["attempt"], schema_version=item["schema_version"],
                               history_versions=len(item["history"]))
                    for mode in MODES:
                        row[mode] = replay_output(item["output"], item["history"],
                                                  item["schema_version"], mode)
                rows.append(row)
            cases[case_dir.name] = {"outputs": rows}
    return {"cases": cases, "summary": summarize(cases)}


def summarize(cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"cases": len(cases)}
    rows = [row for case in cases.values() for row in case["outputs"]]
    paired = [row for row in rows if row["paired"]]
    summary["outputs"] = len(rows)
    summary["outputs_paired"] = len(paired)
    for mode in MODES:
        classes = Counter(row[mode]["classification"] for row in paired)
        codes = Counter(code for row in paired for code in row[mode]["error_codes"])
        case_pass = [name for name, case in cases.items()
                     if any(row["paired"] and row[mode]["classification"] == "PASS"
                            for row in case["outputs"])]
        latest_pass = []
        for name, case in cases.items():
            done = [row for row in case["outputs"] if row["paired"]]
            if done and done[-1][mode]["classification"] == "PASS":
                latest_pass.append(name)
        eras: dict[str, list[int]] = {}
        for row in paired:
            counts = eras.setdefault(f"{row['kind']}:{row['schema_version']}", [0, 0])
            counts[0] += 1
            counts[1] += row[mode]["classification"] == "PASS"
        summary[mode] = {
            "output_classification": dict(sorted(classes.items())),
            "output_pass_rate": (round(classes["PASS"] / len(paired), 4) if paired else None),
            "pass_by_output_era": {key: {"outputs": total, "pass": passed}
                                   for key, (total, passed) in sorted(eras.items())},
            "error_code_frequency": dict(codes.most_common()),
            "cases_with_any_pass": len(case_pass),
            "cases_latest_output_pass": len(latest_pass),
        }
    return summary


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay stored Stage 2B outputs offline")
    parser.add_argument("--run-root", action="append", type=Path,
                        help="Case-directory root; repeatable. Defaults to roleplay batches.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = args.run_root or [ROOT / item for item in RUN_ROOTS]
    report = {"record_type": "stage2b_offline_replay_v1",
              "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "code_head": _git_head(), "repair_policy_version": REPAIR_POLICY_VERSION,
              "model_calls": 0, **replay_runs(roots)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as writer:
        json.dump(report, writer, ensure_ascii=False, indent=2)
        writer.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
