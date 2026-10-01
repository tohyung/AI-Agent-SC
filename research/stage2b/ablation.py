"""Offline core/projection ablation of arbitrary historical shadow JSONL."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from research.stage2b.intent_spec import (
    extract_core_view, validate_intent_spec, validate_shadow_semantic_core,
)
from research.stage2b.projector import project_intent_spec


def _category(error: str) -> str:
    if error.startswith(("missing fields", "unknown top-level", "invalid schema_version")):
        return "CORE_SCHEMA"
    if "evidence" in error or "supersession" in error or "derived_from" in error:
        return "CORE_PROVENANCE"
    if error.startswith("scope ") or "scope_id" in error:
        return "CORE_SCOPE"
    if "normalization_basis" in error:
        return "CORE_NORMALIZATION"
    if "clarification" in error or "business question" in error:
        return "CORE_CLARIFICATION"
    if "conflict" in error:
        return "CORE_CONFLICT"
    if "resolution" in error or "prediction" in error:
        return "CORE_RESOLUTION"
    if "observation" in error or "mutation" in error:
        return "CORE_UNSUPPORTED"
    return "CORE_CLAIM"


def ablate(path: Path) -> dict:
    raw = path.read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    result = {"raw_sha256": hashlib.sha256(raw).hexdigest().upper(),
              "case_count": len(rows), "cases": []}
    for row in rows:
        prediction = row.get("prediction")
        core = extract_core_view(prediction) if isinstance(prediction, dict) else {}
        core_errors = validate_shadow_semantic_core(core)
        projected = project_intent_spec(core)
        full_errors = validate_intent_spec(projected.intent_spec.to_dict())
        projection_errors = (list((Counter(full_errors) - Counter(core_errors)).elements())
                             if not core_errors else None)
        historical_errors = row.get("validation_errors", [])
        historical_noncore = list((Counter(historical_errors) - Counter(core_errors)).elements())
        result["cases"].append({
            "case_id": row.get("case_id"), "core_valid": not core_errors,
            "projected_full_valid": not full_errors,
            "core_error_count": len(core_errors),
            "projection_error_count": len(projection_errors) if projection_errors is not None else None,
            "historical_noncore_error_count": len(historical_noncore),
            "core_categories": dict(sorted(Counter(map(_category, core_errors)).items())),
            "core_errors": core_errors, "projection_errors": projection_errors,
        })
    result["core_valid_count"] = sum(case["core_valid"] for case in result["cases"])
    result["projected_full_valid_count"] = sum(case["projected_full_valid"]
                                               for case in result["cases"])
    result["core_error_count"] = sum(case["core_error_count"] for case in result["cases"])
    result["projection_error_count_on_valid_cores"] = sum(
        case["projection_error_count"] or 0 for case in result["cases"])
    result["historical_noncore_error_count"] = sum(case["historical_noncore_error_count"]
                                                 for case in result["cases"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(ablate(args.path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
