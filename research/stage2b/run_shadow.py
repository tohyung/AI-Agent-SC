#!/usr/bin/env python3
"""Run research-only IntentSpec extraction against frozen candidate cases."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from marlowe_ai_agent.marlowe_agent.models import LLMError  # noqa: E402
from research.stage2a import verify_freeze  # noqa: E402
from research.stage2b.intent_spec import SCHEMA_VERSION  # noqa: E402
from research.stage2b.scoring import FrozenCandidateAdapter, MANIFEST  # noqa: E402
from research.stage2b.shadow_extractor import (  # noqa: E402
    IntentShadowExtractor, InvalidModelOutput, LegacyReasonerTransport, build_prompt,
)


USAGE_FIELDS = ("calls", "latency_seconds", "prompt_tokens", "completion_tokens", "cost")


def _usage_delta(before: dict, after: dict) -> dict:
    delta = {}
    for field in USAGE_FIELDS:
        current = after.get(field)
        previous = before.get(field)
        delta[field] = (current - (previous or 0)) if current is not None else None
    return delta


def _usage_total(per_case: list[dict]) -> dict:
    return {field: (sum(item[field] for item in per_case)
                    if all(item[field] is not None for item in per_case) else None)
            for field in USAGE_FIELDS}


def _sanitized_model_error(exc: Exception) -> dict[str, str]:
    detail = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in detail or "timed out" in detail:
        return {"code": "provider_timeout", "message": "Model request timed out."}
    if isinstance(exc, json.JSONDecodeError) or isinstance(exc.__cause__, json.JSONDecodeError):
        return {"code": "invalid_model_json", "message": "Model returned invalid JSON."}
    if isinstance(exc, InvalidModelOutput):
        return {"code": "invalid_model_output", "message": "Model returned a non-object value."}
    return {"code": "provider_error", "message": "Model request failed."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id")
    parser.add_argument("--split", choices=("development", "validation"), default="development")
    parser.add_argument("--all-canonical", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.live and args.output is None:
        parser.error("--live requires an explicit --output path")
    if args.all_canonical and (args.case_id or args.split != "development"):
        parser.error("--all-canonical cannot be combined with --case-id or --split")
    try:
        aggregate = verify_freeze.verify_freeze(MANIFEST)
        candidates = FrozenCandidateAdapter().load(
            split=args.split, all_canonical=args.all_canonical, case_id=args.case_id)
        model = LegacyReasonerTransport(args.model) if args.live else None
        extractor = IntentShadowExtractor(model) if model is not None else None
    except (OSError, ValueError, LLMError) as exc:
        print(f"Shadow precheck failed: {exc}", file=sys.stderr)
        return 2

    writer = args.output.open("w", encoding="utf-8") if args.output else sys.stdout
    failed = False
    count = 0
    case_usage = []
    try:
        for candidate in candidates:
            history = candidate["requirement_history"]
            record = {
                "case_id": candidate["case_id"],
                "split": candidate["split"],
                "model": model.reasoner.model if model is not None else None,
                "schema_version": SCHEMA_VERSION,
                "source_corpus_version": "stage2a-v1",
                "source_corpus_aggregate_sha256": aggregate,
                "prediction": None,
                "validation_errors": [],
                "usage": None,
                "run_status": "dry_run" if extractor is None else "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if extractor is None:
                system, user = build_prompt(history)
                record["prompt"] = {"system": system, "user": user}
            else:
                usage_before = model.usage()
                try:
                    prediction = extractor.extract(history)
                except (LLMError, TimeoutError, json.JSONDecodeError, InvalidModelOutput) as exc:
                    record["run_status"] = "model_error"
                    record["model_error"] = _sanitized_model_error(exc)
                    failed = True
                else:
                    record["prediction"] = prediction.to_dict()
                    record["validation_errors"] = prediction.validation_errors(
                        expected_history=history)
                finally:
                    record["usage"] = _usage_delta(usage_before, model.usage())
                case_usage.append(record["usage"])
            writer.write(json.dumps(record, ensure_ascii=False) + "\n")
            writer.flush()
            count += 1
    finally:
        if args.output:
            writer.close()
    if args.output:
        print(f"Wrote {count} shadow records to {args.output}")
        if model is not None:
            print("Aggregate usage: " + json.dumps(_usage_total(case_usage)))
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
