"""Live Stage 2B arm for the A2 protocol: original prompt only, no roleplay.

Each dev case gets one extraction through the production Stage 2B port with up
to three validation repairs. Only the case ID and prompt leave the dataset;
evaluator fields are read later by a separate scorer. One record per case is
written exclusively, so an interrupted run resumes at the next missing case.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.experiments.online_tuning_batch01 import DATASET
from research.integrations.model_replay import JournaledModel
from research.integrations.stage2b import Stage2BExtractionPort
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V4
from research.stage2b.repair_policy import REPAIR_POLICY_VERSION


ROOT = Path(__file__).resolve().parents[2]
DEV_CASES = tuple(index for index in range(1, 57))
EXCLUDED_CASES = {57: "evaluator fields were read during roleplay on 2026-10-27"}
MAX_REPAIRS = 3


def dev_prompts(indices: tuple[int, ...] = DEV_CASES) -> list[tuple[int, str, str]]:
    """Return (index, case_id, prompt) only; nothing else from the record is kept."""
    if any(index in EXCLUDED_CASES or not 1 <= index <= 56 for index in indices):
        raise ValueError("evaluation arm accepts only dev cases 1-56")
    with DATASET.open(encoding="utf-8") as source:
        lines = source.read().splitlines()
    if len(lines) != 100:
        raise ValueError("frozen dataset must contain 100 cases")
    selected = []
    for index in indices:
        record = json.loads(lines[index - 1])
        selected.append((index, record["id"], record["prompt"]))
    return selected


def evaluate_case(model: Any, index: int, case_id: str, prompt: str, *,
                  schema_version: str = CORE_SCHEMA_VERSION_V4) -> dict[str, Any]:
    history = [{"version": 1, "messages": [prompt]}]
    source = ArtifactEnvelope("requirement-history", "v1", "user_input",
                              ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                              AuthorityLevel.NO_AUTHORITY, history)
    calls_before = model.llm_calls
    execution = Stage2BExtractionPort(model).execute(
        [source], StageContext(f"stage2b-eval:{case_id}", {
            "core_schema_version": schema_version,
            "max_core_validation_repairs": MAX_REPAIRS,
        }))
    result = execution.result
    candidate = execution.artifacts[0].payload if execution.artifacts else None
    record: dict[str, Any] = {
        "case_index": index, "case_id": case_id, "schema_version": schema_version,
        "run_status": result.run_status.value, "semantic_status": result.semantic_status,
        "safe_error": result.safe_error, "physical_calls": model.llm_calls - calls_before,
        "telemetry": result.telemetry,
    }
    if candidate is not None:
        initial = candidate["initial_core_validation_errors"]
        final_valid = not candidate["core_validation_errors"] and not candidate[
            "full_validation_errors"] and candidate["projection_classification"] == "PASS"
        record.update({
            "first_pass_valid": not initial and final_valid,
            "first_pass_error_count": len(set(initial)),
            "final_valid": final_valid,
            "final_core_error_count": len(set(candidate["core_validation_errors"])),
            "final_full_error_count": len(set(candidate["full_validation_errors"])),
            "projection_classification": candidate["projection_classification"],
            "predicted_resolution": candidate["semantic_core"].get("predicted_resolution"),
            "semantic_core": candidate["semantic_core"],
        })
    return record


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def run_arm(arm_dir: Path, model_factory: Callable[[Callable[[str], None]], Any], *,
            arm: str, indices: tuple[int, ...] = DEV_CASES,
            emit: Callable[[str], None] = print) -> int:
    """Return 0 when every selected case has a record, 3 on a non-model failure."""
    arm_dir.mkdir(parents=True, exist_ok=True)
    journal = arm_dir / "outbound-attempts.jsonl"
    current: dict[str, Any] = {}

    def before_request(phase: str) -> None:
        with journal.open("a", encoding="utf-8") as writer:
            writer.write(json.dumps({"case_id": current.get("case_id"), "phase": phase,
                                     "reserved_at_utc": datetime.now(timezone.utc).isoformat()},
                                    ensure_ascii=False) + "\n")
            writer.flush()
            os.fsync(writer.fileno())

    model = JournaledModel(model_factory(before_request), arm_dir / "logical-model-outputs.jsonl")
    head = _git_head()
    for index, case_id, prompt in dev_prompts(indices):
        target = arm_dir / f"case-{index:02d}.json"
        if target.exists():
            continue
        current["case_id"] = case_id
        record = evaluate_case(model, index, case_id, prompt)
        error = record["safe_error"] or {}
        if error and error.get("model_content_received") is not True:
            # Provider, network or configuration failure: not a model result.
            emit(f"case {index:02d}: {error.get('code')}; stopping without a record")
            return 3
        record.update({"arm": arm, "code_head": head, "model": getattr(model, "model", None),
                       "repair_policy_version": REPAIR_POLICY_VERSION,
                       "recorded_at_utc": datetime.now(timezone.utc).isoformat()})
        with target.open("x", encoding="utf-8") as writer:
            json.dump(record, writer, ensure_ascii=False, indent=2)
            writer.write("\n")
        emit(f"case {index:02d}: first_pass_valid={record.get('first_pass_valid')} "
             f"final_valid={record.get('final_valid')} calls={record['physical_calls']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one live Stage 2B evaluation arm")
    parser.add_argument("--arm", required=True, help="Arm label, e.g. BASE or A2")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--cases", help="Comma-separated dev case indices (default 1-56)")
    args = parser.parse_args()
    indices = (tuple(int(item) for item in args.cases.split(",")) if args.cases
               else DEV_CASES)

    def factory(before_request: Callable[[str], None]) -> Any:
        from research.integrations.model_transport import ModelTransport
        return ModelTransport(before_request=before_request, api_style="chat",
                              max_tokens=16000, disable_reasoning=True,
                              retry_empty=False, request_json_object=False)

    return run_arm(args.out_dir, factory, arm=args.arm, indices=indices)


if __name__ == "__main__":
    raise SystemExit(main())
