"""Score one frozen-corpus shadow run without recomputing scoring formulas."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from research.stage2a import foundation
from research.stage2a import verify_freeze
from research.stage2b.live_safety import (EXPERIMENT_VERSION, STAGE2A_AGGREGATE_SHA256,
                                          require_same_experiment_identity, summary_path,
                                          raw_sha256)
from research.stage2b.scoring import (MANIFEST, FrozenCandidateAdapter, _active_critical,
                                      _key, score_predictions)
from research.stage2b.profile_diagnostic import direct_payment_profile_match


def profile_diagnostic(candidates: list[dict]) -> dict:
    source_owner = []
    for candidate in candidates:
        if any(claim.get("kind") == "payment_source_account_owner"
               for claim in candidate["claims"]):
            source_owner.append(candidate["case_id"])
    # A missing required source-owner claim is sufficient to rule out the
    # exact direct-payment profile; candidate annotations are not IntentSpecs.
    exact = [] if not source_owner else None
    total = foundation.load_corpus()
    return {"canonical": len(candidates),
            "development": sum(case["split"] == "development" for case in candidates),
            "public_validation": sum(case["split"] == "validation" for case in candidates),
            "mutations_excluded": sum(case["mutation"] is not None for case in total),
            "source_owner_case_ids": source_owner,
            "exact_direct_payment_case_ids": exact}


def build_report(records: list[dict], candidates: list[dict]) -> dict:
    by_id = {record["case_id"]: record for record in records}
    if len(by_id) != len(records) or any(item["case_id"] not in
                                        {candidate["case_id"] for candidate in candidates}
                                        for item in records):
        raise ValueError("duplicate or unknown case ID")
    predictions = {case_id: record["prediction"] for case_id, record in by_id.items()
                   if record.get("prediction") is not None}
    score = score_predictions(predictions, candidates, run_records=by_id)
    cases = []
    for candidate in candidates:
        record = by_id.get(candidate["case_id"], {})
        core = record.get("semantic_core") or {}
        predicted = _active_critical(core.get("claims", []))
        expected = _active_critical(candidate["claims"])
        matched = sum((Counter(map(_key, predicted)) & Counter(map(_key, expected))).values())
        spec = record.get("prediction")
        match = direct_payment_profile_match(spec) if isinstance(spec, dict) else None
        cases.append({"case_id": candidate["case_id"], "split": candidate["split"],
                      "family": candidate.get("family"),
                      "expected_resolution": candidate["expected_resolution"],
                      "run_status": record.get("run_status", "not_attempted"),
                      "model_error": record.get("model_error"),
                      "core_valid": bool(core) and not record.get("core_validation_errors"),
                      "projection_classification": record.get("projection_classification"),
                      "predicted_resolution": core.get("predicted_resolution"),
                      "resolution_match": core.get("predicted_resolution") == candidate["expected_resolution"],
                      "critical_expected": len(expected), "critical_predicted": len(predicted),
                      "critical_matched": matched,
                      "required_clarifications": len(core.get("required_clarifications", [])),
                      "compiler_profile_match": match,
                      "unexpected_profile_entry": match == "EXACT_SUPPORTED_PROFILE"})
    return {"experiment_version": EXPERIMENT_VERSION, "profile_diagnostic": profile_diagnostic(candidates),
            "score": score, "cases": cases}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lane-a-summary", type=Path)
    args = parser.parse_args(argv)
    candidates = FrozenCandidateAdapter().load(all_canonical=True)
    if verify_freeze.verify_freeze(MANIFEST) != STAGE2A_AGGREGATE_SHA256:
        raise ValueError("frozen aggregate differs from v1 baseline")
    if len(candidates) != 20 or profile_diagnostic(candidates)["source_owner_case_ids"]:
        raise ValueError("frozen corpus profile facts differ from v1 preflight")
    if args.input is None:
        print(json.dumps(profile_diagnostic(candidates)))
        return 0
    if args.output is None or args.output.exists():
        parser.error("--output must be a new path when --input is given")
    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines()]
    if any(record.get("experiment_version") != EXPERIMENT_VERSION for record in records):
        parser.error("run version mismatch")
    if any(record.get("source_corpus_aggregate_sha256") != STAGE2A_AGGREGATE_SHA256
           for record in records):
        parser.error("frozen aggregate mismatch")
    lane_b_summary = json.loads(summary_path(args.input).read_text(encoding="utf-8"))
    if lane_b_summary.get("raw_output_sha256") != raw_sha256(args.input):
        parser.error("Lane B raw output hash differs from execution summary")
    if any(any(record.get(field) != lane_b_summary.get(field)
               for field in ("experiment_version", "code_sha", "model")) for record in records):
        parser.error("Lane B records differ from execution summary identity")
    if args.lane_a_summary:
        lane_a_summary = json.loads(args.lane_a_summary.read_text(encoding="utf-8"))
        try:
            require_same_experiment_identity(lane_a_summary, lane_b_summary)
        except ValueError as exc:
            parser.error(str(exc))
    report = build_report(records, candidates)
    with args.output.open("x", encoding="utf-8") as writer:
        json.dump(report, writer, ensure_ascii=False, indent=2)
        writer.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
